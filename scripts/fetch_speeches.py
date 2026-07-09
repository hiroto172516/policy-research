#!/usr/bin/env python3
"""
STEP3 (収集): 国会会議録検索システム 公式API から議員の発言を取得する。

  API: https://kokkai.ndl.go.jp/api.html （認証不要）
  出力: data/speeches/<member_id>.json  （発言の生データ＋メタ）

【ネットワーク注意 ★重要】
  会議録API(kokkai.ndl.go.jp)は無認証・無料で稼働しているが、**NDLのCloudFront WAFが
  データセンター/クラウドのIPをホスト全体で403遮断**する（この環境・Anthropic WebFetchとも403を実測）。
  APIそのものは正常。IPが弾かれているだけなので、次のいずれかで取得する:
    --via direct : 非遮断ネットワーク（事務所回線等）で直結（本来の正攻法・全速）
    --via jina   : Jina Reader(r.jina.ai)を串にして取得（この環境で疎通確認済）
    --via auto   : 既定。まず直結、403等ならJinaへ自動フォールバック
  Jina は無料枠だとレート制限が厳しい → 環境変数 JINA_API_KEY を設定すると緩和（合意済み方針）。

使い方:
  python3 scripts/fetch_speeches.py --via auto --since 2025-01-01   # 名簿全員
  python3 scripts/fetch_speeches.py --member H-0001 --via jina      # 1名(Jina経由)
  JINA_API_KEY=xxx python3 scripts/fetch_speeches.py --via jina     # キーで高レート
  python3 scripts/fetch_speeches.py --dry-run                       # 取得せずURLのみ
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urlencode

import common

API = "https://kokkai.ndl.go.jp/api/speech"
UA = "JCLP-policy-research/0.1 (contact: JCLP jimukyoku)"  # HTTPヘッダはASCIIのみ


def _http_get(url: str, timeout: int = 45) -> tuple[int, str]:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    return r.status_code, r.text


def _jina_get(api_url: str, timeout: int = 60) -> str:
    """Jina Reader を串に会議録APIを取得し、JSON文字列を返す。"""
    import requests
    headers = {"User-Agent": UA, "X-Return-Format": "text"}
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    r = requests.get("https://r.jina.ai/" + api_url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Jina HTTP {r.status_code}")
    return r.text


def _extract_json(body: str) -> dict:
    """直結の生JSON、またはJina封筒付きテキストから最初のJSONオブジェクトを取り出す。"""
    i = body.find("{")
    if i < 0:
        raise RuntimeError("JSONが見つかりません（遮断ページの可能性）")
    obj, _ = json.JSONDecoder().raw_decode(body[i:])
    return obj


def get_api_json(url: str, via: str) -> dict:
    """via=direct/jina/auto に応じて会議録APIのJSONを取得する。"""
    if via in ("direct", "auto"):
        try:
            code, text = _http_get(url)
            if code == 200 and "{" in text:
                return _extract_json(text)
            if via == "direct":
                raise RuntimeError(f"HTTP {code}（IP遮断の可能性）")
        except Exception:
            if via == "direct":
                raise
        # auto: 直結失敗 → Jina
    return _extract_json(_jina_get(url))


def build_url(speaker: str, since: str | None, until: str | None,
              start: int = 1, maximum: int = 30, any_kw: str | None = None) -> str:
    params = {
        "speaker": speaker,
        "recordPacking": "json",
        "maximumRecords": maximum,
        "startRecord": start,
    }
    if any_kw:
        params["any"] = any_kw     # 本文キーワード（トピック絞り込み）
    if since:
        params["from"] = since
    if until:
        params["until"] = until
    return f"{API}?{urlencode(params)}"


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def fetch_one(speaker: str, since, until, dry_run: bool,
              via: str = "auto", max_pages: int = 10, any_kw: str | None = None,
              exact_speaker: bool = True) -> dict:
    """会議録APIの speaker 検索は姓の部分一致で同姓別人が混入する。
    exact_speaker=True で発言者名が検索名と完全一致するものだけ残す。"""
    url = build_url(speaker, since, until, any_kw=any_kw)
    if dry_run:
        return {"speaker": speaker, "url": url, "dry_run": True, "speeches": []}
    speeches: list[dict] = []
    dropped = 0
    target = _norm(speaker)
    start = 1
    pages = 0
    while pages < max_pages:
        url = build_url(speaker, since, until, start=start, any_kw=any_kw)
        data = get_api_json(url, via)
        for rec in data.get("speechRecord", []):
            sp_name = rec.get("speaker")
            if exact_speaker and _norm(sp_name) != target:
                dropped += 1
                continue  # 同姓別人（例: 猪口邦子↔猪口幸子）を除外
            speeches.append({
                "date": rec.get("date"),
                "meeting": rec.get("nameOfMeeting"),
                "house": rec.get("nameOfHouse"),
                "speaker": sp_name,
                "speech": rec.get("speech"),
                "url": rec.get("speechURL"),
            })
        next_pos = data.get("nextRecordPosition")
        if not next_pos:
            break
        start = next_pos
        pages += 1
        time.sleep(1.0 if via != "direct" else 0.5)  # Jinaはレート制限に配慮
    return {"speaker": speaker, "url": url, "count": len(speeches),
            "dropped_other_speaker": dropped, "speeches": speeches}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", help="member_id を指定して1名だけ収集")
    ap.add_argument("--since", help="YYYY-MM-DD")
    ap.add_argument("--until", help="YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--via", choices=["auto", "direct", "jina"], default="auto",
                    help="取得経路。auto=直結→403でJina / direct=直結のみ / jina=Jina経由")
    ap.add_argument("--speaker-col", default="name",
                    help="発言者名の列（既定 name）。会議録APIは氏名で引く")
    ap.add_argument("--limit", type=int, help="先頭N名だけ（パイロット用）")
    ap.add_argument("--any", dest="any_kw", help="本文キーワードで絞る（例: 再生可能エネルギー）")
    args = ap.parse_args()

    common.ensure_dirs()
    roster = common.load_roster()
    if args.member:
        roster = [r for r in roster if r["member_id"] == args.member]
        if not roster:
            print(f"member_id={args.member} が名簿に見つかりません", file=sys.stderr)
            return 1
    if args.limit:
        roster = roster[: args.limit]

    for r in roster:
        # 会議録APIは発言者の氏名で引く（roster の name 列。合成データ等では member_id）。
        speaker = r.get(args.speaker_col) or r["member_id"]
        try:
            result = fetch_one(speaker, args.since, args.until, args.dry_run,
                               via=args.via, any_kw=args.any_kw)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {r['member_id']} 取得失敗: {e}", file=sys.stderr)
            continue
        out = common.SPEECHES / f"{r['member_id']}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        n = result.get("count", 0)
        print(f"{r['member_id']}: {'URL='+result['url'] if args.dry_run else str(n)+'件'} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

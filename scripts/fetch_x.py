#!/usr/bin/env python3
"""
STEP3 (SNS収集): 議員のX(旧Twitter)投稿を Jina Reader 経由で取得する。

【前提・重要】
  - x.com は **匿名アクセスがJinaで451ブロック**される（実測。データ取得検証メモと一致）。
    → **JINA_API_KEY（認証済みJina）が必須**。無い場合は取得しない（合意済み方針）。
  - 議員→Xアカウントの対応表 `data/x_handles.csv`（member_id,name,party,x_handle,note）が必要。
    x_handle は @ を除いたユーザー名（例: kantei）。公式に対応表は無いのでJCLPが用意/確認する。
  - Xは非発信議員を捉えられない（メモ L75）→ **会議録と併用が前提**。X由来の根拠は source=X で区別。
  - 取得できる投稿範囲はXの仕様に依存（ログイン制限が強い）。キー投入後にまず疎通・歩留りを検証する。

  出力: data/x_posts/<member_id>.json（投稿の生データ。会議録と同じ枠組みでClaude Codeが分類）

キー: 環境変数 JINA_API_KEY か、config/jina.key（gitignore・チャットに出さない）に置く。

使い方:
  python3 scripts/fetch_x.py --probe kantei            # 疎通・歩留り検証（対応表不要）
  python3 scripts/fetch_x.py --dry-run                 # 対象と取得URLの確認（キー不要）
  python3 scripts/fetch_x.py --member H-0013           # 1名
  python3 scripts/fetch_x.py --skip-existing --limit 50 # 未取得分を50名だけ取得
  python3 scripts/fetch_x.py --any エネルギー           # 本文キーワードで後段フィルタ
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sys
import time

import common

UA = "JCLP-policy-research/0.1 (contact: JCLP jimukyoku)"


def load_handles() -> list[dict]:
    p = common.DATA / "x_handles.csv"
    if not p.exists():
        print("data/x_handles.csv がありません（member_id,name,party,x_handle,note）", file=sys.stderr)
        return []
    with open(p, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("member_id")]


def jina_get(url: str, key: str, timeout: int = 60) -> str:
    import requests
    headers = {"User-Agent": UA, "X-Return-Format": "markdown",
               "Authorization": f"Bearer {key}"}
    r = requests.get("https://r.jina.ai/" + url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Jina HTTP {r.status_code}: {r.text[:120]}")
    return r.text


def _strip_md(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)      # 画像
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)   # リンク→表示文字
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_posts(markdown: str, handle: str) -> list[dict]:
    """Xプロフィールページ（Jina整形）から投稿を構造化抽出する。
    各投稿=本文・日付・パーマリンク・投稿者・本人/リポスト判定。本人投稿を優先。
    ※取得できるのはプロフィール初期表示分（概ね直近十数件）。深い履歴はX仕様上取れない。"""
    target = handle.lstrip("@").lower()
    posts, seen = [], set()
    # 各投稿は /status/<id> のパーマリンクを持つ。ID単位で切り出す。
    for m in re.finditer(r"@(\w+)\]\([^)]*\)\s*\[([^\]]+)\]\(https://x\.com/\w+/status/(\d+)\)(.*?)(?=/status/\d+|\n\* |\Z)",
                         markdown, re.S):
        author, date, sid, tail = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
        if sid in seen:
            continue
        seen.add(sid)
        # 本文＝tailからUI要素・数値・Show moreを除いた表示テキスト
        text = _strip_md(tail.split("Show more")[0])
        text = re.sub(r"^[\s*・>\-|]+", "", text)          # 先頭の箇条書き記号のみ除去（【は残す）
        text = re.sub(r"\[\]\([^)]*\)?\s*$", "", text)     # 末尾の空リンク残渣
        text = re.sub(r"\s*(Video \d+|00:00|\d+:\d+)\s*$", "", text).strip()
        # 直前が reposted かどうか（本人発でないrepost）
        ctx = markdown[max(0, m.start()-120):m.start()]
        is_repost = "reposted" in ctx.lower()
        if len(text) < 8:
            continue
        posts.append({
            "date": date, "text": text[:600], "author": author,
            "own": (author.lower() == target and not is_repost),
            "url": f"https://x.com/{author}/status/{sid}",
        })
    return posts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member")
    ap.add_argument("--any", dest="any_kw", help="本文キーワードで後段フィルタ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, help="取得対象を先頭N名に制限（バッチ実行用）")
    ap.add_argument("--skip-existing", action="store_true",
                    help="data/x_posts/<member_id>.json が既にある議員は取得しない")
    ap.add_argument("--probe", metavar="HANDLE",
                    help="対応表を使わず指定ハンドルで疎通・歩留り検証（例: --probe kantei）")
    args = ap.parse_args()

    common.ensure_dirs()
    out_dir = common.DATA / "x_posts"
    out_dir.mkdir(exist_ok=True)

    # --- 疎通・歩留り検証モード（対応表不要） ---
    if args.probe:
        key = common.get_jina_key()
        if not key:
            print("[STOP] Jinaキーが未取得。config/jina.key に置くか JINA_API_KEY を設定してください。", file=sys.stderr)
            return 2
        h = args.probe.lstrip("@")
        url = f"https://x.com/{h}"
        try:
            md = jina_get(url, key)
        except Exception as e:  # noqa: BLE001
            print(f"[NG] {url} 取得失敗: {e}", file=sys.stderr)
            return 1
        posts = extract_posts(md, h)
        print(f"[OK] @{h}: 応答 {len(md)}字 / 投稿ブロック抽出 {len(posts)}件")
        for p in posts[:5]:
            print("  -", p["text"][:90])
        (out_dir / f"_probe_{h}.json").write_text(
            json.dumps({"handle": h, "url": url, "raw_len": len(md), "posts": posts},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ 保存: data/x_posts/_probe_{h}.json（歩留りを確認して本格収集の可否を判断）")
        return 0

    rows = load_handles()
    if args.member:
        rows = [r for r in rows if r["member_id"] == args.member]
    targets = [r for r in rows if (r.get("x_handle") or "").strip()]
    if args.skip_existing:
        targets = [r for r in targets if not (out_dir / f"{r['member_id']}.json").exists()]
    if args.limit:
        targets = targets[: args.limit]
    missing = [r["member_id"] for r in rows if not (r.get("x_handle") or "").strip()]
    if missing:
        print(f"[INFO] x_handle 未記入: {len(missing)}名（{missing[:6]}…）→ 対応表を埋めてください")

    key = common.get_jina_key()
    if not args.dry_run and not key:
        print("[STOP] Jinaキーが未取得。x.com匿名は451でブロックされます。"
              "config/jina.key に置くか JINA_API_KEY を設定してから実行してください。", file=sys.stderr)
        return 2

    for r in targets:
        h = r["x_handle"].lstrip("@")
        url = f"https://x.com/{h}"
        if args.dry_run:
            print(f"{r['member_id']} {r['name']}: {url}")
            continue
        try:
            md = jina_get(url, key)
            posts = extract_posts(md, h)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {r['member_id']} 取得失敗: {e}", file=sys.stderr)
            continue
        if args.any_kw:
            posts = [p for p in posts if args.any_kw in p["text"]]
        rec = {"member_id": r["member_id"], "handle": h, "source": "X",
               "url": url, "count": len(posts), "posts": posts}
        (out_dir / f"{r['member_id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{r['member_id']} {r['name']}(@{h}): {len(posts)}件 -> x_posts/{r['member_id']}.json")
        time.sleep(1.5)  # Jinaレート配慮

    if args.dry_run and not targets:
        print("（x_handle 記入済みの行がありません。対応表を埋めると取得URLが表示されます）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

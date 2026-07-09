#!/usr/bin/env python3
"""
STEP1 enrich: 参議院議員の profile_url と 当選回数(elected_count) を名簿に補完する。

  背景: 衆の経歴(career)は profile ページの経歴文から取得できたが、**参議院の公式
        プロフィールには経歴文（学歴・職歴）が無い**（当選年・当選回数・所属委員会のみ）。
        → 参の career（略歴プロース）は公式サイトからは取得不可。ここでは公式に存在する
          当選回数と profile_url だけを補完し、career は空のままにする（捏造しない）。

  出典（到達確認済み）:
    参 議員一覧: https://www.sangiin.go.jp/japanese/joho1/kousei/giin/<回>/giin.htm
       各氏名 → ../profile/<番号>.htm（当選回数「当選 N 回」を含む）
  更新列（参のみ）: profile_url, elected_count

使い方:
  python3 scripts/enrich_sangiin.py                 # 参全員の当選回数・profile_url
  python3 scripts/enrich_sangiin.py --session 218
  python3 scripts/enrich_sangiin.py --dry-run
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
import time

import common

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
HOST = "https://www.sangiin.go.jp"
GIIN = HOST + "/japanese/joho1/kousei/giin/{session}/giin.htm"
PROF_BASE = HOST + "/japanese/joho1/kousei/giin/profile/"


def _get(url: str) -> bytes:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    return r.content


def _clean(s: str) -> str:
    return re.sub(r"[　\s]+", " ", re.sub(r"[　\s]*君$", "", s)).strip()


def name_to_profile(session: str) -> dict[str, str]:
    html = _get(GIIN.format(session=session)).decode("utf-8", "replace")
    out = {}
    for href, inner in re.findall(r'<a[^>]+href="([^"]*profile/\d+\.htm)"[^>]*>(.*?)</a>', html, re.S):
        name = _clean(re.sub(r"<[^>]+>", "", inner))
        # 通称[本名] → 通称
        m = re.match(r"^([^\[［]+?)\s*[\[［]", name)
        if m:
            name = _clean(m.group(1))
        url = PROF_BASE + href.split("/")[-1]
        out[name] = url
    return out


def elected_count(profile_html: str) -> str:
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", profile_html))
    m = re.search(r"当選\s*([\d０-９]+)\s*回", txt)
    if not m:
        return ""
    z2h = str.maketrans("０１２３４５６７８９", "0123456789")
    return m.group(1).translate(z2h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="218")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    roster = common.load_roster()
    n2p = name_to_profile(args.session)
    print(f"参 profile リンク: {len(n2p)}件")

    san = [r for r in roster if r.get("chamber") == "参"]
    matched = 0
    unmatched = []
    for r in san:
        url = n2p.get(r["name"]) or n2p.get(r.get("alias") or "")
        if not url:
            unmatched.append(r["name"]); continue
        r["profile_url"] = url
        if not args.dry_run:
            try:
                r["elected_count"] = elected_count(_get(url).decode("utf-8", "replace")) or r.get("elected_count", "")
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {r['name']} profile取得失敗: {e}", file=sys.stderr)
            time.sleep(0.25)
        matched += 1

    ec = sum(1 for r in san if (r.get("elected_count") or "").strip())
    print(f"profile_url 突合: {matched}/{len(san)} / 当選回数取得: {ec}")
    if unmatched:
        print("  未突合:", unmatched[:10])
    if args.dry_run:
        return 0

    cols = [c for c in roster[0].keys() if c not in ("committees_list", "party_divisions_list")]
    with open(common.DATA / "roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(roster)
    print(f"roster.csv 更新（参 profile_url {matched}名 / 当選回数 {ec}名）")
    print("※ 参の career（経歴文）は公式サイトに無いため空のまま（捏造しない）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

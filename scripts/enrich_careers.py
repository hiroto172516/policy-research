#!/usr/bin/env python3
"""
STEP1 enrich: 衆議院プロフィールページから各議員の経歴(career)を名簿に付与する。

  出典（到達確認済み）: 衆 profile ページ（roster.csv の profile_url を使用）
    例 https://www.shugiin.go.jp/internet/itdb_giinprof.nsf/html/profile/001.html
  構造: <div id="contents"> 内に [氏名h2][選挙区・党の行][経歴文][（令和X年X月現在）]
  更新列: career … 経歴文（学歴・職歴・党/国会役職歴・当選回数）を保存。
          profile_asof … 経歴末尾の「（…現在）」時点を保存（任意）。

  ※ 衆議院のみ（roster の profile_url が衆のみ）。参議院は別ページを要特定（TODO）。
    profile_url で直接引くため氏名突合は不要（member_id で直付け）。

使い方:
  python3 scripts/enrich_careers.py                 # 衆の profile_url を全巡回
  python3 scripts/enrich_careers.py --limit 5       # 先頭5名だけ（動作確認）
  python3 scripts/enrich_careers.py --member H-0001
  python3 scripts/enrich_careers.py --dry-run       # 取得せず対象件数のみ
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


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    raw = r.content
    enc = "cp932" if re.search(rb"charset=shift_jis", raw, re.I) else "utf-8"
    return raw.decode(enc, "replace")


def extract_career(html: str) -> tuple[str, str]:
    """(career, profile_asof) を返す。"""
    m = re.search(r'<div id="contents">(.*?)</div>', html, re.S)
    if not m:
        return "", ""
    inner = re.sub(r"<br\s*/?>", "\n", m.group(1), flags=re.I)
    inner = re.sub(r"<[^>]+>", "", inner).replace("&nbsp;", " ")
    lines = [re.sub(r"[ \t　]+", " ", ln).strip() for ln in inner.split("\n")]
    lines = [ln for ln in lines if ln]
    asof = ""
    body = []
    for ln in lines:
        # 氏名h2（「姓 名（かな）」＝読みがカッコ内、○を含まない短い行）を除去
        if re.match(r"^.{2,12}（[ぁ-んァ-ンー・\s]+）$", ln) and "○" not in ln:
            continue
        # 選挙区・党のヘッダ行のみ除去（経歴本文中の「（○区選出）」を巻き込まない）。
        # ヘッダは 小選挙区/比例代表/選挙区 で始まり「選出」を含み、経歴印の○を含まない。
        if re.match(r"^(小選挙区|比例代表|選挙区|比例)", ln) and "選出" in ln and "○" not in ln:
            continue
        if re.match(r"^[（(].*現在[）)]$", ln):   # （令和X年X月現在）
            asof = ln.strip("（）()"); continue
        body.append(ln)
    career = " ".join(body).strip()
    return career, asof


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    roster = common.load_roster()
    targets = [r for r in roster if (r.get("profile_url") or "").strip()]
    if args.member:
        targets = [r for r in targets if r["member_id"] == args.member]
    if args.limit:
        targets = targets[: args.limit]
    print(f"対象（profile_url保持）: {len(targets)}名")
    if args.dry_run:
        return 0

    ok = 0
    for r in targets:
        try:
            career, asof = extract_career(_get(r["profile_url"]))
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {r['member_id']} {r['name']}: {e}", file=sys.stderr); continue
        if career:
            r["career"] = career
            if asof:
                r["profile_asof"] = asof
            ok += 1
        time.sleep(0.3)
    # profile_asof 列を持たせる（無ければ追加）
    cols = [c for c in roster[0].keys() if c not in ("committees_list", "party_divisions_list")]
    if any("profile_asof" in r for r in roster) and "profile_asof" not in cols:
        cols.insert(cols.index("profile_url"), "profile_asof")
    with open(common.DATA / "roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(roster)
    print(f"career を付与: {ok}/{len(targets)}名 → roster.csv 更新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

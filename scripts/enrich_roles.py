#!/usr/bin/env python3
"""
STEP1 enrich: 政府三役（大臣・副大臣・大臣政務官）を名簿(roster.csv)の roles 列に付与する。

  出典（到達確認済み）: 首相官邸 閣僚等名簿（内閣ごとにパスが変わる）
    大臣:   https://www.kantei.go.jp/jp/<内閣>/meibo/index.html
    副大臣: https://www.kantei.go.jp/jp/<内閣>/meibo/fukudaijin.html
    政務官: https://www.kantei.go.jp/jp/<内閣>/meibo/seimukan.html
    （2026-07時点は <内閣>=105＝第2次高市内閣）
  各ページの構造: <a ...>役職 氏名 （よみ） 院</a>。→ 読み(かな)で roster と突合。
  更新列: roles … 「大臣/副大臣/大臣政務官」の役職名を追記（委員長等の既存roleは保持）。

  ※ 内閣改造でパスが変わる → --cabinet で番号を変える（例 --cabinet 106）。
    民間人・非国会議員の大臣は roster に居ないため未突合（想定内）。

使い方:
  python3 scripts/enrich_roles.py                 # 現内閣(105)の三役を付与
  python3 scripts/enrich_roles.py --cabinet 106   # 改造後
  python3 scripts/enrich_roles.py --dry-run
"""
from __future__ import annotations
import argparse
import csv
import re
import sys

import common

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
PAGES = {"大臣": "index.html", "副大臣": "fukudaijin.html", "大臣政務官": "seimukan.html"}


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    raw = r.content
    enc = "cp932" if re.search(rb"charset=shift_jis", raw, re.I) else "utf-8"
    return raw.decode(enc, "replace")


def parse_roles(html: str) -> list[tuple[str, str, str, str]]:
    """アンカー「役職 氏名 （よみ） 院」から (役職, 読み, 氏名込みhead, 院) を返す。"""
    out = []
    for inner in re.findall(r"<a[^>]*>(.*?)</a>", html, re.S):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
        m = re.search(r"（([ぁ-んゝーァ-ン\s]+)）", text)
        if not m:
            continue
        kana = m.group(1)
        head = text[: m.start()].strip()          # 役職＋氏名
        tail = text[m.end():]                       # 院など
        house = "衆" if "衆議院" in tail else ("参" if "参議院" in tail else "")
        rm = re.match(r"^(.*?(?:大臣政務官|副大臣|大臣|長官|補佐官|本部長))", head)
        role = rm.group(1).strip() if rm else head
        out.append((role, kana, head, house))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cabinet", default="105", help="官邸の内閣番号（改造で変わる）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = f"https://www.kantei.go.jp/jp/{args.cabinet}/meibo"
    roster = common.load_roster()
    norm = lambda s: re.sub(r"\s+", "", s or "")
    # 読み仮名は衆参・党内で衝突しうる → (院, 氏名) を優先し、(院, かな) を補助にする
    by_house_kana: dict[tuple, dict] = {}
    for r in roster:
        if r.get("kana"):
            by_house_kana.setdefault((r["chamber"], norm(r["kana"])), r)

    def match(head: str, kana: str, house: str) -> dict | None:
        cands = [r for r in roster if (not house or r["chamber"] == house)]
        # 1) 氏名が head（役職＋氏名）に含まれる（最も確実。同かな別人を分離）
        hit = [r for r in cands if r["name"] and norm(r["name"]) in norm(head)]
        if len(hit) == 1:
            return hit[0]
        # 2) (院, 読み) で一意なら採用
        if house:
            return by_house_kana.get((house, norm(kana)))
        # 3) 院不明はかなが全体で一意な場合のみ
        allk = [r for r in roster if norm(r.get("kana")) == norm(kana)]
        return allk[0] if len(allk) == 1 else None

    mid_roles: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for kind, page in PAGES.items():
        try:
            rows = parse_roles(_get(f"{base}/{page}"))
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {kind} 取得失敗: {e}", file=sys.stderr); continue
        n = 0
        for role, kana, head, house in rows:
            r = match(head, kana, house)
            if not r:
                unmatched.append(f"{kind}:{role}:{kana}"); continue
            mid_roles.setdefault(r["member_id"], []).append(role)
            n += 1
        print(f"  {kind}: {len(rows)}件中 突合 {n}")

    matched = len(mid_roles)
    print(f"\n政府役職 突合: {matched}名 / 未突合: {len(unmatched)}件")
    if unmatched:
        print("  未突合（民間・非議員等の可能性）:", unmatched[:10])
    if args.dry_run:
        return 0

    for r in roster:
        if r["member_id"] in mid_roles:
            existing = [x for x in (r.get("roles") or "").split(";") if x.strip()]
            r["roles"] = ";".join(dict.fromkeys(existing + mid_roles[r["member_id"]]))

    cols = [c for c in roster[0].keys() if c not in ("committees_list", "party_divisions_list")]
    with open(common.DATA / "roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(roster)
    print(f"roster.csv を更新（政府役職 {matched}名付与）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

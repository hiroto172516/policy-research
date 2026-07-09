#!/usr/bin/env python3
"""
STEP1 enrich: 衆議院・参議院の委員名簿から各議員の現職委員会を名簿(roster.csv)に付与する。

  出典（到達確認済み）:
    衆 索引: https://www.shugiin.go.jp/internet/itdb_iinkai.nsf/html/iinkai/list.htm
       各委員会: .../iin_j0090.htm 等（常任 iin_j / 特別 iin_t / 審査会 iin_s）
       セル構造: [役職, 氏名(君), 読み, 会派]
    参 索引: https://www.sangiin.go.jp/japanese/kon_kokkaijyoho/iinkai/tiinkai.html
       各委員会: .../konkokkai/current/list/l0063.htm 等
       セル構造: [役職?, 氏名, （会派）]（役職は委員長/理事のみ・一般委員は役職セル無し）
  更新列:
    - committees … 所属委員会（; 区切り。複数所属可）
    - roles       … 委員長/会長を「○○委員会 委員長」形式で追記（既存を保持）

  氏名（衆は読みも）で roster と突合。両院とも同名重複が無いことを確認済み。
  マッチしない委員は WARN 表示。

使い方:
  python3 scripts/enrich_committees.py            # 衆参まとめて roster.csv を更新
  python3 scripts/enrich_committees.py --dry-run  # 更新せず突合結果のみ表示
  python3 scripts/enrich_committees.py --chamber 衆   # 片院だけ
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

SHU_DIR = "https://www.shugiin.go.jp/internet/itdb_iinkai.nsf/html/iinkai/"
SHU_LIST = SHU_DIR + "list.htm"
SAN_HOST = "https://www.sangiin.go.jp"
SAN_INDEX = SAN_HOST + "/japanese/kon_kokkaijyoho/iinkai/tiinkai.html"

ROLE_WORDS = {"委員長", "会長", "理事", "委員", "幹事", "オブザーバー"}
HEAD_ROLES = ("委員長", "会長")


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    raw = r.content
    enc = "cp932" if re.search(rb"charset=shift_jis", raw, re.I) else "utf-8"
    return raw.decode(enc, "replace")


def _clean(s: str) -> str:
    s = re.sub(r"[　\s]*君$", "", s)
    return re.sub(r"[　\s]+", " ", s).strip()


def _cells(html: str) -> list[str]:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ")).strip()
             for c in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S | re.I)]
    return [c for c in cells if c]


# ---------------- 衆議院 ----------------
def shu_committees() -> list[tuple[str, str]]:
    html = _get(SHU_LIST)
    out, seen = [], set()
    for href, inner in re.findall(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        label = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", inner))
        if re.search(r"iin_[jts]\d+\.htm", href) and re.search(r"(委員会|審査会|調査会)", label):
            url = SHU_DIR + href.split("/")[-1]
            if url not in seen:
                seen.add(url); out.append((label, url))
    return out


def parse_shu(html: str) -> list[tuple[str, str, str]]:
    """[役職, 氏名(君), 読み, 会派] の4つ組。→ (役職, 氏名, 読み)"""
    cells = _cells(html)
    members, i = [], 0
    while i < len(cells):
        if cells[i] in ROLE_WORDS and i + 1 < len(cells):
            role, name = cells[i], _clean(cells[i + 1])
            kana = cells[i + 2] if i + 2 < len(cells) else ""
            if re.search(r"[一-龠ぁ-んァ-ンー]", name) and not re.search(r"[\d０-９]\s*名|[（）]", name):
                members.append((role, name, kana))
            i += 4
        else:
            i += 1
    return members


# ---------------- 参議院 ----------------
def san_committees() -> list[str]:
    html = _get(SAN_INDEX)
    urls = re.findall(r'href="([^"]*/konkokkai/current/list/l\d{4}\.htm)"', html)
    seen, out = set(), []
    for u in urls:
        full = u if u.startswith("http") else SAN_HOST + u
        if full not in seen:
            seen.add(full); out.append(full)
    return out


def parse_san(html: str) -> tuple[str, list[tuple[str, str, str]]]:
    """委員会名は<title>から。委員は「氏名 → （会派）」で、直前が氏名。役職は委員長/理事のみ前置。"""
    title = re.sub(r"\s+", "", (re.findall(r"<title>([^<]+)", html) or [""])[0])
    cname = title.replace("委員名簿：参議院", "").replace("：参議院", "")
    cells = _cells(html)
    members = []
    for i, c in enumerate(cells):
        if re.fullmatch(r"（.+）", c) and i > 0:
            name = _clean(cells[i - 1])
            if name in ROLE_WORDS or re.search(r"[\d０-９]\s*名|[（）]", name):
                continue
            if not re.search(r"[一-龠ぁ-んァ-ンー]", name):
                continue
            role = "委員"
            if i >= 2 and cells[i - 2] in ("委員長", "会長", "理事"):
                role = cells[i - 2]
            members.append((role, name, ""))
    return cname, members


# ---------------- 突合・書き込み ----------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chamber", choices=["衆", "参"], help="片院のみ処理")
    args = ap.parse_args()

    roster = common.load_roster()
    norm = lambda s: re.sub(r"\s+", "", s or "")
    idx = {}  # (chamber, name) / (chamber, 'kana:'+kana) -> member_id
    for r in roster:
        idx[(r["chamber"], r["name"])] = r["member_id"]
        if r.get("alias"):
            idx.setdefault((r["chamber"], r["alias"]), r["member_id"])
        if r.get("kana"):
            idx[(r["chamber"], "kana:" + norm(r["kana"]))] = r["member_id"]

    mid_committees: dict[str, list[str]] = {}
    mid_roles: dict[str, list[str]] = {}
    unmatched: list[str] = []

    def handle(chamber: str, cname: str, members: list[tuple[str, str, str]]):
        for role, name, kana in members:
            mid = idx.get((chamber, name)) or (idx.get((chamber, "kana:" + norm(kana))) if kana else None)
            if not mid:
                unmatched.append(f"{chamber}/{cname}:{role}:{name}"); continue
            mid_committees.setdefault(mid, [])
            if cname not in mid_committees[mid]:
                mid_committees[mid].append(cname)
            if role in HEAD_ROLES:
                mid_roles.setdefault(mid, []).append(f"{cname} {role}")

    # 衆議院
    if args.chamber in (None, "衆"):
        for cname, url in shu_committees():
            try:
                ms = parse_shu(_get(url))
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] 衆 {cname} 取得失敗: {e}", file=sys.stderr); continue
            handle("衆", cname, ms)
            print(f"  衆 {cname}: {len(ms)}名"); time.sleep(0.3)

    # 参議院
    if args.chamber in (None, "参"):
        try:
            urls = san_committees()
            print(f"参 委員会 {len(urls)}件")
            for url in urls:
                try:
                    cname, ms = parse_san(_get(url))
                except Exception as e:  # noqa: BLE001
                    print(f"[WARN] 参 {url} 取得失敗: {e}", file=sys.stderr); continue
                handle("参", cname, ms)
                print(f"  参 {cname}: {len(ms)}名"); time.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] 参 索引取得失敗: {e}", file=sys.stderr)

    matched = len(mid_committees)
    print(f"\n突合成功: {matched}名 / 未突合: {len(unmatched)}件")
    if unmatched:
        print("  未突合例:", unmatched[:10])
    if args.dry_run:
        return 0

    for r in roster:
        mid = r["member_id"]
        if mid in mid_committees:
            r["committees"] = ";".join(mid_committees[mid])
        if mid in mid_roles:
            existing = [x for x in (r.get("roles") or "").split(";") if x.strip()]
            r["roles"] = ";".join(dict.fromkeys(existing + mid_roles[mid]))

    cols = [c for c in roster[0].keys() if c not in ("committees_list", "party_divisions_list")]
    with open(common.DATA / "roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(roster)
    print(f"roster.csv を更新（committees {matched}名 / 委員長等 {len(mid_roles)}名）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

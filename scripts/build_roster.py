#!/usr/bin/env python3
"""
STEP1 (名簿ビルダー): 衆議院・参議院の公式議員一覧から議員マスター名簿を生成する。

  ソース（この環境から HTTP 200 で到達可能・認証不要）:
    - 衆議院 議員一覧: https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/1giin.htm
    - 参議院 議員一覧: https://www.sangiin.go.jp/japanese/joho1/kousei/giin/<回>/giin.htm
  出力: data/roster.csv （氏名・読み・議院・会派・選挙区・profile_url 等 / as_of / verified=yes）

取得できる確定列: name, kana, chamber(衆/参), party(会派), district(選挙区),
  elected_count(衆のみ当選回数), profile_url(衆はプロフィールページ), source_url
未取得（後段のenrichで補充）: roles(役職), committees(委員会), party_divisions(党内部会),
  career(キャリア), member_company_offices

  ※「与党」の判定は政局で変わるため名簿では固定しない。会派をそのまま記録し、
    config/ruling_parties.yml で人間が指定した会派に is_ruling=yes を付ける。

使い方:
  python3 scripts/build_roster.py                        # 衆参まとめて生成
  python3 scripts/build_roster.py --sangiin-session 218  # 参の回次を指定
  python3 scripts/build_roster.py --as-of 2026-07-03
  python3 scripts/build_roster.py --dry-run              # 取得のみ・件数表示
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

import common

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
SHUGIIN_DIR = "https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/"
SHUGIIN = SHUGIIN_DIR + "1giin.htm"  # 五十音ページの起点（1giin〜10giin）
SHUGIIN_BASE = "https://www.shugiin.go.jp/internet/itdb_giinprof.nsf/html/profile/"
SANGIIN = "https://www.sangiin.go.jp/japanese/joho1/kousei/giin/{session}/giin.htm"


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    raw = r.content
    enc = "cp932" if re.search(rb"charset=shift_jis", raw, re.I) else "utf-8"
    return raw.decode(enc, "replace")


def _cells(row_html: str) -> list[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I):
        txt = re.sub(r"<[^>]+>", "", c)
        txt = txt.replace("&nbsp;", " ").strip()
        txt = re.sub(r"\s+", " ", txt)
        if txt:
            out.append(txt)
    return out


def _clean_name(s: str) -> str:
    s = re.sub(r"[　\s]*君$", "", s)          # 敬称「君」除去
    s = re.sub(r"[　\s]+", " ", s).strip()    # 全角/連続スペースを半角1個に
    return s


def _split_alias(s: str) -> tuple[str, str]:
    """「通称[本名]」形式を (通称, 本名) に分離。ブラケットは全角/半角どちらも許容。"""
    m = re.match(r"^\s*([^\[［]+?)\s*[\[［]([^\]］]+)[\]］]\s*$", s)
    if m:
        return _clean_name(m.group(1)), _clean_name(m.group(2))
    return _clean_name(s), ""


def fetch_shugiin_all() -> list[dict]:
    """1giin.htm を起点に <N>giin.htm（五十音ページ）を全て巡回して統合する。"""
    import time
    first = _get(SHUGIIN)
    pages = sorted(set(re.findall(r"(\d+giin\.htm)", first)),
                   key=lambda s: int(re.match(r"\d+", s).group()))
    if "1giin.htm" not in pages:
        pages = ["1giin.htm"] + pages
    all_members: list[dict] = []
    seen = set()
    for pg in pages:
        html = first if pg == "1giin.htm" else _get(SHUGIIN_DIR + pg)
        for m in parse_shugiin(html):
            key = (m["name"], m["district"])
            if key in seen:
                continue
            seen.add(key)
            all_members.append(m)
        time.sleep(0.3)
    return all_members


def parse_shugiin(html: str) -> list[dict]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
    members = []
    for r in rows:
        # プロフィールリンク（氏名セル）
        m = re.search(r"href=['\"]([^'\"]*profile/[^'\"]+)['\"][^>]*>([^<]+)</a>", r, re.I)
        c = _cells(r)
        if not m or len(c) < 4:
            continue
        href, rawname = m.group(1), m.group(2)
        name, alias = _split_alias(rawname)
        # c = [氏名, 読み, 会派, 選挙区, 当選回数]
        kana = c[1] if len(c) > 1 else ""
        party = c[2] if len(c) > 2 else ""
        district = c[3] if len(c) > 3 else ""
        elected = c[4] if len(c) > 4 else ""
        prof = re.sub(r"^(\.\./)+itdb_giinprof\.nsf/html/profile/", SHUGIIN_BASE, href)
        if not prof.startswith("http"):
            prof = SHUGIIN_BASE + Path(href).name
        members.append({
            "name": name, "alias": alias, "kana": kana, "chamber": "衆", "party": party,
            "district": district, "elected_count": elected,
            "profile_url": prof, "source_url": SHUGIIN,
        })
    return members


def parse_sangiin(html: str, src: str) -> list[dict]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
    members = []
    for r in rows:
        c = _cells(r)
        # 行見出し(単一ひらがな)や案内行を除去
        c = [x for x in c if not re.fullmatch(r"[ぁ-ん]", x)]
        if len(c) < 4:
            continue
        if c[0] in ("議員氏名",) or "行" in c[0][:2] and len(c[0]) <= 2:
            continue
        name, kana, party, district = c[0], c[1], c[2], c[3]
        # 氏名は「姓 名」、読みはひらがな。妥当性チェック
        if not re.search(r"[一-龠ぁ-んァ-ンー]", name) or not re.search(r"[ぁ-ん]", kana):
            continue
        clean, alias = _split_alias(name)
        members.append({
            "name": clean, "alias": alias, "kana": kana, "chamber": "参", "party": party,
            "district": district, "elected_count": "",
            "profile_url": "", "source_url": src,
        })
    return members


COLUMNS = ["member_id", "name", "alias", "kana", "chamber", "party", "district",
           "elected_count", "roles", "committees", "party_divisions", "career",
           "as_of", "member_company_offices", "profile_url", "source_url", "verified"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sangiin-session", default="218")
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    ap.add_argument("--out", default=str(common.DATA / "roster.csv"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        shu = fetch_shugiin_all()
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 衆議院取得失敗: {e}", file=sys.stderr); shu = []
    san_src = SANGIIN.format(session=args.sangiin_session)
    try:
        san = parse_sangiin(_get(san_src), san_src)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 参議院取得失敗: {e}", file=sys.stderr); san = []

    print(f"衆議院: {len(shu)}名 / 参議院: {len(san)}名 / 計 {len(shu)+len(san)}名")
    if args.dry_run:
        for m in (shu[:3] + san[:3]):
            print(" ", m["chamber"], m["name"], m["party"], m["district"])
        return 0

    rows = []
    for i, m in enumerate(shu, 1):
        m["member_id"] = f"H-{i:04d}"; rows.append(m)
    for i, m in enumerate(san, 1):
        m["member_id"] = f"S-{i:04d}"; rows.append(m)
    for m in rows:
        m.setdefault("roles", ""); m.setdefault("committees", "")
        m.setdefault("party_divisions", ""); m.setdefault("career", "")
        m.setdefault("member_company_offices", "")
        m["as_of"] = args.as_of
        m["verified"] = "yes"

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"名簿を書き出し -> {args.out}（{len(rows)}名, as_of={args.as_of}, verified=yes）")
    print("※ roles/committees/party_divisions/career は enrich段階で補充してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

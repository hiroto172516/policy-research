#!/usr/bin/env python3
"""
Wikidata の Twitter/X username (P2002) から x_handles.csv の候補を補完する。

注意:
  - Wikidata は一次情報ではないため、note に「要公式確認」と記録する。
  - 氏名が完全一致し、説明文が日本の政治家・国会議員らしい候補だけを採用する。
  - 既に x_handle が入っている行は上書きしない。
"""
from __future__ import annotations
import argparse
import csv
import time
from typing import Any

import requests

import common


FIELDS = ["member_id", "name", "party", "x_handle", "note"]
API = "https://www.wikidata.org/w/api.php"
POLITICIAN_HINTS = ("政治家", "衆議院", "参議院", "国会議員", "大臣", "知事", "市長")
HEADERS = {"User-Agent": "JCLP-policy-research/0.1 (contact: JCLP jimukyoku)"}


def compact_name(s: str) -> str:
    return "".join((s or "").split())


def search_entities(name: str) -> list[dict[str, Any]]:
    r = requests.get(API, params={
        "action": "wbsearchentities",
        "format": "json",
        "language": "ja",
        "uselang": "ja",
        "search": name,
        "limit": 5,
    }, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("search", [])


def get_twitter_username(qid: str) -> str | None:
    r = requests.get(API, params={
        "action": "wbgetentities",
        "format": "json",
        "ids": qid,
        "props": "claims",
    }, headers=HEADERS, timeout=30)
    r.raise_for_status()
    claims = r.json().get("entities", {}).get(qid, {}).get("claims", {})
    vals = []
    for claim in claims.get("P2002", []):
        value = (claim.get("mainsnak", {}).get("datavalue", {}) or {}).get("value")
        if isinstance(value, str) and value.strip():
            vals.append(value.strip().lstrip("@"))
    if len(set(vals)) == 1:
        return vals[0]
    return None


def discover_one(name: str) -> tuple[str, str] | None:
    target = compact_name(name)
    matches = []
    for ent in search_entities(name):
        label = ent.get("label", "")
        desc = ent.get("description", "")
        if compact_name(label) != target:
            continue
        if not any(h in desc for h in POLITICIAN_HINTS):
            continue
        handle = get_twitter_username(ent["id"])
        if handle:
            matches.append((handle, ent["id"], desc))
    uniq = {(h, q, d) for h, q, d in matches}
    if len(uniq) != 1:
        return None
    handle, qid, desc = next(iter(uniq))
    return handle, f"Wikidata P2002候補 {qid}（{desc}）。要公式確認"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="先頭N件だけ試す")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = common.DATA / "x_handles.csv"
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    updated = 0
    checked = 0
    for row in rows:
        if row.get("x_handle", "").strip():
            continue
        if args.limit and checked >= args.limit:
            break
        checked += 1
        try:
            found = discover_one(row["name"])
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {row['member_id']} {row['name']}: {e}")
            continue
        if not found:
            print(f"[MISS] {row['member_id']} {row['name']}")
            time.sleep(0.25)
            continue
        handle, note = found
        print(f"[HIT] {row['member_id']} {row['name']}: @{handle}")
        if not args.dry_run:
            row["x_handle"] = handle
            row["note"] = note
            updated += 1
        time.sleep(0.25)

    if not args.dry_run and updated:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    filled = sum(1 for r in rows if r.get("x_handle", "").strip())
    print(f"完了: checked={checked} updated={updated} filled={filled}/{len(rows)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

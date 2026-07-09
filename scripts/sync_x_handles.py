#!/usr/bin/env python3
"""
roster.csv を基準に data/x_handles.csv を同期する。

既存の x_handle/note は member_id で保持し、未登録議員を空欄で追加する。
全議員のSNS登録作業の台帳を作るためのスクリプト。
"""
from __future__ import annotations
import csv

import common


FIELDS = ["member_id", "name", "party", "x_handle", "note"]


def main() -> int:
    path = common.DATA / "x_handles.csv"
    existing: dict[str, dict] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("member_id"):
                    existing[row["member_id"]] = row

    rows = []
    for member in common.load_roster():
        old = existing.get(member["member_id"], {})
        rows.append({
            "member_id": member["member_id"],
            "name": member.get("name", ""),
            "party": member.get("party", ""),
            "x_handle": old.get("x_handle", ""),
            "note": old.get("note", ""),
        })

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    filled = sum(1 for r in rows if r["x_handle"].strip())
    print(f"同期完了: {path}")
    print(f"  行数: {len(rows)} / x_handle登録済み: {filled} / 未登録: {len(rows) - filled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

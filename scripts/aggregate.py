#!/usr/bin/env python3
"""
STEP4 (集計): 名簿(roster) × 分類(classifications) を結合し、
会議体・党内部会ごとの類型構成を集計する。

  出力: output/aggregate.json
        { "committees": {会議体名: {類型ラベル: 人数}}, "party_divisions": {...}, "overall": {...} }

議員は複数の会議体に所属しうるため、各所属先に1票ずつ計上する。
"""
from __future__ import annotations
import argparse
import json
from collections import Counter, defaultdict

import common


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(common.OUTPUT / "aggregate.json"))
    ap.add_argument("--roster", help="名簿CSVのパス（省略時 data/roster.csv）")
    args = ap.parse_args()

    common.ensure_dirs()
    from pathlib import Path
    roster = {r["member_id"]: r for r in common.load_roster(Path(args.roster) if args.roster else None)}

    committees: dict[str, Counter] = defaultdict(Counter)
    divisions: dict[str, Counter] = defaultdict(Counter)
    overall: Counter = Counter()
    unclassified = []
    committee_totals: Counter = Counter()   # 委員会の全所属数（分類有無に関わらず）

    for mid, member in roster.items():
        for c in member.get("committees_list", []):
            committee_totals[c] += 1
        cpath = common.CLASSIFICATIONS / f"{mid}.json"
        if not cpath.exists():
            unclassified.append(mid)
            continue
        rec = json.loads(cpath.read_text(encoding="utf-8"))
        label = rec.get("archetype", {}).get("label", "分類保留")
        overall[label] += 1
        for c in member.get("committees_list", []):
            committees[c][label] += 1
        for d in member.get("party_divisions_list", []):
            divisions[d][label] += 1

    result = {
        "overall": dict(overall),
        "committees": {k: dict(v) for k, v in sorted(committees.items())},
        "committee_totals": dict(committee_totals),   # 分母（誤認防止）
        "party_divisions": {k: dict(v) for k, v in sorted(divisions.items())},
        "unclassified_members": unclassified,
        "classified_total": sum(overall.values()),
        "member_total": len(roster),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"集計完了 -> {args.out}")
    print(f"  全体分類: {dict(overall)}")
    print(f"  会議体数: {len(committees)} / 部会数: {len(divisions)}")
    if unclassified:
        print(f"  未分類（要収集/分類）: {len(unclassified)}名（例 {unclassified[:5]} …）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

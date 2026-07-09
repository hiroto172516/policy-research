#!/usr/bin/env python3
"""
STEP2 影響力(influence)軸: 名簿(roster)から議員の Tier を機械的に算出する。

  memo L9「影響力」・L26-28（どの類型がどの程度いるか／エンゲージメント戦略）に対応。
  ★発言（スタンス）とは独立の軸。roster の roles/committees/elected_count から算出する。
  規則は config/axes.yml の influence を参照:
    Tier A(重点): 大臣・副大臣・政務官 or 委員長・会長 or 当選 senior_elected_min 回以上
    Tier B(通常): 委員会所属あり（Aでない）
    Tier C(様子見): 上記以外
  出力: roster.csv に influence_tier 列を追記（＋分布を表示）。

使い方:
  python3 scripts/compute_influence.py
  python3 scripts/compute_influence.py --dry-run   # 書き込まず分布のみ
"""
from __future__ import annotations
import argparse
import csv
import re
from collections import Counter

import common


def seniority_of(elected: int, senior_min: int, mid_min: int) -> str:
    if elected >= senior_min:
        return "senior"
    if elected >= mid_min:
        return "mid"
    return "junior"


def tier_of(r: dict, conf: dict) -> tuple[str, str, list[str]]:
    roles = r.get("roles") or ""
    committees = (r.get("committees") or "").strip()
    try:
        elected = int(re.sub(r"[^\d]", "", r.get("elected_count") or "0") or 0)
    except ValueError:
        elected = 0
    sr = conf.get("seniority", {})
    seniority = seniority_of(elected, int(sr.get("senior_min", 5)), int(sr.get("mid_min", 2)))
    signals = []
    if re.search(r"大臣|副大臣|政務官", roles):
        signals.append("role_minister")
    if re.search(r"委員長|会長", roles):
        signals.append("role_committee_chair")
    if conf.get("senior_grants_tier_a") and seniority == "senior":
        signals.append(f"senior(当選{elected})")
    if signals:
        return "A", seniority, signals
    if committees:
        return "B", seniority, ["has_committee"]
    return "C", seniority, []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    axes = common.load_axes()
    conf = axes.get("influence", {})
    roster = common.load_roster()

    dist = Counter()
    sen = Counter()
    by_house = {"衆": Counter(), "参": Counter()}
    for r in roster:
        t, seniority, sig = tier_of(r, conf)
        r["influence_tier"] = t
        r["seniority"] = seniority
        r["_influence_signals"] = ";".join(sig)  # 一時（書き込み対象外）
        dist[t] += 1
        sen[seniority] += 1
        by_house.get(r.get("chamber"), Counter())[t] += 1

    print(f"影響力Tier（senior_grants_tier_a={conf.get('senior_grants_tier_a')}）")
    for t in ["A", "B", "C"]:
        print(f"  Tier {t}: {dist[t]}名  （衆{by_house['衆'][t]} / 参{by_house['参'][t]}）")
    print(f"seniority: senior {sen['senior']} / mid {sen['mid']} / junior {sen['junior']}")
    print("\nTier A の例:")
    for r in [x for x in roster if x["influence_tier"] == "A"][:8]:
        print(f"  {r['chamber']} {r['name']}（{r['party']}）← {r['_influence_signals']}")

    if args.dry_run:
        return 0
    cols = [c for c in roster[0].keys()
            if c not in ("committees_list", "party_divisions_list", "_influence_signals")]
    for extra in ("influence_tier", "seniority"):
        if extra not in cols:
            cols.append(extra)
    with open(common.DATA / "roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(roster)
    print(f"\nroster.csv に influence_tier を付与（A:{dist['A']} B:{dist['B']} C:{dist['C']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

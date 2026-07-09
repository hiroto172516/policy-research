#!/usr/bin/env python3
"""
STEP3 (検証・安全ゲート): Claude Code が書いた分類(data/classifications/<mid>.json)を
機械検証する。**根拠quoteが原発言に実在するか**を必ず確認し、捏造を遮断する。

  検証項目:
    - member_id が名簿に存在
    - topics の stance が axes.stance_scale の key に一致
    - archetype.id が axes.archetypes の id に一致
    - 各 evidence.quote が data/speeches/<mid>.json または data/x_posts/<mid>.json の原文に**実在**（正規化照合）
    - engagement.level が axes.engagement_scale の key に一致
  1件でも不一致があればエラー終了（下流に伝播させない）。

使い方:
  python3 scripts/validate_classifications.py            # 全classificationを検証
  python3 scripts/validate_classifications.py --member S-0160
"""
from __future__ import annotations
import argparse
import json
import re
import sys

import common


def norm(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def load_corpora(mid: str) -> dict[str, str]:
    corpora = {"diet": "", "x": ""}
    sp_path = common.SPEECHES / f"{mid}.json"
    if sp_path.exists():
        corpora["diet"] = norm(" ".join(
            s.get("speech") or ""
            for s in json.loads(sp_path.read_text(encoding="utf-8")).get("speeches", [])))
    xp_path = common.DATA / "x_posts" / f"{mid}.json"
    if xp_path.exists():
        corpora["x"] = norm(" ".join(
            p.get("text") or ""
            for p in json.loads(xp_path.read_text(encoding="utf-8")).get("posts", [])))
    corpora["any"] = corpora["diet"] + corpora["x"]
    return corpora


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member")
    args = ap.parse_args()

    axes = common.load_axes()
    stance_keys = {s["key"] for s in axes["stance_scale"]}
    eng_keys = {e["key"] for e in axes["engagement_scale"]}
    arche_ids = {a["id"] for a in axes["archetypes"]}
    topic_ids = {t["id"] for t in axes["topics"]}
    roster_ids = {r["member_id"] for r in common.load_roster()}

    files = ([common.CLASSIFICATIONS / f"{args.member}.json"] if args.member
             else sorted(common.CLASSIFICATIONS.glob("*.json")))
    files = [f for f in files if f.exists()]
    if not files:
        print("検証対象の分類がありません。", file=sys.stderr)
        return 1

    errors = []
    for f in files:
        mid = f.stem
        rec = json.loads(f.read_text(encoding="utf-8"))
        if mid not in roster_ids:
            errors.append(f"{mid}: 名簿に存在しない")
        corpora = load_corpora(mid)
        # topics
        for tid, t in (rec.get("topics") or {}).items():
            if tid not in topic_ids:
                errors.append(f"{mid}: 未知のtopic {tid}")
            if t.get("stance") not in stance_keys:
                errors.append(f"{mid}/{tid}: 不正なstance {t.get('stance')}")
            for ev in t.get("evidence", []):
                q = ev.get("quote", "")
                source = (ev.get("source") or "any").lower()
                corpus = corpora.get(source, corpora["any"])
                if not q or norm(q) not in corpus:
                    errors.append(f"{mid}/{tid}: quote未検出 source={source}「{q[:30]}」")
        # archetype
        aid = (rec.get("archetype") or {}).get("id")
        if aid not in arche_ids:
            errors.append(f"{mid}: 不正なarchetype {aid}")
        # engagement
        lvl = (rec.get("engagement") or {}).get("level")
        if lvl not in eng_keys:
            errors.append(f"{mid}: 不正なengagement.level {lvl}")
        mark = "OK" if not any(mid in e for e in errors) else "NG"
        print(f"  {mark} {mid}: {rec.get('archetype',{}).get('label','?')} / {lvl}")

    if errors:
        print("\n=== 検証エラー（下流に進めない） ===", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    print(f"\n全 {len(files)} 件 検証OK（quote実在・軸整合）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

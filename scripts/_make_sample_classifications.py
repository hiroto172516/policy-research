#!/usr/bin/env python3
"""
【デモ専用】STEP4 を実証するための合成分類データを生成する。

本番では classify.py（Claude API）が data/classifications/ を生成する。
この環境は会議録API(403)・APIキー未設定のため、パイプライン下流(集計・可視化)を
動かすためのダミー分類を作る。すべて demo=true を付ける。
"""
from __future__ import annotations
import json
import common

# member_id -> 類型(archetype id, label) を決め打ち（会議体別に分布が出るよう配置）
ASSIGN = {
    "M-0001": ("renewable_champion", "再エネ積極支持"),
    "M-0002": ("econ_security_focus", "脱炭素関心薄・経済安保重視"),
    "M-0003": ("renewable_champion", "再エネ積極支持"),
    "M-0004": ("nuclear_energy_focus", "原子力・安定供給重視"),
    "M-0005": ("renewable_champion", "再エネ積極支持"),
    "M-0006": ("solar_skeptic", "太陽光批判"),
    "M-0007": ("nuclear_energy_focus", "原子力・安定供給重視"),
    "M-0008": ("renewable_champion", "再エネ積極支持"),
    "M-0009": ("solar_skeptic", "太陽光批判"),
    "M-0010": ("econ_security_focus", "脱炭素関心薄・経済安保重視"),
    "M-0011": ("low_engagement", "発言少・様子見"),
    "M-0012": ("econ_security_focus", "脱炭素関心薄・経済安保重視"),
}


def main() -> int:
    common.ensure_dirs()
    # デモは合成名簿(roster.sample.csv)を使う。実名簿(roster.csv)とは混同しない。
    sample = common.DATA / "roster.sample.csv"
    roster = {r["member_id"]: r for r in common.load_roster(sample if sample.exists() else None)}
    for mid, (aid, label) in ASSIGN.items():
        member = roster.get(mid, {})
        rec = {
            "member_id": mid,
            "as_of": member.get("as_of"),
            "axes_version": "0.1",
            "demo": True,
            "topics": {
                "decarbonization": {"stance": "neutral_unknown", "confidence": 0.5, "evidence": []},
            },
            "archetype": {"id": aid, "label": label, "confidence": 0.7,
                          "rationale": "【合成データ】STEP4実証用のダミー判定"},
            "engagement": {"relevant_speech_count": 0 if aid == "low_engagement" else 5},
            "flags": ["sensitive:原子力"] if aid == "nuclear_energy_focus" else [],
        }
        out = common.CLASSIFICATIONS / f"{mid}.json"
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{mid}: {label} (demo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

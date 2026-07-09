#!/usr/bin/env python3
"""
【STEP3 パイロット分類】4名の実発言を評価軸(axes.yml)に沿って分類する。

  本来は classify.py（ANTHROPIC_API_KEY で Claude API）が行う工程。ここでは
  APIキー未設定のため、メインのClaudeエージェントが分類した結果を格納する
  （classified_by=claude_main_agent_pilot）。**根拠quoteが実発言に実在することを
  検証してから書き込む**（安全原則：発言に無いことは書かない）。
"""
import json
import re
import sys
sys.path.insert(0, "scripts")
import common

# メインClaudeによる分類（実発言の精読に基づく）。quoteは実在検証にかける。
PILOT = {
    "S-0160": {  # 長浜 博行（立憲・環境委）: 脱炭素の野心度を上げる方向
        "topics": {
            "decarbonization": {"stance": "strong_support", "confidence": 0.8,
                "quotes": ["国際公約の四六％削減目標", "ハードルを低めに設定するんではなくて"]},
            "energy_policy": {"stance": "conditional_support", "confidence": 0.7,
                "quotes": ["一次エネルギー消費量の上位等級を新設"]},
        },
        "archetype": {"id": "renewable_champion", "label": "再エネ積極支持", "confidence": 0.7,
            "rationale": "46%削減の確実な達成・省エネ上位等級新設など、脱炭素の野心度を上げる方向の発言。"},
        "engagement": "medium",
    },
    "H-0405": {  # 宮路 拓馬（自民・環境委員長）: 収集分は議事運営のみ＝スタンス不明
        "topics": {},
        "archetype": {"id": "low_engagement", "label": "発言少・様子見", "confidence": 0.6,
            "rationale": "収集した発言は委員長としての議事運営（開会・参考人招致）のみで、政策スタンスは表明されていない。"},
        "engagement": "none",
        "flags": ["委員長発言のため個人スタンス不明・要追加収集"],
    },
    "S-0033": {  # 猪口 邦子（自民）: 脱炭素＋エネルギー安全保障の双方
        "topics": {
            "decarbonization": {"stance": "conditional_support", "confidence": 0.7,
                "quotes": ["地球温暖化対策の推進に関する法律", "どの国もこの脱炭素を"]},
            "economic_security": {"stance": "strong_support", "confidence": 0.75,
                "quotes": ["食料・エネルギー安全保障", "リスクを分散する必要"]},
        },
        "archetype": {"id": "renewable_champion", "label": "再エネ積極支持", "confidence": 0.55,
            "rationale": "温対法・脱炭素を支持しつつ、エネルギー安全保障（OPEC・供給リスク分散）にも強い関心。econ_security_focus寄りの側面もあり要レビュー。"},
        "engagement": "high",
    },
    "H-0151": {  # 工藤 彰三（自民・経産委員長）: CN・水素・経済安保
        "topics": {
            "decarbonization": {"stance": "conditional_support", "confidence": 0.7,
                "quotes": ["二〇三〇年に四六％減", "カーボンニュートラル"]},
            "renewables": {"stance": "conditional_support", "confidence": 0.65,
                "quotes": ["再生可能エネルギーの一つである水素"]},
            "economic_security": {"stance": "conditional_support", "confidence": 0.6,
                "quotes": ["エネルギー安定供給に与える影響"]},
        },
        "archetype": {"id": "renewable_champion", "label": "再エネ積極支持", "confidence": 0.55,
            "rationale": "カーボンニュートラルポート・水素活用を推進。経済安保・エネルギー安定供給にも言及。"},
        "engagement": "high",
    },
}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def main():
    for mid, cls in PILOT.items():
        d = json.load(open(f"data/speeches/{mid}.json", encoding="utf-8"))
        corpus = norm(" ".join(s.get("speech") or "" for s in d["speeches"]))
        topics_out = {}
        for tid, t in cls.get("topics", {}).items():
            ev = []
            for q in t.get("quotes", []):
                if norm(q) in corpus:                 # ★実在検証
                    ev.append({"quote": q, "verified": True})
                else:
                    print(f"[NG] {mid}/{tid}: quote未検出 「{q}」")
                    sys.exit(1)
            topics_out[tid] = {"stance": t["stance"], "confidence": t["confidence"], "evidence": ev}
        rec = {
            "member_id": mid,
            "classified_by": "claude_main_agent_pilot",
            "axes_version": common.load_axes().get("meta", {}).get("version"),
            "topics": topics_out,
            "archetype": cls["archetype"],
            "engagement": {"level": cls["engagement"],
                           "relevant_speech_count": len(d["speeches"])},
            "flags": cls.get("flags", []),
        }
        out = common.CLASSIFICATIONS / f"{mid}.json"
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{mid} {d['speaker']}: {cls['archetype']['label']} "
              f"(engagement={cls['engagement']}, quote検証OK) -> {out.name}")


if __name__ == "__main__":
    main()

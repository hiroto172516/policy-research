#!/usr/bin/env python3
"""【STEP3 パイロット分類・第2バッチ】6名。Claude Codeによる分類（quote実在検証つき）。"""
import json, re, sys
sys.path.insert(0, "scripts")
import common

PILOT = {
    "H-0044": {  # 伊藤 信太郎（自民・元環境大臣）
        "topics": {
            "decarbonization": {"stance":"strong_support","confidence":0.85,
                "quotes":["二〇五〇年カーボンニュートラル","温室効果ガス四六％削減"]},
            "renewables": {"stance":"strong_support","confidence":0.8,
                "quotes":["基本的には再生エネルギーは増やすべき","再エネ比率三六から三八％"]},
            "solar": {"stance":"conditional_support","confidence":0.7,
                "quotes":["太陽光発電にもいろんな懸念","地域の環境が壊れない形で"]},
            "economic_security": {"stance":"conditional_support","confidence":0.6,
                "quotes":["エネルギー安全保障"]},
        },
        "archetype": {"id":"renewable_champion","label":"再エネ積極支持","confidence":0.75,
            "rationale":"環境大臣として2050CN・46%削減・再エネ拡大を推進。太陽光は地域環境配慮で条件付き。"},
        "engagement":"high",
        "flags":["政府答弁（環境大臣）＝政府方針の色。個人スタンスと区別要"],
    },
    "H-0102": {  # 落合 貴之（立憲/中道・経産委）
        "topics": {
            "decarbonization": {"stance":"conditional_support","confidence":0.6,
                "quotes":["ＧＸ、ＤＸは重要"]},
            "renewables": {"stance":"conditional_support","confidence":0.55,
                "quotes":["太陽光パネルの生産"]},
            "economic_security": {"stance":"strong_support","confidence":0.8,
                "quotes":["食料もエネルギーもデジタルも","生産の国内回帰"]},
        },
        "archetype": {"id":"econ_security_focus","label":"脱炭素関心薄・経済安保重視","confidence":0.5,
            "rationale":"エネルギー自給・国産化・供給網を重視。ただしGX/水素は支持しており『脱炭素関心薄』とは言い切れない→類型の境界事例。"},
        "engagement":"high",
        "flags":["archetype境界: 脱炭素支持かつ経済安保重視は既存類型に当てはまりにくい（軸拡張候補）"],
    },
    "H-0013": {  # 東 徹（維新・経産委）
        "topics": {
            "nuclear": {"stance":"strong_support","confidence":0.8,
                "quotes":["核融合発電","高レベル放射能廃棄物が出ない"]},
            "renewables": {"stance":"cautious","confidence":0.65,
                "quotes":["浮体式の洋上風力だと三十六円の買取り"]},
            "ev": {"stance":"cautious","confidence":0.55,
                "quotes":["ＥＶ、ＰＨＥＶの割合はたった二・九七％"]},
        },
        "archetype": {"id":"nuclear_advocate","label":"原子力・安定供給重視","confidence":0.6,
            "rationale":"核融合を積極評価。再エネはFIT高価格に懐疑的、EV目標未達を指摘。"},
        "engagement":"high",
    },
    "H-0091": {  # 緒方 林太郎（無・環境委）
        "topics": {
            "solar": {"stance":"cautious","confidence":0.6,
                "quotes":["メガソーラー等の再生可能エネルギー"]},
            "economic_security": {"stance":"conditional_support","confidence":0.6,
                "quotes":["中国企業が関与したと思われるロゴ"]},
        },
        "archetype": {"id":"solar_skeptic","label":"太陽光批判","confidence":0.5,
            "rationale":"メガソーラー・再エネ特措法を問題提起。再エネタスクフォースの中国企業関与も指摘（経済安保視点）。"},
        "engagement":"medium",
    },
    "H-0122": {  # 金子 恵美（立憲・環境委・福島）
        "topics": {
            "renewables": {"stance":"strong_support","confidence":0.8,
                "quotes":["再生可能エネルギーをしっかりと大きく進めていく","再生可能エネルギーから生み出す"]},
            "nuclear": {"stance":"cautious","confidence":0.7,
                "quotes":["原発依存から脱却","このままただ原発に依存する"]},
        },
        "archetype": {"id":"renewable_champion","label":"再エネ積極支持","confidence":0.7,
            "rationale":"福島の再エネ100%目標を推進、原発依存からの脱却を主張。"},
        "engagement":"high",
        "flags":["sensitive:原子力"],
    },
    "H-0036": {  # 石原 正敬（自民・環境委）: 発言薄
        "topics": {
            "decarbonization": {"stance":"conditional_support","confidence":0.4,
                "quotes":["カーボンニュートラルもこれは本気で"]},
        },
        "archetype": {"id":"low_engagement","label":"発言少・様子見","confidence":0.5,
            "rationale":"収集分は2件と少なく、明確な政策スタンスは読み取りにくい。要追加収集。"},
        "engagement":"low",
    },
}


def norm(s): return re.sub(r"\s+","",s or "")

def main():
    for mid, cls in PILOT.items():
        d=json.load(open(f"data/speeches/{mid}.json",encoding="utf-8"))
        corpus=norm(" ".join(s.get("speech") or "" for s in d["speeches"]))
        topics_out={}
        for tid,t in cls.get("topics",{}).items():
            ev=[]
            for q in t["quotes"]:
                if norm(q) in corpus: ev.append({"quote":q})
                else: print(f"[NG] {mid}/{tid}: quote未検出「{q}」"); sys.exit(1)
            topics_out[tid]={"stance":t["stance"],"confidence":t["confidence"],"evidence":ev}
        rec={"member_id":mid,"classified_by":"claude_code",
             "axes_version":common.load_axes().get("meta",{}).get("version"),
             "topics":topics_out,"archetype":cls["archetype"],
             "engagement":{"level":cls["engagement"],"relevant_speech_count":len(d["speeches"])},
             "flags":cls.get("flags",[])}
        (common.CLASSIFICATIONS/f"{mid}.json").write_text(
            json.dumps(rec,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"{mid} {d['speaker']}: {cls['archetype']['label']} / {cls['engagement']}")

if __name__=="__main__":
    main()

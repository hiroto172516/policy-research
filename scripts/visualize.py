#!/usr/bin/env python3
"""
STEP4 (可視化): 会議体・部会ごとの類型構成を円グラフ化する（メモ L26-27）。

  入力: output/aggregate.json
  出力: output/charts/<会議体>.png ＋ output/charts/_overall.png

日本語フォント: システムにCJKフォント(Noto Sans CJK / IPAexGothic等)があれば自動使用。
無い場合は豆腐(□)になるため、フォント導入を促す警告を出す。
"""
from __future__ import annotations
import argparse
import json
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import common

# 類型ラベル -> 固定色（会議体をまたいで色を統一）
COLOR = {
    "再エネ積極支持": "#2e7d32",
    "太陽光批判": "#f9a825",
    "脱炭素関心薄・経済安保重視": "#1565c0",
    "原子力・安定供給重視": "#6a1b9a",
    "発言少・様子見": "#9e9e9e",
    "分類保留": "#cfcfcf",
}


def setup_font() -> bool:
    """CJK対応フォントを探して設定。見つかれば True。"""
    candidates = ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic",
                  "TakaoGothic", "VL Gothic", "Source Han Sans JP"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            return True
    # ファイル名から探すフォールバック
    for f in font_manager.fontManager.ttflist:
        if re.search(r"(cjk|noto.*jp|ipa|gothic|source ?han)", f.name, re.I):
            plt.rcParams["font.family"] = f.name
            return True
    return False


def pie(title: str, counts: dict, path, subtitle: str | None = None) -> None:
    labels = list(counts.keys())
    sizes = list(counts.values())
    colors = [COLOR.get(l, "#bbbbbb") for l in labels]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    total = sum(sizes)
    ax.pie(sizes, labels=[f"{l}\n{n}名" for l, n in zip(labels, sizes)],
           colors=colors, autopct=lambda p: f"{p*total/100:.0f}", startangle=90,
           counterclock=False, textprops={"fontsize": 9})
    ax.set_title(subtitle or f"{title}（計{total}名）", fontsize=12)
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\-一-龠ぁ-んァ-ン]", "_", s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=str(common.OUTPUT / "aggregate.json"))
    ap.add_argument("--scope", choices=["committees", "party_divisions", "both"], default="both")
    args = ap.parse_args()

    charts = common.OUTPUT / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    if not setup_font():
        print("[WARN] CJKフォント未検出。日本語が□になります。"
              "→ `sudo apt-get install fonts-noto-cjk` 等で導入してください。")

    agg = json.loads(open(args.infile, encoding="utf-8").read())
    made = 0

    pie("全体の類型構成", agg["overall"], charts / "_overall.png")
    made += 1

    totals = agg.get("committee_totals", {})
    scopes = ["committees", "party_divisions"] if args.scope == "both" else [args.scope]
    for scope in scopes:
        prefix = "委員会" if scope == "committees" else "部会"
        for name, counts in agg.get(scope, {}).items():
            out = charts / f"{prefix}_{safe_name(name)}.png"
            classified = sum(counts.values())
            total_m = totals.get(name)
            # 分類済/全体を明示（パイロットで一部のみ分類の誤認防止）
            sub = (f"{name}（分類済 {classified} / 全 {total_m}名・パイロット）"
                   if total_m else None)
            pie(name, counts, out, subtitle=sub)
            made += 1

    print(f"円グラフ {made}枚を生成 -> {charts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

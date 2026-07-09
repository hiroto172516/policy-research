#!/usr/bin/env bash
# 政策調査パイプライン STEP1→STEP4 一括実行
# 使い方: bash run_pipeline.sh [--demo]
#   --demo : 会議録API/APIキーを使わず、合成分類データでSTEP4まで実証する
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--demo" ]]; then
  echo "== [DEMO] 合成分類データでSTEP3→STEP4を実証 =="
  python3 scripts/_make_sample_classifications.py
else
  echo "== STEP3-a 収集（会議録API） =="
  python3 scripts/fetch_speeches.py "${@}"
  echo "== STEP3-b 分類（Claude API / 要 ANTHROPIC_API_KEY） =="
  python3 scripts/classify.py
fi

echo "== STEP4-a 集計 =="
python3 scripts/aggregate.py
echo "== STEP4-b 可視化 =="
python3 scripts/visualize.py
echo "== 完了: output/charts/ を参照 =="

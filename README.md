# 政策調査 プロトタイプ（STEP1〜4）

`ヒアリング結果メモ.md` / `政策調査_進め方設計メモ.md` の STEP1〜4 を Claude Code 上で
実行可能にした試作パイプライン。**議員マスター名簿 → 評価軸 → 収集・類型化 → 会議体別の
構成可視化** までを通す。

> ⚠️ **現状は「構造実証」段階**です。`data/roster.csv` と `data/classifications/` は
> **合成データ**（実在議員ではない）。本番投入時に公式データへ差し替えてください。

## ステップ対応表

| STEP | 内容 | 実体 | 状態 |
|------|------|------|------|
| STEP1 | 議員マスター名簿（as_of時点管理） | `data/roster.csv` + `scripts/common.py` | ✅ スキーマ確定・合成サンプル |
| STEP2 | 評価軸の設定ファイル化 | `config/axes.yml` | ✅ DRAFT（**人間が確定**） |
| STEP3 | 収集＋類型化 | `scripts/fetch_speeches.py` / `scripts/classify.py` | ✅ 実装済（ライブ収集は要ネットワーク・要APIキー） |
| STEP4 | 会議体別 集計・可視化 | `scripts/aggregate.py` / `scripts/visualize.py` | ✅ 円グラフ生成まで実証 |

## セットアップ

```bash
pip3 install -r requirements.txt
# 日本語フォント（無い場合のみ）: sudo apt-get install fonts-noto-cjk / fonts-ipafont-gothic
```

## 実行

```bash
# 合成データで STEP3→STEP4 を実証（ネットワーク/APIキー不要）
bash run_pipeline.sh --demo

# 本番: 会議録APIから収集 → Claudeで分類 → 集計 → 可視化
export ANTHROPIC_API_KEY=sk-...
bash run_pipeline.sh --since 2025-01-01 --until 2026-06-30
```

個別実行:
```bash
python3 scripts/fetch_speeches.py --member M-0001 --dry-run   # URL確認のみ
python3 scripts/classify.py --member M-0001 --model claude-sonnet-5
python3 scripts/aggregate.py
python3 scripts/visualize.py --scope committees
```

## この環境で確認した制約（重要）

- **国会会議録API**: Claude Code のデータセンターIPからは **HTTP 403**（CloudFront遮断）。
  → 非遮断ネットワーク（事務所回線）またはプロキシ/Jina経由で `fetch_speeches.py` を実行する。
  （`データ取得検証メモ.md` のX/YouTube遮断と同種）
- **分類（STEP3）**: `classify.py` は `ANTHROPIC_API_KEY` があれば Claude API でバッチ分類。
  無い場合は分類プロンプトを `output/prompts/` に書き出す（Claude Code / claude.ai で手動実行も可）。
- **matplotlib / IPAGothic**: 導入済み。円グラフの日本語描画OK。

## 設計上のポイント（メモとの対応）

- **評価軸は人間が設計**（メモ L54-59）→ `config/axes.yml` を差し替えれば同データを再分類。
- **反対派・発言少も対象**（L64-65）→ 名簿は与党全員が土台、`low_engagement` 類型で様子見も可視化。
- **時点管理**（L83-88）→ 名簿・分類に `as_of` 列/フィールド。
- **収集は定期・分析は必要時**（L78-81）→ `fetch_speeches.py`(cron) と `classify.py`(オンデマンド) を分離。
- **機密の非公開面談メモ**（L16）→ 本パイプラインは公開情報のみ。非公開はローカル運用で別管理。

## 本番移行のTODO

1. `data/roster.csv` を公式名簿（衆議院/参議院）で置換し `verified=yes`・`source_url` を記録。
   発言者名でAPIを引くため、本名列（例 `speaker_name`）を追加し `--speaker-col` で指定。
2. `config/axes.yml` を武井氏の評価軸で確定（`status: 確定`）。5〜10名パイロットで精度検証。
3. 非遮断ネットワークで `fetch_speeches.py` を回し、`classify.py`（APIキー）でバッチ分類。
4. STEP5（定期収集の運用化）: cron/`/loop` で収集を定期化、分析は必要時トリガー。

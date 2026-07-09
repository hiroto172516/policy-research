#!/usr/bin/env python3
"""
STEP3 (分類・ワークシート生成): 収集発言・SNS投稿を評価軸(axes.yml)で分類するための
**Claude Code 用ワークシート**を生成する。

【方針】Anthropic API は使わない。分類は Claude Code（このエージェント）自身が
  ワークシートを読んで行う（キーワードタグ付けではなくClaudeの判断）。
  → 生成物: output/worksheets/<member_id>.md（議事録/X投稿＋評価軸＋出力スキーマ＋指示）
  Claude Code はこれを読み、分類JSONを data/classifications/<member_id>.json に書く。
  書いた分類は `validate_classifications.py` が quote実在などを機械検証する（安全ゲート）。

使い方:
  python3 scripts/classify.py                 # 収集済み全員のワークシートを生成
  python3 scripts/classify.py --member S-0160
  python3 scripts/classify.py --sources diet,x
"""
from __future__ import annotations
import argparse
import json
import sys

import common

# Claude Code が満たすべき出力スキーマ（data/classifications/<mid>.json）
OUTPUT_SCHEMA_DOC = """{
  "member_id": "<ID>",
  "classified_by": "claude_code",
  "axes_version": "<axes.ymlのversion>",
  "topics": {                      // 言及があったトピックのみ
    "<topic_id>": {
      "stance": "<stance_scaleのkey>",
      "confidence": 0.0-1.0,
      "evidence": [{"quote": "<原文に実在する文字列>", "source": "diet|x"}]
    }
  },
  "archetype": {"id": "<archetypeのid>", "label": "<label>", "confidence": 0.0-1.0, "rationale": "..."},
  "engagement": {"level": "high|medium|low|none", "relevant_speech_count": <int>},
  "flags": ["<任意>"]
}"""


def _format_diet_sources(speeches: list[dict]) -> str:
    if not speeches:
        return "(国会会議録の関連発言なし)"
    return "\n\n".join(
        f"[D{i+1}] {sp.get('date','')} {sp.get('meeting','')}（発言者: {sp.get('speaker','')}）\n{sp.get('speech','')}"
        for i, sp in enumerate(speeches))


def _format_x_sources(posts: list[dict]) -> str:
    if not posts:
        return "(X投稿なし)"
    return "\n\n".join(
        f"[X{i+1}] {p.get('date','')} @{p.get('author','')} own={p.get('own')} {p.get('url','')}\n{p.get('text','')}"
        for i, p in enumerate(posts))


def build_worksheet(member: dict, axes: dict, speeches: list[dict], x_posts: list[dict]) -> str:
    topics = "\n".join(
        f"- {t['id']}（{t['label']}）: {t['description']}" for t in axes["topics"])
    scale = "、".join(f"{s['key']}={s['label']}" for s in axes["stance_scale"])
    eng = "、".join(f"{e['key']}={e['label']}" for e in axes["engagement_scale"])
    arche = "\n".join(
        f"- {a['id']}（{a['label']}）: {a['definition']}" for a in axes["archetypes"])
    rules = axes.get("output_rules", {})
    diet_body = _format_diet_sources(speeches)
    x_body = _format_x_sources(x_posts)
    source_count = len(speeches) + len(x_posts)
    return f"""# 分類ワークシート: {member.get('member_id')} {member.get('name','')}（{member.get('party','')}）

あなた（Claude Code）はJCLPの政策調査アナリストとして、**下の国会会議録・X投稿という事実のみ**に基づき
評価軸に沿ってこの議員のスタンスを分類し、`data/classifications/{member.get('member_id')}.json`
に下記スキーマで書き出してください。**発言に無い立場を推測で埋めない**（言及なし＝トピックを載せない）。

## 安全原則
- 各スタンスに根拠発言(quote)を必須。**quoteは下の原文に実在する文字列**のみ（捏造禁止）。
- evidence.source は、国会会議録なら "diet"、X投稿なら "x" を入れる。
- 国会会議録を優先根拠とし、X投稿は補助根拠として扱う。Xのみで強い立場判定をする場合は confidence を控えめにする。
- 関連発言が {rules.get('low_engagement_threshold',2)} 件未満なら archetype を low_engagement に寄せる。
- 原子力等センシティブ題材は flags に "sensitive:原子力" 等。
- 委員長等の議事運営のみでスタンス不明なら low_engagement＋flagsに理由。

## 評価軸（トピック）
{topics}

## スタンス尺度（stance の値）
{scale}
## 関心度（engagement.level の値）
{eng}
## 類型（archetype の id/label から1つ）
{arche}

## 出力スキーマ（data/classifications/{member.get('member_id')}.json）
```json
{OUTPUT_SCHEMA_DOC}
```

## この議員の根拠データ（計{source_count}件）

### 国会会議録（{len(speeches)}件・発言者厳密一致済）
{diet_body}

### X投稿（{len(x_posts)}件・Jina経由取得。own=trueは本人投稿、own=falseはRT等）
{x_body}

書き出したら `python3 scripts/validate_classifications.py --member {member.get('member_id')}` で検証すること。
"""


def load_speeches(mid: str) -> list[dict]:
    sp_path = common.SPEECHES / f"{mid}.json"
    if not sp_path.exists():
        return []
    return json.loads(sp_path.read_text(encoding="utf-8")).get("speeches", [])


def load_x_posts(mid: str) -> list[dict]:
    xp_path = common.DATA / "x_posts" / f"{mid}.json"
    if not xp_path.exists():
        return []
    return json.loads(xp_path.read_text(encoding="utf-8")).get("posts", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member")
    ap.add_argument("--sources", default="diet,x",
                    help="ワークシートに含めるソース。カンマ区切り: diet,x")
    args = ap.parse_args()

    common.ensure_dirs()
    ws_dir = common.OUTPUT / "worksheets"
    ws_dir.mkdir(exist_ok=True)
    axes = common.load_axes()
    roster = {r["member_id"]: r for r in common.load_roster()}

    sources = {s.strip() for s in args.sources.split(",") if s.strip()}
    target_ids = set()
    if "diet" in sources:
        target_ids.update(p.stem for p in common.SPEECHES.glob("*.json"))
    if "x" in sources:
        target_ids.update(p.stem for p in (common.DATA / "x_posts").glob("*.json"))
    targets = [args.member] if args.member else sorted(target_ids)
    if not targets:
        print("収集済みデータがありません。先に fetch_speeches.py / fetch_x.py を実行してください。", file=sys.stderr)
        return 1

    for mid in targets:
        member = roster.get(mid, {"member_id": mid})
        speeches = load_speeches(mid) if "diet" in sources else []
        x_posts = load_x_posts(mid) if "x" in sources else []
        if not speeches and not x_posts:
            continue
        (ws_dir / f"{mid}.md").write_text(build_worksheet(member, axes, speeches, x_posts), encoding="utf-8")
        print(f"{mid}: ワークシート生成（議事録{len(speeches)}件/X{len(x_posts)}件）-> output/worksheets/{mid}.md")
    print("\n→ Claude Code が各ワークシートを読み、data/classifications/<mid>.json を作成。"
          "\n  その後 validate_classifications.py で検証してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

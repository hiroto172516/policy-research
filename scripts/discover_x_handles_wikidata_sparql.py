#!/usr/bin/env python3
"""
Wikidata SPARQL で x_handles.csv を一括補完する。

採用条件:
  - x_handle が空欄の議員のみ対象
  - 日本語ラベルが roster の氏名（空白除去後）と完全一致
  - P2002(Twitter/X username) が1つだけ見つかる

Wikidata は一次情報ではないため note には「要公式確認」と残す。
複数ハンドルが見つかった人物は誤登録を避けてスキップする。
"""
from __future__ import annotations
import argparse
import csv
import time

import requests

import common


FIELDS = ["member_id", "name", "party", "x_handle", "note"]
CANDIDATE_FIELDS = ["member_id", "name", "party", "status", "candidates", "note"]
ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "JCLP-policy-research/0.1 (contact: JCLP jimukyoku)"}


def compact(s: str) -> str:
    return "".join((s or "").split())


def chunks(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def query_handles(labels: list[str]) -> dict[str, list[tuple[str, str]]]:
    values = " ".join(f'"{label}"@ja' for label in labels)
    query = f"""
SELECT ?person ?personLabel ?handle WHERE {{
  VALUES ?personLabel {{ {values} }}
  ?person rdfs:label ?personLabel .
  ?person wdt:P31 wd:Q5 .
  ?person wdt:P2002 ?handle .
}}
"""
    r = requests.get(ENDPOINT, params={"query": query, "format": "json"},
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    out: dict[str, list[tuple[str, str]]] = {}
    for b in r.json().get("results", {}).get("bindings", []):
        label = b["personLabel"]["value"]
        qid = b["person"]["value"].rsplit("/", 1)[-1]
        handle = b["handle"]["value"].strip().lstrip("@")
        out.setdefault(label, []).append((handle, qid))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    path = common.DATA / "x_handles.csv"
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    targets = [r for r in rows if not r.get("x_handle", "").strip()]
    if args.limit:
        targets = targets[:args.limit]
    labels = sorted({compact(r["name"]) for r in targets if compact(r["name"])})

    hits: dict[str, list[tuple[str, str]]] = {}
    for part in chunks(labels, 80):
        hits.update(query_handles(part))
        time.sleep(1.0)

    updated = 0
    skipped_multi = 0
    candidates = []
    for row in rows:
        if row.get("x_handle", "").strip():
            continue
        label = compact(row["name"])
        found = hits.get(label, [])
        unique_handles = sorted({h for h, _ in found})
        unique_qids = sorted({q for _, q in found})
        if not found:
            candidates.append({
                "member_id": row["member_id"],
                "name": row["name"],
                "party": row.get("party", ""),
                "status": "not_found",
                "candidates": "",
                "note": "Wikidata P2002候補なし。公式サイト・政党ページ等で要調査",
            })
            continue
        if len(unique_handles) != 1:
            skipped_multi += 1
            print(f"[SKIP multiple] {row['member_id']} {row['name']}: {', '.join('@' + h for h in unique_handles)}")
            candidates.append({
                "member_id": row["member_id"],
                "name": row["name"],
                "party": row.get("party", ""),
                "status": "multiple",
                "candidates": ";".join(unique_handles),
                "note": f"Wikidata P2002が複数候補。QID={','.join(unique_qids)}。公式確認後に1つをx_handles.csvへ登録",
            })
            continue
        handle = unique_handles[0]
        qid = unique_qids[0] if len(unique_qids) == 1 else ",".join(unique_qids)
        print(f"[HIT] {row['member_id']} {row['name']}: @{handle}")
        if not args.dry_run:
            row["x_handle"] = handle
            row["note"] = f"Wikidata P2002候補 {qid}。要公式確認"
            updated += 1

    if not args.dry_run and updated:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    if not args.dry_run:
        cand_path = common.DATA / "x_handle_candidates.csv"
        with open(cand_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
            writer.writeheader()
            writer.writerows(candidates)
        print(f"候補確認リスト: {cand_path} ({len(candidates)}件)")

    filled = sum(1 for r in rows if r.get("x_handle", "").strip())
    print(f"完了: hits={updated} skipped_multi={skipped_multi} filled={filled}/{len(rows)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

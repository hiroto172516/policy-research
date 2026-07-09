#!/usr/bin/env python3
"""
未登録の X ハンドルを DuckDuckGo 検索 + Xプロフィール本文で補完する。

採用条件:
  - 候補Xプロフィール本文に氏名（空白除去）が含まれる
  - 「衆議院議員」「参議院議員」「国会議員」「議員」等の公職ヒントがある
  - 複数候補がある場合は、最高スコアが次点より明確に高い

注意:
  - 検索結果・Xプロフィール本文による自動候補なので、note に「要公式確認」を残す。
  - 曖昧な候補は採用せず data/x_handle_unresolved.csv に残す。
"""
from __future__ import annotations
import argparse
import csv
import html
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import requests

import common
from fetch_x import jina_get


FIELDS = ["member_id", "name", "party", "x_handle", "note"]
UNRESOLVED_FIELDS = ["member_id", "name", "party", "status", "candidates", "scores", "note"]
DDG = "https://html.duckduckgo.com/html/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
PUBLIC_HINTS = ("衆議院議員", "参議院議員", "国会議員", "議員", "大臣", "副大臣", "政務官", "候補", "選挙区")
BAD_HANDLES = {
    "home", "search", "i", "intent", "share", "hashtag", "login", "signup",
    "settings", "messages", "notifications", "explore",
}


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def parse_ddg_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return html.unescape(url)


def extract_handle(url: str) -> str | None:
    url = parse_ddg_url(url)
    m = re.search(r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})(?:[/?#]|$)", url)
    if not m:
        return None
    h = m.group(1)
    if h.lower() in BAD_HANDLES:
        return None
    return h


def search_handles(name: str, chamber: str | None = None) -> list[str]:
    queries = [
        f"{name} X",
        f"{name} Twitter",
        f"{name} {'衆議院議員' if chamber == '衆' else '参議院議員' if chamber == '参' else '国会議員'} X",
    ]
    seen: list[str] = []
    for q in queries:
        try:
            r = requests.get(DDG, params={"q": q}, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] search failed {name}: {e}")
            continue
        for raw in re.findall(r'href="([^"]+)"', r.text):
            h = extract_handle(raw)
            if h and h not in seen:
                seen.append(h)
        time.sleep(0.5)
    return seen[:8]


def profile_score(markdown: str, row: dict, handle: str) -> tuple[int, list[str]]:
    profile = markdown.split("Posts Posts", 1)[0]
    text = compact(profile)
    name = compact(row["name"])
    reasons = []
    score = 0
    if name and name in text:
        score += 8
        reasons.append("name")
    for hint in PUBLIC_HINTS:
        if hint in profile:
            score += 3 if "議員" in hint else 1
            reasons.append(hint)
            break
    party = row.get("party", "")
    if party and party not in ("無", "無所属", "中道", "民主", "みらい") and party in profile:
        score += 2
        reasons.append("party")
    if "公式" in profile:
        score += 1
        reasons.append("official")
    if re.search(r"(office|jim(u|u)syo|jimusho|koenkai|support|team)", handle, re.I):
        score += 1
        reasons.append("org_handle")
    if "候補" in profile and "議員" not in profile:
        score -= 2
        reasons.append("candidate_only")
    return score, reasons


def resolve_one(row: dict, handles: list[str], key: str) -> tuple[str | None, list[dict]]:
    scored = []
    for h in handles:
        try:
            md = jina_get(f"https://x.com/{h}", key)
        except Exception as e:  # noqa: BLE001
            scored.append({"handle": h, "score": -99, "reasons": [f"fetch_error:{e}"]})
            continue
        score, reasons = profile_score(md, row, h)
        scored.append({"handle": h, "score": score, "reasons": reasons})
        time.sleep(0.8)
    def rank(item: dict) -> tuple:
        reasons = item["reasons"]
        handle = item["handle"]
        is_org = bool(re.search(r"(office|jim(u|u)syo|jimusho|koenkai|support|team|staff)", handle, re.I))
        # 同点なら公式表記を少し優先。ただし公式差が無ければ個人名アカウントを優先。
        return (
            item["score"],
            1 if "official" in reasons else 0,
            0 if is_org else 1,
        )
    valid = sorted([s for s in scored if s["score"] >= 10], key=rank, reverse=True)
    if not valid:
        return None, scored
    if len(valid) == 1:
        return valid[0]["handle"], scored
    if valid[0]["score"] >= 13:
        return valid[0]["handle"], scored
    if valid[0]["score"] - valid[1]["score"] >= 3:
        return valid[0]["handle"], scored
    return None, scored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--member")
    args = ap.parse_args()

    key = common.get_jina_key()
    if not key:
        raise SystemExit("JINA_API_KEY または config/jina.key が必要です")

    roster = {r["member_id"]: r for r in common.load_roster()}
    path = common.DATA / "x_handles.csv"
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    unresolved = []
    targets = [
        r for r in rows
        if not r.get("x_handle", "").strip()
        and not r.get("note", "").startswith("未解決:")
    ]
    if args.member:
        targets = [r for r in targets if r["member_id"] == args.member]
    if args.limit:
        targets = targets[:args.limit]

    # 既存候補リスト（Wikidata複数候補）を優先的に使う
    cand_map: dict[str, list[str]] = {}
    cand_path = common.DATA / "x_handle_candidates.csv"
    if cand_path.exists():
        with open(cand_path, encoding="utf-8") as f:
            for c in csv.DictReader(f):
                if c.get("candidates"):
                    cand_map[c["member_id"]] = [x for x in c["candidates"].split(";") if x]

    updated = 0
    for row in targets:
        member = roster.get(row["member_id"], {})
        handles = cand_map.get(row["member_id"]) or search_handles(row["name"], member.get("chamber"))
        deduped = {}
        for h in handles:
            deduped.setdefault(h.lower(), h)
        handles = list(deduped.values())
        if not handles:
            print(f"[MISS] {row['member_id']} {row['name']}: no candidates")
            unresolved.append({
                "member_id": row["member_id"], "name": row["name"], "party": row.get("party", ""),
                "status": "not_found", "candidates": "", "scores": "",
                "note": "検索結果にX候補なし",
            })
            if not args.dry_run:
                row["note"] = "未解決: 検索結果にX候補なし"
            continue
        chosen, scored = resolve_one(row, handles, key)
        score_text = ";".join(f"{s['handle']}={s['score']}({','.join(s['reasons'])})" for s in scored)
        if chosen:
            print(f"[HIT] {row['member_id']} {row['name']}: @{chosen} [{score_text}]")
            if not args.dry_run:
                row["x_handle"] = chosen
                row["note"] = "Xプロフィール/検索結果から自動登録。要公式確認"
                updated += 1
        else:
            print(f"[SKIP] {row['member_id']} {row['name']}: {score_text}")
            unresolved.append({
                "member_id": row["member_id"], "name": row["name"], "party": row.get("party", ""),
                "status": "ambiguous", "candidates": ";".join(handles), "scores": score_text,
                "note": "自動判定条件を満たさず。公式確認が必要",
            })
            if not args.dry_run:
                row["note"] = "未解決: 自動判定条件を満たさず。公式確認が必要"

    if not args.dry_run:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)

    if not args.dry_run:
        out = common.DATA / "x_handle_unresolved.csv"
        with open(out, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=UNRESOLVED_FIELDS)
            writer.writeheader()
            writer.writerows(unresolved)
        print(f"未解決リスト: {out} ({len(unresolved)}件)")
    filled = sum(1 for r in rows if r.get("x_handle", "").strip())
    print(f"完了: updated={updated} filled={filled}/{len(rows)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

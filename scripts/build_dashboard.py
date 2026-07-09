#!/usr/bin/env python3
"""
STEP4+: 名簿(roster)＋分類(classifications)＋評価軸(axes)を1つの自己完結HTMLに出力する。
  概要／ネットワーク／カテゴリ／議員詳細 をタブで切替できる分析ダッシュボード。
  出力:
    output/policy_dashboard.html          … 単体で開ける完全HTML（1ファイル）
    output/policy_dashboard.fragment.html … Artifact公開用（doctype等なし）
  ネットワーク・外部依存なし（データ・CSS・JSを全て内包）。
使い方: python3 scripts/build_dashboard.py
"""
from __future__ import annotations
import json
from collections import Counter

import common

ARCH_ORDER = ["renewable_champion", "econ_security_focus", "solar_skeptic",
              "nuclear_advocate", "low_engagement", "unclassified"]


def trim(s: str, n: int = 140) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def build_data() -> dict:
    axes = common.load_axes()
    roster = common.load_roster()
    arch_label = {a["id"]: a["label"] for a in axes["archetypes"]}
    stance_label = {s["key"]: s["label"] for s in axes["stance_scale"]}
    topic_label = {t["id"]: t["label"] for t in axes["topics"]}

    # 分類の読み込み
    cls = {}
    for f in common.CLASSIFICATIONS.glob("*.json"):
        cls[f.stem] = json.loads(f.read_text(encoding="utf-8"))

    members = []
    party_counts, tier_counts, sen_counts = Counter(), Counter(), Counter()
    committee_totals = Counter()
    for r in roster:
        mid = r["member_id"]
        comm = r.get("committees_list") or []
        for c in comm:
            committee_totals[c] += 1
        party_counts[r.get("party", "")] += 1
        tier_counts[r.get("influence_tier", "")] += 1
        sen_counts[r.get("seniority", "")] += 1
        c = cls.get(mid)
        cls_out = None
        if c:
            topics = {}
            for tid, t in (c.get("topics") or {}).items():
                topics[tid] = {
                    "stance": t.get("stance"),
                    "stanceLabel": stance_label.get(t.get("stance"), t.get("stance")),
                    "topicLabel": topic_label.get(tid, tid),
                    "quotes": [e.get("quote") for e in t.get("evidence", []) if e.get("quote")],
                }
            cls_out = {
                "archetype": c.get("archetype", {}).get("id"),
                "archetypeLabel": c.get("archetype", {}).get("label"),
                "rationale": c.get("archetype", {}).get("rationale", ""),
                "engagement": (c.get("engagement") or {}).get("level"),
                "speechCount": (c.get("engagement") or {}).get("relevant_speech_count"),
                "topics": topics,
                "flags": c.get("flags", []),
            }
        try:
            elected = int("".join(ch for ch in (r.get("elected_count") or "") if ch.isdigit()) or 0)
        except ValueError:
            elected = 0
        members.append({
            "id": mid, "name": r.get("name", ""), "party": r.get("party", ""),
            "chamber": r.get("chamber", ""), "district": r.get("district", ""),
            "elected": elected, "tier": r.get("influence_tier", ""),
            "seniority": r.get("seniority", ""), "roles": r.get("roles", ""),
            "committees": comm, "career": trim(r.get("career", "")),
            "cls": cls_out,
        })

    # 会議体別 類型集計（分類済）
    comm_arch: dict[str, Counter] = {}
    overall = Counter()
    for m in members:
        if not m["cls"]:
            continue
        lbl = m["cls"]["archetypeLabel"] or "分類保留"
        overall[lbl] += 1
        for c in m["committees"]:
            comm_arch.setdefault(c, Counter())[lbl] += 1

    return {
        "meta": {
            "total": len(members),
            "classified": sum(1 for m in members if m["cls"]),
            "axesVersion": axes.get("meta", {}).get("version"),
        },
        "archLabels": arch_label,
        "archOrder": ARCH_ORDER,
        "members": members,
        "partyCounts": dict(party_counts.most_common()),
        "tierCounts": {k: tier_counts.get(k, 0) for k in ["A", "B", "C"]},
        "seniorityCounts": {k: sen_counts.get(k, 0) for k in ["senior", "mid", "junior"]},
        "committeeTotals": dict(committee_totals.most_common()),
        "commArch": {k: dict(v) for k, v in comm_arch.items()},
        "overall": dict(overall),
    }


# ---- HTML/CSS/JS テンプレート（inner＝Artifact用の本体） -------------------
def render_inner(data: dict) -> str:
    # U+FFFD（復号失敗の置換文字）は Artifact 公開でエラーになるため除去（防御）
    payload = json.dumps(data, ensure_ascii=False).replace("�", "")
    return CSS + f'\n<div id="app"></div>\n<script>\nconst DATA = {payload};\n' + JS + "\n</script>\n"


CSS = """<style>
:root{
  --bg:#f7f7f6; --surface:#ffffff; --surface-2:#fbfbfa; --border:#e6e6e9; --border-strong:#d4d4da;
  --ink:#17171c; --ink-2:#57575f; --ink-3:#8a8a93;
  --accent:#3d47a2; --accent-soft:#eceaf6; --focus:#5a63c9;
  --arch-renewable:#008300; --arch-econ:#2a78d6; --arch-solar:#eda100; --arch-nuclear:#4a3aa7;
  --arch-low:#9a9aa2; --arch-none:#c7c7cd;
  --tierA:#1c5cab; --tierB:#5598e7; --tierC:#bcd6f6;
  --shadow:0 1px 2px rgba(20,20,30,.06),0 6px 20px rgba(20,20,30,.05);
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:"Hiragino Kaku Gothic ProN","Hiragino Sans","Noto Sans JP","Yu Gothic",Meiryo,system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#121214; --surface:#1b1b1f; --surface-2:#202026; --border:#2c2c33; --border-strong:#3a3a42;
  --ink:#f1f1f4; --ink-2:#adadb6; --ink-3:#77777f;
  --accent:#9aa0f0; --accent-soft:#23233a; --focus:#8b91e8;
  --arch-econ:#3987e5; --arch-solar:#c98500; --arch-nuclear:#9085e9; --arch-low:#8f8f98; --arch-none:#55555c;
  --tierA:#3987e5; --tierB:#256abf; --tierC:#1a3f75;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35);
}}
:root[data-theme="light"]{--bg:#f7f7f6;--surface:#fff;--surface-2:#fbfbfa;--border:#e6e6e9;--border-strong:#d4d4da;--ink:#17171c;--ink-2:#57575f;--ink-3:#8a8a93;--accent:#3d47a2;--accent-soft:#eceaf6;--arch-econ:#2a78d6;--arch-solar:#eda100;--arch-nuclear:#4a3aa7;--arch-low:#9a9aa2;--arch-none:#c7c7cd;--tierA:#1c5cab;--tierB:#5598e7;--tierC:#bcd6f6;}
:root[data-theme="dark"]{--bg:#121214;--surface:#1b1b1f;--surface-2:#202026;--border:#2c2c33;--border-strong:#3a3a42;--ink:#f1f1f4;--ink-2:#adadb6;--ink-3:#77777f;--accent:#9aa0f0;--accent-soft:#23233a;--arch-econ:#3987e5;--arch-solar:#c98500;--arch-nuclear:#9085e9;--arch-low:#8f8f98;--arch-none:#55555c;--tierA:#3987e5;--tierB:#256abf;--tierC:#1a3f75;}
*{box-sizing:border-box}
#app{font-family:var(--sans);color:var(--ink);background:var(--bg);line-height:1.6;
  -webkit-font-smoothing:antialiased;padding:0;margin:0 auto;max-width:1200px}
#app h1,#app h2,#app h3{margin:0;font-weight:700;text-wrap:balance;letter-spacing:.01em}
.wrap{padding:clamp(16px,3vw,32px)}
.head{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:6px}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
.title{font-size:clamp(20px,3.2vw,28px);line-height:1.2}
.sub{color:var(--ink-2);font-size:13px;margin-top:2px}
.tabs{display:flex;gap:2px;flex-wrap:wrap;margin:18px 0 4px;border-bottom:1px solid var(--border)}
.tab{appearance:none;border:0;background:none;font:inherit;font-size:14px;font-weight:600;color:var(--ink-2);
  padding:9px 14px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;border-radius:6px 6px 0 0}
.tab:hover{color:var(--ink);background:var(--surface-2)}
.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.panel{padding-top:18px}
.grid{display:grid;gap:14px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}
.kpi .n{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.02em;line-height:1}
.kpi .l{font-size:12px;color:var(--ink-2);margin-top:6px}
.kpi .h{font-size:11px;color:var(--ink-3);margin-top:2px}
.two{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.ctitle{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:2px}
.cnote{font-size:11px;color:var(--ink-3);margin-bottom:12px}
.bar-row{display:grid;grid-template-columns:96px 1fr 44px;align-items:center;gap:10px;margin:5px 0;font-size:12px}
.bar-row .k{color:var(--ink-2);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{height:14px;background:var(--surface-2);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px}
.bar-row .v{font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:10px;font-size:12px;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
.donut-wrap{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.stack{display:flex;height:20px;border-radius:5px;overflow:hidden;background:var(--surface-2)}
.stack i{display:block;height:100%;border-right:2px solid var(--surface)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
.filters input,.filters select{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--border-strong);
  border-radius:8px;background:var(--surface);color:var(--ink)}
.filters input:focus,.filters select:focus{outline:2px solid var(--focus);outline-offset:1px}
.count{font-size:12px;color:var(--ink-3);margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{text-align:left;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);
  font-weight:700;padding:8px 10px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--surface)}
tbody td{padding:8px 10px;border-bottom:1px solid var(--border)}
tbody tr{cursor:pointer}
tbody tr:hover{background:var(--surface-2)}
.tablewrap{max-height:60vh;overflow:auto;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;
  border:1px solid var(--border-strong);color:var(--ink-2);background:var(--surface-2);white-space:nowrap}
.chip.arch{color:#fff;border:0}
.tierbadge{font-size:11px;font-weight:800;font-family:var(--mono);padding:1px 7px;border-radius:5px;color:#fff}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.drawer-bg{position:fixed;inset:0;background:rgba(10,10,15,.44);opacity:0;pointer-events:none;transition:opacity .18s;z-index:40}
.drawer-bg.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(460px,94vw);background:var(--surface);border-left:1px solid var(--border);
  box-shadow:-8px 0 30px rgba(0,0,0,.18);transform:translateX(100%);transition:transform .2s ease;z-index:41;overflow-y:auto}
.drawer.on{transform:none}
.drawer .dwrap{padding:20px 22px}
.dclose{float:right;appearance:none;border:1px solid var(--border-strong);background:var(--surface-2);color:var(--ink-2);
  border-radius:8px;width:30px;height:30px;font-size:16px;cursor:pointer}
.dmeta{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.section-t{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:700;margin:18px 0 6px}
.stance-row{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px}
.stance-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
.quote{font-size:12px;color:var(--ink-2);border-left:2px solid var(--border-strong);padding:2px 0 2px 10px;margin:5px 0}
.career{font-size:12.5px;color:var(--ink-2);line-height:1.7}
svg{display:block;max-width:100%}
.node-c{cursor:pointer}
.tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12px;padding:6px 9px;border-radius:7px;
  opacity:0;transition:opacity .1s;z-index:50;max-width:240px;box-shadow:var(--shadow)}
.tip.on{opacity:1}
.foot{margin:26px 0 8px;font-size:11px;color:var(--ink-3);text-align:center}
.themebtn{appearance:none;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink-2);
  border-radius:8px;padding:6px 11px;font:inherit;font-size:12px;cursor:pointer}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>"""


JS = r"""
const $=(s,r=document)=>r.querySelector(s), el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
function cssv(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
const ARCHVAR={renewable_champion:'--arch-renewable',econ_security_focus:'--arch-econ',solar_skeptic:'--arch-solar',nuclear_advocate:'--arch-nuclear',low_engagement:'--arch-low',unclassified:'--arch-none'};
function archColor(id){return cssv(ARCHVAR[id]||'--arch-none')||'#999';}
const LBL=DATA.archLabels; const byLabelId={}; Object.keys(LBL).forEach(id=>byLabelId[LBL[id]]=id);
function archIdFromLabel(l){return byLabelId[l]||'unclassified';}
const STANCE_C={strong_support:'#008300',conditional_support:'#5da35d',neutral_unknown:'#9a9aa2',cautious:'#e0913a',opposed:'#d03b3b'};

// ---------- App shell ----------
const app=$('#app');
function render(){
  app.innerHTML='';
  const wrap=el('div','wrap');
  const head=el('div','head');
  head.innerHTML=`<div><div class="eyebrow">JCLP 政策調査</div>
    <h1 class="title">与党議員 気候・エネルギー政策 スタンス分析</h1>
    <div class="sub">名簿 ${DATA.meta.total}名（実データ）／分類済 ${DATA.meta.classified}名（パイロット・評価軸v${DATA.meta.axesVersion}）</div></div>`;
  const tbtn=el('button','themebtn','◐ テーマ');
  tbtn.onclick=toggleTheme; head.appendChild(tbtn);
  wrap.appendChild(head);

  const tabs=el('div','tabs'); const names=[['overview','概要'],['network','ネットワーク'],['category','カテゴリ'],['members','議員詳細']];
  names.forEach(([k,l])=>{const b=el('button','tab',l);b.setAttribute('role','tab');b.setAttribute('aria-selected',state.tab===k);b.onclick=()=>{state.tab=k;render();};tabs.appendChild(b);});
  wrap.appendChild(tabs);
  const panel=el('div','panel'); panel.id='panel'; wrap.appendChild(panel);
  wrap.appendChild(el('div','foot','出典: 衆議院・参議院 公式議員一覧／各院 委員名簿／首相官邸 閣僚等名簿／国会会議録検索API。分類はClaude Codeがルール（評価軸v'+DATA.meta.axesVersion+'）で判定し、根拠発言の実在を検証済。'));
  app.appendChild(wrap);
  ({overview:viewOverview,network:viewNetwork,category:viewCategory,members:viewMembers})[state.tab](panel);
}
const state={tab:'overview'};
function toggleTheme(){const r=document.documentElement;const cur=r.getAttribute('data-theme')|| (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');r.setAttribute('data-theme',cur==='dark'?'light':'dark');render();}

// ---------- charts ----------
function barChart(rows,color){ // rows:[{k,v,c?}]
  const max=Math.max(1,...rows.map(r=>r.v)); const box=el('div');
  rows.forEach(r=>{const row=el('div','bar-row');
    const t=el('div','bar-track'); const f=el('div','bar-fill'); f.style.width=(r.v/max*100)+'%'; f.style.background=r.c||color; t.appendChild(f);
    row.appendChild(el('div','k',r.k)); row.appendChild(t); row.appendChild(el('div','v',r.v));
    box.appendChild(row);});
  return box;
}
function donut(rows,size=132){ // rows:[{label,v,color}]
  const tot=rows.reduce((a,r)=>a+r.v,0)||1; const R=size/2, r0=R-14; let a0=-Math.PI/2;
  const ns='http://www.w3.org/2000/svg'; const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox',`0 0 ${size} ${size}`); svg.setAttribute('width',size); svg.setAttribute('height',size);
  rows.forEach(r=>{const a1=a0+r.v/tot*Math.PI*2; const large=(a1-a0)>Math.PI?1:0;
    const x0=R+r0*Math.cos(a0),y0=R+r0*Math.sin(a0),x1=R+r0*Math.cos(a1),y1=R+r0*Math.sin(a1);
    const p=document.createElementNS(ns,'path');
    p.setAttribute('d',`M ${R} ${R} L ${x0} ${y0} A ${r0} ${r0} 0 ${large} 1 ${x1} ${y1} Z`);
    p.setAttribute('fill',r.color); p.setAttribute('stroke',cssv('--surface')); p.setAttribute('stroke-width','2');
    svg.appendChild(p); a0=a1;});
  const hole=document.createElementNS(ns,'circle'); hole.setAttribute('cx',R);hole.setAttribute('cy',R);hole.setAttribute('r',r0*0.58);
  hole.setAttribute('fill',cssv('--surface')); svg.appendChild(hole);
  const t=document.createElementNS(ns,'text'); t.setAttribute('x',R);t.setAttribute('y',R+5);t.setAttribute('text-anchor','middle');
  t.setAttribute('font-size','20');t.setAttribute('font-weight','800');t.setAttribute('fill',cssv('--ink'));t.textContent=tot;
  svg.appendChild(t); return svg;
}
function legend(rows){const b=el('div','legend');rows.forEach(r=>{const s=el('span');s.innerHTML=`<i class="sw" style="background:${r.color}"></i>${r.label} <b style="color:var(--ink)">${r.v}</b>`;b.appendChild(s);});return b;}

// ---------- Overview ----------
function viewOverview(p){
  const kg=el('div','grid kpis');
  const kpi=(n,l,h)=>{const c=el('div','card kpi');c.innerHTML=`<div class="n mono">${n}</div><div class="l">${l}</div>${h?`<div class="h">${h}</div>`:''}`;return c;};
  const tc=DATA.tierCounts;
  kg.append(kpi(DATA.meta.total,'与党議員 総数','衆'+DATA.members.filter(m=>m.chamber==='衆').length+' / 参'+DATA.members.filter(m=>m.chamber==='参').length),
    kpi(tc.A,'Tier A（重点・キーマン）','大臣・副大臣・政務官・委員長等'),
    kpi(Object.keys(DATA.partyCounts).length,'会派数',''),
    kpi(DATA.meta.classified,'分類済（パイロット）','評価軸v'+DATA.meta.axesVersion));
  p.appendChild(kg);

  const g=el('div','grid two');g.style.marginTop='14px';
  // party bar
  const c1=el('div','card');c1.appendChild(el('div','ctitle','会派別 議員数'));c1.appendChild(el('div','cnote','公式表記の会派名'));
  const prows=Object.entries(DATA.partyCounts).slice(0,10).map(([k,v])=>({k,v,c:'var(--tierB)'}));
  c1.appendChild(barChart(prows,'var(--tierB)'));g.appendChild(c1);
  // tier donut
  const c2=el('div','card');c2.appendChild(el('div','ctitle','影響力 Tier 構成'));c2.appendChild(el('div','cnote','名簿の役職・委員会から算出'));
  const dw=el('div','donut-wrap');
  const trows=[{label:'A 重点',v:tc.A,color:cssv('--tierA')},{label:'B 通常監視',v:tc.B,color:cssv('--tierB')},{label:'C 様子見',v:tc.C,color:cssv('--tierC')}];
  dw.appendChild(donut(trows));dw.appendChild(legend(trows));c2.appendChild(dw);g.appendChild(c2);
  // seniority
  const c3=el('div','card');c3.appendChild(el('div','ctitle','当選回数（seniority）分布'));c3.appendChild(el('div','cnote','senior≧5回 / mid≧2回 / junior'));
  const sc=DATA.seniorityCounts;
  c3.appendChild(barChart([{k:'senior',v:sc.senior},{k:'mid',v:sc.mid},{k:'junior',v:sc.junior}],'var(--accent)'));g.appendChild(c3);
  // archetype donut (classified)
  const c4=el('div','card');c4.appendChild(el('div','ctitle','類型構成（分類済）'));c4.appendChild(el('div','cnote','パイロット '+DATA.meta.classified+'名。発言スタンスに基づく'));
  const arows=DATA.archOrder.filter(id=>DATA.overall[LBL[id]]).map(id=>({label:LBL[id],v:DATA.overall[LBL[id]],color:archColor(id)}));
  const dw2=el('div','donut-wrap');dw2.appendChild(donut(arows));dw2.appendChild(legend(arows));c4.appendChild(dw2);g.appendChild(c4);
  p.appendChild(g);
}

// ---------- Network ----------
function viewNetwork(p){
  const card=el('div','card');
  card.appendChild(el('div','ctitle','議員 × 委員会 ネットワーク（分類済パイロット）'));
  card.appendChild(el('div','cnote','●＝議員（色＝類型）／■＝委員会。線＝所属。ドラッグで動かせます。ホバーで詳細。'));
  const classified=DATA.members.filter(m=>m.cls);
  const commSet=new Set(); classified.forEach(m=>m.committees.forEach(c=>commSet.add(c)));
  const nodes=[],idx={};
  classified.forEach(m=>{idx['m:'+m.id]=nodes.length;nodes.push({id:'m:'+m.id,label:m.name,type:'m',color:archColor(m.cls.archetype),m});});
  [...commSet].forEach(c=>{idx['c:'+c]=nodes.length;nodes.push({id:'c:'+c,label:c,type:'c'});});
  const links=[]; classified.forEach(m=>m.committees.forEach(c=>{if(commSet.has(c))links.push([idx['m:'+m.id],idx['c:'+c]]);}));
  const W=Math.min(1120,card.clientWidth||900), H=520;
  nodes.forEach((n,i)=>{n.x=W/2+Math.cos(i)*160*Math.random();n.y=H/2+Math.sin(i)*140*Math.random();n.vx=0;n.vy=0;});
  const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('width','100%');svg.setAttribute('height',H);
  const gl=document.createElementNS(ns,'g'),gn=document.createElementNS(ns,'g');svg.appendChild(gl);svg.appendChild(gn);
  const lineEls=links.map(()=>{const l=document.createElementNS(ns,'line');l.setAttribute('stroke',cssv('--border-strong'));l.setAttribute('stroke-width','1.2');gl.appendChild(l);return l;});
  const nodeEls=nodes.map(n=>{
    const g=document.createElementNS(ns,'g');g.setAttribute('class','node-c');
    let shape;
    if(n.type==='m'){shape=document.createElementNS(ns,'circle');shape.setAttribute('r',9);shape.setAttribute('fill',n.color);shape.setAttribute('stroke',cssv('--surface'));shape.setAttribute('stroke-width','2');}
    else{shape=document.createElementNS(ns,'rect');shape.setAttribute('width',13);shape.setAttribute('height',13);shape.setAttribute('rx',3);shape.setAttribute('fill',cssv('--surface-2'));shape.setAttribute('stroke',cssv('--border-strong'));shape.setAttribute('stroke-width','1.5');}
    g.appendChild(shape);
    if(n.type==='c'){const t=document.createElementNS(ns,'text');t.setAttribute('font-size','10');t.setAttribute('fill',cssv('--ink-3'));t.setAttribute('x',10);t.setAttribute('y',4);t.textContent=n.label.replace('委員会','').replace('に関する特別','特');g.appendChild(t);}
    else{const t=document.createElementNS(ns,'text');t.setAttribute('font-size','10.5');t.setAttribute('font-weight','600');t.setAttribute('fill',cssv('--ink-2'));t.setAttribute('x',12);t.setAttribute('y',4);t.textContent=n.label;g.appendChild(t);}
    g.addEventListener('mouseenter',e=>{if(n.type==='m'){showTip(e,`<b>${n.m.name}</b>（${n.m.party}）<br>${n.m.cls.archetypeLabel}・関心度${n.m.cls.engagement}`);}else{showTip(e,`<b>${n.label}</b>`);}});
    g.addEventListener('mousemove',moveTip);g.addEventListener('mouseleave',hideTip);
    if(n.type==='m')g.addEventListener('click',()=>openDrawer(n.m.id));
    enableDrag(g,n,svg,W,H);
    gn.appendChild(g);return g;});
  // force sim
  let alpha=1;function tick(){
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;const f=1400/d2;const d=Math.sqrt(d2);dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;}
    links.forEach(([s,t])=>{const a=nodes[s],b=nodes[t];let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1;const f=(d-90)*0.02;dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;});
    nodes.forEach(n=>{n.vx+=(W/2-n.x)*0.002;n.vy+=(H/2-n.y)*0.002;if(!n.fx){n.x+=n.vx*alpha;n.y+=n.vy*alpha;}n.vx*=0.85;n.vy*=0.85;n.x=Math.max(16,Math.min(W-16,n.x));n.y=Math.max(16,Math.min(H-16,n.y));});
    lineEls.forEach((l,i)=>{const a=nodes[links[i][0]],b=nodes[links[i][1]];l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);});
    nodeEls.forEach((g,i)=>{const n=nodes[i];g.setAttribute('transform',`translate(${n.x} ${n.y})`);});
    alpha*=0.985;if(alpha>0.02)requestAnimationFrame(tick);}
  requestAnimationFrame(tick);
  card.appendChild(svg);
  // legend
  const lg=DATA.archOrder.filter(id=>classified.some(m=>m.cls.archetype===id)).map(id=>({label:LBL[id],v:classified.filter(m=>m.cls.archetype===id).length,color:archColor(id)}));
  card.appendChild(legend(lg));
  p.appendChild(card);
}
function enableDrag(g,n,svg,W,H){
  let on=false;
  g.addEventListener('mousedown',e=>{on=true;n.fx=true;e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!on)return;const pt=svg.getBoundingClientRect();n.x=(e.clientX-pt.left)/pt.width*W;n.y=(e.clientY-pt.top)/pt.height*H;});
  window.addEventListener('mouseup',()=>{if(on){on=false;n.fx=false;}});
}

// ---------- Category ----------
function viewCategory(p){
  const card=el('div','card');
  card.appendChild(el('div','ctitle','会議体（委員会）別 類型構成'));
  card.appendChild(el('div','cnote','分類済メンバーのみ。各バーに「分類済 / 委員会全体」を併記（一部のみ分類の誤認防止）。'));
  const entries=Object.entries(DATA.commArch).map(([c,m])=>({c,m,tot:Object.values(m).reduce((a,b)=>a+b,0),full:DATA.committeeTotals[c]||0}))
    .filter(e=>e.tot>0).sort((a,b)=>b.tot-a.tot);
  entries.forEach(e=>{
    const row=el('div');row.style.margin='14px 0';
    row.appendChild(el('div',null,`<div style="font-size:13px;font-weight:600">${e.c} <span style="color:var(--ink-3);font-weight:500;font-size:12px">（分類済 ${e.tot} / 全 ${e.full}名）</span></div>`));
    const st=el('div','stack');st.style.marginTop='6px';
    DATA.archOrder.forEach(id=>{const v=e.m[LBL[id]];if(!v)return;const i=el('i');i.style.flex=v;i.style.background=archColor(id);i.title=LBL[id]+' '+v;st.appendChild(i);});
    row.appendChild(st);card.appendChild(row);
  });
  const lg=DATA.archOrder.filter(id=>DATA.overall[LBL[id]]).map(id=>({label:LBL[id],v:DATA.overall[LBL[id]],color:archColor(id)}));
  card.appendChild(legend(lg));
  p.appendChild(card);
}

// ---------- Members ----------
const mstate={q:'',chamber:'',party:'',tier:'',cls:''};
function viewMembers(p){
  const parties=Object.keys(DATA.partyCounts);
  const f=el('div','filters');
  f.innerHTML=`<input id="q" placeholder="氏名・選挙区で検索" value="${mstate.q}" style="min-width:180px">
   <select id="chamber"><option value="">議院: 全</option><option value="衆">衆</option><option value="参">参</option></select>
   <select id="tier"><option value="">Tier: 全</option><option value="A">A 重点</option><option value="B">B</option><option value="C">C</option></select>
   <select id="cls"><option value="">分類: 全</option><option value="yes">分類済のみ</option></select>
   <select id="party"><option value="">会派: 全</option>${parties.map(p=>`<option ${mstate.party===p?'selected':''}>${p}</option>`).join('')}</select>
   <span class="count" id="cnt"></span>`;
  p.appendChild(f);
  const tw=el('div','tablewrap');const tbl=el('table');
  tbl.innerHTML=`<thead><tr><th>氏名</th><th>会派</th><th>院</th><th>Tier</th><th>役職 / 委員会</th><th>類型</th></tr></thead><tbody></tbody>`;
  tw.appendChild(tbl);p.appendChild(tw);
  const tb=$('tbody',tbl);
  function apply(){
    const r=DATA.members.filter(m=>{
      if(mstate.chamber&&m.chamber!==mstate.chamber)return false;
      if(mstate.tier&&m.tier!==mstate.tier)return false;
      if(mstate.party&&m.party!==mstate.party)return false;
      if(mstate.cls==='yes'&&!m.cls)return false;
      if(mstate.q){const q=mstate.q;if(!((m.name||'').includes(q)||(m.district||'').includes(q)))return false;}
      return true;});
    tb.innerHTML='';
    r.slice(0,400).forEach(m=>{
      const tr=el('tr');const tcol=m.tier==='A'?'var(--tierA)':m.tier==='B'?'var(--tierB)':'var(--tierC)';
      const role=(m.roles||'').split(';')[0]||'';const comm=m.committees.slice(0,2).join('・');
      const arch=m.cls?`<span class="chip arch" style="background:${archColor(m.cls.archetype)}">${m.cls.archetypeLabel}</span>`:'<span style="color:var(--ink-3);font-size:12px">—</span>';
      tr.innerHTML=`<td style="font-weight:600">${m.name}</td><td>${m.party}</td><td>${m.chamber}</td>
        <td><span class="tierbadge" style="background:${tcol}">${m.tier||'-'}</span></td>
        <td style="color:var(--ink-2);font-size:12px">${role?('<b style=color:var(--ink)>'+role+'</b> '):''}${comm}</td><td>${arch}</td>`;
      tr.onclick=()=>openDrawer(m.id);tb.appendChild(tr);});
    $('#cnt').textContent=`${r.length}名`+(r.length>400?'（上位400表示）':'');
  }
  f.addEventListener('input',e=>{const id=e.target.id;if(id in mstate){mstate[id==='q'?'q':id]=e.target.value;apply();}});
  f.addEventListener('change',e=>{const id=e.target.id;if(id in mstate){mstate[id]=e.target.value;apply();}});
  apply();
}

// ---------- Drawer ----------
function openDrawer(id){
  const m=DATA.members.find(x=>x.id===id);if(!m)return;
  let bg=$('#dbg'),dr=$('#drw');
  if(!bg){bg=el('div','drawer-bg');bg.id='dbg';bg.onclick=closeDrawer;document.body.appendChild(bg);
    dr=el('div','drawer');dr.id='drw';document.body.appendChild(dr);}
  const col=m.tier==='A'?'var(--tierA)':m.tier==='B'?'var(--tierB)':'var(--tierC)';
  let html=`<div class="dwrap"><button class="dclose" aria-label="閉じる">×</button>
    <div class="eyebrow">${m.chamber}議院 ・ ${m.party}</div>
    <h2 style="font-size:22px;margin-top:2px">${m.name}</h2>
    <div class="dmeta">
      <span class="tierbadge" style="background:${col}">Tier ${m.tier}</span>
      <span class="chip">${m.district||'—'}</span>
      <span class="chip">当選${m.elected}回・${m.seniority}</span></div>`;
  if(m.roles)html+=`<div class="section-t">役職</div><div>${m.roles.split(';').map(r=>`<span class="chip">${r}</span>`).join(' ')}</div>`;
  if(m.committees.length)html+=`<div class="section-t">所属委員会</div><div>${m.committees.map(c=>`<span class="chip">${c}</span>`).join(' ')}</div>`;
  if(m.cls){
    html+=`<div class="section-t">類型・関心度</div><div><span class="chip arch" style="background:${archColor(m.cls.archetype)}">${m.cls.archetypeLabel}</span> <span class="chip">関心度 ${m.cls.engagement}・発言${m.cls.speechCount}件</span></div>`;
    if(m.cls.rationale)html+=`<div class="career" style="margin-top:8px">${m.cls.rationale}</div>`;
    const tp=Object.values(m.cls.topics||{});
    if(tp.length){html+=`<div class="section-t">トピック別スタンス（根拠発言つき）</div>`;
      tp.forEach(t=>{html+=`<div class="stance-row"><span class="stance-dot" style="background:${STANCE_C[t.stance]||'#999'}"></span><b>${t.topicLabel}</b>：${t.stanceLabel}</div>`;
        (t.quotes||[]).forEach(q=>{html+=`<div class="quote">「${q}」</div>`;});});}
    if(m.cls.flags&&m.cls.flags.length)html+=`<div class="section-t">フラグ</div>${m.cls.flags.map(x=>`<div class="career">⚑ ${x}</div>`).join('')}`;
  }else{
    html+=`<div class="section-t">分類</div><div class="career">未分類（発言未収集/未分類）。STEP3で収集→分類すると、ここに類型と根拠発言が表示されます。</div>`;
  }
  if(m.career)html+=`<div class="section-t">経歴（公式プロフィール）</div><div class="career">${m.career}</div>`;
  html+=`</div>`;
  dr.innerHTML=html;$('.dclose',dr).onclick=closeDrawer;
  requestAnimationFrame(()=>{bg.classList.add('on');dr.classList.add('on');});
  document.addEventListener('keydown',escClose);
}
function closeDrawer(){const bg=$('#dbg'),dr=$('#drw');if(bg)bg.classList.remove('on');if(dr)dr.classList.remove('on');document.removeEventListener('keydown',escClose);}
function escClose(e){if(e.key==='Escape')closeDrawer();}

// ---------- tooltip ----------
let tip;
function showTip(e,h){if(!tip){tip=el('div','tip');document.body.appendChild(tip);}tip.innerHTML=h;tip.classList.add('on');moveTip(e);}
function moveTip(e){if(!tip)return;tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px';}
function hideTip(){if(tip)tip.classList.remove('on');}

render();
"""


def main() -> int:
    common.ensure_dirs()
    data = build_data()
    inner = render_inner(data)
    full = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>JCLP 政策調査ダッシュボード</title></head>'
            '<body style="margin:0">' + inner + '</body></html>')
    out = common.OUTPUT / "policy_dashboard.html"
    out.write_text(full, encoding="utf-8")
    print(f"生成: {out}（{len(full)//1024}KB, 議員{data['meta']['total']}名/分類{data['meta']['classified']}名）")
    print("→ ブラウザでこのファイルを開いて閲覧してください（単体で動作・外部依存なし）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# 政策調査プロトタイプ 進捗ダッシュボード

> 目的: 国会議員（与党全員）の気候・エネルギー政策スタンスを収集→類型化→会議体別に可視化し、
> JCLPの政策エンゲージメント戦略の基礎情報にする（→ `../ヒアリング結果メモ.md` / `../政策調査_進め方設計メモ.md`）。
> **このファイルは新規セッションでの引き継ぎ用。作業したら必ず更新すること。**
> 最終更新: 2026-07-09（★会議録：**ローカル環境で直結が通ることを確認**し、全713名の発言を一括取得・73,328件）

---

## 0. 全体像（STEP1→5）と現在地

| STEP | 内容 | 状態 | 成果物 |
|------|------|------|--------|
| STEP1 | 議員マスター名簿 | 🟢 **公開データで取れる列は完了**（部会/参経歴は公開なし＝要外部データ） | `data/roster.csv`（713名・実データ） |
| STEP2 | 評価軸の設定ファイル化 | 🟢 v0.2メモ準拠（**要JCLPレビュー**）＋影響力Tier算出済 | `config/axes.yml` / `docs/axes_design.md` |
| STEP3 | 収集＋類型化 | 🟢 **会議録は713名全件取得済**（73,328件）／X投稿はパイロット20名のみ／分類はパイロット10名のみ | `fetch_speeches.py`（--via direct）/ `fetch_x.py` / `classify.py` |
| STEP4 | 会議体別 集計・可視化 | 🟢 **実データで実証**（分類済/全体を明示） | `scripts/aggregate.py` / `visualize.py` |
| STEP5 | 定期収集の運用化 | ⚪ 未着手 | （cron / `/loop`） |

凡例: 🟢完了 / 🟡確定待ち / 🟠外部依存で停止中 / ⚪未着手

---

## 1. 環境で確認済みの制約（★重要・毎回参照）

| 対象 | 結果 | 意味 |
|------|------|------|
| 衆議院サイト | ✅ HTTP 200 | 名簿取得OK（この環境で可） |
| 参議院サイト | ✅ HTTP 200 | 名簿取得OK |
| 自民党サイト | ✅ HTTP 200 | 党情報の取得余地あり |
| **国会会議録API（直結）** | ❌ Codespaces等クラウドは403 ／ ✅ **ローカル(自宅/事務所)回線は200** | NDLのCloudFront WAFが**クラウドIPのみ**をホスト全体で遮断（curl/WebFetch共に403）。API自体は無認証で正常。2026-07-09にローカルMacから`curl`で200を実測し、`--via direct`で713名を一括取得（Jina不要） |
| **国会会議録API（Jina経由）** | ✅ 疎通（クラウド環境向けの代替経路） | `r.jina.ai` を串に取得可（実測）。`fetch_speeches.py --via jina` で収集。JINA_API_KEYでレート緩和。**ローカル実行時は直結の方が速く不要** |
| **X（SNS）** | 🟢 台帳化・一部取得済 | JINA_API_KEY（config/jina.key）で451解除を実証。`data/x_handles.csv` を全713名に拡張し、614名分のハンドルを登録（公式確認9＋Wikidata P2002候補531＋Web/Xプロフィール補完74）。`data/x_posts/` は20名・計253投稿を保存済み。未解決99名は `data/x_handle_unresolved.csv` で確認管理 |
| Anthropic API | ⛔ **使わない方針** | 分類は**Claude Code自身**が実施（classify.py=ワークシート生成、validate_classifications.py=quote実在ゲート） |
| CJKフォント(IPAGothic) | ✅ 有 | 円グラフの日本語描画OK |

→ **会議録API取得の実運用**（STEP3）: **APIは無認証で正常。IPが弾かれているだけ**なので、
  (a) 非遮断ネットワーク（ローカルPC・事務所回線）で `--via direct`（全速・**2026-07-09に実運用で確認**）、または
  (b) クラウド環境（Codespaces等）なら `--via jina`（Jina Reader経由。JINA_API_KEYでレート緩和）。
  ※ ★speaker検索は**姓の部分一致**で同姓別人が混入する（例: 猪口邦子↔幸子）→ 発言者名で厳密フィルタ済（115,302件を除外・実測）。
  ※ ★`fetch_one()` の `max_pages=10`（＝1名あたり最大300件）がハードコードされておりCLIオプション化されていない。
  713名中**59名がちょうど300件で頭打ち**＝実際の発言数はもっと多い可能性（取りこぼし）。現状は許容し先に進める方針（2026-07-09合意）。
  精査したい場合は `--max-pages` オプションを追加してこの59名だけ再取得する。

---

## 2. STEP1 名簿の現状（713名）

`data/roster.csv` … 衆465 + 参248 = **713名**、`verified=yes`、`source_url`付き、`as_of=2026-07-03`。

**列の充足状況:**

| 列 | 状態 | 出典 |
|----|------|------|
| name / kana / alias | ✅ 充足 | 衆参 公式議員一覧（alias=通称[本名]の本名） |
| chamber(衆/参) | ✅ 充足 | 同上 |
| party(会派) | ✅ 充足（公式表記のまま） | 同上 |
| district(選挙区) | ✅ 充足 | 同上 |
| elected_count | 🟢 711/713 | 衆=議員一覧 / 参=profileの「当選N回」（参2名のみ未） |
| profile_url | 🟢 713 | 衆参ともプロフィールページ |
| **committees(委員会)** | 🟢 **両院671充足**（衆425/参246） | 衆参の委員名簿から自動付与済。残42は大臣・議長等で委員会に属さない |
| **career(キャリア)** | 🟢 衆465（＝取得可能な全数） | 衆profileの経歴文を全付与。**★参は公式プロフィールに経歴文が無い**（当選歴・委員会のみ）→公式からは取得不可 |
| **roles(役職)** | 🟢 **133充足**（政府三役72＋委員長/会長59） | 官邸の閣僚等名簿＋委員会名簿から付与。**内閣改造時は要更新** |
| **party_divisions(部会)** | 🔴 公開データでは取得不可 | **部会の構成員名簿は非公開**。自民の個別議員ページに部会長等の「役職」は載るが所属は不明。会議体分析はcommittees（公開・充足）で代替 |
| member_company_offices | ⚪ 空 | 後付け → 会員企業拠点×選挙区 突合（JCLPデータ待ち） |

**与党サブセット**: `config/ruling_parties.yml` で会派ごとに `ruling: yes/no` を人間が確定 → 対象集合が決まる（現状すべて `null`）。

---

## 3. 名簿を「完成」させる手順（enrichロードマップ）

BASEは完成済み。以降は列を足していく。**出典は実測で到達確認済み**。

1. **committees（現職委員会）★STEP4の会議体キー** … 🟢 **両院完了**（`enrich_committees.py`）。
   - 衆: 委員名簿 `itdb_iinkai.nsf/html/iinkai/list.htm`（27委員会）
   - 参: 索引 `kon_kokkaijyoho/iinkai/tiinkai.html` → 各 `konkokkai/current/list/l00NN.htm`
   - 氏名（衆は読みも）＋別名(alias)で roster と突合。671名付与・未突合1（`木村 義雄`＝出典側の掲載残り）。
2. **career（キャリア）** … 🟢 **衆は完了**（`enrich_careers.py`、465/465）。
   衆 `profile_url` の `<div id="contents">` から経歴文を抽出（学歴・職歴・役職歴・当選回数）。
   - **★参は公式に経歴文なし**（`enrich_sangiin.py` で確認）。参profileは当選年・当選回数・委員会のみ。
     → 参の profile_url と elected_count は補完済（`enrich_sangiin.py`）。**参の略歴プロースが要る場合は
     非公式ソース（Wikipedia・議員個人サイト等）を人間判断で追加**（真正性は落ちる＝要フラグ）。
3. **roles（大臣・副大臣・政務官）** … 🟢 **完了**（`enrich_roles.py`）。
   官邸 閣僚等名簿 `kantei.go.jp/jp/<内閣>/meibo/{index,fukudaijin,seimukan}.html`（現在=105/第2次高市内閣）。
   （院,氏名）優先＋（院,読み）補助で突合（同姓同名/同読みの衆参別人を分離）。**内閣改造で `--cabinet` 更新**。
4. **party_divisions（部会）** … 🔴 **公開データでは自動取得不可**（2026-07-03 調査）。
   - 党内部会の**構成員名簿は非公開**。自民の個別議員ページ（`jimin.jp/member/<id>.html` の JSON-LD）には
     党役職・部会長等の「役職」は載るが、平の「所属部会」は載らない。かつ議員一覧がJS描画で名前→ID対応に
     別処理（Playwright等）が要り、自民のみ（417/713）。
   - **代替**: 会議体分析（STEP4）は公開・充足の **committees（常任/特別委員会）** で実施可能。
   - 部会軸が必須なら **JCLP提供データ**か**非公式集計**＋人間判断（真正性フラグ）。
5. **member_company_offices**: JCLP会員企業の拠点リスト（JCLP提供）× `district` を突合。
6. **与党確定**: `config/ruling_parties.yml` に yes/no を記入（一次情報で連立構成を確認）。

> enrichは「列を足す」だけなので、いつでも再取得・上書き可。`as_of` を更新して時点管理する。

---

## 4. 出典URL（一次情報・到達確認済み）

- 衆議院 議員一覧（五十音10ページ）: `https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/1giin.htm` 〜 `10giin.htm`
- 衆議院 プロフィール: `https://www.shugiin.go.jp/internet/itdb_giinprof.nsf/html/profile/<NNN>.html`
- 参議院 議員一覧: `https://www.sangiin.go.jp/japanese/joho1/kousei/giin/218/giin.htm`（回次は要確認）
- 自民党: `https://www.jimin.jp/member/`
- 国会会議録検索API（**現状403**）: `https://kokkai.ndl.go.jp/api.html`

---

## 5. コマンド早見表

```bash
cd jclp/TASK-E/policy-research
pip3 install -r requirements.txt

# STEP1: 名簿を公式サイトから再生成（BASE）
python3 scripts/build_roster.py --as-of 2026-07-03        # data/roster.csv を更新
python3 scripts/build_roster.py --dry-run                 # 件数確認のみ

# STEP1 enrich: 委員会を付与（衆参・実行済。build_roster後に毎回かける）
python3 scripts/enrich_committees.py                      # 両院 roster.csv に committees/委員長roles
python3 scripts/enrich_committees.py --chamber 参         # 片院のみ
python3 scripts/enrich_committees.py --dry-run            # 突合結果のみ

# STEP1 enrich: 経歴を付与（衆・実行済。profile_urlを巡回・約5分）
python3 scripts/enrich_careers.py                        # 衆465名の career を付与
python3 scripts/enrich_careers.py --limit 5              # 動作確認（先頭5名）

# STEP1 enrich: 政府役職を付与（衆参・実行済）
python3 scripts/enrich_roles.py                          # 現内閣105の三役を roles に付与
python3 scripts/enrich_roles.py --cabinet 106            # 内閣改造後は番号を更新

# STEP1 enrich: 参の profile_url・当選回数を補完（実行済。参に経歴文は無い）
python3 scripts/enrich_sangiin.py                        # 参248名の当選回数・profile_url

# STEP2: 影響力Tierを名簿から算出（実行済・403非依存）
python3 scripts/compute_influence.py                     # roster に influence_tier/seniority を付与

# STEP3: 発言収集（氏名で引き同姓別人は自動除外）
python3 scripts/fetch_speeches.py --via direct --since 2022-01-01           # ローカル実行はこれ（2026-07-09: 713名完了・73,328件）
python3 scripts/fetch_speeches.py --member S-0160 --via direct --any エネルギー --since 2022-01-01
JINA_API_KEY=xxx python3 scripts/fetch_speeches.py --via jina --any エネルギー   # クラウド環境（Codespaces等）はJina経由
# パイロット分類（APIキー無のためメインClaudeが分類した4名の実例）
python3 scripts/_pilot_classify.py

# STEP3: 類型化（★Anthropic API不使用。Claude Code自身が分類する）
python3 scripts/classify.py                      # 議事録＋X投稿のワークシートを output/worksheets/ に生成
python3 scripts/classify.py --sources diet       # 議事録のみ
python3 scripts/classify.py --sources diet,x     # 議事録＋X投稿
#   → Claude Code がワークシートを読み data/classifications/<mid>.json を作成
python3 scripts/validate_classifications.py      # quote実在・軸整合を機械検証（安全ゲート）

# STEP3: Xハンドル台帳・投稿取得
python3 scripts/sync_x_handles.py                         # roster.csv を基準に x_handles.csv を全713名へ同期
python3 scripts/discover_x_handles_wikidata_sparql.py      # Wikidata P2002で候補補完（要公式確認）
python3 scripts/resolve_x_handles_web.py --limit 40        # DDG検索＋Xプロフィールで未登録分を安全側に補完
python3 scripts/fetch_x.py --skip-existing --limit 50       # 未取得分を50名だけ取得

# STEP4: 集計＋可視化
python3 scripts/aggregate.py
python3 scripts/visualize.py

# 分析ダッシュボード（1つの自己完結HTML）を生成
python3 scripts/build_dashboard.py                       # → output/policy_dashboard.html

# STEP4 の配線実証（合成データ・NW/API不要）
python3 scripts/_make_sample_classifications.py
python3 scripts/aggregate.py --roster data/roster.sample.csv
python3 scripts/visualize.py
```

---

## 6. 意思決定ログ / 未解決事項（申し送り）

- **[進捗 2026-07-09]** ★**会議録を713名全件取得完了**。従来はGithub Codespaces（クラウドIP）での実行を前提に
  `--via jina` を使っていたが、**ローカルPC（自宅回線）から実行する場合はNDLのWAFに遮断されず直結できる**ことを
  `curl` で実測（HTTP 200）。仮想環境(`venv`)を新規作成し `--via direct --since 2022-01-01` で713名を一括取得
  （所要時間: 約65分、16:05〜17:10）。結果: **合計73,328発言**・取得失敗(WARN)は0件・発言0件の議員85名。
  同姓別人の除外（`exact_speaker`厳密フィルタ）は115,302件が対象になった（姓の部分一致検索の仕様上、正常）。
  **★既知の制約**: `fetch_one()` の `max_pages=10`（1名最大300件）がCLIオプション化されておらずハードコード。
  713名中**59名がちょうど300件で頭打ち**＝実際の発言数はもっと多い可能性（例: H-0083, S-0238, S-0244等）。
  今回は「現状の73,328件で十分、まず先に進める」と合意（2026-07-09）。精査する場合は `--max-pages` を
  追加実装し、この59名だけ再取得すればよい（`data/speeches/*.json` の `count==300` で該当ファイルを抽出可能）。
  → 次はSTEP3後半（713名全件の分類）またはSTEP4（全件集計・可視化）に進める。X投稿はまだパイロット20名のみ。
- **[決定]** 名簿は会派を公式表記のまま記録し、与党判定は `ruling_parties.yml` で分離（政局変化に強くするため）。
- **[決定]** STEP4はまず**合成データ**で配線実証済（`output/charts/*.png`）。合成名簿は `data/roster.sample.csv` に退避。
- **[進捗 2026-07-03]** 衆参**両院**の委員会を実データで付与（671/713名、委員長・会長58名）。
  氏名＋読み＋別名(alias)で突合、未突合1（`木村 義雄`＝出典の掲載残り）。参の名簿は「通称[本名]」形式のため
  `build_roster.py` で通称=name／本名=alias に分離。
- **[決定]** 名簿の再構成順: `build_roster.py`（BASE）→ `enrich_committees.py`（委員会）→
  `enrich_careers.py`（衆経歴）→ `enrich_roles.py`（政府役職）→ `enrich_sangiin.py`（参 当選回数/profile_url）。
  各enrichは冪等（roles列は委員会→官邸の順で追記）。
- **[発見 2026-07-03]** ★**党内部会の構成員名簿は公開されていない**。自民の議員個別ページに部会長等の
  役職は載るが所属は不明、一覧もJS描画。→ party_divisions は公開データで自動取得不可。会議体分析は
  committees（公開・671充足）で代替する。部会軸が要るなら JCLP提供データ／非公式集計＋人間判断。
- **[発見 2026-07-03]** ★**参議院の公式プロフィールには経歴文（学歴・職歴）が無い**（当選歴・委員会のみ）。
  衆(465)のような career は参からは公式取得不可。参は profile_url・当選回数(elected_count)のみ補完。
  参の略歴が必要なら非公式ソース＋人間判断（真正性フラグ）。career列は 衆465＝公式で取得可能な全数。
- **[進捗 2026-07-03]** 政府三役72名＋委員長/会長59名を roles に付与（計133/713）。
  読み仮名は衆参・党内で衝突する（青山繁晴・鬼木誠・西田しょうじ・伊藤たかえ）ため、官邸ページの
  「院」＋氏名で厳密突合。**内閣改造・委員会改選時は再enrich必要（`--cabinet`更新）**。
- **[進捗 2026-07-03]** 衆の経歴を全465名付与（`enrich_careers.py`）。抽出時、経歴本文中の
  「（○区選出）」を選挙区ヘッダ除去フィルタが巻き込むバグを修正（ヘッダは行頭が小選挙区/比例代表等の行のみ除去）。
- **[成果 2026-07-03]** ★**分析ダッシュボード（1つの自己完結HTML）**を作成（`scripts/build_dashboard.py` →
  `output/policy_dashboard.html`）。概要／ネットワーク（議員×委員会・力学配置）／カテゴリ（会議体別類型構成）／
  議員詳細（713名を検索・フィルタ→ドロワーで役職・委員会・経歴・スタンス根拠発言）。テーマ対応・外部依存なし・
  CVD検証済配色。**ブラウザで直接開いて閲覧**（Artifact等の公開はしない方針）。
  （enrich系の復号は shift_jis→**cp932** に修正＝ローマ数字「Ⅰ種」等の文字化け解消）。
- **[進捗 2026-07-03]** ★STEP1→STEP4を**実データで一気通貫**。パイロット10名（経産委/環境委・多党）を
  実発言から分類（Claude Code・quote検証済）→ 会議体別の類型構成を可視化。環境委=再エネ積極支持3/発言少2/
  太陽光批判1、経産委=再エネ2/原子力1/経済安保1。**円グラフに「分類済N/全M名・パイロット」を明示**（誤認防止）。
  軸の境界事例も検出（落合＝脱炭素支持かつ経済安保重視は既存類型に収まりにくい→軸拡張候補）。
- **[進捗 2026-07-03]** ★SNS(X)収集の**疎通・歩留り確認済**。JINA_API_KEY（`config/jina.key`・gitignore）で
  x.comの451解除を実証。`fetch_x.py --probe <handle>` で**1プロフィール取得＝約13投稿**（本人＋RT）を
  日付・本文・パーマリンク・本人/RT判定つきで構造化取得できた。**制約**: 取得はプロフィール初期表示分
  （直近十数件）。深い履歴はX仕様上不可 → 定期収集(cron)で蓄積 or X公式API。**残**: `data/x_handles.csv` の
  ハンドル記入（公式対応表が無いためJCLP確認／私が検索して提示も可）。X偏り(メモL75)→会議録と併用・source=X で区別。
  鍵は `common.get_jina_key()`（env → config/jina.key）で読み、チャット/gitに出さない運用。
- **[進捗 2026-07-06]** ★SNS(X)アカウント登録＋投稿取得を実施。`data/x_handles.csv` のパイロット10名について
  9名のXハンドルを登録（公式サイト・政党ページ・Xプロフィール等で確認）。緒方林太郎氏は公式サイトに
  Facebook/Instagram掲載はあるが本人公式Xを確認できず、空欄＋noteに理由を記録。`fetch_x.py` をJinaキーで実行し、
  `data/x_posts/` に9名分を保存（東13、石原14、伊藤14、落合14、金子14、工藤15、宮路13、猪口13、長浜12投稿）。
  `classify.py` に `data/x_posts/` を併合する入力レイヤーを追加し、evidence.source=`x` として扱えるようにした。
  `validate_classifications.py` も議事録・X投稿の両方でquote実在検証するよう更新済み。
- **[進捗 2026-07-06]** ★全議員SNS台帳を作成。`sync_x_handles.py` で `roster.csv` 713名を
  `data/x_handles.csv` に同期し、既存9件を保持。`discover_x_handles_wikidata_sparql.py` でWikidata P2002を一括照合し、
  単一候補のみ自動登録した結果、**540/713名**のx_handleが充足（公式確認9、Wikidata候補531）。
  Wikidataは一次情報ではないため、noteに「要公式確認」を記録。未登録173名は `data/x_handle_candidates.csv`
  に確認リスト化（複数候補34、候補なし139）。複数候補は誤登録防止のため自動採用しない。
- **[進捗 2026-07-06]** ★Xハンドル未登録分を追加調査。`resolve_x_handles_web.py` を作成し、DuckDuckGo検索結果と
  Jina経由のXプロフィール本文（投稿本文はスコア対象外）で、氏名＋議員表記等が確認できるものだけ安全側に自動補完。
  追加で**74名**を登録し、`data/x_handles.csv` は**614/713名**まで充足。残り**99名**は `note` に
  `未解決:` 理由を残し、`data/x_handle_unresolved.csv` に再整理。誤登録防止のため、プロフィール本文で本人性を
  確認できない候補、同点候補、政党広報等の汎用アカウントは採用しない。
- **[進捗 2026-07-06]** ★X投稿の追加取得を実施。`fetch_x.py` に `--skip-existing` / `--limit` を追加し、
  バッチ取得可能にした。追加で11名を取得し、現状 `data/x_posts/` は**20名・計253投稿**。分類済みJSONの
  既存10件は `validate_classifications.py` で検証OK。
- **[決定 2026-07-03]** ★**Anthropic APIは使わない**。STEP3の分類は**Claude Code自身**が行う前提。
  classify.py はワークシート（発言＋軸＋スキーマ）を生成し、Claude Codeが分類JSONを書き、
  validate_classifications.py が quote実在・軸整合を機械検証（捏造遮断）。→ 名簿系と同じく「Claude Code完結」。
- **[発見/進捗 2026-07-03]** ★STEP3 実データ疎通。会議録APIは直結403だが **Jina Reader経由で取得可**
  （`--via jina`）。APIは無認証で正常＝IP遮断のみ。パイロット4名（長浜/宮路/猪口/工藤）を実発言で分類し、
  **根拠quoteの実在を検証**して `data/classifications/` に格納。speaker検索の姓・部分一致（同姓別人混入）は
  発言者名で厳密フィルタして解消。宮路（委員長）は議事運営のみ＝low_engagementと正しく判定。
- **[進捗 2026-07-03]** STEP2評価軸を**メモ準拠v0.2**で作成（`config/axes.yml` / `docs/axes_design.md`）。
  4軸（トピック別スタンス／関心度／類型／影響力Tier）。影響力Tierは名簿から算出済（A130/B577/C6）。
- **[要人間]** `axes.yml` を武井氏がレビューし確定（トピック過不足・類型定義・閾値`senior_grants_tier_a`）。
  → STEP3が通ったら5〜10名パイロットで精度検証（`docs/axes_design.md` §7）。
- **[要人間]** `config/ruling_parties.yml` の与党会派 yes/no を一次情報で確定。
- **[要人間]** `data/x_handles.csv` のWikidata由来531件・Web/Xプロフィール補完74件を、公式サイト・政党ページ・Xプロフィール等で順次確認。
  未解決99名は `data/x_handle_unresolved.csv` をもとに、個別の公式確認・手動調査を行う。
- **[要運用設計]** 非公開面談メモ（メモ L16）はローカル処理限定。本パイプラインは公開情報のみ。
- **[外部依存]** 会議録API 403 の回避（非遮断NW/プロキシ）が STEP3 ライブ実行の前提。
- **[優先度]** 政策調査は第2フェーズ。第1優先はPowerPoint支援（メモ L106, L116）。

---

## 7. ディレクトリ構成

```
policy-research/
├─ dashboard.md              ← 本ファイル（進捗の単一ソース）
├─ README.md                 ← 使い方
├─ requirements.txt
├─ run_pipeline.sh
├─ config/
│  ├─ axes.yml               ← STEP2 評価軸（v0.2メモ準拠・要JCLPレビュー）
│  └─ ruling_parties.yml     ← 与党会派の指定（要確定）
├─ data/
│  ├─ roster.csv             ← STEP1 実名簿（713名）
│  ├─ roster.sample.csv      ← 合成デモ用（STEP4配線実証）
│  ├─ x_handles.csv          ← Xハンドル対応表（713名中614名登録済）
│  ├─ x_handle_candidates.csv← Wikidata補完時の確認リスト（複数候補/候補なし）
│  ├─ x_handle_unresolved.csv← Xハンドル未解決99名の確認リスト
│  ├─ x_posts/               ← X投稿取得結果（Jina経由・20名/253投稿）
│  ├─ speeches/              ← STEP3 収集発言（会議録API）
│  └─ classifications/       ← STEP3 類型化結果
├─ scripts/
│  ├─ common.py              ← 名簿/軸ローダ
│  ├─ build_roster.py        ← STEP1 名簿ビルダー（衆参公式サイト）
│  ├─ enrich_committees.py   ← STEP1 委員会付与（衆参・委員名簿）
│  ├─ enrich_careers.py      ← STEP1 経歴付与（衆・profileページ）
│  ├─ enrich_roles.py        ← STEP1 政府役職付与（官邸・閣僚等名簿）
│  ├─ enrich_sangiin.py      ← STEP1 参の当選回数・profile_url補完
│  ├─ compute_influence.py   ← STEP2 影響力Tier算出（名簿由来）
│  ├─ fetch_speeches.py      ← STEP3 発言収集
│  ├─ fetch_x.py             ← STEP3 SNS(X)投稿収集
│  ├─ sync_x_handles.py      ← Xハンドル台帳をroster.csvへ同期
│  ├─ discover_x_handles_wikidata_sparql.py ← Wikidata P2002でXハンドル候補補完
│  ├─ discover_x_handles_wikidata.py ← Wikidata個別API版の補助スクリプト（429が出やすいためSPARQL版優先）
│  ├─ resolve_x_handles_web.py ← DDG検索＋Xプロフィール本文で未登録分を補完
│  ├─ classify.py            ← STEP3 分類ワークシート生成（API不使用）
│  ├─ validate_classifications.py ← STEP3 分類の安全ゲート（quote実在検証）
│  ├─ aggregate.py           ← STEP4 集計
│  ├─ visualize.py           ← STEP4 円グラフ
│  ├─ compute_influence.py   ← STEP2 影響力Tier算出
│  ├─ build_dashboard.py     ← 分析ダッシュボード(1HTML)生成
│  └─ _make_sample_classifications.py  ← デモ専用
└─ output/
   ├─ aggregate.json
   └─ charts/*.png
```

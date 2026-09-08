# CLAUDE.md

このファイルは、このリポジトリで作業する人間・AIエージェント双方に向けた、アーキテクチャの全体像と設計判断の「なぜ」を記録したドキュメントです。テンプレートとして新しいプロジェクトの土台に使う際、まずここを読めば構造の意図が分かるようにしています。

## レイヤー構成

```
routes (app/api/routes) → services (app/services) → repositories (app/repositories) → models (app/models)
                                        ↓
                                  ai (app/ai)  ※ LangChain/LangGraphによるLLM連携
```

- **routes**：リクエスト/レスポンスの変換のみを担当し、ビジネスロジックを持たない。ルートは基本的に「サービスを呼ぶ→スキーマに詰めて返す」だけで、例外処理も原則書かない（後述）。
- **services**：ユースケース単位のロジックとトランザクション境界を持つ。DBの`commit()`はサービス層でのみ行う。
- **repositories**：永続化のみを担当し、`flush()`はしても`commit()`はしない（トランザクションの単位はサービス層が握るため）。
- **models**：SQLAlchemyのORM定義のみ。
- **ai**：LLM/検索ツールのクライアントとLangGraphのワークフローをまとめた独立パッケージ。servicesから呼び出される。

### ファイル分割の粒度（相談ログ Q21 / `../textbook/Phase-3/Phase-3-3.md` §2.3）

層をまたいだ 1:1:1:1 のファイル名対応は**目指さない**（テンプレートも取っていない ── `conversation.py` モデルに `Message` が同居、`chat.py` スキーマが会話とメッセージとチャットターンを兼ね、`auth.py` ルートに対応するモデルは無い）。軸は 2 つ:

| 層 | 分割の軸 | 例 |
| --- | --- | --- |
| `models` / `schemas` / `repositories` | **永続化の関心事**（どのテーブル群か） | `optimization.py` に `Problem` / `Solution` / `BenchmarkRun`（全部 JSONB payload の「最適化レコード」）。repo は model と 1:1（同じファイル） |
| `api/routes` / `services` | **操作**（エンドポイント群 / ユースケース） | `solve.py` / `verify.py` / `solutions.py` / `algorithms.py` / `benchmark.py`（読み出しは所有者スコープで `optimization_read.py` に集約） |

- 格納先は**ファイル名でなく import で辿る**（`app/models/__init__.py` が全 re-export ── `from app.models import BenchmarkRun` はどのファイルに定義しても通る）。
- 「短いから別ファイル」はしない。分けるのは**変更理由と消費者が別**のとき（`../textbook/Phase-0/Phase-0-2.md` §2.5）。18 行のモデル・8 行のリポジトリで極小ファイルを量産すると `__init__.py` / `alembic/env.py` の登録リストが伸びるだけ。
- `app/domain/` `app/algorithms/` は別ルール ── 「1 概念 1 ファイル」（`dijkstra.py` / `bfs.py` / `route_planner.py`）。models / repos とは 1:1 対応しない。
- 新しい problem_type（Phase 4〜）でテーブルは増えない（hybrid JSONB スキーマ ── `Phase-0-8.md`）。増えるのは操作（route / service）と、本物の新集約が出たときの 1 式（`user.py` / `conversation.py` と同型）。テンプレート還元候補。

## DeciTima 固有レイヤー

このリポジトリは DeciTima プロジェクトのバックエンドとして使われる（元テンプレートは `fastapi-langchain-template`）。DeciTima の全体像・開発ポリシー・進行ルール・設計上の決定事項は、ワークスペースルートの `../CLAUDE.md` と `../textbook/Phase-0/` を参照。

上記のレイヤーに加えて、DeciTima では次の 2 層を新設している（設計は `../textbook/Phase-0/Phase-0-3.md`）。

```
routes → services ─┬→ domain (app/domain)     ※ 純粋。問題・制約・目的・解の型と意味
                   ├→ algorithms (app/algorithms) ※ 純粋関数。決定論的な計算
                   └→ repositories → models
```

- **domain**（`app/domain/{problems,constraints,objectives,solutions}`）：`OptimizationProblem` などの共通スキーマ、制約チェッカー、目的関数の評価。副作用（I/O・DB・時刻・乱数）を持たない。依存してよいのは標準ライブラリと Pydantic のみ。
- **algorithms**（`app/algorithms/{search,graph,optimization,scheduling,patterns}`）：BFS / Dijkstra / バックトラッキング等。`AlgorithmStrategy` プロトコル（`solve(problem) -> CandidateSolution` + メタデータ）を満たす純粋関数。手実装トラックと産業ソルバートラック（networkx / ortools）が同一インターフェースで並ぶ。`registry` が problem_type → 候補アルゴリズムを持つ（設計は `Phase-0-4.md`）。
  - **グラフの下地は `graph/{adjacency,union_find,segments,connectivity,waypoints}.py`（Phase 4〜）**：`build_adjacency` / `UnionFind` / route 3 strategy の共通足回り（`Segment` / `plan_route` / `reconstruct_path` ── 経路復元は Dijkstra / Bellman-Ford / A* で同一なので公開関数）/ 連結性クエリ / 経由順最適化。これらは registry に載らない「アルゴリズム・プリミティブ」（`Phase-0-4.md` §2.4）。`dijkstra.py` / `reachability.py` / `brute_force.py` はここから import する。
  - **route_planning のストラテジー**：`graph/{dijkstra,bellman_ford,a_star}.py`（手実装）+ `graph/networkx_shortest.py`（`library:networkx`。`_ops` を出さない）。`services/algorithm_selection.py::select_strategy` が問題特性で rule-based に選ぶ（負辺→bellman_ford / 全座標→a_star / 既定→dijkstra）。
  - **network_design（MST。Phase 4〜）**：`graph/{mst,kruskal,prim,networkx_mst}.py`。`registry["network_design"]`。新しい problem_type だが hybrid JSONB スキーマなのでテーブルは増えない（`alembic upgrade head` は no-op）。`NetworkLink.endpoints` は無向 tuple。全域木の「連結∧非閉路」判定は `algorithms/graph/connectivity.py::forms_spanning_tree` を `SolutionVerificationService` が呼ぶ（`domain` は計算を持たない ── `Phase-2-2.md` §3）。
  - **shift_scheduling（Constraint Optimization。Phase 6〜）**：`scheduling/{common,greedy,backtracking,branch_and_bound,ortools_cpsat}.py`。`registry["shift_scheduling"]` に手実装 3 本（`family="scheduling"` / `implementation="handwritten"`）+ `OrToolsCpSatShiftStrategy`（`library:ortools`。`_ops` を出さない）。`common.py` が共通足回り（`parse_shift_problem` / `eligible_staff` / `respects_hard` / `score` ── `domain/objectives/weighted_sum` を呼ぶ / `shift_solution`）。B&B の anytime は壁時計でなく決定論的なノード予算 `_MAX_NODES`（`solve` の純粋性を守る）。CP-SAT は `num_search_workers=1` + `random_seed` 固定で決定論。schema / V&V / 判別ユニオンは Phase 1〜2 で完成済みなので Phase 6 は「アルゴリズムを書くだけ」。プリミティブ `patterns/{sliding_window,difference_array}.py`（連続勤務日数の逐次判定 / 時間帯別の在籍人数 imos 法）。`domain/objectives/weighted_sum.py`（多目的の重み付き和。`Σ wᵢ·orient(metricᵢ)` を minimize 向きに）。`verify_shift_structure`（`domain/solutions/structure.py`）の metrics は Phase 6-1 で `hour_variance` を追加。
- **Validation と Verification は別サービス**：`services/validation.py`（問題定義の妥当性）と `services/verification.py`（解の制約充足）を分離する（設計は `Phase-0-6.md`）。
- **Benchmark（Phase 3〜）**：`services/benchmark.py` の `BenchmarkService` が 1 問題を registry の全アルゴリズムで解いて実測を横並びにする（`POST /api/v1/benchmark`）。実行時間・メモリは `services/measurement.py::measure_call` が `solve()` の**外**で測り（`solve()` の中で数えるのは操作回数 `metrics["_ops"]` だけ）、結果は `benchmark_runs` テーブル（JSONB payload 中心、`Problem` への FK なし）に保存。`BruteForceRouteStrategy`（`algorithms/optimization/brute_force.py`）は正解オラクル兼ベンチ対象として registry の route_planning に登録済み。
- **依存ライブラリの遅延追加**：`numpy`（Phase 3、`measure_call` の中央値・四分位集計のみ。アルゴリズム計算には使わない）/ **`networkx`（Phase 4-5 で追加済み。`networkx>=3.3`）** / **`ortools`（Phase 6-7 で `[project].dependencies` に追加済み。`OrToolsCpSatShiftStrategy` は solve / benchmark のリクエスト経路で動く runtime 依存。Phase 8/9 で再利用）**。`hypothesis` は当初 Phase 3 候補だったが見送り（手書きジェネレータで足りた）。
- **`scripts/`（Phase 3-5〜）**：開発用の一発スクリプト置き場（`analysis/` / `tests/` と同じ「`app/` の上」。`app/` から import されない。`scripts/__init__.py` + `uv run python -m scripts.<name>`）。現状 `scripts/seed.py` のみ ── `/login` を試すための固定テストユーザー（`example-user@example.com` / `sample-user-0123`）を `UserService.create_user` で 1 人作る（冪等・dev 専用・本番 DB では実行しない）。ドメイン非依存 = テンプレート還元候補。
- **分析トラック `analysis/`（Phase 3-8〜）**：`benchmark_runs` / `solutions` に貯まった実測を pandas で集計・可視化する**オフラインのトラック**。`app/` からは import されない（`tests/` と同じく app の「上」。逆＝`app → analysis` は禁止）。依存は `[dependency-groups].analysis`（`pandas` / `matplotlib`）で **runtime（`[project].dependencies`）には入れない**。`jupyter` はロックせず `uv run --with jupyter`。DB との結合は「エクスポート（`analysis/export.py`、async、独立エンジン）→ JSONL → `analysis/loaders.py`（純粋、file→DataFrame）」の一方向のみ。`analysis/benchmark_report.py` は DataFrame→DataFrame の純粋関数（`by_algorithm` / `input_size_curve` / `regression`）。**Phase 4-6 で `analysis/route_benchmark.py` を追加**（`load_route_benchmark_runs` が size / density 列を足し、`handwritten_vs_library` / `crossover_size` が「手実装 vs library の交差点」を出す ── MVP 規模では手実装が勝つ）。`analysis/` は **ruff のみ**（pyright の `include` は `["app","tests"]` のまま ── pandas の型は standard で騒がしく `app/ai` と同じ割り切り）。ruff の `src` / `known-first-party` には `analysis` を含める。pandas は `app/domain` `app/algorithms` や solve/verify/benchmark のリクエスト経路には**絶対に入れない**（純粋レイヤーの契約・「手実装で示す」軸・テスト速度と衝突）。このトラックは Phase 4/6/10/12/14/15 が育てる（設計は `../textbook/Phase-3/Phase-3-8.md`、相談ログ Q18）。

### 型解析（Pylance / pyright）

`backend/pyproject.toml` の `[tool.pyright]` で解析ルートを `backend/` に固定している（`typeCheckingMode = "standard"`）。ワークスペースをどのフォルダで開いても `app` が first-party として解決される。first-party の import が Pylance で赤い場合はまず解析ルートを疑う（詳細は `README.md` の「エディタ / 型チェック」、ルート `../CLAUDE.md` の Notes）。この tooling 設定はテンプレート（`fastapi-langchain-template`）への還元候補。判別子のあるサブタイプ（`Constraint` 系）は、基底に `kind` を宣言すると standard モードで `reportIncompatibleVariableOverride` が出るため、共通フィールドだけの基底 + 各サブタイプが `kind` を宣言する形にする（設計は `../textbook/Phase-0/Phase-0-2.md` §4）。

### chat 機能の無効化（Phase 11 まで）

テンプレート由来の LLM チャット機能は DeciTima では Phase 11 から扱う。それまでは：

- `app/api/routes/__init__.py` の集約から `chat_router` を外し、`POST /chat` を無効化している。
- `app/api/routes/chat.py`・`app/ai/`・`app/schemas/chat.py`・`app/schemas/generation.py`・`Conversation`/`Message` モデル・既存マイグレーションは**削除せず保持**（Phase 11 で DeciTima 用ワークフローに作り替える土台）。
- `app/ai/graph/` 単体のテスト（`tests/unit/test_ai_graph_nodes.py`）はそのまま有効。

## エラーハンドリングの設計

- `app/core/errors.py`に`AppError`とHTTPステータスコード別の基底例外（`NotFoundError`, `ConflictError`など）を定義し、`app/services/errors.py`に具体的なドメイン例外（`UserAlreadyExistsError`など）をまとめている。
- **なぜ`services/errors.py`という1つのleafモジュールに例外を集約しているか**：各サービスファイルに例外を分散させると、あるサービスが別サービスの例外をimportする際に循環importが発生しやすい。依存関係を持たない末端モジュールに全ドメイン例外を集めることで、この問題を構造的に避けている。
- ルートは`AppError`を`try/except`で捕まえず、そのまま伝播させる。`app/api/error_handlers.py`の`register_error_handlers`が一括で`AppError`→JSONレスポンスに変換するため、ルートごとの`try/except HTTPException`のボイラープレートが不要になる。
- **例外：`app/api/deps.py`の認証境界だけは生の`HTTPException`を使う**。認証失敗の理由（トークン不正／期限切れ／ユーザー無効化など）を外部に細かく漏らさないため、あえて`AppError`の仕組みを使わずこの1箇所に閉じている。これは意図的な設計であり、統一漏れではない。

## リポジトリ層

- `app/repositories/base.py`の`CRUDRepository[ModelType]`が、`get_by_id` / `find_one` / `list_all` / `get_or_create` / `count` / `delete`という共通CRUD操作を提供する（PEP 695のジェネリクス構文を使用）。
- 各リポジトリは`model`属性にORMモデルを指定して継承し、Eagerロードが必要な場合は`_default_options()`を上書きする（例：`ConversationRepository`は`Message`を常に`selectinload`する）。
- 新しいエンティティを追加する際は、まずこの基底クラスを継承し、固有のクエリだけを追加メソッドとして書くのが基本パターン。

## レート制限

- `app/services/rate_limit.py`の`RateLimiter`は、Redisの`INCR`+`EXPIRE`を使った汎用的な複数ウィンドウ（時間単位・日単位など）のレート制限クラス。
- **なぜ`ChatService`のコンストラクタに直接ロジックを書かず、独立したサービスに切り出したか**：レート制限の対象・ウィンドウ・上限値は機能ごとに異なりうるため、`RateLimiter`を汎用部品として切り出し、各サービスは「どのresource名で、どのウィンドウ設定を使うか」だけを指定する形にしている。

## LLM/LangGraph連携

- `app/ai/llm/gemini.py`・`app/ai/tools/tavily.py`は、LLM/検索ツールのクライアントを`lru_cache`でプロセス内キャッシュしている。**理由**：クライアント生成コストを避けつつ、単一プロセス・単一APIキー構成のテンプレートとしてはこれで十分なため。マルチテナントで複数APIキーを使い分ける場合はこのキャッシュ戦略を見直す必要がある。
- `app/ai/graph/`にLangGraphの`StateGraph`ワークフローを定義。ノード（`nodes.py`）・状態（`state.py`）・組み立て（`workflow.py`）を分離している。
- `app/services/chat.py`の`_invoke_with_retry`は、LLM呼び出しをラップし「クォータ超過（429相当）は即座に諦める」「それ以外の一時的エラーは規定回数リトライする」を切り分けている。クォータ超過をリトライしても無駄にAPIコールを消費するだけなので、ここは明確に区別する設計にしている。
- `generate_final_answer`ノードは`with_structured_output`でPydanticスキーマ（`app/schemas/generation.py`の`FinalAnswer`）を使った構造化出力を行う。生文字列のパースに頼らず、LLM出力の型を保証するための最小限のデモ実装。

## テストの分離

- `backend/tests/conftest.py`は、`app.core.database`などをimportする**前**に`os.environ.setdefault(...)`でテスト用の`DATABASE_URL`等を設定している。**なぜこの順序が重要か**：Pythonのimportは一度実行されると以後はキャッシュされるため、先に本物の設定を使うモジュールがimportされてしまうと、後から環境変数を上書きしても手遅れになる。この順序を誤ると、テストが誤って開発/本番用のDBに接続してしまう事故につながる。
- ユニットテストはインメモリSQLite（`db_session`フィクスチャ）、統合テスト（`tests/integration/`）は実際のPostgreSQL/Redis（`docker compose up postgres redis`で起動）を使う。統合テストは`@pytest.mark.integration`でマークされ、デフォルトでは実行されない（`pyproject.toml`の`addopts = "-m 'not integration'"`）。

## Docker構成

- `backend/Dockerfile`は`base → builder → runtime`の3段構成。開発時は`builder`ステージ（`--reload`付き）をソースのbindマウントと組み合わせて使い、本番は`runtime`ステージ（非rootユーザー、`--reload`無し）を使う。
- `nginx/nginx.conf`（開発用、平文HTTP）と`nginx/nginx.prod.conf`（本番用、HTTP→HTTPSリダイレクト＋certbot対応＋TLS終端）を分離している。

# FastAPI + LangChain + LangGraph Template

FastAPI・LangChain・LangGraph・PostgreSQL・Redisを組み合わせた、AIチャットバックエンドの開発テンプレートです。JWT認証基盤とLangGraphによる`User → Gemini → Tavily → 検索結果評価 → Gemini → 最終回答`のワークフローに加え、`AppError`による統一エラーハンドリングとRedisベースのレート制限を備えています。

設計判断の背景（なぜエラーを1箇所に集約しているか、なぜリポジトリ層は`flush`のみか等）は [`CLAUDE.md`](./CLAUDE.md) にまとめています。

## 技術スタック

| 分類 | 技術 |
| --- | --- |
| 言語 / ランタイム | Python 3.13 |
| Web Framework | FastAPI, Uvicorn |
| AI | LangChain, LangGraph, Gemini (`langchain-google-genai`), Tavily (`langchain-tavily`) |
| DB | PostgreSQL, SQLAlchemy 2.x (async), Alembic |
| Cache / State | Redis |
| 認証 | PyJWT, pwdlib (Argon2) |
| バリデーション | Pydantic v2, pydantic-settings |
| パッケージ管理 | uv |
| テスト | pytest, pytest-asyncio, pytest-mock, pytest-cov, HTTPX |
| Lint / Format | Ruff |
| インフラ | Docker, Docker Compose, Nginx |
| CI/CD | GitHub Actions |

## ディレクトリ構造

```text
project-root/
├── .github/workflows/deploy.yml   # CI (test) + CD (SSH deploy)
├── CLAUDE.md                       # アーキテクチャ全体像・設計判断の記録
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPIエントリーポイント
│   │   ├── api/                   # ルーティング + DI + エラーハンドラ登録
│   │   ├── core/                  # 設定 / セキュリティ / DB接続 / 共通例外(AppError)
│   │   ├── models/                # SQLAlchemy ORM
│   │   ├── schemas/                # Pydantic Schema（LLM構造化出力スキーマ含む）
│   │   ├── services/               # ユースケース層 / ドメイン例外 / レート制限
│   │   ├── repositories/           # データアクセス層（汎用CRUD基底クラス）
│   │   ├── ai/                     # LangChain / LangGraph / Gemini / Tavily
│   │   └── infrastructure/         # Redis / HTTPクライアント
│   ├── alembic/                    # DBマイグレーション
│   ├── tests/{unit,integration,fixtures}/
│   ├── pyproject.toml / uv.lock
│   └── Dockerfile
├── nginx/nginx.conf                # 開発用（平文HTTP）
├── nginx/nginx.prod.conf           # 本番用（HTTPSリダイレクト + TLS終端 + certbot対応）
├── docker-compose.yml              # 開発環境
├── docker-compose.prod.yml         # 本番環境
├── .env.example                    # docker-compose用
└── backend/.env.example            # ホスト上で直接起動する場合用
```

## 必要な環境

- Python 3.13（`uv`が自動で用意するため手動インストールは不要）
- [uv](https://docs.astral.sh/uv/)
- Docker / Docker Compose（コンテナで動かす場合）

## uvのセットアップ

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

cd backend
uv sync   # pyproject.toml / uv.lock から依存関係を再現
```

## 環境変数

- ルートの `.env.example` … `docker-compose` で使用（Postgres/Redis の認証情報 + バックエンドへ渡す設定）
- `backend/.env.example` … `backend/` 直下で `uv run uvicorn ...` のようにホスト上で直接起動する場合用

いずれも `.env` にコピーして値を埋めてください（`.env` はコミットしないでください）。

| 変数 | 説明 |
| --- | --- |
| `ENVIRONMENT` | `development` / `production` など。`production`時はSwagger UI・ReDoc・OpenAPIスキーマを自動的に非公開にします |
| `DATABASE_URL` | 例: `postgresql+asyncpg://user:pass@host:5432/app` |
| `REDIS_URL` | 例: `redis://host:6379/0` |
| `JWT_SECRET_KEY` | JWT署名用シークレット（32byte以上推奨） |
| `JWT_ALGORITHM` | 既定 `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token有効期限（分） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token有効期限（日）。RedisにJTI単位で保存されます |
| `GOOGLE_API_KEY` | Gemini用APIキー |
| `TAVILY_API_KEY` | Tavily検索用APIキー |
| `GEMINI_MODEL` | 既定 `gemini-2.5-flash` |
| `CHAT_RATE_LIMIT_PER_HOUR` | チャットメッセージ送信のレート制限（1時間あたり、既定 `20`）。超過時は429を返します |
| `CHAT_RATE_LIMIT_PER_DAY` | チャットメッセージ送信のレート制限（1日あたり、既定 `100`） |
| `DEBUG` | 本番では必ず `false` |

## 開発環境

### Docker Composeで起動

```bash
cp .env.example .env   # 値を編集してから

docker compose up --build
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Nginx経由のヘルスチェック: http://localhost/health

backendコンテナは `backend/` をバインドマウントし、`--reload` 付きUvicornで起動するため、コード変更が即座に反映されます（`.venv` は名前付きボリュームで分離しているためホストの仮想環境と衝突しません）。

### Dockerを使わずホストで直接起動

```bash
cd backend
cp .env.example .env   # localhostのPostgres/Redisを指す値に編集
uv run uvicorn app.main:app --reload
```

## DB Migration

```bash
cd backend
uv run alembic upgrade head          # マイグレーション適用
uv run alembic revision --autogenerate -m "message"   # 新規マイグレーション作成
```

Docker Compose経由で実行する場合:

```bash
docker compose exec backend uv run alembic upgrade head
```

## 開発用シード

`decitima-ui` の `/login` からログインを試すためのテストユーザーを 1 人作る（冪等・dev 専用）。

```bash
cd backend
uv run python -m scripts.seed
# docker:
docker compose run --rm backend uv run python -m scripts.seed
```

作成される資格情報: `example-user@example.com` / `sample-user-0123`（`scripts/seed.py` の `SEED_USER`）。

## テスト実行方法

```bash
cd backend
uv run pytest                        # unit tests（既定でintegrationは除外）
uv run pytest -m integration         # PostgreSQL/Redisが起動している状態で結合テスト
uv run pytest --cov=app --cov-report=term-missing   # カバレッジ付き
```

結合テスト (`tests/integration/`) はFastAPI → 実PostgreSQL → 実Redisを実際に使用するため、`docker compose up postgres redis` などで両方を起動した状態で実行してください。Gemini/TavilyはUnit Testでは全てMockに置き換えています（`tests/unit/test_ai_graph_nodes.py`）。

**`docker compose run` 経由で実行する場合は `DATABASE_URL` を明示的にテスト専用データベース（`app_test`）へ上書きすること。** `env_file: .env` により `backend` サービスには実データベース（`app`）の `DATABASE_URL` がそのまま注入されるため、上書きを忘れると結合テストのフィクスチャが `Base.metadata.drop_all()` で実データベースの全テーブルを消去してしまう（2026-09-14 に実際に発生した事故）。`tests/integration/conftest.py::ensure_test_database()` が `DATABASE_URL` に `test` が含まれない場合は実行前に止める安全装置になっているが、念のため常に明示的に上書きすること:

```bash
docker compose run --rm --no-deps \
  -e DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's#/app$#/app_test#')" \
  backend uv run pytest -m integration
```

`app_test` データベースは `postgres-init/01-create-test-db.sql` により新規環境では自動作成される（既存の `postgres_data` ボリュームでは自動実行されないため、既存環境では初回のみ `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "CREATE DATABASE app_test OWNER $POSTGRES_USER;"` を手動実行する）。

## Ruff実行方法

```bash
cd backend
uv run ruff check .      # Lint
uv run ruff format .     # Format
```

## エディタ / 型チェック

型解析(VSCode の Pylance、CLI の pyright)の設定は `backend/pyproject.toml` の
`[tool.pyright]` に集約している。解析ルートを `backend/` に固定しているため、
**ワークスペースをどのフォルダで開いても `app` パッケージが first-party として解決される**。

- 親ディレクトリ（`decitima-project` など）を開いて作業する場合は、そのワークスペース側の
  `.vscode/settings.json` に `"python.analysis.extraPaths": ["decitima-api/backend"]` を足すと
  Pylance がより確実に解決する。
- CLI で確認: `cd backend && uvx --with pydantic --with pydantic-settings pyright`
- 設定変更後は VSCode で「Developer: Reload Window」。
- first-party の import が赤いままなら、まず解析ルートが `backend/` になっているかを疑う
  （`from route_planner import ...` のような bare import は実行時 `ModuleNotFoundError` にも
  なるので、`from app.domain.problems.route_planner import ...` と絶対 import にする）。

## 本番環境

```bash
cp .env.example .env     # 本番用の値（強固なパスワード・シークレット）を設定
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend uv run alembic upgrade head
```

`docker-compose.prod.yml` では以下を行っています。

- `--reload`を使用しない本番用Uvicorn起動
- backendコンテナのポートをホストに公開せず、Nginxのみを外部公開の入口とする
- PostgreSQL/RedisはDocker内部ネットワークのみに限定し、ポートを公開しない
- PostgreSQLデータは名前付きVolumeで永続化
- `ENVIRONMENT=production`が設定されるため、Swagger UI・ReDoc・OpenAPIスキーマは自動的に非公開になります
- Nginxは`nginx/nginx.prod.conf`（80→443へのリダイレクト + TLS終端 + certbotの`/.well-known/acme-challenge/`対応）を使用します。有効化するには`nginx/certs/`に`fullchain.pem`・`privkey.pem`を配置してください（証明書自体の発行・更新（certbotの実行）は本テンプレートには含まれていないため、別途用意する必要があります）

## GitHub Actionsによるデプロイ方法

`.github/workflows/deploy.yml` は `main` へのpushをトリガーに、テスト → SSHでVPSへ接続 → `git pull` → `docker compose build/up` → `alembic upgrade head` を実行します。

以下のSecretsをGitHubリポジトリに登録してください（Settings → Secrets and variables → Actions）。

| Secret名 | 内容 |
| --- | --- |
| `VPS_HOST` | デプロイ先VPSのホスト名 / IPアドレス |
| `VPS_USER` | SSHログインユーザー名 |
| `VPS_SSH_PRIVATE_KEY` | SSH秘密鍵（PEM形式） |
| `VPS_SSH_PORT` | SSHポート番号 |
| `VPS_PROJECT_PATH` | VPS上のリポジトリ配置先パス |

VPS側には事前に以下を用意してください。

1. リポジトリをclone済みであること（`git pull`が実行できる状態）
2. Docker / Docker Composeがインストール済みであること
3. VPS上の `.env`（本番用の値）が配置済みであること（`.env`はGit管理対象外のため、初回は手動で配置）

## 未実装・今後対応が必要な事項

- 認証API（登録・ログイン・リフレッシュ・ログアウト）の基盤は実装済みですが、パスワードリセットやメール確認などの拡張は未実装です
- LangGraphのワークフローは検索要否判定が簡易的なダミー実装です。実運用では`draft_response`内の判定ロジックを強化してください
- 本番用HTTPS証明書の発行・自動更新（certbotの実行）は自動化されておらず、別途スクリプトやCronの用意が必要です

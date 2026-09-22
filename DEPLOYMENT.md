# デプロイ Runbook

GitHub → GitHub Actions → Docker → VPS(API)、Next.js → Vercel(UI)。
**手順書のみ。実際の VPS 契約・ドメイン取得・Vercel 連携・TLS 証明書発行は含まない。**

## API(decitima-api)

前提: `docker-compose.prod.yml`(`postgres` / `redis` / `backend` / `worker` / `nginx`)・
`nginx/nginx.prod.conf`・`backend/Dockerfile` の `runtime` ステージを使う。

1. **CI(`.github/workflows/backend-ci.yml`)** が `main` へのプッシュで lint・型・テスト・性能回帰・Docker ビルドを検証する。
2. **VPS への配置**:
   ```bash
   # 初回
   git clone <decitima-api リポジトリ> && cd decitima-api
   cp .env.example .env            # 実際の値に書き換える(SECURITY.md の本番チェックリスト)
   mkdir -p nginx/certs            # fullchain.pem / privkey.pem を配置
   docker compose -f docker-compose.prod.yml up -d --build

   # 更新時
   git pull && docker compose -f docker-compose.prod.yml up -d --build
   ```
3. **マイグレーション**: 新しいテーブルを伴う更新では、起動後に
   `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head` を実行する。
4. **確認**: `curl https://<domain>/health` が 200 かつ `"status":"ok"`。`worker` が起動していること
   (`docker compose -f docker-compose.prod.yml ps`)を確認する ── 落ちていると `/jobs` `/simulate` は 202 を返すのに
   ジョブが `queued` のまま進まない。
5. **ロールバック**: `git checkout <前のコミット> && docker compose -f docker-compose.prod.yml up -d --build`。
   テーブル追加を伴う更新は `alembic downgrade` も検討する。

`ENVIRONMENT=production` の起動時検証(`E2E_TESTING` / `DEBUG` / 弱い `JWT_SECRET_KEY` の拒否)に引っかかると
`backend` / `worker` は起動直後に終了する。`docker compose logs backend` のエラー文に原因が出る。

## ソルバーの実行方式(SOLVE_ISOLATION)

既定の `thread` では、タイムアウト(504)を返した後も計算スレッドが走り続けて CPU を占有する。
`.env` に `SOLVE_ISOLATION=process` を設定すると、solve / benchmark / simulate のシナリオ実行が
使い捨ての子プロセス(forkserver)で行われ、**タイムアウト・クライアント切断で子プロセスごと kill される**
(実測: タイムアウト後 2 秒間の CPU 消費は thread で 4.13 秒、process で 0.00 秒)。複数の solve が
コア数まで並列に走る利点もあるが、呼び出しごとに約 50〜100 ms のオーバーヘッドが乗る。

- まず `worker` サービスだけに設定するのが安全(同期の `POST /solve` は遅延が利用者に見える)。`.env` は
  `backend` と `worker` で共有されるので、`docker-compose.prod.yml` の `worker` の `environment:` に
  `SOLVE_ISOLATION: process` を書く。
- **コンテナ内での動作は未検証**(実験は WSL 上のホストで実施)。有効化前にステージングで確認する。
- `SOLVE_MAX_PROCESSES`(既定 4)を VPS のコア数に合わせる。
- 有効化後、重い問題をタイムアウトさせて `docker stats` で CPU が解放されることを確認する。

## UI(decitima-ui)

1. Vercel にリポジトリを接続(`main` への自動デプロイ)。
2. 環境変数は `NEXT_PUBLIC_API_URL`(デプロイした API の公開 URL)だけ。`NEXT_PUBLIC_*` はブラウザに露出するので秘密情報を置かない。
3. ビルド設定は Next.js の既定のまま。

## CORS との連携

API 側の `CORS_ORIGINS` に Vercel のドメイン(本番 + プレビュー)を設定する。

## 未実施

実際の VPS・ドメイン・Vercel・証明書の用意、HTTP レベルの負荷試験。

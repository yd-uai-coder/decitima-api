# セキュリティ

README §15「Security」の 6 項目について、実装のどこが担っているかと、デプロイ前の確認事項をまとめる。
診断の経緯・未対応事項は `../textbook/appendix/project-diagnosis.md` §5・§6。

## 1. Authentication(認証)

| 項目 | 実装 |
| --- | --- |
| パスワード | Argon2(`app/core/security.py`)。`UserCreate.password` は 10〜128 文字(上限は巨大入力で Argon2 の CPU を浪費させる攻撃の対策) |
| トークン | JWT(access 30 分 + refresh 30 日)。`type` クレームで用途を分離し、`jti` を Redis に保持して失効できる(`app/services/auth.py`) |
| ユーザー列挙の抑止 | ユーザー不在でもダミーハッシュに対して Argon2 検証を行い(応答時間を揃える)、「不在 / パスワード不一致 / 無効化済み」は同じ文言 `Invalid email or password` |
| 無効化ユーザー | リフレッシュ時に `is_active` を再確認する(無効化後は既存のリフレッシュトークンで再発行できない) |
| ブルートフォース | `POST /auth/login` は IP 単位(30/時)とメール単位(20/時)、`POST /auth/register` は IP 単位(10/時)でレート制限(`app/services/auth_rate_limit.py`)。nginx でも IP 単位の粗い制限をかける |

**既知の残課題**: リフレッシュトークンはローテーションしない(UI は `localStorage` に保管)。`POST /auth/register` は
重複メールで 409 を返すため、メールの存在は登録試行で判別できる(レート制限でのみ緩和)。

## 2. Authorization(認可)

全ての読み書きが所有者スコープ(`user_id`)を通る。他人のリソースは 403 でなく **404**(存在の有無を漏らさない)。
`OptimizationReadService`(problems / solutions)、`JobService.get_for_user`(jobs)、`/explain` のキャッシュ参照
(所有者チェックがキャッシュ参照より先)が該当する。**新しいエンドポイントを足すときはこのパターンから外れないこと。**

## 3. Input Validation(入力検証)

- 全リクエストボディを Pydantic で検証(判別可能ユニオン・値域・`model_validator`)。SQL は ORM/パラメータ化クエリのみ。
- **サイズ上限**: ボディ 2MB(`MAX_REQUEST_BODY_BYTES`、`app/api/middleware.py`。Content-Length が無いチャンク転送も
  受信バイト数で拒否 → 413)、`StructuringRequest.text` は 1〜2000 文字、`SimulationRequest.scenarios` は 1〜20 件。
- **タイムアウト**: 利用者指定の `timeout_seconds` は `SOLVE_TIMEOUT_SECONDS` で頭打ち(`app/services/timeouts.py`)。
  計算スレッドを長時間占有させられない。

## 4. Rate Limit(レート制限)

`app/services/rate_limit.py::RateLimiter`。カウンタの加算と TTL 設定を `MULTI/EXEC` で 1 往復にまとめる
(途中でプロセスが落ちても TTL 無しのキーが残らない)。`EXPIRE ... NX` を使うため **Redis 7.0 以上が必要**。
solve / verify / benchmark / jobs / simulate / structure / recommend / explain / compare は利用者単位、
認証系は IP・メール単位(`app/core/config.py` の `*_RATE_LIMIT_*`)。`/explain` はキャッシュヒット時に枠を消費しない。

## 5. CORS

`CORSMiddleware`(`app/main.py`)は origin を `CORS_ORIGINS` に限定し、メソッドは `GET/POST/PUT/PATCH/DELETE/OPTIONS`、
ヘッダは `Authorization` / `Content-Type` / `Accept` だけを許可する。

## 6. Secret Management(秘密情報)

`.env` は `.gitignore` で除外、コミットするのは `.env.example` のみ。**`ENVIRONMENT=production` のとき、次の設定は起動時に拒否される**
(`app/core/config.py`): `E2E_TESTING=true`(LLM が固定応答のフェイクになる)/ `DEBUG=true` /
`JWT_SECRET_KEY` が 32 文字未満または `change-me` で始まる値。

その他: ジョブ失敗時に利用者へ返す `error` は、利用者向けに書かれた例外(`AppError`)以外は固定文言 `internal error`
にして内部事情(SQL 断片・パス)を返さない(詳細はサーバーログ)。

## 7. ネットワーク境界(nginx / Docker)

- Postgres / Redis / backend は公開ポートを持たず、内部ネットワークの nginx からしか届かない(`docker-compose.prod.yml`)。
- nginx: `server_tokens off`、IP 単位のレート制限(全体 20 req/s、`/api/v1/auth/` は 30 req/min)、`X-Forwarded-For` は
  利用者の値を引き継がず nginx が見た接続元で上書き(IP 制限のキーを偽装させない)、`nosniff` / `X-Frame-Options` /
  `Referrer-Policy`、本番は HSTS。
- backend の runtime イメージは `--proxy-headers --forwarded-allow-ips "*"` で起動する。**backend を直接公開する構成では使わないこと**
  (X-Forwarded-For を偽装されて IP 制限を回避される)。

## 本番チェックリスト

- [ ] `JWT_SECRET_KEY` をランダムな 64 文字以上に(短い・プレースホルダのままだと起動しない)
- [ ] `ENVIRONMENT=production`、`DEBUG=false`、`E2E_TESTING` を設定しない(設定すると起動しない)
- [ ] `CORS_ORIGINS` を実際のフロントエンドのドメインに
- [ ] `DATABASE_URL` / `REDIS_URL` を本番の接続先に(Redis は 7.0 以上)
- [ ] `nginx/certs/` に `fullchain.pem` / `privkey.pem` を配置
- [ ] `docker compose -f docker-compose.prod.yml` に **`worker` サービスが含まれている**こと(無いと `/jobs` `/simulate` が処理されない)

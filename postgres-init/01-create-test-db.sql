#!/bin/sh
# postgres:17-alpine イメージの /docker-entrypoint-initdb.d/ 規約に沿う初期化スクリプト。
# 新規にボリュームを作る環境でのみ、コンテナ起動時に自動実行される
# (既存の postgres_data ボリュームでは再実行されない ── 既存環境では手動で
# `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "CREATE DATABASE app_test OWNER $POSTGRES_USER;"`
# を1回実行すること)。
#
# 統合テスト(tests/integration/)が誤って実データベース($POSTGRES_DB)に対して
# Base.metadata.drop_all() を実行してしまう事故(全テーブル削除)を防ぐため、
# テスト専用のデータベースをここで用意する。
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE app_test OWNER $POSTGRES_USER;
EOSQL

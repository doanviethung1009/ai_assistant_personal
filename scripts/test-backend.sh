#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Chạy pytest của backend trên database RIÊNG, không đụng database dev.
#
#  Dùng:
#    bash scripts/test-backend.sh                 # chạy toàn bộ
#    bash scripts/test-backend.sh -k ai_log -x    # truyền tham số cho pytest
#    make test                                    # tương đương
#
#  Vì sao tách DB: test DB XOÁ SẠCH bảng nghiệp vụ sau mỗi test (xem
#  apps/core/tests/conftest.py). Chạy trên DB dev là mất task/note thật.
#  Script tạo database `<POSTGRES_DB>_test` nếu chưa có và trỏ
#  TEST_DATABASE_URL vào đó; schema do conftest dựng bằng Alembic.
#
#  Cần stack đang chạy (make up): dùng container postgres và api.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

DC="docker compose"

# Tạo DB test nếu chưa có (chạy trong container postgres, nơi có sẵn
# POSTGRES_USER và POSTGRES_DB).
$DC exec -T postgres sh <<'INNER'
if ! psql -U "$POSTGRES_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}_test'" | grep -q 1; then
  createdb -U "$POSTGRES_USER" "${POSTGRES_DB}_test"
fi
INNER

# TEST_DATABASE_URL suy từ DATABASE_URL của api: đổi tên database cuối
# thành `<tên>_test`, giữ nguyên user, mật khẩu, host.
$DC exec -T api sh -s -- "$@" <<'INNER'
export TEST_DATABASE_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's#/([^/?]+)$#/\1_test#')"
exec pytest -q "$@"
INNER

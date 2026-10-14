#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Chạy lint + migration + pytest của apps/core trên VM dev (ai-dev-01),
#  vì máy local không có Docker.
#
#  Dùng (CORE_SRC=<thư mục> để thử một bản sao khác thay cho apps/core):
#    bash scripts/patches/dev-vm-backend-test.sh              # toàn bộ
#    bash scripts/patches/dev-vm-backend-test.sh -k isolation # truyền cho pytest
#
#  CÁCH LY (cố ý): KHÔNG đụng stack dev đang chạy trong /srv/builder-ai/dev.
#    - Mã nguồn rsync vào ~/auth-test/<run-id> (thư mục riêng của user deploy).
#    - Postgres riêng `authtest-pg` (dữ liệu trên tmpfs, mất khi dừng), network riêng.
#    - Không dùng DB, volume hay compose project của stack dev; dọn sạch khi xong.
#  VM chỉ ~2.4 GB RAM nên đặt giới hạn bộ nhớ cho container tạm và chạy từng lần một (flock).
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/../.."

SSH_KEY="${SSH_KEY:-$HOME/.ssh/ai_assistant_deploy}"
HOST="${DEV_VM:-deploy@192.168.100.201}"
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST")

# Mỗi lần chạy một thư mục + tên container riêng: nhiều session dùng chung script này và
# từng đạp lên nhau (xoá network, ghi đè mã nguồn) rồi làm VM cạn RAM.
RUN_ID="$$-$(date +%s)"
echo "==> rsync -> $HOST:~/auth-test/$RUN_ID"
"${SSH[@]}" "mkdir -p ~/auth-test/$RUN_ID"
rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  -e "ssh -i $SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes" \
  "${CORE_SRC:-apps/core}/" "$HOST:~/auth-test/$RUN_ID/"

# Tham số pytest đưa qua biến môi trường để khỏi lồng quoting ba lớp.
PYTEST_ARGS="$*"
"${SSH[@]}" "PYTEST_ARGS='${PYTEST_ARGS}' RUN_ID='${RUN_ID}' bash -s" <<'REMOTE'
set -euo pipefail
cd ~/auth-test/$RUN_ID
# Hàng đợi: VM chỉ ~2.4 GB RAM nên chỉ cho MỘT lần chạy tại một thời điểm (nhiều session
# cùng dùng script này). Lần sau xếp hàng chờ tối đa 30 phút thay vì đạp lên nhau.
exec 9>/tmp/authtest.lock
flock -w 1800 9 || { echo "Hết thời gian chờ hàng đợi test" >&2; exit 3; }

NET="authtest-net-$RUN_ID"
PG="authtest-pg-$RUN_ID"
API="authtest-api-$RUN_ID"
SECRET="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"   # mật khẩu DB tạm, chỉ sống trong lần chạy
JWT="$(head -c 32 /dev/urandom | base64 | tr -d '/+=')"

cleanup() {
  docker rm -f "$PG" "$API" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker run --rm -v "$HOME/auth-test:/t" --entrypoint sh authtest-api:latest -c "rm -rf /t/$RUN_ID" >/dev/null 2>&1 || true
  rm -rf ~/auth-test/"$RUN_ID" 2>/dev/null || true
}
trap cleanup EXIT

docker network create "$NET" >/dev/null
echo "==> Postgres tạm (tmpfs)"
docker run -d --name "$PG" --network "$NET" --memory 400m \
  --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD="$SECRET" -e POSTGRES_USER=app -e POSTGRES_DB=app_test \
  pgvector/pgvector:pg17 >/dev/null
for _ in $(seq 1 30); do
  docker exec "$PG" pg_isready -U app -d app_test >/dev/null 2>&1 && break
  sleep 1
done

echo "==> build image (target dev)"
docker build -q --target dev -t authtest-api:latest . >/dev/null

DB_URL="postgresql+asyncpg://app:${SECRET}@${PG}:5432/app_test"
run() {
  # bind-mount mã nguồn như stack dev: .dockerignore loại tests/ khỏi image
  docker run --rm --name "$API" --network "$NET" --memory 700m -v "$PWD:/app" \
    -e DATABASE_URL="$DB_URL" -e TEST_DATABASE_URL="$DB_URL" \
    -e API_KEY="test-api-key-not-secret" -e CORE_JWT_SECRET="$JWT" \
    -e ADMIN_EMAILS="admin@example.test" -e ENVIRONMENT=development \
    -e REDIS_URL="redis://localhost:6379/0" \
    authtest-api:latest "$@"
}

echo "==> ruff"
run sh -c 'ruff check --no-cache app migrations tests'
# Format chỉ cảnh báo: migration cũ (ai_logs) chưa format từ trước, không thuộc phạm vi đang thử.
run sh -c 'ruff format --no-cache --check app migrations tests' || echo "CẢNH BÁO: có file chưa format (không chặn)"
echo "==> alembic: heads, upgrade, downgrade -1, upgrade, check"
run sh -c 'test "$(alembic heads | wc -l)" = 1 && alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check'
echo "==> pytest"
# shellcheck disable=SC2086
run sh -c "pytest -q -p no:cacheprovider ${PYTEST_ARGS}"
REMOTE

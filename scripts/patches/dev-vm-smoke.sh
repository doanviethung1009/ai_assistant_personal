#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Chạy `make smoke` (scripts/smoke-test.sh) trên VM dev trong một stack TẠM,
#  cô lập hoàn toàn khỏi stack dev đang chạy.
#
#  Dùng:  bash scripts/patches/dev-vm-smoke.sh [<git-ref>]    (mặc định: origin/main)
#
#  VÌ SAO KHÔNG DEPLOY THẲNG VÀO /srv/builder-ai/dev: checkout đó có thay đổi chưa commit
#  và DB thật; kéo `main` + migrate sẽ đè mã đang chạy và đổi schema dữ liệu thật.
#  Script này: xuất đúng commit bằng `git archive` (không lấy thay đổi chưa commit ở máy
#  local) -> ~/smoke/<run-id> trên VM -> Postgres tmpfs + Redis + api riêng, cổng 127.0.0.1:18000
#  -> kích hoạt MỘT user thử trong DB tạm -> chạy smoke với shim `make` (không có Docker
#  compose của dự án) -> dọn sạch. Không đụng container `builder-*`, volume, hay .env của dev.
#  VM chỉ ~2.4 GB RAM nên: giới hạn bộ nhớ, và chỉ một lượt tại một thời điểm (flock).
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/../.."

REF="${1:-origin/main}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ai_assistant_deploy}"
HOST="${DEV_VM:-deploy@192.168.100.201}"
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST")
RUN_ID="$$-$(date +%s)"

echo "==> xuất $REF ($(git rev-parse --short "$REF")) -> $HOST:~/smoke/$RUN_ID"
"${SSH[@]}" "mkdir -p ~/smoke/$RUN_ID"
git archive "$REF" apps/core scripts/smoke-test.sh Makefile | "${SSH[@]}" "tar -x -C ~/smoke/$RUN_ID"

"${SSH[@]}" "RUN_ID='$RUN_ID' bash -s" <<'REMOTE'
set -euo pipefail
cd ~/smoke/$RUN_ID
exec 9>/tmp/authtest.lock
flock -w 1800 9 || { echo "Hết thời gian chờ hàng đợi" >&2; exit 3; }

NET="smoke-net-$RUN_ID"; PG="smoke-pg-$RUN_ID"; RD="smoke-rd-$RUN_ID"; API="smoke-api-$RUN_ID"
IMG="smoke-api:$RUN_ID"; PORT=18000
SMOKE_EMAIL="smoke-admin@example.test"
DBPASS="$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
APIKEY="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
JWT="$(head -c 32 /dev/urandom | base64 | tr -d '/+=')"

cleanup() {
  docker rm -f "$API" "$PG" "$RD" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker rmi "$IMG" >/dev/null 2>&1 || true
  docker run --rm -v "$HOME/smoke:/t" --entrypoint sh python:3.12-slim -c "rm -rf /t/$RUN_ID" >/dev/null 2>&1 || true
  rm -rf ~/smoke/"$RUN_ID" 2>/dev/null || true
}
trap cleanup EXIT

docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" --memory 400m --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD="$DBPASS" -e POSTGRES_USER=app -e POSTGRES_DB=app \
  pgvector/pgvector:pg17 >/dev/null
docker run -d --name "$RD" --network "$NET" --memory 64m redis:7-alpine >/dev/null
for _ in $(seq 1 30); do docker exec "$PG" pg_isready -U app -d app >/dev/null 2>&1 && break; sleep 1; done

echo "==> build image api (target dev)"
docker build -q --target dev -t "$IMG" apps/core >/dev/null

docker run -d --name "$API" --network "$NET" --memory 700m -p 127.0.0.1:$PORT:8000 \
  -v "$PWD/apps/core:/app" \
  -e DATABASE_URL="postgresql+asyncpg://app:${DBPASS}@${PG}:5432/app" \
  -e REDIS_URL="redis://${RD}:6379/0" -e API_KEY="$APIKEY" -e CORE_JWT_SECRET="$JWT" \
  -e ADMIN_EMAILS="$SMOKE_EMAIL" -e ENVIRONMENT=development \
  -e RATE_LIMIT_REQUESTS_PER_MINUTE=100000 \
  "$IMG" >/dev/null
echo "==> chờ api sẵn sàng (tự chạy alembic upgrade head)"
ok=0
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$PORT/health/ready" >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[[ "$ok" == 1 ]] || { docker logs --tail 40 "$API" >&2; echo "api không sẵn sàng" >&2; exit 2; }

# Admin từ ADMIN_EMAILS ở trạng thái `invited` (chỉ Google login mới kích hoạt): chỉ trong DB tạm này.
docker exec "$PG" psql -U app -d app -Atc "UPDATE users SET status='active', google_sub='smoke-sub-$RUN_ID' WHERE email='$SMOKE_EMAIL'" >/dev/null

# Shim `make`: smoke chỉ gọi `make -s auth-token` và `make -s auth-create-local`; chuyển vào container api tạm.
mkdir -p shim
cat > shim/make <<SHIM
#!/usr/bin/env bash
target=""; email=""; ttl=60; username=""
for a in "\$@"; do case "\$a" in auth-*) target="\${a#auth-}";; EMAIL=*) email="\${a#EMAIL=}";; TTL=*) ttl="\${a#TTL=}";; USERNAME=*) username="\${a#USERNAME=}";; esac; done
case "\$target" in
  token) exec docker exec "$API" python -m app.cli.auth token --email "\$email" --ttl "\$ttl" ;;
  create-local) exec docker exec "$API" python -m app.cli.auth create-local --username "\$username" --email "\$email" ;;
  *) echo "shim make: chưa hỗ trợ target '\$target'" >&2; exit 2 ;;
esac
SHIM
chmod +x shim/make
printf 'API_KEY=%s\nAPI_PORT=%s\nADMIN_EMAILS=%s\n' "$APIKEY" "$PORT" "$SMOKE_EMAIL" > .env

echo "==> smoke"
set +e
PATH="$PWD/shim:$PATH" bash scripts/smoke-test.sh
rc=$?
echo "==> smoke exit=$rc"
exit $rc
REMOTE

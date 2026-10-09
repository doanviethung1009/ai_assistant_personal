#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Deploy một phiên bản image đã build sẵn lên VM này (chạy TRÊN VM, trong thư mục môi trường).
#
#  Dùng:   bash scripts/deploy.sh sha-abc1234 [--skip-smoke]
#          (CI gọi qua SSH; chạy tay được khi cần)
#
#  Vì sao tách script: runbook (docs/deploy-runbook.md) là chuỗi lệnh dài dễ gõ sai thứ tự. Script này
#  đóng gói đúng thứ tự đó và thêm cổng chặn, nhưng KHÔNG thay thế việc hiểu runbook.
#
#  Thứ tự:  pre-check → backup DB → ghi IMAGE_TAG → kéo image → up → migrate → health → smoke.
#  Fail ở health: nếu migration KHÔNG đổi head thì tự lùi về tag cũ (an toàn, không đụng dữ liệu);
#  nếu đã migrate thì DỪNG và in hướng dẫn tay (runbook Case 8), vì lùi schema cần người quyết định.
#
#  Cần: Docker Compose ≥ 2.24, .env có API_KEY..., image tag tồn tại ở GHCR (repo public).
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

TAG="${1:?Thiếu tag image. Dùng: bash scripts/deploy.sh sha-abc1234 [--skip-smoke]}"
SKIP_SMOKE=0; [ "${2:-}" = "--skip-smoke" ] && SKIP_SMOKE=1
[[ "$TAG" =~ ^(sha-[0-9a-f]{7,40}|local)$ ]] || { echo "Tag không hợp lệ: $TAG (cần sha-<hex> hoặc local)" >&2; exit 1; }

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Thiếu .env (chạy: make env)" >&2; exit 1; }
PC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
ENVNAME="$(grep -E '^ENVIRONMENT=' .env | cut -d= -f2-)"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "1/7 Pre-check (môi trường: ${ENVNAME:-?}, tag: $TAG)"
avail_pct=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$avail_pct" -lt 80 ] || { echo "Disk đã dùng ${avail_pct}% (>=80%), dừng." >&2; exit 1; }
ver="$(docker compose version --short)"
[ "$(printf '%s\n2.24\n' "$ver" | sort -V | head -1)" = "2.24" ] || { echo "Compose $ver < 2.24 (cần cho !override)" >&2; exit 1; }
echo "disk dùng ${avail_pct}%, compose $ver — OK"

PREV_TAG="$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2- || true)"; PREV_TAG="${PREV_TAG:-local}"
HEAD_BEFORE="$($PC exec -T api alembic current 2>/dev/null | grep -o '[0-9a-f]\{12\}' | head -1 || true)"
echo "tag hiện tại: $PREV_TAG, alembic head hiện tại: ${HEAD_BEFORE:-<chưa có>}"

say "2/7 Backup database (bắt buộc trước khi migrate)"
if $PC ps --status running postgres 2>/dev/null | grep -q postgres; then
  make backup
  latest="$(ls -t backups/*.sql.gz | head -1)"
  [ -s "$latest" ] || { echo "File backup rỗng: $latest" >&2; exit 1; }
else
  echo "Postgres chưa chạy (deploy lần đầu) — bỏ qua backup"
fi

say "3/7 Ghi IMAGE_TAG=$TAG vào .env"
if grep -q '^IMAGE_TAG=' .env; then sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$TAG|" .env; else echo "IMAGE_TAG=$TAG" >> .env; fi

say "4/7 Kéo image"
if [ "$TAG" != "local" ]; then $PC pull api web; fi

say "5/7 Up"
$PC up -d --remove-orphans

say "6/7 Migrate + health"
$PC exec -T api alembic upgrade head
HEAD_AFTER="$($PC exec -T api alembic current 2>/dev/null | grep -o '[0-9a-f]\{12\}' | head -1 || true)"
ok=0
for i in $(seq 1 20); do
  if curl -fsS "http://localhost:${API_PORT:-8000}/health/ready" >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
if [ "$ok" != 1 ]; then
  echo "Health FAIL." >&2
  if [ "$HEAD_BEFORE" = "$HEAD_AFTER" ] && [ "$PREV_TAG" != "$TAG" ]; then
    echo "Migration không đổi head → tự lùi về $PREV_TAG" >&2
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$PREV_TAG|" .env
    $PC up -d
  else
    echo "Schema đã đổi ($HEAD_BEFORE → $HEAD_AFTER): KHÔNG tự lùi. Xem docs/deploy-runbook.md Case 8." >&2
  fi
  exit 1
fi

if [ "$SKIP_SMOKE" = 1 ]; then say "7/7 Smoke: BỎ QUA theo yêu cầu"; else
  say "7/7 Smoke"
  make smoke
fi
say "XONG: $ENVNAME chạy $TAG"

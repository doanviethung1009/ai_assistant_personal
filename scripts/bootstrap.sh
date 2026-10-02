#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Dựng toàn bộ stack từ đầu trên Ubuntu.
#  Chạy được nhiều lần, không phá dữ liệu đã có.
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

cd "$(dirname "$0")/.."

BOLD=$'\033[1m'
DIM=$'\033[2m'
RED=$'\033[31m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RESET=$'\033[0m'

step() { echo ""; echo "${BOLD}==> $1${RESET}"; }
ok() { echo "  ${GREEN}ok${RESET}  $1"; }
warn() { echo "  ${YELLOW}chú ý${RESET}  $1"; }
die() { echo "  ${RED}lỗi${RESET}  $1" >&2; exit 1; }

# ── 1. Kiểm tra môi trường ─────────────────────────────────────────────

step "Kiểm tra môi trường"

command -v docker >/dev/null 2>&1 \
  || die "Chưa có docker. Xem hướng dẫn cài trong README, phần Ubuntu."

docker compose version >/dev/null 2>&1 \
  || die "Chưa có compose plugin. Cài: sudo apt install -y docker-compose-plugin"

if ! docker info >/dev/null 2>&1; then
  echo ""
  echo "  Không kết nối được docker daemon. Hai nguyên nhân thường gặp:"
  echo ""
  echo "    1) Daemon chưa chạy:"
  echo "       sudo systemctl enable --now docker"
  echo ""
  echo "    2) User chưa thuộc group docker:"
  echo "       sudo usermod -aG docker \$USER && newgrp docker"
  echo ""
  die "Sửa xong rồi chạy lại: make bootstrap"
fi

ok "docker $(docker version --format '{{.Server.Version}}')"
ok "compose $(docker compose version --short)"

# ── 2. Chuẩn hoá line ending ───────────────────────────────────────────
# Project này soạn trên Windows. Nếu file mang CRLF thì shell trong
# container sẽ báo lỗi rất khó hiểu.

step "Chuẩn hoá line ending"

crlf_count=0
while IFS= read -r -d '' file; do
  if grep -qU $'\r' "$file" 2>/dev/null; then
    sed -i '' 's/\r$//' "$file"
    crlf_count=$((crlf_count + 1))
  fi
done < <(find scripts apps infra -type f \
  \( -name '*.sh' -o -name '*.py' -o -name '*.yml' -o -name '*.yaml' -o -name 'Dockerfile' \) \
  -print0 2>/dev/null || true)

if [[ $crlf_count -gt 0 ]]; then
  warn "đã đổi $crlf_count file từ CRLF sang LF"
else
  ok "toàn bộ file đã dùng LF"
fi

# ── 3. Cấu hình ────────────────────────────────────────────────────────

step "Cấu hình"

if [[ -f .env ]]; then
  ok ".env đã có, giữ nguyên"
else
  bash scripts/gen-env.sh
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

[[ -n "${API_KEY:-}" && "${API_KEY}" != "CHANGE_ME_GENERATE_A_RANDOM_KEY" ]] \
  || die "API_KEY trong .env chưa được đặt. Chạy: rm .env && make bootstrap"

mkdir -p backups

# ── 4. Build ───────────────────────────────────────────────────────────

step "Build image (lần đầu mất vài phút)"
docker compose build
ok "build xong"

# ── 5. Dựng lớp dữ liệu ────────────────────────────────────────────────

step "Dựng Postgres và Redis"
docker compose up -d postgres redis

printf "  chờ postgres nhận kết nối "
for i in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    echo ""
    ok "postgres sẵn sàng"
    break
  fi
  printf "."
  sleep 2
  [[ $i -eq 60 ]] && { echo ""; die "postgres không lên sau 120 giây. Xem: docker compose logs postgres"; }
done

# ── 6. Migration ───────────────────────────────────────────────────────
# Lần đầu chưa có revision nào. Sinh từ model thay vì viết tay, để schema
# luôn khớp tuyệt đối với app/models.

step "Migration"

shopt -s nullglob
existing=(apps/core/migrations/versions/*.py)
shopt -u nullglob

if [[ ${#existing[@]} -eq 0 ]]; then
  echo "  chưa có revision nào, sinh initial schema từ model"
  # Chạy bằng uid/gid của bạn để file sinh ra không thuộc root
  if ! docker compose run --rm --no-deps --user "$(id -u):$(id -g)" api \
      alembic revision --autogenerate -m "initial schema"; then
    warn "sinh bằng uid hiện tại thất bại, thử lại bằng root"
    docker compose run --rm --no-deps api \
      alembic revision --autogenerate -m "initial schema" \
      || die "Không sinh được migration. Xem: docker compose logs postgres"
    sudo chown -R "$(id -u):$(id -g)" apps/core/migrations/versions 2>/dev/null || true
  fi

  shopt -s nullglob
  created=(apps/core/migrations/versions/*.py)
  shopt -u nullglob
  [[ ${#created[@]} -gt 0 ]] || die "Alembic không tạo ra file revision nào."
  ok "đã sinh $(basename "${created[0]}")"
else
  ok "đã có ${#existing[@]} revision, bỏ qua bước sinh"
fi

# ── 7. Dựng ứng dụng ───────────────────────────────────────────────────
# Container api tự chạy `alembic upgrade head` trước khi start uvicorn.

step "Dựng API (migration được áp khi khởi động)"
docker compose up -d api

API_PORT="${API_PORT:-8000}"
printf "  chờ api trả readiness "
api_ready=0
for i in $(seq 1 60); do
  if curl -fsS "http://localhost:${API_PORT}/health/ready" >/dev/null 2>&1; then
    echo ""
    ok "api sẵn sàng"
    api_ready=1
    break
  fi
  printf "."
  sleep 2
done

if [[ $api_ready -eq 0 ]]; then
  echo ""
  echo ""
  echo "  API không lên. Log 40 dòng cuối:"
  echo "  ${DIM}────────────────────────────────────────${RESET}"
  docker compose logs --tail=40 api || true
  echo "  ${DIM}────────────────────────────────────────${RESET}"
  die "Xem thêm: make logs-api"
fi

step "Dựng Web"
docker compose up -d web

WEB_PORT="${WEB_PORT:-3000}"
printf "  chờ next.js biên dịch "
for i in $(seq 1 90); do
  if curl -fsS -o /dev/null "http://localhost:${WEB_PORT}/" 2>/dev/null; then
    echo ""
    ok "web sẵn sàng"
    break
  fi
  printf "."
  sleep 2
  [[ $i -eq 90 ]] && { echo ""; warn "web chưa phản hồi. Xem: make logs-web"; }
done

# ── 7. Kiểm tra ────────────────────────────────────────────────────────

step "Kiểm tra end-to-end"
if bash scripts/smoke-test.sh; then
  ok "smoke test pass"
else
  warn "smoke test fail, xem chi tiết ở trên"
fi

# ── 8. Tổng kết ────────────────────────────────────────────────────────

cat <<EOF

${BOLD}Xong.${RESET}

  Web        http://localhost:${WEB_PORT}
  API docs   http://localhost:${API_PORT}/docs
  Readiness  http://localhost:${API_PORT}/health/ready

  Lệnh hay dùng:
    make          xem toàn bộ lệnh
    make logs     theo dõi log
    make smoke    kiểm tra lại end-to-end
    make psql     mở psql
    make mon-up   dựng Prometheus + Grafana
    make llm-up   dựng LiteLLM gateway

EOF

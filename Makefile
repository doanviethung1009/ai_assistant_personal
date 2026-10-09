# ═══════════════════════════════════════════════════════════════════════
#  Builder AI Assistant — lệnh vận hành
#
#  Mục đích: mọi thao tác thường dùng đều có một lệnh ngắn, để bạn tự chạy
#  mà không cần nhờ agent mò lệnh. Chạy `make` để xem danh sách.
# ═══════════════════════════════════════════════════════════════════════

SHELL := /bin/bash
.DEFAULT_GOAL := help

DC := docker compose
API := $(DC) exec -T api

.PHONY: help
help: ## Hiện danh sách lệnh
	@echo ""
	@echo "  Builder AI Assistant"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Khởi tạo ───────────────────────────────────────────────────────────

.PHONY: bootstrap
bootstrap: ## Cài từ đầu: sinh .env, build, dựng stack, chạy migration
	@bash scripts/bootstrap.sh

.PHONY: env
env: ## Sinh file .env với khoá ngẫu nhiên (không ghi đè nếu đã có)
	@bash scripts/gen-env.sh

.PHONY: env-fill
env-fill: ## Bổ sung IMPORT_COMMIT_SECRET và INTEGRATION_SECRET_KEY vào .env cũ (không đổi biến đã có)
	@bash scripts/gen-env.sh --fill-missing

# ── Vòng đời stack ─────────────────────────────────────────────────────

.PHONY: up
up: ## Dựng profile core (postgres, redis, api, web)
	$(DC) up -d
	@echo ""
	@echo "  Web   http://localhost:$${WEB_PORT:-3000}"
	@echo "  API   http://localhost:$${API_PORT:-8000}/docs"
	@echo ""

.PHONY: down
down: ## Dừng stack, giữ nguyên dữ liệu
	$(DC) down

.PHONY: restart
restart: ## Khởi động lại api và web
	$(DC) restart api web

.PHONY: use-db
use-db: ## Chuyển web sang DATA_SOURCE=api (Postgres), nguồn dữ liệu thật
	@sed -i '' 's/^DATA_SOURCE=.*/DATA_SOURCE=api/' .env 2>/dev/null \
		|| echo "DATA_SOURCE=api" >> .env
	$(DC) up -d web
	@echo "  Đã đổi sang DATA_SOURCE=api. Dữ liệu nằm trong Postgres."

.PHONY: use-local
use-local: ## Chuyển web sang DATA_SOURCE=file, ghi vào ./data/, không cần Postgres
	@sed -i '' 's/^DATA_SOURCE=.*/DATA_SOURCE=file/' .env 2>/dev/null \
		|| echo "DATA_SOURCE=file" >> .env
	$(DC) up -d web
	@echo "  Đã đổi sang DATA_SOURCE=file. Dữ liệu ghi vào ./data/builder-data.json."
	@echo "  Lưu ý: dữ liệu ở hai nguồn KHÔNG tự đồng bộ. Xem README mục Dữ liệu."

.PHONY: ps
ps: ## Trạng thái container
	$(DC) ps

.PHONY: build
build: ## Build lại image
	$(DC) build

.PHONY: rebuild
rebuild: ## Build lại từ đầu, bỏ cache
	$(DC) build --no-cache

.PHONY: logs
logs: ## Theo dõi log toàn bộ stack
	$(DC) logs -f --tail=100

.PHONY: logs-api
logs-api: ## Theo dõi log của api
	$(DC) logs -f --tail=100 api

.PHONY: logs-web
logs-web: ## Theo dõi log của web
	$(DC) logs -f --tail=100 web

# ── Database ───────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Áp migration lên head
	$(API) alembic upgrade head

.PHONY: migration
migration: ## Sinh migration từ model. Dùng: make migration m="thêm bảng x"
	@test -n "$(m)" || (echo "Thiếu tham số m. Ví dụ: make migration m=\"add notes\"" && exit 1)
	$(DC) run --rm --no-deps --user "$$(id -u):$$(id -g)" api \
		alembic revision --autogenerate -m "$(m)"

.PHONY: migration-init
migration-init: ## Sinh initial schema (chỉ dùng khi migrations/versions còn trống)
	$(DC) up -d postgres
	$(DC) run --rm --no-deps --user "$$(id -u):$$(id -g)" api \
		alembic revision --autogenerate -m "initial schema"
	@ls -1 apps/core/migrations/versions/*.py

.PHONY: downgrade
downgrade: ## Lùi một bước migration
	$(API) alembic downgrade -1

.PHONY: history
history: ## Lịch sử migration
	$(API) alembic history --indicate-current

.PHONY: psql
psql: ## Mở psql vào database chính
	$(DC) exec postgres psql -U $${POSTGRES_USER:-builder} -d $${POSTGRES_DB:-builder_ai}

.PHONY: backup
backup: ## Dump database ra backups/
	@mkdir -p backups
	$(DC) exec -T postgres pg_dump -U $${POSTGRES_USER:-builder} -d $${POSTGRES_DB:-builder_ai} \
		| gzip > backups/builder_ai_$$(date +%Y%m%d_%H%M%S).sql.gz
	@ls -lh backups | tail -n 1

# ── Kiểm tra ───────────────────────────────────────────────────────────

.PHONY: smoke
smoke: ## Kiểm tra end-to-end qua API thật (tạo, sửa, xoá task)
	@bash scripts/smoke-test.sh

.PHONY: test
test: ## pytest backend trên database riêng <POSTGRES_DB>_test (không đụng DB dev)
	@bash scripts/test-backend.sh

.PHONY: purge
purge: ## Dọn task đã quá thời hạn giữ trong thùng rác
	@curl -fsS -X POST -H "X-API-Key: $${API_KEY}" \
		http://localhost:$${API_PORT:-8000}/api/v1/tasks/trash/purge | python3 -m json.tool

.PHONY: trash
trash: ## Xem thùng rác qua API
	@curl -fsS -H "X-API-Key: $${API_KEY}" \
		"http://localhost:$${API_PORT:-8000}/api/v1/tasks/trash?limit=50" | python3 -m json.tool

.PHONY: health
health: ## Gọi readiness probe
	@curl -fsS http://localhost:$${API_PORT:-8000}/health/ready | python3 -m json.tool

.PHONY: pve-check
pve-check: ## Đọc thông tin Proxmox bằng token chỉ đọc (infra/proxmox/.env.pve)
	@bash infra/proxmox/scripts/pve-check.sh

.PHONY: pve-vm
pve-vm: ## Dựng VM môi trường trên Proxmox: make pve-vm ENV=dev|staging|prod [DRY=1]
	@bash infra/proxmox/scripts/pve-vm.sh $(ENV) $(if $(DRY),--dry-run,)

.PHONY: pve-config
pve-config: ## Cấu hình VM bằng Ansible: make pve-config ENV=dev|staging|prod [CHECK=1 chỉ xem thay đổi]
	@cd infra/proxmox/ansible && ANSIBLE_COLLECTIONS_PATH=collections ../.venv/bin/ansible-playbook site.yml -e target=$(ENV) $(if $(CHECK),--check --diff,)

.PHONY: lint
lint: ## Ruff cho backend, tsc cho frontend
	$(API) ruff check app migrations tests
	$(DC) exec -T web npx tsc --noEmit

.PHONY: gen-types
gen-types: ## Sinh lại apps/web/lib/generated/openapi.d.ts từ /openapi.json của api đang chạy
	$(DC) exec -T web npm run gen:types
	@echo "Đã sinh lại openapi.d.ts. Nếu tsc báo lỗi, kiểm tra lib/types.ts có cần ép lại field nào không."

.PHONY: fmt
fmt: ## Tự sửa lỗi format backend
	$(API) ruff check --fix app migrations tests
	$(API) ruff format app migrations tests

.PHONY: lock
lock: ## Sinh lại uv.lock cho backend (chạy sau khi sửa pyproject.toml)
	$(API) uv lock
	@echo "uv.lock đã cập nhật. Chạy 'make build' để image dùng lock mới."

# ── Shell ──────────────────────────────────────────────────────────────

.PHONY: web-local
web-local: ## Chạy riêng web app trên host, lưu vào file JSON, không cần Docker
	cd apps/web && npm install --no-audit --no-fund && DATA_SOURCE=file npm run dev

.PHONY: web-demo
web-demo: ## Chạy riêng web app với dữ liệu mẫu trong RAM, không ghi đĩa
	cd apps/web && npm install --no-audit --no-fund && DATA_SOURCE=memory npm run dev

.PHONY: export
export: ## Tải JSON và CSV từ web app đang chạy về thư mục backups/
	@mkdir -p backups
	@curl -fsS "http://localhost:$${WEB_PORT:-3000}/api/export?format=json" \
		-o "backups/builder-data-$$(date +%Y%m%d_%H%M%S).json"
	@curl -fsS "http://localhost:$${WEB_PORT:-3000}/api/export?format=csv&entity=tasks" \
		-o "backups/builder-tasks-$$(date +%Y%m%d_%H%M%S).csv"
	@ls -lh backups | tail -n 2

.PHONY: sh-api
sh-api: ## Vào shell của container api
	$(DC) exec api bash

.PHONY: sh-web
sh-web: ## Vào shell của container web
	$(DC) exec web sh

# ── Profile phụ ────────────────────────────────────────────────────────

.PHONY: llm-up
llm-up: ## Dựng LiteLLM gateway
	$(DC) --profile llm up -d litellm
	@echo "  LiteLLM  http://localhost:$${LITELLM_PORT:-4000}"

.PHONY: llm-spend
llm-spend: ## Xem chi tiêu LLM đã ghi nhận
	@curl -fsS -H "Authorization: Bearer $${LITELLM_MASTER_KEY}" \
		http://localhost:$${LITELLM_PORT:-4000}/spend/logs | python3 -m json.tool

.PHONY: mon-up
mon-up: ## Dựng Prometheus, Grafana, blackbox và các exporter
	$(DC) --profile monitoring up -d
	@echo "  Prometheus  http://localhost:$${PROMETHEUS_PORT:-9090}"
	@echo "  Grafana     http://localhost:$${GRAFANA_PORT:-3001} (admin)"

.PHONY: mon-down
mon-down: ## Dừng riêng phần monitoring
	$(DC) --profile monitoring down

.PHONY: all-up
all-up: ## Dựng cả ba profile
	$(DC) --profile llm --profile monitoring up -d

# ── Chia sẻ trong LAN ────────────────────────────────────────────────────

.PHONY: lan-up
lan-up: ## Mở web ra LAN để máy khác trong nhà dùng chung. Đọc README trước khi bật
	$(DC) -f docker-compose.yml -f docker-compose.lan.yml up -d
	@echo ""
	@echo "  Web mở ra LAN. Tìm IP máy này: ip addr | grep 'inet ' (Linux) hoặc ipconfig (Windows)"
	@echo "  Máy khác truy cập: http://<IP-may-nay>:$${WEB_PORT:-3000}"
	@echo "  CẢNH BÁO: không có đăng nhập. Chỉ dùng trên mạng tin tưởng toàn bộ thiết bị."
	@echo ""

.PHONY: lan-down
lan-down: ## Đóng lại, web chỉ còn truy cập từ 127.0.0.1
	$(DC) up -d web
	@echo "  Đã đóng. Web chỉ còn trả lời ở 127.0.0.1:$${WEB_PORT:-3000}."

# ── Production ─────────────────────────────────────────────────────────

.PHONY: prod-build
prod-build: ## Build image target prod
	$(DC) -f docker-compose.yml -f docker-compose.prod.yml build

.PHONY: prod-up
prod-up: ## Dựng stack ở chế độ prod (không bind mount, không reload)
	$(DC) -f docker-compose.yml -f docker-compose.prod.yml up -d

.PHONY: prod-logs
prod-logs: ## Log của stack prod
	$(DC) -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100

# ── Git flow: main → uat → prod ────────────────────────────────────────
#
#  Nhánh môi trường chỉ đi lên bằng fast-forward. Chi tiết và lý do:
#  docs/git-workflow.md

.PHONY: git-status
git-status: ## Xem main, uat, prod đang lệch nhau thế nào
	@bash scripts/release.sh status

.PHONY: promote-uat
promote-uat: ## Đưa main lên uat rồi push (fast-forward)
	@bash scripts/release.sh uat

.PHONY: promote-prod
promote-prod: ## Go-live: uat lên prod kèm tag. Dùng: make promote-prod v=1.0.0
	@test -n "$(v)" || (echo "Thiếu tham số v. Ví dụ: make promote-prod v=1.0.0" && exit 1)
	@bash scripts/release.sh prod "$(v)"

.PHONY: rollback-info
rollback-info: ## In hướng dẫn lùi production về tag trước
	@bash scripts/release.sh rollback

.PHONY: git-init-branches
git-init-branches: ## Tạo nhánh uat và prod từ main (chỉ chạy một lần)
	@bash scripts/init-branches.sh

.PHONY: install-hooks
install-hooks: ## Cài hook kiểm tra message commit (Conventional Commits)
	@bash scripts/install-hooks.sh

.PHONY: changelog
changelog: ## Sinh lại CHANGELOG.md từ git log. Xem trước: make changelog-preview
	@bash scripts/changelog.sh --write

.PHONY: changelog-preview
changelog-preview: ## In changelog ra màn hình, không ghi file
	@bash scripts/changelog.sh

# ── Dọn dẹp ────────────────────────────────────────────────────────────

.PHONY: fix-eol
fix-eol: ## Đổi CRLF sang LF (chạy nếu gặp lỗi 'bad interpreter' sau khi copy từ Windows)
	@find scripts apps infra -type f \
		\( -name '*.sh' -o -name '*.py' -o -name '*.yml' -o -name '*.yaml' -o -name 'Dockerfile' \) \
		-exec sed -i '' 's/\r$$//' {} +
	@sed -i '' 's/\r$$//' Makefile docker-compose.yml docker-compose.prod.yml 2>/dev/null || true
	@echo "Đã chuẩn hoá line ending sang LF."

.PHONY: clean
clean: ## Xoá file tạm, giữ nguyên dữ liệu
	@rm -f *.log
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Đã dọn file tạm."

.PHONY: reset
reset: ## XOÁ TOÀN BỘ DỮ LIỆU rồi dựng lại từ đầu
	@echo ""
	@echo "  Lệnh này xoá vĩnh viễn volume postgres, redis, grafana."
	@echo "  Toàn bộ task và project sẽ mất."
	@echo ""
	@read -p "  Gõ 'xoa' để xác nhận: " confirm && [ "$$confirm" = "xoa" ] || (echo "  Đã huỷ." && exit 1)
	$(DC) --profile llm --profile monitoring down -v
	$(MAKE) up
	@echo "  Đã dựng lại. Migration chạy tự động khi api khởi động."

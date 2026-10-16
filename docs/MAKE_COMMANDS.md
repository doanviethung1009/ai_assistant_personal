# Lệnh `make` — cấu hình và cách dùng

Mọi thao tác vận hành thường dùng đều có một target `make`. Mục đích: tự chạy được, không phải nhờ agent mò lệnh `docker compose` dài.

## 1. Cấu hình nằm ở đâu

| File | Vai trò |
|---|---|
| `Makefile` (thư mục gốc) | Nơi **định nghĩa duy nhất** của mọi lệnh. Mỗi target có `.PHONY` và một comment `## mô tả`. |
| `scripts/*.sh` | Logic dài được tách ra script: `bootstrap.sh`, `gen-env.sh`, `smoke-test.sh`, `test-backend.sh`. Makefile chỉ gọi `bash scripts/...`. |
| `.env` | Biến môi trường cho Docker Compose và các lệnh (`API_KEY`, `POSTGRES_*`, `API_PORT`, `EXPOSE_LAN`...). Không commit. |
| `.env.example` | Mẫu của `.env`, được commit. `make env` sao chép từ file này. |
| `.env.worktree` | Chỉ có trong worktree của task: tên compose project, DB, cổng riêng. Makefile tự nạp và export, đè lên `.env`. |

Cơ chế đáng biết trong `Makefile`:

- **`make` không đối số = `make help`** (`.DEFAULT_GOAL := help`). `help` tự quét mọi dòng `target: ## mô tả` rồi in bảng, nên thêm target mới chỉ cần viết đúng cú pháp `## mô tả` là nó tự hiện (tên target chỉ gồm chữ, `_`, `-`).
- **Biến `DC`** là lệnh compose. Checkout chính: `docker compose`. Worktree (có `.env.worktree`): `docker compose -p <project> -f docker-compose.yml -f docker-compose.worktree.yml`. Vì vậy cùng một lệnh `make up` chạy đúng stack riêng của task mà không đụng stack chính.
- **Biến `API`** = `$(DC) exec -T api`, dùng để chạy lệnh bên trong container api (alembic, ruff, CLI auth).
- **Tham số** truyền dạng `make <target> BIEN=giatri` (ví dụ `m=`, `EMAIL=`, `ENV=`). Biến có `?=` (như `DEVVM_HOST`) có giá trị mặc định và ghi đè được.

## 2. Cách dùng

```bash
make            # xem danh sách lệnh + mô tả (cùng là make help)
make <target>   # chạy một lệnh
```

Không chạy `npm run dev` hay `uvicorn` trực tiếp trên host: web và api đã chạy trong container có hot reload.

## 3. Thiết lập `.env` — `make env` và `.env.example`

Câu hỏi hay gặp: **không có** target tên `env.example`. `.env.example` là một **file mẫu**, còn lệnh liên quan là:

| Lệnh | Việc làm |
|---|---|
| `make env` | Sao chép `.env.example` thành `.env` rồi điền khoá ngẫu nhiên (`POSTGRES_PASSWORD`, `API_KEY`, `LITELLM_*`, `GRAFANA_ADMIN_PASSWORD`, `INTEGRATION_SECRET_KEY`, `CORE_JWT_SECRET`, `AUTH_SECRET`), chmod 600. **Không ghi đè** nếu `.env` đã có. Cần `openssl`. |
| `make env-fill` | Dành cho `.env` cũ: chỉ bổ sung `INTEGRATION_SECRET_KEY`, `CORE_JWT_SECRET`, `AUTH_SECRET` nếu thiếu hoặc rỗng, không đổi biến đã có. Sau đó `make up` để api nhận biến mới. |
| `make bootstrap` | Cài từ đầu: sinh `.env`, build, dựng stack, chạy migration (gọi `scripts/bootstrap.sh`). |

Muốn sinh lại toàn bộ khoá: `mv .env .env.bak && bash scripts/gen-env.sh`. Lưu ý `INTEGRATION_SECRET_KEY` mất thì phải nhập lại token Jira, nên sao lưu `.env`.

Thêm biến mới vào hệ thống: sửa `.env.example` (nguồn mẫu). Nếu biến là khoá bí mật cần sinh ngẫu nhiên thì thêm một dòng `set_var` (và `fill_if_missing`) trong `scripts/gen-env.sh`.

## 4. Danh mục lệnh theo nhóm

**Khởi tạo & vòng đời stack**

| Lệnh | Việc |
|---|---|
| `make bootstrap` | Cài từ đầu (env + build + up + migrate) |
| `make up` | Dựng profile core (postgres, redis, api, web). `EXPOSE_LAN=true` trong `.env` thì mở web ra LAN |
| `make up-backend` | Chỉ postgres, redis, api, chờ healthcheck (dùng cho worktree task) |
| `make down` / `make restart` | Dừng (giữ dữ liệu) / khởi động lại api và web |
| `make ps`, `make logs`, `make logs-api`, `make logs-web` | Trạng thái và log |
| `make build` / `make rebuild` | Build image / build bỏ cache |
| `make use-db` / `make use-local` | Web dùng Postgres (`DATA_SOURCE=api`) / file JSON trong `./data/` |
| `make sh-api` / `make sh-web` | Vào shell container |
| `make clean` | Xoá file tạm, giữ dữ liệu |
| `make reset` | **XOÁ toàn bộ dữ liệu** rồi dựng lại (hỏi xác nhận gõ `xoa`) |

**Database**

| Lệnh | Việc |
|---|---|
| `make migration m="mô tả"` | Sinh migration từ model (bắt buộc có `m`) |
| `make migrate` | Áp migration lên head |
| `make downgrade` / `make history` | Lùi một bước / xem lịch sử |
| `make migration-init` | Sinh initial schema (chỉ khi `versions/` trống) |
| `make psql` | Mở psql vào DB chính |
| `make backup` | Dump DB ra `backups/` (gzip) |

**Chất lượng & kiểm tra**

| Lệnh | Việc |
|---|---|
| `make lint` | Ruff (backend) + tsc (frontend) |
| `make fmt` | Tự sửa format backend |
| `make test` | pytest trên DB riêng `<POSTGRES_DB>_test` |
| `make smoke` | E2E qua API thật |
| `make health` | Gọi `/health/ready` |
| `make gen-types` | Sinh lại `openapi.d.ts` từ api đang chạy |
| `make lock` | Sinh lại `uv.lock` sau khi sửa `pyproject.toml` |

**Dữ liệu & web chạy riêng**: `make export`, `make web-local`, `make web-demo`, `make purge`, `make trash`.

**LLM, monitoring, LAN, prod**: `make llm-up`, `make llm-spend`, `make mon-up`, `make mon-down`, `make all-up`, `make lan-up`, `make lan-down`, `make prod-build`, `make prod-up`, `make prod-logs`.

**Git & release**: `make install-hooks` (hook Conventional Commits, chạy một lần), `make changelog`, `make changelog-preview`, `make git-status`, `make promote-uat`, `make promote-prod v=1.0.0`, `make rollback-info`, `make git-init-branches`, `make fix-eol`.

**Proxmox**: `make pve-check`, `make pve-vm ENV=dev|staging|prod [DRY=1]`, `make pve-config ENV=... [CHECK=1]`. Xem `PROXMOX_OPERATIONS.md`.

**Tài khoản đăng nhập** (chạy trong container api, nguồn `app/cli/auth.py`): `make auth-create-local USERNAME= EMAIL= [ROLE=] [NAME=]`, `auth-reset-password`, `auth-unlock`, `auth-invite`, `auth-revoke`, `auth-disable`, `auth-enable`, `auth-token`, `auth-alias`, `auth-alias-set`, `auth-alias-remove`, `auth-bootstrap OWNER=...`. Tham số bắt buộc ghi trong mô tả của từng lệnh (`make help`).

**Trỏ web local vào VM dev**: `make devvm-tunnel`, `make devvm-web`, `make devvm-down` (host/khoá SSH ghi đè qua `DEVVM_HOST`, `DEVVM_KEY`, `DEVVM_PORT`).

> Danh sách trên là ảnh chụp lúc viết. Nguồn đúng nhất luôn là `make help` / `Makefile`.

## 5. Thêm một lệnh mới

```make
.PHONY: ten-lenh
ten-lenh: ## Mô tả ngắn, hiện trong make help. Dùng: make ten-lenh x=1
	@test -n "$(x)" || (echo "Thiếu x" && exit 1)   # kiểm tra tham số bắt buộc
	$(DC) exec -T api ...                           # dùng $(DC)/$(API) để chạy đúng cả trong worktree
```

Logic quá vài dòng thì đưa vào `scripts/` và để Makefile gọi `bash scripts/ten.sh`. `Makefile` là file dùng chung: sửa phải nằm trong phạm vi task (xem `CLAUDE.md`).

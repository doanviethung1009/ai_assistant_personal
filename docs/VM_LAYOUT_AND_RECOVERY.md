# Bản đồ thư mục trên VM và khởi động lại sau khi reset/down

Cập nhật: 2026-10-10. Dành cho người vào VM kiểm tra hoặc cứu hệ thống. Số liệu đo trên VM dev `ai-dev-01`
(192.168.100.201). Danh sách VM, IP, vai trò: [PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md) mục 1; cách SSH: mục 1b
cùng file và [PROXMOX_ACCESS.md](PROXMOX_ACCESS.md); dựng VM: [PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md); container và
image: [DOCKER_ARCHITECTURE.md](DOCKER_ARCHITECTURE.md).

## 1. Root folder của hệ thống trên VM

Mỗi môi trường có **một thư mục riêng** dưới `/srv/builder-ai/`, là bản checkout của repo, chạy bằng Docker Compose.

| Môi trường | VM | Thư mục | Nhánh |
|---|---|---|---|
| dev | `ai-dev-01` (201) | `/srv/builder-ai/dev` | `main` (hot reload) |
| staging | `ai-stg-01` (202) | `/srv/builder-ai/staging` | `uat` |
| prod | `ai-prod-01` (203) | `/srv/builder-ai/prod` | `prod` |

```bash
ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.201
cd /srv/builder-ai/dev
```

Bên trong (VM dev, đo ngày 2026-10-10):

| Mục | Ý nghĩa |
|---|---|
| `apps/`, `docs/`, `infra/`, `scripts/` | Mã nguồn như repo |
| `docker-compose.yml` | Stack mặc định (profile `core`: postgres, redis, api, web) |
| `docker-compose.prod.yml`, `docker-compose.lan.yml` | Lớp phủ cho prod (không bind mount) và mở web ra LAN |
| `Makefile` | Mọi thao tác đi qua `make`; chạy `make` để xem danh sách. Không tự gõ `docker compose` dài |
| `.env` | Cấu hình và secret của môi trường này, quyền `600`, **không có trong git**. Mỗi môi trường khoá riêng |
| `.env.example` | Mẫu, an toàn để đọc |
| `data/` | Thuộc `root` (không thuộc `deploy`); dùng cho chế độ lưu file, hiện không phải đường chạy chính (`DATA_SOURCE=api`) |

Ngoài `/srv/builder-ai`, trong `~` của user `deploy` có thể còn `auth-test/` và `rptest/`: đó là **bản rsync tạm** của
các lượt test backend (mục 5), không thuộc hệ thống chính, xoá được khi không còn dùng.

## 2. Container, cổng và dữ liệu

Stack `core` của VM dev (tên project compose `builder-dev`):

| Container | Cổng host | Chức năng |
|---|---|---|
| `builder-api` | `127.0.0.1:8000` | FastAPI; lúc khởi động tự chạy `alembic upgrade head` |
| `builder-web` | `0.0.0.0:3000` (mở LAN khi `EXPOSE_LAN=true`) | Next.js |
| `builder-postgres` | `127.0.0.1:5432` | Postgres 17 + pgvector |
| `builder-redis` | `127.0.0.1:6379` | Redis (rate limit, cache) |

Dữ liệu nằm trong **named volume**, không nằm trong thư mục repo: `builder-dev_postgres_data`, `builder-dev_redis_data`
(cùng hai volume cache của web). Hệ quả: xoá thư mục `/srv/builder-ai/dev` **không** mất DB, nhưng `docker compose down -v`
hoặc `docker volume rm` thì mất. `make down` an toàn (giữ dữ liệu).

Mọi service có `restart: unless-stopped` và Docker bật cùng hệ điều hành (`systemctl is-enabled docker` = enabled), nên
sau khi VM bật lại, **stack tự lên** mà không cần gõ lệnh.

## 3. Sau khi VM bị reset hoặc down: checklist

Làm theo thứ tự, dừng ở bước đầu tiên thấy bất thường.

1. **VM sống chưa?** `ping 192.168.100.201`, rồi SSH (lệnh ở mục 1). Không SSH được: xem mục 4.
2. **Chờ khoảng 1 phút** cho Docker và các container. Lúc vừa lên, api có thể ghi vài lỗi
   `Temporary failure in name resolution` / `rate_limit_redis_error` rồi tự hết (DNS nội bộ của Docker chưa sẵn). Đó **không
   phải** bug.
3. **Xem trạng thái:** `cd /srv/builder-ai/dev && make ps`. Cả bốn container phải `Up`, postgres/redis/api `(healthy)`.
4. **Kiểm sức khoẻ:** `make health` (gọi `/health/ready`). Trả OK nghĩa là api nối được Postgres và Redis.
5. **Container nào không lên:** `make logs-api` hoặc `make logs-web`; thử `make up` (idempotent).
6. **Migration:** api tự `alembic upgrade head` khi khởi động. Chỉ chạy `make migrate` tay khi log báo lệch phiên bản.
7. **Máy local dùng API của VM dev?** Tunnel SSH chết cùng VM. Mở lại từ máy local, trong thư mục repo:

   ```bash
   make devvm-tunnel   # localhost:8001 -> API VM dev
   make devvm-web      # (tuỳ chọn) chạy web local trỏ vào API VM; tắt next dev đang chạy ở :3000 trước
   make devvm-down     # đóng tunnel
   ```

   Triệu chứng tunnel/API chết: trang của web local **treo ở trạng thái pending** (request `…?_rsc=` không bao giờ xong),
   hoặc báo "Core API trả về 500".
8. **Dọn đồ test sót** (mục 5) nếu lượt test bị cắt ngang.

## 4. Khi SSH không vào được hoặc VM quá chậm

Dấu hiệu: `ping` bình thường nhưng SSH báo `Connection timed out during banner exchange`, web và API treo. Nguyên nhân đã
gặp (2026-10-10): **hết RAM** — VM dev chỉ có **~2.4 GB**, khi vừa chạy stack dev vừa build image Docker và chạy Postgres tạm
cho test thì cả máy gần như đứng.

- Đợi vài phút nếu có lượt build/test đang chạy; nếu không hồi, **reset VM** từ node Proxmox: giao diện web
  (`https://192.168.100.252:8006` → VM 201 → Reset) hoặc trên node `qm reset 201`. Cần quyền `root@pam` của chủ hạ tầng
  (agent AI không có). `qm shutdown 201` êm hơn nếu máy còn phản hồi; `qm stop` chỉ khi treo cứng.
- VM tự bật lại ứng dụng nhờ `restart: unless-stopped`; sau đó làm mục 3.
- VM có `onboot=1`; nếu sau khi **node** reboot mà VM không tự lên: `qm config 201 | grep onboot`, đặt `qm set 201 --onboot 1`.

## 5. Chạy test backend trên VM mà không làm sập nó

Máy local không có Docker nên test backend chạy trên VM bằng `scripts/patches/dev-vm-backend-test.sh` (rsync mã nguồn
sang `~/auth-test/core`, Postgres tạm trên tmpfs, network riêng, **không đụng stack dev**).

- **Chỉ một lượt test tại một thời điểm.** Hai lượt cùng lúc (hoặc cộng thêm build image) là đủ làm VM 2.4 GB treo.
- Kiểm trước khi chạy: `docker ps --format '{{.Names}}'` không có container `authtest-*` / `rptest-*` đang chạy.
- Lượt test bị cắt giữa chừng có thể để lại container/network tạm. Dọn **đúng tên của mình**, không động vào `builder-*`:

  ```bash
  docker rm -f authtest-pg authtest-api rptest-pg rptest-api 2>/dev/null
  docker network rm authtest-net rptest-net 2>/dev/null
  ```
- Ghi chú đã biết về script (chưa sửa): `.dockerignore` loại thư mục `tests/` nên `ruff` trong image không thấy test;
  `ENVIRONMENT=test` không hợp lệ (chỉ nhận `development|staging|production`); image thiếu `pyjwt` cho epic đăng nhập.

## 6. Đồng bộ Jira trên môi trường DEV cần quyền gì

Nút "Cào ngay" (chế độ api) gọi `POST /api/v1/integrations/{id}/sync`, do core kiểm quyền theo role: cần tài khoản
**admin** (email nằm trong `ADMIN_EMAILS`). Không còn mật khẩu nhập; biến `IMPORT_COMMIT_SECRET` đã bỏ, nếu còn trong `.env`
của VM thì xoá đi (core chỉ ghi cảnh báo). Token Jira được mã hoá Fernet bằng `INTEGRATION_SECRET_KEY` trong `.env`:
mất khoá này thì phải nhập lại mọi token.

## 7. Sự cố tham khảo (2026-10-10)

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tab Data báo "Core API trả về 500" | VM quá tải RAM (test + stack), API không phản hồi; sau reset còn lỗi DNS thoáng qua | Mục 4, rồi mục 3 |
| Trang web local pending mãi | Tunnel `localhost:8001` chết cùng VM | `make devvm-tunnel` |
| Cào Jira trả 401/403 | Chưa đăng nhập, hoặc tài khoản không phải admin | Mục 6 |
| SSH "banner exchange" timeout | VM hết RAM | Mục 4 |

# Spec: Quy trình dựng VM trên Proxmox và deploy theo runbook (dev / staging / prod)

- Trạng thái: DRAFT (User đã chốt Q2–Q5 ngày 2026-10-09; còn Q1 và Q6 ở mục 7)
- Tác giả: Claude (orchestrator, theo vai trò architect)

## 1. Bối cảnh & phạm vi

**Vấn đề.** Hiện chưa có quy trình lặp lại được để dựng máy chạy stack Docker Compose.
`docs/deploy-runbook.md` mô tả bước chạy trên server nhưng giả định máy đã có sẵn.
Cần một cách dựng VM từ Proxmox rồi chạy đúng runbook đó, cho 3 môi trường.

**Hạ tầng đã xác minh (2026-10-09, từ máy dev 192.168.100.75, không cần đăng nhập):**

| Mục | Kết quả |
|---|---|
| Ping 192.168.100.252 | thông, ~9 ms |
| Cổng 8006 (web/API) | mở, giao diện "Proxmox Virtual Environment" |
| Cổng 22 (SSH) | mở, OpenSSH 10.0 trên Debian 13 (trixie) → suy ra PVE 9.x |
| Chứng chỉ TLS | tự ký bởi PVE Cluster Manager CA, CN `isec.dbahomeslab.com`, hạn 2028-02-29 |
| Fingerprint SHA-256 | `A3:33:33:B3:90:3C:34:10:88:85:25:3B:1B:19:61:1B:EB:71:72:61:D0:7A:1C:09:85:F7:30:EE:8C:D2:12:AE` |
| Node | 1 node `isec`, PVE 9.1.11, 6 nhân, RAM 15.5 GB (đang dùng 10.0 GB), swap 8 GB |
| Storage | `local-lvm` (lvmthin, trống 756/794 GB, chứa disk VM); `local` (dir, trống 80/94 GB, chứa iso/snippets/backup) |
| Mạng | một bridge `vmbr0` 192.168.100.252/24, gw 192.168.100.1; không có VLAN riêng |
| VM đang chạy (không thuộc dự án này) | 100 `isec-vpn-gateway` 2 GB, 140 `agent-hub` 6 GB (dùng thực ~3.5), 150 `jump-host-hub` 2 GB |
| Template có sẵn | **9000 `ubuntu-2404-tmpl`** (Ubuntu 24.04 cloud-init, guest agent bật, 2 vCPU/2 GB, disk 3.5 GB) → dùng lại, không tạo mới |

Fingerprint dùng để ghim TLS khi gọi API, không tắt kiểm tra chứng chỉ.

**In-scope**
- VM template cloud-init (Debian 13 hoặc Ubuntu 24.04) dùng chung.
- 3 VM: `dev`, `staging`, `prod`, cấu hình bằng Ansible.
- Runbook thực thi được: `make pve-*` và `make deploy ENV=...` bọc lại các target `make prod-*` đã có.
- Backup, snapshot trước migrate, rollback.
- API token Proxmox quyền tối thiểu.

**Out-of-scope**
- Proxmox cluster/HA, Ceph, live migration.
- Terraform (để giai đoạn sau, mục 8).
- CI/CD tự động deploy prod.
- Đổi code `apps/core`, `apps/web`. Không có thay đổi DB, API hay Web.

## 2. Thay đổi dữ liệu
Không có. Không migration.

## 3. API contract
Không đổi API của sản phẩm. Phía Proxmox chỉ dùng API sẵn có (`/api2/json`), do script gọi, xem mục 4.

## 4. Thiết kế

### 4.1 Sơ đồ môi trường

| Môi trường | Nhánh git | `ENVIRONMENT` | VM | vCPU / RAM / disk (đề xuất) | Duyệt người |
|---|---|---|---|---|---|
| dev | `main` | `development` | máy cá nhân (`make dev`); IP .201 dự trữ | — | không |
| staging | `uat` | `staging` | `ai-stg-01` (.202) | 2 / 4 GB / 40 GB | không |
| prod | `prod` | `production` | `ai-prod-01` (.203) | 2 / 6 GB / 60 GB + disk dữ liệu 40 GB | **bắt buộc** |
| runner CI | — | — | LXC `ai-ci-01` (.204) | 1 / 1 GB / 10 GB | — |

"staging" = nhánh `uat` trong `docs/git-workflow.md` (giữ nguyên tên nhánh, không đổi mô hình git).
Cấu hình mỗi VM lấy từ `.env` riêng, mỗi VM có khoá/secret khác nhau (đã nêu ở runbook Case 4).

**RAM thực tế (đo 2026-10-09):** node 15.5 GB, đã dùng 10.0 GB bởi 3 VM có sẵn + host. Còn trống ~5.5 GB, an toàn chỉ ~3.5 GB nếu 3 VM cũ dùng hết RAM đã cấp. Kế hoạch staging 4 + prod 6 + runner 1 = 11 GB **không vừa**. Phải chọn một hướng ở Q7 trước khi dựng VM. Không overcommit RAM cho prod.

### 4.2 Quy trình dựng VM (làm một lần, rồi lặp lại cho mỗi VM)

1. **Template** (`make pve-template`): tải cloud image, tạo VM id 9000, bật `qemu-guest-agent`, cloud-init, chuyển thành template. Chạy trên node bằng SSH.
2. **Clone** (`make pve-vm ENV=staging`): `qm clone` từ 9000 → đặt tên, id, IP tĩnh, SSH key, user qua cloud-init → start → chờ guest agent báo IP.
3. **Cấu hình** (`make pve-config ENV=staging`): Ansible cài Docker, `ufw` (chỉ mở 22, 80/443 hoặc cổng web), tắt SSH mật khẩu và root, đồng bộ giờ, tạo `/srv/builder-ai/<env>`, clone repo đúng nhánh.
4. Bước 1–3 phải **idempotent**: chạy lại không phá VM đang có.

### 4.3 Runbook deploy (bọc runbook sẵn có)

`make deploy ENV=<env>` chạy qua SSH trong VM, theo thứ tự (map vào Case 2/3 của `deploy-runbook.md`):

| # | Bước | Lệnh trong VM | Cổng chặn |
|---|---|---|---|
| 1 | Pre-check | `git status` sạch, disk còn >20%, `docker compose version` ≥ 2.24 | dừng nếu fail |
| 2 | Snapshot VM (staging, prod) | `qm snapshot <id> pre-<sha>` trên node | prod: người duyệt trước |
| 3 | Backup DB | `make backup`, kiểm file không rỗng | bắt buộc nếu có migration |
| 4 | Lấy image | `IMAGE_TAG=sha-<7> docker compose pull` (cần compose đã sửa, mục 4.6) | tag phải tồn tại ở GHCR |
| 5 | Up | `make prod-up` với `IMAGE_TAG` mới | |
| 6 | Migrate | `make migrate` | |
| 7 | Kiểm tra | `make health && make smoke` | fail → bước 8 |
| 8 | Rollback | Case 7/8 của runbook; revert snapshot chỉ khi hỏng cả DB | |
| 9 | Ghi nhận | in SHA/tag đã deploy; orchestrator cập nhật `docs/AI_HANDOFF_STATE.md` | |

Dev dùng `make dev` (hot reload), không áp bước 2–3.

### 4.4 Bảo mật

- Tạo user `deploy@pve` + **API token** `deploy@pve!automation` (không dùng `root@pam`), role tuỳ chỉnh chỉ có: `VM.Clone`, `VM.Allocate`, `VM.Config.*`, `VM.PowerMgmt`, `VM.Snapshot`, `VM.Audit`, `Datastore.AllocateSpace`, `SDN.Use`, trên pool `ai-assistant`.
- Agent AI chỉ dùng token `PVEAuditor` (đọc) cho healthcheck. Tạo/xoá VM do người chạy.
- Secret nằm ở `infra/proxmox/.env.pve` (gitignore), không commit, không dán vào chat.
- Ghim fingerprint TLS ở mục 1 (`curl --pinnedpubkey`/`verify_ssl` + fingerprint), không `-k`.
- Prod đặt VLAN/bridge riêng nếu node hỗ trợ; cổng 8006 chỉ cho dải quản trị.
- Nội dung từ nguồn ngoài (log, Jira) vẫn là untrusted, không đổi.

### 4.5 Backup & giám sát

- Giai đoạn 1: `vzdump` hằng đêm (prod), giữ 7 bản, cùng `make backup` (pg_dump) copy ra ngoài VM.
- Giai đoạn 2: Proxmox Backup Server khi có máy thứ hai.
- Giám sát: `prometheus-pve-exporter` vào profile `monitoring` sẵn có.

### 4.6 Lấy code & image: CHỐT phương án B (registry + CI), User chọn 2026-10-09

Build image **một lần** trong CI, gắn tag là commit SHA, đẩy lên GHCR. VM chỉ `docker pull`.
Prod chạy đúng image (cùng digest) đã qua staging. Rollback = đổi tag về SHA cũ, không cần build lại.

Thay đổi phải làm (giai đoạn 2):
- `docker-compose.prod.yml`: thêm `image: ghcr.io/doanviethung1009/ai-assistant-{api,web}:${IMAGE_TAG}` bên cạnh `build:` (dev vẫn build tại chỗ).
- `NEXT_PUBLIC_DISPLAY_TZ` nhúng lúc build (xem `web-conventions.md`): image dùng chung cho cả 3 môi trường nên múi giờ cố định ở build. Hiện cả 3 cùng `Asia/Ho_Chi_Minh` nên chấp nhận được; nếu cần khác nhau phải chuyển sang cấu hình lúc chạy.
- Giữ `make prod-build` làm đường dự phòng khi GHCR/CI hỏng.

### 4.7 CI/CD (mở rộng `.github/workflows/ci.yml`)

| Sự kiện | Việc | Nơi chạy |
|---|---|---|
| PR | `ci.yml` hiện có: ruff, alembic check, pytest, tsc, audit | GitHub-hosted |
| push `main` | test → build 2 image → quét lỗ hổng (Trivy) → push GHCR tag `sha-<7>` | GitHub-hosted |
| push `uat` (fast-forward từ main) | deploy staging đúng tag SHA của commit đó → `make health`, `make smoke` | runner tự host |
| push `prod` | **chờ người duyệt** (GitHub Environment `production`, required reviewers) → snapshot + backup → deploy → verify | runner tự host |

- Proxmox nằm sau NAT (192.168.100.x), runner của GitHub không với tới. Cần **runner tự host** (LXC `ai-ci-01`, 1 vCPU / 1 GB, IP đề xuất 192.168.100.204) chỉ làm bước deploy, không build. Build vẫn ở GitHub-hosted.
- Runner SSH vào VM bằng key riêng cho từng môi trường; key prod chỉ dùng được trong job của Environment `production`.
- VM kéo image bằng token GHCR chỉ có quyền `read:packages`.
- Mô hình nhánh `main → uat → prod` (fast-forward) giữ nguyên: cùng SHA đi từ staging lên prod, không build lại.

### 4.8 Tab "Hạ tầng / Instance" trên web (ý tưởng của User)

Khả thi, nhưng chia 2 giai đoạn vì xung đột với ràng buộc dự án:

- **Giai đoạn A (làm được ngay, an toàn): chỉ đọc.** Trang liệt kê VM, trạng thái, CPU/RAM, phiên bản (SHA) đang chạy mỗi môi trường, kết quả health. Dữ liệu do **backend** gọi Proxmox bằng token `PVEAuditor` rồi trả về; token không bao giờ xuống browser (đúng quy tắc API key của dự án). Không lưu metrics, query trực tiếp.
- **Giai đoạn B (chờ có đăng nhập/RBAC): nút hành động.** "Deploy phiên bản X lên staging", "Tạo instance mới". Nút **không gọi Proxmox trực tiếp**; nó kích hoạt workflow GitHub (`workflow_dispatch`), nên vẫn đi qua pipeline và bước duyệt của người. Lý do: web hiện không có đăng nhập (`/system` đã cảnh báo ai mở được URL là xem được hết), nếu gắn token ghi vào web thì ai vào LAN cũng tạo/xoá được VM, vi phạm "agent không có standing write access vào production".
- Tạo VM mới qua web = workflow chạy `make pve-vm` với token giới hạn trong pool `ai-assistant`.

## 5. Ownership (không agent nào sửa file của agent khác)

- orchestrator: `docs/specs/proxmox-deploy.md`, `docs/PROXMOX_DEPLOY.md` (khi làm), `apps/web/lib/docs.ts`, `docs/AI_HANDOFF_STATE.md`, `Makefile`
- hạ tầng (không thuộc backend-dev/frontend-dev): `infra/proxmox/` gồm `scripts/*.sh`, `ansible/`, `.env.pve.example`
- backend-dev / frontend-dev: không có phần việc

Theo AGENTS.md mục 3.9: mọi file cấu hình phải có comment từng quyết định và tài liệu giải thích WHY.

## 6. Tiêu chí nghiệm thu (kiểm chứng được)

- [ ] `make pve-check` (chỉ đọc) báo đúng phiên bản PVE, node, RAM/disk trống, storage, bridge
- [ ] `make pve-template` rồi chạy lại lần 2 không lỗi, không tạo trùng
- [ ] `make pve-vm ENV=staging` ra VM có IP đúng, SSH bằng key được, SSH mật khẩu bị từ chối
- [ ] `make pve-config ENV=staging` chạy 2 lần: lần 2 báo `changed=0`
- [ ] `make deploy ENV=staging` xong: `make health` và `make smoke` pass trong VM
- [ ] Cố ý làm `smoke` fail → quy trình dừng, in hướng dẫn rollback
- [ ] Token `PVEAuditor` không tạo/xoá được VM (thử thực tế)
- [ ] Không có secret nào trong `git diff`/`git grep`
- [ ] `make lint` pass, tài liệu đã đăng ký trong `apps/web/lib/docs.ts`

## 7. Rủi ro & câu hỏi cần User chốt

- **Q1 (còn chặn):** thông tin node (RAM, disk, storage, bridge) cần token chỉ đọc. User tạo token `PVEAuditor` và lưu vào `infra/proxmox/.env.pve` (đã được `.gitignore` bao bởi `.env.*`), không dán vào chat.
- **Q2 (chốt):** node có 16 GB RAM. `dev` chạy ở máy cá nhân, VM chỉ gồm staging và prod (+ LXC runner). Ngân sách: staging 4 GB, prod 6 GB, runner 1 GB, host Proxmox ~3 GB.
- **Q3 (chốt):** Ubuntu 24.04 LTS (hỗ trợ đến 2029, khớp README/runbook, cloud image chính thức cho cloud-init).
- **Q4 (chốt):** phương án B, xem 4.6–4.7.
- **Q5 (chốt):** dev `192.168.100.201` (dự trữ, dùng khi cần VM dev), staging `.202`, prod `.203`, runner `.204` (đề xuất), gateway `192.168.100.1`.
- **Q7 (chặn dựng VM):** RAM không đủ cho kế hoạch ban đầu. Chọn một: (a) giảm `agent-hub` 6→4 GB (đang dùng ~3.5 GB), dành 2 GB; (b) staging chỉ bật khi cần (VM tắt không chiếm RAM); (c) hạ cấu hình: prod 3 GB, staging 2 GB, runner 512 MB; (d) kết hợp (b)+(c).
- **Q6 (mới):** repo GitHub đang để private hay public? Quyết định cách VM kéo image GHCR (private cần token `read:packages`).
- **Rủi ro:** môi trường test có thể bị xoá/cài lại, nên mọi thứ phải dựng lại được từ code. Chứng chỉ tự ký sẽ đổi nếu cài lại Proxmox, khi đó phải cập nhật fingerprint.
- **Rủi ro:** snapshot không thay thế backup (nằm cùng storage với VM).

## 8. Lộ trình

1. Giai đoạn 1 (sau khi chốt Q1–Q5): `pve-check`, template, VM `staging`, `make deploy ENV=staging`.
2. Giai đoạn 2: `dev`, `prod` kèm phê duyệt, `vzdump`, exporter giám sát.
3. Giai đoạn 3: Terraform (provider `bpg/proxmox`), registry + CI (phương án B).

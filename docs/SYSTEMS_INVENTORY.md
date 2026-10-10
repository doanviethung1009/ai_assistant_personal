# Hồ sơ các hệ thống (inventory vận hành)

Cập nhật: 2026-10-09. Một nơi duy nhất trả lời: **có những hệ thống nào, chạy ở đâu, cấu hình ra sao, ai/cái gì phụ
thuộc vào nó, cần gì khi vận hành.** Số liệu lấy từ đo thực tế (`make pve-check` và SSH vào VM) ngày 2026-10-09, không phải ước
lượng. Cách truy cập ở [PROXMOX_ACCESS.md](PROXMOX_ACCESS.md); việc hằng ngày ở
[PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md); dựng mới ở [PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md).

## Bản đồ tài liệu: cần gì thì đọc file nào

| Bạn muốn... | Đọc | Mục |
|---|---|---|
| Biết có những hệ thống nào, IP, cổng, cấu hình, việc còn thiếu | [SYSTEMS_INVENTORY.md](SYSTEMS_INVENTORY.md) | toàn bộ |
| **SSH vào server**, thêm khóa, mở web dev/staging/prod, `make lan-up`, `.env` từng môi trường | [PROXMOX_ACCESS.md](PROXMOX_ACCESS.md) | 2, 3, 4, 7 |
| Việc hằng ngày: kiểm tra, snapshot, backup, cập nhật, xoay token, sự cố | [PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md) | 2-9 |
| Dựng VM mới, Ansible, CI/CD, deploy bản mới, rollback | [PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md) | 4, 5, 7, 8 |
| Template VM, cloud-init, tạo nhiều instance | [PROXMOX_TEMPLATES.md](PROXMOX_TEMPLATES.md) | toàn bộ |
| Lý do thiết kế, các quyết định đã chốt | [spec](specs/proxmox-deploy.md) | 7 |

> Cập nhật file này **mỗi khi** thêm/xóa VM, đổi IP, đổi cổng, đổi phiên bản lớn. Số liệu đo (RAM dùng, container) đổi theo
> thời gian: chạy lại lệnh ở mục 9 để làm mới thay vì tin con số cũ.

## 1. Sơ đồ tổng

```
                       Mạng LAN 192.168.100.0/24   (gateway 192.168.100.1)
   ┌──────────────┐        │
   │ Máy dev (Mac)│ .75    │
   │ make, ssh,   │────────┤
   │ ansible      │        │
   └──────────────┘        │
        ┌──────────────────┴────────────────────────────────────────────┐
        │  Proxmox VE 9.1.11  node "isec"   192.168.100.252   :8006 :22  │
        │   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │
        │   │ 100 vpn    │ │ 201 dev    │ │ 202 staging│ │ 203 prod   │  │
        │   │ gateway    │ │ .201 2.5GB │ │ .202 3 GB  │ │ .203 5 GB  │  │
        │   │ 2 GB       │ │ nhánh main │ │ nhánh uat  │ │ nhánh prod │  │
        │   └────────────┘ └────────────┘ └────────────┘ └────────────┘  │
        │   template 9000 (Ubuntu 24.04 cloud-init)                       │
        │   tắt: 140 agent-hub, 150 jump-host-hub                         │
        └────────────────────────────────────────────────────────────────┘
   GitHub (repo public) ── Actions: CI, Build images → GHCR (ai-assistant-api / -web)
   Runner tự host (LXC .204): chưa dựng
```

## 2. Danh mục hệ thống

| # | Hệ thống | Loại | Địa chỉ | Vai trò | Trạng thái | Chủ trì |
|---|---|---|---|---|---|---|
| 1 | Proxmox VE node `isec` | Hạ tầng ảo hóa | 192.168.100.252 | Chạy mọi VM | online | Chủ hạ tầng |
| 2 | `isec-vpn-gateway` (VM 100) | VM, **không thuộc dự án** | (không rõ) | VPN vào mạng nhà | chạy, `onboot=1` | Chủ hạ tầng |
| 3 | `ai-dev-01` (VM 201) | VM dự án | 192.168.100.201 | Môi trường dev, nhánh `main` | chạy, stack lên | Nhóm dự án |
| 4 | `ai-stg-01` (VM 202) | VM dự án | 192.168.100.202 | Staging | chạy, stack lên (thử, tag `local`) | Nhóm dự án |
| 5 | `ai-prod-01` (VM 203) | VM dự án | 192.168.100.203 | Production | chạy, **chưa deploy stack** | Nhóm dự án |
| 6 | Template 9000 | Mẫu VM | — | Nguồn clone | tắt (là template) | Nhóm dự án |
| 7 | GitHub repo `doanviethung1009/ai_assistant_personal` | Mã nguồn + CI | github.com | Nguồn sự thật mã, CI, build image | public | Chủ repo |
| 8 | GHCR (`ai-assistant-api`, `ai-assistant-web`) | Registry image | ghcr.io | Lưu image theo tag `sha-<7>` | api đã có 1 lần đẩy, web chưa | CI |
| 9 | Runner CI tự host (LXC `ai-ci-01`) | Dự kiến | 192.168.100.204 | Chạy deploy trong LAN | **chưa dựng** | — |
| 10 | Jira Cloud (nguồn dữ liệu) | Dịch vụ ngoài | (theo cấu hình kết nối) | Đồng bộ task | tùy môi trường | Người dùng |
| 11 | LLM gateway (LiteLLM, profile `llm`) | Dịch vụ trong stack | `:4000` trên VM | Gọi model qua một cổng | tắt mặc định, chưa có API key | — |

VM 140 `agent-hub` (6 GB, disk 104 GB) và 150 `jump-host-hub` (2 GB, 24 GB) đang **tắt, chưa xóa**; chỉ chiếm dung lượng đĩa, không chiếm RAM.

## 3. Thông tin Proxmox node `isec`

| Mục | Giá trị |
|---|---|
| Phiên bản | Proxmox VE 9.1.11 (nền Debian 13, OpenSSH 10.0) |
| Phần cứng | 6 nhân, RAM 15.5 GB, swap 8 GB, disk gốc 94 GB (9 GB dùng) |
| Storage | `local-lvm` (LVM-thin, 794 GB, ~734 GB trống): disk VM. `local` (thư mục, 94 GB, ~80 GB trống): iso, snippet, template LXC, **backup** |
| Mạng | một bridge `vmbr0` = 192.168.100.252/24, cổng ra `nic0`; **không VLAN** |
| Cổng dịch vụ | 8006 (web + API, HTTPS), 22 (SSH) |
| TLS | tự ký, CN `isec.dbahomeslab.com`, hết hạn 2028-02-29; fingerprint SHA-256 `A3:33:33:B3:...:12:AE` (đầy đủ ở `.env.pve`) |
| Danh tính | `root@pam` (con người); `readonly@pve!audit` (PVEAuditor); `deploy@pve!automation` (AIDeploy, pool `ai-assistant`) |
| Pool | `ai-assistant` (dự án) |
| Backup | **chưa có job** |
| RAM đã cấp | 2 (vpn) + 2.5 + 3 + 5 = 12.5 GB đang chạy; thực dùng ~12.1 GB tại lúc đo (đo thay đổi) |

## 4. Thông tin các VM dự án

Cấu hình chung (cả ba): Ubuntu 24.04.5 LTS, kernel 6.8.0-117, 2 vCPU, Docker Engine 29.x + Compose 5.6.0, user `deploy`
(sudo không mật khẩu), `qemu-guest-agent`/`chrony`/`docker`/`ufw` bật khi khởi động, SSH chỉ khóa, `ufw` chỉ nhận 22 và 3000 từ
`192.168.100.0/24`, múi giờ `Asia/Ho_Chi_Minh`, log container xoay vòng 10 MB x 3.

| | dev | staging | prod |
|---|---|---|---|
| VM id / tên | 201 `ai-dev-01` | 202 `ai-stg-01` | 203 `ai-prod-01` |
| IP | 192.168.100.201 | 192.168.100.202 | 192.168.100.203 |
| RAM / disk | 2.5 GB / 30 GB (25% dùng) | 3 GB / 40 GB (17%) | 5 GB / 60 GB (5%) |
| Nhánh git trên VM | `main` | `main` (checkout tay để thử; đúng quy trình là `uat`) | `prod` (cũ, `d0cbccc`) |
| Thư mục app | `/srv/builder-ai/dev` | `/srv/builder-ai/staging` | `/srv/builder-ai/prod` |
| File cấu hình | `.env` (xem PROXMOX_ACCESS.md mục 7) | `.env` | `.env` |
| `ENVIRONMENT` | development | staging | production |
| `COMPOSE_PROJECT_NAME` | builder-dev | builder-staging | builder-prod |
| Cách chạy | `make up` (dev, bind mount, hot reload; image build tại chỗ) | `docker-compose.prod.yml` + `scripts/deploy.sh` | như staging, **chưa chạy** |
| Image app | `builder-dev-api`, `builder-dev-web` (build tại chỗ) | `ghcr.io/.../ai-assistant-{api,web}:local` | chưa có |
| `protection` | không | không | **có** (không xóa nhầm được) |
| Backup | không (dữ liệu thử) | `backups/` trên VM (1 file), không có job | chưa |
| Liên hệ nghiệp vụ | dùng thử/phát triển | nghiệm thu trước prod | dữ liệu thật (khi vận hành) |

### 4.1 Container trong mỗi VM (stack core)

| Container | Image | Cổng trong VM | Vai trò | Dữ liệu |
|---|---|---|---|---|
| `builder-web` | Next.js (build từ `apps/web`, target `prod`/`dev`) | `127.0.0.1:3000` | Giao diện + Server Actions (gọi API, giữ khóa API ở server) | — |
| `builder-api` | FastAPI (build từ `apps/core`) | `127.0.0.1:8000` | REST API, migration lúc khởi động, healthcheck | — |
| `builder-postgres` | `pgvector/pgvector:pg17` | dev: `127.0.0.1:5432`; staging/prod: **không publish** | CSDL chính | volume `builder-<env>_postgres_data` → `/var/lib/postgresql/data` |
| `builder-redis` | `redis:7.4-alpine` | dev: `127.0.0.1:6379`; staging/prod: không publish | Rate limit, cache | volume `builder-<env>_redis_data` |

Mạng Docker nội bộ: `builder-ai-net`. Profile phụ (chưa bật): `llm` (LiteLLM :4000), `monitoring` (Prometheus :9090, Grafana :3001, blackbox :9115, exporters).

### 4.2 Bảng cổng và luồng truy cập

| Cổng | Ở đâu | Ai vào được | Ghi chú |
|---|---|---|---|
| 22/tcp | node, mỗi VM | LAN `192.168.100.0/24`, bằng khóa | VM: ufw; node: theo cấu hình sshd |
| 8006/tcp | node | LAN | Web/API Proxmox, HTTPS tự ký |
| 3000/tcp | mỗi VM | **LAN, sau khi bật** (dev: `make lan-up`; staging/prod: `EXPOSE_LAN=true`) | Mặc định container chỉ nghe 127.0.0.1; khi mở thì nghe 0.0.0.0. Docker bỏ qua ufw nên giới hạn thực tế là mạng LAN. App chưa có đăng nhập. Xem PROXMOX_ACCESS.md mục 4.3b |
| 8000/tcp | mỗi VM | chỉ `127.0.0.1` | API + `/docs`; qua tunnel |
| 5432, 6379 | mỗi VM | dev: chỉ `127.0.0.1`; staging/prod: không | Không bao giờ mở ra ngoài |

## 5. Nguồn dữ liệu và quan hệ phụ thuộc

| Hệ thống | Phụ thuộc vào | Nếu phụ thuộc đó hỏng |
|---|---|---|
| Web | API (`CORE_API_URL`), khóa `API_KEY` | Trang lỗi/trống; kiểm tra `make health` |
| API | Postgres, Redis | `/health/ready` báo lỗi từng thành phần |
| Postgres | Volume trên `local-lvm` | Thin pool đầy → treo VM (PROXMOX_OPERATIONS.md mục 6.2) |
| Deploy tự động | GHCR có tag, runner trong LAN, GitHub Secrets | Chưa dùng được; chạy tay `scripts/deploy.sh` |
| Truy cập từ ngoài LAN | VM 100 (VPN gateway) | Không vào được mạng nhà |
| Đồng bộ Jira | Mạng ra Internet, token Jira (mã hóa trong DB) | Task Jira không cập nhật |

## 6. Thông tin xác thực và bí mật: ở đâu (không có giá trị ở đây)

| Thứ | Vị trí | Ai được xem |
|---|---|---|
| `.env` ứng dụng (API_KEY, mật khẩu DB, LITELLM_*, GRAFANA, IMPORT_COMMIT_SECRET, INTEGRATION_SECRET_KEY) | Trên từng VM, `600` | Người có SSH vào VM đó |
| Token Proxmox đọc/ghi | `infra/proxmox/.env.pve`, `.env.pve.deploy` (máy dev, gitignore) | Chủ máy dev |
| Khóa SSH `ai_assistant_deploy` | `~/.ssh` máy dev | Chủ máy dev |
| Khóa quản trị node `isec_admin` | `~/.ssh` của từng quản trị viên | Từng người |
| Mật khẩu `root@pam` | Chủ hạ tầng | Chủ hạ tầng |
| GitHub Secrets (CI) | GitHub | **chưa tạo** |
| Token tích hợp ngoài (Jira) | Mã hóa trong DB (`INTEGRATION_SECRET_KEY`) | Không bao giờ trả ra API |

## 7. Quy trình thay đổi thông tin hệ thống

1. Thay đổi hạ tầng (thêm VM, đổi IP, đổi RAM): dùng `make pve-vm`/`pve-config`; **cập nhật file này** và bảng ở PROXMOX_OPERATIONS.md mục 1.
2. Đổi mã/cấu hình ứng dụng: PR → CI xanh → merge `main` → `uat` → `prod` (git-workflow.md).
3. Đổi bí mật: xoay theo PROXMOX_OPERATIONS.md mục 8; ghi ngày xoay vào nhật ký (mục 10).
4. Sự cố/thay đổi lớn: ghi vào `docs/AI_HANDOFF_STATE.md` để phiên làm việc sau nắm được.

## 8. Việc còn thiếu (rà soát tài liệu và hệ thống, 2026-10-09)

| # | Thiếu gì | Mức | Gợi ý |
|---|---|---|---|
| 1 | **Chưa có job backup** (node và DB) | Cao | Tạo job `vzdump` cho 203 và 202; chép `backups/` ra ngoài node (PROXMOX_OPERATIONS.md mục 5) |
| 2 | **Prod chưa deploy stack**; nhánh `prod` trên VM đang là bản rất cũ | Cao | Thăng cấp `main → uat → prod` (cần bạn quyết, có `git push`), rồi `scripts/deploy.sh` |
| 3 | **Staging/prod thiếu `IMPORT_COMMIT_SECRET`, `INTEGRATION_SECRET_KEY`** | Cao | `make env-fill` trên VM trước khi deploy |
| 4 | Runner CI tự host và GitHub Environments/Secrets chưa tạo → workflow Deploy chưa chạy được | Trung bình | Dựng LXC `ai-ci-01`; RAM node sát giới hạn (tắt dev khi không dùng) |
| 5 | Build images: image api đã đẩy được; **web chưa có image** (job bị hủy khi Trivy của api fail); lỗi Trivy chưa rõ nguyên nhân | Trung bình | PR #29 đã thêm `fail-fast: false` + `continue-on-error`; chạy lại `Build images` và đọc log Trivy |
| 6 | **Giám sát hạ tầng**: chưa có cảnh báo cho node/VM (RAM, thin pool, đĩa) | Trung bình | `prometheus-pve-exporter` + profile `monitoring`; tạm thời kiểm tay hằng tuần |
| 7 | Tài liệu về **VM 100 (VPN gateway)** gần như trống (cấu hình, cách vào từ ngoài, ai chịu trách nhiệm) | Trung bình | Chủ hạ tầng bổ sung mục riêng; dự án phụ thuộc nó để truy cập từ xa |
| 8 | Chưa kiểm chứng **SSH `root` vào node** và việc tắt mật khẩu SSH (PROXMOX_ACCESS.md mục 2) | Trung bình | Bạn thử và báo lại |
| 9 | Chưa **thử restore** backup bao giờ | Trung bình | Sau khi có backup, restore sang VM id trống (mục 5.3) |
| 10 | Chưa có **người chịu trách nhiệm / liên hệ** cho từng hệ thống và quy trình leo thang sự cố | Thấp-TB | Điền cột "Chủ trì" ở mục 2 bằng tên thật |
| 11 | VM 140, 150 tắt nhưng chưa xóa | Thấp | Xóa hoặc ghi rõ lý do giữ (mục 4 PROXMOX_DEPLOY.md) |
| 12 | Chưa có **tab Hạ tầng** trên web (giai đoạn A chỉ đọc) | Thấp | Spec có; làm sau khi web có đăng nhập cho phần hành động |
| 13 | `instances.yml` (danh mục instance) mới ở dạng đề xuất | Thấp | PROXMOX_TEMPLATES.md mục 7.3 |
| 14 | Môi trường dev chỉ 2.5 GB, có thể thiếu khi build lớn | Thấp | Nâng lên 3 GB nếu OOM |
| 15 | Còn `sed -i ''` (macOS-only) ở `scripts/bootstrap.sh` và `Makefile` | Thấp | Sửa như `gen-env.sh` |

## 9. Lệnh làm mới số liệu (chạy khi cần cập nhật file này)

```bash
make pve-check                                             # node, storage, bridge, danh sách VM
for ip in 201 202 203; do ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.$ip \
  'hostname; free -m | sed -n 2p; df -h / | tail -1; docker ps --format "{{.Names}} {{.Image}} {{.Status}}"'; done
gh run list --limit 5                                      # trạng thái CI
```

## 10. Nhật ký thay đổi hệ thống

| Ngày | Thay đổi | Người/Công cụ |
|---|---|---|
| 2026-10-09 | Dựng VM staging 202, prod 203, dev 201 từ template 9000; cấu hình Ansible; thử stack trên staging | `make pve-vm`, `make pve-config` |
| 2026-10-09 | Tắt VM 140, 150 (chưa xóa) | Chủ hạ tầng |
| 2026-10-09 | Thêm CI build image lên GHCR và workflow deploy (chưa chạy được đủ) | PR #25, #26, #28, #29 |

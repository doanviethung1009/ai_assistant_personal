# Truy cập server: thêm khóa SSH và quản lý các môi trường đã deploy

Cập nhật: 2026-10-09. Hướng dẫn **thêm khóa SSH vào node Proxmox và vào các VM**, rồi **cách vào quản lý** dev, staging,
prod. Thông tin hiện trạng (IP, VM) ở [PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md); cách dựng ở
[PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md).

## 0. Hiểu nhanh các thuật ngữ

| Từ | Nghĩa trong dự án này |
|---|---|
| **Khóa SSH** | Một cặp file: khóa **riêng** (`id_xxx`, giữ bí mật, không rời máy bạn) và khóa **công khai** (`id_xxx.pub`, đưa cho server). Server nào có khóa công khai thì chỉ máy giữ khóa riêng tương ứng đăng nhập được, không cần mật khẩu |
| **`authorized_keys`** | File trên server liệt kê các khóa công khai được phép vào. Mỗi dòng một khóa |
| **Node Proxmox** | Máy chủ vật lý `isec` (192.168.100.252), chạy Proxmox. Đăng nhập bằng `root` |
| **VM** | Máy ảo chạy trên node: `ai-dev-01`, `ai-stg-01`, `ai-prod-01`. Đăng nhập bằng user `deploy` |
| **Ansible** | Công cụ tự động hóa cấu hình server: bạn mô tả "VM phải trông như thế nào" trong file YAML, Ansible kết nối SSH vào VM và làm cho đúng như vậy. Chạy lại bao nhiêu lần cũng được (nếu đã đúng thì không làm gì). Dự án dùng nó để cài Docker, firewall, thư mục app, khóa SSH trên mọi VM mà không phải gõ tay. Chạy bằng `make pve-config ENV=...`; các file ở `infra/proxmox/ansible/` |
| **cloud-init** | Chương trình trong VM đọc cấu hình lúc **khởi động lần đầu** (user, khóa, IP) do Proxmox cung cấp |

## 1. Tạo khóa SSH cho riêng bạn (mỗi người, mỗi máy một khóa)

Khóa quản trị node **khác** khóa tự động hóa `ai_assistant_deploy` (dùng cho Ansible/CI). Tách ra để thu hồi từng cái được.

```bash
ssh-keygen -t ed25519 -C "hungdv@macbook-2026" -f ~/.ssh/isec_admin
# Nên đặt passphrase khi được hỏi: khóa bị lấy cắp vẫn chưa dùng ngay được
ssh-add --apple-use-keychain ~/.ssh/isec_admin      # macOS: nhớ passphrase trong Keychain
cat ~/.ssh/isec_admin.pub                           # đây là thứ đưa cho server
```

- Phần `-C` là **comment** `<người>@<máy>-<năm>`: sau này dựa vào đó biết khóa của ai để gỡ.
- Chỉ dùng loại `ed25519`. Không bao giờ gửi file không có đuôi `.pub` cho ai, và không dán nó vào chat.

## 2. Thêm khóa SSH vào node Proxmox (`root@192.168.100.252`)

Cách A: từ máy bạn, nếu SSH bằng mật khẩu root còn mở:

```bash
ssh-copy-id -i ~/.ssh/isec_admin.pub root@192.168.100.252
```

Cách B: qua giao diện web (không cần SSH): `https://192.168.100.252:8006` → node `isec` → **Shell**, rồi dán một dòng
(thay bằng nội dung file `.pub` của bạn, giữ trong một dòng):

```bash
echo 'ssh-ed25519 AAAAC3...xyz hungdv@macbook-2026' >> /root/.ssh/authorized_keys
```

Lưu ý riêng của Proxmox: `/root/.ssh/authorized_keys` là **liên kết tới `/etc/pve/priv/authorized_keys`** (hệ thống file
cụm của Proxmox). Cứ thêm vào đường dẫn `/root/.ssh/authorized_keys` như trên là đúng, và với cụm nhiều node thì khóa tự đồng bộ.

Kiểm tra:

```bash
ssh -i ~/.ssh/isec_admin root@192.168.100.252 'pveversion'
```

Thêm vào `~/.ssh/config` để gõ ngắn (`ssh isec`):

```
Host isec
  HostName 192.168.100.252
  User root
  IdentityFile ~/.ssh/isec_admin
  IdentitiesOnly yes
```

### 2.1 Siết bảo mật sau khi khóa đã chạy (nên làm, làm sau cùng)

Khi chắc chắn đăng nhập bằng khóa được, tắt mật khẩu qua SSH. **Giữ nguyên một cửa sổ Shell web đang mở** làm đường lui
trong lúc làm, vì cấu hình sai sẽ khóa chính bạn ra ngoài.

```bash
cat > /etc/ssh/sshd_config.d/99-isec-hardening.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh      # chỉ reload khi cú pháp đúng
```

Sau đó thử mở một phiên SSH mới bằng khóa **trước khi** đóng cửa sổ web. Đăng nhập web `:8006` bằng mật khẩu `root@pam`
vẫn hoạt động riêng, không bị ảnh hưởng. (Tắt SSH mật khẩu là khuyến nghị; nếu bạn còn dùng mật khẩu trên máy khác thì
thêm khóa cho máy đó trước.)

## 3. Thêm khóa SSH vào các VM (dev, staging, prod)

VM chỉ cho user `deploy` vào bằng khóa; khóa đầu tiên là `ai_assistant_deploy` (cloud-init nạp lúc dựng). Muốn **thêm người/máy
khác**, có hai cách. Khuyến nghị cách 3.1 vì VM dựng lại vẫn giữ khóa.

### 3.1 Bằng Ansible (khuyến nghị)

Thêm khóa công khai vào `infra/proxmox/ansible/group_vars/all.yml`:

```yaml
extra_ssh_keys:
  - "ssh-ed25519 AAAAC3...xyz hungdv@macbook-2026"
```

Rồi áp lên VM cần thiết:

```bash
make pve-config ENV=dev
make pve-config ENV=staging
make pve-config ENV=prod      # prod: chỉ thêm khóa của người được phép quản lý prod
```

Khóa công khai không phải bí mật, nên commit cũng được; nếu không muốn đưa tên người lên git, để trong file biến riêng
không commit (`-e @file.yml`). Lệnh chạy lại không nhân đôi khóa.

### 3.2 Bằng tay (khi khẩn cấp)

```bash
ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.202 \
  "echo 'ssh-ed25519 AAAAC3...xyz hungdv@macbook-2026' >> ~/.ssh/authorized_keys"
```

Cách này **không bền**: VM bị dựng lại là mất. Hãy ghi lại vào 3.1 sau đó.

### 3.3 Đừng dùng `qm set --sshkeys` để thêm khóa cho VM đã chạy

Tham số cloud-init `sshkeys` của Proxmox **thay toàn bộ** danh sách khóa và chỉ có hiệu lực ở lần khởi động đầu tiên
của VM. Đặt lại trên VM đang chạy thường không có tác dụng, và nếu có thì ghi đè mất các khóa khác.

## 4. Truy cập các server đã deploy để quản lý

### 4.1 Vào bằng SSH

```bash
ssh ai-dev        # 192.168.100.201, nhánh main, hot reload
ssh ai-stg        # 192.168.100.202, nhánh uat
ssh ai-prod       # 192.168.100.203, nhánh prod (chỉ đọc/chẩn đoán là chính)
```

(Alias cấu hình ở PROXMOX_OPERATIONS.md mục 1b. Chưa có alias thì: `ssh -i ~/.ssh/ai_assistant_deploy deploy@<ip>`.)
Phải ở trong mạng `192.168.100.0/24` (firewall VM chỉ nhận SSH từ dải này). Ở ngoài, **kết nối VPN** vào mạng nhà trước
(VM `isec-vpn-gateway` đang đảm nhiệm), rồi SSH như bình thường.

### 4.2 Thư mục và lệnh quản lý trên VM

App nằm ở `/srv/builder-ai/<dev|staging|prod>`. Mọi lệnh dùng `make` từ thư mục đó:

```bash
cd /srv/builder-ai/prod
make ps               # container đang chạy và trạng thái
make logs-api         # log backend
make logs-web         # log web
make health           # kiểm tra readiness của API
make psql             # vào Postgres
make backup           # dump DB ra backups/
docker stats --no-stream      # CPU/RAM từng container
df -h /               # dung lượng đĩa
```

Triển khai bản mới **không** làm tay: dùng `scripts/deploy.sh <tag>` hoặc pipeline (PROXMOX_DEPLOY.md mục 8). Chỉ chạm
trực tiếp vào container prod khi chẩn đoán. Nguyên tắc dự án: agent AI không có quyền ghi thường trực lên production, thay đổi
đi qua runbook/pipeline có duyệt.

### 4.3 Mở giao diện web/API của app (ứng dụng chỉ nghe ở `127.0.0.1` trên VM)

Mặc định web (3000) và API (8000) bind `127.0.0.1` trong VM nên không thấy từ máy bạn. Cách an toàn nhất là **SSH tunnel**:

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 ai-stg
# giữ cửa sổ đó, rồi mở trình duyệt:
#   http://localhost:3000         web
#   http://localhost:8000/docs    tài liệu API
```

Cách thứ hai: `make lan-up` trên VM để mở web ra LAN (firewall đã mở sẵn 3000 cho `192.168.100.0/24`). Cẩn thận: **app chưa có
đăng nhập** (Phase 1), ai trong LAN mở được là dùng được; chỉ nên cho dev/staging, không cho prod.

Không bao giờ mở Postgres/Redis ra ngoài VM; truy cập DB chỉ qua `make psql` trên VM.

### 4.4 Quản lý hàng loạt bằng Ansible

```bash
cd infra/proxmox/ansible
../.venv/bin/ansible all -m ping                                  # VM nào còn tới được
../.venv/bin/ansible all -m command -a "uptime"                   # chạy một lệnh trên mọi VM
../.venv/bin/ansible staging -b -m command -a "systemctl is-active docker"
```

Thay đổi cấu hình VM (gói, firewall, khóa) nên đi qua playbook (`make pve-config`), không gõ tay, để VM dựng lại không mất.

### 4.5 Khi SSH không vào được

Thứ tự thử:
1. **Giao diện Proxmox:** chọn VM → **Console** (hoặc trên node: `qm terminal <id>`, thoát bằng `Ctrl+O`). VM không có mật khẩu
   đăng nhập nên console chỉ để xem log khởi động và trạng thái, chưa đăng nhập được.
2. **Guest agent từ node** (VM đã cài `qemu-guest-agent` qua Ansible): chạy lệnh trong VM mà không cần SSH, ví dụ nạp lại khóa:

   ```bash
   qm guest exec 203 -- bash -c "echo 'ssh-ed25519 AAAA... hungdv@macbook-2026' >> /home/deploy/.ssh/authorized_keys"
   qm guest exec 203 -- bash -c "ufw status; systemctl is-active ssh"
   ```

3. **Firewall:** SSH chỉ cho `192.168.100.0/24`; nếu bạn ở dải khác (VPN?), thêm dải đó vào `admin_cidr` trong
   `group_vars/all.yml` rồi `make pve-config` (hoặc dùng bước 2 để sửa tay tạm thời).
4. Xem log VM: `qm guest exec <id> -- journalctl -u ssh -n 50`.

## 5. Gỡ khóa và xoay khóa

| Việc | Cách làm |
|---|---|
| Người rời nhóm / mất máy | Xóa dòng chứa comment của họ khỏi `authorized_keys` ở **node** (mục 2) **và mọi VM**; xóa khỏi `extra_ssh_keys` để VM dựng lại không có |
| Xóa khỏi node | Shell web: `sed -i '/hungdv@macbook-2026/d' /root/.ssh/authorized_keys` (kiểm tra bằng `cat` trước) |
| Xóa khỏi VM | `ssh ai-stg "sed -i '/hungdv@macbook-2026/d' ~/.ssh/authorized_keys"` (làm cho cả dev, stg, prod) |
| Xoay khóa tự động hóa `ai_assistant_deploy` | Tạo khóa mới, thêm vào VM bằng 3.1, đổi `PVE_SSH_PUBKEY`/GitHub Secret `DEPLOY_SSH_KEY`, kiểm tra, rồi xóa khóa cũ |
| Nghi khóa bị lộ | Gỡ ngay ở mọi nơi; tạo khóa mới; xem `lastlog`/`journalctl -u ssh` trên server tìm đăng nhập lạ |

Ansible hiện chỉ **thêm** khóa, không tự gỡ khóa đã có; gỡ phải làm như bảng trên.

## 6. Quy tắc an toàn


1. Mỗi người, mỗi máy một khóa riêng; khóa riêng **không** copy sang máy khác, không đưa lên git/chat.
2. Khóa quản trị có passphrase; khóa tự động hóa (`ai_assistant_deploy`) không passphrase nên chỉ để trên máy tin cậy, quyền `600`.
3. Quản lý prod bằng quyền tối thiểu và qua runbook; chỉ đọc/chẩn đoán trực tiếp.
4. Giữ đường lui (Shell web, `qm guest exec`) trước khi đổi bất cứ cấu hình SSH nào.
5. Định kỳ (mỗi quý) rà `authorized_keys` ở node và VM, gỡ khóa không còn dùng.

## 7. File cấu hình (`.env`) của từng môi trường và cách lấy thông tin

Có **hai nhóm file cấu hình khác nhau**, đừng nhầm:

### 7.1 `.env` của ứng dụng: nằm TRÊN từng VM

| Môi trường | File | Sinh bởi | Ghi chú |
|---|---|---|---|
| dev | `192.168.100.201:/srv/builder-ai/dev/.env` | Ansible (`make env`) | `ENVIRONMENT=development`, `COMPOSE_PROJECT_NAME=builder-dev` |
| staging | `192.168.100.202:/srv/builder-ai/staging/.env` | Ansible | `ENVIRONMENT=staging`, `IMAGE_TAG` do deploy ghi |
| prod | `192.168.100.203:/srv/builder-ai/prod/.env` | Ansible | `ENVIRONMENT=production`; quyền `600`, chủ `deploy` |

- Mỗi môi trường có **khóa ngẫu nhiên riêng** (`API_KEY`, `POSTGRES_PASSWORD`, `LITELLM_*`, `GRAFANA_ADMIN_PASSWORD`...). Chúng chỉ tồn tại
  trên VM đó, **không** trong git, **không** trong tài liệu, nên cũng không có trong chat. Đây là chủ ý.
- Ansible sinh `.env` **một lần** và không ghi đè (đổi `API_KEY`/mật khẩu DB làm app và Postgres lệch nhau). Nên muốn
  biết giá trị thật thì phải đọc từ VM.
- Biến cố định theo môi trường (`COMPOSE_PROJECT_NAME`, `ENVIRONMENT`, `CORS_ORIGINS`) do Ansible đặt lại mỗi lần `make pve-config`.

Xem **tên biến (che giá trị bí mật)**, an toàn để chia sẻ:

```bash
ssh ai-prod "grep -E '^[A-Z_]+=' /srv/builder-ai/prod/.env | sed -E 's/^([A-Z_]*(KEY|PASSWORD|SECRET|TOKEN|SALT)[A-Z_]*)=.*/\1=<ẩn>/'"
```

Xem **giá trị thật** của một biến (chỉ khi cần, đừng dán vào chat/git):

```bash
ssh ai-prod "grep '^API_KEY=' /srv/builder-ai/prod/.env"
```

Cần `API_KEY` của môi trường nào thì đọc ở VM đó. Web gọi API qua Server Action phía server nên **người dùng không bao giờ cần API key**;
chỉ dùng khi gọi API trực tiếp (ví dụ `curl -H "X-API-Key: ..." http://localhost:8000/api/v1/tasks` chạy trên VM).

Sửa `.env`: chỉ sửa trên VM (`nano /srv/builder-ai/<env>/.env`), rồi `make prod-up` để container nhận giá trị mới. Đổi
`NEXT_PUBLIC_*` thì phải build lại (xem deploy-runbook.md Case 4). **Không** commit `.env`.

### 7.2 Bản đối chiếu giữa các môi trường

| Biến | dev | staging | prod |
|---|---|---|---|
| `ENVIRONMENT` | development | staging | production |
| `COMPOSE_PROJECT_NAME` | builder-dev | builder-staging | builder-prod |
| `CORS_ORIGINS` | `http://192.168.100.201:3000` | `http://192.168.100.202:3000` | `http://192.168.100.203:3000` |
| `IMAGE_TAG` | (không dùng, build tại chỗ) | do deploy ghi | do deploy ghi |
| Khóa bí mật | riêng | riêng | riêng (**không dùng chung**) |

Hiện **staging và prod thiếu hai biến** mà code mới ở `main` cần: `IMPORT_COMMIT_SECRET` và `INTEGRATION_SECRET_KEY` (hai VM này sinh `.env` từ
nhánh `uat`/`prod` cũ). Trước khi deploy phiên bản mới lên đó, chạy trên VM: `make env-fill` (chỉ bổ sung biến còn thiếu, không đổi biến đã có).

### 7.3 Token Proxmox và khóa SSH: nằm TRÊN MÁY DEV của bạn

| Thứ | Ở đâu | Dùng cho |
|---|---|---|
| `infra/proxmox/.env.pve` | máy dev, trong repo nhưng bị `.gitignore` | `make pve-check` (token chỉ đọc) |
| `infra/proxmox/.env.pve.deploy` | như trên | `make pve-vm`, `pve-snapshot` (token ghi) |
| `~/.ssh/ai_assistant_deploy` | máy dev | khóa riêng SSH vào cả 3 VM (user `deploy`) |
| `~/.ssh/isec_admin` | máy dev (tạo ở mục 1) | khóa riêng SSH vào node Proxmox |

Mất hoặc muốn dùng trên máy khác: copy theo cách an toàn (không qua chat), `chmod 600`, hoặc tạo token/khóa mới (PROXMOX_OPERATIONS.md mục 8).
CI dùng bản sao trong GitHub Secrets (`DEPLOY_SSH_KEY`, `PVE_*`), chưa tạo.

### 7.4 Địa chỉ truy cập từng môi trường

| Môi trường | Web | API docs | Cách mở |
|---|---|---|---|
| dev | `http://192.168.100.201:3000` | `:8000/docs` | `make lan-up` trên VM, hoặc SSH tunnel (mục 4.3) |
| staging | `http://192.168.100.202:3000` | `:8000/docs` | như trên |
| prod | `http://192.168.100.203:3000` | `:8000/docs` | SSH tunnel; app chưa có đăng nhập nên **không** mở ra LAN |

Mặc định web/API bind `127.0.0.1` trong VM; xem mục 4.3.

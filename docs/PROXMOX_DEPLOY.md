# Hướng dẫn Proxmox: dựng VM và deploy sản phẩm

Cập nhật: 2026-10-09. Thiết kế và lý do nằm ở [spec](specs/proxmox-deploy.md). File này là
**hướng dẫn thao tác từng bước**. Lệnh chạy trên server sau khi VM đã có nằm ở
[deploy-runbook.md](deploy-runbook.md), không lặp lại ở đây.

> Tìm tài liệu khác: xem **Bản đồ tài liệu** ở [SYSTEMS_INVENTORY.md](SYSTEMS_INVENTORY.md). SSH vào server và mở web các môi trường: [PROXMOX_ACCESS.md](PROXMOX_ACCESS.md).

## 0. Trạng thái triển khai (đọc trước)

| Hạng mục | Trạng thái |
|---|---|
| Kiểm tra Proxmox bằng token chỉ đọc (`pve-check.sh`) | **Đã có**, chạy được |
| Template Ubuntu cloud-init | **Đã có** trên node: id 9000 `ubuntu-2404-tmpl` (dùng lại, bỏ qua mục 3) |
| Dựng VM staging / prod | **Đã có** `make pve-vm ENV=dev\|staging\|prod` (mục 13). cả 3 VM đã dựng và cấu hình Ansible (2026-10-09): dev `.201`, staging `.202`, prod `.203` (`protection=1`); stack mới chạy trên dev và staging, **prod chưa deploy** |
| Cấu hình VM bằng Ansible | **Đã có** `make pve-config ENV=...`, đã áp lên staging, chạy lần 2 `changed=0` (mục 5) |
| Thử build + chạy stack trên staging | **Đã thử** (2026-10-09): build, up, migrate, health OK; `make smoke` 93/98 (5 lỗi là race của backend, xem PROXMOX_OPERATIONS.md mục 11) |
| CI build image + deploy tự động | Workflow đã viết và merge (`build-images.yml`, `deploy.yml`); `Build images` đã build+đẩy được image api, bước Trivy còn lỗi chưa rõ nguyên nhân; `Deploy` **chưa chạy được** (cần runner tự host, Environments, Secrets) |
| Tab "Hạ tầng" trên web | Chưa làm (mục 10) |

Khi một mục chuyển sang "Đã có", cập nhật bảng này.

Việc hằng ngày sau khi dựng xong (kiểm tra, backup, cập nhật, sự cố) nằm ở [PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md).

## 1. Bức tranh tổng

```
 GitHub ──push main──► CI: test → build 2 image → quét lỗ hổng → push GHCR (tag sha-xxxxxxx)
    │
    ├─ push uat  ──► runner (LXC .204) ──ssh──► VM staging .202 : pull image sha → up → health/smoke
    └─ push prod ──► [người duyệt] ► runner ──ssh──► VM prod .203 : snapshot → backup → pull → up → health/smoke

 Proxmox node "isec" (192.168.100.252:8006, PVE 9.1) chứa: template 9000, VM dev, VM staging, VM prod, (LXC runner: chưa dựng)
 dev: VM ai-dev-01 (.201) chạy `make up` (hot reload từ nhánh main); vẫn có thể chạy `make dev` trên máy cá nhân
```

| Môi trường | Nhánh git | `ENVIRONMENT` | Chạy ở | IP | RAM |
|---|---|---|---|---|---|
| dev | `main` | `development` | VM `ai-dev-01` (id 201) | 192.168.100.201 | 2.5 GB |
| staging | `uat` | `staging` | VM `ai-stg-01` | 192.168.100.202 | 3 GB |
| prod | `prod` | `production` | VM `ai-prod-01` | 192.168.100.203 | 5 GB |
| runner CI | — | — | LXC `ai-ci-01` | 192.168.100.204 | 1 GB (**chưa dựng**) |

Gateway `192.168.100.1`. Node có 15.5 GB RAM. Ngân sách đã cấp: vpn 2 + dev 2.5 + staging 3 + prod 5 = **12.5 GB** (VM `agent-hub` và `jump-host-hub` đang tắt). Mức dùng thực tế thấp hơn, nhưng chưa còn chỗ cho runner CI 1 GB: muốn thêm thì tắt dev khi không dùng (`qm shutdown 201`).

## 2. Chuẩn bị: token API Proxmox

Dùng token thay cho mật khẩu `root`, mỗi token một việc, quyền tối thiểu.

### 2.1 Token chỉ đọc (cho `pve-check` và tab web giai đoạn A)

Chạy trong shell Proxmox (web: node → Shell):

```bash
pveum user add readonly@pve
pveum user token add readonly@pve audit --privsep 1
pveum acl modify / --users 'readonly@pve' --roles PVEAuditor
pveum acl modify / --tokens 'readonly@pve!audit' --roles PVEAuditor
```

- Lệnh 2 in **secret đúng một lần**. Copy vào `infra/proxmox/.env.pve` (dòng `PVE_TOKEN_SECRET=`).
- **Phải gán quyền cho CẢ user lẫn token** (hai lệnh `acl modify` cuối). Với `--privsep 1`, quyền hiệu lực
  của token là **phần giao** giữa quyền của token và quyền của user. User không có quyền thì token cũng
  không có gì, dù ACL của token đúng. Đây là lỗi đã gặp thật khi dựng (mục 11, lỗi #1).
- Kiểm tra: `make pve-check` phải in được RAM, storage, bridge. Nếu chỉ thấy tên node mà
  số liệu bằng 0, token chưa có quyền: xem mục 11, lỗi #1.

**Gán quyền cho token (bước hay bị bỏ sót).** Tạo token xong nó chưa làm được gì cho đến khi có ACL.
Có hai cách, chọn một.

*Cách 1, Shell trên web:* mở `https://192.168.100.252:8006`, đăng nhập `root` (realm *Linux PAM*),
bấm node **isec** → **Shell**, rồi chạy:

```bash
pveum acl modify / --users 'readonly@pve' --roles PVEAuditor
pveum acl modify / --tokens 'readonly@pve!audit' --roles PVEAuditor
pveum acl list        # phải có 2 dòng: type=user readonly@pve và type=token readonly@pve!audit
```

*Cách 2, giao diện:* **Datacenter** → **Permissions** → **Add**, làm **hai lần**, mỗi lần điền Path `/`,
Role `PVEAuditor`, bật Propagate, bấm Add:
- **User Permission** với User `readonly@pve`.
- **API Token Permission** với API Token `readonly@pve!audit`.

*Kiểm tra từ máy dev:* `make pve-check`. Hoặc gọi thẳng; nếu trả `{"data":{}}` nghĩa là token
vẫn chưa có quyền:

```bash
set -a; . infra/proxmox/.env.pve; set +a
curl -sk -H "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" \
  "https://${PVE_HOST}:8006/api2/json/access/permissions"
```

Cạm bẫy thường gặp: chỉ gán cho **token** mà quên **user** (hoặc ngược lại). Token `privsep=1` chỉ có
quyền là phần giao của hai bên, nên thiếu một bên thì kết quả vẫn rỗng và API vẫn trả HTTP 200 (không báo lỗi).

### 2.2 Token tự động hóa (cho dựng VM, dùng ở mục 4 khi đóng gói script)

Tạo sau, chỉ khi cần tự động. Gắn vào pool để giới hạn phạm vi:

```bash
pveum pool add ai-assistant
pveum role add AIDeploy --privs "VM.Allocate VM.Clone VM.Config.CPU VM.Config.Memory VM.Config.Disk VM.Config.Network VM.Config.Cloudinit VM.Config.Options VM.PowerMgmt VM.Snapshot VM.Audit Datastore.AllocateSpace Datastore.Audit SDN.Use"
pveum user add deploy@pve
pveum user token add deploy@pve automation --privsep 1
```

Quyền phải đủ ở **bốn đường dẫn** (pool, VM 9000, storage, mạng), cho **cả user lẫn token** (token `privsep=1` chỉ có
phần giao của hai bên); thiếu một chỗ là clone báo `Permission check failed`. **Đừng gộp `--users` và `--tokens` trong
cùng một lệnh `acl modify`**: thực tế chỉ phần user được ghi (ACL của token vẫn rỗng). Dùng khối bên dưới.

**Gán lại toàn bộ quyền** (dùng khi tạo lại token, vì xóa token làm các ACL của nó thành "invalid" và phải gán lại
**cả bốn đường dẫn**, không chỉ chỗ vừa báo lỗi). Viết từng dòng, **dấu nháy đơn** quanh tên token, không dùng vòng
`for`: bash tương tác coi `!` trong `deploy@pve!automation` là mở rộng lịch sử lệnh và vòng lặp dán vào Shell web bị
lỗi cú pháp (đã gặp thật).

```bash
pveum acl modify /pool/ai-assistant --users 'deploy@pve' --roles AIDeploy
pveum acl modify /pool/ai-assistant --tokens 'deploy@pve!automation' --roles AIDeploy
pveum acl modify /vms/9000 --users 'deploy@pve' --roles AIDeploy
pveum acl modify /vms/9000 --tokens 'deploy@pve!automation' --roles AIDeploy
pveum acl modify /storage/local-lvm --users 'deploy@pve' --roles AIDeploy
pveum acl modify /storage/local-lvm --tokens 'deploy@pve!automation' --roles AIDeploy
pveum acl modify /sdn/zones/localnetwork --users 'deploy@pve' --roles AIDeploy
pveum acl modify /sdn/zones/localnetwork --tokens 'deploy@pve!automation' --roles AIDeploy
pveum acl list | grep deploy     # phải ra 8 dòng: 4 đường dẫn x (user + token)
```

**Lưu secret:** lệnh `token add` in secret một lần. Ghi vào file `.env.pve.deploy` (bước dưới), và với CI thì vào
GitHub Secrets (mục 7). Không vào repo, không dán vào chat. Agent AI không được dùng token này; chỉ người hoặc
pipeline có duyệt.

**Tạo file `.env.pve.deploy` trên máy dev** (tương tự mục 2.3, nhưng là token GHI):

```bash
cp infra/proxmox/.env.pve.deploy.example infra/proxmox/.env.pve.deploy   # file mẫu có sẵn trong repo
nano infra/proxmox/.env.pve.deploy      # điền PVE_TOKEN_SECRET=<secret vừa in ra>
chmod 600 infra/proxmox/.env.pve.deploy
git check-ignore -v infra/proxmox/.env.pve.deploy   # phải in ra 1 dòng, nghĩa là đã được ignore
```

Các biến còn lại (`PVE_NODE`, `PVE_STORAGE=local-lvm`, `PVE_TEMPLATE_ID=9000`, gateway, DNS) đã điền sẵn theo
node `isec` đo ở mục 0.

### 2.3 Tạo file `.env.pve` trên máy dev

File này chứa token nên **không nằm trong git** (quy tắc `.env.*` của `.gitignore`); mỗi máy tự tạo.
Chạy ở thư mục gốc của repo:

```bash
# 1. Sao chép file mẫu (mẫu đã điền sẵn địa chỉ node và fingerprint TLS)
cp infra/proxmox/.env.pve.example infra/proxmox/.env.pve

# 2. Mở file và điền secret của token vào sau PVE_TOKEN_SECRET=
nano infra/proxmox/.env.pve        # hoặc: code infra/proxmox/.env.pve

# 3. Thu hẹp quyền đọc file chỉ cho chủ máy
chmod 600 infra/proxmox/.env.pve

# 4. Thử
make pve-check
```

Nội dung file sau khi điền (không có dấu ngoặc kép, không có khoảng trắng quanh dấu `=`):

```
PVE_HOST=192.168.100.252
PVE_PORT=8006
PVE_TOKEN_ID=readonly@pve!audit
PVE_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PVE_TLS_FINGERPRINT=A3:33:...:AE
```

- `PVE_TOKEN_ID` = `<user>@<realm>!<tên token>`; phải khớp đúng với token đã gán quyền.
- `PVE_TOKEN_SECRET` là chuỗi UUID 36 ký tự do lệnh `pveum user token add` in ra **một lần**.
  Mất thì tạo lại token (mục 11, lỗi #3).
- Kiểm tra đã ignore chưa: `git check-ignore -v infra/proxmox/.env.pve` phải in ra một dòng; `git status`
  không được liệt kê file này.
- Máy khác (hoặc runner CI) cần tự tạo file riêng theo đúng các bước trên. Không copy qua chat hay email.

Script `pve-check` ghim fingerprint chứng chỉ TLS (`PVE_TLS_FINGERPRINT`) thay vì tắt kiểm tra. Nếu cài lại
Proxmox, fingerprint đổi và script dừng với mã 2; lấy fingerprint mới ở mục 11, lỗi #2. Nếu ACL rỗng
script dừng với mã 3 và in lệnh gán quyền cần chạy.

## 3. Tạo VM template Ubuntu 24.04 (làm một lần)

> **Node `isec` đã có template id 9000 `ubuntu-2404-tmpl`** (đo bằng `make pve-check`, 2026-10-09): Ubuntu 24.04
> cloud-init, guest agent bật, 2 vCPU / 2 GB, disk 3.5 GB. **Bỏ qua mục này, dùng lại 9000.** Chỉ làm khi
> cần template mới (ví dụ nâng phiên bản Ubuntu) và dùng id khác (ví dụ 9001), đừng ghi đè 9000.

Template là máy mẫu để nhân bản. Làm trên node (SSH hoặc Shell web). Storage chứa disk VM trên node này là
`local-lvm` (xem `make pve-check`, cột content có `images`); `<STORAGE>` bên dưới = `local-lvm`.

```bash
cd /var/lib/vz/template/iso
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img

qm create 9000 --name ubuntu-2404-tpl --memory 2048 --cores 2 \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-pci --agent enabled=1 --ostype l26
qm set 9000 --scsi0 <STORAGE>:0,import-from=/var/lib/vz/template/iso/noble-server-cloudimg-amd64.img
qm set 9000 --ide2 <STORAGE>:cloudinit
qm set 9000 --boot order=scsi0 --serial0 socket --vga serial0
qm template 9000
```

- `--agent enabled=1` bật kênh guest agent; gói `qemu-guest-agent` được Ansible cài ở mục 5.
- Ảnh cloud-image không có mật khẩu; chỉ đăng nhập bằng SSH key (cấu hình ở mục 4).
- Muốn cập nhật template: tải ảnh mới, tạo template id khác (9001), đổi script sang id mới. Không sửa template cũ.

## 4. Dựng một VM từ template

Ví dụ staging (id 202, IP .202). Prod: id 203, `--memory 6144`, thêm disk dữ liệu.

```bash
# Khoá SSH công khai dùng để đăng nhập (đặt sẵn trên node)
qm clone 9000 202 --name ai-stg-01 --full --pool ai-assistant
qm set 202 --memory 4096 --cores 2 \
  --ipconfig0 ip=192.168.100.202/24,gw=192.168.100.1 --nameserver 192.168.100.1 \
  --ciuser deploy --sshkeys /root/deploy.pub --ciupgrade 1
qm resize 202 scsi0 40G
qm start 202
```

Kiểm tra sau ~1 phút:

```bash
ssh deploy@192.168.100.202 'hostname; cloud-init status --wait'
```

Chỉ prod: thêm disk dữ liệu riêng để thay VM không mất DB.

```bash
qm set 203 --scsi1 <STORAGE>:40
# trong VM: format ext4, mount vào /var/lib/docker/volumes (hoặc thư mục dữ liệu), thêm vào /etc/fstab
```

Quy ước: id VM = octet cuối của IP; tên `ai-<env>-01`; gắn tag `env:<env>`.

### Các cách tạo VM (chọn theo tình huống)

| # | Cách | Khi nào dùng | Cần gì |
|---|---|---|---|
| A | Giao diện web: clone template | Làm tay lần đầu, muốn nhìn thấy từng bước | đăng nhập web |
| B | CLI `qm clone` (mục 4 ở trên) | Nhanh, lặp lại được, dán vào script | SSH vào node |
| C | API `curl` | Tự động hóa không cần SSH (CI, tab web giai đoạn B) | token ghi (mục 2.2) |
| D | Ansible | Dựng + cấu hình nhiều VM, idempotent | token ghi |
| E | Terraform | Quản lý hạ tầng như code, thấy diff trước khi áp | token ghi |
| F | Cài từ ISO | Cần OS không có cloud image, hoặc học cách cài | file ISO |
| G | LXC (`pct`) | Dịch vụ nhẹ như runner CI, exporter | template LXC |

**A. Giao diện web.** Chuột phải template `9000 (ubuntu-2404-tmpl)` → **Clone** → Mode **Full Clone**,
VM ID (ví dụ 202), Name `ai-stg-01`, Target storage `local-lvm`, Pool `ai-assistant` → Clone. Rồi chọn VM mới →
**Cloud-Init**: User `deploy`, SSH public key (dán khoá), IP Config → IPv4/CIDR `192.168.100.202/24`, Gateway
`192.168.100.1`, DNS `192.168.100.1` → **Regenerate Image**. Tab **Hardware**: Memory, Processors; **Hardware → Hard Disk →
Disk Action → Resize** (+Gb). Cuối cùng **Start**. Thứ tự quan trọng: sửa Cloud-Init **trước** lần Start đầu tiên.

**C. API (`curl`).** Clone là thao tác bất đồng bộ, trả về mã tác vụ (UPID); đợi tác vụ xong rồi mới cấu hình.

```bash
set -a; . infra/proxmox/.env.pve.deploy; set +a      # token GHI, file riêng, bị gitignore
H="Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}"
B="https://${PVE_HOST}:8006/api2/json/nodes/isec"
curl -sk -H "$H" -X POST "$B/qemu/9000/clone" \
  -d newid=202 -d name=ai-stg-01 -d full=1 -d pool=ai-assistant -d storage=local-lvm
# đợi xong: GET $B/tasks/<UPID>/status  → "status":"stopped","exitstatus":"OK"
curl -sk -H "$H" -X PUT "$B/qemu/202/config" \
  -d memory=4096 -d cores=2 -d ciuser=deploy \
  --data-urlencode "sshkeys=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(open(sys.argv[1]).read().strip(),safe=""))' ~/.ssh/deploy.pub)" \
  -d ipconfig0=ip=192.168.100.202/24,gw=192.168.100.1 -d nameserver=192.168.100.1
curl -sk -H "$H" -X PUT  "$B/qemu/202/resize" -d disk=scsi0 -d size=40G
curl -sk -H "$H" -X POST "$B/qemu/202/status/start"
```

Thao tác ghi cần token `deploy@pve!automation` (quyền ở mục 2.2), **không** dùng token chỉ đọc. Dùng file env riêng
(`.env.pve.deploy`) để token ghi không lẫn với token đọc.

**D. Ansible** (collection `community.proxmox`, module `proxmox_kvm`):

```yaml
- community.proxmox.proxmox_kvm:
    api_host: 192.168.100.252
    api_user: deploy@pve
    api_token_id: automation
    api_token_secret: "{{ pve_token_secret }}"   # lấy từ ansible-vault hoặc biến môi trường
    validate_certs: false                         # bù lại: kiểm fingerprint ở bước pre-check
    node: isec
    clone: ubuntu-2404-tmpl
    vmid: 9000
    newid: 202
    name: ai-stg-01
    full: true
    storage: local-lvm
    timeout: 300
```

**E. Terraform** (provider `bpg/proxmox`):

```hcl
resource "proxmox_virtual_environment_vm" "stg" {
  name      = "ai-stg-01"
  node_name = "isec"
  vm_id     = 202
  pool_id   = "ai-assistant"
  clone { vm_id = 9000 }
  cpu    { cores = 2 }
  memory { dedicated = 4096 }
  initialization {
    ip_config { ipv4 { address = "192.168.100.202/24"  gateway = "192.168.100.1" } }
    user_account { username = "deploy"  keys = [file("~/.ssh/deploy.pub")] }
  }
}
```

Chạy `terraform plan` để xem thay đổi trước khi `apply`. State của Terraform chứa thông tin nhạy cảm, **không** commit.

**F. Cài từ ISO (không dùng cloud-init).** Tải ISO lên storage `local` (Datacenter → `local` → ISO Images → Upload).
**Create VM** → tab OS chọn ISO, System bật **Qemu Agent**, Disks chọn `local-lvm`, Network `vmbr0`. Start → Console → cài OS
như máy thật; trong VM cài `qemu-guest-agent`. Cách này không lặp lại được, chỉ dùng khi buộc phải vậy; sau khi cài xong
nên **Convert to template** để lần sau clone.

**G. LXC (container nhẹ).** Dùng cho dịch vụ không cần kernel riêng. Tải template: node → `local` → CT Templates →
Templates → `ubuntu-24.04-standard`. Rồi:

```bash
pct create 204 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname ai-ci-01 --cores 1 --memory 1024 --swap 512 \
  --rootfs local-lvm:10 --net0 name=eth0,bridge=vmbr0,ip=192.168.100.204/24,gw=192.168.100.1 \
  --unprivileged 1 --features nesting=1 --ssh-public-keys /root/deploy.pub --pool ai-assistant --start 1
```

`nesting=1` cần nếu chạy Docker trong LXC. Tên file template có thể khác phiên bản; xem `pveam list local`.

**Nên chọn gì cho dự án này:** giai đoạn đầu dùng **A hoặc B** (hiểu rõ từng bước). Khi pipeline CI vào, chuyển sang **C hoặc D**.
**E** đáng làm khi hơn ~5 VM. **F** gần như không cần vì đã có template 9000.

### Xóa VM (an toàn)

Xóa là **không hoàn tác** và xóa luôn disk. Làm theo thứ tự:

1. Xem VM cần giữ gì: `pve-check` liệt kê VM; xác nhận id và tên **đúng** VM định xóa.
2. Nếu còn dữ liệu cần giữ, sao lưu trước. Node này chưa có job backup nào:
   `vzdump <id> --storage local --mode stop --compress zstd` (kiểm dung lượng `local` còn trống đủ không).
3. Tắt VM: `qm shutdown <id>` (hoặc `qm stop <id>` nếu treo).
4. Xóa: `qm destroy <id> --purge --destroy-unreferenced-disks 1`.
   `--purge` gỡ VM khỏi job backup và HA; không có nó, job backup còn tham chiếu id đã xóa.
5. Kiểm tra: `make pve-check`, VM đã biến mất, RAM giải phóng.

VM có `protection=1` không xóa được: bỏ cờ bằng `qm set <id> --protection 0`. **Prod nên bật protection.**

## 5. Cấu hình VM (Ansible)

Mục tiêu: VM mới thành "máy chạy được Docker Compose" mà không gõ tay, và **chạy lại bao nhiêu lần cũng được**
(idempotent: lần 2 phải báo `changed=0`).

### 5.1 Cài công cụ (một lần, trên máy dev)

Ansible nằm trong venv của dự án (đã bị `.gitignore`), không cài vào hệ thống:

```bash
python3 -m venv infra/proxmox/.venv
infra/proxmox/.venv/bin/pip install ansible-core
cd infra/proxmox/ansible
ANSIBLE_COLLECTIONS_PATH=collections ../.venv/bin/ansible-galaxy collection install community.general -p collections
```

### 5.2 Chạy

```bash
make pve-config ENV=staging            # áp thật
make pve-config ENV=staging CHECK=1    # chỉ xem thay đổi (--check --diff)
```

`CHECK=1` chỉ xem trước được một phần trên VM mới: gói chưa được cài thật nên các bước sau đó (dịch vụ, kho Docker)
có thể báo lỗi giả. Với VM mới, cứ áp thật rồi chạy lần 2 để kiểm tra `changed=0`.
Nếu Ansible báo `requires blocking IO on stdin/stdout/stderr`, chạy kèm `| cat` (xảy ra khi terminal là pipe không chặn).

### 5.3 Cấu trúc `infra/proxmox/ansible/`

| File | Công dụng |
|---|---|
| `ansible.cfg` | Khoá SSH riêng của dự án, `host_key_checking = accept-new`, sudo bật sẵn |
| `inventory.ini` | VM nào: `ai-stg-01` (.202, nhánh `uat`), `ai-prod-01` (.203, nhánh `prod`) |
| `group_vars/all.yml` | Dải LAN cho phép (`admin_cidr`), cổng web, URL repo, thư mục gốc `/srv/builder-ai` |
| `site.yml` | Playbook gọi ba role theo thứ tự `base` → `docker` → `app` |
| `roles/base` | Gói nền, guest agent, chrony, múi giờ, tự vá bảo mật, siết SSH, firewall |
| `roles/docker` | Docker Engine + Compose từ kho chính thức, xoay vòng log, nhóm `docker` |
| `roles/app` | Thư mục app, checkout nhánh môi trường, sinh `.env`, đặt biến theo môi trường |

### 5.4 Từng bước làm gì và vì sao

1. **Gói nền** (`qemu-guest-agent`, `chrony`, `ufw`, `git`, `make`...). Guest agent để Proxmox thấy IP và tắt máy êm.
   `chrony` thay `systemd-timesyncd` (apt tự gỡ bản cũ), giữ đồng hồ đúng cho log và token.
2. **Múi giờ** `Asia/Ho_Chi_Minh`, khớp `NEXT_PUBLIC_DISPLAY_TZ` của web.
3. **`unattended-upgrades`**: chỉ vá bảo mật, **không tự reboot** (reboot bất ngờ làm sập stack).
4. **Siết SSH** bằng file drop-in `/etc/ssh/sshd_config.d/99-hardening.conf` (tắt mật khẩu, tắt root, `MaxAuthTries 3`).
   File được kiểm cú pháp bằng `sshd -t` **trước khi ghi**: file lỗi thì sshd không lên và mất kết nối.
5. **Firewall `ufw`**: mặc định chặn vào, chỉ cho SSH (22) và web (3000) từ `192.168.100.0/24`.
   **Lưu ý:** Docker bỏ qua `ufw` cho cổng nó publish. Bảo vệ thật của DB/Redis là compose không publish cổng
   (`docker-compose.prod.yml` đã `ports: !override []`).
6. **Docker** từ kho `download.docker.com` (không dùng `docker.io` của Ubuntu vì cũ, thiếu Compose ≥ 2.24 cần cho `!override`).
   `daemon.json` giới hạn log mỗi container 10 MB x 3 file, nếu không log không xoay vòng sẽ đầy đĩa VM.
   User `deploy` vào nhóm `docker` (quyền tương đương root trên máy, chấp nhận vì VM chỉ phục vụ app).
7. **App**: thư mục `/srv/builder-ai/<env>`, checkout nhánh `uat` (staging) hoặc `prod`.
   `update: false` nên **không** ghi đè khi đã có (server chỉ `git pull`, không chỉnh tay, theo runbook).
8. **`.env`**: sinh một lần bằng `make env` (khoá ngẫu nhiên, `creates` làm task idempotent, **không ghi đè** nếu đã có
   vì đổi `API_KEY`/mật khẩu DB làm app và Postgres lệch nhau), rồi đặt `COMPOSE_PROJECT_NAME`, `ENVIRONMENT`, `CORS_ORIGINS`.

### 5.5 Kết quả đã kiểm chứng trên staging (2026-10-09)

| Kiểm tra | Kết quả |
|---|---|
| Áp lần 1 | `ok=25 changed=17 failed=0` |
| Áp lần 2 (idempotent) | `ok=23 changed=0 failed=0` |
| Docker / Compose | 29.8.2 / 5.6.0 (đủ ≥ 2.24) |
| `qemu-guest-agent`, `chrony`, `docker` | cả ba `active` |
| `ufw` | active, chỉ 22 và 3000 từ 192.168.100.0/24 |
| SSH | `passwordauthentication no`, `permitrootlogin no` |
| `.env` | `ENVIRONMENT=staging`, `COMPOSE_PROJECT_NAME=builder-staging`, `CORS_ORIGINS=http://192.168.100.202:3000` |

Mặc định web chỉ bind `127.0.0.1:3000` (compose). Muốn mở ra LAN cần override `docker-compose.lan.yml`
(`make lan-up`) hoặc đổi cổng publish khi deploy; firewall đã mở sẵn cổng 3000 cho LAN.

## 6. Cấu hình môi trường cho từng VM

`.env` trong `/srv/builder-ai/<env>` (sinh bằng `make env`, rồi sửa). Mỗi môi trường **khoá riêng**.

| Biến | staging | prod |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `builder-stg` | `builder-prod` |
| `ENVIRONMENT` | `staging` | `production` |
| `API_KEY`, mật khẩu Postgres, `JIRA` token | khác nhau | khác nhau |
| `CORS_ORIGINS` | `http://192.168.100.202:3000` | `http://192.168.100.203:3000` |
| `IMAGE_TAG` | do pipeline đặt | do pipeline đặt |

Quy tắc: không đặt secret trong git; không dùng chung `API_KEY` giữa staging và prod.

## 7. CI/CD với image

Repo đang **public**, nên GHCR kéo image công khai không cần token. Nếu chuyển private, tạo token
`read:packages` cho VM.

### 7.1 Luồng

| Sự kiện | Việc | Nơi chạy |
|---|---|---|
| Pull request | `ci.yml` có sẵn: ruff, alembic check, pytest, tsc, audit | GitHub |
| push `main` | test → build `api`, `web` → Trivy → push GHCR tag `sha-<7 ký tự>` | GitHub |
| push `uat` | deploy staging đúng SHA, chạy `make health` + `make smoke` | runner `.204` |
| push `prod` | chờ người duyệt → snapshot → backup → deploy → verify | runner `.204` |

Vì nhánh đi `main → uat → prod` theo fast-forward (xem [git-workflow.md](git-workflow.md)), cùng một SHA
đi từ staging lên prod; không build lại. Prod chạy đúng image đã qua staging.

### 7.2 Thiết lập một lần

1. **Runner tự host**: tạo LXC `ai-ci-01` (.204), cài GitHub Actions runner, gắn nhãn `proxmox`. Lý do:
   runner của GitHub không với được mạng LAN 192.168.100.x.
2. **GitHub Secrets**: khoá SSH deploy cho từng môi trường (key prod chỉ gắn vào Environment `production`).
3. **GitHub Environments**: tạo `staging` (không duyệt) và `production` (bắt buộc reviewer).
4. **Sửa compose** (`docker-compose.prod.yml`): thêm `image: ghcr.io/doanviethung1009/ai-assistant-api:${IMAGE_TAG}`
   và tương tự cho `web`, giữ `build:` làm dự phòng.
5. Lưu ý `NEXT_PUBLIC_DISPLAY_TZ` nhúng lúc build: image dùng chung nên múi giờ cố định ở bước build.

Chưa triển khai; xem trạng thái ở mục 0.

## 8. Quy trình deploy một bản mới

### 8.1 Lên staging (tự động)

1. Merge PR vào `main`. CI build image, push `sha-abc1234`.
2. Thăng cấp: `make promote-uat` (xem git-workflow.md). Pipeline deploy staging.
3. Xác nhận: `make health` và `make smoke` xanh; mở `http://192.168.100.202:3000` xem tay.

### 8.2 Lên prod (có duyệt)

1. Đạt các mục của "Checklist trước mỗi lần deploy production" trong [deploy-runbook.md](deploy-runbook.md).
2. Thăng cấp lên `prod`. Pipeline dừng chờ người duyệt trên GitHub.
3. Sau khi duyệt, pipeline chạy tuần tự:

| # | Bước | Lệnh trong pipeline | Dừng nếu |
|---|---|---|---|
| 1 | Pre-check | disk còn >20%, `docker compose version` ≥ 2.24 | fail |
| 2 | Snapshot | `qm snapshot 203 pre-<sha>` | fail |
| 3 | Backup DB | `make backup`, kiểm file không rỗng | rỗng |
| 4 | Kéo image | `docker compose pull` với `IMAGE_TAG` mới | tag không tồn tại |
| 5 | Up | `make prod-up` | container không lên |
| 6 | Migrate | `make migrate` | lỗi |
| 7 | Kiểm tra | `make health && make smoke` | fail → rollback |

4. Ghi lại SHA đã deploy, cập nhật `docs/AI_HANDOFF_STATE.md`.

### 8.3 Rollback

| Tình huống | Cách làm |
|---|---|
| Lỗi logic/UI, không đổi schema | Deploy lại `IMAGE_TAG` cũ (một lệnh, không build). Runbook Case 7. |
| Migration lùi được | `make downgrade` rồi deploy tag cũ. Runbook Case 8 đường A. |
| Migration phá dữ liệu | Restore backup DB (Case 8 đường B). Chỉ khi hỏng cả hệ thống mới `qm rollback 203 pre-<sha>`. |

Snapshot nằm cùng storage với VM nên **không thay thế backup**.

## 9. Backup và giám sát

- **Mỗi lần deploy**: `make backup` (pg_dump) + snapshot VM, như bảng 8.2.
- **Hằng đêm (prod)**: Datacenter → Backup → thêm job `vzdump` cho VM 203, giữ 7 bản, chế độ `snapshot`.
  Chép bản backup ra máy khác. Với một node, backup cùng ổ đĩa chỉ bảo vệ khỏi lỗi phần mềm, không phải hỏng ổ.
- **Khi có máy thứ hai**: Proxmox Backup Server.
- **Giám sát**: `prometheus-pve-exporter` vào profile `monitoring` có sẵn; cần token chỉ đọc (mục 2.1).

## 10. Tab "Hạ tầng" trên web (kế hoạch)

- **Giai đoạn A, chỉ đọc**: liệt kê VM, trạng thái, tài nguyên, SHA đang chạy ở staging/prod. Backend gọi Proxmox bằng
  token chỉ đọc; token không xuống browser. Phân trang 50 dòng/trang nếu danh sách dài.
- **Giai đoạn B, có hành động** (deploy, tạo instance): chỉ làm sau khi web có đăng nhập và phân quyền. Nút kích hoạt
  workflow GitHub, qua bước duyệt, không gọi Proxmox ghi trực tiếp.

## 11. Xử lý sự cố

| # | Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|---|
| 1 | `pve-check` thoát mã 3, hoặc thấy node nhưng RAM, storage, bridge trống; `/access/permissions` trả `{}` (HTTP 200); lỗi `Permission check failed (/nodes/isec, Sys.Audit)` | Token đăng nhập được nhưng không có quyền hiệu lực. **Nguyên nhân hay gặp nhất: ACL của token đúng nhưng user `readonly@pve` chưa có quyền** (token `privsep=1` chỉ có phần giao). Chạy `pveum acl modify / --users 'readonly@pve' --roles PVEAuditor` rồi `pveum acl list`: phải có đủ 2 dòng (user và token). Nguyên nhân khác: tên token trong ACL khác `.env.pve`; token bị xóa/tạo lại nên ACL cũ thành "invalid acl token" (gán lại ACL). |
| 2 | `pve-check` thoát mã 2 "Fingerprint TLS không khớp" | Proxmox đã cài lại hoặc bị chặn giữa đường. Nếu bạn chủ động cài lại, lấy mã mới trên node: `pvenode cert info` rồi cập nhật `PVE_TLS_FINGERPRINT`. Nếu không, **đừng** gửi token. |
| 3 | `401` khi gọi API | Sai `PVE_TOKEN_ID` hoặc secret. Secret chỉ hiện một lần: tạo lại token (`pveum user token remove` rồi `add`). |
| 4 | `qm clone` báo storage không hỗ trợ | Dùng storage có content `images` (xem `pve-check`), thường là `local-lvm` hoặc `local-zfs`. |
| 5 | VM lên nhưng không SSH được | Chưa có IP: kiểm tra `--ipconfig0`, bridge, gateway. Xem console VM trong web. |
| 6 | Guest agent không trả IP | Ảnh cloud gốc chưa có `qemu-guest-agent`; cài bằng Ansible (mục 5). |
| 7 | `docker compose` lỗi `!override` | Compose < 2.24. Cập nhật Docker (mục 5). |
| 8 | Pipeline không với được VM | Runner nằm ngoài LAN. Dùng runner tự host (mục 7.2). |
| 9 | `pve-vm` báo `HTTP 403 ... Permission check failed (/storage/local-lvm, Datastore.AllocateSpace)` (hoặc `/sdn/zones/localnetwork`, `SDN.Use`) | Token ghi thiếu quyền ở storage hoặc mạng. Chạy khối 8 lệnh "Gán lại toàn bộ quyền" ở mục 2.2 (4 đường dẫn, **cả user lẫn token**, từng lệnh riêng). Kiểm tra: `curl .../access/permissions` bằng token ghi phải liệt kê 4 đường dẫn: pool, `/vms/9000`, storage, sdn. |
| 10 | Script treo ở `[1/5]` mãi | Bản cũ của `pve-vm.sh` nuốt lỗi API và quay vòng chờ vô hạn. Đã sửa (`run_task`). Nếu tự viết script khác: đừng bọc lời gọi API trong `$(... \| ...)` mà không kiểm tra mã lỗi. |

## 12. Công cụ trong repo (tham chiếu)

| Thành phần | Công dụng | Cần gì |
|---|---|---|
| `infra/proxmox/.env.pve` | Token **đọc** (PVEAuditor) cho `pve-check` | tạo ở mục 2.1, 2.3 |
| `infra/proxmox/.env.pve.deploy` | Token **ghi** (AIDeploy, giới hạn pool `ai-assistant`) cho `pve-vm` | tạo ở mục 2.2 |
| `*.example` | Bản mẫu được commit; file thật bị `.gitignore` | `cp` rồi điền |
| `make pve-check` / `scripts/pve-check.sh` | Chỉ GET: phiên bản, node, storage, bridge, VM | token đọc |
| `make pve-vm ENV=...` / `scripts/pve-vm.sh` | Clone template 9000 → cấu hình cloud-init → nới disk → bật → chờ SSH | token ghi + khoá SSH |
| `~/.ssh/ai_assistant_deploy(.pub)` | Cặp khoá ed25519 riêng cho dự án; khoá công khai nạp vào VM, người dùng `deploy` | `ssh-keygen -t ed25519 -f ~/.ssh/ai_assistant_deploy` |

Mã thoát: `pve-check` 0 = ổn, 2 = fingerprint TLS lệch, 3 = token chưa có quyền. `pve-vm` 0 = xong (hoặc VM đã có, không làm gì),
1 = Proxmox từ chối (đọc dòng `LỖI ... HTTP ...`), 2 = fingerprint lệch, 3 = VM lên nhưng SSH chưa mở.

Môi trường hỗ trợ: `dev` (id 201, 2.5 GB, 30 GB), `staging` (202, 3 GB, 40 GB), `prod` (203, 5 GB, 60 GB, tự bật `protection`).

Quy ước thiết kế của `pve-vm`: **idempotent** (VM id đã có thì dừng, không bao giờ ghi đè), id VM = octet cuối IP,
tag `env-<tên>`, prod tự bật `protection`. Thêm cờ `DRY=1` để chỉ in kế hoạch: `make pve-vm ENV=staging DRY=1`.

## 13. Dựng VM bằng `make pve-vm`

```bash
make pve-vm ENV=staging DRY=1   # xem kế hoạch, không đổi gì
make pve-vm ENV=staging         # dựng thật (khoảng 1-2 phút)
ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.202 'hostname; cloud-init status --wait'
```

Lần khởi động đầu mất khoảng 2-4 phút: cloud-init nâng cấp gói rồi **tự reboot**, nên SSH có thể báo
`Connection refused` rồi tự hết. Đợi `cloud-init status` ra `done` (đừng dùng `--wait` qua SSH, nó treo khi VM reboot giữa chừng).
Kết quả đã kiểm chứng trên staging: Ubuntu 24.04.5, 3 GB RAM, disk 38 GB, người dùng `deploy` có `sudo` không cần mật khẩu.
Lưu ý: `qemu-guest-agent` chưa chạy (`inactive`) cho tới khi Ansible cài ở mục 5, nên giao diện Proxmox chưa hiện IP của VM.

Điều kiện: mục 2.2 xong (token ghi, **đủ quyền ở 4 đường dẫn**), `.env.pve.deploy` đã điền, khoá SSH đã tạo.
Sau đó chuyển sang mục 5 (cấu hình VM) và mục 8 (deploy).

**Không chạy script bằng `bash -x`**: chế độ trace in cả header `Authorization` có secret token ra màn hình/log.

## 14. Bảo mật tóm tắt

- Token chỉ đọc cho quan sát; token ghi chỉ cho pipeline có duyệt. Không dùng `root@pam`.
- Ghim fingerprint TLS, không `curl -k` trần.
- Secret chỉ ở `.env.pve` (bị gitignore) và GitHub Secrets. Không dán vào chat, không commit.
- Cổng 8006 chỉ cho dải quản trị; prod nên ở VLAN riêng nếu hạ tầng hỗ trợ.
- Nội dung từ nguồn ngoài (log, Jira) là dữ liệu không đáng tin, không bao giờ nâng thành lệnh.

# Template Proxmox và đề xuất tạo instance

Cập nhật: 2026-10-09. Giải thích **template là gì, template 9000 của dự án chứa gì, cách làm mới nó**, rồi **đề xuất cách
tạo instance (VM/LXC) hiệu quả** cho dự án. Thao tác từng bước nằm ở [PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md); vận hành hằng
ngày ở [PROXMOX_OPERATIONS.md](PROXMOX_OPERATIONS.md).

## 1. Template là gì

Trong Proxmox có **ba thứ khác nhau cùng được gọi là "template"**. Đừng nhầm:

| Loại | Là gì | Dùng để | Nằm ở đâu | Ví dụ trong dự án |
|---|---|---|---|---|
| **VM template** | Một VM được đánh dấu `template: 1`: khóa lại, không bật được, chỉ để **nhân bản** | Dựng VM mới trong vài giây | Trong cây VM, cùng nơi lưu disk VM (`local-lvm`) | **9000 `ubuntu-2404-tmpl`** |
| **Cloud image** | File ảnh đĩa gốc của hãng phân phối (`.img`), đã cài sẵn `cloud-init` | Nguyên liệu để **tạo** VM template | Tải về, nhập vào VM bằng `import-from` | `noble-server-cloudimg-amd64.img` (Ubuntu 24.04) |
| **LXC template** (`vztmpl`) | Gói rootfs nén (`.tar.zst`) cho container | Tạo container LXC | Storage `local` (nội dung `vztmpl`) | `ubuntu-24.04-standard_...tar.zst` |
| ISO | Đĩa cài đặt | Cài OS thủ công như máy thật | Storage `local` (nội dung `iso`) | chưa dùng |

Hiểu ngắn gọn: **cloud image → (một lần) → VM template → (mỗi lần) → VM chạy được**.

## 2. Template 9000 của dự án (đo thực tế)

Đọc bằng `qm config 9000` trên node (hoặc API `GET /nodes/isec/qemu/9000/config`):

| Trường | Giá trị | Ý nghĩa |
|---|---|---|
| `name` | `ubuntu-2404-tmpl` | Tên gợi nhớ |
| `template` | `1` | Đã khóa thành template, **không bật được** |
| `scsi0` | `local-lvm:base-9000-disk-0`, 3.5 GB | Disk gốc, tiền tố **`base-`** nghĩa là chỉ đọc và dùng làm nguồn clone |
| `ide2` | `local-lvm:vm-9000-cloudinit` | Ổ cloud-init (xem mục 3) |
| `memory` / `cores` | 2048 MB / 2 | Mặc định; VM con ghi đè được |
| `net0` | `virtio`, bridge `vmbr0` | Card mạng |
| `agent` | `enabled=1` | Mở kênh QEMU guest agent; **gói `qemu-guest-agent` chưa cài trong ảnh**, Ansible cài sau |
| `scsihw` | `virtio-scsi-single` | Bộ điều khiển đĩa nhanh |
| `serial0` / `vga` | `socket` / `serial0` | Console qua cổng serial (cloud image không có màn hình đồ họa) |
| `ostype` | `l26` | Linux kernel 2.6+ |

**Template chỉ chứa Ubuntu "trống"**: chưa có Docker, user, khóa SSH, firewall. Mọi thứ riêng của dự án được gắn vào
**sau khi clone** bằng cloud-init (user, khóa, IP) và Ansible (Docker, firewall...). Đây là chủ ý: template càng ít thứ
thì càng ít khi phải làm lại và càng không lỗi thời.

## 3. Cloud-init hoạt động ra sao

Cloud-init là chương trình chạy **ở lần khởi động đầu tiên** của VM, đọc cấu hình từ một "đĩa cấu hình" gắn kèm rồi
tự thiết lập máy. Proxmox tạo đĩa này (ổ `ide2` dạng CD-ROM) từ các trường bạn đặt:

| Bạn đặt (`qm set` / API) | Cloud-init làm |
|---|---|
| `ciuser=deploy` | Tạo user `deploy` (có `sudo` không mật khẩu) |
| `sshkeys=...` | Ghi khóa công khai vào `authorized_keys` |
| `ipconfig0=ip=192.168.100.202/24,gw=...` | Đặt IP tĩnh |
| `nameserver=...` | Đặt DNS |
| `ciupgrade=1` (mặc định) | `apt upgrade` ở lần boot đầu, **rồi có thể tự reboot** (nên SSH có lúc `Connection refused`) |

Hệ quả cần nhớ:
1. Sửa cloud-init **phải trước lần bật đầu**; sau đó cloud-init không chạy lại cấu hình mạng/user (đã "xong").
2. Đổi IP về sau: `qm set <id> --ipconfig0 ...` rồi **tắt/bật** VM (hoặc `qm cloudinit update <id>`); trong VM có thể cần
   `sudo cloud-init clean --logs && sudo reboot` để chạy lại.
3. Mật khẩu **không** đặt (chỉ khóa SSH), đúng nguyên tắc dự án.
4. Mỗi VM clone có `machine-id`/khóa host SSH riêng (cloud-init tạo mới), không trùng giữa các VM.

## 4. Clone: đầy đủ hay liên kết

| | Full clone (dự án đang dùng) | Linked clone |
|---|---|---|
| Disk | Bản sao độc lập | Chia sẻ disk `base-` của template, chỉ ghi phần thay đổi |
| Tốc độ / dung lượng | Chậm hơn, tốn thêm dung lượng | Gần như tức thì, rất nhẹ |
| Phụ thuộc | Không | **Không xóa được template** khi còn VM con; hỏng template là hỏng VM con |
| Hợp với | VM sống lâu (staging, prod) | VM tạm, thử nghiệm, môi trường xem trước |

Dự án dùng **full clone** (`full=1` trong `pve-vm.sh`) vì VM sống lâu và cần độc lập với template. Linked clone chỉ nên
dùng cho VM dùng một lần (mục 7.3).

## 5. Vòng đời template: làm mới, đặt tên, chọn bản

### 5.1 Khi nào làm template mới
Ubuntu ra bản mới, cần gói mặc định mới, hoặc template cũ quá lâu (clone xong phải tải quá nhiều bản vá).
**Không sửa template đang dùng**: tạo template mới với id khác, thử, rồi mới chuyển.

### 5.2 Quy ước
- Id `9000-9099` dành cho template. Tên có ngày: `ubuntu-2404-tmpl-20261009`.
- Template đang dùng ghi ở `PVE_TEMPLATE_ID` (`infra/proxmox/.env.pve.deploy`). Đổi biến này là chuyển bản.
- Giữ bản cũ một thời gian để lùi lại; xóa khi chắc chắn (`qm destroy 9000 --purge`).

### 5.3 Làm template mới từ cloud image (trên node)

```bash
cd /var/lib/vz/template/iso
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img   # kiểm tra checksum trên trang hãng

qm create 9001 --name ubuntu-2404-tmpl-20261009 --memory 2048 --cores 2 \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --agent enabled=1 --ostype l26
qm set 9001 --scsi0 local-lvm:0,import-from=/var/lib/vz/template/iso/noble-server-cloudimg-amd64.img
qm set 9001 --ide2 local-lvm:cloudinit
qm set 9001 --boot order=scsi0 --serial0 socket --vga serial0
qm template 9001
```

Thử template mới: `PVE_TEMPLATE_ID=9001 make pve-vm ENV=staging` trên một id/VM thử, `make pve-config`, rồi mới đổi mặc định.

### 5.4 "Golden image": nhúng sẵn gói vào template (tùy chọn, đề xuất giai đoạn sau)

Hiện mỗi VM mới mất vài phút cài `qemu-guest-agent`, Docker, vá bảo mật bằng Ansible. Có thể **nướng sẵn** vào ảnh gốc
trước khi biến thành template, bằng `virt-customize` (gói `libguestfs-tools`):

```bash
apt install -y libguestfs-tools
virt-customize -a noble-server-cloudimg-amd64.img \
  --install qemu-guest-agent,chrony,ufw,git,make \
  --run-command 'systemctl enable qemu-guest-agent'
```

| | Template trống (hiện tại) | Golden image |
|---|---|---|
| Thời gian dựng VM | ~5-8 phút (Ansible cài hết) | ~1-2 phút |
| Độ mới của gói | Luôn mới nhất khi dựng | Cũ dần, phải làm lại định kỳ |
| Bảo trì | Không cần | Phải có quy trình làm mới (mục 5.3) và lịch (hàng tháng) |
| Rủi ro | Thấp | Template lỗi thời gây lệch giữa VM cũ và mới |

Khuyến nghị: **giữ template trống** cho tới khi có ≥ 5 VM hoặc thời gian dựng thành vấn đề; Ansible vẫn là nguồn sự thật,
golden image chỉ là tối ưu tốc độ (và Ansible vẫn phải chạy được trên ảnh trống).

## 6. LXC template (cho container)

Dùng cho dịch vụ nhẹ như runner CI. Container chia sẻ kernel của node nên **nhẹ hơn VM nhiều** nhưng cô lập yếu hơn.

```bash
pveam update
pveam available --section system | grep ubuntu-24
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
pveam list local
```

Tạo container: `pct create` (PROXMOX_DEPLOY.md mục 4, cách G). Không chạy prod chính trong LXC; Docker trong LXC cần
`nesting=1` và làm yếu cô lập.

## 7. Đề xuất cách tạo instance cho dự án

### 7.1 Nguyên tắc (áp dụng cho mọi cách tạo)

1. **Khai báo, không gõ tay**: mỗi instance được mô tả ở một chỗ duy nhất (id, tên, IP, cấu hình), VM sinh ra từ mô tả đó.
2. **Mọi instance dựng được lại từ code**: VM chỉ là hạ tầng bỏ đi; **dữ liệu** mới là thứ cần backup.
3. **Idempotent**: chạy lại không phá cái đã có.
4. **Quyền tối thiểu**: tạo instance chỉ trong pool `ai-assistant`, bằng token riêng, không `root`.
5. **Có người duyệt** cho prod; tự động cho staging/dev tạm.
6. **Tính ngân sách tài nguyên trước khi tạo** (RAM 15.5 GB, thin pool; xem PROXMOX_OPERATIONS.md mục 3, 6).

### 7.2 Quy ước đặt id, tên, IP, cỡ máy

| Hạng mục | Quy ước đề xuất |
|---|---|
| Id VM | = octet cuối của IP. Dải dự án: 200-249 |
| Tên | `ai-<vai trò>-<số>`: `ai-stg-01`, `ai-prod-01`, `ai-ci-01` |
| IP | 192.168.100.200-249 cấp tĩnh theo bảng, **không** dùng DHCP |
| Tag | `env-staging`, `env-prod`, `role-ci`... để lọc và đặt quyền |
| Pool | `ai-assistant` cho mọi instance của dự án |

Cỡ máy (profile) để khỏi nghĩ lại mỗi lần:

| Profile | vCPU | RAM | Disk | Dùng cho |
|---|---|---|---|---|
| `small` | 1 | 1 GB | 10 GB | runner CI, exporter (LXC) |
| `medium` | 2 | 3 GB | 40 GB | staging, dev tạm |
| `large` | 2 | 5 GB | 60 GB (+40 GB dữ liệu) | prod |

Bảng cấp IP hiện tại:

| IP | Dùng cho | Trạng thái |
|---|---|---|
| .201 | dev (dự trữ) | trống |
| .202 | staging `ai-stg-01` | **đã dựng** |
| .203 | prod `ai-prod-01` | kế hoạch |
| .204 | runner CI `ai-ci-01` (LXC) | kế hoạch |
| .205-.249 | instance tạm / mở rộng | trống |

### 7.3 Ba mức tự động hóa (chọn theo giai đoạn)

| Mức | Cách | Khi nào | Công sức | Ghi chú |
|---|---|---|---|---|
| **1. Script theo môi trường** (đang có) | `make pve-vm ENV=staging\|prod` + `make pve-config` | Bây giờ, 2-3 VM | Đã xong | Thông số cứng trong `pve-vm.sh` |
| **2. Danh mục instance (đề xuất làm tiếp)** | Một file `infra/proxmox/instances.yml` là nguồn sự thật; `make pve-up` đọc file và dựng cái còn thiếu | 4-10 VM, có instance tạm | Nhỏ-vừa | Thêm instance = thêm 6 dòng YAML + chạy lệnh |
| **3. Terraform + Ansible** | Terraform (`bpg/proxmox`) quản vòng đời VM, Ansible cấu hình | > 10 VM, nhiều người | Lớn hơn | `plan` thấy diff trước khi áp; state là dữ liệu nhạy cảm |

**Đề xuất cụ thể cho mức 2** (nên làm sau khi staging/prod chạy ổn):

```yaml
# infra/proxmox/instances.yml  (bản phác thảo)
profiles:
  small:  {cores: 1, memory: 1024, disk: 10G, kind: lxc}
  medium: {cores: 2, memory: 3072, disk: 40G, kind: vm}
  large:  {cores: 2, memory: 5120, disk: 60G, kind: vm, data_disk: 40G, protection: true}
instances:
  - {id: 202, name: ai-stg-01,  ip: 192.168.100.202, profile: medium, env: staging, branch: uat}
  - {id: 203, name: ai-prod-01, ip: 192.168.100.203, profile: large,  env: prod,    branch: prod}
  - {id: 204, name: ai-ci-01,   ip: 192.168.100.204, profile: small,  role: ci}
```

`pve-up` đọc file, so với danh sách VM hiện có (`pve-check`), và chỉ **tạo cái thiếu**; không bao giờ xóa hay sửa cái có sẵn
(xóa luôn là thao tác tay có xác nhận). Inventory Ansible cũng sinh từ cùng file này để IP không lệch giữa hai nơi.

### 7.4 Quy trình cấp một instance mới (checklist)

1. Xác định **mục đích và vòng đời** (vĩnh viễn hay tạm, có dữ liệu cần giữ không).
2. Chọn profile, kiểm ngân sách RAM/disk (`make pve-check`; còn dư ≥ 2 GB RAM sau khi cộng VM mới).
3. Cấp id/IP/tên theo mục 7.2, ghi vào danh mục.
4. Dựng: `make pve-vm ...` (hoặc `make pve-up` khi có mức 2), đợi `cloud-init status` = `done`.
5. Cấu hình: `make pve-config ...`, chạy lần 2 phải `changed=0`.
6. Bật bảo vệ cho VM quan trọng: `qm set <id> --protection 1`; thêm vào job backup nếu có dữ liệu.
7. Ghi vào bảng hiện trạng (PROXMOX_OPERATIONS.md mục 1) và cập nhật `docs/AI_HANDOFF_STATE.md`.

### 7.5 Instance tạm (preview theo nhánh, đề xuất mở rộng)

Cho mỗi PR có thể dựng một VM **linked clone** nhỏ, đẩy image của PR lên, cho người xem, rồi tự xóa khi đóng PR. Điều kiện:
- Giới hạn số lượng đồng thời (ví dụ ≤ 2) và **TTL** (tự xóa sau 3 ngày) để khỏi cạn RAM.
- Đặt tag `ephemeral`; chỉ job dọn dẹp được xóa VM mang tag này (quyền xóa chỉ trên tag/pool đó).
- Dùng IP trong dải .205-.249 cấp theo số PR.
Với một node 16 GB chưa cần ngay; ghi lại để khi muốn "xem thử trước khi merge" thì làm.

### 7.6 Tạo instance từ web (giai đoạn B của tab Hạ tầng)

Nút "Tạo instance" không gọi Proxmox trực tiếp. Luồng an toàn:
1. Người dùng (đã đăng nhập, có quyền) chọn profile + mục đích trên web.
2. Web kích hoạt workflow GitHub (`workflow_dispatch`) với tham số đó.
3. Workflow chạy trên runner tự host: kiểm ngân sách, chờ duyệt (prod) rồi gọi `pve-up`.
4. Kết quả ghi lại và hiện trên web.

Điều kiện tiên quyết: **web có đăng nhập và phân quyền** (hiện chưa có). Trước đó, tab chỉ **đọc** (giai đoạn A).

## 8. Tóm tắt khuyến nghị

1. Giữ **template trống 9000**, làm bản mới theo mục 5.3 khi cần; chưa cần golden image.
2. Dùng **full clone** cho VM sống lâu, linked clone chỉ cho VM tạm.
3. Giai đoạn này: tiếp tục `make pve-vm` + `make pve-config`; **làm mức 2 (danh mục `instances.yml`)** ngay sau khi dựng
   xong prod và runner, để thêm instance chỉ là thêm một dòng.
4. Terraform và instance tạm theo PR: để sau, khi số instance hoặc số người tăng.

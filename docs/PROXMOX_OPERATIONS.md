# Vận hành server Proxmox

Cập nhật: 2026-10-09. Tài liệu này dành cho **việc hằng ngày sau khi hạ tầng đã dựng**: kiểm tra sức khỏe, quản lý
VM, snapshot/backup, cập nhật, xoay token, xử lý sự cố. Cách dựng ban đầu nằm ở
[PROXMOX_DEPLOY.md](PROXMOX_DEPLOY.md); thiết kế và lý do ở [spec](specs/proxmox-deploy.md).

## 1. Hiện trạng (đo bằng `make pve-check`, 2026-10-09)

| Mục | Giá trị |
|---|---|
| Server | node `isec`, Proxmox VE 9.1.11, `https://192.168.100.252:8006`, SSH 22 |
| Phần cứng | 6 nhân, RAM 15.5 GB, swap 8 GB, disk gốc 94 GB (`local`), thin pool `local-lvm` 794 GB |
| Mạng | một bridge `vmbr0` = 192.168.100.252/24, gateway 192.168.100.1 |
| TLS | tự ký, CN `isec.dbahomeslab.com`, hạn 2028-02-29, fingerprint trong `infra/proxmox/.env.pve` |

| VM / ID | Vai trò | IP | RAM | Trạng thái |
|---|---|---|---|---|
| 100 `isec-vpn-gateway` | VPN gateway (**không thuộc dự án, không động vào**) | — | 2 GB | chạy, `onboot=1` |
| 201 `ai-dev-01` | dev (nhánh `main`, hot reload) | 192.168.100.201 | 2.5 GB | chạy, Docker cài; stack dựng bằng `make up` |
| 202 `ai-stg-01` | staging | 192.168.100.202 | 3 GB | chạy, Docker + stack đã deploy thử |
| 203 `ai-prod-01` | prod | 192.168.100.203 | 5 GB | chạy, đã cấu hình Ansible, `protection=1`; chưa deploy stack |
| 9000 `ubuntu-2404-tmpl` | template Ubuntu 24.04 cloud-init | — | — | template, không bật |
| 140, 150 | VM cũ (`agent-hub`, `jump-host-hub`) | — | — | **tắt**, chờ xóa hoặc giữ |

Danh tính và thông tin truy cập:

| Đối tượng | Dùng cho | Quyền | File |
|---|---|---|---|
| `readonly@pve!audit` | `make pve-check`, tab web giai đoạn A | PVEAuditor (chỉ đọc) | `infra/proxmox/.env.pve` |
| `deploy@pve!automation` | `make pve-vm`, CI | AIDeploy, giới hạn pool `ai-assistant` | `infra/proxmox/.env.pve.deploy` |
| Khóa SSH `~/.ssh/ai_assistant_deploy` | SSH vào VM, user `deploy` (sudo không mật khẩu) | — | máy dev |
| `root@pam` | quản trị tay trên giao diện web | toàn quyền | **không** dùng cho tự động hóa |

## 1b. Truy cập SSH vào node và các VM (đọc trước khi làm việc trên server)

| Đích | Lệnh | Xác thực | Ghi chú |
|---|---|---|---|
| Node Proxmox `isec` | `ssh root@192.168.100.252` | tài khoản `root` của **chủ hạ tầng** | Mật khẩu/khóa root **không** lưu trong repo, agent AI không có. Việc gì cần `qm`/`pveum` trên node thì người dùng tự chạy, hoặc dùng giao diện web (node → Shell) |
| VM dev `ai-dev-01` | `ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.201` | như trên | Mã nguồn tại `/srv/builder-ai/dev` (nhánh `main`) |
| VM staging `ai-stg-01` | `ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.202` | khóa `ai_assistant_deploy`, user `deploy`, sudo không mật khẩu | Mã nguồn tại `/srv/builder-ai/staging` |
| VM prod `ai-prod-01` | `ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.203` | như trên | Mã nguồn tại `/srv/builder-ai/prod`; có `protection=1` |

Gợi ý thêm vào `~/.ssh/config` để gõ ngắn (`ssh ai-dev`, `ssh ai-stg`, `ssh ai-prod`):

```
Host ai-dev
  HostName 192.168.100.201
Host ai-stg
  HostName 192.168.100.202
Host ai-prod
  HostName 192.168.100.203
Host ai-dev ai-stg ai-prod
  User deploy
  IdentityFile ~/.ssh/ai_assistant_deploy
  IdentitiesOnly yes
```

Điều cần biết:
- **Chỉ đăng nhập bằng khóa.** Mật khẩu SSH và đăng nhập root trên VM đã bị tắt (Ansible `roles/base`); firewall chỉ cho
  SSH từ `192.168.100.0/24`, nên phải ở trong LAN.
- **Khóa riêng nằm ở `~/.ssh/ai_assistant_deploy` trên máy dev** (quyền 600, không passphrase để tự động hóa), **không** trong repo.
  Khóa công khai `.pub` được cloud-init nạp vào VM lúc dựng. Mất khóa thì không SSH được: phải dựng lại VM hoặc nạp khóa mới qua
  `qm set <id> --sshkeys` rồi khởi động lại (mục PROXMOX_TEMPLATES.md 3).
- **Máy/phiên khác muốn SSH:** copy khóa riêng sang máy đó qua kênh an toàn (không qua chat/email), `chmod 600`.
  Các file `infra/proxmox/.env.pve` và `.env.pve.deploy` (token API) cũng **không có trong git**.
- **Session AI chạy trong worktree riêng** là một bản checkout sạch của git: không có file bị `.gitignore` (token, `.env*`) và
  không thấy tài liệu/mã chưa commit. Khóa SSH thì dùng chung được vì nằm ở thư mục home (`~/.ssh`). Với token, trỏ script tới
  file gốc bằng biến môi trường thay vì copy: `PVE_ENV_FILE=/đường/dẫn/.env.pve make pve-check` và
  `PVE_DEPLOY_ENV_FILE=/đường/dẫn/.env.pve.deploy make pve-vm ENV=staging`.
- Vào VM để xem trạng thái app: `ssh ai-stg 'cd /srv/builder-ai/staging && make ps'`; log: `make logs-api`.
- Nguyên tắc dự án: agent không có quyền ghi thường trực lên production. SSH vào **prod** chỉ để đọc/chẩn đoán, thay đổi đi qua
  pipeline/runbook có duyệt.

## 2. Lịch kiểm tra định kỳ

| Tần suất | Việc | Cách làm | Ngưỡng cần hành động |
|---|---|---|---|
| Hằng ngày / khi mở máy | Tổng quan | `make pve-check` | VM mong đợi không `running`; RAM đã dùng > 85% |
| Hằng tuần | Dung lượng thin pool | `lvs` trên node, cột `Data%` | > 80% là cảnh báo, **> 90% nguy hiểm** (mục 6.2) |
| Hằng tuần | Bản vá hệ điều hành VM | `make pve-config ENV=<env>` (hoặc để `unattended-upgrades`) | cần reboot (`/var/run/reboot-required`) |
| Hằng tháng | Cập nhật Proxmox | mục 7 | luôn đọc release notes trước |
| Hằng tháng | Thử restore backup | mục 5.3 | restore thất bại = coi như chưa có backup |
| Hằng quý | Xoay token | mục 8 | token lộ hoặc người rời nhóm: xoay ngay |
| Khi cài lại Proxmox | Cập nhật fingerprint TLS | mục 9.2 | `pve-check` thoát mã 2 |

## 3. Việc hằng ngày với VM

Chạy trong **Shell của node** (web: node `isec` → Shell) hoặc SSH vào `root@192.168.100.252`.

```bash
qm list                          # danh sách VM, trạng thái, RAM
qm status 202                    # trạng thái một VM
qm config 202                    # cấu hình đầy đủ (CPU, RAM, disk, cloud-init)
qm shutdown 202 --timeout 90     # tắt êm (cần guest agent); quá hạn mới dùng qm stop
qm start 202
qm reboot 202
qm stop 202                      # tắt cứng, như rút điện: chỉ khi shutdown treo
qm agent 202 ping                # guest agent trả lời không (cần agent chạy trong VM)
```

SSH vào VM dự án: `ssh -i ~/.ssh/ai_assistant_deploy deploy@192.168.100.202`.

Đổi tài nguyên:

```bash
qm set 202 --memory 4096         # RAM: áp dụng sau khi tắt/bật VM
qm set 202 --cores 2
qm resize 202 scsi0 +10G         # nới disk (CHỈ nới, không thu nhỏ được)
```

Sau khi nới disk, cloud-init thường tự nới phân vùng gốc ở lần boot; nếu chưa, trong VM:
`sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1`.

**Ngân sách RAM.** Tổng RAM đã cấp cho VM đang chạy + khoảng 2 GB cho host phải nhỏ hơn 15.5 GB. Hiện: 2 (vpn) + 2.5
(dev) + 3 (staging) + 5 (prod) = 12.5 GB đã cấp, **sát giới hạn** (đo thực tế thấp hơn nhiều vì VM ít việc, swap 8 GB đỡ phần còn lại).
Chưa còn chỗ cho runner CI (1 GB): muốn thêm thì tắt dev khi không dùng (`qm shutdown 201`) hoặc hạ cấu hình. Dựng thêm VM phải cộng vào bảng này
trước. Không overcommit RAM cho prod.

**Thứ tự khởi động sau khi node reboot.** VM có `onboot=1` tự bật; đặt thứ tự để phụ thuộc lên trước:

```bash
qm set 100 --startup order=1,up=30     # VPN lên trước, chờ 30 giây
qm set 203 --startup order=2,up=20     # prod
qm set 202 --startup order=3           # staging
```

## 4. Snapshot (lùi nhanh, không phải backup)

```bash
qm snapshot 202 pre-deploy --description "trước deploy sha-abc1234"
qm listsnapshot 202
qm rollback 202 pre-deploy            # VM quay về đúng trạng thái snapshot (mất mọi thay đổi sau đó)
qm delsnapshot 202 pre-deploy         # dọn khi không cần
```

- Snapshot nằm **cùng thin pool** với VM: mất ổ là mất cả hai. Nó chỉ để lùi nhanh sau thao tác rủi ro.
- Snapshot cũ làm VM chậm dần và ăn dung lượng thin pool. Xóa snapshot sau khi deploy ổn định (vài ngày).
- Pipeline deploy chụp `pre-<sha>` trước mỗi lần lên prod (PROXMOX_DEPLOY.md mục 8.2).

## 5. Backup và restore

### 5.1 Hiện trạng

**Chưa có job backup nào** (đã kiểm tra: không có job, không có file trong `local`). Việc đầu tiên nên làm trước khi
có dữ liệu thật trên prod.

### 5.2 Tạo job backup hằng đêm (giao diện)

Datacenter → **Backup** → **Add**: Storage `local`, Schedule `02:00`, Selection mode *Include selected VMs* chọn 203 (và
202 nếu muốn), Mode **Snapshot**, Compression **ZSTD**, Retention *Keep Last* 7. Lưu ý `local` chỉ còn khoảng
80 GB: tính trước (VM 60 GB nén thường còn một phần ba, nhưng kiểm tra bằng thực tế).

Backup tay một VM:

```bash
vzdump 203 --storage local --mode snapshot --compress zstd
ls -lh /var/lib/vz/dump/
```

### 5.3 Restore (và thử restore định kỳ)

```bash
# Restore thành VM mới để THỬ, không ghi đè bản thật (id 900 là ví dụ trống)
qmrestore /var/lib/vz/dump/vzdump-qemu-203-<ngày>.vma.zst 900 --storage local-lvm
qm set 900 --ipconfig0 ip=192.168.100.250/24,gw=192.168.100.1   # đổi IP để không trùng với bản thật
qm start 900   # kiểm tra, rồi xóa: qm stop 900; qm destroy 900 --purge
```

Restore đè VM đang có chỉ khi hỏng thật, thêm `--force`, và **tắt VM trước**.

### 5.4 Sao lưu ra ngoài node

Một node duy nhất thì backup nằm cùng máy chỉ chống được lỗi phần mềm, không chống được hỏng ổ. Chép định kỳ
`/var/lib/vz/dump/` sang máy khác (`rsync`) hoặc dựng Proxmox Backup Server khi có máy thứ hai. Dữ liệu ứng dụng còn có
`make backup` (pg_dump) bên trong VM, xem [deploy-runbook.md](deploy-runbook.md).

## 6. Dung lượng

### 6.1 Xem nhanh

```bash
pvesm status                      # mọi storage, dung lượng
lvs                               # thin pool + từng disk VM, xem cột Data%
df -h /var/lib/vz                 # storage "local" (iso, backup)
```

### 6.2 Thin pool đầy là sự cố nghiêm trọng

`local-lvm` là LVM-thin: cấp phát lười, nên tổng disk đã cấp cho VM có thể lớn hơn dung lượng thật. Khi `Data%`
chạm 100% các VM bị treo hoặc hỏng dữ liệu. Cách phòng: không để quá 80%; xóa snapshot và VM thừa; không nới disk
bừa. Muốn giải phóng: `qm destroy <id> --purge --destroy-unreferenced-disks 1` cho VM bỏ đi (đã backup nếu cần).

### 6.3 Disk "mồ côi"

Khi xóa VM sai cách có thể còn disk thừa: `lvs` thấy `vm-<id>-disk-N` mà không VM nào dùng. Kiểm tra
`qm config <id>` và `pvesm list local-lvm`, xóa bằng `pvesm free local-lvm:vm-<id>-disk-N` **sau khi chắc chắn**.

## 7. Cập nhật Proxmox

1. Đọc release notes; chọn giờ ít dùng. Có backup VM quan trọng.
2. Kho gói: node không có subscription thì kho `enterprise` báo lỗi 401. Node → **Updates** → **Repositories**: tắt kho
   *enterprise*, bật *No-Subscription*. (Phù hợp môi trường test; môi trường quan trọng nên mua subscription.)
3. Cập nhật: node → **Updates** → *Refresh* → *Upgrade*, hoặc Shell: `apt update && apt dist-upgrade`.
   Không dùng `apt upgrade` (không xử lý đổi phụ thuộc của Proxmox).
4. Kernel mới thì phải **reboot node**: tắt êm các VM (`qm shutdown`), reboot, kiểm tra VM `onboot` đã lên (`qm list`),
   rồi `make pve-check`.
5. Kiểm tra phiên bản: `pveversion -v | head`.

Reboot node làm **VPN gateway (100) ngắt**, chọn thời điểm không ai cần VPN.

## 8. Xoay token và quản lý quyền

Xoay khi: secret từng bị lộ (đã xảy ra: secret đã hiện trong chat), người dùng rời nhóm, định kỳ mỗi quý.

```bash
pveum user token list readonly@pve          # xem token hiện có
pveum user token remove deploy@pve automation
pveum user token add deploy@pve automation --privsep 1     # IN SECRET MỘT LẦN: lưu ngay vào .env.pve.deploy
# Xóa token làm ACL của nó thành "invalid": gán lại cả 8 lệnh ở PROXMOX_DEPLOY.md mục 2.2
pveum acl list | grep deploy                 # kiểm tra: 8 dòng
```

Sau khi xoay: sửa file `.env.*` trên máy dev, và GitHub Secrets nếu CI dùng. Kiểm tra: `make pve-check` (token đọc) hoặc
`make pve-vm ENV=staging DRY=1` rồi một thao tác ghi thật nhỏ.

Nguyên tắc: token `privsep=1` chỉ có quyền ở **phần giao** giữa user và token, nên gán quyền cho cả hai.
Không gộp `--users` và `--tokens` trong một lệnh `pveum acl modify`. Không dùng `root@pam` cho tự động hóa.

## 9. Xử lý sự cố

### 9.1 Bảng chẩn đoán nhanh

| Triệu chứng | Hướng xử lý |
|---|---|
| Không vào được `:8006` | Ping node. Trên console vật lý/SSH: `systemctl status pveproxy pvedaemon pve-cluster`; `systemctl restart pveproxy` |
| `pve-check` thoát mã 3 (ACL rỗng) | Token mất quyền (thường sau khi tạo lại token). Mục 8, hoặc PROXMOX_DEPLOY.md mục 11 lỗi #1 |
| `pve-check` hoặc `pve-vm` thoát mã 2 | Fingerprint TLS lệch: mục 9.2 |
| VM báo `locked` (`qm` từ chối thao tác) | Tác vụ trước bị gián đoạn: `qm unlock <id>`, rồi thử lại |
| VM không bật được, lỗi `out of memory` | Hết RAM của host. `qm list`, tắt VM không cần, xem ngân sách RAM (mục 3) |
| Tác vụ treo | Node → **Tasks** xem log; `ps aux | grep qm`; chỉ `kill` tiến trình đúng của tác vụ đó |
| VM chạy chậm / treo hàng loạt | `lvs` kiểm tra thin pool đầy (mục 6.2); `free -m`, `iostat` trên node |
| Không SSH được vào VM | Console VM trên web; kiểm tra cloud-init (`cloud-init status`), IP (`ip a`), `ufw status` (SSH chỉ cho 192.168.100.0/24) |
| Giao diện không thấy IP của VM | `qemu-guest-agent` chưa chạy: trong VM `systemctl status qemu-guest-agent` |
| Giờ sai, token/cert lỗi lạ | `timedatectl` (node và VM), `chronyc tracking` |
| Sau reboot VM không tự lên | `qm config <id> | grep onboot`; đặt `qm set <id> --onboot 1` |

Xem log:

```bash
journalctl -u pveproxy -n 100 --no-pager    # web/API
journalctl -u pvedaemon -n 100 --no-pager   # tác vụ nền
tail -f /var/log/pve/tasks/active           # tác vụ đang chạy
```

### 9.2 Cài lại Proxmox hoặc đổi chứng chỉ

Fingerprint TLS đổi, `pve-check`/`pve-vm` dừng với mã 2 (bảo vệ khỏi giả mạo). Nếu chính bạn cài lại hoặc đổi cert:

```bash
openssl x509 -in /etc/pve/local/pve-ssl.pem -noout -fingerprint -sha256     # chạy trên node
```

Cập nhật `PVE_TLS_FINGERPRINT` trong `infra/proxmox/.env.pve` **và** `.env.pve.deploy`. Nếu bạn **không** làm gì mà
fingerprint đổi: dừng, đừng gửi token, điều tra.

### 9.3 Mất node (khôi phục thảm họa)

1. Cài lại Proxmox VE, đặt IP `192.168.100.252`, tạo lại `vmbr0`.
2. Chép backup (`/var/lib/vz/dump/`) từ nơi sao lưu ngoài về, restore từng VM (`qmrestore`, mục 5.3).
3. Tạo lại user/token/ACL (PROXMOX_DEPLOY.md mục 2), cập nhật fingerprint (mục 9.2).
4. Template 9000 dựng lại theo mục 3 của PROXMOX_DEPLOY.md; VM dự án dựng lại bằng `make pve-vm` + `make pve-config`,
   dữ liệu lấy từ dump DB.

Vì VM dựng từ code (cloud-init + Ansible), **dữ liệu** mới là thứ không thay thế được: đó là lý do backup (mục 5) quan trọng nhất.

## 10. Vòng đời VM dự án

| Việc | Cách làm |
|---|---|
| Thêm môi trường/VM | `make pve-vm ENV=...` rồi `make pve-config ENV=...` (PROXMOX_DEPLOY.md mục 13, 5) |
| Cập nhật cấu hình VM (gói, firewall) | Sửa Ansible, chạy lại `make pve-config`; phải `changed=0` ở lần 2 |
| Nâng cấp OS VM lớn (24.04 → 26.04) | Dựng VM mới từ template mới, chuyển dữ liệu; không nâng tại chỗ |
| Làm template mới | Tải cloud image mới, tạo template **id khác** (9001); đổi `PVE_TEMPLATE_ID`; không sửa template đang dùng |
| Xóa VM | PROXMOX_DEPLOY.md mục 4, "Xóa VM (an toàn)": backup, tắt, `qm destroy ... --purge`. Prod có `protection=1`, phải bỏ cờ trước |
| Khóa chống xóa nhầm | `qm set <id> --protection 1` |

## 11. Kết quả thử runbook trên staging (2026-10-09)

Mục đích: chứng minh VM dựng bằng script chạy được sản phẩm thật.

| Bước | Kết quả |
|---|---|
| Dựng VM | `make pve-vm ENV=staging`: VM 202 lên, SSH được |
| Cấu hình | `make pve-config ENV=staging`: lần 1 `changed=17`, lần 2 `changed=0` |
| Build + up | `make prod-build && make prod-up` trên VM: 4 container `builder-api/web/redis/postgres` đều lên, api `healthy` |
| Migration | `alembic current` = `f3a8c1d5e7b9 (head)` |
| `make smoke` | **93 pass, 5 fail** (xem dưới) |

5 lỗi smoke cùng một dạng: sau khi xóa (mềm hoặc vĩnh viễn) một task/note, đọc lại ngay vẫn trả 200 thay vì 404. Gọi
tay có độ trễ thì đúng 404. Nghi ngờ **race**: transaction của `get_session` commit sau khi response đã gửi. Đây là lỗi của
mã backend trên nhánh `main`, **không do hạ tầng Proxmox**; đã tạo việc điều tra riêng. Staging chưa nên coi là đạt
nghiệm thu cho tới khi smoke xanh 100%.

Lưu ý: nhánh `uat` trên remote đang **cũ hơn `main` 195 commit** nên thử nghiệm này checkout `main` tay trên VM staging.
Làm đúng quy trình cần thăng cấp `main → uat` (`make promote-uat`, có `git push`, phải được bạn đồng ý) rồi VM mới `git pull --ff-only`.

## 12. Tham chiếu nhanh

| Cần gì | Lệnh |
|---|---|
| Xem hạ tầng | `make pve-check` |
| Dựng VM | `make pve-vm ENV=staging\|prod [DRY=1]` |
| Cấu hình VM | `make pve-config ENV=staging\|prod [CHECK=1]` |
| Danh sách VM | `qm list` (trên node) |
| Snapshot / lùi | `qm snapshot` / `qm rollback` |
| Backup / restore | `vzdump` / `qmrestore` |
| Dung lượng | `pvesm status`, `lvs` |
| Xoay token | mục 8 |
| Đọc thêm | PROXMOX_DEPLOY.md (dựng, CI, deploy), deploy-runbook.md (lệnh trong VM) |

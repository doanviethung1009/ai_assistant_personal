#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Dựng một VM môi trường (staging | prod) từ template 9000 qua API Proxmox.
#
#  Dùng:
#    bash infra/proxmox/scripts/pve-vm.sh staging --dry-run   # chỉ in kế hoạch
#    bash infra/proxmox/scripts/pve-vm.sh staging             # dựng thật
#    make pve-vm ENV=staging
#
#  Vì sao là script thay vì gõ tay: cùng một thông số (id, IP, RAM, disk) lặp
#  lại được, và chạy lại KHÔNG phá VM đã có (idempotent: VM tồn tại thì dừng).
#
#  Cần: infra/proxmox/.env.pve.deploy (token GHI, role AIDeploy trong pool
#  ai-assistant, xem docs/PROXMOX_DEPLOY.md mục 2.2) và một khoá SSH công khai.
#
#  Bảo mật: ghim fingerprint TLS trước khi gửi token; không in secret.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

ENV_NAME="${1:-}"; DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PVE_DEPLOY_ENV_FILE:-$HERE/.env.pve.deploy}"
[ -f "$ENV_FILE" ] || { echo "Thiếu $ENV_FILE (xem docs/PROXMOX_DEPLOY.md mục 2.2)" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a
: "${PVE_TOKEN_SECRET:?PVE_TOKEN_SECRET trống trong $ENV_FILE}"
PORT="${PVE_PORT:-8006}"; NODE="${PVE_NODE:-isec}"
BASE="https://${PVE_HOST}:${PORT}/api2/json/nodes/${NODE}"
# Khoá công khai nạp vào VM qua cloud-init; khoá riêng tương ứng dùng để SSH vào.
PUBKEY_FILE="${PVE_SSH_PUBKEY:-$HOME/.ssh/ai_assistant_deploy.pub}"
CI_USER="${PVE_CI_USER:-deploy}"

# ── Thông số từng môi trường ────────────────────────────────────────────
# id VM = octet cuối của IP (quy ước ở docs/PROXMOX_DEPLOY.md mục 4).
case "$ENV_NAME" in
  staging) VMID=202; NAME=ai-stg-01;  IP=192.168.100.202; MEM=3072; CORES=2; DISK=40G; PROTECT=0 ;;
  prod)    VMID=203; NAME=ai-prod-01; IP=192.168.100.203; MEM=5120; CORES=2; DISK=60G; PROTECT=1 ;;
  *) echo "Dùng: $0 staging|prod [--dry-run]" >&2; exit 1 ;;
esac

echo "Kế hoạch: $ENV_NAME → VM $VMID '$NAME' $IP, ${MEM}MB RAM, $CORES vCPU, disk $DISK, protection=$PROTECT"
echo "          clone từ template ${PVE_TEMPLATE_ID} → storage ${PVE_STORAGE}, pool ${PVE_POOL}, khoá $PUBKEY_FILE"
[ -f "$PUBKEY_FILE" ] || { echo "Thiếu khoá công khai $PUBKEY_FILE (ssh-keygen -t ed25519 -f ${PUBKEY_FILE%.pub})" >&2; exit 1; }
[ "$DRY" = 1 ] && { echo "(--dry-run: không thay đổi gì)"; exit 0; }

# Ghim fingerprint trước khi gửi token (giống pve-check.sh).
actual="$(echo | openssl s_client -connect "${PVE_HOST}:${PORT}" 2>/dev/null | openssl x509 -noout -fingerprint -sha256 | cut -d= -f2)"
[ "$actual" = "$PVE_TLS_FINGERPRINT" ] || { echo "Fingerprint TLS KHÔNG khớp, dừng." >&2; exit 2; }

AUTH="Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}"
# Đã ghim fingerprint nên -k an toàn. Mọi lời gọi in lỗi của Proxmox nếu HTTP != 2xx.
call() { # call METHOD PATH [curl args...]
  local m="$1" p="$2"; shift 2
  local out code
  out="$(curl -sk -m 60 -w '\n%{http_code}' -X "$m" -H "$AUTH" "$@" "$BASE$p")"
  code="${out##*$'\n'}"; out="${out%$'\n'*}"
  if [[ ! "$code" =~ ^2 ]]; then echo "LỖI $m $p → HTTP $code: $out" >&2; return 1; fi
  printf '%s' "$out"
}
# Tác vụ clone/start chạy nền; trả UPID, phải đợi trạng thái "stopped" + OK.
wait_task() {
  local upid="$1" i st
  for i in $(seq 1 120); do
    st="$(call GET "/tasks/$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=""))' "$upid")/status")"
    case "$st" in
      *'"status":"stopped"'*) [[ "$st" == *'"exitstatus":"OK"'* ]] && return 0; echo "Tác vụ lỗi: $st" >&2; return 1 ;;
    esac
    sleep 2
  done
  echo "Quá thời gian chờ tác vụ" >&2; return 1
}
upid_of() { python3 -c 'import sys,json; print(json.load(sys.stdin)["data"])'; }
# Gọi API tạo tác vụ nền rồi đợi nó xong. KHÔNG viết `wait_task "$(call ... | upid_of)"`:
# lỗi của `call` bị nuốt trong pipeline, UPID rỗng, và vòng chờ quay vô hạn (đã gặp thật).
run_task() { # run_task METHOD PATH [curl args...]
  local out upid
  out="$(call "$@")" || return 1
  upid="$(printf '%s' "$out" | upid_of)"
  [[ "$upid" == UPID:* ]] || { echo "Không nhận được UPID hợp lệ: $out" >&2; return 1; }
  wait_task "$upid"
}

# ── 1. VM đã có thì dừng (idempotent, không bao giờ ghi đè) ─────────────
if curl -sk -m 15 -o /dev/null -w '%{http_code}' -H "$AUTH" "$BASE/qemu/$VMID/status/current" | grep -q '^200$'; then
  echo "VM $VMID đã tồn tại → không làm gì (xoá tay nếu muốn dựng lại: docs/PROXMOX_DEPLOY.md, mục Xóa VM)."
  exit 0
fi

# ── 2. Clone đầy đủ từ template ────────────────────────────────────────
echo "[1/5] Clone template ${PVE_TEMPLATE_ID} → $VMID"
run_task POST "/qemu/${PVE_TEMPLATE_ID}/clone" \
  --data-urlencode "newid=$VMID" --data-urlencode "name=$NAME" --data-urlencode "full=1" \
  --data-urlencode "pool=${PVE_POOL}" --data-urlencode "storage=${PVE_STORAGE}"

# ── 3. Cloud-init + tài nguyên ──────────────────────────────────────────
echo "[2/5] Cấu hình cloud-init, RAM, CPU"
# sshkeys phải URL-encode TRƯỚC khi curl encode lần nữa (yêu cầu của API Proxmox).
SSHKEY_ENC="$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(open(sys.argv[1]).read().strip(),safe=""))' "$PUBKEY_FILE")"
call PUT "/qemu/$VMID/config" \
  --data-urlencode "memory=$MEM" --data-urlencode "cores=$CORES" \
  --data-urlencode "ciuser=$CI_USER" --data-urlencode "sshkeys=$SSHKEY_ENC" \
  --data-urlencode "ipconfig0=ip=$IP/24,gw=${PVE_GATEWAY}" --data-urlencode "nameserver=${PVE_DNS}" \
  --data-urlencode "agent=enabled=1" --data-urlencode "onboot=1" \
  --data-urlencode "tags=env-$ENV_NAME" \
  --data-urlencode "description=Dựng bởi pve-vm.sh ($ENV_NAME). Xem docs/PROXMOX_DEPLOY.md" >/dev/null

# ── 4. Nới disk ─────────────────────────────────────────────────────────
echo "[3/5] Nới disk lên $DISK"
call PUT "/qemu/$VMID/resize" --data-urlencode "disk=scsi0" --data-urlencode "size=$DISK" >/dev/null

# ── 5. Bật máy và chờ SSH ───────────────────────────────────────────────
echo "[4/5] Khởi động"
run_task POST "/qemu/$VMID/status/start"
echo "[5/5] Chờ SSH tại $IP:22 (tối đa 3 phút)"
for i in $(seq 1 36); do nc -z -G 3 "$IP" 22 2>/dev/null && break; sleep 5; done
nc -z -G 3 "$IP" 22 2>/dev/null || { echo "SSH chưa lên, xem Console VM $VMID trên web." >&2; exit 3; }

# Prod: bật protection để không xoá nhầm (cần quyền VM.Config.Options).
[ "$PROTECT" = 1 ] && call PUT "/qemu/$VMID/config" --data-urlencode "protection=1" >/dev/null && echo "Đã bật protection cho VM $VMID"
echo "XONG. Thử: ssh -i ${PUBKEY_FILE%.pub} $CI_USER@$IP 'hostname; cloud-init status --wait'"

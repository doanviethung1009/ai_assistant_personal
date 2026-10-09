#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Chụp snapshot một VM qua API Proxmox (dùng token GHI) trước khi deploy.
#
#  Dùng:  bash infra/proxmox/scripts/pve-snapshot.sh <vmid> <tên-snapshot>
#         Biến lấy từ infra/proxmox/.env.pve.deploy, hoặc từ môi trường (CI: GitHub Secrets).
#
#  Snapshot chỉ để LÙI NHANH, không phải backup (cùng thin pool với VM). Tên: chữ, số, gạch.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
VMID="${1:?Dùng: pve-snapshot.sh <vmid> <tên>}"; SNAP="${2:?Thiếu tên snapshot}"
[[ "$SNAP" =~ ^[A-Za-z][A-Za-z0-9_-]{0,39}$ ]] || { echo "Tên snapshot không hợp lệ: $SNAP" >&2; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$HERE/.env.pve.deploy" ] && { set -a; . "$HERE/.env.pve.deploy"; set +a; }
: "${PVE_HOST:?}" "${PVE_TOKEN_ID:?}" "${PVE_TOKEN_SECRET:?}" "${PVE_TLS_FINGERPRINT:?}"
PORT="${PVE_PORT:-8006}"; NODE="${PVE_NODE:-isec}"
actual="$(echo | openssl s_client -connect "${PVE_HOST}:${PORT}" 2>/dev/null | openssl x509 -noout -fingerprint -sha256 | cut -d= -f2)"
[ "$actual" = "$PVE_TLS_FINGERPRINT" ] || { echo "Fingerprint TLS KHÔNG khớp, dừng." >&2; exit 2; }
out="$(curl -sk -m 60 -w '\n%{http_code}' -X POST -H "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" \
  --data-urlencode "snapname=$SNAP" --data-urlencode "description=Tự động trước deploy" \
  "https://${PVE_HOST}:${PORT}/api2/json/nodes/${NODE}/qemu/${VMID}/snapshot")"
code="${out##*$'\n'}"; [[ "$code" =~ ^2 ]] || { echo "LỖI snapshot HTTP $code: ${out%$'\n'*}" >&2; exit 1; }
echo "Đã yêu cầu snapshot '$SNAP' cho VM $VMID (tác vụ nền: ${out%$'\n'*})"

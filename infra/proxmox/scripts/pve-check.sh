#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Đọc thông tin Proxmox qua API bằng token CHỈ ĐỌC (PVEAuditor).
#
#  Dùng:  bash infra/proxmox/scripts/pve-check.sh        (hoặc: make pve-check)
#
#  Vì sao có script này: trước khi dựng VM phải biết node còn bao nhiêu
#  RAM/disk, storage nào chứa được image, bridge nào dùng được. Script chỉ
#  gửi GET, không thể thay đổi gì trên Proxmox (token là PVEAuditor).
#
#  Bảo mật:
#   - Secret đọc từ infra/proxmox/.env.pve (bị gitignore), không in ra màn hình.
#   - Chứng chỉ TLS tự ký được GHIM bằng fingerprint thay vì tắt kiểm tra (-k).
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PVE_ENV_FILE:-$HERE/.env.pve}"
[ -f "$ENV_FILE" ] || { echo "Thiếu $ENV_FILE (cp .env.pve.example .env.pve rồi điền token)" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${PVE_TOKEN_SECRET:?PVE_TOKEN_SECRET đang trống trong $ENV_FILE}"
BASE="https://${PVE_HOST}:${PVE_PORT:-8006}/api2/json"

# Kiểm tra fingerprint của chứng chỉ server trước khi gửi token đi.
# Nếu lệch (bị chặn giữa đường, hoặc Proxmox đã cài lại) thì dừng.
actual="$(echo | openssl s_client -connect "${PVE_HOST}:${PVE_PORT:-8006}" 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256 | cut -d= -f2)"
if [ "$actual" != "$PVE_TLS_FINGERPRINT" ]; then
  echo "Fingerprint TLS KHÔNG khớp. Mong đợi: $PVE_TLS_FINGERPRINT" >&2
  echo "Thực tế: $actual — dừng, không gửi token." >&2
  exit 2
fi

# Đã ghim fingerprint nên được phép bỏ kiểm tra chuỗi CA (-k) cho các lời gọi sau.
api() { curl -sk -m 15 -H "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" "$BASE$1"; }

# Token đăng nhập được nhưng chưa có ACL thì mọi API trả rỗng mà KHÔNG báo lỗi,
# rất dễ nhầm là "Proxmox trống". Chặn sớm và chỉ đúng chỗ sửa.
if [ "$(api /access/permissions)" = '{"data":{}}' ]; then
  echo "Token ${PVE_TOKEN_ID} đăng nhập được nhưng CHƯA có quyền nào (ACL rỗng)." >&2
  echo "Token privsep chỉ có phần GIAO quyền của user và token, nên gán cho CẢ HAI. Trong Shell của node:" >&2
  echo "  pveum acl modify / --users '${PVE_TOKEN_ID%%!*}' --roles PVEAuditor" >&2
  echo "  pveum acl modify / --tokens '${PVE_TOKEN_ID}' --roles PVEAuditor" >&2
  echo "Chi tiết: docs/PROXMOX_DEPLOY.md mục 2.1 và 11 (lỗi #1)." >&2
  exit 3
fi

# Phần định dạng viết bằng Python (đọc JSON từ stdin) để tránh lồng quote trong bash.
fmt() { python3 -c "$1"; }
G=1073741824

echo "== Phiên bản =="
api /version | fmt 'import sys,json; d=json.load(sys.stdin)["data"]; print(d["version"], "(release", d["release"]+")")'

echo "== Node =="
api /nodes | fmt '
import sys,json
G=1024**3
for n in json.load(sys.stdin)["data"]:
    print("%-10s %s | CPU %s nhân | RAM dùng %.1f/%.1f GB | disk root %.0f/%.0f GB" % (
        n["node"], n.get("status"), n.get("maxcpu"), n.get("mem",0)/G, n.get("maxmem",0)/G,
        n.get("disk",0)/G, n.get("maxdisk",0)/G))
'

NODE="$(api /nodes | fmt 'import sys,json; print(json.load(sys.stdin)["data"][0]["node"])')"

echo "== Storage (node $NODE) =="
api "/nodes/$NODE/storage" | fmt '
import sys,json
G=1024**3
for s in json.load(sys.stdin)["data"]:
    print("%-14s %-8s content=%-28s còn %.0f/%.0f GB  active=%s" % (
        s["storage"], s.get("type"), s.get("content"), s.get("avail",0)/G, s.get("total",0)/G, s.get("active")))
'

echo "== Bridge mạng =="
api "/nodes/$NODE/network" | fmt '
import sys,json
for n in json.load(sys.stdin)["data"]:
    if n.get("type") in ("bridge","bond","vlan"):
        print("%-8s %-7s %s gw=%s ports=%s" % (n["iface"], n["type"], n.get("cidr") or n.get("address"), n.get("gateway"), n.get("bridge_ports")))
'

echo "== VM / LXC đang có =="
api "/cluster/resources?type=vm" | fmt '
import sys,json
G=1024**3
d=json.load(sys.stdin)["data"]
if not d: print("(chưa có)")
for v in sorted(d, key=lambda x: x["vmid"]):
    print("%-5s %-6s %-22s %-8s template=%s RAM %.1f GB" % (v["vmid"], v["type"], v.get("name"), v.get("status"), v.get("template",0), v.get("maxmem",0)/G))
'

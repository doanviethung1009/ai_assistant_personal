#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Sinh lại apps/core/uv.lock trên VM dev khi máy local không có uv/Docker
#  (thay cho `make lock`). Chạy `uv lock` trong container python:3.12-slim tạm rồi chép
#  uv.lock về máy local. Mặc định dùng uv MỚI NHẤT (cùng đời với CI `setup-uv` và với
#  `revision = 5` của lock hiện tại); uv 0.5.x của Dockerfile ghi lại định dạng cũ nên
#  diff nhiễu. Ghim bằng UV_VERSION=x.y.z nếu cần.
#
#  Dùng:  bash scripts/patches/dev-vm-lock.sh
#
#  CÁCH LY: chỉ rsync pyproject.toml + uv.lock sang ~/lock/<run-id>, không đụng stack
#  `builder-*`. Sau khi chạy, xem `git diff apps/core/uv.lock` rồi mới commit.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/../.."

SSH_KEY="${SSH_KEY:-$HOME/.ssh/ai_assistant_deploy}"
HOST="${DEV_VM:-deploy@192.168.100.201}"
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST")
UV_VERSION="${UV_VERSION:-}"
RUN_ID="$$-$(date +%s)"

echo "==> uv ${UV_VERSION:-mới nhất}, thư mục tạm ~/lock/$RUN_ID"
"${SSH[@]}" "mkdir -p ~/lock/$RUN_ID"
# Luôn xuất phát từ uv.lock đã commit (HEAD), không từ file đang sửa dở: chạy lại được,
# và diff chỉ gồm phần dependency thay đổi.
BASE_LOCK="$(mktemp)"
git show HEAD:apps/core/uv.lock > "$BASE_LOCK"
scp -q -i "$SSH_KEY" -o IdentitiesOnly=yes apps/core/pyproject.toml "$HOST:~/lock/$RUN_ID/"
scp -q -i "$SSH_KEY" -o IdentitiesOnly=yes "$BASE_LOCK" "$HOST:~/lock/$RUN_ID/uv.lock"
rm -f "$BASE_LOCK"
"${SSH[@]}" "RUN_ID='$RUN_ID' UV_VERSION='$UV_VERSION' bash -s" <<'REMOTE'
set -euo pipefail
cd ~/lock/$RUN_ID
# Ảnh uv chính thức (cùng nguồn với `COPY --from=ghcr.io/astral-sh/uv` trong Dockerfile).
# `pip install uv` trong python:3.12-slim cho bản cũ hơn nên ghi lock sai định dạng.
docker run --rm --memory 500m -v "$PWD:/w" -w /w "ghcr.io/astral-sh/uv:${UV_VERSION:+$UV_VERSION-}python3.12-bookworm-slim" \
  uv lock
REMOTE
scp -q -i "$SSH_KEY" -o IdentitiesOnly=yes "$HOST:~/lock/$RUN_ID/uv.lock" apps/core/uv.lock
# uv chạy trong container với root nên file thuộc root: xoá bằng container, không cần sudo.
"${SSH[@]}" "docker run --rm -v \$HOME/lock:/t python:3.12-slim rm -rf /t/$RUN_ID; rmdir ~/lock 2>/dev/null || true"
echo "==> xong. Kiểm: git diff --stat apps/core/uv.lock"

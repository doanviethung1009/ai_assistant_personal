#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Cài hook git cục bộ của repo (hiện chỉ có commit-msg).
#
#  An toàn với git-secrets: hook công ty được cấu hình qua core.hookspath
#  (global, trỏ ra ngoài repo) nên nó LUÔN chạy trước, bất kể gì nằm trong
#  .git/hooks/. Script này chỉ thêm một hook chạy NỐI TIẾP sau đó, không
#  thay thế, không tắt được việc quét bí mật. Xem chi tiết cơ chế trong
#  comment đầu file scripts/git-hooks/commit-msg.
#
#  Dùng:
#    bash scripts/install-hooks.sh
#
#  Chạy lại an toàn nhiều lần (idempotent). Nếu .git/hooks/commit-msg đã
#  có nội dung khác (không phải bản cài từ script này ở lần trước), script
#  giữ lại bản cũ dưới dạng .bak trước khi ghi đè.
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

cd "$(dirname "$0")/.."

GREEN=$'\033[32m'
YELLOW=$'\033[33m'
DIM=$'\033[2m'
RESET=$'\033[0m'

git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" \
  || { echo "Không ở trong git repo." >&2; exit 1; }

hooks_dir="$git_common_dir/hooks"
mkdir -p "$hooks_dir"

SOURCE_MARK="# scripts/install-hooks.sh"

install_hook() {
  local name="$1" source="scripts/git-hooks/$1" target="$hooks_dir/$1"

  [[ -f "$source" ]] || { echo "  ${YELLOW}bỏ qua${RESET} $name — không có $source" >&2; return; }

  if [[ -f "$target" ]] && ! grep -q "$SOURCE_MARK" "$target" 2>/dev/null; then
    cp "$target" "$target.bak"
    echo "  ${DIM}đã lưu bản cũ: $target.bak${RESET}"
  fi

  cp "$source" "$target"
  chmod +x "$target"
  echo "  ${GREEN}đã cài${RESET} $name"
}

echo "Cài hook git cục bộ (hooks dir: $hooks_dir)"
echo ""
install_hook commit-msg
echo ""
echo "Kiểm tra thử:"
echo "  git commit --allow-empty -m \"sai định dạng\"   # phải bị chặn"
echo "  git commit --allow-empty -m \"chore: test hook\" # phải qua"

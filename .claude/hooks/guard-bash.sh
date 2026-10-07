#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  PreToolUse hook cho Bash: chặn lệnh phá dữ liệu trước khi chạy.
#
#  Claude Code gửi JSON của tool call vào stdin. Exit 2 = chặn lệnh và
#  đưa nội dung stderr cho agent đọc để nó đổi hướng. Exit 0 = cho chạy.
#
#  Vì sao cần hook dù AGENTS.md đã cấm: luật viết bằng chữ chỉ là lời
#  dặn, agent vẫn có thể quên khi context dài. Hook là hàng rào cứng,
#  áp dụng cho cả session chính lẫn mọi subagent.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

cmd="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))')"

block() { echo "BLOCKED by .claude/hooks/guard-bash.sh: $1" >&2; exit 2; }

# ── Dữ liệu ─────────────────────────────────────────────────────────
# Xoá volume = mất toàn bộ Postgres. Chỉ người làm bằng tay.
echo "$cmd" | grep -Eq 'docker( |-)compose .*down .*-v|docker volume (rm|prune)' \
  && block "lệnh xoá volume Docker. Hãy đề xuất cho User tự chạy."

# SQL phá huỷ gõ thẳng qua psql. Migration phải đi qua Alembic.
echo "$cmd" | grep -Eiq '(psql|make psql).*(drop +(table|database|schema)|truncate|delete +from)' \
  && block "SQL phá huỷ qua psql. Dùng Alembic migration có downgrade()."

# ── Git ─────────────────────────────────────────────────────────────
echo "$cmd" | grep -Eq 'git push .*(--force|-f( |$))' \
  && block "force push bị cấm."
echo "$cmd" | grep -Eq 'git (reset --hard|clean -[a-z]*f)' \
  && block "lệnh git huỷ thay đổi chưa commit. Hỏi User trước."

exit 0

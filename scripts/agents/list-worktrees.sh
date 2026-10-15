#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Liệt kê mọi worktree: nhánh, task, DB, cổng, Docker, trạng thái trong
#  TASKS.md (đọc từ nhánh main, nơi bảng điều phối được ghi).
#
#  Dùng:
#    scripts/agents/list-worktrees.sh
#    scripts/agents/list-worktrees.sh --help
#
#  Chỉ đọc, không đổi gì.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# shellcheck source=scripts/agents/lib.sh
source "$(dirname "$0")/lib.sh"

case "${1:-}" in
  -h|--help) sed -n '3,10p' "$0" | sed -E 's/^#( {1,2})?//'; exit 0 ;;
  "") ;;
  *) die "không nhận tham số: $1 (xem --help)" ;;
esac

resolve_repo
cd "$MAIN_WT"

BOARD="$(git show main:TASKS.md 2>/dev/null || true)"
DOCKER=0; has_docker && DOCKER=1

# Đọc một biến từ .env.worktree mà không source (file do script sinh, nhưng
# vẫn tránh thực thi nội dung).
env_get() { sed -n "s/^$2=//p" "$1/.env.worktree" 2>/dev/null | head -n 1; }

printf '%-6s %-34s %-44s %-16s %-26s %-10s %s\n' TASK BRANCH WORKTREE DATABASE "PORTS web/api/pg/redis" DOCKER BOARD
git worktree list --porcelain | awk '
  /^worktree /{p = substr($0, 10)}
  /^branch /{b = substr($0, 19)}
  /^detached/{b = "(detached)"}
  /^$/{ if (p != "") print p "\t" b; p = ""; b = "" }
  END { if (p != "") print p "\t" b }' |
while IFS=$'\t' read -r path branch; do
  task="-"; db="-"; ports="-"; docker_state="-"; board="-"
  if [[ -f "$path/.env.worktree" ]]; then
    task="$(env_get "$path" TASK_ID)"
    db="$(env_get "$path" POSTGRES_DB)"
    ports="$(env_get "$path" WEB_PORT)/$(env_get "$path" API_PORT)/$(env_get "$path" POSTGRES_PORT)/$(env_get "$path" REDIS_PORT)"
    project="$(env_get "$path" COMPOSE_PROJECT_NAME)"
    if [[ $DOCKER -eq 1 ]]; then
      running="$(docker ps -q --filter "label=com.docker.compose.project=${project}" | wc -l | tr -d ' ')"
      docker_state="${running} up"
    else
      docker_state="no-docker"
    fi
    board="$(printf '%s\n' "$BOARD" | TASK="$task" awk -F'|' '
      function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
      trim($2) == ENVIRON["TASK"] { print trim($7); exit }')"
    board="${board:-(chưa có)}"
  elif [[ "$path" == "$MAIN_WT" ]]; then
    task="(chính)"
  fi
  printf '%-6s %-34s %-44s %-16s %-26s %-10s %s\n' "$task" "$branch" "${path/#$WT_PARENT\//../}" "$db" "$ports" "$docker_state" "$board"
done

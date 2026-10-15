#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Dọn một task: Docker riêng (container, volume DB, network, image),
#  worktree và nhánh local. Ngược lại với new-worktree.sh.
#
#  Dùng:
#    scripts/agents/remove-worktree.sh <task-id> [tuỳ chọn]
#    scripts/agents/remove-worktree.sh T12
#
#  Tuỳ chọn:
#    --yes          không hỏi lại trước khi xoá volume DB (dùng cho script)
#    --force        xoá worktree dù còn thay đổi chưa commit (MẤT thay đổi đó)
#    --keep-branch  giữ nhánh local dù đã merge
#    -h, --help     in hướng dẫn này
#
#  Nhánh local chỉ bị xoá khi đã nằm trong origin/main hoặc PR đã MERGED;
#  nếu chưa thì giữ lại và báo. Chạy lại an toàn: phần đã dọn thì bỏ qua.
#  KHÔNG BAO GIỜ đụng tài nguyên ngoài prefix builder-t<N> / builder_ai_t<N>.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# shellcheck source=scripts/agents/lib.sh
source "$(dirname "$0")/lib.sh"

usage() { sed -n '3,19p' "$0" | sed -E 's/^#( {1,2})?//'; }

FORCE=0; KEEP_BRANCH=0; ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --yes) export ASSUME_YES=1; shift ;;
    --force) FORCE=1; shift ;;
    --keep-branch) KEEP_BRANCH=1; shift ;;
    -*) die "tuỳ chọn không hợp lệ: $1 (xem --help)" ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
[[ ${#ARGS[@]} -eq 1 ]] || { usage; exit 1; }

parse_task_id "${ARGS[0]}"
resolve_repo
task_vars
assert_task_resource

BRANCH="$(find_task_branch)"
WT=""
[[ -n "$BRANCH" ]] && WT="$(worktree_of_branch "$BRANCH")"
[[ -z "$WT" && -d "$WT_PATH" ]] && WT="$WT_PATH"

# Xoá worktree mình đang đứng trong sẽ làm shell mất thư mục làm việc.
case "$PWD/" in
  "${WT_PATH}/"*|"${WT:-/nonexistent}/"*) die "đang đứng trong worktree của $TASK_ID. Chạy từ checkout chính: cd \"$MAIN_WT\"" ;;
esac
cd "$MAIN_WT"

# ═══════════════════════════════════════════════════════════════════════
#  1. Kiểm tra worktree trước, để không xoá DB rồi mới phát hiện còn code dở
# ═══════════════════════════════════════════════════════════════════════
if [[ -n "$WT" && -d "$WT" ]]; then
  dirty="$(git -C "$WT" status --porcelain)"
  if [[ -n "$dirty" && $FORCE -eq 0 ]]; then
    echo "$dirty" | head -20 >&2
    die "worktree $WT còn thay đổi chưa commit. Commit/push trước, hoặc thêm --force để BỎ chúng."
  fi
fi

# ═══════════════════════════════════════════════════════════════════════
#  2. Docker: chỉ tài nguyên mang nhãn compose project của task
# ═══════════════════════════════════════════════════════════════════════
# Lọc theo nhãn com.docker.compose.project thay vì `docker compose down`, để
# vẫn dọn được khi thư mục worktree (và file compose) đã mất.
if has_docker; then
  LABEL="label=com.docker.compose.project=${PROJECT}"
  containers="$(docker ps -aq --filter "$LABEL")"
  volumes="$(docker volume ls -q --filter "$LABEL")"
  networks="$(docker network ls -q --filter "$LABEL")"
  if [[ -n "$containers$volumes$networks" ]]; then
    echo "Tài nguyên Docker của ${PROJECT}:"
    [[ -n "$volumes" ]] && echo "$volumes" | sed 's/^/    volume /'
    [[ -n "$containers" ]] && info "$(echo "$containers" | wc -l | tr -d ' ') container"
    confirm "Xoá toàn bộ, gồm DATABASE ${DB_NAME} (không khôi phục được)?" \
      || die "đã huỷ, giữ nguyên mọi thứ."
    [[ -n "$containers" ]] && docker rm -f $containers >/dev/null
    [[ -n "$volumes" ]] && docker volume rm $volumes >/dev/null
    [[ -n "$networks" ]] && docker network rm $networks >/dev/null
    images="$(docker image ls -q --filter "$LABEL" | sort -u)"
    [[ -n "$images" ]] && { docker image rm -f $images >/dev/null 2>&1 || warn "không xoá được vài image của ${PROJECT}."; }
    info "Đã xoá Docker của ${PROJECT}."
  else
    info "Không có tài nguyên Docker nào của ${PROJECT}."
  fi
else
  warn "Docker không chạy: không kiểm tra/xoá được volume DB của ${PROJECT}. Chạy lại script khi có Docker."
fi

# ═══════════════════════════════════════════════════════════════════════
#  3. Worktree
# ═══════════════════════════════════════════════════════════════════════
if [[ -n "$WT" && -d "$WT" ]]; then
  # --force ở đây chỉ để bỏ qua file bị gitignore (.env, data/); thay đổi
  # thật đã được chặn ở bước 1 nếu không có --force của người dùng.
  git worktree remove --force "$WT"
  info "Đã xoá worktree $WT"
else
  info "Không có worktree nào cho $TASK_ID."
fi
git worktree prune

# ═══════════════════════════════════════════════════════════════════════
#  4. Nhánh local
# ═══════════════════════════════════════════════════════════════════════
if [[ -n "$BRANCH" && $KEEP_BRANCH -eq 0 ]]; then
  git fetch -q origin main 2>/dev/null || warn "không fetch được origin, kiểm tra merge bằng origin/main đang có."
  merged=0
  git merge-base --is-ancestor "$BRANCH" origin/main 2>/dev/null && merged=1
  if [[ $merged -eq 0 ]] && command -v gh >/dev/null 2>&1; then
    [[ "$(gh pr view "$BRANCH" --json state -q .state 2>/dev/null || true)" == "MERGED" ]] && merged=1
  fi
  if [[ $merged -eq 1 ]]; then
    git branch -D "$BRANCH" >/dev/null
    info "Đã xoá nhánh local $BRANCH (đã merge)."
  else
    warn "nhánh $BRANCH CHƯA merge vào origin/main, giữ lại. Xoá tay nếu chắc: git branch -D $BRANCH"
  fi
fi

echo
info "Xong. Cập nhật bảng: scripts/agents/task-board.sh status $TASK_ID done"

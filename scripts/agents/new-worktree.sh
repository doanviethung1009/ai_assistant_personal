#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Tạo nhánh + git worktree + môi trường Docker riêng cho một task.
#
#  Dùng:
#    scripts/agents/new-worktree.sh <task-id> <slug> [tuỳ chọn]
#    scripts/agents/new-worktree.sh T12 note-tags --type feat
#
#  Tuỳ chọn:
#    --type <t>     feat|fix|chore|docs|refactor|test|perf|build|ci (mặc định feat)
#    --base <ref>   nhánh gốc khi tạo nhánh mới (mặc định origin/main)
#    --no-stack     chỉ tạo worktree và .env.worktree, không dựng Docker
#    --here         dùng worktree HIỆN TẠI (không tạo worktree mới). Tự bật khi đang
#                   đứng trong một linked worktree (vd agent view tạo ở .claude/worktrees/)
#    --new          ép tạo worktree mới ../<repo>-T<N> dù đang ở linked worktree
#    -h, --help     in hướng dẫn này
#
#  Kết quả: nhánh <type>/T<N>-<slug>, worktree ../<repo>-T<N>, file
#  .env.worktree (compose project builder-t<N>, DB builder_ai_t<N>, cổng
#  web 3100+N / api 8100+N / postgres 5500+N / redis 6400+N). Nếu Docker chạy
#  được: dựng postgres, redis, api của riêng worktree và chạy migration.
#
#  Chế độ --here: giữ nguyên thư mục, chỉ đổi tên nhánh hiện tại thành
#  <type>/T<N>-<slug> (nếu chưa đúng dạng), sinh .env/.env.worktree và dựng
#  Docker/DB/cổng riêng ngay tại đó. Chỉ tạo worktree mới khi đứng ở checkout chính.
#
#  Chạy lại an toàn: nhánh, worktree, .env đã có thì giữ; .env.worktree được
#  sinh lại (nội dung chỉ phụ thuộc task-id).
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# shellcheck source=scripts/agents/lib.sh
source "$(dirname "$0")/lib.sh"

usage() { sed -n '3,28p' "$0" | sed -E 's/^#( {1,2})?//'; }

TYPE="feat"; BASE=""; STACK=1; MODE="auto"; ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --type) TYPE="${2:?thiếu giá trị cho --type}"; shift 2 ;;
    --base) BASE="${2:?thiếu giá trị cho --base}"; shift 2 ;;
    --no-stack) STACK=0; shift ;;
    --here) MODE="here"; shift ;;
    --new) MODE="new"; shift ;;
    -*) die "tuỳ chọn không hợp lệ: $1 (xem --help)" ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
[[ ${#ARGS[@]} -eq 2 ]] || { usage; exit 1; }

parse_task_id "${ARGS[0]}"
SLUG="${ARGS[1]}"
[[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || die "slug chỉ gồm a-z, 0-9 và '-', ví dụ note-tags"
[[ "$TYPE" =~ ^(feat|fix|chore|docs|refactor|test|perf|build|ci)$ ]] || die "--type không hợp lệ: $TYPE"

resolve_repo
task_vars
assert_task_resource

# Đang đứng trong linked worktree? (git-dir riêng khác git-common-dir.)
# Khi đó mặc định dùng luôn worktree này thay vì đẻ thêm worktree thứ hai.
HERE_ROOT="$(git rev-parse --show-toplevel)"
if [[ "$(git rev-parse --path-format=absolute --git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ]]; then
  IN_LINKED=1
else
  IN_LINKED=0
fi
if [[ "$MODE" == "auto" ]]; then
  [[ $IN_LINKED -eq 1 ]] && MODE="here" || MODE="new"
fi
[[ "$MODE" != "here" || $IN_LINKED -eq 1 ]] \
  || die "--here chỉ dùng trong linked worktree; đây là checkout chính (bỏ --here để tạo worktree mới)."

# ═══════════════════════════════════════════════════════════════════════
#  1. Nhánh và worktree
# ═══════════════════════════════════════════════════════════════════════
BRANCH="${TYPE}/${TASK_ID}-${SLUG}"
EXISTING="$(find_task_branch)"
if [[ -n "$EXISTING" && "$EXISTING" != "$BRANCH" ]]; then
  warn "$TASK_ID đã có nhánh '$EXISTING', dùng nhánh đó thay cho '$BRANCH'."
  BRANCH="$EXISTING"
fi

if [[ "$MODE" == "here" ]]; then
  # Dùng worktree hiện tại: không `git worktree add`. Mọi tài nguyên Docker/DB/cổng
  # vẫn suy từ task-id, chỉ đường dẫn worktree là thư mục đang đứng.
  WT_PATH="$HERE_ROOT"
  if [[ -f "$WT_PATH/.env.worktree" ]]; then
    OLD_TASK="$(sed -n 's/^TASK_ID=//p' "$WT_PATH/.env.worktree" | head -n 1)"
    [[ -z "$OLD_TASK" || "$OLD_TASK" == "$TASK_ID" ]] \
      || die "worktree này đã thuộc $OLD_TASK. Mở worktree khác cho $TASK_ID."
  fi
  CUR="$(git branch --show-current)"
  [[ "$CUR" != "main" ]] || die "worktree đang ở nhánh main, không gắn task vào main."
  OTHER_WT="$(worktree_of_branch "$BRANCH")"
  if [[ "$CUR" != "$BRANCH" ]]; then
    [[ -z "$OTHER_WT" ]] || die "nhánh $BRANCH đang được checkout ở '$OTHER_WT'. Dùng worktree đó."
    if [[ -z "$CUR" ]]; then
      git switch -c "$BRANCH"
    elif git show-ref --verify -q "refs/heads/$BRANCH"; then
      die "nhánh $BRANCH đã tồn tại ở nơi khác, không đổi tên '$CUR' đè lên được."
    else
      # Nhánh do agent view đặt tên (vd worktree-xxx) không khớp quy ước; đổi để
      # find_task_branch / finish-task / cleanup-task tìm ra theo T<N>.
      git branch -m "$CUR" "$BRANCH"
      info "Đã đổi tên nhánh '$CUR' -> '$BRANCH'."
    fi
  fi
  info "Dùng worktree hiện tại: $WT_PATH"
else
  cd "$MAIN_WT"
  OTHER_WT="$(worktree_of_branch "$BRANCH")"
  if [[ -n "$OTHER_WT" && "$OTHER_WT" != "$WT_PATH" ]]; then
    die "nhánh $BRANCH đang được checkout ở '$OTHER_WT'. Dùng worktree đó."
  fi

  if [[ -z "$OTHER_WT" ]]; then
    [[ ! -e "$WT_PATH" ]] || die "'$WT_PATH' đã tồn tại nhưng không phải worktree của $BRANCH. Kiểm tra tay."
    if git show-ref --verify -q "refs/heads/$BRANCH"; then
      git worktree add "$WT_PATH" "$BRANCH"
    else
      if [[ -z "$BASE" ]]; then
        # Gốc là origin/main chứ không phải main local: main local có thể mang
        # commit bảng TASKS.md chưa push (xem task-board.sh).
        git fetch -q origin main || warn "không fetch được origin, dùng origin/main đang có."
        BASE="origin/main"
      fi
      git rev-parse --verify -q "$BASE" >/dev/null || die "không thấy ref gốc '$BASE'."
      # --no-track: nhánh task không theo dõi main; upstream đặt khi push lần đầu.
      git worktree add --no-track -b "$BRANCH" "$WT_PATH" "$BASE"
    fi
  else
    info "Worktree đã có: $WT_PATH"
  fi
fi

# ═══════════════════════════════════════════════════════════════════════
#  2. .env và .env.worktree
# ═══════════════════════════════════════════════════════════════════════
cd "$WT_PATH"

# .env bị gitignore nên worktree mới không có. Sinh mới bằng gen-env.sh để
# mỗi worktree có khoá riêng, không chép khoá thật của checkout chính.
if [[ ! -f .env ]]; then
  bash scripts/gen-env.sh >/dev/null
  info "Đã sinh .env với khoá ngẫu nhiên riêng cho worktree."
fi

# Makefile nạp và export các biến này, nên chúng đè lên giá trị trong .env.
cat > .env.worktree <<EOF
# Sinh bởi scripts/agents/new-worktree.sh. Đừng sửa tay, chạy lại script để sinh lại.
TASK_ID=${TASK_ID}
TASK_BRANCH=${BRANCH}
COMPOSE_PROJECT_NAME=${PROJECT}
POSTGRES_DB=${DB_NAME}
WEB_PORT=${WEB_PORT}
API_PORT=${API_PORT}
POSTGRES_PORT=${POSTGRES_PORT}
REDIS_PORT=${REDIS_PORT}
AUTH_URL=http://localhost:${WEB_PORT}
CORS_ORIGINS=http://localhost:${WEB_PORT}
EOF

[[ -f docker-compose.worktree.yml ]] \
  || warn "nhánh gốc chưa có docker-compose.worktree.yml (PR quy trình chưa merge?). 'make up' sẽ đụng stack chính."

for port in "$WEB_PORT" "$API_PORT" "$POSTGRES_PORT" "$REDIS_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    warn "cổng $port đang có tiến trình lắng nghe (có thể là stack của chính task này nếu chạy lại)."
  fi
done

# ═══════════════════════════════════════════════════════════════════════
#  3. Docker: DB riêng + migration
# ═══════════════════════════════════════════════════════════════════════
STACK_NOTE="chưa dựng (--no-stack)"
if [[ $STACK -eq 1 ]]; then
  if has_docker && [[ -f docker-compose.worktree.yml ]]; then
    # Chỉ dựng phần backend: web build lâu và không cần cho migration.
    # --wait chờ healthcheck của postgres và api trước khi chạy migration.
    make --no-print-directory up-backend
    make --no-print-directory migrate
    STACK_NOTE="đang chạy (postgres, redis, api), đã migrate lên head"
  else
    STACK_NOTE="CHƯA dựng: Docker không chạy. Khi có Docker: make up-backend && make migrate"
    warn "Docker không chạy hoặc thiếu docker-compose.worktree.yml, bỏ qua bước dựng DB."
  fi
fi

cat <<EOF

  ✔ Worktree sẵn sàng cho ${TASK_ID}
    Thư mục   ${WT_PATH}
    Nhánh     ${BRANCH}
    Compose   ${PROJECT}  (${STACK_NOTE})
    Database  ${DB_NAME}  (test: ${DB_NAME}_test)
    Cổng      web ${WEB_PORT} · api ${API_PORT} · postgres ${POSTGRES_PORT} · redis ${REDIS_PORT}

$(if [[ "$MODE" == "here" ]]; then
  echo "  Bước tiếp: cứ code tiếp trong session/worktree này (không cần mở session mới)."
else
  printf '  Bước tiếp: mở session Claude Code MỚI trong thư mục trên:\n    cd "%s" && claude' "$WT_PATH"
fi)
EOF

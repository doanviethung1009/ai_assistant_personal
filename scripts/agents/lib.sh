# shellcheck shell=bash
# ═══════════════════════════════════════════════════════════════════════
#  Hàm dùng chung cho scripts/agents/*.sh. Chỉ `source`, không chạy trực tiếp.
#
#  Một task T<N> (N = 1..99) suy ra MỌI tên tài nguyên từ N, nên hai task
#  khác số không bao giờ trùng nhau:
#    worktree   ../<repo>-T<N>          (cạnh checkout chính)
#    compose    builder-t<N>            (container, volume, network riêng)
#    database   builder_ai_t<N>         (test: builder_ai_t<N>_test)
#    cổng       web 3100+N, api 8100+N, postgres 5500+N, redis 6400+N
#  Cổng mặc định của stack chính (3000/8000/5432/6379) nằm ngoài các dải này.
# ═══════════════════════════════════════════════════════════════════════

die()  { echo "LỖI: $*" >&2; exit 1; }
warn() { echo "CẢNH BÁO: $*" >&2; }
info() { echo "  $*"; }

# Mọi tài nguyên của task đều mang prefix này. Script KHÔNG BAO GIỜ thao tác
# trên project/DB không khớp regex ở assert_task_resource.
readonly TASK_PROJECT_PREFIX="builder-t"
readonly TASK_DB_PREFIX="builder_ai_t"

# parse_task_id <raw>: nhận "T12", "t12" hoặc "12"; đặt TASK_N=12, TASK_ID=T12.
parse_task_id() {
  local raw="${1:-}"
  raw="${raw#[Tt]}"
  [[ "$raw" =~ ^[0-9]{1,2}$ ]] || die "task-id phải dạng T<số> (T1..T99), nhận: '${1:-}'"
  TASK_N=$((10#$raw))
  (( TASK_N >= 1 && TASK_N <= 99 )) || die "task-id phải trong khoảng T1..T99"
  TASK_ID="T${TASK_N}"
}

# Checkout chính = worktree đầu tiên trong `git worktree list`. Tên repo và
# thư mục cha lấy từ đây, để chạy script từ worktree nào cũng ra cùng kết quả.
resolve_repo() {
  MAIN_WT="$(git worktree list --porcelain | awk '/^worktree /{print substr($0, 10); exit}')"
  [[ -n "$MAIN_WT" ]] || die "không tìm thấy git worktree. Chạy trong repo."
  REPO_NAME="$(basename "$MAIN_WT")"
  WT_PARENT="$(dirname "$MAIN_WT")"
}

# task_vars: cần TASK_N và resolve_repo đã chạy. Đặt các tên tài nguyên.
task_vars() {
  WT_PATH="${WT_PARENT}/${REPO_NAME}-${TASK_ID}"
  PROJECT="${TASK_PROJECT_PREFIX}${TASK_N}"
  DB_NAME="${TASK_DB_PREFIX}${TASK_N}"
  WEB_PORT=$((3100 + TASK_N))
  API_PORT=$((8100 + TASK_N))
  POSTGRES_PORT=$((5500 + TASK_N))
  REDIS_PORT=$((6400 + TASK_N))
}

# Hàng rào cuối trước mọi lệnh xoá: tên phải đúng dạng của task, không bao
# giờ là builder-ai (stack chính) hay builder_ai (DB chính).
assert_task_resource() {
  [[ "$PROJECT" =~ ^builder-t[0-9]{1,2}$ ]] || die "từ chối: project '$PROJECT' không có prefix task."
  [[ "$DB_NAME" =~ ^builder_ai_t[0-9]{1,2}$ ]] || die "từ chối: database '$DB_NAME' không có prefix task."
}

# find_task_branch: tìm nhánh <type>/T<N>-<slug> đã có (local). In tên nhánh hoặc rỗng.
find_task_branch() {
  git for-each-ref --format='%(refname:short)' "refs/heads/*/${TASK_ID}-*" | head -n 1
}

# worktree_of_branch <branch>: in đường dẫn worktree đang checkout nhánh đó, hoặc rỗng.
worktree_of_branch() {
  git worktree list --porcelain | awk -v b="refs/heads/$1" '
    /^worktree /{p = substr($0, 10)}
    /^branch /{ if (substr($0, 8) == b) { print p; exit } }'
}

has_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

# confirm <câu hỏi>: trả 0 nếu người dùng gõ y/yes. ASSUME_YES=1 bỏ qua hỏi.
confirm() {
  [[ "${ASSUME_YES:-0}" == "1" ]] && return 0
  local ans
  read -r -p "$1 [y/N] " ans || return 1
  [[ "$ans" =~ ^([yY]|yes)$ ]]
}

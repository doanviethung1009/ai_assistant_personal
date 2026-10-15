#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Đọc/ghi bảng điều phối TASKS.md trên nhánh `main` mà KHÔNG checkout main.
#
#  Dùng:
#    scripts/agents/task-board.sh show
#    scripts/agents/task-board.sh next-id
#    scripts/agents/task-board.sh add <ID> "<mô tả>" "<phạm vi file/module>"
#    scripts/agents/task-board.sh claim <ID> <branch> <worktree>
#    scripts/agents/task-board.sh status <ID> <todo|claimed|in-progress|review|done> ["ghi chú"]
#    scripts/agents/task-board.sh coord <ID> "<cần phối hợp gì>"
#    scripts/agents/task-board.sh decide "<quyết định và lý do>"
#    scripts/agents/task-board.sh sync      # đưa main local theo origin/main, giữ commit bảng
#
#  Vì sao ghi thẳng vào nhánh main: mọi worktree dùng chung một kho git, nên
#  commit vào ref `main` thì session ở worktree khác thấy NGAY bằng
#  `git show main:TASKS.md`, không cần push. Mỗi worktree có bản TASKS.md
#  riêng trên đĩa, sửa file đó thì session khác không thấy.
#
#  Chống ghi đè: commit tạo bằng plumbing (commit-tree) rồi `git update-ref`
#  kèm giá trị cũ (compare-and-swap). Hai session ghi cùng lúc thì một bên
#  thất bại CAS, đọc lại bảng mới và áp lại thay đổi. `claim` từ chối task
#  không ở trạng thái `todo`, nên hai session không nhận trùng một task.
#
#  Commit bảng chỉ nằm ở local cho tới khi User push `main`. Nhánh task luôn
#  rebase lên `origin/main` (không phải `main` local) để PR không kéo theo
#  commit bảng.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# shellcheck source=scripts/agents/lib.sh
source "$(dirname "$0")/lib.sh"

usage() { sed -n '3,13p' "$0" | sed -E 's/^#( {1,2})?//'; }

readonly BOARD="TASKS.md"
readonly STATUSES="todo claimed in-progress review done"

# ── Ghi vào main bằng compare-and-swap ──────────────────────────────
# board_commit <file nội dung mới> <message> <commit cha> <giá trị main mong đợi>
board_commit() {
  local blob tmpidx tree commit
  blob="$(git hash-object -w "$1")"
  tmpidx="$(mktemp)"
  GIT_INDEX_FILE="$tmpidx" git read-tree "$3"
  GIT_INDEX_FILE="$tmpidx" git update-index --cacheinfo "100644,${blob},${BOARD}"
  tree="$(GIT_INDEX_FILE="$tmpidx" git write-tree)"
  rm -f "$tmpidx"
  commit="$(git commit-tree "$tree" -p "$3" -m "$2")"
  git update-ref -m "task-board: $2" refs/heads/main "$commit" "$4" 2>/dev/null
}

# Nếu main đang checkout ở worktree nào đó, đổi ref sẽ làm index của worktree
# đó lệch (hiện như có thay đổi ngược). Luật mới: không ai làm việc trên main.
guard_main_not_checked_out() {
  local wt
  wt="$(worktree_of_branch main)"
  [[ -z "$wt" ]] || die "nhánh main đang được checkout ở '$wt'. Đổi worktree đó sang nhánh khác rồi chạy lại."
}

# edit_board <message> <hàm biến đổi>: đọc TASKS.md của main, gọi hàm với
# (file vào, file ra), commit. Thử lại tối đa 5 lần khi main bị đổi giữa chừng.
edit_board() {
  local msg="$1" fn="$2" attempt old in out
  guard_main_not_checked_out
  in="$(mktemp)"; out="$(mktemp)"
  for attempt in 1 2 3 4 5; do
    old="$(git rev-parse --verify -q refs/heads/main)" || die "không có nhánh main local."
    git show "${old}:${BOARD}" >"$in" 2>/dev/null \
      || die "main chưa có ${BOARD}. Merge PR thiết lập quy trình trước."
    "$fn" "$in" "$out"
    if cmp -s "$in" "$out"; then info "Không có gì thay đổi."; rm -f "$in" "$out"; return 0; fi
    if board_commit "$out" "$msg" "$old" "$old"; then
      rm -f "$in" "$out"
      info "Đã ghi vào main: $msg"
      return 0
    fi
    warn "main vừa bị session khác cập nhật, thử lại (lần $attempt)."
  done
  rm -f "$in" "$out"
  die "không ghi được sau 5 lần thử."
}

# ── Biến đổi nội dung bảng (awk đọc tham số qua ENVIRON để không bị xử lý \) ─

# Không cho ký tự phá bảng markdown hoặc xuống dòng vào ô.
check_cell() {
  [[ "$1" != *"|"* && "$1" != *$'\n'* ]] || die "giá trị không được chứa '|' hoặc xuống dòng: '$1'"
}

row_status() { # <file> <ID> → in trạng thái hoặc rỗng
  ID="$2" awk -F'|' '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    trim($2) == ENVIRON["ID"] { print trim($7); exit }' "$1"
}

do_add() {
  awk '
    BEGIN { row = "| " ENVIRON["ID"] " | " ENVIRON["DESC"] " | " ENVIRON["SCOPE"] " | - | - | todo | |" }
    /^\| ID \|/ { intable = 1 }
    intable && !/^\|/ { print row; intable = 0; done = 1 }
    { print }
    END { if (intable && !done) print row }' "$1" >"$2"
}

do_set_row() { # đổi ô của dòng ID; ô rỗng trong ENVIRON = giữ nguyên
  awk -F'|' -v OFS='|' '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    trim($2) == ENVIRON["ID"] {
      if (ENVIRON["BRANCH"] != "") $5 = " " ENVIRON["BRANCH"] " "
      if (ENVIRON["WT"] != "")     $6 = " " ENVIRON["WT"] " "
      if (ENVIRON["ST"] != "")     $7 = " " ENVIRON["ST"] " "
      if (ENVIRON["NOTE"] != "")   $8 = " " ENVIRON["NOTE"] " "
    }
    { print }' "$1" >"$2"
}

do_insert_after_marker() { # chèn LINE ngay dưới dòng MARKER (mới nhất lên đầu)
  awk '{ print } index($0, ENVIRON["MARKER"]) == 1 { print ENVIRON["LINE"] }' "$1" >"$2"
}

# ── Lệnh ────────────────────────────────────────────────────────────

cmd="${1:-}"; shift || true
case "$cmd" in
  -h|--help|"") usage; exit 0 ;;
esac

resolve_repo
cd "$MAIN_WT"

case "$cmd" in
  show)
    git show "main:${BOARD}"
    ;;

  next-id)
    max="$(git show "main:${BOARD}" | awk -F'|' '
      { id = $2; gsub(/[ \t]/, "", id) }
      id ~ /^T[0-9]+$/ { n = substr(id, 2) + 0; if (n > m) m = n }
      END { print m + 0 }')"
    echo "T$((max + 1))"
    ;;

  add)
    [[ $# -eq 3 ]] || die "dùng: add <ID> \"<mô tả>\" \"<phạm vi>\""
    parse_task_id "$1"; check_cell "$2"; check_cell "$3"
    git show "main:${BOARD}" >/dev/null 2>&1 || die "main chưa có ${BOARD}."
    [[ -z "$(row_status <(git show "main:${BOARD}") "$TASK_ID")" ]] || die "$TASK_ID đã có trong bảng."
    export ID="$TASK_ID" DESC="$2" SCOPE="$3"
    edit_board "chore(tasks): add $TASK_ID" do_add
    ;;

  claim)
    [[ $# -eq 3 ]] || die "dùng: claim <ID> <branch> <worktree>"
    parse_task_id "$1"; check_cell "$2"; check_cell "$3"
    export ID="$TASK_ID" BRANCH="$2" WT="$3" ST="claimed" NOTE=""
    # Kiểm trạng thái BÊN TRONG hàm biến đổi, để lần thử lại sau CAS cũng kiểm lại.
    claim_fn() {
      local st
      st="$(row_status "$1" "$ID")"
      [[ -n "$st" ]] || die "$ID chưa có trong bảng. Thêm bằng: task-board.sh add"
      [[ "$st" == "todo" ]] || die "$ID đang ở trạng thái '$st', đã có người nhận. Không làm task này."
      do_set_row "$1" "$2"
    }
    edit_board "chore(tasks): claim $TASK_ID" claim_fn
    ;;

  status)
    [[ $# -ge 2 && $# -le 3 ]] || die "dùng: status <ID> <trạng thái> [\"ghi chú\"]"
    parse_task_id "$1"
    [[ " $STATUSES " == *" $2 "* ]] || die "trạng thái phải là một trong: $STATUSES"
    check_cell "${3:-}"
    export ID="$TASK_ID" BRANCH="" WT="" ST="$2" NOTE="${3:-}"
    status_fn() {
      [[ -n "$(row_status "$1" "$ID")" ]] || die "$ID chưa có trong bảng."
      do_set_row "$1" "$2"
    }
    edit_board "chore(tasks): $TASK_ID -> $2" status_fn
    ;;

  coord)
    [[ $# -eq 2 ]] || die "dùng: coord <ID> \"<nội dung>\""
    parse_task_id "$1"; check_cell "$2"
    export MARKER="<!-- coord:insert -->" LINE="- [$(date +%F)] **$TASK_ID**: $2"
    edit_board "chore(tasks): coordination note for $TASK_ID" do_insert_after_marker
    ;;

  decide)
    [[ $# -eq 1 ]] || die "dùng: decide \"<quyết định và lý do>\""
    check_cell "$1"
    export MARKER="<!-- decision:insert -->" LINE="- [$(date +%F)] $1"
    edit_board "chore(tasks): record decision" do_insert_after_marker
    ;;

  sync)
    # Sau khi PR merge trên GitHub, main local bị lệch: origin/main có merge
    # commit mới, main local có commit bảng chưa push. Gom lại thành
    # origin/main + 1 commit mang TASKS.md mới nhất của local.
    guard_main_not_checked_out
    git fetch -q origin main
    local_sha="$(git rev-parse main)"; remote_sha="$(git rev-parse origin/main)"
    if [[ "$local_sha" == "$remote_sha" ]] || git merge-base --is-ancestor main origin/main; then
      git update-ref refs/heads/main "$remote_sha" "$local_sha"
      info "main local đã theo origin/main ($(git rev-parse --short "$remote_sha"))."
    elif git merge-base --is-ancestor origin/main main; then
      info "main local đi trước origin/main $(git rev-list --count origin/main..main) commit bảng. Push khi muốn: git push origin main"
    else
      base="$(git merge-base main origin/main)"
      only_board="$(git diff --name-only "$base" main | grep -vx "$BOARD" || true)"
      [[ -z "$only_board" ]] || die "main local có commit ngoài ${BOARD} chưa push: $only_board. Xử lý tay."
      [[ -z "$(git diff --name-only "$base" origin/main -- "$BOARD")" ]] \
        || die "origin/main cũng đổi ${BOARD}. Gộp tay: so sánh 'git diff $base main -- $BOARD'."
      tmp="$(mktemp)"; git show "main:${BOARD}" >"$tmp"
      board_commit "$tmp" "chore(tasks): sync board onto origin/main" "$remote_sha" "$local_sha" \
        || die "main vừa bị đổi, chạy lại sync."
      rm -f "$tmp"
      info "main local = origin/main + 1 commit bảng. Push khi muốn: git push origin main"
    fi
    ;;

  *) die "lệnh không hợp lệ: $cmd (xem --help)" ;;
esac

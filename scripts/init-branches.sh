#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Tạo nhánh môi trường 'uat' và 'prod' từ 'main'. Chạy một lần duy nhất.
#
#  Cả hai nhánh bắt đầu tại đúng commit hiện tại của main, nên chuỗi
#  ancestor  prod ⊆ uat ⊆ main  đúng ngay từ đầu.
#
#  Script không ghi đè nhánh đã tồn tại.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

TRUNK="${BRANCH_TRUNK:-main}"
UAT="${BRANCH_UAT:-uat}"
PROD="${BRANCH_PROD:-prod}"
REMOTE="${GIT_REMOTE:-origin}"

if [[ -t 1 ]]; then
	red=$'\033[31m'; green=$'\033[32m'; yellow=$'\033[33m'; dim=$'\033[2m'; off=$'\033[0m'
else
	red=""; green=""; yellow=""; dim=""; off=""
fi

die()  { echo "${red}✗ $*${off}" >&2; exit 1; }
ok()   { echo "${green}✓ $*${off}"; }
warn() { echo "${yellow}! $*${off}"; }
note() { echo "${dim}  $*${off}"; }

git rev-parse --git-dir >/dev/null 2>&1 || die "Không ở trong git repo."

original_branch="$(git rev-parse --abbrev-ref HEAD)"
trap 'git checkout --quiet "$original_branch" 2>/dev/null || true' EXIT

git show-ref --verify --quiet "refs/heads/$TRUNK" \
	|| die "Chưa có nhánh '$TRUNK'."

if ! git diff --quiet || ! git diff --cached --quiet; then
	die "Working tree còn thay đổi chưa commit. Commit hoặc stash trước."
fi

base="$(git rev-parse --short "$TRUNK")"
echo
note "Tạo nhánh môi trường tại $TRUNK = $base"
echo

created=()
for branch in "$UAT" "$PROD"; do
	if git show-ref --verify --quiet "refs/heads/$branch"; then
		warn "Nhánh '$branch' đã có, bỏ qua."
	else
		git branch "$branch" "$TRUNK"
		ok "Đã tạo '$branch' tại $base"
		created+=("$branch")
	fi
done

echo
if git remote get-url "$REMOTE" >/dev/null 2>&1; then
	for branch in "$UAT" "$PROD"; do
		if git push -u "$REMOTE" "$branch" 2>/dev/null; then
			ok "Đã push '$branch' lên $REMOTE"
		else
			warn "Không push được '$branch'. Nhánh vẫn tồn tại ở local."
			note "Thử lại sau bằng: git push -u $REMOTE $branch"
		fi
	done
else
	warn "Chưa có remote '$REMOTE'. Nhánh chỉ có ở local."
fi

echo
note "Kiểm tra lại: make git-status"
note "Bước tiếp theo: bật branch protection trên GitHub cho $TRUNK, $UAT, $PROD."
note "Chi tiết: docs/git-workflow.md"
echo

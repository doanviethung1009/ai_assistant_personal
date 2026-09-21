#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Thăng cấp code qua các nhánh môi trường:  main → uat → prod
#
#  Quy tắc duy nhất: chỉ fast-forward.
#
#  Nếu fast-forward thất bại nghĩa là nhánh đích có commit không nằm trên
#  nhánh nguồn — tức là ai đó commit trực tiếp vào nhánh môi trường.
#  Script dừng lại và nói rõ, thay vì tạo merge commit làm hai nhánh phân kỳ.
#
#  Dùng:
#    bash scripts/release.sh status          xem chênh lệch ba nhánh
#    bash scripts/release.sh uat             main → uat
#    bash scripts/release.sh prod 1.0.0      uat  → prod, gắn tag v1.0.0
#    bash scripts/release.sh rollback        chỉ in hướng dẫn, không tự chạy
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

TRUNK="${BRANCH_TRUNK:-main}"
UAT="${BRANCH_UAT:-uat}"
PROD="${BRANCH_PROD:-prod}"
REMOTE="${GIT_REMOTE:-origin}"

if [[ -t 1 ]]; then
	red=$'\033[31m'; green=$'\033[32m'; yellow=$'\033[33m'
	bold=$'\033[1m'; dim=$'\033[2m'; off=$'\033[0m'
else
	red=""; green=""; yellow=""; bold=""; dim=""; off=""
fi

die()  { echo "${red}✗ $*${off}" >&2; exit 1; }
ok()   { echo "${green}✓ $*${off}"; }
warn() { echo "${yellow}! $*${off}"; }
note() { echo "${dim}  $*${off}"; }

original_branch=""
restore_branch() {
	if [[ -n "$original_branch" ]]; then
		git checkout --quiet "$original_branch" 2>/dev/null || true
	fi
}
trap restore_branch EXIT

# ── Kiểm tra tiên quyết ────────────────────────────────────────────────

require_repo() {
	git rev-parse --git-dir >/dev/null 2>&1 || die "Không ở trong git repo."
	original_branch="$(git rev-parse --abbrev-ref HEAD)"
}

require_clean() {
	if ! git diff --quiet || ! git diff --cached --quiet; then
		die "Working tree còn thay đổi chưa commit. Commit hoặc stash trước khi thăng cấp."
	fi
}

fetch_remote() {
	if git remote get-url "$REMOTE" >/dev/null 2>&1; then
		git fetch --quiet --tags "$REMOTE" 2>/dev/null \
			|| warn "Không fetch được $REMOTE. Đang dùng dữ liệu local, có thể đã cũ."
	else
		warn "Chưa có remote '$REMOTE'. Chỉ làm việc trên nhánh local."
	fi
}

branch_exists() { git show-ref --verify --quiet "refs/heads/$1"; }

require_branch() {
	branch_exists "$1" || die "Chưa có nhánh '$1'. Tạo bằng: git branch $1 $TRUNK"
}

# Nhánh local có tụt lại so với remote không. Nếu có thì phải pull trước,
# nếu không sẽ thăng cấp một bản cũ hơn những gì đang có trên server.
require_synced() {
	local branch="$1" upstream
	upstream="$(git rev-parse --abbrev-ref --symbolic-full-name "${branch}@{u}" 2>/dev/null || true)"
	[[ -n "$upstream" ]] || return 0

	local behind
	behind="$(git rev-list --count "${branch}..${upstream}")"
	if [[ "$behind" -gt 0 ]]; then
		die "Nhánh '$branch' đang tụt $behind commit so với $upstream. Chạy: git checkout $branch && git pull --ff-only"
	fi
}

# ── status ─────────────────────────────────────────────────────────────

show_pending() {
	local base="$1" head="$2" label="$3" count
	branch_exists "$base" && branch_exists "$head" || return 0

	count="$(git rev-list --count "${base}..${head}")"
	if [[ "$count" -eq 0 ]]; then
		echo "  ${dim}${label}: không có gì${off}"
	else
		echo "  ${bold}${label}: ${count} commit${off}"
		git log --oneline --no-decorate "${base}..${head}" | sed 's/^/      /'
	fi
	echo
}

check_invariant() {
	local broken=0

	if branch_exists "$PROD" && branch_exists "$UAT"; then
		if ! git merge-base --is-ancestor "$PROD" "$UAT"; then
			warn "'$PROD' có commit không nằm trên '$UAT'. Thường là do hotfix chưa back-merge."
			note "Sửa: git checkout $TRUNK && git merge --no-ff $PROD && git checkout $UAT && git merge --ff-only $TRUNK"
			broken=1
		fi
	fi

	if branch_exists "$UAT" && branch_exists "$TRUNK"; then
		if ! git merge-base --is-ancestor "$UAT" "$TRUNK"; then
			warn "'$UAT' có commit không nằm trên '$TRUNK'. Đừng commit trực tiếp vào nhánh môi trường."
			broken=1
		fi
	fi

	[[ "$broken" -eq 0 ]] && ok "Chuỗi ancestor còn đúng: $PROD ⊆ $UAT ⊆ $TRUNK"
}

cmd_status() {
	fetch_remote
	echo
	printf '  %-22s %-10s %s\n' "NHÁNH" "COMMIT" "MÔ TẢ"
	printf '  %-22s %-10s %s\n' "──────────────────────" "──────────" "────────────────────────"

	local b label
	for b in "$TRUNK" "$UAT" "$PROD"; do
		case "$b" in
			"$TRUNK") label="$b (dev)" ;;
			"$UAT")   label="$b (UAT)" ;;
			*)        label="$b (production)" ;;
		esac
		if branch_exists "$b"; then
			printf '  %-22s %-10s %s\n' "$label" \
				"$(git rev-parse --short "$b")" \
				"$(git log -1 --format=%s "$b" | cut -c1-48)"
		else
			printf '  %-22s %s\n' "$label" "${yellow}(chưa tạo)${off}"
		fi
	done
	echo

	show_pending "$UAT" "$TRUNK" "Chờ lên UAT"
	show_pending "$PROD" "$UAT" "Chờ go-live"

	local last_tag
	last_tag="$(git describe --tags --abbrev=0 "$PROD" 2>/dev/null || true)"
	[[ -n "$last_tag" ]] && note "Release gần nhất trên $PROD: $last_tag"

	check_invariant
	echo
}

# ── Thăng cấp ──────────────────────────────────────────────────────────

promote() {
	local from="$1" to="$2"

	require_branch "$from"
	require_branch "$to"
	require_synced "$from"
	require_synced "$to"

	if [[ "$(git rev-parse "$from")" == "$(git rev-parse "$to")" ]]; then
		ok "'$to' đã trùng '$from', không có gì để thăng cấp."
		return 1
	fi

	if ! git merge-base --is-ancestor "$to" "$from"; then
		echo
		warn "Không thể fast-forward '$to' từ '$from'."
		note "'$to' có commit không nằm trên '$from':"
		git log --oneline --no-decorate "${from}..${to}" | sed 's/^/      /'
		echo
		note "Nhánh môi trường chỉ được đi lên bằng fast-forward. Back-merge trước:"
		note "  git checkout $from && git merge --no-ff $to"
		die "Dừng lại để không tạo phân kỳ."
	fi

	local count
	count="$(git rev-list --count "${to}..${from}")"
	echo
	echo "  ${bold}$count commit sẽ được đưa từ '$from' sang '$to':${off}"
	git log --oneline --no-decorate "${to}..${from}" | sed 's/^/      /'
	echo

	git checkout --quiet "$to"
	git merge --ff-only "$from" >/dev/null
	ok "'$to' đã fast-forward tới $(git rev-parse --short "$to")"
	return 0
}

push_branch() {
	local branch="$1"; shift
	if git remote get-url "$REMOTE" >/dev/null 2>&1; then
		git push "$REMOTE" "$branch" "$@"
		ok "Đã push '$branch' lên $REMOTE"
	else
		warn "Chưa có remote '$REMOTE', bỏ qua bước push."
	fi
}

cmd_uat() {
	require_clean
	fetch_remote
	if promote "$TRUNK" "$UAT"; then
		push_branch "$UAT"
		echo
		note "Bước tiếp theo trên máy UAT:"
		note "  cd /srv/builder-ai/uat && git pull --ff-only && make prod-build && make prod-up && make migrate && make smoke"
		echo
	fi
}

cmd_prod() {
	local version="${1:-}"
	[[ -n "$version" ]] || die "Thiếu số phiên bản. Ví dụ: bash scripts/release.sh prod 1.0.0"

	# Chuẩn hoá: nhận cả "1.0.0" và "v1.0.0"
	version="${version#v}"
	[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] \
		|| die "Phiên bản '$version' không theo semver. Dùng dạng 1.0.0 hoặc 1.0.0-rc1."

	local tag="v${version}"
	git rev-parse -q --verify "refs/tags/${tag}" >/dev/null \
		&& die "Tag '$tag' đã tồn tại. Chọn số phiên bản khác."

	require_clean
	fetch_remote

	# Không cho go-live thứ chưa từng chạy trên UAT.
	require_branch "$UAT"
	if [[ "$(git rev-parse "$UAT")" == "$(git rev-parse "$TRUNK")" ]]; then
		:
	else
		local unreleased
		unreleased="$(git rev-list --count "${UAT}..${TRUNK}")"
		note "$unreleased commit đang ở '$TRUNK' nhưng chưa lên '$UAT' — sẽ KHÔNG go-live lần này."
	fi

	if promote "$UAT" "$PROD"; then
		echo
		warn "Trước khi deploy lên production: chạy 'make backup' trên máy prod."
		echo

		git tag -a "$tag" -m "release $tag" "$PROD"
		ok "Đã gắn tag '$tag' tại $(git rev-parse --short "$PROD")"

		push_branch "$PROD" --follow-tags
		echo
		note "Bước tiếp theo trên máy production:"
		note "  cd /srv/builder-ai/prod && make backup && git pull --ff-only && make prod-build && make prod-up && make migrate && make health"
		echo
		note "Rollback nếu lỗi:  bash scripts/release.sh rollback"
		echo
	fi
}

cmd_rollback() {
	local current previous
	current="$(git describe --tags --abbrev=0 "$PROD" 2>/dev/null || echo '(chưa có tag)')"
	previous="$(git tag --sort=-v:refname --merged "$PROD" | sed -n '2p')"

	echo
	echo "  ${bold}Rollback production${off}"
	echo
	note "Tag đang chạy:   $current"
	note "Tag trước đó:    ${previous:-(không có)}"
	echo

	if [[ -z "$previous" ]]; then
		warn "Chưa có tag nào cũ hơn để lùi về."
		return 0
	fi

	echo "  Trên máy production, checkout tag cũ rồi dựng lại:"
	echo
	echo "      cd /srv/builder-ai/prod"
	echo "      git fetch --tags origin"
	echo "      git checkout $previous"
	echo "      make prod-build && make prod-up"
	echo
	warn "Migration KHÔNG tự lùi. Nếu release vừa rồi có đổi schema, phải:"
	note "  make downgrade   (lùi một bước Alembic)  — hoặc restore từ backups/"
	note "Đây là lý do luôn chạy 'make backup' trước khi migrate trên prod."
	echo
	note "Nhánh '$PROD' vẫn đang trỏ tới bản mới. Sau khi xác định nguyên nhân,"
	note "sửa trên '$TRUNK' rồi thăng cấp lại, đừng force-push '$PROD'."
	echo
}

# ── Điều phối ──────────────────────────────────────────────────────────

usage() {
	cat <<EOF

  Thăng cấp code qua các nhánh môi trường

    status              Xem chênh lệch giữa $TRUNK, $UAT, $PROD
    uat                 Fast-forward $UAT từ $TRUNK rồi push
    prod <phiên bản>    Fast-forward $PROD từ $UAT, gắn tag, push
    rollback            In hướng dẫn lùi về tag trước

  Ví dụ:
    bash scripts/release.sh status
    bash scripts/release.sh uat
    bash scripts/release.sh prod 1.0.0

EOF
}

main() {
	require_repo
	case "${1:-status}" in
		status)   cmd_status ;;
		uat)      cmd_uat ;;
		prod)     shift; cmd_prod "${1:-}" ;;
		rollback) cmd_rollback ;;
		-h|--help|help) usage ;;
		*) usage; die "Lệnh không hợp lệ: $1" ;;
	esac
}

main "$@"

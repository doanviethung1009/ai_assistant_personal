#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Sinh CHANGELOG.md từ git log, gom theo type của Conventional Commits.
#
#  Dùng:
#    bash scripts/changelog.sh              in ra stdout, không ghi file
#    bash scripts/changelog.sh --write      ghi đè CHANGELOG.md
#    bash scripts/changelog.sh --since TAG  chỉ lấy commit sau TAG
#
#  Commit không theo định dạng "type(scope): mô tả" (ví dụ commit cũ trước
#  khi có quy ước, hoặc merge commit) rơi vào nhóm "Khác", không bị bỏ qua.
#  Mục đích là có bản ghi đầy đủ, không phải lọc lịch sử cho đẹp.
#
#  Idempotent theo nghĩa: chạy lại nhiều lần với cùng input cho cùng output.
#  KHÔNG gộp dần qua từng lần chạy — mỗi lần --write là viết lại toàn bộ
#  file từ đầu lịch sử (hoặc từ --since), không phải chỉ thêm phần mới.
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

cd "$(dirname "$0")/.."

write=0
since=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --write) write=1; shift ;;
    --since) since="${2:?Thiếu giá trị cho --since}"; shift 2 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Tham số không hợp lệ: $1" >&2; exit 1 ;;
  esac
done

range=""
[[ -n "$since" ]] && range="${since}..HEAD"

# Định dạng: hash<TAB>subject đầy đủ, một dòng một commit.
log_lines="$(git log ${range:+"$range"} --no-merges --date=short \
  --pretty=format:'%h%x09%s' 2>/dev/null || true)"

if [[ -z "$log_lines" ]]; then
  echo "Không có commit nào trong khoảng đã chọn." >&2
  exit 1
fi

BUCKET_feat=""
BUCKET_fix=""
BUCKET_docs=""
BUCKET_refactor=""
BUCKET_perf=""
BUCKET_test=""
BUCKET_build=""
BUCKET_ci=""
BUCKET_chore=""
BUCKET_other=""

get_title() {
  case "$1" in
    feat) echo "Thêm mới" ;;
    fix) echo "Sửa lỗi" ;;
    docs) echo "Tài liệu" ;;
    refactor) echo "Tái cấu trúc" ;;
    perf) echo "Hiệu năng" ;;
    test) echo "Kiểm tra" ;;
    build) echo "Build" ;;
    ci) echo "CI/CD" ;;
    chore) echo "Dọn dẹp" ;;
    *) echo "Khác" ;;
  esac
}

GROUP_ORDER=(feat fix docs refactor perf test build ci chore other)

while IFS=$'\t' read -r hash subject; do
  [[ -z "$hash" ]] && continue

  type="other"
  desc="$subject"

  if [[ "$subject" =~ ^([a-z]+)(\([a-z0-9/_-]+\))?!?:[[:space:]]*(.+)$ ]]; then
    candidate="${BASH_REMATCH[1]}"
    if [[ "$candidate" == "feat" || "$candidate" == "fix" || "$candidate" == "docs" || "$candidate" == "refactor" || "$candidate" == "perf" || "$candidate" == "test" || "$candidate" == "build" || "$candidate" == "ci" || "$candidate" == "chore" ]]; then
      type="$candidate"
      desc="${BASH_REMATCH[3]}"
    fi
  fi

  line="- ${desc} (\`${hash}\`)"
  eval "BUCKET_${type}=\"\${BUCKET_${type}}\${line}
\""
done <<< "$log_lines"

today="$(date +%F)"

{
  echo "# Changelog"
  echo ""
  echo "Sinh tự động bằng \`bash scripts/changelog.sh --write\` từ \`git log\`,"
  echo "gom theo type của [Conventional Commits](.agents/skills/git-commit/SKILL.md)."
  echo "Đừng sửa tay — chạy lại script sau khi có commit mới."
  echo ""
  echo "## [Chưa phát hành] — cập nhật lần cuối ${today}"
  echo ""

  any_section=0
  for key in "${GROUP_ORDER[@]}"; do
    eval "val=\"\${BUCKET_${key}}\""
    if [[ -n "$val" ]]; then
      any_section=1
      title=$(get_title "$key")
      echo "### ${title}"
      echo ""
      printf '%s' "$val"
      echo ""
    fi
  done

  [[ "$any_section" -eq 0 ]] && echo "_Không có commit nào trong khoảng đã chọn._"
} > /tmp/builder-changelog.$$.tmp

if [[ "$write" -eq 1 ]]; then
  mv /tmp/builder-changelog.$$.tmp CHANGELOG.md
  echo "Đã ghi CHANGELOG.md"
else
  cat /tmp/builder-changelog.$$.tmp
  rm -f /tmp/builder-changelog.$$.tmp
fi

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

declare -A GROUP_TITLE=(
  [feat]="Thêm mới"
  [fix]="Sửa lỗi"
  [docs]="Tài liệu"
  [refactor]="Tái cấu trúc"
  [perf]="Hiệu năng"
  [test]="Kiểm tra"
  [build]="Build"
  [ci]="CI/CD"
  [chore]="Dọn dẹp"
  [other]="Khác"
)
# Thứ tự hiển thị cố định, không theo alphabet, để feat/fix luôn lên đầu —
# đó là phần người đọc changelog quan tâm nhất.
GROUP_ORDER=(feat fix docs refactor perf test build ci chore other)

declare -A BUCKET
for key in "${GROUP_ORDER[@]}"; do BUCKET["$key"]=""; done

while IFS=$'\t' read -r hash subject; do
  [[ -z "$hash" ]] && continue

  type="other"
  desc="$subject"

  if [[ "$subject" =~ ^([a-z]+)(\([a-z0-9/_-]+\))?!?:[[:space:]]*(.+)$ ]]; then
    candidate="${BASH_REMATCH[1]}"
    if [[ -n "${GROUP_TITLE[$candidate]:-}" ]]; then
      type="$candidate"
      desc="${BASH_REMATCH[3]}"
    fi
  fi

  line="- ${desc} (\`${hash}\`)"
  BUCKET["$type"]+="${line}"$'\n'
done <<< "$log_lines"

today="$(date +%F)"

{
  echo "# Changelog"
  echo ""
  echo "Sinh tự động bằng \`bash scripts/changelog.sh --write\` từ \`git log\`,"
  echo "gom theo type của [Conventional Commits](.kiro/steering/contributing.md)."
  echo "Đừng sửa tay — chạy lại script sau khi có commit mới."
  echo ""
  echo "## [Chưa phát hành] — cập nhật lần cuối ${today}"
  echo ""

  any_section=0
  for key in "${GROUP_ORDER[@]}"; do
    [[ -z "${BUCKET[$key]}" ]] && continue
    any_section=1
    echo "### ${GROUP_TITLE[$key]}"
    echo ""
    printf '%s' "${BUCKET[$key]}"
    echo ""
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

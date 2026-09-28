#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Kiểm tra end-to-end qua HTTP thật, không mock.
#
#  Mục đích: bạn tự xác nhận backend còn đúng sau mỗi lần sửa, không cần
#  nhờ agent đọc log và suy đoán. Tạo dữ liệu tạm rồi tự xoá.
#
#  Chạy:  make smoke
#  Exit:  0 nếu tất cả pass, 1 nếu có bất kỳ test fail
# ═══════════════════════════════════════════════════════════════════════

set -uo pipefail

cd "$(dirname "$0")/.."

GREEN=$'\033[32m'
RED=$'\033[31m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

if [[ ! -f .env ]]; then
  echo "Không có .env. Chạy: make env" >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

BASE="http://localhost:${API_PORT:-8000}"
KEY="${API_KEY:?API_KEY chưa có trong .env}"
TODAY="$(date +%F)"
STAMP="$(date +%s)"

PASS=0
FAIL=0
PROJECT_ID=""
TASK_ID=""
DUP_ID=""
NOTE_ID=""
NOTE_DUP_ID=""

# ── Tiện ích ───────────────────────────────────────────────────────────

jget() {
  python3 - "$@" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)
for key in sys.argv[2:]:
    try:
        data = data[int(key)] if isinstance(data, list) else data[key]
    except Exception:
        print("<missing>")
        sys.exit(0)
print("" if data is None else data)
PY
}

STATUS=""
BODY=""

req() {
  local method="$1" path="$2" data="${3:-}" key="${4-$KEY}"
  local args=(-sS -X "$method" -H "Content-Type: application/json" -w $'\n%{http_code}')
  [[ -n "$key" ]] && args+=(-H "X-API-Key: $key")
  [[ -n "$data" ]] && args+=(-d "$data")
  local raw
  raw="$(curl "${args[@]}" "$BASE$path" 2>/dev/null)"
  STATUS="$(tail -n1 <<<"$raw")"
  BODY="$(sed '$d' <<<"$raw")"
}

expect() {
  local name="$1" want="$2" got="$3"
  if [[ "$want" == "$got" ]]; then
    printf "  %sPASS%s  %s\n" "$GREEN" "$RESET" "$name"
    PASS=$((PASS + 1))
  else
    printf "  %sFAIL%s  %s\n" "$RED" "$RESET" "$name"
    printf "        mong đợi: %s\n" "$want"
    printf "        thực tế:  %s\n" "$got"
    [[ -n "$BODY" ]] && printf "        %sbody: %s%s\n" "$DIM" "${BODY:0:300}" "$RESET"
    FAIL=$((FAIL + 1))
  fi
}

cleanup() {
  # permanent=true để không bỏ rác lại trong thùng rác sau mỗi lần test
  [[ -n "$TASK_ID" ]] && req DELETE "/api/v1/tasks/$TASK_ID?permanent=true" >/dev/null 2>&1
  [[ -n "$DUP_ID" ]] && req DELETE "/api/v1/tasks/$DUP_ID?permanent=true" >/dev/null 2>&1
  [[ -n "$NOTE_ID" ]] && req DELETE "/api/v1/notes/$NOTE_ID?permanent=true" >/dev/null 2>&1
  [[ -n "$NOTE_DUP_ID" ]] && req DELETE "/api/v1/notes/$NOTE_DUP_ID?permanent=true" >/dev/null 2>&1
  # Project xoá sau cùng: task và note tham chiếu tới nó qua FK
  [[ -n "$PROJECT_ID" ]] && req DELETE "/api/v1/projects/$PROJECT_ID" >/dev/null 2>&1
  return 0
}
trap cleanup EXIT

echo ""
echo "${BOLD}Smoke test${RESET} $BASE"
echo ""

# ── Nhóm 1: healthcheck ────────────────────────────────────────────────

echo "${DIM}health${RESET}"

req GET /health/live
expect "liveness trả 200" "200" "$STATUS"

req GET /health/ready
expect "readiness trả 200" "200" "$STATUS"
expect "readiness status ok" "ok" "$(jget "$BODY" status)"
expect "database ok" "ok" "$(jget "$BODY" components database status)"
expect "redis ok" "ok" "$(jget "$BODY" components redis status)"

req GET /metrics "" ""
expect "metrics trả 200 không cần key" "200" "$STATUS"
if grep -q "http_requests_total" <<<"$BODY"; then
  expect "metrics có http_requests_total" "yes" "yes"
else
  expect "metrics có http_requests_total" "yes" "no"
fi

# ── Nhóm 2: xác thực ───────────────────────────────────────────────────

echo ""
echo "${DIM}xác thực${RESET}"

req GET /api/v1/tasks "" ""
expect "thiếu API key trả 401" "401" "$STATUS"

req GET /api/v1/tasks "" "sai-khoa-hoan-toan"
expect "API key sai trả 403" "403" "$STATUS"

# ── Nhóm 3: project ────────────────────────────────────────────────────

echo ""
echo "${DIM}project${RESET}"

req POST /api/v1/projects "{\"key\":\"SMOKE$STAMP\",\"name\":\"Smoke test\",\"color\":\"#4f8cff\"}"
expect "tạo project trả 201" "201" "$STATUS"
PROJECT_ID="$(jget "$BODY" id)"
[[ "$PROJECT_ID" == "<missing>" ]] && PROJECT_ID=""

req GET /api/v1/projects
expect "liệt kê project trả 200" "200" "$STATUS"

# ── Nhóm 4: vòng đời task ──────────────────────────────────────────────

echo ""
echo "${DIM}task${RESET}"

# Dựng sẵn giá trị JSON cho project_id để không phải nội suy điều kiện
# ngay trong chuỗi, chỗ đó rất dễ ghép sai.
if [[ -n "$PROJECT_ID" ]]; then
  PROJECT_JSON="\"$PROJECT_ID\""
else
  PROJECT_JSON="null"
fi

req POST /api/v1/tasks "{
  \"title\": \"Smoke task $STAMP\",
  \"description\": \"Tạo bởi scripts/smoke-test.sh\",
  \"priority\": \"high\",
  \"project_id\": $PROJECT_JSON,
  \"estimate_minutes\": 45,
  \"tags\": [\"Smoke Test\", \"smoke-test\", \"tmp\"]
}"
expect "tạo task trả 201" "201" "$STATUS"
TASK_ID="$(jget "$BODY" id)"
[[ "$TASK_ID" == "<missing>" ]] && TASK_ID=""
expect "task mặc định status todo" "todo" "$(jget "$BODY" status)"
expect "task mặc định source manual" "manual" "$(jget "$BODY" source)"
expect "tag được chuẩn hoá và loại trùng" "['smoke-test', 'tmp']" "$(jget "$BODY" tags)"
expect "event created được ghi" "created" "$(jget "$BODY" events 0 event_type)"

if [[ -z "$TASK_ID" ]]; then
  echo ""
  echo "  ${RED}Không tạo được task, bỏ qua phần còn lại.${RESET}"
  echo ""
  exit 1
fi

req GET "/api/v1/tasks?q=Smoke%20task%20$STAMP"
expect "tìm task theo q trả 200" "200" "$STATUS"
expect "tìm thấy đúng 1 task" "1" "$(jget "$BODY" total)"

req GET "/api/v1/tasks/$TASK_ID"
expect "lấy chi tiết task trả 200" "200" "$STATUS"

# Patch này chứa datetime và UUID trong diff của event payload.
# Nếu JSONB serialization không xử lý được thì sẽ ra 500.
req PATCH "/api/v1/tasks/$TASK_ID" \
  "{\"due_at\":\"${TODAY}T23:30:00+07:00\",\"scheduled_for\":\"$TODAY\",\"status\":\"in_progress\"}"
expect "patch due_at + scheduled_for + status trả 200" "200" "$STATUS"
expect "status đã đổi sang in_progress" "in_progress" "$(jget "$BODY" status)"
expect "scheduled_for đã lưu" "$TODAY" "$(jget "$BODY" scheduled_for)"

req POST "/api/v1/tasks/$TASK_ID/time" '{"minutes":30,"note":"smoke"}'
expect "ghi 30 phút trả 200" "200" "$STATUS"
expect "spent_minutes bằng 30" "30" "$(jget "$BODY" spent_minutes)"

req POST "/api/v1/tasks/$TASK_ID/time" '{"minutes":15}'
expect "ghi thêm 15 phút tích luỹ thành 45" "45" "$(jget "$BODY" spent_minutes)"

# ── Nhóm 5: agenda và stats ────────────────────────────────────────────

echo ""
echo "${DIM}agenda và thống kê${RESET}"

req GET /api/v1/tasks/agenda
expect "agenda trả 200" "200" "$STATUS"
expect "agenda dùng ngày hôm nay" "$TODAY" "$(jget "$BODY" reference_date)"
if grep -q "$TASK_ID" <<<"$BODY"; then
  expect "task đang làm xuất hiện trong agenda" "yes" "yes"
else
  expect "task đang làm xuất hiện trong agenda" "yes" "no"
fi

req GET /api/v1/tasks/stats
expect "stats trả 200" "200" "$STATUS"
expect "stats có reference_date đúng" "$TODAY" "$(jget "$BODY" reference_date)"
expect "stats ghi nhận 45 phút hôm nay" "45" "$(jget "$BODY" minutes_logged_today)"

# ── Nhóm 6: hoàn thành ─────────────────────────────────────────────────

echo ""
echo "${DIM}hoàn thành${RESET}"

req POST "/api/v1/tasks/$TASK_ID/complete"
expect "complete trả 200" "200" "$STATUS"
expect "status là done" "done" "$(jget "$BODY" status)"
completed_at="$(jget "$BODY" completed_at)"
if [[ -n "$completed_at" && "$completed_at" != "<missing>" ]]; then
  expect "completed_at được set" "yes" "yes"
else
  expect "completed_at được set" "yes" "no"
fi

req PATCH "/api/v1/tasks/$TASK_ID" '{"status":"todo"}'
expect "mở lại task trả 200" "200" "$STATUS"
reopened_at="$(jget "$BODY" completed_at)"
if [[ -z "$reopened_at" || "$reopened_at" == "<missing>" ]]; then
  expect "completed_at được xoá khi mở lại" "yes" "yes"
else
  expect "completed_at được xoá khi mở lại" "yes" "no (=$reopened_at)"
fi

# ── Nhóm 7: ràng buộc dữ liệu ──────────────────────────────────────────

echo ""
echo "${DIM}ràng buộc${RESET}"

req POST /api/v1/tasks '{"title":"   "}'
expect "title toàn khoảng trắng bị chặn 422" "422" "$STATUS"

req POST /api/v1/tasks '{"title":"x","project_id":"00000000-0000-0000-0000-000000000000"}'
expect "project_id không tồn tại bị chặn 422" "422" "$STATUS"

req POST /api/v1/tasks '{"title":"x","estimate_minutes":0}'
expect "estimate_minutes bằng 0 bị chặn 422" "422" "$STATUS"

# Kiểm tra unique (source, external_id) — nền tảng cho sync idempotent ở Phase 2
req POST /api/v1/tasks "{\"title\":\"Ext $STAMP\",\"source\":\"jira\",\"external_id\":\"SMOKE-$STAMP\"}"
expect "tạo task từ nguồn ngoài trả 201" "201" "$STATUS"
DUP_ID="$(jget "$BODY" id)"
[[ "$DUP_ID" == "<missing>" ]] && DUP_ID=""

req POST /api/v1/tasks "{\"title\":\"Ext trùng\",\"source\":\"jira\",\"external_id\":\"SMOKE-$STAMP\"}"
expect "external_id trùng bị chặn 409" "409" "$STATUS"

# ── Nhóm 8: sổ tay ─────────────────────────────────────────────────────

echo ""
echo "${DIM}sổ tay${RESET}"

# Nội dung nhiều dòng, có ký tự đặc biệt của shell và SQL. Nó phải được lưu
# và trả về NGUYÊN VĂN: server không parse, không escape, không thực thi.
req POST /api/v1/notes "{
  \"title\": \"Smoke note $STAMP\",
  \"kind\": \"sql\",
  \"content\": \"SELECT count(*)\\nFROM tasks\\nWHERE deleted_at IS NULL;\",
  \"description\": \"Tạo bởi scripts/smoke-test.sh\",
  \"context\": \"DB builder_ai\",
  \"project_id\": $PROJECT_JSON,
  \"tags\": [\"Smoke Test\", \"smoke-test\", \"tmp\"],
  \"is_pinned\": true
}"
expect "tạo note trả 201" "201" "$STATUS"
NOTE_ID="$(jget "$BODY" id)"
[[ "$NOTE_ID" == "<missing>" ]] && NOTE_ID=""
expect "note lưu đúng kind" "sql" "$(jget "$BODY" kind)"
expect "note mặc định source manual" "manual" "$(jget "$BODY" source)"
expect "note mặc định use_count 0" "0" "$(jget "$BODY" use_count)"
expect "tag của note được chuẩn hoá và loại trùng" "['smoke-test', 'tmp']" "$(jget "$BODY" tags)"
expect "content giữ nguyên xuống dòng" "SELECT count(*)
FROM tasks
WHERE deleted_at IS NULL;" "$(jget "$BODY" content)"

if [[ -z "$NOTE_ID" ]]; then
  echo ""
  echo "  ${RED}Không tạo được note, bỏ qua phần sổ tay còn lại.${RESET}"
else
  req GET /api/v1/notes
  expect "liệt kê note trả 200" "200" "$STATUS"

  # Tìm theo một đoạn nằm trong content chứ không nằm trong title. Đây là
  # cách dùng thật: thường chỉ nhớ một mẩu câu lệnh.
  req GET "/api/v1/notes?q=deleted_at%20IS%20NULL"
  expect "tìm note theo nội dung trả 200" "200" "$STATUS"
  note_found="$(jget "$BODY" total)"
  if [[ "$note_found" =~ ^[0-9]+$ ]] && [[ "$note_found" -ge 1 ]]; then
    expect "tìm thấy note qua content" "yes" "yes"
  else
    expect "tìm thấy note qua content" "yes" "no (total=$note_found)"
  fi

  req GET "/api/v1/notes?kind=sql"
  expect "lọc note theo kind trả 200" "200" "$STATUS"

  req GET "/api/v1/notes?pinned_only=true"
  expect "lọc note đã ghim trả 200" "200" "$STATUS"
  if grep -q "$NOTE_ID" <<<"$BODY"; then
    expect "note đã ghim xuất hiện khi lọc pinned_only" "yes" "yes"
  else
    expect "note đã ghim xuất hiện khi lọc pinned_only" "yes" "no"
  fi

  req GET /api/v1/notes/stats
  expect "thống kê note trả 200" "200" "$STATUS"
  sql_count="$(jget "$BODY" sql)"
  if [[ "$sql_count" =~ ^[0-9]+$ ]] && [[ "$sql_count" -ge 1 ]]; then
    expect "stats đếm được note loại sql" "yes" "yes"
  else
    expect "stats đếm được note loại sql" "yes" "no (=$sql_count)"
  fi

  req GET "/api/v1/notes/$NOTE_ID"
  expect "lấy chi tiết note trả 200" "200" "$STATUS"

  req PATCH "/api/v1/notes/$NOTE_ID" '{"is_dangerous":true,"context":"máy prod"}'
  expect "patch note trả 200" "200" "$STATUS"
  expect "is_dangerous đã bật" "True" "$(jget "$BODY" is_dangerous)"
  expect "context đã đổi" "máy prod" "$(jget "$BODY" context)"

  req POST "/api/v1/notes/$NOTE_ID/use"
  expect "ghi nhận lần dùng trả 200" "200" "$STATUS"
  expect "use_count tăng lên 1" "1" "$(jget "$BODY" use_count)"
  used_at="$(jget "$BODY" last_used_at)"
  if [[ -n "$used_at" && "$used_at" != "<missing>" ]]; then
    expect "last_used_at được set" "yes" "yes"
  else
    expect "last_used_at được set" "yes" "no"
  fi

  req POST "/api/v1/notes/$NOTE_ID/use"
  expect "use_count tích luỹ thành 2" "2" "$(jget "$BODY" use_count)"
fi

# Ràng buộc của note
req POST /api/v1/notes '{"title":"   ","content":"x"}'
expect "title note toàn khoảng trắng bị chặn 422" "422" "$STATUS"

req POST /api/v1/notes '{"title":"x","content":"   "}'
expect "content note toàn khoảng trắng bị chặn 422" "422" "$STATUS"

req POST /api/v1/notes '{"title":"x","content":"y","kind":"khong-ton-tai"}'
expect "kind không hợp lệ bị chặn 422" "422" "$STATUS"

req POST /api/v1/notes '{"title":"x","content":"y","project_id":"00000000-0000-0000-0000-000000000000"}'
expect "project_id note không tồn tại bị chặn 422" "422" "$STATUS"

# Unique (source, external_id) — nền tảng cho sync Obsidian ở Phase 2
req POST /api/v1/notes "{\"title\":\"Ext note $STAMP\",\"content\":\"x\",\"source\":\"obsidian\",\"external_id\":\"SMOKE-N-$STAMP\"}"
expect "tạo note từ nguồn ngoài trả 201" "201" "$STATUS"
NOTE_DUP_ID="$(jget "$BODY" id)"
[[ "$NOTE_DUP_ID" == "<missing>" ]] && NOTE_DUP_ID=""

req POST /api/v1/notes "{\"title\":\"Ext note trùng\",\"content\":\"y\",\"source\":\"obsidian\",\"external_id\":\"SMOKE-N-$STAMP\"}"
expect "external_id note trùng bị chặn 409" "409" "$STATUS"

# Route tĩnh phải thắng route động: nếu /{note_id} khớp trước thì "trash"
# sẽ bị hiểu là UUID và trả 422.
req GET /api/v1/notes/trash
expect "/notes/trash không bị /{note_id} bắt mất" "200" "$STATUS"

# ── Nhóm 9: xoá ────────────────────────────────────────────────────────

echo ""
echo "${DIM}thùng rác${RESET}"

# Xoá mặc định là xoá mềm
req DELETE "/api/v1/tasks/$TASK_ID"
expect "xoá task trả 204" "204" "$STATUS"

req GET "/api/v1/tasks/$TASK_ID"
expect "task đã xoá không đọc được nữa, trả 404" "404" "$STATUS"

req GET /api/v1/tasks/trash
expect "thùng rác trả 200" "200" "$STATUS"
if grep -q "$TASK_ID" <<<"$BODY"; then
  expect "task nằm trong thùng rác" "yes" "yes"
else
  expect "task nằm trong thùng rác" "yes" "no"
fi
expect "thùng rác báo đúng thời hạn giữ" "30" "$(jget "$BODY" retention_days)"

# Task trong thùng rác không được lọt vào agenda hay thống kê
req GET /api/v1/tasks/agenda
if grep -q "$TASK_ID" <<<"$BODY"; then
  expect "task đã xoá KHÔNG xuất hiện trong agenda" "no" "yes"
else
  expect "task đã xoá KHÔNG xuất hiện trong agenda" "no" "no"
fi

req GET /api/v1/tasks/stats
trash_total="$(jget "$BODY" trash_total)"
if [[ "$trash_total" =~ ^[0-9]+$ ]] && [[ "$trash_total" -ge 1 ]]; then
  expect "stats đếm được task trong thùng rác" "yes" "yes"
else
  expect "stats đếm được task trong thùng rác" "yes" "no (=$trash_total)"
fi

# Phục hồi
req POST "/api/v1/tasks/$TASK_ID/restore"
expect "phục hồi trả 200" "200" "$STATUS"
restored_deleted_at="$(jget "$BODY" deleted_at)"
if [[ -z "$restored_deleted_at" || "$restored_deleted_at" == "<missing>" ]]; then
  expect "deleted_at được xoá sau khi phục hồi" "yes" "yes"
else
  expect "deleted_at được xoá sau khi phục hồi" "yes" "no"
fi

req GET "/api/v1/tasks/$TASK_ID"
expect "task đọc lại được sau khi phục hồi" "200" "$STATUS"

req POST "/api/v1/tasks/$TASK_ID/restore"
expect "phục hồi task không ở trong thùng rác trả 422" "422" "$STATUS"

# Xoá vĩnh viễn
req DELETE "/api/v1/tasks/$TASK_ID?permanent=true"
expect "xoá vĩnh viễn trả 204" "204" "$STATUS"

req GET "/api/v1/tasks/$TASK_ID"
expect "task đã xoá vĩnh viễn trả 404" "404" "$STATUS"

req GET /api/v1/tasks/trash
if grep -q "$TASK_ID" <<<"$BODY"; then
  expect "task xoá vĩnh viễn không còn trong thùng rác" "no" "yes"
else
  expect "task xoá vĩnh viễn không còn trong thùng rác" "no" "no"
fi
TASK_ID=""

req POST /api/v1/tasks/trash/purge
expect "dọn quá hạn trả 200" "200" "$STATUS"
purged="$(jget "$BODY" purged)"
if [[ "$purged" =~ ^[0-9]+$ ]]; then
  expect "dọn quá hạn trả về số đếm" "yes" "yes"
else
  expect "dọn quá hạn trả về số đếm" "yes" "no (=$purged)"
fi

# ── Thùng rác của sổ tay ───────────────────────────────────────────────

if [[ -n "$NOTE_ID" ]]; then
  echo ""
  echo "${DIM}thùng rác sổ tay${RESET}"

  req DELETE "/api/v1/notes/$NOTE_ID"
  expect "xoá note trả 204" "204" "$STATUS"

  req GET "/api/v1/notes/$NOTE_ID"
  expect "note đã xoá không đọc được nữa, trả 404" "404" "$STATUS"

  req GET /api/v1/notes/trash
  expect "thùng rác note trả 200" "200" "$STATUS"
  if grep -q "$NOTE_ID" <<<"$BODY"; then
    expect "note nằm trong thùng rác" "yes" "yes"
  else
    expect "note nằm trong thùng rác" "yes" "no"
  fi
  expect "thùng rác note báo đúng thời hạn giữ" "30" "$(jget "$BODY" retention_days)"

  # Note trong thùng rác không được lọt vào danh sách hay tìm kiếm
  req GET "/api/v1/notes?q=deleted_at%20IS%20NULL"
  if grep -q "$NOTE_ID" <<<"$BODY"; then
    expect "note đã xoá KHÔNG xuất hiện khi tìm kiếm" "no" "yes"
  else
    expect "note đã xoá KHÔNG xuất hiện khi tìm kiếm" "no" "no"
  fi

  req POST "/api/v1/notes/$NOTE_ID/restore"
  expect "phục hồi note trả 200" "200" "$STATUS"
  note_restored="$(jget "$BODY" deleted_at)"
  if [[ -z "$note_restored" || "$note_restored" == "<missing>" ]]; then
    expect "deleted_at của note được xoá sau khi phục hồi" "yes" "yes"
  else
    expect "deleted_at của note được xoá sau khi phục hồi" "yes" "no"
  fi

  req POST "/api/v1/notes/$NOTE_ID/restore"
  expect "phục hồi note không ở trong thùng rác trả 422" "422" "$STATUS"

  req DELETE "/api/v1/notes/$NOTE_ID?permanent=true"
  expect "xoá vĩnh viễn note trả 204" "204" "$STATUS"

  req GET "/api/v1/notes/$NOTE_ID"
  expect "note đã xoá vĩnh viễn trả 404" "404" "$STATUS"
  NOTE_ID=""

  req POST /api/v1/notes/trash/purge
  expect "dọn quá hạn note trả 200" "200" "$STATUS"
fi

# ── Tổng kết ───────────────────────────────────────────────────────────

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "${GREEN}${BOLD}$PASS test pass, 0 fail.${RESET}"
  echo ""
  exit 0
else
  echo "${RED}${BOLD}$FAIL test fail${RESET}, $PASS pass."
  echo ""
  echo "  Xem log backend: make logs-api"
  echo ""
  exit 1
fi

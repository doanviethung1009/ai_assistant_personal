# Hook ghi vết phiên Claude Code (Giai đoạn 1)

> Cập nhật: 2026-10-08. Trạng thái: **giai đoạn 1, chỉ thêm**. AI log viết tay
> (`docs/ai_logs.md`, `data/ai-logs.json`, bảng `ai_logs`, `/ai-logs`) vẫn giữ nguyên để so sánh.

## Mục đích (WHY)

Nhật ký AI viết tay là lời **tự khai** của model: có thể sai hoặc thiếu, quá ngắn
(TB ~205 ký tự, thiếu prompt gốc, tool call, kết quả) nên không đủ để trace hay train, và
`docs/ai_logs.md` chỉ-nối-thêm nên hai nhánh song song luôn xung đột. Hook do harness
chạy, không phụ thuộc model có nhớ ghi hay không.

## Ghi gì, khi nào

Một script duy nhất `.claude/hooks/trace-hook.py` (Python 3 chuẩn thư viện) cho 3 sự kiện,
khai trong `.claude/settings.json`:

| Sự kiện | Ghi gì |
|---|---|
| `Stop`, `SubagentStop` | Thêm **một dòng** vào `turns.jsonl`: thời điểm UTC, `session_id`, tên hook, `cwd`, nhánh git, `git diff --stat` (15 dòng cuối), `prompt_id`, **prompt của User** ở lượt đó (khớp `prompt_id`, bỏ thông báo tác vụ nền), `last_assistant_message` (lời model tự khai, để đối chiếu với diff thật), `transcript_path`, số lần che theo mẫu. `SubagentStop` thêm `agent_id`, `agent_type`, `agent_prompt` (đề bài của chính subagent; `prompt` ở đó là prompt User gửi orchestrator) và sao chép transcript subagent đã lọc (bỏ qua nếu file không tồn tại). |
| `SessionEnd` | Sao chép transcript sang `sessions/<session_id>.<UTC>.jsonl` **sau khi lọc secret**. |

Không dùng `UserPromptSubmit`/`PostToolUse`: prompt lấy được từ transcript, tool call và kết
quả đã nằm sẵn trong transcript, nên thêm hook chỉ tăng độ ồn và chi phí mỗi lượt.

Trường stdin lấy từ tài liệu chính thức (code.claude.com/docs/en/hooks): `session_id`,
`transcript_path`, `cwd`, `hook_event_name`, `prompt_id`; `Stop` có `last_assistant_message`;
`SubagentStop` có `agent_id`, `agent_type`, `agent_transcript_path`. **Định dạng transcript
không được tài liệu mô tả**: quy tắc nhận prompt thật (dòng `type=user`, không
`isMeta`/`isSidechain`, `origin.kind` là `human` nếu có, `promptId` khớp `prompt_id`, `content` là chuỗi hoặc mảng không có `tool_result`) suy ra từ file
thật. Nếu Claude Code đổi định dạng, trường `prompt` sẽ rỗng nhưng hook vẫn chạy.

## Nơi lưu

Mặc định `~/.claude/trace/ai_assistant_personal/` (**ngoài repo**), đổi bằng biến
`CLAUDE_TRACE_DIR`. Thư mục quyền 700, file quyền 600. Hook **từ chối** ghi nếu thư mục nằm
trong repo. Không bao giờ commit.

```
turns.jsonl                         một dòng mỗi lượt
sessions/<sid>.<UTC>.jsonl          transcript đã lọc (resume tạo bản mới, không đè)
sessions/<sid>/subagent-<id>.<UTC>.jsonl  transcript subagent đã lọc
errors.log                          lỗi của hook (chỉ loại lỗi, không nội dung)
```

## Lọc secret

Áp dụng **trước khi chạm đĩa** (`.claude/hooks/trace_redact.py`), trên cấu trúc JSON đã
parse (JSON lồng nhau bị escape làm regex trên chuỗi thô trượt). Chỉ ghi **tên mẫu** đã che,
ví dụ `[REDACTED:bearer]`, không ghi giá trị:

- header `Authorization`, `Bearer`/`Basic`, JWT (`eyJ...`), token Atlassian (`ATATT...`),
  khoá nhà cung cấp (`sk-`, `ghp_`, `AKIA`, ...), khối private key;
- giá trị của khoá chứa `API_KEY`, `SECRET`, `PASSWORD`, `TOKEN`, `CREDENTIAL`
  (`IMPORT_COMMIT_SECRET`, `INTEGRATION_SECRET_KEY`, `POSTGRES_PASSWORD`, `*_API_KEY`...)
  ở dạng `KEY=value`, `key: value`, `"key": "value"`;
- chuỗi dài (>= 32 ký tự) đứng cạnh từ khoá nhạy cảm; toàn bộ userinfo của URL (`user:pw@`); khoá Fernet, `glpat-`, webhook Slack; tham số CLI (`--password X`, `curl -u u:p`, `mysql -pX`); "mật khẩu là X"; khoá JSON nhạy cảm che cả list/dict; dạng JSON bị escape trong lệnh shell;
- **email**;
- mọi giá trị trong `~/.env`, `<repo>/.env*` và `<repo>/apps/*/.env*` (trừ `*.example`), cùng biến môi trường có tên nhạy cảm
  (đọc vào RAM của hook, không lưu);
- blob nhị phân dài (ảnh base64) bị bỏ, vì vô ích và làm chậm bộ lọc.

**Đánh đổi:** vì che MỌI giá trị trong `.env` (>= 6 ký tự) nên các chữ như `postgres`, `localhost` bị che khắp nơi, kể cả trong code; an toàn hơn nhưng giảm giá trị dữ liệu train. Lọc xong mới cắt độ dài (không xẻ đôi token). Số khoá `*_tokens` (đếm token chi phí) được giữ. Bộ lọc **thiên về che thừa**; không đảm bảo
tuyệt đối (secret có dạng lạ, dữ liệu Jira dạng văn xuôi **không** bị che). Test:
`python3 -m unittest discover -s .claude/hooks/tests -v` (dữ liệu giả).

## An toàn cho phiên

Luôn exit 0, không in stdout (stdout của `Stop`/`SessionEnd` không vào context nhưng vẫn
giữ sạch), bắt mọi exception, báo thức tự ngắt (8 s; `SessionEnd` 25 s; `timeout` trong
settings là 10/10/30 s, vì `SessionEnd` mặc định chỉ có 1,5 s), không gọi mạng (chỉ `git`
cục bộ, timeout 3 s), không chặn tool, không ghi vào repo, ghi nối thêm bằng `O_APPEND` +
`flock`, không bao giờ cắt/ghi đè file có sẵn.

Hạn chế đã biết: mật khẩu chứa `/` hoặc `@` **thô** trong URL (không mã hoá %) không bị che hết; dạng mật khẩu đứng riêng không kèm từ khoá và không có tiền tố nhận dạng được (ví dụ chuỗi ngẫu nhiên ngắn) lọt; transcript lớn hơn ~100 MB có thể vượt báo thức 25 s của `SessionEnd` (đo: 31 MB mất 7,4 s) và không có bản sao (chỉ có dòng trong `errors.log`); transcript còn chứa kết quả `make psql` và nội dung Note (lệnh, SQL, cấu hình) ngoài các mẫu trên. Trên hệ file không hỗ trợ hard link (exFAT, SMB) hook dùng đổi tên thay cho link (race rất hẹp); bị SIGKILL giữa chừng có thể để lại `.tmp-*` (lần sau dọn bản cũ hơn 1 giờ).

**Đã kiểm chứng (2026-10-08):** một phiên `claude -p` thật chạy Stop và SessionEnd qua harness, sinh `turns.jsonl` và `sessions/<sid>.<UTC>.jsonl` (quyền 600, thư mục 700, không có `errors.log`) với transcript nhỏ. Test hiệu năng transcript lớn (mặc định bỏ qua): `TRACE_SLOW_TESTS=1 python3 -m unittest discover -s .claude/hooks/tests -k large`. Nếu `SessionEnd` bị cắt vì timeout, đặt `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`. Giá trị trong `.env` là đường dẫn (bắt đầu bằng `/` hoặc `~`) không bị che, vì đường dẫn không phải secret.

## Bật hook (mặc định TẮT)

Hook nằm trong `.claude/settings.json` dùng chung nhưng **chỉ ghi khi `CLAUDE_TRACE_ENABLED=1`**,
để người clone repo không bị lưu transcript (có thể chứa dữ liệu Jira công ty) khi chưa biết.
Bật ở máy mình, trong `.claude/settings.local.json` (đã gitignore):

```json
{ "env": { "CLAUDE_TRACE_ENABLED": "1" } }
```

Khi thêm khoá `env` vào file này, giữ nguyên khoá `permissions` có sẵn. Chưa bật thì hook thoát
ngay, không đọc stdin, không tạo thư mục.

## Tắt hook

Bỏ biến `CLAUDE_TRACE_ENABLED` (hoặc đặt khác `1`) trong `.claude/settings.local.json`. Dữ liệu cũ nằm
nguyên ở thư mục trace; xoá bằng `rm -r ~/.claude/trace/ai_assistant_personal`.

## Dùng dữ liệu để train

`turns.jsonl` là chỉ mục: nối `prompt`, `diff_stat` (sự thật) với `last_assistant_message`
(lời khai) để phát hiện lệch; `sessions/*.jsonl` chứa chuỗi hội thoại đầy đủ gồm tool call và
kết quả. Chưa có pipeline train; đó là việc giai đoạn sau.

## Rủi ro và chính sách

- Transcript chứa **dữ liệu Jira của công ty** và email của User (email bị che, nội dung Jira
  thì không). **Quyết định của User (2026-10-08): chưa rõ chính sách, chỉ lưu cục bộ, CHƯA
  được dùng để train** cho đến khi User xác nhận. Không sao chép, upload hay chia sẻ thư mục
  trace.
- Trace tăng theo thời gian (transcript hàng MB mỗi phiên). Xoay vòng: mỗi lần `SessionEnd`, transcript trong `sessions/` cũ hơn `CLAUDE_TRACE_RETENTION_DAYS` (mặc định 90; `0` = giữ mãi) bị xoá. `turns.jsonl` không bị xoá, và dọn dẹp không theo symlink.
- Khi đã bật, hook chạy trên mọi lượt của mọi session trong repo này, kể cả subagent.

## File liên quan

`.claude/hooks/trace-hook.py`, `.claude/hooks/trace_redact.py`,
`.claude/hooks/tests/test_trace_hook.py`, `.claude/settings.json`.

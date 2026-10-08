# Claude CLI Quickstart — chạy Claude Code với cấu hình multi-agent của repo

> Dành cho người mới mở repo này bằng Claude Code (CLI hoặc app desktop). Đọc xong trong 5 phút là
> chạy được. Chi tiết cơ chế nạp context nằm ở `docs/CLAUDE_OPERATING_GUIDE.md`, luồng phối hợp
> agent ở `docs/MULTI_AGENT_WORKFLOW.md`.

---

## 1. Chạy lần đầu

```bash
cd ai_assistant_personal
claude
```

Claude Code tự đọc `CLAUDE.md` ở gốc repo. File này chỉ làm điểm vào: nó import `AGENTS.md`
(luật chung cho mọi agent) và chỉ ra tài liệu nào đọc khi cần. Luật chi tiết (`.agents/rules/`)
và skill (`.agents/skills/`) được nạp qua hai symlink `.claude/rules` và `.claude/skills`, nên
**không có bản sao thứ hai để lệch nhau**. Sửa ở `.agents/`.

Việc đầu tiên nên làm trong session mới:

```text
Đọc docs/AI_HANDOFF_STATE.md rồi tóm tắt trạng thái hiện tại cho tôi.
```

## 2. Cấu trúc `.claude/`

| Đường dẫn | Vai trò |
|---|---|
| `.claude/agents/` | 5 subagent: `architect`, `backend-dev`, `frontend-dev`, `db-reviewer`, `code-reviewer` |
| `.claude/settings.json` | Quyền (allow / ask / deny) và hook, dùng chung cả team |
| `.claude/hooks/guard-bash.sh` | Chặn lệnh phá dữ liệu trước khi chạy |
| `.claude/hooks/no-patch-scripts.sh` | Chặn tạo `patch_*.py` / `fix_*.py` để sửa code gián tiếp |
| `.claude/rules` → `.agents/rules` | Symlink tới luật code |
| `.claude/skills` → `.agents/skills` | Symlink tới skill (commit, migration, QC...) |

Cài đặt cá nhân đặt ở `.claude/settings.local.json` và `CLAUDE.local.md` (đã nằm trong `.gitignore`).

## 3. Mô hình orchestrator + subagent

Session chính là **orchestrator**: hiểu yêu cầu, chia việc, gọi subagent, tổng hợp kết quả.

| Việc | Subagent | Ghi chú |
|---|---|---|
| Epic chạm từ 2 tầng (DB + API + Web) | `architect` | Ra `docs/specs/<epic>.md`, chờ bạn chốt |
| Code backend | `backend-dev` | Chỉ sửa `apps/core/`, theo spec |
| Code web | `frontend-dev` | Chỉ sửa `apps/web/`, theo spec |
| Có migration hoặc đổi model | `db-reviewer` | Chỉ đọc |
| Trước commit / merge | `code-reviewer` | Chỉ đọc, context sạch |

Việc nhỏ (sửa 1–2 file, một tầng) thì orchestrator tự làm, không cần subagent.

Xem hoặc tạo subagent trong CLI bằng `/agents`. Gọi đích danh bằng prompt:

```text
Dùng architect thiết kế tính năng "tag cho Note", ra spec trong docs/specs/ rồi dừng chờ tôi duyệt.
```

```text
Spec note-tags đã chốt. Chạy backend-dev và frontend-dev song song theo mục Ownership, sau đó code-reviewer.
```

Chạy song song hai dev agent chỉ khi spec đã tách Ownership rõ, và mỗi agent dùng một git worktree riêng.

## 4. Quyền và hàng rào an toàn

Cấu hình trong `.claude/settings.json`:

- **Tự chạy, không hỏi**: `make lint`, `make smoke`, `make ps`, `make history`, `make gen-types`,
  `git status`, `git diff`, `git log`, `npx tsc --noEmit`.
- **Luôn hỏi**: `git push`, `make migrate`, `make downgrade`, `make down`.
- **Cấm hẳn**: đọc `.env*` và `secrets/`, `docker compose down -v`, `git push --force` / `-f`,
  `git reset --hard`.

Hook `guard-bash.sh` là lớp thứ hai, chặn cả khi lệnh đi vòng qua rule: xoá volume Docker,
`DROP` / `TRUNCATE` / `DELETE FROM` gõ thẳng qua `psql`, force push, `git reset --hard`,
`git clean -f`. Hook là hàng rào cứng, áp dụng cho cả session chính lẫn mọi subagent. Luật viết
bằng chữ chỉ là lời dặn, agent có thể quên khi context dài.

Hook `no-patch-scripts.sh` buộc agent dùng Edit trực tiếp thay vì sinh script `patch_*.py`.
Script một lần thật sự cần thiết thì đặt tên khác và cất trong `scripts/patches/`.

## 5. Lệnh hay dùng

Mọi thao tác đã có `make`. Chạy `make` để xem danh sách; đừng tự viết `docker compose ...`.

| Cần gì | Lệnh |
|---|---|
| Dựng stack | `make up` |
| Kiểm tra backend | `make smoke` |
| Lint và typecheck | `make lint` |
| Log | `make logs-api`, `make logs-web` |
| Migration mới | `make migration m="mô tả"` rồi `make migrate` |

Trong session CLI: `/memory` xem file context đã nạp, `/agents` quản lý subagent, `/clear` mở
ngữ cảnh mới, `/compact` nén hội thoại dài.

## 6. Quy trình commit và push

1. Orchestrator gọi `code-reviewer` trên diff của nhánh so với `main`.
2. Sửa các vấn đề reviewer nêu, rồi commit theo skill `git-commit` (Conventional Commits,
   có scope, ví dụ `docs(ai): ...`). Chỉ `git add` đúng file thuộc task, không dùng `git add -A`.
3. Push luôn cần bạn xác nhận (hook và `ask` rule chặn sẵn). Nhánh đẩy lên là nhánh tính năng,
   không bao giờ force push.

Chỉ orchestrator được cập nhật `docs/AI_HANDOFF_STATE.md`, đăng ký tài liệu mới vào
`apps/web/lib/docs.ts`. Không còn ghi AI log tay; hook ghi vết (`docs/CLAUDE_TRACE_HOOKS.md`) thay thế.

## 7. Xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Agent báo `BLOCKED by .claude/hooks/guard-bash.sh` | Lệnh bị hook chặn. Đọc lý do, đổi cách làm hoặc tự chạy tay nếu thật sự cần |
| Agent không thấy rule / skill | Symlink `.claude/rules` hoặc `.claude/skills` bị hỏng. Kiểm tra bằng `ls -la .claude` |
| Hook chặn nhầm khi viết commit message hoặc body PR | `guard-bash.sh` quét cả chuỗi lệnh bằng regex, nên tên một lệnh nguy hiểm xuất hiện trong văn bản cũng bị coi là lệnh thật. Diễn đạt lại câu chữ (ví dụ "các lệnh git huỷ thay đổi"), không tắt hook. Viết file bằng công cụ Edit/Write cũng tránh được |
| Hook không chạy | Mất quyền thực thi. Chạy `chmod +x .claude/hooks/*.sh` |
| Không đọc được `.env` | Chủ ý. Cần biết biến nào thì xem `.env.example` |
| Task lớn bị lạc hướng | Mở session mới, bắt đầu bằng "đọc `docs/AI_HANDOFF_STATE.md`" |

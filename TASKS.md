# Bảng điều phối task (multi-session)

> **Đọc trước khi sửa.**
> - Bản có hiệu lực là bản trên **nhánh `main`**: `scripts/agents/task-board.sh show`.
>   File này trong worktree của anh/chị có thể đã cũ.
> - **Không sửa file này bằng tay trong nhánh task.** Mọi thay đổi đi qua
>   `scripts/agents/task-board.sh` (add, claim, status, coord, decide). Script ghi thẳng
>   vào ref `main` bằng compare-and-swap, nên hai session không ghi đè nhau và không
>   nhận trùng một task.
> - Một task là một nhánh `<type>/T<N>-<slug>` và một worktree `../<repo>-T<N>`.
>   Quy trình đầy đủ ở `docs/agents/WORKFLOW.md`.
>
> **Trạng thái:** `todo` (chưa ai nhận), `claimed` (đã nhận, đang dựng worktree),
> `in-progress` (đang code), `review` (đã mở PR), `done` (đã merge và dọn worktree).
>
> **Phạm vi file/module** liệt kê đúng thư mục hoặc file task được sửa, ví dụ
> `apps/web/app/notes/**, apps/web/components/note-*`. Cần sửa ngoài phạm vi thì ghi
> vào mục "Cần phối hợp" (`task-board.sh coord`) và dừng lại hỏi User.

## Bảng task

| ID | Mô tả | Phạm vi file/module | Branch | Worktree | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|
| T1 | Thiết lập quy trình multi-session (TASKS.md, skill, script worktree) | `CLAUDE.md`, `TASKS.md`, `docs/agents/**`, `scripts/agents/**`, `.agents/skills/{start-task,finish-task,handoff,sync-main,cleanup-task}/**`, `.agents/rules/{migrations,root-config,core-shared}.md`, `Makefile`, `docker-compose.worktree.yml` | chore/multi-agent-workflow | ../ai_assistant_personal-setup | review | Tạo trước khi có quy trình nên không theo tên nhánh `T<N>` |

## Cần phối hợp

Việc một task cần nhưng nằm ngoài phạm vi của nó, hoặc hai task đụng cùng file. Mới nhất ở trên.
Ghi bằng `scripts/agents/task-board.sh coord <ID> "<nội dung>"`.

<!-- coord:insert -->

## Quyết định đã chốt

Quyết định ảnh hưởng nhiều task (kiến trúc, quy ước, ai sở hữu file dùng chung). Mới nhất ở trên.
Ghi bằng `scripts/agents/task-board.sh decide "<quyết định và lý do>"`.

<!-- decision:insert -->
- [2026-10-15] Mỗi worktree chạy compose project riêng `builder-t<N>` (Docker), DB `builder_ai_t<N>`, cổng web 3100+N, api 8100+N, postgres 5500+N, redis 6400+N. Không trỏ vào DB của stack chính hay VM dev.
- [2026-10-15] Tên nhánh giữ type của Conventional Commits: `<type>/T<N>-<slug>` (vd `feat/T12-note-tags`).
- [2026-10-15] TASKS.md chỉ ghi trên nhánh `main` qua `task-board.sh`; nhánh task rebase lên `origin/main`, không lên `main` local.
- [2026-10-15] Migration mới có timestamp UTC ở đầu tên file (`file_template` trong `apps/core/alembic.ini`).

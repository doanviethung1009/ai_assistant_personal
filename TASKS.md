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
| T2 | Kiểm tra và tăng RAM/CPU VM dev Proxmox (ai-dev-01): nâng 2.5→3.5 GB, 3 nhân, cpu host; hạ prod 4 GB; đo lại OOM/swap; cân nhắc tắt WATCHPACK_POLLING trên dev | docs/PROXMOX_OPERATIONS.md, docs/SYSTEMS_INVENTORY.md, infra/proxmox/ansible/**; (nếu tắt polling: docker-compose.yml) | - | - | todo | |
| T3 | Bỏ mặc định AUTH_URL=http://localhost:3000 trong compose: thiếu AUTH_URL thì web báo thiếu cấu hình (/config-error) thay vì lặng lẽ đẩy người dùng về localhost sau đăng nhập. Gốc lỗi: VM dev thiếu AUTH_URL nên login xong bị redirect về localhost | docker-compose.yml (dòng AUTH_URL), .env.example, docs/GOOGLE_OAUTH_SETUP.md, docs/PROXMOX_DEPLOY.md; kiểm Makefile (new-worktree.sh đã tự đặt AUTH_URL) | fix/T3-auth-url-no-default | ../ai_assistant_personal-T3 | done | PR #54 merged 2026-10-16 |
| T4 | Bổ sung tài liệu deploy prod: (1) deploy-runbook.md thêm hướng dẫn auth/login (AUTH_URL, AUTH_SECRET, CORE_JWT_SECRET, ADMIN_EMAILS, INTEGRATION_SECRET_KEY, make env-fill, make auth-create-local; dòng trong Case 4 và checklist; case bật login lần đầu trên prod); (2) PROXMOX_DEPLOY.md mục 0 và 8.2 ghi rõ pipeline Deploy chưa chạy được, hiện deploy tay theo runbook; (3) rà Case 1 (make migration-init có còn đúng khi migrations đã nằm trong repo) | docs/deploy-runbook.md, docs/PROXMOX_DEPLOY.md (mục 0, 8.2), docs/INDEX.md nếu cần; chỉ docs, không đụng file cấu hình dùng chung | docs/T4-deploy-runbook-auth | ../ai_assistant_personal-T4 | done | PR #56 merged 2026-10-16 |

## Cần phối hợp

Việc một task cần nhưng nằm ngoài phạm vi của nó, hoặc hai task đụng cùng file. Mới nhất ở trên.
Ghi bằng `scripts/agents/task-board.sh coord <ID> "<nội dung>"`.

<!-- coord:insert -->
- [2026-10-16] **T3**: Cần thêm AUTH_URL (http://{{ ansible_host }}:{{ web_port }}) vào infra/proxmox/ansible/roles/app/tasks/main.yml:38 cạnh CORS_ORIGINS; staging/prod chưa có AUTH_URL nên web sẽ hiện /config-error ở lần tạo lại web tới. Ngoài phạm vi T3.

## Quyết định đã chốt

Quyết định ảnh hưởng nhiều task (kiến trúc, quy ước, ai sở hữu file dùng chung). Mới nhất ở trên.
Ghi bằng `scripts/agents/task-board.sh decide "<quyết định và lý do>"`.

<!-- decision:insert -->
- [2026-10-15] Mỗi worktree chạy compose project riêng `builder-t<N>` (Docker), DB `builder_ai_t<N>`, cổng web 3100+N, api 8100+N, postgres 5500+N, redis 6400+N. Không trỏ vào DB của stack chính hay VM dev.
- [2026-10-15] Tên nhánh giữ type của Conventional Commits: `<type>/T<N>-<slug>` (vd `feat/T12-note-tags`).
- [2026-10-15] TASKS.md chỉ ghi trên nhánh `main` qua `task-board.sh`; nhánh task rebase lên `origin/main`, không lên `main` local.
- [2026-10-15] Migration mới có timestamp UTC ở đầu tên file (`file_template` trong `apps/core/alembic.ini`).

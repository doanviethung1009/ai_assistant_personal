---
# Claude Code đọc `paths`, Kiro/Antigravity đọc `fileMatchPattern` - giữ cả hai.
paths:
  - "apps/core/migrations/**"
  - "apps/core/alembic.ini"
  - "apps/core/app/models/**"
inclusion: fileMatch
fileMatchPattern: ["apps/core/migrations/**/*", "apps/core/alembic.ini", "apps/core/app/models/**/*"]
---

# Vùng nhạy cảm: migration và model DB (multi-session)

Nạp khi mở migration, `alembic.ini` hoặc model. Quy trình chi tiết ở skill `db-migration`,
quy trình đa session ở `docs/agents/WORKFLOW.md`.

- **Chỉ sửa khi phạm vi task trong `TASKS.md` có ghi migration/model.** Không có thì
  `scripts/agents/task-board.sh coord T<N> "..."` và dừng lại hỏi User.
- **Mỗi thay đổi schema là một file migration mới**, sinh bằng `make migration m="..."`. Tên file
  tự có timestamp UTC ở đầu (`file_template` trong `alembic.ini`). Không đặt tên tay.
- **Không sửa migration đã merge vào `main`** (kể cả đổi tên file hay sửa comment). Sai thì viết
  migration mới sửa lại.
- **Chỉ chạy `make migrate` / `make downgrade` trong worktree của mình**: Makefile trỏ vào DB
  `builder_ai_t<N>` của task. Nếu thư mục hiện tại không có `.env.worktree` thì đang ở stack
  chính: dừng, không migrate.
- **Không chạy migration vào VM dev hay DB dùng chung** bằng `DATABASE_URL` tự đặt.
- **Trước khi mở PR**: `make history` phải có đúng một head. Hai nhánh cùng sinh migration từ một
  `down_revision` thì nhánh merge sau sửa `down_revision` của mình, không tự `alembic merge`.
- Đổi `alembic.ini` là đổi file dùng chung: chỉ khi task nói rõ.

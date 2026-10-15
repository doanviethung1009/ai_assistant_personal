---
# Claude Code đọc `paths`, Kiro/Antigravity đọc `fileMatchPattern` - giữ cả hai.
paths:
  - "apps/core/app/core/**"
  - "apps/core/app/db/**"
  - "apps/core/app/main.py"
  - "apps/core/app/schemas/common.py"
  - "apps/core/app/services/errors.py"
  - "apps/core/app/services/clock.py"
  - "apps/web/lib/api.ts"
  - "apps/web/lib/types.ts"
  - "apps/web/lib/generated/**"
  - "apps/web/app/actions.ts"
  - "apps/web/middleware.ts"
  - "apps/web/auth.ts"
inclusion: fileMatch
fileMatchPattern: ["apps/core/app/core/**/*", "apps/core/app/db/**/*", "apps/core/app/main.py", "apps/core/app/schemas/common.py", "apps/core/app/services/errors.py", "apps/core/app/services/clock.py", "apps/web/lib/api.ts", "apps/web/lib/types.ts", "apps/web/lib/generated/**/*", "apps/web/app/actions.ts", "apps/web/middleware.ts", "apps/web/auth.ts"]
---

# Vùng nhạy cảm: module lõi dùng chung (multi-session)

Nạp khi mở file mà gần như mọi tính năng đều đi qua: cấu hình, bảo mật, session DB, hợp đồng
API giữa web và core, Server Action, xác thực. Một thay đổi nhỏ ở đây ảnh hưởng mọi task đang
chạy song song.

- **Chỉ sửa khi phạm vi task trong `TASKS.md` có file này.** Task tính năng thường chỉ cần
  *thêm* vào file dùng chung (một type mới trong `types.ts`, một hàm trong `api.ts`): vẫn phải
  ghi rõ trong phạm vi, hoặc `task-board.sh coord` rồi hỏi User.
- **Chỉ thêm, không đổi chữ ký có sẵn.** Đổi tên/kiểu của hàm, type, setting đang dùng thì là
  task riêng, không làm kèm trong task tính năng.
- **`apps/web/lib/generated/**`** chỉ sinh lại bằng `make gen-types` từ api của worktree mình,
  không sửa tay.
- Chạm xác thực, `core/security.py`, `core/auth.py`, `auth.ts`, `middleware.ts`, `actions.ts`:
  chạy subagent `security-auditor` sau `code-reviewer` (CLAUDE.md).
- Rebase sớm (skill `sync-main`) khi biết task khác vừa merge thay đổi ở các file này.

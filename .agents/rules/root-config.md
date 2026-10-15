---
# Claude Code đọc `paths`, Kiro/Antigravity đọc `fileMatchPattern` - giữ cả hai.
paths:
  - "Makefile"
  - "docker-compose*.yml"
  - ".env.example"
  - ".gitignore"
  - "CLAUDE.md"
  - "AGENTS.md"
  - "TASKS.md"
  - ".claude/settings.json"
  - ".claude/agents/**"
  - ".agents/**"
  - "apps/core/pyproject.toml"
  - "apps/core/uv.lock"
  - "apps/web/package.json"
  - "apps/web/package-lock.json"
  - ".github/**"
  - "infra/**"
inclusion: fileMatch
fileMatchPattern: ["Makefile", "docker-compose*.yml", ".env.example", ".gitignore", "CLAUDE.md", "AGENTS.md", "TASKS.md", ".claude/settings.json", ".claude/agents/**/*", ".agents/**/*", "apps/core/pyproject.toml", "apps/core/uv.lock", "apps/web/package.json", "apps/web/package-lock.json", ".github/**/*", "infra/**/*"]
---

# Vùng nhạy cảm: cấu hình gốc và file dùng chung (multi-session)

Nạp khi mở file cấu hình mà mọi task đều phụ thuộc. Hai session cùng sửa các file này gần như
chắc chắn conflict, và sửa sai thì hỏng stack của mọi worktree.

- **Chỉ sửa khi phạm vi task trong `TASKS.md` ghi rõ file này.** Không có thì
  `scripts/agents/task-board.sh coord T<N> "<cần đổi gì, vì sao>"` và dừng lại hỏi User.
- **`TASKS.md`: không sửa tay trong nhánh task.** Chỉ đổi qua `scripts/agents/task-board.sh`
  (ghi thẳng vào nhánh `main`).
- **Lockfile** (`uv.lock`, `package-lock.json`) chỉ sinh lại bằng công cụ (`make lock`,
  `npm install`), không sửa tay, và chỉ trong task có nhiệm vụ đổi dependency.
- **`CLAUDE.md`, `AGENTS.md`, `.agents/**`, `.claude/**`**: chỉ session điều phối sửa, và chỉ bổ
  sung, không xoá luật cũ khi User chưa đồng ý.
- **Docker/Makefile/CI**: theo AGENTS.md 3.9, comment từng dòng quyết định và cập nhật tài liệu
  tương ứng (`docs/DOCKER_ARCHITECTURE.md`, `docs/agents/WORKFLOW.md`...).
- Đừng gỡ cơ chế worktree trong `Makefile` (khối `ifneq (,$(wildcard .env.worktree))`) hay
  `docker-compose.worktree.yml`: thiếu chúng thì `make up` trong worktree sẽ chiếm container
  của stack chính.

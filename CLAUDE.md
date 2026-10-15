# Claude Code - điểm vào

@AGENTS.md

<!--
  CHỈ import AGENTS.md. Mọi `@đường-dẫn` trong file này đều được Claude Code
  nạp NGAY khi mở session (kể cả khi nằm giữa câu "xem @x khi cần"), nên
  tài liệu sâu bên dưới cố tình viết KHÔNG có ký tự @ để giữ đúng tinh thần
  lazy-load. Rules theo đường dẫn nằm ở .claude/rules (symlink tới .agents/rules),
  skills ở .claude/skills (symlink tới .agents/skills).
-->

## Đọc khi cần (không nạp sẵn)
- Trạng thái hiện tại: `docs/AI_HANDOFF_STATE.md` - đọc khi bắt đầu task lớn.
- Bức tranh tổng: `docs/project-review.md`.
- Thiết kế DB / RAG / Vault: `docs/TARGET_ARCHITECTURE.md`.
- Hạ tầng, Docker: `docs/DOCKER_ARCHITECTURE.md`.
- Hồ sơ các hệ thống (VM, cổng, cấu hình, việc còn thiếu): `docs/SYSTEMS_INVENTORY.md`.
- Proxmox, VM staging/prod, **cách SSH vào server**: `docs/PROXMOX_OPERATIONS.md` (mục 1b) và `docs/PROXMOX_ACCESS.md` (thêm khóa, quản lý), dựng VM/deploy: `docs/PROXMOX_DEPLOY.md`.

## Mô hình multi-agent (Claude Code)
Session chính là **orchestrator**: hiểu yêu cầu, chia việc, gọi subagent, tổng hợp,
commit khi User cho phép. Subagent ở `.claude/agents/`:

| Việc | Subagent | Ghi chú |
|---|---|---|
| Epic chạm ≥ 2 tầng | `architect` | Ra `docs/specs/<epic>.md`, chờ User chốt |
| Code backend | `backend-dev` | Chỉ `apps/core/`, theo spec |
| Code web | `frontend-dev` | Chỉ `apps/web/`, theo spec |
| Có migration / đổi model | `db-reviewer` | Chỉ đọc |
| Trước commit/merge | `code-reviewer` | Chỉ đọc, context sạch - thay cho tự QC |
| Chạm Vault/RBAC/auth/Server Action | `security-auditor` | Chỉ đọc, chạy thêm sau `code-reviewer` |
| Hỏi tiến độ (đang làm/đã xong/treo) | `work-tracker` | Chỉ đọc, theo skill `work-tracking`, xem `docs/WORK_TRACKING.md` |
| Tìm kiếm rộng trong repo | `Explore` (built-in) | Không đọc hết file vào session chính |

Việc nhỏ (sửa 1-2 file, một tầng) → orchestrator tự làm, không spawn subagent.
Chạy song song backend-dev và frontend-dev chỉ khi spec đã tách Ownership rõ;
khi chạy song song, dùng git worktree riêng cho từng agent.

## Quy tắc đa session (bắt buộc)
Nhiều session Claude Code chạy song song, mỗi session một worktree. Chi tiết: `docs/agents/WORKFLOW.md`.

| Lệnh | Việc |
|---|---|
| `make up` / `make up-backend` | Dựng stack (cả web / chỉ postgres+redis+api) |
| `make lint` · `make test` · `make smoke` | Ruff+tsc · pytest trên DB `_test` · E2E qua API |
| `make migration m="..."` → `make migrate` | Sinh / áp migration |
| `scripts/agents/task-board.sh show` | Bảng TASKS.md trên `main` |
| `scripts/agents/list-worktrees.sh` | Worktree, DB, cổng, trạng thái |

Vùng sở hữu: `apps/core/` (backend) · `apps/web/` (web) · `apps/core/migrations/` + model
(dùng chung, `.agents/rules/migrations.md`) · cấu hình gốc, lockfile, `.agents/`, `.claude/`
(`.agents/rules/root-config.md`) · lõi dùng chung `core/`, `db/`, `lib/types.ts`, `lib/api.ts`
(`.agents/rules/core-shared.md`).

- **Không code trên `main`.** Mỗi task = 1 nhánh `<type>/T<N>-<slug>` + 1 worktree `../<repo>-T<N>` (skill `start-task`).
- **Claim trước khi code** qua `scripts/agents/task-board.sh claim`. Không làm task đã có người claim.
  Không sửa `TASKS.md` bằng tay: bảng sống trên nhánh `main`, chỉ đổi qua `task-board.sh`.
- **Chỉ sửa file trong phạm vi task.** Cần sửa ngoài phạm vi: `task-board.sh coord T<N> "..."` rồi dừng, hỏi User.
- **Không sửa file dùng chung** (lockfile, config gốc, compose, Makefile, migration/schema, `CLAUDE.md`) trừ khi phạm vi task ghi rõ.
- **Migration:** mỗi migration một file mới, tên có timestamp (`make migration`). Không sửa migration đã merge.
  Chỉ `make migrate` trong worktree của mình (thư mục có `.env.worktree`).
- **DB và cổng riêng:** worktree dùng compose project `builder-t<N>`, DB `builder_ai_t<N>`, cổng theo
  `.env.worktree` (Makefile tự nạp). Không trỏ vào DB của stack chính hay VM dev.
- **Commit nhỏ, Conventional Commits** (skill `git-commit`). Rebase lên `origin/main` trước khi mở PR (skill `finish-task`).
- **Kết thúc session phải viết handoff** (skill `handoff`, file `docs/agents/handoffs/YYYY-MM-DD-T<N>.md`).
- Skill khác của quy trình: `sync-main` (rebase + migrate + test), `cleanup-task` (sau merge).

## Chỉ orchestrator làm (subagent không làm)
- Cập nhật `docs/AI_HANDOFF_STATE.md`, đăng ký docs mới vào `apps/web/lib/docs.ts`.
- Không ghi AI log tay (đã gỡ, xem mục 3.4 AGENTS.md); ghi vết do hook tự động.
- `git commit` theo skill `git-commit`. `git push` luôn hỏi User trước (hook chặn sẵn).

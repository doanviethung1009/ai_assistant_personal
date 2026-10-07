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
| Tìm kiếm rộng trong repo | `Explore` (built-in) | Không đọc hết file vào session chính |

Việc nhỏ (sửa 1-2 file, một tầng) → orchestrator tự làm, không spawn subagent.
Chạy song song backend-dev và frontend-dev chỉ khi spec đã tách Ownership rõ;
khi chạy song song, dùng git worktree riêng cho từng agent.

## Chỉ orchestrator làm (subagent không làm)
- Cập nhật `docs/AI_HANDOFF_STATE.md`, đăng ký docs mới vào `apps/web/lib/docs.ts`.
- Ghi AI log (Rule 3.4) một lần ở cuối task, không ghi theo từng subagent.
- `git commit` theo skill `git-commit`. `git push` luôn hỏi User trước (hook chặn sẵn).

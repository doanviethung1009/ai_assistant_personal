# Lưu trữ Dữ liệu AI: Trace ngoài repo vs. Entity trong Database

> Cập nhật: 2026-10-08. Luồng "AI log viết tay" (`docs/ai_logs.md`, `data/ai-logs.json`, bảng `ai_logs`)
> **đã gỡ**; bản sao log cũ nằm ở `~/.claude/trace/ai_assistant_personal/legacy-ai-logs/`.

Dữ liệu sinh ra từ AI có hai luồng khác nhau về mục đích. Phân biệt rõ để không lẫn:

## 1. Luồng Trace: ghi vết phiên làm việc của agent

- **Nơi lưu:** ngoài repo, `~/.claude/trace/ai_assistant_personal/` (không bao giờ commit).
- **Ai ghi:** hook của Claude Code (`.claude/hooks/trace-hook.py`), tự động, không phụ thuộc agent nhớ ghi.
  Mặc định TẮT, bật bằng `CLAUDE_TRACE_ENABLED=1`.
- **Nội dung:** mỗi lượt (prompt, `git diff --stat`, lời agent tự khai) và transcript đầy đủ đã lọc secret.
- **Mục đích:** truy vết "agent đã làm gì", đối chiếu lời khai với diff thật, và (sau này) làm dữ liệu eval/training.
- Chi tiết: `docs/CLAUDE_TRACE_HOOKS.md`; hướng dùng cho training: `docs/LLM_TRAINING_DATA_PLAN.md`.

## 2. Luồng Entity: dữ liệu nghiệp vụ của ứng dụng

- **Ví dụ:** Task, Project, Note.
- **Nơi lưu:** PostgreSQL qua API (`DATA_SOURCE=api`), hoặc file JSON cục bộ `data/builder-data.json` (`DATA_SOURCE=file`).
- **Mục đích:** người dùng thao tác hằng ngày (lọc, sửa, xoá mềm, phân trang), nên cần ràng buộc, index, migration.
- Chi tiết: `docs/TARGET_ARCHITECTURE.md`, `docs/JSON_STORAGE.md`, `docs/DATA_MIGRATION_TO_POSTGRES.md`.

## Quy tắc chọn

Dữ liệu cho **người dùng thao tác** → Entity. Dữ liệu **vết của agent** (append-only, lớn, nhạy cảm) → Trace ngoài repo,
không đưa vào Postgres hay `data/`.

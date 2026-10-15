---
name: handoff
description: Viết file bàn giao cuối session cho một task (đã làm gì, quyết định và lý do, file đã sửa, việc còn dở, rủi ro, lệnh để tiếp tục) vào docs/agents/handoffs/YYYY-MM-DD-T<N>.md. Dùng KHI kết thúc hoặc tạm dừng một session làm task, khi User nói "handoff", "bàn giao", "ghi lại để mai làm tiếp", "sắp hết context", và luôn chạy ở cuối skill finish-task.
---

# Viết handoff cho session

Mục đích: session sau (người hoặc AI, không có context hiện tại) đọc một file là tiếp tục được. Viết bằng bằng chứng (lệnh, đường dẫn, kết quả test), không bằng trí nhớ.

## Bước 1 - Thu thập
```bash
grep -E '^(TASK_ID|TASK_BRANCH)=' .env.worktree 2>/dev/null
git branch --show-current
git status --short
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
scripts/agents/task-board.sh show | grep "| T<N> |"
```
Không ở worktree task (không có `.env.worktree`): hỏi User handoff này thuộc task nào. Việc của session điều phối thì dùng ID `coord`.

## Bước 2 - Tạo file
- Đường dẫn: `docs/agents/handoffs/$(date +%F)-T<N>.md`. File đã có (session trước cùng ngày): tạo `-2`, `-3`, không ghi đè.
- Chép khung từ `docs/agents/handoffs/_TEMPLATE.md`, điền **mọi** mục:
  - **Đã làm gì**: kết quả, không kể lể quá trình.
  - **Quyết định và lý do**: kèm phương án đã bỏ. Quyết định ảnh hưởng task khác thì thêm `scripts/agents/task-board.sh decide "..."`.
  - **File đã sửa**: dán `git diff --stat origin/main...HEAD`, cộng file chưa commit nếu có.
  - **Việc còn dở**: checklist cụ thể, việc nào làm được ngay ghi trước.
  - **Rủi ro**: migration chưa chạy, test thiếu, lỗi chưa rõ nguyên nhân, chỗ chạm phạm vi task khác.
  - **Lệnh để tiếp tục**: lệnh copy-chạy được, gồm `cd` vào worktree.
- Không chép secret, token, nội dung `.env` vào handoff.

## Bước 3 - Lưu
- Commit vào nhánh task: `docs(handoff): T<N> <tóm tắt>` (theo skill `git-commit`). Không commit lên `main`.
- Cập nhật ghi chú trên bảng nếu trạng thái đổi:
  `scripts/agents/task-board.sh status T<N> <trạng thái> "handoff <ngày>"`.
- `docs/AI_HANDOFF_STATE.md` (ảnh chụp toàn dự án) chỉ session điều phối cập nhật, khi task merge.

## Bước 4 - Báo User
Đường dẫn file handoff và 1-3 dòng: việc còn dở quan trọng nhất, rủi ro lớn nhất.

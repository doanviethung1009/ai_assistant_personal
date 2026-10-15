---
name: cleanup-task
description: Dọn một task sau khi PR đã merge - xoá Docker riêng (hỏi trước khi xoá DB), xoá worktree, xoá nhánh local, đồng bộ main local, chuyển TASKS.md sang done. Dùng KHI User bảo "dọn task T12", "PR merge rồi", "cleanup", "xoá worktree". Chạy từ checkout chính hoặc worktree khác, KHÔNG chạy từ trong worktree đang bị dọn.
---

# Dọn task sau khi merge

## Bước 1 - Xác nhận đã merge
```bash
scripts/agents/task-board.sh show | grep "| T<N> |"
scripts/agents/list-worktrees.sh
gh pr view <branch> --json state,url -q '.state + " " + .url'
```
- `MERGED`: tiếp tục.
- Chưa merge: **dừng**, hỏi User có thật muốn bỏ task không. Bỏ task thì chuyển trạng thái về `todo` (trả lại cho người khác) thay vì `done`.

## Bước 2 - Ra khỏi worktree sắp xoá
Session đang đứng trong `../<repo>-T<N>` thì không dọn được. Chạy từ checkout chính (đường dẫn worktree đầu tiên trong `git worktree list`).

## Bước 3 - Xoá
```bash
scripts/agents/remove-worktree.sh T<N>
```
Script sẽ:
1. Từ chối nếu worktree còn thay đổi chưa commit. **Không** tự thêm `--force`: báo User, để User quyết định.
2. Liệt kê container/volume của `builder-t<N>` và **hỏi xác nhận** trước khi xoá DB `builder_ai_t<N>`. Session AI không trả lời thay User: chạy lệnh để User thấy câu hỏi, hoặc hỏi User trước rồi mới thêm `--yes`.
3. Xoá worktree, xoá nhánh local nếu đã merge (chưa merge thì giữ và báo).

Script chỉ đụng tài nguyên có prefix `builder-t<N>` / `builder_ai_t<N>`.

## Bước 4 - Cập nhật bảng và main local
```bash
scripts/agents/task-board.sh sync
scripts/agents/task-board.sh status T<N> done "PR #<số> merged $(date +%F)"
```
`sync` đưa `main` local theo `origin/main` và giữ commit bảng ở trên cùng. Push `main` để lưu bảng lên GitHub là tuỳ User (luôn hỏi).

## Bước 5 - Bàn giao chung
Session điều phối cập nhật `docs/AI_HANDOFF_STATE.md` nếu task có ý nghĩa với trạng thái dự án (theo skill `work-tracking`). Báo User: đã xoá gì, nhánh nào còn giữ, task còn mở trong bảng.

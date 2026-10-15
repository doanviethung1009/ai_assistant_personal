# Handoff T<N> - <tiêu đề ngắn> (YYYY-MM-DD)

> Lưu thành `docs/agents/handoffs/YYYY-MM-DD-T<N>.md`. Nhiều session cùng ngày cho một task thì
> thêm hậu tố `-2`, `-3`. Viết cho người (hoặc session) chưa biết gì về việc này.

- **Task:** T<N> - <mô tả trong TASKS.md>
- **Nhánh / worktree:** `<type>/T<N>-<slug>` / `../<repo>-T<N>`
- **Trạng thái trong TASKS.md:** in-progress | review | ...
- **PR:** <link hoặc "chưa mở">

## Đã làm gì

- ...

## Quyết định và lý do

| Quyết định | Lý do | Phương án đã bỏ |
|---|---|---|
| ... | ... | ... |

## File đã sửa

<!-- dán kết quả: git diff --stat origin/main...HEAD -->

## Việc còn dở

- [ ] ...

## Rủi ro và điều cần kiểm

- ... (migration chưa chạy trên DB nào, test chưa có, chỗ đụng phạm vi task khác...)

## Lệnh để tiếp tục

```bash
cd ../<repo>-T<N>
make up-backend && make migrate   # dựng lại stack riêng nếu đã tắt
git log --oneline origin/main..HEAD
# bước tiếp theo cụ thể...
```

---
name: sync-main
description: Đưa nhánh task đang làm lên mới nhất so với origin/main - fetch, rebase, chạy lại migration trên DB riêng của worktree, chạy test, báo kết quả. Dùng KHI User bảo "sync main", "rebase", "cập nhật theo main", khi biết task khác vừa merge thay đổi liên quan (migration, types, file dùng chung), hoặc trước khi chạy finish-task lâu ngày sau khi tạo nhánh.
---

# Đồng bộ nhánh task với origin/main

Chạy trong worktree của task (có `.env.worktree`). Không dùng trên `main`.

## Bước 1 - Kiểm sạch
```bash
test -f .env.worktree || echo "KHÔNG ở worktree task - dừng"
git status --short
```
Có thay đổi chưa commit: commit (skill `git-commit`) hoặc hỏi User. Không dùng `git stash` trần (stack stash dùng chung giữa các worktree).

## Bước 2 - Fetch và xem sẽ nhận gì
```bash
git fetch origin main
git log --oneline HEAD..origin/main
git diff --stat HEAD...origin/main
```
Ghi lại: có migration mới (`apps/core/migrations/versions/`), có đổi dependency (`uv.lock`, `package-lock.json`), có đổi file trong phạm vi task không.

## Bước 3 - Rebase
```bash
git rebase origin/main
```
- Conflict trong phạm vi task: sửa, `git add`, `git rebase --continue`.
- Conflict ngoài phạm vi: `git rebase --abort`, `scripts/agents/task-board.sh coord T<N> "..."`, dừng và hỏi User.
- Luôn rebase lên `origin/main`, không lên `main` local.

## Bước 4 - Cập nhật stack riêng
```bash
make up-backend               # đổi uv.lock/Dockerfile thì: make build && make up-backend
make history                  # phải có đúng một head
make migrate                  # chỉ chạm DB builder_ai_t<N> của worktree
```
Alembic báo nhiều head (task mình và main cùng thêm migration): sửa `down_revision` migration của task mình trỏ vào head mới của main, chạy lại `make migrate`. Migration của mình đã áp vào DB riêng theo thứ tự cũ thì `make downgrade` về trước nó rồi `make migrate` lại. Không `alembic merge` khi chưa hỏi User.

## Bước 5 - Test
```bash
make lint
make test
make smoke        # nếu task đổi apps/core
```

## Bước 6 - Báo kết quả
Ngắn gọn: số commit nhận từ main, conflict đã xử lý (file nào, chọn thế nào), migration đã chạy, kết quả lint/test (dán lỗi nếu đỏ). Nhánh đã push trước đó thì nhắc: lần push sau cần `--force-with-lease`, phải hỏi User.

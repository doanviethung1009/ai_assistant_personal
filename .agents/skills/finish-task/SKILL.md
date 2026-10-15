---
name: finish-task
description: Đóng gói task đang làm trong worktree để mở Pull Request - kiểm phạm vi, lint, test, rebase lên origin/main, push (hỏi User), mở PR bằng gh, chuyển TASKS.md sang review, viết handoff. Dùng KHI User bảo "xong task", "mở PR", "finish task", "đẩy lên review" trong worktree của một task T<N>. Không dùng trên checkout chính hay nhánh main.
---

# Hoàn tất task và mở PR

Chạy trong worktree của task (thư mục có `.env.worktree`). Làm từng bước; bước nào đỏ thì dừng, sửa, chạy lại từ bước đó.

## Bước 0 - Xác định task
```bash
test -f .env.worktree || echo "KHÔNG ở worktree task - dừng"
grep -E '^(TASK_ID|TASK_BRANCH)=' .env.worktree
git branch --show-current
git status --short
```
Còn thay đổi chưa commit: commit theo skill `git-commit` (commit nhỏ, đúng type), hoặc hỏi User.

## Bước 1 - Kiểm phạm vi
```bash
scripts/agents/task-board.sh show | grep "| T<N> |"
git fetch origin main
git diff --stat origin/main...HEAD
```
- Mọi file phải nằm trong cột "Phạm vi". File ngoài phạm vi: dừng, `task-board.sh coord` và hỏi User.
- Nhánh có đổi `TASKS.md`: gỡ khỏi nhánh (bảng chỉ đổi qua `task-board.sh`).

## Bước 2 - Lint và test trên stack riêng
```bash
make up-backend          # nếu stack đã tắt
make lint
make test
make smoke               # khi có đổi apps/core
```
Đổi `apps/web`: thêm `cd apps/web && npx vitest run` nếu có test liên quan.

## Bước 3 - Rebase lên origin/main
```bash
git rebase origin/main
```
- Conflict ở file trong phạm vi: sửa, `git add`, `git rebase --continue`.
- Conflict ở file ngoài phạm vi: `git rebase --abort`, ghi `task-board.sh coord`, hỏi User. Không tự chọn phía.
- Có migration: `make history` phải đúng một head; xong `make migrate` rồi chạy lại Bước 2.

Rebase **lên `origin/main`**, không lên `main` local (main local mang commit bảng chưa push).

## Bước 4 - Review độc lập
Gọi subagent `code-reviewer` trên diff `origin/main...HEAD` (thêm `db-reviewer` nếu có migration, `security-auditor` nếu chạm auth/Vault/RBAC/Server Action). Sửa lỗi nghiêm trọng trước khi push.

## Bước 5 - Push và mở PR (HỎI USER TRƯỚC)
Hỏi User: "Push nhánh `<branch>` và mở PR?". Chỉ làm khi User đồng ý.
```bash
git push -u origin HEAD        # sau rebase nhánh đã push trước: git push --force-with-lease (hỏi User, hook có thể chặn)
gh pr create --base main --title "<type>(<scope>): <mô tả> [T<N>]" --body-file <file body>
```
Body PR gồm: Task T<N> và mô tả, tóm tắt thay đổi, cách test, rủi ro/migration, link handoff, và dòng attribution theo quy định của session.

## Bước 6 - Cập nhật bảng và handoff
```bash
scripts/agents/task-board.sh status T<N> review "PR #<số>"
```
Chạy skill `handoff` (ghi link PR). Commit file handoff vào nhánh task và push (cũng hỏi User).

Báo User: link PR, kết quả lint/test, rủi ro còn lại. Sau khi merge thì dùng skill `cleanup-task`.

---
name: start-task
description: Nhận một task trong TASKS.md và dựng môi trường làm việc riêng cho nó (nhánh + git worktree + Docker/DB/cổng riêng). Đang ở linked worktree (vd agent view tạo trong .claude/worktrees/) thì KHÔNG tạo worktree mới, dùng luôn worktree hiện tại. Dùng KHI User bảo "bắt đầu task T12", "nhận task", "làm task mới", "tạo worktree cho ...", hoặc trước khi code bất cứ thứ gì chưa có task đã claim. Không dùng khi worktree hiện tại đã thuộc một task đã claim (khi đó cứ code tiếp).
---

# Bắt đầu một task (multi-session)

Quy trình đầy đủ: `docs/agents/WORKFLOW.md`. Làm từng bước, không nhảy cóc.

## Bước 0 - Xác định chế độ
```bash
[ "$(git rev-parse --path-format=absolute --git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ] && echo HERE || echo NEW
```
- `HERE` (đang ở linked worktree, vd do agent view tạo ở `.claude/worktrees/`): **không tạo worktree mới**. Chỉ claim task rồi dựng Docker/DB/cổng riêng ngay tại thư mục này. Đi theo các bước dưới, chỗ nào khác sẽ ghi "chế độ HERE".
- `NEW` (checkout chính): tạo worktree mới như mô tả.
- Worktree hiện tại đã có `.env.worktree` của task khác: **dừng**, báo User.

## Bước 1 - Đọc bảng trên main
```bash
scripts/agents/task-board.sh show
scripts/agents/list-worktrees.sh
```
Bản TASKS.md trong thư mục hiện tại có thể cũ; chỉ tin bản `show`.

## Bước 2 - Chọn task
- User đã nêu ID: kiểm trạng thái là `todo`. Khác `todo` thì **dừng**, báo ai đang giữ (cột Branch/Worktree), không làm.
- Task chưa có trong bảng: hỏi User mô tả và **phạm vi file/module** (bắt buộc, cụ thể tới thư mục), rồi:
  ```bash
  ID=$(scripts/agents/task-board.sh next-id)
  scripts/agents/task-board.sh add "$ID" "<mô tả>" "<phạm vi>"
  ```
- Phạm vi chạm file dùng chung (migration, lockfile, Makefile, `lib/types.ts`...) thì nói rõ cho User biết trước khi claim.

## Bước 3 - Chọn type và slug
- type theo Conventional Commits: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`, `build`, `ci`.
- slug: 2-4 từ tiếng Anh, chữ thường, nối `-` (vd `note-tags`).
- Nhánh sẽ là `<type>/T<N>-<slug>`. Chế độ NEW: worktree `../<repo>-T<N>` (repo = tên thư mục checkout chính). Chế độ HERE: worktree là thư mục hiện tại (`git rev-parse --show-toplevel`); nhánh hiện tại (tên do agent view đặt, vd `worktree-xxx`) sẽ được đổi tên thành nhánh trên.

## Bước 4 - Claim (trước khi tạo gì)
```bash
scripts/agents/task-board.sh claim T<N> <type>/T<N>-<slug> ../<repo>-T<N>      # chế độ NEW
scripts/agents/task-board.sh claim T<N> <type>/T<N>-<slug> "$(git rev-parse --show-toplevel)"  # chế độ HERE
```
Lệnh báo task đã có người nhận thì **dừng**, không thử lại, không sửa tay bảng.
Báo `main` đang checkout ở worktree nào đó: báo User, đừng tự đổi nhánh của worktree người khác.

## Bước 5 - Tạo worktree (NEW) hoặc dựng môi trường tại chỗ (HERE)
```bash
scripts/agents/new-worktree.sh T<N> <slug> --type <type>
```
Script tự nhận biết chế độ: ở linked worktree thì chạy `--here` (đổi tên nhánh hiện tại sang `<type>/T<N>-<slug>`, không `git worktree add`); ở checkout chính thì tạo worktree mới. Ép tay bằng `--here` / `--new`. Ở chế độ NEW script tạo nhánh từ `origin/main`, sinh `.env` + `.env.worktree`, dựng postgres/redis/api của riêng task và chạy migration (nếu Docker chạy). Lần đầu build image có thể mất vài phút. Lỗi thì đọc thông báo, sửa nguyên nhân rồi chạy lại (script chạy lại an toàn).

Máy không có Docker (script báo "Docker không chạy"): **không phải lỗi**. Worktree và `.env.worktree` vẫn
đủ để code. Kiểm chứng backend sau này dùng `make devvm-test` / `make devvm-smoke` (chạy trên VM dev),
web xem nhanh bằng `make devvm-web`. Chi tiết: `docs/agents/WORKFLOW.md` mục 9.

## Bước 6 - Báo cho User
In nguyên khối tóm tắt cuối của script (thư mục, nhánh, compose project, DB, cổng).
- Chế độ NEW, nhắc: mở session Claude Code **mới** trong worktree: `cd <đường dẫn> && claude`. Session hiện tại không code task này.
- Chế độ HERE: không cần mở session mới, code tiếp ngay trong session/worktree này.

Khi session mới bắt đầu code: `scripts/agents/task-board.sh status T<N> in-progress`.

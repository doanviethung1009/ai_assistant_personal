---
name: git-commit
description: Quy trình commit và push cho repo này — Conventional Commits, checklist trước khi commit, cách chia nhiều commit, hook kiểm tra message, và sinh changelog. Dùng khi chuẩn bị commit, viết commit message, hoặc được yêu cầu "commit" / "update git" / "push lên git".
---

# Quy trình commit

Mục đích: để sáu tháng sau đọc lại `git log` vẫn hiểu được **tại sao**, không
chỉ **cái gì**. Quy ước viết comment trong code nằm ở steering
`comment-style` (tự nạp khi sửa file code) — không lặp ở đây.

## Định dạng: Conventional Commits

```
<type>(<phạm vi tuỳ chọn>): <mô tả ngắn, thì hiện tại, không viết hoa đầu>

<nội dung chi tiết tuỳ chọn, giải thích WHY>
```

| Type | Dùng khi |
|---|---|
| `feat` | Thêm tính năng hoặc hành vi người dùng thấy được |
| `fix` | Sửa lỗi |
| `docs` | Chỉ sửa tài liệu (`docs/`, `.kiro/`, README, comment) |
| `refactor` | Đổi cấu trúc code, không đổi hành vi |
| `perf` | Cải thiện hiệu năng, không đổi hành vi quan sát được |
| `test` | Thêm hoặc sửa test, kể cả `scripts/smoke-test.sh` |
| `build` | Đổi dependency, Dockerfile, cấu hình build |
| `ci` | Đổi pipeline, hook, script vận hành git |
| `chore` | Dọn dẹp không thuộc nhóm trên |

Ví dụ thật khớp lịch sử hiện có của repo:

```
feat(core): thêm soft delete cho task và note
fix(web): sửa lệch timezone ở completed_last_7_days
docs: bổ sung quy ước comment và quy trình commit
refactor(core): chuyển _enum_col thành enum_column dùng chung
chore(git): dựng nhánh uat và prod từ main
```

Phạm vi (`scope`) gợi ý dùng: `core`, `web`, `infra`, `docs`, `git`. Bỏ qua
nếu thay đổi trải khắp nhiều phần.

**Breaking change** — thêm `!` sau type/scope và dòng `BREAKING CHANGE:` ở
phần nội dung:

```
feat(core)!: đổi response của /api/v1/tasks/stats

BREAKING CHANGE: field `trash_total` đổi tên thành `deleted_total`.
```

## Trước khi commit

1. **Chạy kiểm tra tương ứng với phần đã sửa.**
   - Sửa `apps/core/`: `make lint` (ruff + tsc), rồi `make smoke` nếu có đổi
     hành vi API.
   - Sửa `apps/web/`: `cd apps/web && npx tsc --noEmit`.
   - Sửa migration: `make migrate` chạy sạch trên DB thử.
2. **Soát `git status` và `git diff` trước khi stage.** Không `git add -A`
   theo phản xạ — nêu rõ từng file trong lần stage, để không commit nhầm
   file tạm hay `.env` lọt lưới `.gitignore`.
3. **Một commit, một thay đổi logic.** Đổi schema và sửa UI tương ứng đi
   cùng một commit nếu chúng không chạy được riêng lẻ; việc không liên quan
   tách commit khác (ví dụ: thêm steering mới và sửa logic nghiệp vụ là hai
   commit riêng, dù làm trong cùng một phiên).

## Thứ tự lệnh thường dùng

```bash
git status --short
git diff -- <file đã sửa>
git add <file 1> <file 2>
git commit -m "feat(web): thêm bộ lọc theo tag ở trang Sổ tay"
git push origin main
```

Quy trình thăng cấp lên `uat`/`prod` sau khi đã commit vào `main` nằm ở
[docs/git-workflow.md](../../../docs/git-workflow.md) — không lặp ở đây.
Thứ tự lệnh deploy thực tế theo từng tình huống nằm ở
[docs/deploy-runbook.md](../../../docs/deploy-runbook.md).

## Hook kiểm tra message

`scripts/install-hooks.sh` cài một `commit-msg` hook cục bộ, kiểm tra message
đúng định dạng Conventional Commits trước khi tạo commit. Cài một lần:

```bash
bash scripts/install-hooks.sh
```

Hook này **không** đụng tới `core.hookspath` của git-secrets (chính sách
quét bí mật cấp công ty) — nó chạy nối tiếp sau khi git-secrets quét xong,
không thay thế. Chi tiết cơ chế nằm trong comment đầu file
`scripts/git-hooks/commit-msg`.

## Changelog

```bash
make changelog
```

Sinh `CHANGELOG.md` từ `git log` theo Conventional Commits, gom theo nhóm
`feat`/`fix`/`docs`/... Chạy trước mỗi lần `make promote-prod` để changelog
luôn khớp với thứ sắp go-live. Xem chi tiết đầu file `scripts/changelog.sh`.

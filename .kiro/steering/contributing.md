# Quy ước comment và quy trình commit

Hai việc tách biệt nhưng cùng mục đích: để sáu tháng sau đọc lại code hoặc
`git log` vẫn hiểu được **tại sao**, không chỉ **cái gì**.

## Quy ước comment

Nguyên tắc chung: comment giải thích **WHY**, không diễn lại **WHAT**. Code
đã nói nó làm gì; comment chỉ cần khi có quyết định, đánh đổi, hoặc cạm bẫy
mà đọc code không suy ra được.

### Banner chia section trong file dài

Dùng khi một file có nhiều nhóm hàm rõ rệt (đọc / ghi / xoá, hoặc các bước
tuần tự của một script).

```python
# ═══════════════════════════════════════════════════════════════════════
#  Đọc
# ═══════════════════════════════════════════════════════════════════════
```

Dòng kẻ dài 73 ký tự `═` (U+2550), căn đều hai bên cho các banner trong
cùng file. Xem ví dụ thật ở `apps/core/app/services/task_service.py` (nhóm
Đọc/Ghi) và `scripts/release.sh` (header mô tả cách dùng).

Nhóm nhỏ hơn trong cùng section dùng gạch ngắn:

```python
# ── Thùng rác ───────────────────────────────────────────────────
```

### Docstring giải thích lý do tồn tại, không tả lại chữ ký hàm

Sai — chỉ lặp lại những gì type hint đã nói:

```python
def restore_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    """Nhận session và task_id, trả về Task."""
```

Đúng — nói vì sao hàm này cần tồn tại và cạm bẫy nó tránh:

```python
def restore_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    """Lấy task ra khỏi thùng rác.

    Trước khi phục hồi phải chắc chắn không đụng partial unique index.
    Tình huống thật: xoá một issue Jira, sync tạo lại, rồi bấm phục hồi.
    """
```

Ví dụ thật: docstring của `class Note` trong `apps/core/app/models/note.py`
giải thích Note khác Task ở điểm nào (không có vòng đời, không có hạn) —
đó là thông tin không thể suy ra từ việc đọc danh sách field.

### Cảnh báo an toàn: viết hoa từ khoá chính, bọc bằng banner dày

Khi một quyết định có thể gây hậu quả nếu người sau hiểu sai, nói thẳng và
làm nó khó lướt qua. Xem `apps/core/app/models/note.py`:

```python
# ══════════════════════════════════════════════════════════════════════
#  `content` LÀ DỮ LIỆU, KHÔNG PHẢI CODE.
#
#  Hệ thống không bao giờ thực thi nội dung note, không truyền nó vào
#  shell, không nối vào câu SQL. Người dùng tự copy và tự chịu trách
#  nhiệm khi dán vào terminal.
# ══════════════════════════════════════════════════════════════════════
```

Không lạm dụng — chỉ dùng cho thứ thật sự có thể gây sự cố (an toàn dữ
liệu, bảo mật, mất mát không hoàn tác), không dùng cho ghi chú thông
thường.

### Comment một dòng ngay trên field hoặc biến khi giá trị cần giải thích

```python
# Ghim để nổi lên đầu danh sách, dành cho thứ dùng hằng ngày.
is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

# Cờ do NGƯỜI DÙNG đặt, không phải máy suy ra. Web có gợi ý tự tích sẵn
# dựa trên vài từ khoá, nhưng người dùng luôn sửa được.
is_dangerous: Mapped[bool] = mapped_column(Boolean, default=False)
```

Đặt ngay trên dòng khai báo, không đặt cuối dòng — comment cuối dòng dễ bị
cắt khi diff hoặc khi dòng dài.

### Script shell: banner mở đầu nêu mục đích và cách dùng

Mọi file trong `scripts/` bắt đầu bằng banner nói file này làm gì, và nếu
có tham số thì liệt kê cách gọi. Xem `scripts/release.sh`:

```bash
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Thăng cấp code qua các nhánh môi trường:  main → uat → prod
#
#  Dùng:
#    bash scripts/release.sh status
#    bash scripts/release.sh uat
# ═══════════════════════════════════════════════════════════════════════
```

Người chạy `cat` hoặc `head` file đó phải hiểu được công dụng mà không cần
đọc hết logic.

### Markdown trong `docs/` và `.kiro/steering/`

Viết tiếng Việt, câu ngắn. Dùng bảng khi so sánh nhiều lựa chọn hoặc liệt kê
cấu hình. Dùng code block kèm chú thích chứ không dán lệnh trần không giải
thích. Mỗi quyết định kiến trúc nói rõ **vì sao chọn cách này** và tối thiểu
một **phương án đã bị loại** — xem cách `docs/git-workflow.md` so sánh với
Git Flow và trunk-based thuần.

## Quy trình commit

### Định dạng: Conventional Commits

```
<type>(<phạm vi tuỳ chọn>): <mô tả ngắn, thì hiện tại, không viết hoa đầu>

<nội dung chi tiết tuỳ chọn, giải thích WHY>
```

| Type | Dùng khi |
|---|---|
| `feat` | Thêm tính năng hoặc hành vi người dùng thấy được |
| `fix` | Sửa lỗi |
| `docs` | Chỉ sửa tài liệu (`docs/`, `.kiro/steering/`, README, comment) |
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

### Trước khi commit

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
   tách commit khác.

### Thứ tự lệnh thường dùng

```bash
git status --short
git diff -- <file đã sửa>
git add <file 1> <file 2>
git commit -m "feat(web): thêm bộ lọc theo tag ở trang Sổ tay"
git push origin main
```

Quy trình thăng cấp lên `uat`/`prod` sau khi đã commit vào `main` nằm ở
[docs/git-workflow.md](../../docs/git-workflow.md) — không lặp lại ở đây.

### Hook kiểm tra message

`scripts/install-hooks.sh` cài một `commit-msg` hook cục bộ, kiểm tra message
đúng định dạng Conventional Commits trước khi tạo commit. Cài một lần:

```bash
bash scripts/install-hooks.sh
```

Hook này **không** đụng tới `core.hookspath` của git-secrets (chính sách
quét bí mật cấp công ty) — nó chạy nối tiếp sau khi git-secrets quét xong,
không thay thế. Chi tiết cơ chế nằm trong comment đầu file
`scripts/git-hooks/commit-msg`.

### Changelog

```bash
make changelog
```

Sinh `CHANGELOG.md` từ `git log` theo Conventional Commits, gom theo nhóm
`feat`/`fix`/`docs`/... Chạy trước mỗi lần `make promote-prod` để changelog
luôn khớp với thứ sắp go-live. Xem chi tiết đầu file `scripts/changelog.sh`.

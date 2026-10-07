---
# Claude Code đọc `paths`, Kiro/Antigravity đọc `fileMatchPattern` - giữ cả hai.
paths:
  - "apps/**/*.py"
  - "apps/**/*.ts"
  - "apps/**/*.tsx"
  - "scripts/**/*.sh"
inclusion: fileMatch
fileMatchPattern: ["apps/**/*.py", "apps/**/*.ts", "apps/**/*.tsx", "scripts/**/*.sh"]
---

# Quy ước comment

Chỉ nạp khi đang sửa file code (Python, TypeScript, shell) — không nạp vào
mọi request để đỡ tốn token. Quy trình commit nằm ở skill `git-commit`, quy
trình thêm entity mới nằm ở skill `add-entity`, không lặp ở đây.

Nguyên tắc chung: comment giải thích **WHY**, không diễn lại **WHAT**. Code
đã nói nó làm gì; comment chỉ cần khi có quyết định, đánh đổi, hoặc cạm bẫy
mà đọc code không suy ra được.

## Banner chia section trong file dài

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

## Docstring giải thích lý do tồn tại, không tả lại chữ ký hàm

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

## Cảnh báo an toàn: viết hoa từ khoá chính, bọc bằng banner dày

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

## Comment một dòng ngay trên field hoặc biến khi giá trị cần giải thích

```python
# Ghim để nổi lên đầu danh sách, dành cho thứ dùng hằng ngày.
is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

# Cờ do NGƯỜI DÙNG đặt, không phải máy suy ra. Web có gợi ý tự tích sẵn
# dựa trên vài từ khoá, nhưng người dùng luôn sửa được.
is_dangerous: Mapped[bool] = mapped_column(Boolean, default=False)
```

Đặt ngay trên dòng khai báo, không đặt cuối dòng — comment cuối dòng dễ bị
cắt khi diff hoặc khi dòng dài.

## Script shell: banner mở đầu nêu mục đích và cách dùng

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

## AI Role: Tự động comment mô tả chức năng (Auto-commenting)

Mỗi khi AI tạo mới hoặc chỉnh sửa cấu trúc một hàm, class, hoặc UI component quan trọng, AI **PHẢI TỰ ĐỘNG** thêm docstring/comment mô tả chức năng mà không cần người dùng nhắc.

**Hướng dẫn dành riêng cho AI khi auto-comment:**
1. **Tập trung vào WHY và bối cảnh nghiệp vụ**: Trả lời câu hỏi "Hàm này sinh ra để giải quyết bài toán gì ở góc độ người dùng/nghiệp vụ?", tuyệt đối không dịch từng dòng code thành tiếng Việt (không lặp lại WHAT).
2. **Liệt kê rủi ro & cạm bẫy (nếu có)**: Nếu hàm có các edge-cases, side-effects (ví dụ: trigger event, thay đổi state global), hoặc giới hạn (ví dụ: chưa có rate limit), AI phải ghi chú rõ ràng để người sau đọc không bị dẫm mìn.
3. **Định dạng chuẩn**: 
   - Với **Python**: Luôn dùng Docstring (`"""..."""`) đặt ngay dưới dòng khai báo `def` hoặc `class`.
   - Với **TypeScript/Next.js**: Luôn dùng JSDoc (`/** ... */`) đặt ngay trên dòng định nghĩa hàm hoặc component.

## AI Role: Tự động cập nhật tài liệu khi thay đổi chức năng (Auto-documenting)

Mỗi khi AI **tạo mới, sửa đổi, hoặc xoá** một chức năng (feature, endpoint, page, component quan trọng), AI **PHẢI TỰ ĐỘNG** cập nhật tài liệu liên quan mà không cần người dùng nhắc.

**Hướng dẫn dành riêng cho AI khi auto-document:**

1. **Ghi nhận thay đổi vào `docs/`**: AI phải cập nhật hoặc bổ sung mô tả chức năng mới/đã sửa vào file tài liệu phù hợp trong thư mục `docs/` hoặc `.agents/rules/`.
2. **Nội dung cần ghi**:
   - Chức năng làm gì (mô tả ngắn gọn, 1–2 câu).
   - File chính liên quan (đường dẫn).
   - Các thay đổi đáng chú ý so với phiên bản trước (nếu là cập nhật).
   - Ngày cập nhật.
3. **Thêm vào Tab Tài liệu (Quan trọng)**: NẾU bạn tạo mới một file tài liệu markdown (ví dụ khi tạo chức năng lớn, thêm Agent rule mới, hoặc hướng dẫn task mới), bạn **BẮT BUỘC PHẢI** mở file `apps/web/lib/docs.ts` và thêm thông tin file đó vào mảng `DOCS` để file được hiển thị lên "Tab Tài Liệu" trên giao diện Web.
4. **Không tạo tài liệu rác**: Chỉ ghi khi thay đổi có ý nghĩa ở mức chức
   năng (thêm trang mới, thêm API endpoint, đổi luồng dữ liệu). Sửa lỗi nhỏ,
   refactor nội bộ, hay đổi style không cần ghi.
5. **Giữ tài liệu đồng bộ với code**: Nếu xoá hoặc đổi tên chức năng, phải
   cập nhật lại tài liệu tương ứng — tài liệu lỗi thời còn nguy hiểm hơn
   không có tài liệu.

## AI Role: Phân trang bắt buộc cho danh sách dữ liệu lớn (Pagination)

Mọi trang hiển thị danh sách dữ liệu (task, history, team, tags, notes, ...)
mà số lượng bản ghi có thể **vượt quá 50 dòng** thì **PHẢI CÓ phân trang**
(pagination) — không được dump toàn bộ ra một trang.

**Hướng dẫn dành riêng cho AI khi triển khai phân trang:**

1. **Dùng server-side pagination qua search params**: Truyền `page` (và tuỳ
   chọn `pageSize`) qua URL query string để server chỉ render đúng số bản ghi
   cần hiển thị. Mặc định `pageSize = 50`.
2. **Thanh phân trang (pagination bar)** phải có:
   - Nút **Trước / Sau** (Previous / Next).
   - Hiển thị **trang hiện tại / tổng số trang** (ví dụ: "Trang 3 / 12").
   - Hiển thị **tổng số bản ghi** (ví dụ: "Tổng: 580 kết quả").
3. **Giữ nguyên filter khi chuyển trang**: Khi bấm sang trang khác, tất cả
   bộ lọc hiện tại (search, sort, date range, ...) phải được giữ nguyên trong
   URL.
4. **Không slice cứng**: Tuyệt đối không dùng `.slice(0, N)` rồi bỏ qua phần
   còn lại — người dùng phải có cách xem toàn bộ dữ liệu thông qua phân trang.

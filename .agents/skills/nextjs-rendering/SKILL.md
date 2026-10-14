---
name: nextjs-rendering
description: Cách tận dụng tối đa Next.js (App Router) và React khi làm trang có dữ liệu, filter, phân trang - chọn đúng server render hay client render, giảm request vào core API, làm click filter mượt. Dùng khi tạo/sửa page trong apps/web có danh sách, bộ lọc, hoặc khi trang chậm, bị 429 rate limit, giật khi lọc.
---

# Tận dụng Next.js: server render vs client render

Bối cảnh dự án: web gọi core API bằng MỘT `X-API-Key` dùng chung, nên mọi trang và mọi người
cùng một bucket rate limit (xem `core/rate_limit.py`). Mỗi lần Next render lại page là mỗi lần
gọi core. Tối ưu = bớt render server không cần thiết và bớt request lặp.

## 1. Chọn nơi lọc theo kích thước tập dữ liệu (quy tắc quan trọng nhất)

| Tập dữ liệu | Cách làm | Ví dụ trong repo |
|---|---|---|
| Nhỏ (≲ 1000 dòng, vd task ĐANG MỞ) | Server Component tải MỘT lần, giao xuống một client component lọc bằng React (`useMemo`). Filter = 0 request. | `app/team/page.tsx` + `components/team-open-list.tsx` |
| Lớn (lịch sử, tất cả) | Lọc + phân trang Ở BACKEND (limit/offset), URL `?page=`. Mỗi click là một lần render server, nên phải có skeleton. | `app/tasks/page.tsx`, `/team?status=closed` |
| Vượt ngưỡng của chế độ nhỏ | Tự rơi về chế độ lớn (có hằng ngưỡng, vd `CLIENT_MODE_MAX`). | `loadOpenWorkTasks()` trả `null` |

Không "tải hết rồi lọc ở server" cho tập lớn: đó là lỗi cũ của `/team` (tới 25 request nối tiếp mỗi click).

## 2. Server Component làm gì, Client Component làm gì

- **Server Component (mặc định):** gọi `lib/api.ts`, đọc `searchParams`, tải song song bằng `Promise.all`.
  Không gửi key hay dữ liệu thừa xuống browser.
- **Client Component (`"use client"`) chỉ khi cần:** state UI, ô gõ, filter tại chỗ, `useTransition`.
  Giữ nó NHỎ và ở LÁ cây; đừng đánh `"use client"` cho cả page.
- Dữ liệu qua ranh giới server→client phải **serialize được và gọn**: chỉ truyền trường cần hiển thị,
  không truyền `raw_payload`/trường nặng; tránh giao hàng nghìn dòng.
- Giá trị phụ thuộc thời gian (`Date.now()`, "N ngày qua") tính ở server rồi truyền xuống (`nowMs`)
  để server và client cùng một mốc, tránh lệch hydration.

## 3. Làm click filter mượt

- **Filter tại chỗ (chế độ nhỏ):** `useDeferredValue` cho giá trị lọc (ô gõ không khựng) và làm mờ
  danh sách khi `deferred !== current`. Đồng bộ URL bằng `window.history.replaceState` trong `useEffect`:
  không render lại server, refresh/chia sẻ link vẫn giữ filter. Reset `page=1` khi đổi filter.
- **Điều hướng server (chế độ lớn):** thêm `loading.tsx` (skeleton) cho route; với filter dạng nút
  dùng `useTransition` + `router.push` để GIỮ danh sách cũ (mờ đi) thay vì trắng trang. Có thể bọc
  phần danh sách nặng trong `<Suspense>` để thanh filter hiện trước.
- Không bao giờ `window.location.reload()`; dùng `router.refresh()` sau mutation (đã có
  `revalidateAll()` trong `app/actions.ts`).

## 4. Giảm request vào core (đã có sẵn, đừng tự viết lại)

- `coreFetch` trong `lib/api.ts`: **GET được cache 10 giây** theo path+query và gộp lời gọi đồng thời
  (`lib/core-cache.ts`); mọi lời gọi ghi và `revalidateAll()` xoá cache; `/api/v1/integrations*` không
  cache. Tự thử lại tối đa 2 lần khi core trả 429 (theo `Retry-After`, trần 3 giây).
- `React.cache()` cho hàm được nhiều Server Component gọi trong cùng một lần render
  (`getCurrentUsersApi`). Múi giờ không cần: nó là hằng `DISPLAY_TZ`, không gọi API.
- Dữ liệu dùng chung nhiều trang (projects, current-users) đặt ở layout hoặc để cache lo;
  layout KHÔNG render lại khi chỉ đổi `searchParams`.
- Tải song song độc lập bằng `Promise.all`; không `await` nối tiếp trừ khi phụ thuộc nhau.
- Phân trang bắt buộc phía server cho danh sách lớn, mặc định 50, tối đa 200 (backend `le=200`).

## 5. Checklist trước khi báo xong một trang có filter/danh sách

- [ ] Đã ước lượng kích thước tập dữ liệu và chọn chế độ nhỏ/lớn đúng bảng mục 1; có ngưỡng fallback.
- [ ] Đếm số lời gọi core mỗi lần render và mỗi click filter (ghi vào PR/handoff). Chế độ nhỏ: 0 mỗi click.
- [ ] Không truyền dữ liệu thừa xuống client; không `any`; `tsc --noEmit` đạt.
- [ ] Có `loading.tsx` hoặc pending state; không trắng trang khi lọc.
- [ ] Filter nằm trên URL, refresh giữ nguyên; `page` reset khi đổi filter; tổng số + nút trước/sau.
- [ ] Sau mutation danh sách cập nhật (Server Action → `revalidateAll()`), client state (filter) không mất.
- [ ] Lỗi API hiện `ApiErrorPanel`, không crash trắng.

---
inclusion: fileMatch
fileMatchPattern: "apps/web/**/*"
---

# Quy ước web dễ vi phạm

Chỉ nạp khi đang sửa file trong `apps/web/`. Quy trình thêm entity mới
xuyên suốt backend+frontend nằm ở skill `add-entity`.

- **API key không được xuống browser.** Chỉ Server Component và Server
  Action gọi `lib/api.ts`. Client component gọi Server Action, không gọi
  fetch trực tiếp.
- **`NEXT_PUBLIC_*` nhúng lúc build**, không đọc được ở runtime. Thêm biến
  mới loại này thì phải khai báo build arg trong `apps/web/Dockerfile` và
  truyền trong `docker-compose.prod.yml`.
- **State của store cục bộ phải nằm trên `globalThis`.** Next bundle Server
  Component và Route Handler thành hai module graph riêng, nên biến ở mức
  module có thể tồn tại hai bản khác nhau. Triệu chứng đã gặp: trang hiển
  thị đủ dữ liệu nhưng `/api/export` trả về mảng rỗng. Xem `lib/store/engine.ts`.
- **Đọc/ghi dữ liệu chỉ qua `lib/api.ts`.** Nó điều phối ba chế độ
  `DATA_SOURCE` (api, file, memory). Đừng import `store/engine.ts` trực tiếp
  từ page hay component.
- **Thêm trang mới thì khai báo trong `lib/nav.ts`,** không sửa `layout.tsx`.
  Việc hàng ngày vào `PRIMARY_NAV`, tài liệu về dự án vào `SECONDARY_NAV`.
  Nav là phẳng, không dropdown — đừng thêm lại menu bấm mới mở.
- **Sơ đồ ở `components/architecture-diagrams.tsx` tính toạ độ tay.** Giữ
  khoảng cách tối thiểu 20px giữa các hộp, cho mũi tên đi gấp khúc qua vùng
  trống. `DiagramDefs` chỉ được render một lần cho mỗi trang.
  Nhãn mũi tên **có nền nên chiếm chỗ thật**: ước lượng khoảng 6px mỗi ký tự
  rồi kiểm tra nó không chồng lên hộp nào. Đã từng phải đẩy hộp `done` từ
  x=650 sang x=680 chỉ để nhãn `completed_at` có chỗ đứng.
- **Hiệu ứng sơ đồ dùng CSS, không dùng SMIL,** để tắt được bằng
  `prefers-reduced-motion` và bằng công tắc trên trang. Khi tắt, trạng thái
  tĩnh phải là **đã vẽ xong**: nhớ reset `stroke-dasharray` trong khối
  `[data-motion="off"]`, nếu không nét sẽ biến mất. Chỉ bật `animated` cho
  luồng chính, đừng cho mọi mũi tên chạy cùng lúc.
- **Thêm tài liệu mới thì khai báo trong `lib/docs.ts`** và mount vào
  compose nếu file nằm ngoài `apps/web`. Tài liệu người dùng ở `docs/`.
- **Đổi cấu trúc file JSON thì phải tăng `SCHEMA_VERSION` và viết bước
  migrate.** Xem `store/json-file.ts`. Thêm field mà không backfill thì dữ
  liệu cũ đọc lên là `undefined`, và code so sánh `=== null` sẽ hiểu sai.
  Hiện tại đang ở **v3** (v2 → v3 là thêm mảng `notes`). Thêm mảng mới thì
  phải backfill thành `[]`, vì engine gọi `.filter()` ngay khi nạp.
- **Nội dung note render bằng text node của JSX**, tuyệt đối không
  `dangerouslySetInnerHTML` — nội dung do người dùng dán, mở đường cho XSS.

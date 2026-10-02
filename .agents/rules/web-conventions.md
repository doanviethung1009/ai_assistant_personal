---
inclusion: fileMatch
fileMatchPattern: ["apps/web/**/*", "apps/**/*web*/**/*", "apps/**/*ui*/**/*", "apps/**/*admin*/**/*", "apps/**/*.tsx"]
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
- **`DATA_SOURCE=file` qua Docker cần mount `./data:/data`.** Đã khai sẵn ở
  `docker-compose.yml` và `DATA_DIR=/data`. Nếu tự viết compose khác và quên
  mount, `lib/store/json-file.ts` vẫn ghi được nhưng dữ liệu nằm trong
  filesystem của container — mất khi `docker compose rm`/rebuild. Đổi
  `DATA_SOURCE` qua `.env` không tự áp dụng, phải `docker compose up -d web`
  lại (dùng `make use-db` / `make use-local`, đã làm sẵn cả hai bước).
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
  Hiện tại đang ở **v4** (v4 là tách mảng `ai_logs` ra file riêng). Thêm mảng mới thì
  phải backfill thành `[]`, vì engine gọi `.filter()` ngay khi nạp.
- **Quy tắc Lưu trữ JSON (Local Storage Split vs Group):** Khi phát sinh tính năng/dữ liệu mới, BẮT BUỘC ĐÁNH GIÁ ĐẶC TÍNH DỮ LIỆU trước khi thêm vào JSON.
  - **Để chung (`builder-data.json`):** Dành cho dữ liệu cốt lõi, có tính ràng buộc (relational), số lượng bản ghi được kiểm soát, thường xuyên cập nhật/xoá (Ví dụ: `tasks`, `projects`, `notes`).
  - **Tách riêng file mới (VD: `ai-logs.json`):** Dành cho dữ liệu dạng Append-only (chỉ thêm mới), lịch sử, log, hoặc dữ liệu có kích thước văn bản cực lớn. Vì cơ chế lưu file là Atomic Write (ghi đè toàn bộ), việc nhồi nhét dữ liệu phình to liên tục vào file chung sẽ tạo nút thắt cổ chai (I/O Bottleneck), làm giật lag toàn hệ thống. HÃY TÁCH RIÊNG nếu nhận thấy dữ liệu có tính chất này.
- **Nội dung note render bằng text node của JSX**, tuyệt đối không
  `dangerouslySetInnerHTML` — nội dung do người dùng dán, mở đường cho XSS.
- **`lib/types.ts` không còn viết tay field của entity.** Nó alias sang
  `lib/generated/openapi.d.ts`, sinh tự động từ `/openapi.json` của api đang
  chạy bằng `make gen-types` (hay `npm run gen:types` trong container web).
  Sửa model hay schema Pydantic ở backend thì chạy lại lệnh đó, đừng sửa tay
  field trong `types.ts`. File generated **có commit vào git**, không
  gitignore, để `tsc` chạy được mà không cần container `api` đang sống.
  Field nào Pydantic khai `default=None` (ví dụ `deleted_at`, `color`,
  `events`) thì openapi-typescript sinh ra optional (`field?: T | undefined`)
  dù response thật luôn trả đủ field — chỉ giá trị có thể null. `types.ts`
  dùng helper `WithRequiredDeletedAt` / `WithRequiredColor` để ép lại required
  cho đúng với response thật, tránh `undefined` lan ra khắp component. Thêm
  field optional kiểu mới ở backend thì nhớ kiểm tra `tsc --noEmit` có báo lỗi
  ở component không — nếu có, mở rộng helper tương ứng trong `types.ts`, đừng
  sửa từng component.
  Những type không nằm trong OpenAPI (nhãn hiển thị như `STATUS_LABELS`,
  `NOTE_KIND_LABELS`, hay field tính riêng cho UI) vẫn khai tay trong
  `types.ts` như trước — chỉ phần trùng với schema backend là alias.
- **Trang `/system` (Thông tin hệ thống) không bao giờ render secret thật.**
  Trang này không có cơ chế đăng nhập riêng — ai mở được URL (kể cả qua LAN
  nếu đã `make lan-up`) đều xem được mọi thứ ở đó. Field hiển thị PHẢI tới từ
  `apps/core/app/schemas/system.py::SystemInfo` (đã được backend lọc chỉ còn
  field không nhạy cảm), không tự thêm biến môi trường mới vào component.
  Muốn thêm field thì sửa `SystemInfo` ở backend trước, chạy `make gen-types`,
  rồi mới render. Thông tin "nội bộ nhưng không mật" (URL nội bộ, tên biến
  đang dùng) bọc trong `<SensitiveToggle>` để không hiện ngay khi mở trang,
  nhưng đừng dùng nó để biện minh cho việc hiện secret thật sau một cú click.

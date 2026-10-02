---
name: add-entity
description: Checklist đầy đủ 15 bước để thêm một entity/model mới xuyên suốt backend FastAPI và frontend Next.js (giống Task hoặc Note đã có). Dùng khi được yêu cầu thêm bảng mới, model mới, hoặc một loại dữ liệu mới cần CRUD + hiển thị trên web.
---

# Thêm entity mới

Bỏ sót một khâu trong chuỗi dưới đây thì lỗi chỉ hiện ở đúng một chế độ
`DATA_SOURCE` (api/file/memory), và thường là chế độ bạn không chạy lúc test
— rất khó phát hiện bằng cách đọc lại code. Đi đúng thứ tự, đừng nhảy bước.

Tham khảo entity `Task` hoặc `Note` đã có làm mẫu cho mỗi bước.

## Backend (`apps/core/`)

1. **Model** — tạo file trong `app/models/`, kế thừa `Base`. Dùng
   `enum_column()` từ `db/base.py` cho cột enum (xem steering
   `backend-conventions`). Nếu entity hỗ trợ xoá mềm, thêm cột `deleted_at`
   và ràng buộc unique phải là **partial index** `WHERE deleted_at IS NULL`.
2. **Export model** — thêm vào `app/models/__init__.py`, nếu không Alembic
   autogenerate sẽ không thấy bảng mới.
3. **Schema** — tạo Pydantic schema trong `app/schemas/` (Create/Update/Read
   tách riêng, theo mẫu `schemas/task.py`).
4. **Service** — logic nghiệp vụ trong `app/services/`. Nếu có xoá mềm, viết
   helper `_alive()` lọc `deleted_at IS NULL` — bắt buộc dùng ở mọi query.
5. **Router** — route trong `app/api/v1/`. Route tĩnh (`/stats`, `/trash`...)
   phải khai báo **trước** route động (`/{id}`), xem steering
   `backend-conventions`.
6. **Đăng ký router** — thêm vào `app/api/v1/router.py`.
7. **Migration** — `make migration m="thêm bảng <ten>"` rồi `make migrate`.

## Frontend (`apps/web/`)

8. **Type** — mirror schema backend vào `lib/types.ts`.
9. **Store type** — thêm `StoredX` (bản lưu file JSON) và field tương ứng
   trong `DataFile` ở `lib/store/types.ts`. Nếu đổi cấu trúc file đã có,
   tăng `SCHEMA_VERSION` và viết bước migrate trong `store/json-file.ts`
   (xem steering `web-conventions`).
10. **Engine** — thêm CRUD trong `lib/store/engine.ts` (dùng cho chế độ
    `file` và `memory`).
11. **API client** — thêm hàm gọi trong `lib/api.ts`, phải hoạt động đúng ở
    **cả ba chế độ** `DATA_SOURCE` (api, file, memory) — đây là bước hay bị
    bỏ sót nhất.
12. **Server Action** — thêm mutation trong `app/actions.ts` nếu cần ghi từ
    client component.
13. **Data Migration (Export/Import)** — **BẮT BUỘC:** Mọi Data/Entity phát sinh đều phải có cơ chế di chuyển giữa Local JSON và Database (Postgres). Bạn phải cập nhật UI Nhập dữ liệu (`components/data-import.tsx`), logic (`app/actions.ts`), luồng Export (`app/api/export/route.ts`), và lõi xử lý (`store/transfer.ts`) để người dùng có thể import/export entity mới này. Đừng để dữ liệu mới bị kẹt chết ở một môi trường.
14. **Nav/UI** — nếu cần trang riêng, khai báo trong `lib/nav.ts` (không sửa
    `layout.tsx` trực tiếp).

## Kiểm tra

15. **Smoke test** — bổ sung assertion vào `scripts/smoke-test.sh`, rồi chạy
    `make smoke`. Đây là cách duy nhất xác nhận cả 15 bước trên khớp nhau —
    đọc lại code không đủ để bắt lỗi thiếu đồng bộ giữa `lib/types.ts` và
    schema backend.

# Lưu trữ JSON Cục bộ (Local JSON Storage)

Dự án này hỗ trợ chế độ lưu trữ dữ liệu thông qua File JSON cục bộ (khi biến môi trường `DATA_SOURCE=file`). Dữ liệu sẽ được lưu tại `data/builder-data.json`.

Để đảm bảo an toàn cho dữ liệu người dùng khi ứng dụng được cập nhật thêm các tính năng mới (Ví dụ: Thêm tính năng Thùng rác, Sổ tay, hoặc Nhật ký AI), chúng ta sử dụng một cơ chế gọi là **Data Migration** (Di chuyển dữ liệu) dành riêng cho file JSON, được điều khiển bởi cờ `SCHEMA_VERSION`.

---

## 1. `SCHEMA_VERSION` là gì?

`SCHEMA_VERSION` là một số nguyên (Integer) đại diện cho **phiên bản cấu trúc** của file JSON hiện tại. 
Nó được định nghĩa tại file `apps/web/lib/store/types.ts`.

Mỗi khi hệ thống có thêm một tính năng mới yêu cầu thêm trường dữ liệu (Ví dụ: thêm mảng `ai_logs`), chúng ta **BẮT BUỘC BUMP (Tăng)** số `SCHEMA_VERSION` này lên +1.

---

## 2. Lịch sử các phiên bản (Schema History)

- **v1**: Phiên bản sơ khai (Chỉ có `tasks` và `projects`).
- **v2**: Thêm trường `deleted_at` vào Task để phục vụ tính năng Thùng rác.
- **v3**: Thêm mảng `notes` để phục vụ tính năng Sổ tay (Notes).
- **v4**: Phiên bản dọn dẹp (Lược bỏ `ai_logs` khỏi file chính).

> [!NOTE]
> **Thiết kế phân mảnh (Split Storage):** 
> Dữ liệu `ai_logs` là dạng append-only (ghi thêm) và phình to rất nhanh. Nếu để chung trong `builder-data.json`, mỗi khi bạn đánh dấu "Done" một Task, hệ thống sẽ phải ghi đè (Atomic Write) toàn bộ 10MB dữ liệu AI, gây giật lag nghiêm trọng. Do đó, từ Schema v4 trở đi, `ai_logs` được tách ra lưu riêng tại file `data/ai-logs.json`. Khối xử lý `json-file.ts` và `engine.ts` quản lý việc ghi 2 file này hoàn toàn độc lập.

---

## 3. Cơ chế tự động Migrate (Backward Compatibility)

Khi ứng dụng khởi động (chạy `npm run dev`), hệ thống Engine (tại `apps/web/lib/store/json-file.ts`) sẽ đọc file `builder-data.json` hiện có của người dùng.

1. Nó sẽ kiểm tra trường `schema_version` bên trong file JSON đó.
2. Nếu phiên bản trong file **nhỏ hơn** phiên bản hiện tại của Code (`SCHEMA_VERSION = 4`), hệ thống sẽ tự động chạy các hàm "Trám dữ liệu" (Backfill).
3. **Ví dụ:** Nếu file cũ của người dùng đang là `v3`, code sẽ chạy khối lệnh:
   ```typescript
   if (data.schema_version < 4) {
     if (!Array.isArray(data.ai_logs)) {
       data.ai_logs = []; // Trám mảng rỗng vào để không bị lỗi undefined
     }
     data.schema_version = 4;
   }
   ```
4. Sau đó, nó ghi ngược lại file JSON với phiên bản mới. Người dùng hoàn toàn không cảm nhận được quá trình này, và app không bao giờ bị crash vì thiếu dữ liệu.

---

## 4. Tại sao không dùng Database cho nhanh?

Với PostgreSQL, việc thêm cột/bảng được quản lý qua Alembic (`make migration`).
Tuy nhiên, điểm mạnh của chế độ `DATA_SOURCE=file` là sự tiện lợi: **Chạy app không cần cài Docker hay CSDL**.
Do đó, chúng ta phải "tự tay" viết script migrate JSON để đảm bảo ứng dụng vẫn chạy mượt mà trên môi trường máy cá nhân yếu hoặc chưa được thiết lập đầy đủ.

# Két bảo mật (Vault)

Trang `/vault` lưu thông tin hệ thống nhạy cảm: mật khẩu DB, SSH key, API token,
connection string, tài khoản console… Dữ liệu được **mã hoá ngay trên trình
duyệt**, server không bao giờ thấy mật khẩu master, mã khôi phục hay nội dung gốc.

## Mô hình khoá (envelope encryption, blob v2)

```
DEK (AES-256 ngẫu nhiên)  ──mã hoá──▶  nội dung két
 ├─ wrap bằng KEK_password   (PBKDF2-SHA256 600k vòng, từ mật khẩu master)
 └─ wrap bằng KEK_recovery   (PBKDF2-SHA256 100k vòng, từ mã khôi phục 160 bit)
```

Hai cách mở cùng một DEK nên **quên mật khẩu vẫn mở được bằng mã khôi phục**, mà
không phải mã hoá nội dung hai lần. Đổi mật khẩu chỉ wrap lại DEK.

## Luồng hoạt động

1. **Tạo két**: đặt mật khẩu master (tối thiểu 10 ký tự). App sinh **mã khôi
   phục** dạng `XXXX-XXXX-…` (8 nhóm) và hiện **đúng một lần**; phải tick “đã cất”
   mới vào được két. Có nút Chép / Tải .txt / In.
2. **Mở khoá**: nhập mật khẩu. Sai mật khẩu → AES-GCM báo lỗi xác thực (không
   lưu hash mật khẩu). Sai liên tiếp từ lần 4 sẽ bị làm chậm dần.
3. **Quên mật khẩu**: ở màn khoá bấm *“Quên mật khẩu? Dùng mã khôi phục”* → nhập
   mã + đặt mật khẩu mới. Dữ liệu giữ nguyên, mã khôi phục vẫn dùng được.
4. **Xem**: trường *Bí mật* hiển thị `••••••••••`. **Hiện** xem tạm 15 giây.
   **Chép** đưa vào clipboard và cố xoá sau 30 giây.
5. **Tự khoá**: sau 5 phút không thao tác hoặc bấm *Khoá ngay*; plaintext và khoá
   bị xoá khỏi bộ nhớ.
6. **Mã khôi phục mới**: nút *Mã khôi phục mới* sinh mã khác, **mã cũ mất hiệu lực**.

Két tạo trước khi có mã khôi phục (blob v1) vẫn mở được; lần mở đầu tiên sẽ tự
nâng lên v2 và hiện banner *“Tạo mã khôi phục ngay”*.

## Mỗi mục lưu gì

Tên, loại hệ thống (Database, Server/SSH, API, Cloud, Tài khoản web, Khác), dự
án, tag, ghi chú, và danh sách trường `{nhãn, giá trị, bí mật?}` tuỳ ý. Chọn loại
sẽ điền sẵn các trường thường dùng. Tìm kiếm chỉ quét trường **không** bí mật.

## Lưu trữ

- File: `data/vault.json` (quyền 0600, có `.bak` của lần ghi trước). Nằm trong
  `/data/` nên đã được `.gitignore`.
- **Độc lập `DATA_SOURCE`**: file/memory/api dùng chung một nơi, không cần
  migration Postgres hay import/export giữa các chế độ.
- Mã hoá cả danh sách thành MỘT blob để không lộ số mục và metadata.
- Chống ghi đè: server so `updated_at` của blob client đã đọc, tab cũ không ghi
  đè được bản mới.
- Sao lưu: nút *Sao lưu (đã mã hoá)* hoặc `GET /api/export?format=json&entity=vault`.
  File chỉ chứa ciphertext nên an toàn để cất.

## Giới hạn cần biết

- **Mất CẢ mật khẩu LẪN mã khôi phục = mất dữ liệu.** Không có đường khôi phục
  nào khác, kể cả với người quản trị server.
- **Mã khôi phục = chìa khoá dự phòng.** Ai có mã đều mở được két, nên đừng cất
  cùng chỗ với mật khẩu master.
- Bảo vệ khỏi người đọc file/DB, KHÔNG bảo vệ khỏi máy bị cài mã độc hoặc
  extension trình duyệt xấu (khi két đang mở, plaintext nằm trong RAM).
- Web Crypto cần **secure context**: chạy qua `localhost` hoặc HTTPS. Mở bằng
  `http://<IP-LAN>` thì trình duyệt không cho dùng `crypto.subtle`.

## File liên quan

| File | Vai trò |
| --- | --- |
| `apps/web/lib/vault/crypto.ts` | PBKDF2 + AES-GCM, DEK/wrap, mã khôi phục (chạy ở browser) |
| `apps/web/lib/vault/store.ts` | Đọc/ghi blob `data/vault.json` (server-only) |
| `apps/web/app/vault-actions.ts` | Server Action chuyển blob, không nhận plaintext |
| `apps/web/components/vault-client.tsx` | UI: đặt/mở khoá, thẻ mục, che/hiện, form |
| `apps/web/components/vault-recovery.tsx` | Màn hiện mã khôi phục, form quên mật khẩu |
| `apps/web/app/vault/page.tsx` | Trang `/vault` |
| `scripts/checks/vault-crypto-check.ts` | Kiểm thử vòng đời mã hoá: `npx tsx …` |

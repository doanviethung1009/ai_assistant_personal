---
name: e2ee-vault
description: Quy trình triển khai hệ thống mã hoá đầu cuối (End-to-End Encryption) cho tính năng Vault. Dùng khi thao tác với dữ liệu siêu nhạy cảm.
---

# Quy trình Triển khai Zero-Knowledge Vault

1. **Mã hoá tại Client (Client-Side Encryption):** Mọi dữ liệu Vault phải được mã hoá bằng thuật toán AES-256-GCM trực tiếp trên trình duyệt bằng mật khẩu Master của người dùng.
2. **Kéo giãn khoá (Key Derivation):** Sử dụng PBKDF2 (hoặc Argon2) để biến mật khẩu Master thành Encryption Key mạnh.
3. **Luật Backend:** API Backend `apps/core/` CHỈ được phép nhận dải ký tự đã mã hoá (Cipher text) và Nonce/IV. Cấm Backend đòi mật khẩu Master của User. Backend không có khả năng giải mã dữ liệu này.
4. **Cảnh báo mất data:** Agent phải thiết lập cơ chế UI cảnh báo rõ ràng cho User: "Nếu quên mật khẩu Master, toàn bộ dữ liệu Vault sẽ vĩnh viễn không thể khôi phục".

# Lưu trữ: script sửa lỗi một lần (đã áp dụng)

71 script `patch_*.py` / `fix_*.py` ở đây là lịch sử các lần agent sửa code gián tiếp.
Chúng đã chạy xong, kết quả nằm sẵn trong source. **Không chạy lại** (phần lớn không idempotent
và sẽ ghi đè code hiện tại). Giữ để truy vết, có thể xoá khi không còn cần.

Script mới: dùng Edit trực tiếp trên file đích. Hook `.claude/hooks/no-patch-scripts.sh` chặn
tạo `patch_*` / `fix_*`. Script một lần thật sự cần thiết thì đặt tên khác, cất ở `scripts/patches/`.

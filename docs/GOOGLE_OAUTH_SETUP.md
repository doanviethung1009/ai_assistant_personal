# Cấu hình Google OAuth Client (đăng nhập Google)

> Dành cho epic đăng nhập đa người dùng (`docs/specs/auth-multiuser.md`). Đây là phần **bạn tự làm trên Google Cloud Console**; code không làm thay được.
>
> **Google chỉ là MỘT trong hai cách đăng nhập.** Cách còn lại là tài khoản nội bộ (tên đăng nhập + mật khẩu, `PASSWORD_LOGIN_ENABLED`, mặc định bật; spec `docs/specs/admin-users-local-login.md`). **Nếu chỉ dùng tài khoản nội bộ thì bỏ qua các mục 2-5**: để trống `AUTH_GOOGLE_ID`/`AUTH_GOOGLE_SECRET`, nút Google sẽ không hiện ở `/login`. Tạo admin đầu tiên bằng `make auth-create-local USERNAME=... EMAIL=... ROLE=admin` (in mật khẩu tạm một lần; đăng nhập xong web ép đổi).

## 1. Khi nào cần, khi nào không

| Chế độ | Cần Google OAuth? |
|---|---|
| Local debug (`DATA_SOURCE=file` hoặc `memory`) | **Không.** Không có đăng nhập, mở thẳng web. |
| Local chạy thử luồng đăng nhập (`DATA_SOURCE=api`, `http://localhost:3000`) | Có, dùng một OAuth client riêng cho dev. |
| Server dev / staging / prod (Proxmox) | Có, **mỗi môi trường một OAuth client riêng** (xem mục 5). |

## 2. Tạo project và màn hình đồng ý (OAuth consent screen)

1. Vào <https://console.cloud.google.com/> và chọn (hoặc tạo) một project, ví dụ `builder-ai-assistant`.
2. Menu **APIs & Services → OAuth consent screen** (giao diện mới có thể tên **Google Auth Platform → Branding / Audience**).
3. **User type**:
   - **Internal**: chỉ khi tài khoản Google Workspace của công ty tạo project; chỉ người cùng tổ chức đăng nhập được. Phù hợp nhất nếu mọi người dùng chung domain.
   - **External**: cho Gmail cá nhân hoặc nhiều domain. Trạng thái **Testing** chỉ cho tối đa 100 test user bạn khai báo thủ công; muốn bỏ giới hạn phải **Publish** (với scope cơ bản `openid email profile` thường không cần Google duyệt).
4. Điền tên ứng dụng, email hỗ trợ, email liên hệ nhà phát triển.
5. **Scopes**: chỉ cần `openid`, `email`, `profile`. **Không thêm** scope nhạy cảm (Drive, Gmail, Calendar...) nếu chưa có nhu cầu; thêm scope nhạy cảm sẽ kéo theo quy trình xác minh của Google.
6. Nếu để **External + Testing**: thêm email của những người sẽ đăng nhập vào **Test users**.

> Lưu ý: "Test users" của Google và danh sách mời (invite) trong ứng dụng là **hai lớp khác nhau**. Google quyết định ai được đi qua màn hình đăng nhập; ứng dụng quyết định email nào được vào hệ thống (invite-only).

## 3. Tạo OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. **Application type**: `Web application`.
3. **Name**: ví dụ `builder-ai-web-dev` (đặt tên theo môi trường).
4. **Authorized JavaScript origins** (không có dấu `/` ở cuối):
   - Local: `http://localhost:3000`
   - Staging/Prod: `https://<domain-của-web>`
5. **Authorized redirect URIs** (phải khớp **từng ký tự**, kể cả `http`/`https`, cổng, dấu `/`):
   - Local: `http://localhost:3000/api/auth/callback/google`
   - Staging/Prod: `https://<domain-của-web>/api/auth/callback/google`
6. Bấm **Create**, lưu lại **Client ID** và **Client secret**.

Quy tắc của Google cần nhớ:
- Redirect URI dùng `http` chỉ được phép với `localhost`. Mọi host khác **bắt buộc HTTPS**.
- Không dùng địa chỉ IP trần (ví dụ `https://192.168.1.10`) cho redirect URI; dùng tên miền (có thể là tên nội bộ qua DNS/hosts, nhưng phải kết thúc bằng TLD hợp lệ hoặc `localhost`). Với VM Proxmox nội bộ, nên đặt một tên miền thật có chứng chỉ hợp lệ (Let's Encrypt qua DNS challenge, hoặc reverse proxy có sẵn).
- Sửa cấu hình trên Google có thể mất vài phút mới có hiệu lực.

## 4. Đưa khoá vào ứng dụng

Đặt vào `.env` của môi trường (file này **không** commit; `.env.example` chỉ chứa tên biến, không chứa giá trị thật):

```bash
# Web (Auth.js v5)
AUTH_GOOGLE_ID=<Client ID>
AUTH_GOOGLE_SECRET=<Client secret>
AUTH_SECRET=<chuỗi ngẫu nhiên ≥ 32 byte>   # sinh bằng: openssl rand -base64 32
AUTH_URL=https://<domain-của-web>           # local: http://localhost:3000; VM qua LAN: http://<ip-vm>:3000. BẮT BUỘC, không có mặc định
AUTH_TRUST_HOST=true                        # chỉ khi web chạy sau reverse proxy đáng tin
CORE_JWT_SECRET=<chuỗi ngẫu nhiên ≥ 32 byte> # web ký JWT 60 giây gửi core; PHẢI giống hệt ở core
GOOGLE_ALLOWED_HD=                          # để trống; chỉ điền nếu cả team dùng một domain Workspace

# Core
# CORE_JWT_SECRET (cùng giá trị với web), GOOGLE_ALLOWED_HD (cùng giá trị với web)
ADMIN_EMAILS=ban@congty.com                 # bootstrap admin đầu tiên (email, ngăn cách bằng dấu phẩy)
```

`IMPORT_COMMIT_SECRET` đã bị bỏ (quyền nhập/cào Jira nay theo role, core kiểm). Thêm `PASSWORD_LOGIN_ENABLED=true` (mặc định; đặt `false` để tắt tạm đăng nhập mật khẩu khi có sự cố dò mật khẩu, không ảnh hưởng Google/CLI/admin API; đặt giống nhau ở `api` và `web`). Danh sách biến chốt cuối nằm ở `docs/specs/auth-multiuser.md` và `docs/specs/admin-users-local-login.md`.

- `AUTH_SECRET` mất hoặc đổi: mọi phiên đăng nhập hiện có bị vô hiệu (người dùng đăng nhập lại), dữ liệu không mất.
- **Client secret là bí mật**: không dán vào chat, ticket, commit hay log. Nếu lỡ lộ, vào Credentials → client → **Reset secret** rồi cập nhật `.env`.
- Mỗi môi trường dùng secret riêng để lộ một nơi không kéo theo nơi khác.

## 5. Mỗi môi trường một client

| Môi trường | Origin | Redirect URI | Ghi chú |
|---|---|---|---|
| Local | `http://localhost:3000` | `http://localhost:3000/api/auth/callback/google` | Chỉ khi cần thử luồng đăng nhập thật |
| Dev/Staging (Proxmox) | `https://<staging-domain>` | `https://<staging-domain>/api/auth/callback/google` | Xem `docs/PROXMOX_DEPLOY.md` |
| Prod | `https://<prod-domain>` | `https://<prod-domain>/api/auth/callback/google` | Consent screen nên ở trạng thái Published |

Một client có thể khai báo nhiều redirect URI, nhưng tách riêng theo môi trường để tắt/đổi từng nơi độc lập.

## 6. Kiểm tra sau khi cấu hình

1. Mở web, bấm **Đăng nhập với Google**, chọn tài khoản có trong `ADMIN_EMAILS`: phải vào được và thấy mục **Quản trị** (Người dùng, Nhật ký) trên menu.
2. Đăng nhập bằng một tài khoản Google **chưa được mời**: phải bị từ chối với thông báo rõ ràng, không tạo user.
3. Admin mời thêm một email ở **Quản trị → Người dùng** (có thể gán luôn "Tên trên Jira") rồi đăng nhập bằng email đó: vào được với vai trò đã gán.
4. Vô hiệu hoá một user: lần gọi tiếp theo của họ phải bị chặn ngay, không chờ hết phiên.

## 7. Lỗi thường gặp

| Thông báo của Google | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Error 400: redirect_uri_mismatch` | Redirect URI trên Google khác URI mà web gửi | So lại từng ký tự (scheme, host, cổng, `/api/auth/callback/google`); kiểm `AUTH_URL` |
| `Error 403: access_denied` / "app is being tested" | Consent screen ở Testing và email chưa vào Test users | Thêm email vào Test users hoặc Publish |
| `Error 401: invalid_client` | Sai Client ID/secret hoặc đã reset secret | Cập nhật lại `.env` rồi restart web |
| Đăng nhập Google xong nhưng quay lại trang login | `AUTH_SECRET` thiếu/đổi, hoặc cookie bị chặn do chạy HTTP ở host không phải localhost | Dùng HTTPS; kiểm `AUTH_URL`, `AUTH_TRUST_HOST` |
| Đăng nhập (mật khẩu hoặc Google) xong bị đẩy về `localhost` hoặc sang host khác host bạn gõ | `AUTH_URL` sai host: Auth.js redirect về `AUTH_URL`, không về host của request | Đặt `AUTH_URL` đúng URL đang gõ (vd `http://192.168.100.201:3000`) rồi tạo lại container web. Thiếu `AUTH_URL`: web hiện `/config-error` |
| Đăng nhập xong báo "chưa được mời" | Email chưa có trong danh sách mời (đúng thiết kế invite-only) | Admin thêm email ở **Quản trị → Người dùng → Thêm người dùng** (tab Google) |

## 8. Liên quan

- Spec: `docs/specs/auth-multiuser.md`, `docs/specs/admin-users-local-login.md`
- API đăng nhập và quản trị: `docs/API_REFERENCE.md` mục 9
- Hạ tầng và deploy: `docs/PROXMOX_DEPLOY.md`, `docs/PROXMOX_OPERATIONS.md`

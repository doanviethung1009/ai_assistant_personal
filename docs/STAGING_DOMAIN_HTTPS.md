# Domain và HTTPS cho staging/prod (để đăng nhập Google chạy được)

> Trả lời câu hỏi **Q1** của `docs/specs/auth-multiuser.md`. Có hai bối cảnh: **cá nhân** (bạn tự lo domain) và **công ty** (dùng domain công ty). Code không đổi giữa hai bối cảnh; chỉ đổi domain, chứng chỉ và OAuth client.
> Trạng thái: DRAFT, các đoạn cấu hình Caddy/compose là mẫu, sẽ chốt khi làm bước hạ tầng.

## 1. Vì sao cần domain

Hiện staging truy cập qua `http://192.168.100.202:3000`. Đăng nhập Google (OAuth) **không chạy** với địa chỉ này vì Google áp ba luật cho *Authorized redirect URI*:

| Luật của Google | Hệ quả với `http://192.168.100.202:3000` |
|---|---|
| `http://` chỉ được phép cho `localhost`; mọi host khác bắt buộc `https://` | Bị từ chối |
| Không chấp nhận IP trần (trừ localhost) | Bị từ chối |
| Host phải là domain có hậu tố công khai (public suffix: `.com`, `.vn`, `.ts.net`...); tên nội bộ như `.local`, `.lan`, `.internal`, `.home` bị từ chối | `ai-stg.lan` cũng không được |

Cần hiểu đúng một điều hay gây nhầm: **Google không bao giờ kết nối vào server của bạn.** Luồng chuyển hướng diễn ra trong **trình duyệt của người dùng**: trình duyệt đi sang Google, rồi Google bảo trình duyệt quay về `https://<domain>/api/auth/callback/google`. Vì vậy domain **chỉ cần phân giải được từ máy người dùng**. Nó được phép trỏ về IP riêng `192.168.100.202`; server không cần mở ra Internet.

Vậy bài toán gồm 3 mảnh:

1. **Tên miền** hợp lệ (qua public suffix) trỏ về staging.
2. **Chứng chỉ HTTPS** hợp lệ cho tên đó (trình duyệt tin cậy).
3. **Reverse proxy** (Caddy) đứng trước web để cắm chứng chỉ, nhận cổng 443.

## 2. Cách chứng chỉ được cấp khi server chỉ ở mạng LAN

Let's Encrypt có hai cách xác minh bạn sở hữu tên miền:

| Cách | Cần gì | Dùng được cho server chỉ trong LAN? |
|---|---|---|
| HTTP-01 | Let's Encrypt gọi vào cổng 80 của server từ Internet | **Không** (server không mở ra Internet) |
| **DNS-01** | Tạo một bản ghi TXT `_acme-challenge` trong DNS của domain; Caddy tự làm qua API của nhà cung cấp DNS | **Có** |

Nên dùng **DNS-01**. Hệ quả: nhà cung cấp DNS của bạn phải có API được Caddy hỗ trợ (Cloudflare, DigitalOcean, Route 53, Google Cloud DNS, Namecheap...), và cần **một API token chỉ có quyền sửa bản ghi DNS của đúng zone đó**, không phải mật khẩu tài khoản.

## 3. Bối cảnh CÁ NHÂN: các phương án

| # | Phương án | Chi phí | Công sức | Ai dùng được | Ghi chú |
|---|---|---|---|---|---|
| A | **Mua domain rẻ + Caddy DNS-01** (khuyến nghị) | ~8-15 USD/năm | Trung bình | Mọi máy trong LAN (hoặc ngoài, nếu có VPN) | Ổn định nhất, làm một lần dùng mãi |
| B | **Domain DDNS miễn phí** (DuckDNS, v.v.) + DNS-01 | 0 | Trung bình | Như A | Google thường chấp nhận nếu hậu tố nằm trong public suffix list; **phải thử tạo OAuth client** để chắc. Phụ thuộc dịch vụ miễn phí |
| C | **Tailscale** (`*.ts.net` + `tailscale cert`) | 0 | Thấp | Chỉ máy đã cài Tailscale | Không cần mua domain, không lộ ra Internet. Nhiều người báo Google chấp nhận `ts.net`; **cần thử khi tạo client** |
| D | **Localhost + SSH tunnel** | 0 | Rất thấp | Chỉ bạn, trên máy có tunnel | Không cần domain/HTTPS: `ssh -L 3000:localhost:3000 deploy@192.168.100.202` rồi mở `http://localhost:3000` (Google cho phép http với localhost). Tốt để thử nhanh; **không** dùng cho nhiều người |
| E | **Cloudflare Tunnel** | Domain trên Cloudflare | Trung bình | Cả Internet (hoặc giới hạn bằng Cloudflare Access) | Mở staging ra Internet. Chỉ chọn nếu thật sự cần truy cập từ ngoài |
| F | nip.io / sslip.io (`192-168-100-202.sslip.io`) | 0 | Thấp | Như A | **Không khuyến nghị**: bạn không kiểm soát DNS nên không làm DNS-01, không lấy được chứng chỉ ổn định |

### Khuyến nghị cá nhân

- **Dùng lâu dài, có thể mời vài người thử:** phương án **A**. Ví dụ mua `tenban.dev`, bản ghi `A  staging  192.168.100.202` (Cloudflare để chế độ **DNS only**, không proxy), tên truy cập `https://staging.tenban.dev`.
- **Chỉ mình bạn thử luồng đăng nhập trên staging:** phương án **D** là nhanh nhất, không tốn gì.
- **Có Tailscale sẵn:** phương án **C**.

### Việc làm cho phương án A (tóm tắt)

1. Mua domain, chuyển DNS về Cloudflare (hoặc nhà cung cấp có plugin Caddy).
2. Tạo API token chỉ có quyền *Zone → DNS → Edit* cho đúng zone.
3. Tạo bản ghi `A staging → 192.168.100.202`.
4. Máy trong LAN thấy bản ghi trỏ về IP riêng: một số router chặn trả lời kiểu này ("DNS rebinding protection"). Nếu không vào được, thêm ngoại lệ trong router/Pi-hole, hoặc ghi đè DNS nội bộ cho tên này.
5. Dựng Caddy (mục 5), tạo OAuth client với redirect URI `https://staging.tenban.dev/api/auth/callback/google` (xem `docs/GOOGLE_OAUTH_SETUP.md`).
6. Đặt `AUTH_URL=https://staging.tenban.dev`, `CORS_ORIGINS=https://staging.tenban.dev`.

## 4. Bối cảnh CÔNG TY: dùng domain công ty

Đây là cách tốt nhất khi dùng cho team: tên miền đáng tin, người dùng không phải cài gì, và có thể giới hạn đúng người trong công ty.

### 4.1. Nhờ IT/quản trị DNS những gì

| Yêu cầu | Chi tiết |
|---|---|
| Tên miền con | Ví dụ `ai-stg.congty.com` (staging), `ai.congty.com` (prod). Mỗi môi trường một tên riêng |
| Bản ghi A | Trỏ về IP của VM (`192.168.100.202` cho staging). Có thể chỉ khai báo ở **DNS nội bộ** (split-horizon), không cần đưa IP riêng lên DNS công khai |
| Chứng chỉ | Một trong ba cách ở 4.2 |
| Firewall/mạng | Cho phép người dùng truy cập cổng 443 của VM từ mạng nội bộ/VPN công ty |

### 4.2. Chứng chỉ HTTPS (chọn một)

| Cách | Khi nào hợp | Lưu ý |
|---|---|---|
| **Chứng chỉ do CA nội bộ của công ty** | Công ty có sẵn PKI, máy nhân viên đã tin CA | Không cần Let's Encrypt. IT cấp file cert/key, gắn vào Caddy |
| **Let's Encrypt DNS-01 qua API DNS công ty** | DNS công ty dùng nhà cung cấp có plugin Caddy | Cần token DNS. Nên xin token chỉ cho một zone con |
| **Let's Encrypt + CNAME ủy quyền `_acme-challenge`** | IT không muốn giao token của zone chính | IT tạo `_acme-challenge.ai-stg.congty.com CNAME <zone-do-bạn-kiểm-soát>`; bạn chạy DNS-01 trên zone đó. Giới hạn rủi ro ở mức thấp nhất |

### 4.3. Google Cloud và OAuth cho công ty

- Tạo project OAuth trong **tổ chức Google Workspace của công ty**, không dùng tài khoản cá nhân: khi bạn nghỉ việc hoặc đổi vai trò, client không bị mất theo.
- **OAuth consent screen → User type = Internal**: chỉ tài khoản cùng tổ chức đăng nhập được, không bị giới hạn 100 test user, không cần Publish.
- Đặt `GOOGLE_ALLOWED_HD=congty.com` ở web và core: lớp chặn thứ hai, từ chối tài khoản ngoài domain dù Google cho qua. Vẫn giữ **invite-only**; `hd` chỉ thu hẹp thêm, không thay cho danh sách mời.
- Mỗi môi trường một OAuth client với redirect URI của riêng nó (`https://ai-stg.congty.com/api/auth/callback/google`, `https://ai.congty.com/...`).
- Client secret lưu ở nơi công ty quy định (vault/secret manager), không gửi qua chat hay email.

### 4.4. Chuyển từ cá nhân sang công ty

Chỉ đổi cấu hình, không đổi code:

1. DNS + chứng chỉ cho tên miền công ty.
2. OAuth client mới trong Workspace công ty; cập nhật `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`.
3. `AUTH_URL`, `CORS_ORIGINS`, `GOOGLE_ALLOWED_HD`.
4. Mời lại người dùng bằng **email công ty** (mời theo email nên email Gmail cá nhân không tự chuyển sang). Nếu admin đầu tiên cũng đổi email, cập nhật `ADMIN_EMAILS` và chạy lại bước bootstrap để dữ liệu cũ gán cho email mới.

## 5. Mẫu Caddy (mọi phương án có HTTPS)

Caddy đứng trước web, nhận 443, cấp chứng chỉ tự động bằng DNS-01. Cần bản Caddy có plugin DNS của nhà cung cấp (build bằng `xcaddy`, ví dụ `caddy-dns/cloudflare`).

```caddyfile
# Caddyfile (mẫu). Domain và nhà cung cấp DNS là ví dụ.
staging.tenban.dev {
    tls {
        # DNS-01: Caddy tự tạo/xoá bản ghi TXT _acme-challenge qua API
        dns cloudflare {env.CF_API_TOKEN}
    }
    encode zstd gzip
    reverse_proxy web:3000
}
```

Điểm cần đúng khi tích hợp vào stack hiện tại:

- Web hiện chỉ bind `127.0.0.1:3000` (xem `docs/PROXMOX_DEPLOY.md`). Giữ nguyên; chỉ Caddy cùng mạng compose mới gọi được `web:3000`. Caddy là dịch vụ duy nhất publish cổng 443.
- `AUTH_TRUST_HOST=true` **chỉ** vì có Caddy đứng trước và web không bị truy cập trực tiếp.
- Firewall `ufw` hiện chỉ mở 22 và 3000 cho `192.168.100.0/24`: đổi thành 22 và 443 (từ LAN/VPN). **Docker bỏ qua `ufw` với cổng nó publish**, nên cách kiểm soát thật là chỉ publish đúng cổng cần.
- Không bao giờ mở cổng 8006 của Proxmox ra Internet hay qua Cloudflare Tunnel.
- File `.env` chứa `CF_API_TOKEN` (hoặc token của nhà cung cấp khác) không commit.

## 6. Chọn phương án nhanh

```
Chỉ mình bạn thử đăng nhập trên staging?            → D (SSH tunnel, 0 đồng)
Có Tailscale và mọi người dùng được Tailscale?        → C
Muốn ổn định, mời vài người, tự chủ?                  → A (mua domain)
Làm cho team công ty?                                 → Mục 4 (domain công ty)
```

## 7. Câu hỏi còn lại

- Domain/nhà cung cấp DNS cụ thể bạn chọn? (quyết định plugin Caddy cần build)
- Staging công ty có nằm trong cùng mạng `192.168.100.0/24` không, hay công ty sẽ cấp VM riêng?
- Người dùng truy cập từ mạng công ty hay qua VPN?

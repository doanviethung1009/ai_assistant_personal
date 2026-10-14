# Spec: Tài khoản nội bộ (mật khẩu) và trang quản trị người dùng

- Trạng thái: **CHỐT** (User chốt 2026-10-14: Q1-Q13 theo khuyến nghị của architect ở mục 9.1). Triển khai ở session mới, xem `docs/AI_HANDOFF_STATE.md` mục 18
- Tác giả: architect
- Ngày: 2026-10-13
- Nhánh lúc viết: `feat/auth-multiuser` (HEAD `55f5865`, working tree còn nhiều file sửa chưa commit; frontend-dev đang làm `web-authjs-login.md` song song, đã có `lib/auth-config.ts`, `lib/core-jwt.ts`, `lib/client-ip.ts`, `lib/redirect-safety.ts`; **chưa** có `auth.ts`)
- Spec liên quan (đều CHỐT): `docs/specs/auth-multiuser.md` (gọi tắt **[cha]**, P3 mục 4.2, 5.4, 5.5), `docs/specs/web-authjs-login.md` (gọi tắt **[web]**). Spec này **không** sửa hai spec đó; mọi điểm lệch nằm ở mục 8.
- Alembic head thật: `e8a3c6f2b1d7` (add_tasks_reporter), không phải `a1c9e4b7d2f8` như [cha] ghi (Phụ lục A7).
- Đã đối chiếu code: `apps/core/app/core/{auth,permissions,security,rate_limit,config}.py`, `api/v1/{auth,me,router}.py`, `api/deps.py`, `main.py`, `models/{user,audit_log,enums}.py`, `services/{auth_service,user_service,audit_service,errors}.py`, `schemas/{auth,user,common}.py`, `cli/auth.py`, `migrations/versions/b2f7a9c1d4e6_add_users_and_ownership.py` (qua head), `Makefile` (target `auth-*`); `apps/web/lib/{nav,auth-config,core-jwt,client-ip}.ts`, `components/main-nav.tsx`; `docs/GOOGLE_OAUTH_SETUP.md`.

## 1. Bối cảnh & phạm vi

### 1.1. Vấn đề

Hiện chỉ đăng nhập được bằng Google (invite-only theo email, [cha] C1). User muốn thêm **tài khoản nội bộ**: admin tạo ngay trong hệ thống (tên đăng nhập + mật khẩu do admin cấp), dùng cho người không có tài khoản Google công ty. Đồng thời cần **trang quản trị** `/admin/users`, `/admin/audit` ([cha] P3, chưa làm: `router.py` chưa có `admin`). Hiện admin chỉ quản lý được qua CLI `make auth-*`.

### 1.2. In-scope

1. Bảng `users`: thêm loại đăng nhập (`auth_provider`), `username`, `password_hash` (argon2id), cờ buộc đổi mật khẩu, đếm sai/khoá tạm.
2. Core: `POST /auth/login/password`, `POST /me/password`, chặn mọi route khi còn phải đổi mật khẩu, toàn bộ `/api/v1/admin/*` (người dùng + nhật ký).
3. Băm, chính sách mật khẩu, mật khẩu tạm hiện **một lần**, chống brute-force, chống liệt kê tài khoản, audit mọi thao tác.
4. Web: provider Credentials của Auth.js bên cạnh Google, form đăng nhập mật khẩu ở `/login`, `/me/password`, ép đổi mật khẩu lần đầu, trang `/admin/users`, `/admin/audit`, Server Action `app/admin/actions.ts`, nav theo quyền.
5. CLI: lệnh mới dùng chung service (`create-local`, `reset-password`, `unlock`), sửa `enable`/`token` cho tài khoản nội bộ.

### 1.3. Out-of-scope

- 2FA/TOTP cho tài khoản nội bộ (Q12), passkey/WebAuthn.
- Tự đăng ký, "quên mật khẩu" qua email (không gửi email; người dùng nhờ admin đặt lại).
- Một tài khoản đăng nhập được bằng **cả** Google và mật khẩu; chuyển đổi loại đăng nhập của tài khoản đã có (Q3).
- Xoá mềm user (Q7). RLS, token Jira theo user (P4 của [cha]).
- Thay đổi mô hình JWT web→core (giữ nguyên [web] Q2: web ký HS256).

### 1.4. Luồng đăng nhập mật khẩu (khớp mô hình JWT đã chốt)

**Quyết định:** core **xác thực mật khẩu**, web **ký JWT** như với Google. Credentials provider của Auth.js gọi core, core trả đúng `LoginResult { user_id, role, session_version }` như `/auth/login`; phần còn lại của [web] (cookie JWE `uid, sv`, `signCoreToken`, `coreFetch`, rào cache `uid:sv`) **không đổi**.

| Phương án | Mô tả | Chọn |
|---|---|---|
| A | Web chuyển `identifier + password` cho core qua `POST /auth/login/password` (X-API-Key), core so argon2id, trả `{user_id, sv}`; web ký JWT 60 giây như Google | **Có.** Hash không rời core; không thêm khoá, không đổi Q2, không đổi `core/auth.py::decode_token` |
| B | Core tự phát token (refresh/access) cho tài khoản nội bộ | Không. Hai loại token song song, phải sửa [web] 3.2, 4.5 và rào cache |

Mật khẩu đi qua tiến trình web trong bộ nhớ (không tránh được khi form nằm ở server). Không log, không đưa vào `Error.message`.

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as Web (Server Action + Auth.js Credentials)
    participant C as Core
    participant R as Redis
    B->>W: POST form /login (identifier, password) [Server Action, kiểm Origin]
    W->>W: signIn("credentials") → authorize()
    W->>C: POST /api/v1/auth/login/password (X-API-Key, identifier, password, client_ip)
    C->>R: đếm login-pw-ip, login-pw-id:<sha256>, login-pw-global
    C->>C: SELECT users (local) FOR UPDATE; argon2 verify (thread, semaphore); không có user → verify hash giả
    alt sai / khoá / disabled / tạm hết hạn
        C->>C: failed_login_count++, có thể đặt locked_until; audit login_denied; COMMIT
        C-->>W: 403 code=invalid_credentials (một thông báo chung)
        W-->>B: /login?error=invalid_credentials
    else đúng
        C->>C: reset đếm sai, last_login_at, rehash nếu cần, audit login_success{method:password}
        C-->>W: 200 {user_id, role, session_version}
        W->>C: GET /api/v1/me (JWT vừa ký) [tự kiểm khoá, [web] 4.3 bước 4]
        W-->>B: Set-Cookie phiên (uid, sv) + 302 callbackUrl
        B->>W: GET /tasks
        W->>C: GET /api/v1/me → must_change_password=true?
        W-->>B: layout thay nội dung bằng form đổi mật khẩu (mọi route core khác trả 403 password_change_required)
    end
```

## 2. Thay đổi dữ liệu

### 2.1. Bảng `users` (migration mới, `down_revision = "e8a3c6f2b1d7"`)

| Cột | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `auth_provider` | `varchar(16) NOT NULL` | `'google'` | `google` \| `local`. Dòng cũ thành `google`, không cần backfill |
| `username` | `varchar(64) NULL` | | Chỉ tài khoản `local`. Lưu chữ thường |
| `password_hash` | `varchar(255) NULL` | | Chuỗi mã hoá PHC của argon2id (`$argon2id$v=19$m=...`), ~100 ký tự |
| `must_change_password` | `boolean NOT NULL` | `false` | `true` sau khi admin tạo/đặt lại |
| `password_changed_at` | `timestamptz NULL` | | Lần đặt mật khẩu gần nhất; tính hạn mật khẩu tạm (Q5) |
| `failed_login_count` | `integer NOT NULL` | `0` | Số lần sai liên tiếp |
| `locked_until` | `timestamptz NULL` | | Khoá tạm tới thời điểm này |

Index/constraint (tên theo naming convention của `db/base.py`, tiền tố `ck_users_`, `uq_users_`):

| Tên | Định nghĩa | Lý do |
|---|---|---|
| `uq_users_username` | UNIQUE(`username`) (NULL lặp được) | Một tên đăng nhập một người |
| `ck_users_auth_provider_valid` | `auth_provider IN ('google','local')` | `enum_column()` không sinh CHECK |
| `ck_users_username_format` | `username IS NULL OR username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'` | Chữ thường, không `@` (phân biệt được với email khi đăng nhập), không khoảng trắng/ký tự điều khiển |
| `ck_users_local_credentials` | `auth_provider <> 'local' OR (username IS NOT NULL AND password_hash IS NOT NULL)` | Tài khoản nội bộ luôn có tên và hash |
| `ck_users_google_no_password` | `auth_provider <> 'google' OR (password_hash IS NULL AND username IS NULL AND must_change_password = false)` | Tài khoản Google không bao giờ có đường mật khẩu |
| `ck_users_local_no_sub` | `auth_provider <> 'local' OR google_sub IS NULL` | Không gắn Google vào tài khoản nội bộ (Q3) |
| `ck_users_local_not_invited` | `auth_provider <> 'local' OR status <> 'invited'` | Tài khoản nội bộ chỉ `active`/`disabled` |
| `ck_users_failed_login_non_negative` | `failed_login_count >= 0` | |
| `ck_users_active_has_sub` | **thay** thành `status <> 'active' OR auth_provider = 'local' OR google_sub IS NOT NULL` | Bản cũ chặn mọi tài khoản `active` không có `google_sub` |
| `ix_audit_log_target_created` | (`target_type`, `target_id`, `created_at`) trên `audit_log` | Lọc nhật ký theo user bị tác động (`/admin/audit?target=`) |

`email` giữ `NOT NULL` + `uq_users_email` + CHECK chuẩn hoá cho **mọi** loại tài khoản (Q1). Email của tài khoản nội bộ **chưa được xác minh**: chỉ để liên lạc/hiển thị, không dùng cho quyết định bảo mật nào, và nhờ UNIQUE nên không trùng được lời mời Google.

### 2.2. Enum, model

- `AuthProvider(StrEnum)`: `GOOGLE = "google"`, `LOCAL = "local"`, khai qua `enum_column(AuthProvider, "auth_provider")`.
- `AuditAction` thêm: `user_created` (tài khoản nội bộ), `password_reset` (admin đặt lại), `password_changed` (tự đổi), `login_locked`, `user_unlocked`, `user_deleted`. Không migration (cột `action` không có CHECK, [cha] 2.4).
- `User.__repr__` giữ như cũ (không email, không hash). Không thêm `password_hash` vào bất kỳ schema đọc nào.

### 2.3. Migration (viết tay, backend-dev)

- Upgrade: `ADD COLUMN` với default hằng (Postgres ≥ 11 chỉ đổi metadata), `DROP CONSTRAINT ck_users_active_has_sub` rồi tạo lại bản mới, tạo các CHECK/UNIQUE/index ở bảng trên. Bảng `users` nhỏ nên tạo CHECK VALID trực tiếp.
- Downgrade: (1) `UPDATE users SET status='disabled', session_version=session_version+1 WHERE auth_provider='local'` (để CHECK cũ `active_has_sub` tạo lại được và mọi phiên nội bộ chết); (2) drop index/CHECK/UNIQUE mới; (3) tạo lại `ck_users_active_has_sub` bản cũ; (4) drop 7 cột. **Mất** hash mật khẩu và tên đăng nhập: tài khoản nội bộ còn lại ở dạng `google` `disabled` không đăng nhập được, dữ liệu sở hữu (`owner_id`) giữ nguyên. Trước khi downgrade trên dữ liệu thật: `pg_dump -t users` (orchestrator ghi runbook).

## 3. Bảo mật mật khẩu (core)

Mọi phần dưới đây nằm ở `app/core/passwords.py` (mới) và `services/auth_service.py`, `services/user_service.py`. Web **không** băm, **không** kiểm chính sách (chỉ gợi ý độ dài trên UI).

### 3.1. Băm

| Mục | Quyết định |
|---|---|
| Thuật toán | argon2id |
| Thư viện | `argon2-cffi` (pin `>=23.1,<26`, `make lock`). Không dùng `passlib` (không còn bảo trì tích cực) |
| Tham số | `argon2.profiles.RFC_9106_LOW_MEMORY`: `time_cost=3`, `memory_cost=65536` KiB (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16` (muối ngẫu nhiên mỗi lần) |
| Chạy | `await anyio.to_thread.run_sync(...)` (không chặn event loop) sau một `asyncio.Semaphore(4)` của tiến trình: tối đa 4 phép băm đồng thời, trần ~256 MiB RAM |
| Nâng tham số | Đăng nhập đúng mà `check_needs_rehash()` → băm lại, ghi cùng transaction |
| Hash giả | Một hash của chuỗi ngẫu nhiên tính lúc import module; dùng để `verify` khi không có user hợp lệ (thời gian phản hồi như nhau) |
| Test | Fixture `monkeypatch` hasher sang `time_cost=1, memory_cost=8, parallelism=1` để test nhanh; test riêng khẳng định cấu hình production dùng đúng profile trên |

### 3.2. Chính sách (khi **đặt** mật khẩu, theo NIST SP 800-63B, Q4)

- Độ dài 12-128 ký tự (đếm code point), và ≤ 512 byte UTF-8. Đăng nhập nhận tối đa 1024 ký tự rồi mới so (chặn payload khổng lồ đốt CPU).
- Không có quy tắc "phải có chữ hoa/ký tự đặc biệt". Cho phép mọi ký tự in được kể cả dấu cách và tiếng Việt; cấm ký tự điều khiển (`\x00-\x1f\x7f`). Không chuẩn hoá Unicode (so đúng byte người dùng gõ).
- Từ chối: nằm trong danh sách mật khẩu phổ biến (`app/core/data/common-passwords.txt`, ~10.000 dòng từ SecLists, so không phân biệt hoa thường); chứa `username` hoặc phần trước `@` của email (khi phần đó ≥ 4 ký tự); trùng mật khẩu hiện tại (đổi mật khẩu).
- Lỗi trả 422 `code="weak_password"`, `detail` liệt kê **lý do** (không echo mật khẩu).

### 3.3. Mật khẩu tạm

- Core sinh (Q2): 16 ký tự từ bảng chữ không gây nhầm (`ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789`) bằng `secrets.choice`. ~92 bit entropy.
- Trả **một lần** trong body response của `POST /admin/users/local` và `POST /admin/users/{id}/reset-password`, header `Cache-Control: no-store`. Chỉ lưu hash. Không ghi vào log, audit, Redis.
- Đặt `must_change_password = true`, `password_changed_at = now()`. Hết hạn sau **72 giờ** nếu chưa đổi (Q5): đăng nhập bị từ chối như sai mật khẩu, admin đặt lại.

### 3.4. Chống brute-force và liệt kê tài khoản

| Lớp | Quy tắc |
|---|---|
| Redis (trước khi chạm DB) | `login-pw-ip:<ip>` 10/phút; `login-pw-id:<sha256(identifier chuẩn hoá)>` 10/phút; `login-pw-global` 60/phút. Vượt → 429. Khoá Redis dùng hash, không chứa tên đăng nhập |
| Theo tài khoản (DB) | Sai liên tiếp **5** lần → `locked_until = now + 15 phút`, ghi `login_locked`, `failed_login_count` về 0. Đúng → về 0, `locked_until = NULL`. Admin mở khoá bằng `/unlock` (Q5) |
| Phản hồi | Mọi thất bại (không có user, không phải `local`, sai mật khẩu, đang khoá, `disabled`, mật khẩu tạm hết hạn) → **cùng** 403 `{"detail": "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá", "code": "invalid_credentials"}`. Lý do thật chỉ ở `audit_log.details.reason` |
| Thời gian | Luôn chạy đúng **một** lần argon2 verify mỗi request (hash thật hoặc hash giả), kể cả khi user không tồn tại hoặc đang khoá. Test khẳng định bằng đếm số lần gọi, không bằng đồng hồ |
| Thứ tự kiểm | Rate limit → tìm user → verify (luôn) → khoá → status → hết hạn tạm. Kiểm status **sau** verify để kẻ đoán không phân biệt "disabled" với "sai mật khẩu" |
| Ghi | Commit đếm sai và audit **trước** khi ném lỗi (theo mẫu `_deny` hiện có, vì `get_session` sẽ rollback) |

Rủi ro chấp nhận: kẻ biết tên đăng nhập giữ được tài khoản đó trong trạng thái khoá (DoS có giới hạn 15 phút/lượt). Khi web chạy qua tunnel, `client_ip` = `null` ([web] 4.8), bucket theo IP thành bucket chung của container web; lớp theo tài khoản là lớp chính.

### 3.5. Phiên

| Sự kiện | `session_version` | Ghi chú |
|---|---|---|
| Admin đặt lại mật khẩu | `+1` | Mọi phiên của người đó chết ngay |
| Tự đổi mật khẩu | `+1` | Mọi thiết bị khác đăng xuất; web đăng nhập lại ngay bằng mật khẩu mới (4.3) (Q9) |
| Khoá (`status=disabled`) | `+1` | Như CLI `disable` |
| Mở khoá tạm (`unlock`), đổi role | không | Core đọc role mỗi request |

### 3.6. Ép đổi mật khẩu ở core

- `CurrentUser` thêm `auth_provider`, `must_change_password` (đọc trong cùng truy vấn PK, không thêm query).
- Dependency mới `require_password_current` (403 `code="password_change_required"`). `router.py`: `user_router` (JWT) chứa `me.router` (cho phép `GET /me`, `POST /me/password`), và một `active_router = APIRouter(dependencies=[Depends(require_password_current)])` chứa **mọi** router còn lại kể cả `admin`. Test liệt kê mọi route và khẳng định chỉ hai route trên lọt qua.

### 3.7. Không lộ

- Pydantic: trường mật khẩu là `SecretStr`. Không `repr`/log request body.
- `main.py::_NO_ECHO_PREFIXES` thêm `/api/v1/admin`, `/api/v1/me/password` (`/api/v1/auth` đã có, phủ `/auth/login/password`).
- `audit_service._FORBIDDEN_KEYS` đã chặn khoá `password`; thêm `temporary_password`, `password_hash`, `identifier` (identifier gõ sai thường là mật khẩu gõ nhầm ô: chỉ ghi `identifier_sha256[:16]` khi không khớp user nào; khớp user thì ghi `target_id`).
- Grep nghiệm thu ở 6.1.

## 4. API contract (core, prefix `/api/v1`, mọi route cần `X-API-Key`)

Lỗi theo dạng sẵn có `{"detail": str, "code"?: str}` (`services/errors.py`). Phân trang `Page[T] { items, total, limit, offset }` (`schemas/common.py`).

### 4.1. Đăng nhập và tài khoản của tôi

| Method | Path | Xác thực | Request | Response | Lỗi |
|---|---|---|---|---|---|
| POST | `/auth/login/password` | chỉ API key | `PasswordLoginRequest { identifier: str(1..320), password: SecretStr(1..1024), client_ip: str(..45) \| None }`, `extra="forbid"` | 200 `LoginResult` (như `/auth/login`) | 403 `invalid_credentials`; 403 `password_login_disabled` khi `PASSWORD_LOGIN_ENABLED=false` (Q6); 422; 429 |
| POST | `/auth/login` | chỉ API key | không đổi | không đổi | thêm: email khớp tài khoản `local` → 403 `account_mismatch` (audit `reason="provider_local"`). **Bắt buộc**, nếu không Google sẽ gắn `google_sub` vào tài khoản nội bộ trùng email |
| GET | `/me` | JWT | | `MeRead` thêm `auth_provider: AuthProvider`, `username: str \| None`, `must_change_password: bool` | 401 |
| POST | `/me/password` | JWT (được phép khi đang bị ép đổi) | `PasswordChange { current_password: SecretStr(1..1024), new_password: SecretStr(1..1024) }` | 200 `PasswordChanged { session_version: int }` | 409 `not_local_account`; 422 `current_password_invalid` (**không** 401: [web] 3.4 coi 401 là hết phiên); 422 `weak_password`; 429 (Redis `pwchange:<uid>` 5/15 phút, không khoá tài khoản) |

`identifier`: có `@` → so `email` (đã `normalize_email`), không có → so `username` (`lower(strip)`); chỉ trong `auth_provider='local'`.

### 4.2. Quản trị (`/admin`, mọi route `require_permission(user:manage)` + `require_password_current`)

Schema đọc chung:

```
UserAdminRead {
  id, email, username: str|None, name: str|None, role, status, auth_provider,
  must_change_password: bool, locked_until: datetime|None, failed_login_count: int,
  last_login_at, created_at, invited_by: UUID|None,
  aliases: list[AliasRead], is_env_admin: bool   # email thuộc ADMIN_EMAILS: UI khoá nút hạ/khoá
}
AuditRead {
  id, created_at, action: str, actor_user_id, actor_email: str|None,
  target_type, target_id, target_email: str|None, client_ip: str|None, details: dict|None
}
```

| Method | Path | Request | Response | Lỗi | Audit |
|---|---|---|---|---|---|
| GET | `/admin/users` | query `q` (≤ 200, ILIKE email/username/name), `role`, `status`, `auth_provider`, `locked: bool`, `limit` (1..200, mặc định 50), `offset` (0..1e6) | `Page[UserAdminRead]`, sắp `created_at desc, id desc`; aliases nạp `selectin` (không N+1) | 403 | |
| POST | `/admin/users` | `GoogleUserInvite { email, role = member, name? }` | 201 `UserAdminRead` (`invited`) | 409 `email_exists`; 422 | `user_invited {role, via:"api"}` |
| POST | `/admin/users/local` | `LocalUserCreate { username, email, name?, role = member }` | 201 `LocalUserCreated { user: UserAdminRead, temporary_password: str }`, `Cache-Control: no-store` | 409 `email_exists` \| `username_exists`; 422 | `user_created {provider:"local", role}` |
| GET | `/admin/users/{id}` | | `UserAdminRead` | 404 | |
| PATCH | `/admin/users/{id}` | `UserAdminUpdate { role?, status?: "active"\|"disabled", name?, email? (chỉ local), username? (chỉ local) }`, ít nhất một trường | `UserAdminRead` | 409 `self_lockout` (tự hạ role/tự khoá), `last_admin`, `env_admin`, `email_exists`, `username_exists`, `not_local_account` (sửa email/username của Google); 404; 422 | `user_role_changed {from,to}`, `user_status_changed {from,to}`, `user_updated {fields:[...]}` (tên trường, không giá trị cũ của email) |
| POST | `/admin/users/{id}/reset-password` | | 200 `TemporaryPassword { temporary_password }`, `no-store` | 409 `not_local_account`, `self_action` (tự đặt lại → dùng `/me/password`); 404 | `password_reset` |
| POST | `/admin/users/{id}/unlock` | | 204 (`failed_login_count=0`, `locked_until=NULL`) | 404 | `user_unlocked` |
| POST | `/admin/users/{id}/revoke-sessions` | | 204 (`sv+1`) | 404 | `sessions_revoked {via:"api"}` |
| PUT | `/admin/users/{id}/aliases` | `{ aliases: list[{source:"jira", alias: str(1..200)}] }` (≤ 20, thay toàn bộ, không trùng) | `UserAdminRead` | 409 `alias_taken` (detail có email người giữ); 404; 422 | `user_aliases_changed {added, removed}` |
| DELETE | `/admin/users/{id}` | | 204 | 409 `has_data` (còn task/note `owner_id` kể cả trong thùng rác), `self_lockout`, `last_admin`, `env_admin`; 404 | `user_deleted {provider, role}` (ghi trước khi xoá; `target_id` giữ uuid) |
| GET | `/admin/audit-log` | query `action` (`AuditAction`), `actor_user_id`, `target_id`, `since`, `until` (timestamptz), `limit` (1..200, 50), `offset` | `Page[AuditRead]` sắp `created_at desc, id desc`; email nối bằng LEFT JOIN `users` (một truy vấn) | 403; 422 | |

Quy tắc khoá admin (service `user_service`, một nơi, dùng chung API và CLI):

- **Admin hoạt động** = `role='admin' AND status='active'` (khoá tạm `locked_until` và `must_change_password` vẫn tính).
- Thao tác làm giảm số admin hoạt động (hạ role, `disabled`, xoá) chạy dưới `pg_advisory_xact_lock(<hằng>)` rồi đếm lại; còn 0 → 409 `last_admin`. Hai admin hạ quyền nhau cùng lúc không thể cùng thành công.
- Người gọi tự hạ role/tự khoá/tự xoá → 409 `self_lockout` (kiểm trước `last_admin`). Tự thu hồi phiên: **cho phép** (đăng xuất mọi thiết bị của mình; web về `/auth/expired`).
- Email trong `ADMIN_EMAILS` → 409 `env_admin` cho hạ role/khoá/xoá.
- `status="active"` cho tài khoản Google chưa gắn `google_sub` → lưu thành `invited` (như CLI `enable`, không 422; lệch [cha] 4.2, xem 8.2).

### 4.3. Cấu hình core mới

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PASSWORD_LOGIN_ENABLED` | `true` (Q6) | `false` → `/auth/login/password` trả 403 `password_login_disabled` (công tắc khi có sự cố brute-force). Không ảnh hưởng tài khoản Google, CLI, admin API |

Ngưỡng (5 lần, 15 phút, 72 giờ, 10/phút) là hằng trong `core/passwords.py`/`rate_limit.py`, không phải env (Q5).

## 5. Thay đổi Web

Toàn bộ chỉ ở `DATA_SOURCE=api`. Local (`file|memory`): `/admin/*` và `/me/password` hiện `LocalOnlyNotice`, form mật khẩu không hiện ở `/login` (vốn 302 `/`).

### 5.1. Auth.js (`auth.ts`)

- Thêm `Credentials({ id: "credentials", credentials: { identifier: {}, password: {} }, authorize })`. Session vẫn `jwt` (Credentials bắt buộc `jwt`, khớp [web] Q3).
- `authorize(creds, request)`: kiểm kiểu chuỗi, `identifier` 1..320, `password` 1..1024 (không trim mật khẩu); gọi `corePasswordLogin({ identifier, password, client_ip: clientIpFrom(request.headers) })`. 200 → `{ id: uid, uid, sv }`. 403/429/khác → ném lớp con `CredentialsSignin` với `code` ∈ `invalid_credentials | rate_limited | password_login_disabled | unavailable`. Không log `creds`, không gắn mật khẩu vào lỗi.
- `callbacks.signIn({ user, account, profile })`: nhánh `account.provider === "google"` giữ nguyên [web] 4.3 bước 1-3; nhánh `credentials` bỏ bước 1-3 (core đã làm). Cả hai chạy bước 4 (tự kiểm `GET /me`).
- `callbacks.jwt`: **bỏ qua hoàn toàn** `trigger === "update"` (không lấy `uid`/`sv` từ dữ liệu `update()`; client gọi được `POST /api/auth/session` để cập nhật phiên). Test bắt buộc.
- Google provider chỉ khai khi có `AUTH_GOOGLE_ID`/`AUTH_GOOGLE_SECRET` (Q6). `lib/auth-config.ts`: hai biến này thành tuỳ chọn; trả thêm `googleEnabled`, `passwordEnabled` (`PASSWORD_LOGIN_ENABLED !== "false"`); cả hai tắt → lỗi cấu hình.

### 5.2. `lib/api.ts`

- `corePasswordLogin(body)`: như `coreLogin` (thẳng `coreFetchRaw`, không Bearer, không cache), chỉ gọi trong `auth.ts`.
- `changeMyPasswordApi`, `listAdminUsersApi(params)`, `getAdminUserApi`, `inviteGoogleUserApi`, `createLocalUserApi`, `updateAdminUserApi`, `resetUserPasswordApi`, `unlockUserApi`, `revokeUserSessionsApi`, `setUserAliasesApi`, `deleteUserApi`, `listAuditLogApi(params)`.
- `UNCACHED_PREFIXES` thêm `/api/v1/admin` (Q8): dữ liệu PII, hai admin thao tác cùng lúc cần thấy ngay, lưu lượng thấp. Mutation vẫn xoá toàn bộ `core-cache` như [web] 4.5.
- `CoreApiError.code` mới cần map: `password_change_required` (3.4 của [web] thêm một dòng, xem 8.1), `invalid_credentials`, `weak_password`, `current_password_invalid`, `self_lockout`, `last_admin`, `env_admin`, `self_action`, `not_local_account`, `email_exists`, `username_exists`, `alias_taken`, `has_data`.

### 5.3. Route, trang, component

| Route / file | Nội dung |
|---|---|
| `app/login/page.tsx` | Thêm form "Tên đăng nhập hoặc email" + "Mật khẩu" (`autocomplete="username"` / `"current-password"`) dưới nút Google, ngăn bằng "hoặc". Ẩn phần tắt theo `googleEnabled`/`passwordEnabled`. Vẫn **không** gọi core. Map `error`: `invalid_credentials` → "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá. Thử lại sau ít phút hoặc liên hệ quản trị viên."; `rate_limited`, `password_login_disabled`, `unavailable` có câu riêng |
| `app/login/actions.ts` | Thêm `passwordSignInAction(prev, formData)` (miễn trừ guard như action Google). Dùng `useActionState` ở client để giữ `pending`, không mất ô `identifier` khi lỗi. Gọi `signIn("credentials", { identifier, password, redirectTo: safeCallbackPath(cb) })`; bắt `AuthError` → trả `{ error: code }`; **ném lại** lỗi redirect của Next (`isRedirectError`), nuốt nó là đăng nhập thành công mà không chuyển trang |
| `app/me/password/page.tsx` (mới) | Đổi mật khẩu tự nguyện; chỉ tài khoản `local` (Google → thông báo "đổi ở Google") |
| `app/me/actions.ts` (mới) | `changeMyPasswordAction`: `requireSession()` đầu tiên → `changeMyPasswordApi` → thành công thì `signIn("credentials", { identifier: me.username, password: new, redirectTo: "/" })` (phiên mới mang `sv` mới; các thiết bị khác chết) |
| `components/change-password-form.tsx` (mới, client) | Ba ô (`autocomplete="current-password"`, `"new-password"` x2), đếm ký tự/gợi ý ≥ 12, khớp xác nhận ở client; lỗi `weak_password` hiện danh sách lý do từ core |
| `app/layout.tsx` | `me.must_change_password` → render `ChangePasswordRequired` (bọc `change-password-form`, kèm nút Đăng xuất) **thay cho** `children`, nav tối thiểu. Không cần biết pathname, không cần middleware gọi core. Lớp chặn thật là core 3.6 |
| `app/admin/users/page.tsx` (mới) | Xem 5.4 |
| `app/admin/users/loading.tsx`, `app/admin/audit/loading.tsx` (mới) | Skeleton bảng |
| `app/admin/audit/page.tsx` (mới) | Bảng nhật ký, lọc `action`, `actor`, `target`, khoảng ngày trong URL; `?page=` 50/trang; "Trang x / y", "Tổng: n". `details` render bằng text node (JSON `pre`), không `dangerouslySetInnerHTML` |
| `app/admin/actions.ts` (mới) | 5.5 |
| `components/admin/user-table.tsx` (client), `user-filters.tsx` (client), `create-user-dialog.tsx` (client, hai tab Google/Nội bộ), `temp-password-reveal.tsx` (client), `alias-editor.tsx` (client), `audit-table.tsx` (server), `pagination-bar.tsx` (dùng lại nếu đã có) | |
| `lib/nav.ts` | `ADMIN_NAV`: `/admin/users` "Người dùng" (icon `UserCog`), `/admin/audit` "Nhật ký" (icon `ScrollText`), cả hai `permission: "user:manage"` |
| `components/main-nav.tsx` | Section "Quản trị" chỉ render khi có ít nhất một mục được phép (lọc theo prop `permissions` của [web] 4.11) |
| `components/user-menu.tsx` | Mục "Đổi mật khẩu" khi `me.auth_provider === "local"` |

### 5.4. `/admin/users` và hiệu năng ([web] 4.12)

- Trang: `const me = await getMe()` (đã dedupe bằng `React.cache` với layout, không thêm request); thiếu `user:manage` → `ForbiddenPanel`, **không** gọi `/admin/*`. Có quyền → `Promise.all([listAdminUsersApi(params), getAssigneesApi()])` (gợi ý alias; `getAssigneesApi` qua cache `uid:sv`). Tổng: 1 lời gọi `/admin/users` + 1 `assignees` (cache) + `/me` sẵn có.
- Bọc bảng trong `<Suspense key={searchParams} fallback={<TableSkeleton/>}>`; tiêu đề, nút "Thêm người dùng", bộ lọc hiện ngay.
- Bộ lọc `q` (debounce 300 ms), `role`, `status`, `auth_provider`, `locked` ghi vào URL bằng `router.replace` trong `startTransition` (bảng cũ mờ đi, không trắng trang). Đổi bộ lọc về `page=1`. Phân trang server-side `?page=` 50/trang, giữ mọi bộ lọc.
- Mỗi dòng: role (select), khoá/mở, mở khoá tạm (khi `locked_until > now`), thu hồi phiên, đặt lại mật khẩu (chỉ `local`), alias, xoá, link "Nhật ký" → `/admin/audit?target=<id>`. Không gọi `GET /admin/users/{id}`: mọi dữ liệu có sẵn trong dòng.
- `useOptimistic` + `useTransition` cho đổi role, khoá/mở, mở khoá tạm, thu hồi phiên, alias: UI đổi ngay, rollback và toast khi action lỗi (gồm `self_lockout`, `last_admin`, `env_admin`, `forbidden`, `session_expired` → `/auth/expired`, `password_change_required` → tải lại). Nút khoá trong lúc `pending`. Tạo user, đặt lại mật khẩu, xoá: **không** optimistic (cần kết quả server); xoá và khoá có hộp xác nhận.
- UI chặn sớm: dòng của chính mình và dòng `is_env_admin` khoá nút hạ role/khoá/xoá (core vẫn quyết định).
- Mật khẩu tạm: action trả `{ ok: true, temporaryPassword }` cho client component; `temp-password-reveal` hiện trong dialog với `CopyButton`, cảnh báo "Chỉ hiện một lần", nút "Tôi đã lưu" xoá state. **Không** đưa vào URL, `searchParams`, `localStorage`, toast, `console`, Server Component (không vào RSC payload/route cache). Đóng dialog hay rời trang là mất.
- Sau mỗi mutation: `revalidatePath("/admin/users")` (không `router.refresh()` toàn trang).

### 5.5. Server Action (`app/admin/actions.ts`)

Mọi hàm câu lệnh đầu tiên `const auth = await requirePermission("user:manage");` (khớp test tĩnh [web] 4.7, không thêm miễn trừ). Kiểu trả về `{ ok: true, ... } | { ok: false, code?, error }`.

| Action | Kiểm input trước khi gọi core | Core |
|---|---|---|
| `inviteGoogleUserAction(formData)` | email ≤ 320 có `@`; role ∈ 3 giá trị; name ≤ 200 | `POST /admin/users` |
| `createLocalUserAction(formData)` | username khớp regex 2.1 (sau `toLowerCase`); email như trên; role; name | `POST /admin/users/local` → trả `temporaryPassword` |
| `updateUserAction(id, patch)` | `id` UUID; trường thuộc danh sách cho phép | `PATCH` |
| `resetPasswordAction(id)` | UUID | `POST .../reset-password` → `temporaryPassword` |
| `unlockUserAction(id)`, `revokeSessionsAction(id)`, `deleteUserAction(id)` | UUID | tương ứng |
| `setAliasesAction(id, aliases)` | ≤ 20, mỗi alias trim 1..200, không ký tự điều khiển, không trùng | `PUT .../aliases` |

`app/me/actions.ts::changeMyPasswordAction`: `requireSession()`; mật khẩu không trim, ≤ 1024.

## 6. Ownership

Không agent nào sửa file của agent khác. Web của spec này chạy **sau** khi frontend-dev xong P1-web và P2-web của [web] (cùng chạm `auth.ts`, `/login`, layout, nav, `lib/api.ts`), nên không có hai agent cùng sửa một file.

- **backend-dev** (`apps/core/**`, `scripts/smoke-test.sh`):
  - `pyproject.toml`, `uv.lock` (`argon2-cffi`)
  - `app/models/user.py`, `app/models/enums.py`
  - `migrations/versions/<rev>_add_local_password_login.py` (mới)
  - `app/core/passwords.py` (mới), `app/core/data/common-passwords.txt` (mới, ghi nguồn + giấy phép ở dòng đầu file hoặc README kèm), `app/core/auth.py`, `app/core/rate_limit.py`, `app/core/config.py`
  - `app/api/v1/auth.py`, `app/api/v1/me.py`, `app/api/v1/admin.py` (mới), `app/api/v1/router.py`, `app/api/deps.py`, `app/main.py` (`_NO_ECHO_PREFIXES`)
  - `app/schemas/auth.py`, `app/schemas/user.py`, `app/schemas/admin.py` (mới)
  - `app/services/auth_service.py`, `app/services/user_service.py`, `app/services/audit_service.py` (thêm hàm **đọc** `list_entries`, khoá cấm mới)
  - `app/cli/auth.py`
  - `tests/conftest.py`, `tests/test_auth.py`, `tests/test_passwords_unit.py` (mới), `tests/test_password_login.py` (mới), `tests/test_admin_users.py` (mới), `tests/test_admin_audit.py` (mới), `tests/test_cli_auth.py` (mới hoặc sửa nếu có)
- **frontend-dev** (`apps/web/**` trừ `lib/generated/**`, `lib/docs.ts`):
  - `auth.ts`, `lib/auth-config.ts`, `lib/api.ts`, `lib/types.ts`, `lib/nav.ts`, `lib/core-errors.ts` (nếu map `code` nằm ở đây)
  - `app/login/page.tsx`, `app/login/actions.ts`, `app/layout.tsx`, `app/me/password/page.tsx` (mới), `app/me/actions.ts` (mới)
  - `app/admin/users/page.tsx`, `app/admin/users/loading.tsx`, `app/admin/audit/page.tsx`, `app/admin/audit/loading.tsx`, `app/admin/actions.ts` (đều mới)
  - `components/main-nav.tsx`, `components/user-menu.tsx`, `components/change-password-form.tsx` (mới), `components/admin/*` (mới)
  - `tests/auth-callbacks.test.ts` (mới), `tests/login-actions.test.ts` (mới), `tests/admin-actions.test.ts` (mới); test tĩnh guard của [web] tự phủ file action mới
- **orchestrator:** `apps/web/lib/generated/openapi.d.ts` (`make gen-types` sau P1-be), `Makefile` (`auth-create-local`, `auth-reset-password`, `auth-unlock`), `.env.example`, `docker-compose.yml`/`docker-compose.prod.yml` (`PASSWORD_LOGIN_ENABLED` cho `api` và `web`), docs mục 7.4.
- **Không ai sửa:** `docs/specs/auth-multiuser.md`, `docs/specs/web-authjs-login.md`, `lib/store/**`, `lib/task-scope.ts`, `data/**`.

### 6.1. CLI (`app/cli/auth.py`, dùng chung `user_service`)

| Lệnh | Hành vi |
|---|---|
| `create-local --username u --email e [--role] [--name]` | Gọi cùng `user_service.create_local_user` như API; in mật khẩu tạm **một lần** ra stdout; audit `via:"cli"`. Đường phá kính khi không cấu hình Google |
| `reset-password --email e \| --username u` | `user_service.reset_password`; in mật khẩu tạm một lần |
| `unlock --email e \| --username u` | `user_service.unlock` |
| `enable` | Sửa: `local` → `active`; `google` giữ quy tắc cũ (`active` nếu có sub, ngược lại `invited`) |
| `disable`, `revoke`, `alias`, `invite`, `token`, `bootstrap` | Giữ; chuyển sang gọi hàm service dùng chung (`set_status`, `revoke_sessions`) để CLI và API cùng ghi audit giống nhau. `token`: sửa câu báo lỗi "đăng nhập Google" thành theo `auth_provider` |

CLI **không** đi qua `last_admin`/`self_lockout` (người có shell là chủ máy), nhưng in CẢNH BÁO khi thao tác làm còn 0 admin hoạt động.

## 7. Tiêu chí nghiệm thu (kiểm chứng được)

`TEST_DATABASE_URL` trỏ DB `_test`; test `db` bị skip không tính là pass.

### 7.1. Backend

- [ ] `cd apps/core && uv run ruff check app migrations tests && uv run ruff format --check app migrations tests` → exit 0.
- [ ] `uv run alembic heads` → một head, migration mới có `down_revision = "e8a3c6f2b1d7"`. `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check` → exit 0. Downgrade khi có một user `local` active → không lỗi, user đó thành `disabled`.
- [ ] `uv run pytest -q` toàn bộ pass, gồm:
  - `test_passwords_unit.py`: hash bắt đầu `$argon2id$v=19$m=65536,t=3,p=4$`; hai lần băm cùng mật khẩu khác nhau; chính sách từ chối 11 ký tự, 129 ký tự, `password1234` (danh sách phổ biến), mật khẩu chứa username, ký tự `\x00`; nhận 12 ký tự tiếng Việt có dấu cách; mật khẩu tạm 16 ký tự đúng bảng chữ.
  - `test_password_login.py`: đúng → 200 `LoginResult`, `audit_log` có `login_success` `details.method="password"`; sai → 403 `invalid_credentials`; identifier không tồn tại → 403 cùng `detail`/`code` và `verify` được gọi đúng 1 lần (mock đếm); 5 lần sai → lần 6 với mật khẩu **đúng** vẫn 403, có `login_locked`; `/unlock` → 200; user `disabled` + mật khẩu đúng → 403 cùng thông báo; mật khẩu tạm quá 72 giờ (sửa `password_changed_at`) → 403; email của user `local` đăng nhập qua `/auth/login` (Google) → 403 `account_mismatch`, `google_sub` vẫn NULL; `PASSWORD_LOGIN_ENABLED=false` → 403 `password_login_disabled`; 11 request/phút cùng identifier → 429; `audit_log.details` không bao giờ có khoá `password`, `identifier` hay giá trị mật khẩu (quét mọi dòng sau test).
  - `must_change_password=true`: `GET /me` 200 (có `must_change_password: true`), `POST /me/password` 200, **mọi** route khác 403 `password_change_required` (test duyệt `app.routes`, trừ `/health/*`, `/auth/*`, `/me`, `/me/password`); đổi xong → JWT cũ (sv cũ) 401 `user_inactive`, JWT với `sv` mới 200 và route khác 200.
  - `/me/password`: sai mật khẩu hiện tại → 422 `current_password_invalid` (không phải 401); mật khẩu mới yếu → 422 `weak_password`; tài khoản Google → 409 `not_local_account`.
  - `test_admin_users.py`: member/lead gọi mọi `/admin/*` → 403; 120 user → `limit=50` trả 50, `total=120`, `offset=100` trả 20; lọc `q`, `role`, `status`, `auth_provider`, `locked`; tạo local → 201 có `temporary_password`, header `Cache-Control: no-store`, `GET` sau đó không có field mật khẩu/hash nào (kiểm key của JSON); đăng nhập bằng mật khẩu tạm được; trùng email/username → 409; tự hạ role → 409 `self_lockout`; hạ admin hoạt động cuối (người khác) → 409 `last_admin`; hai request hạ quyền chéo chạy đồng thời (`asyncio.gather`) → đúng một thành công; email `ADMIN_EMAILS` → 409 `env_admin`; reset mật khẩu → `sv+1`, JWT cũ 401; reset cho Google → 409 `not_local_account`; reset chính mình → 409 `self_action`; xoá user có task (kể cả trong thùng rác) → 409 `has_data`; alias trùng → 409 `alias_taken`; mỗi thao tác ghi đúng một dòng audit với action ở bảng 4.2.
  - `test_admin_audit.py`: lọc theo `action`, `actor_user_id`, `target_id`, `since/until`; `actor_email` có giá trị, NULL sau khi actor bị xoá; sắp giảm dần.
  - `test_cli_auth.py`: `create-local` in đúng 1 dòng mật khẩu, tạo được đăng nhập; `enable` user local → `active`; `reset-password`, `unlock` ghi audit `via:"cli"`.
- [ ] `grep -rnE "log(ger)?\.(debug|info|warning|error|exception)\(.*(password|temporary_password|password_hash)" apps/core/app` → rỗng.
- [ ] `make smoke` pass, có assertion mới: tạo user local qua CLI, đăng nhập `/auth/login/password` → 200; route bất kỳ với token của user đó → 403 `password_change_required`; đổi mật khẩu → route đó 200; dọn user tạm.

### 7.2. Types (orchestrator)

- [ ] `openapi.d.ts` có `PasswordLoginRequest`, `PasswordChange`, `UserAdminRead`, `LocalUserCreated`, `AuditRead`, `MeRead.must_change_password`; `grep -n "password_hash" apps/web/lib/generated/openapi.d.ts` → rỗng.

### 7.3. Web

- [ ] `cd apps/web && npx tsc --noEmit` → exit 0; `npm run lint` → exit 0; `npm test` → exit 0 gồm:
  - `jwt` callback với `trigger: "update", session: { uid: "<khác>", sv: 99 }` → token giữ nguyên `uid`, `sv`.
  - `authorize`: core 403 → ném `CredentialsSignin` có `code="invalid_credentials"`; core 200 → `{ uid, sv }`; mật khẩu > 1024 ký tự → không gọi core.
  - `passwordSignInAction`: lỗi redirect của Next được ném lại; `AuthError` → `{ error }`.
  - Test tĩnh guard [web] 4.7 phủ `app/admin/actions.ts`, `app/me/actions.ts` (không thêm miễn trừ).
- [ ] `grep -rnE "console\.(log|error|warn)\(.*(password|temporaryPassword|formData)" apps/web/app apps/web/lib apps/web/components apps/web/auth.ts` → rỗng.
- [ ] `grep -rn "temporaryPassword" apps/web/app --include=page.tsx` → rỗng (không render ở Server Component).

### 7.4. Kịch bản tay (SSH tunnel, `DATA_SOURCE=api`)

1. Admin A vào `/admin/users` → bảng, "Trang 1 / n", "Tổng: m"; member B mở `/admin/users` → "Không đủ quyền", nav không có mục Quản trị; `make logs-api` không có request `/api/v1/admin` của B.
2. A tạo user nội bộ `c.nguyen` → dialog hiện mật khẩu tạm một lần; đóng dialog, tải lại trang → không còn cách xem lại. `docker compose logs api web | grep -F "<mật khẩu tạm>"` → rỗng.
3. Cửa sổ ẩn danh: đăng nhập `c.nguyen` + mật khẩu tạm → chỉ thấy form đổi mật khẩu ở mọi URL (`/tasks`, `/team`); đổi xong → vào `/`, dữ liệu hiện bình thường.
4. Sai mật khẩu 5 lần → lần 6 đúng vẫn báo lỗi chung; A thấy dòng có nhãn "Đang khoá tạm", bấm "Mở khoá" → C đăng nhập được. `/admin/audit` có `login_denied`, `login_locked`, `user_unlocked`.
5. A "Đặt lại mật khẩu" cho C đang đăng nhập → C bấm trang bất kỳ → `/login?error=session`.
6. A hạ role chính mình → toast "Không thể tự hạ quyền", UI quay lại role cũ; khoá admin cuối cùng khác → "Phải còn ít nhất một quản trị viên".
7. Đổi role B thành lead → B tải lại trang thấy menu Team (không cần đăng nhập lại).
8. `make logs-api` khi mở `/admin/users` lần đầu: đúng 1 `GET /api/v1/admin/users` + `GET /api/v1/me` + tối đa 1 `GET /api/v1/tasks/assignees`; đổi bộ lọc: 1 request `/admin/users`.
9. Đặt `PASSWORD_LOGIN_ENABLED=false` (core và web) → form mật khẩu biến mất ở `/login`, Google vẫn dùng được.
10. Google với email trùng user nội bộ → "chưa được cấp quyền", `audit_log` `reason=account_mismatch`, `details.provider="local"`.

### 7.5. Review

`db-reviewer` (migration, CHECK thay thế, downgrade), `code-reviewer`, **`security-auditor`** (bắt buộc: băm, brute-force, liệt kê tài khoản, Credentials provider, `jwt` callback `update`, Server Action admin, mật khẩu tạm).

### 7.6. Docs (orchestrator, khi code xong)

- `docs/GOOGLE_OAUTH_SETUP.md`: Google là một trong hai cách; mục 6 "menu Quản trị" thành thật; mục 7 "Admin thêm email ở trang Quản trị → Người dùng"; thêm `PASSWORD_LOGIN_ENABLED`; nếu chỉ dùng tài khoản nội bộ thì không cần mục 2-5.
- `docs/API_REFERENCE.md`: 4.1, 4.2, CLI 6.1.
- `docs/AI_HANDOFF_STATE.md`: trạng thái P3, tài khoản nội bộ.
- `.agents/rules/web-conventions.md`: mật khẩu tạm không bao giờ qua Server Component/URL; `/api/v1/admin` không cache; `jwt` callback bỏ qua `update`; sửa câu "Nav là phẳng, không dropdown" cho khớp `main-nav.tsx` (Phụ lục A5).
- `.agents/rules/backend-conventions.md`: mọi route mới mặc định nằm trong `active_router` (ép đổi mật khẩu); chỉ `user_service` được đổi role/status/xoá user.
- `docs/PROXMOX_DEPLOY.md`: biến mới, runbook phá kính `make auth-create-local ROLE=admin`.
- `apps/web/lib/docs.ts`: không đăng ký spec trong `docs/specs/` (như [web] 9).

## 8. Thay đổi so với spec đã chốt

### 8.1. So với `web-authjs-login.md` [web]

| # | Mục [web] | Đã chốt | Spec này | Khuyến nghị |
|---|---|---|---|---|
| W1 | 1.3, 4.3 | Chỉ provider Google | Thêm Credentials; `signIn` rẽ nhánh theo `account.provider` | Chấp nhận. Bước 4 (tự kiểm `/me`) giữ cho cả hai |
| W2 | 4.3 | `callbacks.jwt` chỉ chép `uid, sv` lúc đăng nhập | Thêm: bỏ qua `trigger === "update"` | **Nên áp ngay cả khi không làm spec này** (đóng đường client sửa phiên). Báo frontend-dev đang làm [web] |
| W3 | 4.2, `lib/auth-config.ts` | `AUTH_GOOGLE_ID/SECRET` bắt buộc | Tuỳ chọn khi có đăng nhập mật khẩu; thêm `PASSWORD_LOGIN_ENABLED` | Q6 |
| W4 | 3.4 | Bảng lỗi không có `password_change_required` | Thêm dòng: Server Component → layout đã thay bằng form đổi mật khẩu; Server Action → `{ ok:false, code:"password_change_required" }`, client `router.refresh()` | Chấp nhận |
| W5 | 4.5 | `UNCACHED_PREFIXES` = `/integrations`, `/me` | Thêm `/api/v1/admin` | Q8 |
| W6 | 4.11 `/login` | Chỉ nút Google | Thêm form mật khẩu, mã lỗi mới | Chấp nhận |
| W7 | 4.11 `/me` | Hồ sơ chỉ đọc | Thêm link "Đổi mật khẩu" (local) | Chấp nhận |
| W8 | Q9 | Đăng xuất chỉ xoá cookie | Không đổi. Tự đổi mật khẩu thì `sv+1` (đăng xuất thiết bị khác) | Q9 |
| W9 | Q2 | Web ký JWT | Giữ nguyên (1.4) | Không xung đột |
| W10 | 4.4 middleware | Không gọi core | Giữ; ép đổi mật khẩu làm ở layout + core | Không xung đột |
| W11 | 1.3 | Trang admin out-of-scope | Spec này làm | Không xung đột |

### 8.2. So với `auth-multiuser.md` [cha]

| # | Mục [cha] | Đã chốt | Spec này |
|---|---|---|---|
| M1 | 1.4 | "IdP khác Google, mật khẩu, 2FA" out-of-scope | Mật khẩu vào scope theo yêu cầu mới của User; 2FA vẫn ngoài |
| M2 | 2.1 | `ck_users_active_has_sub` | Thay bản cho phép `local` |
| M3 | 2.4 | `AuditAction` ban đầu | Thêm 6 giá trị (2.2) |
| M4 | 4.2 PATCH | 422 khi `status=active` mà chưa có `google_sub` | Lưu thành `invited` (như CLI `enable`) |
| M5 | 4.2 DELETE | Chỉ user `invited` chưa có dữ liệu | Mọi user không còn task/note, không phải mình, không phải admin cuối/`ADMIN_EMAILS` (Q7) |
| M6 | 4.2 | Không có `/admin/users/local`, `/reset-password`, `/unlock` | Thêm |
| M7 | 6 threat model | "Dò email đã mời" chỉ qua `/auth/login` | Thêm chống liệt kê ở đăng nhập mật khẩu (3.4) |

## 9. Rủi ro & câu hỏi cần User chốt

### 9.1. Câu hỏi (kèm khuyến nghị)

| # | Câu hỏi | Khuyến nghị |
|---|---|---|
| Q1 | Tài khoản nội bộ có bắt buộc email? Đăng nhập bằng gì? | **Email bắt buộc** (giữ `NOT NULL`, không phải sửa `MeRead.email`, audit, invite), `username` bắt buộc, đăng nhập bằng username **hoặc** email. Thay thế: email tuỳ chọn → phải đổi `email` thành NULL được và mọi chỗ đọc email (`MeRead`, `CurrentUser`, `login_denied`, web) |
| Q2 | Mật khẩu tạm do core sinh hay admin tự gõ? | **Core sinh** (16 ký tự, ~92 bit), hiện một lần. Admin gõ thì dễ đặt yếu/đặt giống nhau cho nhiều người |
| Q3 | Một tài khoản chỉ một cách đăng nhập? | **Có.** Gắn Google vào tài khoản nội bộ (hoặc ngược lại) để epic sau; hiện muốn chuyển thì tạo tài khoản mới (dữ liệu không chuyển chủ) |
| Q4 | Chính sách mật khẩu | **12-128 ký tự, chặn ~10k mật khẩu phổ biến và chuỗi chứa username, không bắt ký tự đặc biệt** (NIST 800-63B) |
| Q5 | Ngưỡng khoá và hạn mật khẩu tạm | **5 lần sai → khoá 15 phút**, admin mở khoá được; **mật khẩu tạm hết hạn 72 giờ**. Hằng trong code, không env |
| Q6 | Google thành tuỳ chọn + công tắc `PASSWORD_LOGIN_ENABLED`? | **Có cả hai.** Mặc định bật mật khẩu; Google tắt khi thiếu biến; cả hai tắt → lỗi cấu hình |
| Q7 | Xoá user | **Không có xoá mềm**; "Khoá" là cách chính. Xoá cứng chỉ khi user không còn task/note (kể cả thùng rác) |
| Q8 | `/admin/*` có qua cache 10 giây `uid:sv`? | **Không cache** (PII, cần tươi giữa nhiều admin, ít truy cập) |
| Q9 | Tự đổi mật khẩu có đăng xuất các thiết bị khác? | **Có** (`sv+1`), web đăng nhập lại ngay bằng mật khẩu mới để thiết bị hiện tại không bị đá ra |
| Q10 | Admin được đặt lại mật khẩu của admin khác? | **Có**, có audit. Không tự đặt lại cho mình qua API admin (`self_action`) |
| Q11 | Tài khoản nội bộ được làm admin? | **Có** (cần cho triển khai không có Google). UI cảnh báo "tài khoản nội bộ không có 2FA" khi chọn role admin |
| Q12 | 2FA (TOTP) cho tài khoản nội bộ? | **Không ở đợt này.** Đề xuất epic sau nếu dùng tài khoản nội bộ cho admin lâu dài |
| Q13 | Chấp nhận giới hạn theo IP gần như vô hiệu khi chạy qua tunnel (`client_ip=null`)? | **Chấp nhận** giai đoạn đầu; lớp chính là khoá theo tài khoản + bucket theo identifier. Bật `TRUST_FORWARDED_FOR` khi có Caddy |

### 9.2. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Google gắn `google_sub` vào tài khoản nội bộ trùng email (chiếm tài khoản) | `/auth/login` từ chối khi `auth_provider='local'` + CHECK `ck_users_local_no_sub` + test |
| Brute-force/đoán mật khẩu | argon2id, 3 bucket Redis, khoá 5/15', chặn mật khẩu phổ biến, công tắc tắt |
| Liệt kê tài khoản qua thông báo/thời gian | Một thông báo, luôn một lần verify, test đếm lời gọi |
| DoS bằng khoá tài khoản người khác | Khoá tạm 15', admin mở khoá; chấp nhận |
| DoS CPU/RAM bằng argon2 | Semaphore 4, giới hạn độ dài 1024, rate limit trước khi băm |
| Lộ mật khẩu tạm | Chỉ trong body response `no-store` → state client; không log/URL/RSC; test grep |
| Lộ mật khẩu qua log/422 | `SecretStr`, `_NO_ECHO_PREFIXES`, khoá cấm trong audit, grep |
| Client sửa phiên qua `update()` của Auth.js | `jwt` callback bỏ qua `trigger === "update"` + test (W2) |
| Quên route mới khỏi `active_router` (bỏ qua ép đổi mật khẩu) | Mặc định đặt trong `active_router`; test duyệt `app.routes` |
| Khoá hết admin | `self_lockout`, `last_admin` dưới advisory lock, `ADMIN_EMAILS`, CLI `create-local ROLE=admin` |
| Tài khoản nội bộ admin không có 2FA | Q11, Q12; khuyến nghị admin chính dùng Google |
| Đổi `openapi.d.ts` khi frontend-dev đang làm [web] | Sinh types sau khi [web] P2-web merge (mục 9.3) |

### 9.3. Thứ tự pha

| Pha | Nội dung | Ai | Song song? | Xong khi |
|---|---|---|---|---|
| P0 | User chốt Q1-Q13; báo frontend-dev đang làm [web] áp W2 | User, orchestrator | | |
| P1-be | Migration, `passwords.py`, `/auth/login/password`, `/me/password`, ép đổi mật khẩu, `/admin/*`, CLI, test, smoke | backend-dev | **Song song** với [web] P1/P2-web (file khác tầng) | 7.1 |
| P1-review | `db-reviewer`, `code-reviewer`, `security-auditor` cho backend | orchestrator gọi | | Không còn critical/high |
| P1-deploy | Có thể lên staging **một mình**: cột mới mặc định `google`, endpoint mới chưa ai gọi, `MeRead` chỉ thêm field | orchestrator | | `make migrate`, `make smoke` |
| P2-types | `make gen-types`, commit `openapi.d.ts`; Makefile `auth-create-local/reset-password/unlock`; env | orchestrator | Sau khi [web] P2-web merge | 7.2 |
| P3-web-a | Credentials, `/login` form, `/me/password`, ép đổi ở layout, `auth-config` | frontend-dev | Nối tiếp [web], **không** song song với nó | 7.3, kịch bản 3, 5, 9, 10 |
| P3-web-b | `/admin/users`, `/admin/audit`, `app/admin/actions.ts`, nav | frontend-dev (cùng worktree, sau P3-web-a) | | 7.3, kịch bản 1, 2, 4, 6-8 |
| P4-review | `code-reviewer` rồi `security-auditor` cho web | orchestrator gọi | | |
| P5-docs | 7.6 | orchestrator | | |

## Phụ lục A. Lệch giữa tài liệu và code thật

| # | Tài liệu nói | Code thật | Xử lý |
|---|---|---|---|
| A1 | [cha] 1.4: mật khẩu out-of-scope | Yêu cầu mới của User | Mục 8.2 M1 |
| A2 | `GOOGLE_OAUTH_SETUP.md` mục 6-7: "có menu Quản trị", "Admin thêm email ở trang Quản trị"; mục 4 "`IMPORT_COMMIT_SECRET` sẽ bị bỏ" | Chưa có trang/API admin; biến đã bỏ (`main.py` chỉ cảnh báo) | 7.6 |
| A3 | `user_service.py` docstring: "múi giờ", "P1 chỉ có phần CLI cần" | Múi giờ theo user đã gỡ | backend-dev sửa docstring khi thêm hàm admin |
| A4 | CLI `enable`: `ACTIVE if google_sub else INVITED` | Sai với tài khoản `local` (sẽ thành `invited`, vi phạm CHECK mới) | 6.1 |
| A5 | `web-conventions.md`: "Nav là phẳng, không dropdown — đừng thêm lại menu bấm mới mở" | `main-nav.tsx` đã có `CollapsibleSection` bấm mở/đóng | 7.6: orchestrator sửa rule cho khớp code, hoặc User quyết định bỏ collapsible |
| A6 | [cha] 4.2 PATCH: 422 khi active mà chưa có `google_sub` | CLI `enable` lưu `invited` | M4 |
| A7 | [cha] dòng 8: migration của epic có `down_revision = "a1c9e4b7d2f8"` | Head hiện tại `e8a3c6f2b1d7` (add_tasks_reporter, sau `b2f7a9c1d4e6` add_users_and_ownership) | 2.1 |
| A8 | [web] 4.2: `AUTH_GOOGLE_ID/SECRET` bắt buộc | `lib/auth-config.ts` đã code bắt buộc | W3, Q6 |
| A9 | `audit_service.py`: "CHỈ INSERT: không có hàm sửa hay xoá" | Chưa có hàm đọc | Thêm `list_entries` (đọc), vẫn không sửa/xoá |
| A10 | `api/v1/auth.py`: "IP browser do web chuyển (Caddy ghi đè X-Forwarded-For)" | [web] Q8 `TRUST_FORWARDED_FOR=false` mặc định → `client_ip` thường `null`, bucket IP là IP container web | Q13 |
| A11 | [cha] 3.5/5.4: trang `/admin/audit`; [cha] 4.2: API `/admin/audit-log` | Chưa có cả hai | Giữ hai tên như [cha] |
| A12 | `models/user.py` docstring: "Người dùng đăng nhập bằng Google", `active_has_sub` "không có đường active mà không qua Google" | Sẽ sai sau spec này | backend-dev sửa docstring/comment cùng migration |

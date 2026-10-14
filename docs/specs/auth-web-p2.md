# Spec: Đăng nhập đa người dùng, pha P2 (Web)

- Trạng thái: **DRAFT** (chờ User duyệt các câu hỏi ở mục 7.1)
- Tác giả: architect
- Ngày: 2026-10-13
- Nhánh lúc viết: `feat/auth-multiuser` (HEAD `5484441`, sạch)
- Spec cha (CHỐT): `docs/specs/auth-multiuser.md`. Spec này **chi tiết hoá** mục 5, 8.2, 9.3 của spec cha cho phần web, chốt các điểm spec cha để ngỏ (rào cache, rate limit, `client_ip`, chế độ file) và liệt kê các chỗ code web còn lệch với core đã làm xong. Chỗ nào spec này im lặng thì theo spec cha.
- Đã đối chiếu với code thật: `apps/core/app/core/auth.py`, `api/v1/auth.py`, `api/v1/me.py`, `api/v1/router.py`, `core/permissions.py`, `core/rate_limit.py`; `apps/web/lib/api.ts`, `lib/core-cache.ts`, `lib/excel-upsert.ts`, `app/*actions*.ts`, `app/api/export/route.ts`, `app/layout.tsx`, `lib/nav.ts`, `lib/vault/store.ts`, `package.json` (lock: `next@15.5.25`).

## 1. Bối cảnh & phạm vi

### 1.1. Vấn đề

Core (P1) đã đòi `Authorization: Bearer <JWT HS256 60s>` cho mọi `/api/v1/*` trừ `POST /auth/login`. Web chưa có Auth.js, chưa ký JWT, nên ở `DATA_SOURCE=api` mọi trang nhận 401 từ core. Ngoài ra web còn gọi các endpoint core **đã gỡ** (lệch code thật, xem 1.4), và cache GET dùng chung (`lib/core-cache.ts`) khoá chỉ theo path, sẽ trả dữ liệu của A cho B ngay khi web gửi JWT từng người nếu không xử lý.

### 1.2. In-scope

1. Auth.js v5 (Google OIDC, gợi ý `hd`, invite-only qua core), `middleware.ts`, trang `/login`, `/auth/expired`, trang lỗi cấu hình.
2. Web ký JWT ngắn hạn theo từng người và gắn vào `coreFetch` (một chỗ duy nhất).
3. Rào cache dùng chung: chốt phương án và có test khoá hành vi.
4. Gửi `client_ip` cho `POST /auth/login`.
5. Gỡ mọi lời gọi endpoint/header đã gỡ ở core: `/settings/current-users`, `/settings/display-timezone`, `/import/verify-secret`, `X-Import-Secret` (trong `lib/api.ts`, `lib/excel-upsert.ts`, `app/jira-actions.ts`, `app/actions.ts`, `app/actions-import.ts`, các component có ô mật khẩu).
6. Kiểm phiên (và quyền khi cần) ở đầu **mọi** Server Action, có test tĩnh khoá quy tắc.
7. Sinh lại `lib/generated/openapi.d.ts` (orchestrator) và sửa `lib/types.ts` theo.
8. Hành vi của `DATA_SOURCE=file|memory` khi đã có code đăng nhập.
9. Hạ ngưỡng rate limit 900/phút về mức hợp lý khi có JWT từng người (đổi nhỏ ở core + compose).
10. `/me`, nav theo quyền, panel "Không đủ quyền", két (Vault) theo user, route `/api/export` có kiểm phiên.
11. Trang quản trị mời user `/admin/users` (+ `/admin/audit`): pha **P3-web**, chỉ làm sau khi backend P3 có `/api/v1/admin/*` (hiện **chưa có** trong `api/v1/router.py`).

### 1.3. Out-of-scope

- Mọi thay đổi model/migration ở core. P2 không có migration.
- Backend P3 (`/admin/users/**`, `/admin/audit-log`): theo spec cha 4.2, do backend-dev làm; spec này chỉ phần web của nó.
- Caddy, compose `edge`, `ufw`, DNS, chứng chỉ (orchestrator, khi có domain công ty). Giai đoạn đầu chạy **localhost + SSH tunnel** (phương án D, `docs/STAGING_DOMAIN_HTTPS.md`).
- RLS, token Jira theo user, step-up auth (P4).
- Lọc `/team` ở backend (S12).

### 1.4. Lệch giữa tài liệu và code thật (đã kiểm)

| # | Thực tế | Hệ quả cho P2 |
|---|---|---|
| L1 | Core **không còn** `GET/PUT /settings/current-users`, `GET/PUT /settings/display-timezone`, `POST /import/verify-secret`; `settings.py` chỉ còn `sync-urls` (đòi `integration:manage`) và `timezones` | `getCurrentUsersApi`, `setCurrentUsersApi`, `getDisplayTimezoneApi`, `setDisplayTimezoneApi`, `verifyImportSecret` ở nhánh api phải gỡ/đổi. `SLOW_TTL_PATHS` trỏ path chết |
| L2 | `lib/generated/openapi.d.ts` còn cũ: vẫn có 3 path trên và `X-Import-Secret` ở 4 operation, chưa có `/me`, `/auth/login` | Bước P2.0 sinh lại trước khi frontend-dev bắt đầu; `tsc` sẽ đỏ ở mọi chỗ dùng type cũ, đó là danh sách việc |
| L3 | `GET /integrations` đòi `integration:sync`; `GET /tasks/assignees` đòi `team:read`; `GET /settings/sync-urls` đòi `integration:manage` | Trang `/data` không được gọi các hàm này khi user thiếu quyền, nếu không member nhận 403 và trang vỡ |
| L4 | Mật khẩu nhập đi qua `lib/excel-upsert.ts::authorizeImport/pushRowsToCore` (không chỉ `lib/api.ts`), và qua component `core-import-panel.tsx`, `url-sync-manager.tsx`, `file-upload-manager.tsx`, `jira-connections-manager.tsx` | Phạm vi gỡ rộng hơn spec cha liệt kê |
| L5 | `next` đã ở `15.5.25` (≥ 15.2.3, đã có bản vá CVE-2025-29927); Next 15.5 có middleware runtime Node.js ổn định | Không cần nâng Next; dùng runtime `nodejs` cho middleware (Q5) |
| L6 | Web **chưa có** test runner nào (`package.json` không có `test`), `npm run lint` chưa có cấu hình ESLint | Cần thêm runner để "test khoá hành vi" (Q4) |
| L7 | Rate limit core đã tách bucket `user:<sub>` khi JWT hợp lệ (`_identity`), ngưỡng mặc định 900 ở `core/config.py` và `docker-compose.yml` | Chỉ còn việc hạ ngưỡng (mục 4.9) |

## 2. Thay đổi dữ liệu

Không có thay đổi Postgres. Chỉ thay đổi file trên volume web:

| Đối tượng | Thay đổi | Ràng buộc | Migration / rollback |
|---|---|---|---|
| `DATA_DIR/vault.json` | Ở `DATA_SOURCE=api`: mỗi user một file `vault-<user_id>.json` | `user_id` lấy từ phiên, kiểm khớp regex UUID trước khi ghép đường dẫn; không bao giờ lấy từ input client | Đổi tên một lần theo runbook spec cha 7.3 (`vault.json` → `vault-<owner_id>.json`). Rollback: đổi tên ngược lại. Chế độ local vẫn dùng `vault.json` |
| Cookie phiên Auth.js | Mới: JWE chứa `uid`, `sv` (không chứa `role`, `access_token`, `id_token`) | `HttpOnly`, `SameSite=Lax`, `Secure` khi `AUTH_URL` là https | Đổi `AUTH_SECRET` là thu hồi mọi phiên |

## 3. API contract

### 3.1. Core endpoint web dùng (đã có ở P1, không đổi)

| Method | Path | Request | Response | Lỗi web phải xử lý |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | Header `X-API-Key` (không Bearer). Body `LoginRequest { google_sub, email, email_verified, name?, hd?, client_ip? (≤ 45) }` | 200 `LoginResult { user_id, role, session_version }` | 403 `code ∈ {not_invited, disabled, email_unverified, hd_not_allowed, account_mismatch}`; 429; 422 |
| GET | `/api/v1/me` | Bearer | `MeRead { id, email, name, role, status, timezone, effective_timezone, aliases, permissions }` | 401 `token_invalid` / `user_inactive` |
| PUT | `/api/v1/me/timezone` | `{ timezone: str \| null }` | `MeRead` | 422 tên IANA sai |
| GET | `/api/v1/settings/timezones` | Bearer | `TimezoneList` | |
| mọi route khác | | Bearer + `X-API-Key` | | 401 → `/auth/expired`; 403 `forbidden` → thông báo "Không đủ quyền" |

Lỗi core có dạng `{ "detail": str, "code": str }`. `CoreApiError` thêm field `code?: string` (đọc từ body), giữ `status`.

### 3.2. JWT web → core (khớp `core/auth.py`)

- Thuật toán `HS256`, khoá `CORE_JWT_SECRET` (web từ chối khởi động phần api nếu < 32 ký tự).
- Claim: `iss="builder-web"`, `aud="builder-core"`, `sub=<user uuid>`, `sv=<int>`, `iat=now`, `exp=now+60`, `jti=randomUUID()`. Không thêm claim khác (không email, không role).
- Ký **mỗi lời gọi** core (HMAC rẻ), không tái dùng token giữa request, không log token.

### 3.3. Route handler web

| Method | Path | Hành vi | Lỗi |
|---|---|---|---|
| GET, POST | `/api/auth/[...nextauth]` | Auth.js. Ở chế độ local trả 404 | |
| GET | `/auth/expired` | `signOut({ redirect: false })` rồi 302 `/login?error=session` | |
| GET | `/api/export` | api: không phiên → 401 JSON; `entity=vault` → file của user hiện tại; entity khác → 501 "Dùng trang Dữ liệu" (store cục bộ không phải dữ liệu thật ở api). Local: như cũ | 401, 404, 501 |

### 3.4. Core thay đổi nhỏ (backend-dev)

| Thay đổi | File | Ghi chú |
|---|---|---|
| `rate_limit_requests_per_minute` mặc định 900 → **300** (Q2) | `apps/core/app/core/config.py` | Chỉ deploy **cùng lúc** với P2: trước P2 mọi người chung bucket `key:` nên 300 sẽ gây 429 |

## 4. Thay đổi Web

Mọi điều dưới đây chỉ áp ở `DATA_SOURCE=api`, trừ khi ghi khác. Chế độ local xem 4.10.

### 4.1. Phụ thuộc

- `next-auth` **pin chính xác** (không `^`, không `~`) bản v5 mới nhất tại thời điểm cài; frontend-dev ghi vào báo cáo: bản, ngày, trạng thái bảo trì của dự án (Q6).
- `jose` pin chính xác.
- devDependency: `vitest` (Q4), pin chính xác. Script `"test": "vitest run"`.
- Không nâng `next` (đã 15.5.25). Không thêm biến `NEXT_PUBLIC_*` nào.

### 4.2. Biến môi trường (chốt theo spec cha 5.6, bổ sung một biến)

| Biến | Bắt buộc ở api | Ghi chú |
|---|---|---|
| `AUTH_SECRET`, `AUTH_URL`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `CORE_JWT_SECRET`, `CORE_API_KEY`, `CORE_API_URL` | có | Như spec cha |
| `AUTH_TRUST_HOST` | có (`true`) | |
| `GOOGLE_ALLOWED_HD` | không | Danh sách phân cách dấu phẩy, cùng giá trị với core |
| `TRUST_FORWARDED_FOR` | không, mặc định `false` | **Mới (Q8).** `true` chỉ khi có Caddy đứng trước và ghi đè `X-Forwarded-For`. `false` thì `client_ip = null` |

Module `lib/auth-config.ts` (`server-only`) đọc và kiểm các biến này **lúc chạy** một lần, trả `{ ok: true, ... } | { ok: false, missing: string[] }`. Thiếu biến ở api → mọi trang render trang lỗi cấu hình (chỉ liệt kê **tên** biến thiếu, không giá trị), không gọi core, không mở cửa không đăng nhập.

### 4.3. Auth.js (`auth.ts` ở gốc `apps/web`)

- `NextAuth` với **cấu hình lười** (hàm trả config) để `import` không ném lỗi ở chế độ local khi thiếu `AUTH_SECRET`.
- Provider Google; `authorization.params = { prompt: "select_account", scope: "openid email profile" }`; thêm `hd` nếu `GOOGLE_ALLOWED_HD` có **đúng một** giá trị (chỉ là gợi ý UI).
- `session: { strategy: "jwt", maxAge: 7 * 24 * 3600 }`, không adapter.
- `callbacks.signIn({ user, profile })`:
  1. `profile.email_verified !== true` → `"/login?error=email_unverified"`.
  2. `GOOGLE_ALLOWED_HD` có giá trị mà `profile.hd` không thuộc danh sách → `"/login?error=hd_not_allowed"`.
  3. `coreLogin({ google_sub: profile.sub, email, email_verified, name, hd }, clientIp)`; 403 → `"/login?error=<code>"` (code lấy từ body, ngoài tập 5 code thì `denied`); 429 → `error=rate_limited`; lỗi khác → `error=unavailable`.
  4. Thành công: gắn `uid`, `sv` lên object `user` (module augmentation kiểu `next-auth`), trả `true`.
- `callbacks.jwt({ token, user })`: khi có `user` (lần đăng nhập) chép `uid`, `sv`; xoá mọi field khác ngoài `uid`, `sv`, `iat`, `exp`, `jti` chuẩn của Auth.js. **Không** lưu `role`, `email`, `access_token`, `id_token`.
- `callbacks.session`: chỉ lộ `session.user = { uid }`. Component client không cần phiên (Server Component lo hết), nên không dùng `SessionProvider`.
- `callbacks.redirect({ url, baseUrl })`: dùng `safeCallbackPath()` (4.6).
- `debug: false` khi production; `logger.error` chỉ in `error.name` và `code`, không in object.
- `app/api/auth/[...nextauth]/route.ts`: export `GET`, `POST` từ `handlers`; ở local trả 404.

### 4.4. `middleware.ts`

- `export const config = { runtime: "nodejs", matcher: [...] }` (Q5). Matcher loại `/_next/*`, `/favicon.ico`, file tĩnh, `/api/auth/*`, `/auth/expired`.
- Đọc `DATA_SOURCE` qua `process.env` lúc chạy. Local → `NextResponse.next()` **trước** khi chạm Auth.js.
- api, thiếu cấu hình → 503 trang lỗi cấu hình.
- api, không phiên → 302 `/login?callbackUrl=<safeCallbackPath(pathname+search)>`. Có phiên mà vào `/login` → 302 `/`.
- Không kiểm quyền ở middleware. Middleware là UX, không phải ranh giới bảo mật (ranh giới: `coreFetch` + core).

### 4.5. `lib/api.ts` và các module mới cạnh nó

**Module mới (đều `server-only`):**

| File | Nội dung |
|---|---|
| `lib/auth-config.ts` | Đọc, kiểm env auth (4.2) |
| `lib/core-jwt.ts` | `signCoreToken({ uid, sv }): Promise<string>` theo 3.2, dùng `jose` |
| `lib/session.ts` | `getSessionUser = cache(async () => { uid, sv } \| null)` gọi `auth()`; `uid` phải khớp regex UUID, `sv` là số nguyên ≥ 0, sai → coi như không phiên |
| `lib/auth-guard.ts` | `requireSession()`, `requirePermission(perm)`, `hasPermission(me, perm)`, `actionAuthError()` (4.7) |
| `lib/permissions.ts` | Hằng `Permission` khớp `core/permissions.py` (9 giá trị), kiểu lấy từ `openapi.d.ts` nếu có, không thì union khai tay + test so khớp |
| `lib/redirect-safety.ts` | `safeCallbackPath(input, baseUrl?)` (4.6) |
| `lib/client-ip.ts` | `clientIpFrom(headers)` (4.8) |

**`coreFetch` (thay đổi chính):**

```
coreFetch(path, init):
  api mode:
    session = await getSessionUser()
    nếu null → throw CoreApiError("Chưa đăng nhập", 401, "no_session")   // KHÔNG gọi core, KHÔNG chạm cache
    token = await signCoreToken(session)
    identity = `${session.uid}:${session.sv}`
  GET và path không thuộc UNCACHED → cachedGet(identity, path, loader)   // phương án A, 4.5.1
  ghi → gọi thật, finally invalidateCoreCache()
```

- `coreFetchRaw` gắn `Authorization: Bearer <token>` **sau** khi trộn `init.headers` (caller không ghi đè được).
- `coreLogin(claims, clientIp)`: hàm riêng, đi thẳng `coreFetchRaw` không Bearer, không cache, chỉ được gọi trong `auth.ts`.
- 401 từ core trong Server Component → `redirect("/auth/expired")` (ở `getMe` và một helper `handleAuthError` cho page); trong Server Action → xem 4.7.
- `getMe = cache(...)`: `GET /api/v1/me`, **không qua cache dùng chung** (đặt `/api/v1/me` vào `UNCACHED_PREFIXES`), để khoá/thu hồi có hiệu lực ngay lần render kế tiếp.
- `getDisplayTimezoneApi()` ở api: không phiên → `FALLBACK_TZ`; có phiên → `me.effective_timezone`; lỗi → `FALLBACK_TZ`. Nhánh local giữ nguyên. Kiểu trả về giữ `DisplayTimezoneRead` (khai tay trong `types.ts` nếu `make gen-types` gỡ schema đó), `source = timezone ? "user" : "default"`.
- `setDisplayTimezoneApi(tz)` ở api → `PUT /api/v1/me/timezone`.
- Gỡ ở nhánh api: `getCurrentUsersApi` (local giữ), `setCurrentUsersApi` (api ném `CoreApiError(..., 400, "alias_admin_only")`), `ownersFor`, tham số `owner` trong `appendView` (core đã bỏ, gửi thừa vô hại nhưng gây hiểu nhầm), `verifyImportSecret`, `ImportCallOptions.secret`, tham số `secret` của `syncIntegration` và `upsertTasksBatch`, mọi header `X-Import-Secret`, `SLOW_TTL_PATHS` cũ (thay bằng không có, vì múi giờ đã lấy qua `/me`).
- `view=mine` ở api: core tự suy "của tôi" từ JWT; web chỉ gửi `view`.

#### 4.5.1. Rào cache dùng chung (Q1, khuyến nghị phương án A)

| Phương án | Mô tả | Ưu | Nhược |
|---|---|---|---|
| **A (khuyến nghị)** | Khoá cache = `${uid}:${sv}\u0000${path}`. Không phiên thì không vào cache (đã throw trước) | Giữ lợi ích cache cho `/team` (tải tới 1000 task) và các GET lặp khi click filter; `sv` trong khoá nên thu hồi phiên tạo khoá mới | Thêm một chỗ phải đúng; TTL 10s nghĩa là quyền mới hạ (`can_edit`) có thể hiển thị cũ tới 10s (core vẫn chặn ghi) |
| B | Có phiên thì không cache (giữ rào hiện tại) | Đơn giản nhất, không thể rò chéo | Mất toàn bộ lợi ích cache; mỗi click filter lại 4-6 lời gọi; bucket per-user 300/phút vẫn đủ nhưng `/team` chậm hơn |

Quy tắc bắt buộc với A:

1. `cachedGet` đổi chữ ký thành `cachedGet(identity: string, path: string, loader, ttl?)`; `identity` rỗng → ném lỗi lập trình (không bao giờ ghép khoá thiếu danh tính). Chế độ local không dùng `cachedGet`.
2. Khoá ghép bằng hàm thuần `cacheKey(identity, path)` export để test.
3. Không cache: `/api/v1/me`, `/api/v1/integrations*`, mọi non-GET.
4. Mọi lời gọi ghi xoá **toàn bộ** cache (mọi user), như hiện tại: A ghi task work thì B thấy ngay ở lần render sau.
5. Comment banner trong `core-cache.ts` cập nhật: "KHOÁ PHẢI CÓ uid:sv".
6. Giá trị dùng chung theo tham chiếu: không sửa tại chỗ (giữ quy tắc cũ).

Nếu User chọn B: giữ `perUser` bypass, test 2-4 ở dưới đổi thành "có phiên thì loader chạy mỗi lần".

**Test khoá hành vi** (`apps/web/tests/core-cache.test.ts`, `tests/core-fetch.test.ts`, mock `fetch`, mock `server-only` bằng alias trong `vitest.config.ts`, mock `getSessionUser`):

- T1: `cacheKey("A:1", p) !== cacheKey("B:1", p)` và `!== cacheKey("A:2", p)`.
- T2: user A GET `/api/v1/tasks?view=all` rồi user B GET cùng path trong TTL → `fetch` được gọi **2 lần**, B nhận body của B (body mock theo header Bearer).
- T3: cùng user, cùng path trong TTL → `fetch` 1 lần.
- T4: A ghi (POST) → GET tiếp theo của B gọi lại `fetch`.
- T5: `/api/v1/me` gọi 2 lần liên tiếp cùng user → `fetch` 2 lần.
- T6: api mode, không phiên → `coreFetch` ném `CoreApiError` 401 `no_session`, `fetch` **không** được gọi, cache không có mục mới.
- T7: header `Authorization` do caller truyền trong `init.headers` bị ghi đè bởi token của phiên.
- T8: JWT ký ra verify được bằng `jose.jwtVerify` với cùng secret, `aud/iss` đúng, `exp - iat === 60`, có `jti`, `alg === "HS256"`; secret < 32 ký tự → ném lỗi cấu hình.

### 4.6. Lọc `callbackUrl` (`safeCallbackPath`)

Chấp nhận: chuỗi bắt đầu `/`, không bắt đầu `//` hay `/\`, không chứa ký tự điều khiển, sau `new URL(x, base)` vẫn cùng origin; hoặc URL tuyệt đối cùng origin với `AUTH_URL`. Còn lại → `/`. Dùng ở middleware, `/login` và `callbacks.redirect`. Test: `/tasks?x=1` giữ nguyên; `//evil.example`, `/\evil.example`, `https://evil.example`, `javascript:alert(1)`, `/%2F%2Fevil.example` (sau decode), `\t/evil` → `/`.

### 4.7. Server Action

- **Mọi** `export async function` trong file `"use server"` (`app/actions.ts`, `actions-user.ts`, `actions-import.ts`, `actions-danger.ts`, `jira-actions.ts`, `vault-actions.ts`, `app/admin/actions.ts` ở P3) gọi ở **câu lệnh đầu tiên** một trong:
  - `const auth = await requireSession();` (đọc phiên, không gọi core), hoặc
  - `const auth = await requirePermission("<perm>");` (gọi `getMe()` một lần, kiểm `permissions`).
  - Ở local cả hai trả `{ ok: true, user: LOCAL_USER }` ngay (không auth, C4).
  - Thất bại trả `{ ok: false, error, code: "unauthenticated" | "forbidden" }` để action trả về theo kiểu kết quả sẵn có của nó; không ném lỗi thô ra client.
- 401 từ core giữa chừng (phiên bị thu hồi) → action trả `code: "session_expired"`; client component nhận code này thì `router.push("/auth/expired")`. Không dùng `redirect()` trong action trả dữ liệu (để giữ kiểu kết quả).
- Quyền theo action (khớp `core/permissions.py` và spec cha 3.4):

| Action | Guard |
|---|---|
| task/note/project CRUD, trash, `logTime`, tag (local) | `requireSession` (core tự kiểm quyền ghi theo chủ) |
| `importToCoreAction`, `importDataAction` (nhánh api) | `requirePermission("data:import")` |
| `syncFromUrlAction`, `importBulkTasksAction`, `importBulkFileAction`, `syncIntegrationAction` | `requirePermission("integration:sync")` **trước** khi fetch URL hay parse file (giữ tính chất "chặn sớm" mà `authorizeImport` từng có) |
| `saveIntegrationAction`, `clearIntegrationTokenAction`, `deleteIntegrationAction`, `migrateLocalIntegrationsAction`, `addSyncUrlAction`, `removeSyncUrlAction` | `requirePermission("integration:manage")` |
| `setCurrentUserAction` | local: như cũ; api: trả lỗi "Alias Jira do quản trị viên quản lý" |
| `setDisplayTimezoneAction` | `requireSession`, api gọi `PUT /me/timezone` |
| `wipeAllDataAction`, `restoreFromJsonAction`, `processJsonUploadAction`, `syncJiraAction` | `requireSession`; ở api từ chối như hiện có (chỉ local) |
| vault actions | `requireSession`; đường file theo `auth.user.uid` (4.11) |

- `lib/excel-upsert.ts`: gỡ `parseImportSecret`, `SECRET_REQUIRED_MESSAGE`, `authorizeImport`, `FORBIDDEN_MESSAGE` cũ (403 nay là "Bạn không có quyền đồng bộ"); `pushRowsToCore(rows)` bỏ tham số `secret`.
- **Test tĩnh khoá quy tắc** (`tests/server-actions-guard.test.ts`): đọc mọi file `app/**/*.ts` mở đầu bằng `"use server"`, tìm mọi `export async function <name>`, khẳng định câu lệnh đầu tiên trong thân hàm khớp `/^\s*const \w+ = await require(Session|Permission)\(/`. Danh sách miễn trừ chỉ có `app/login/actions.ts` (chưa có phiên là đúng, xem 4.12); muốn miễn thêm thì phải sửa test kèm lý do (review thấy được).

### 4.8. `client_ip` cho `/auth/login`

- `clientIpFrom(headers)`: nếu `TRUST_FORWARDED_FOR !== "true"` → `null`. Ngược lại lấy phần tử **đầu** của `X-Forwarded-For` (Caddy không tin XFF từ client không thuộc `trusted_proxies` nên tự đặt IP thật), `trim`, chấp nhận chỉ khi `net.isIP(x) !== 0` và độ dài ≤ 45; sai → `null`.
- Đọc header trong `signIn` callback qua `headers()` của `next/headers` (frontend-dev xác minh khả dụng trong callback của bản Auth.js đã pin; nếu không, dùng dạng `NextAuth((req) => config)` để lấy `req.headers`).
- Không log IP cùng email.
- Test: `"203.0.113.5, 10.0.0.1"` → `203.0.113.5`; `"abc"` → null; IPv6 hợp lệ giữ; cờ tắt → null.
- Hệ quả khi `null` (SSH tunnel, không Caddy): core dùng IP kết nối = IP container web, mọi người chung bucket 20 lần đăng nhập/phút. Chấp nhận ở giai đoạn một người dùng.

### 4.9. Rate limit

- Sau P2 mọi request (trừ `/auth/login`) mang JWT hợp lệ nên core đếm theo `user:<sub>`. Bucket `key:<API_KEY>` chỉ còn lượt đăng nhập (đã có trần riêng 20/IP, 60 toàn cục).
- Ngưỡng đề xuất **300/phút/user** (Q2): một lần render ~4-6 lời gọi, cache A gộp phần lặp; 300 là ~50 lần chuyển trang/phút, đủ cho người thật, đủ chặn client lỗi gọi lặp.
- backend-dev đổi default `core/config.py`; orchestrator đổi `docker-compose.yml` (`${RATE_LIMIT_REQUESTS_PER_MINUTE:-300}`) và kiểm `.env` trên VM không còn ghi đè 900.
- `fetchWithRetry` giữ nguyên (thử lại 1 lần khi `Retry-After` ≤ 3s, không với POST).

### 4.10. Chế độ `DATA_SOURCE=file|memory` khi đã có code đăng nhập

Giữ quyết định C4 (không auth), cụ thể hoá:

- Middleware cho qua trước khi chạm Auth.js. `/login` → 302 `/`. `/api/auth/*` → 404. `/auth/expired` → 302 `/`.
- `auth.ts` không được khởi tạo cấu hình (lazy), nên thiếu `AUTH_SECRET` không ném lỗi.
- `requireSession`/`requirePermission` trả `LOCAL_USER` (`uid = "local"`, mọi permission) và **không** gọi core. `coreFetch` không bao giờ chạy ở local (đường `local()`).
- `/me`, `/admin/*` hiện `LocalOnlyNotice` ("Chỉ có ở chế độ đa người dùng"). Nav ẩn `/admin/users`.
- Két giữ `vault.json`. `/api/export` như cũ.
- Banner chế độ file trong layout thêm một câu: "Chế độ này không có đăng nhập, không mở cho người khác truy cập."
- Không có cờ "tắt auth ở api" và không có auth ở file (Q3).

### 4.11. Két (Vault) theo user

- `lib/vault/store.ts`: mọi hàm nhận `owner: string | null`; `vaultFilePath(owner)` → `vault.json` khi `null` (local), `vault-<owner>.json` khi `owner` khớp regex UUID; khác → ném lỗi.
- `vault-actions.ts` truyền `auth.user.uid` ở api, `null` ở local. `wipeAllDataAction` (`vault: true`) chỉ ở local.
- Test: `vaultFilePath("../x")` ném lỗi; UUID hợp lệ ra đúng tên; `null` ra `vault.json`.

### 4.12. Route / trang

| Route | Thay đổi |
|---|---|
| `app/login/page.tsx` (mới) | Như spec cha 5.4. Map `error`: `not_invited`/`disabled`/`account_mismatch`/`denied` → cùng một câu chung; `email_unverified`, `hd_not_allowed`, `session`, `rate_limited`, `unavailable` có câu riêng không lộ thông tin. Không gọi core. Nút là form Server Action gọi `signIn("google", { redirectTo: safeCallbackPath(callbackUrl) })` (action này là ngoại lệ duy nhất của 4.7, khai trong file riêng `app/login/actions.ts` và nằm trong danh sách miễn trừ của test có ghi lý do "chưa có phiên là đúng") |
| `app/auth/expired/route.ts` (mới) | 3.3 |
| `app/config-error/page.tsx` (mới) | Trang lỗi cấu hình, chỉ tên biến thiếu |
| `app/me/page.tsx` (mới) | Email, tên, role, alias Jira (chỉ đọc), `TimezoneSelector` (chuyển từ `/data` ở chế độ api) |
| `app/layout.tsx` | api + có phiên: `getMe()`; truyền `me` cho `MainNav` (lọc theo `permission`) và `UserMenu` (tên, role, "Hồ sơ", "Đăng xuất" là form POST gọi `signOut`). Không phiên (`/login`): không gọi core, tz dự phòng. `getMe` lỗi không phải 401 → layout vẫn render với nav tối thiểu và banner "Không kết nối được core" |
| `lib/nav.ts` | `NavItem.permission?: Permission`; `/team` → `team:read`; `/system` → `system:read`; `/admin/users` → `user:manage` (P3-web); `/me` ở menu user, không ở nav |
| `app/team/page.tsx`, `app/team/participation/page.tsx`, `app/system/page.tsx` | Thiếu quyền → `components/forbidden-panel.tsx` (không gọi endpoint bị cấm) |
| `app/data/page.tsx` | api: bỏ khối "Tên của tôi" (link `/me`), bỏ `getCurrentUsersApi`/`getAssigneesApi`; chỉ gọi `listIntegrations` khi có `integration:sync`, `getSyncUrlsApi` khi có `integration:manage`; tab nhập JSON chỉ `data:import`; gỡ mọi ô mật khẩu |
| `components/core-import-panel.tsx`, `url-sync-manager.tsx`, `file-upload-manager.tsx`, `jira-connections-manager.tsx`, `jira-quick-sync.tsx` | Gỡ ô/state mật khẩu và tham số `secret` khi gọi action |
| `components/task-item.tsx` | Ẩn nút sửa/xoá theo `can_edit`/`can_delete` của `TaskRead` (nếu field có trong openapi sau P2.0; nếu không, ghi vào báo cáo và bỏ qua, core vẫn chặn) |
| `app/api/export/route.ts` | 3.3 |

### 4.13. Trang quản trị (pha P3-web, sau backend P3)

- `app/admin/users/page.tsx`: `requirePermission("user:manage")` khi render (thiếu → `ForbiddenPanel`). Danh sách phân trang server-side `?page=` 50/trang, lọc `q`/`role`/`status` trong URL, "Trang x / y", "Tổng: n" (theo `Page[UserRead]` của `GET /admin/users`).
- Form mời (`email`, `role` mặc định `member`, `name?`). Mỗi dòng: đổi role, khoá/mở, thu hồi phiên, sửa alias Jira (gợi ý từ `/tasks/assignees`), xoá (chỉ khi `status=invited`). Hiện lỗi 409 bằng câu tiếng Việt theo `code`: `email_exists`, `last_admin`, `self_lockout`, `env_admin`, `alias_taken`, `has_data`.
- `app/admin/audit/page.tsx`: nhật ký, phân trang 50/trang.
- `app/admin/actions.ts`: `inviteUserAction`, `updateUserAction`, `revokeSessionsAction`, `setAliasesAction`, `deleteUserAction`. Mỗi action: `requirePermission("user:manage")` đầu tiên; validate email (≤ 320, có `@`, `lower(trim)`), `role`/`status` thuộc enum, id UUID, alias ≤ 20 mục, mỗi mục 1-200 ký tự không ký tự điều khiển.
- `lib/api.ts`: `listUsers`, `inviteUser`, `updateUser`, `revokeUserSessions`, `setUserAliases`, `deleteUser`, `listAuditLog` (path qua `pathId`).
- Trước P3: mời bằng `make auth-invite EMAIL=... ROLE=...`; nav không hiện mục Quản trị (cờ ẩn đến khi route có thật).

## 5. Ownership (không agent nào sửa file của agent khác)

### 5.1. Lộ trình pha

| Pha | Nội dung | Ai | Điều kiện vào |
|---|---|---|---|
| P2.0 | Dựng core P1 (có `CORE_JWT_SECRET`), `make gen-types`, commit `openapi.d.ts` | orchestrator | User duyệt spec này |
| P2.1 | Nền auth: deps, `auth.ts`, route Auth.js, `middleware.ts`, `/login`, `/auth/expired`, `/config-error`, `lib/auth-config.ts`, `lib/core-jwt.ts`, `lib/session.ts`, `lib/redirect-safety.ts`, `lib/client-ip.ts`, `coreFetch` gắn JWT + cache A, `getMe`, layout, vitest + test T1-T8 | frontend-dev | P2.0 xong |
| P2.2 | Gỡ endpoint cũ và mật khẩu nhập, guard mọi Server Action + test tĩnh, nav/quyền, `/data`, `/team`, `/system`, `/me`, két theo user, export route | frontend-dev | P2.1 xong (cùng worktree, nối tiếp) |
| P2.3 | Hạ rate limit 900 → 300 | backend-dev (`config.py`), orchestrator (compose) | Song song P2.1 được (file tách rời); **merge cùng P2** |
| P2.4 | Review: `code-reviewer`, rồi `security-auditor` (bắt buộc: auth, Server Action, route handler, Vault) | orchestrator gọi | P2.1-P2.3 xong |
| P3-be | `/admin/users/**`, `/admin/audit-log` theo spec cha 4.2 | backend-dev | Có thể song song P2 |
| P3-web | 4.13 | frontend-dev | P3-be xong + `make gen-types` lại |

P1 + P2 lên staging **cùng một đợt** (spec cha mục 8). P3 lên sau, không chặn dùng thử (mời bằng CLI).

### 5.2. Danh sách file

- **backend-dev:** `apps/core/app/core/config.py` (chỉ dòng default rate limit, P2.3); test core nào khẳng định giá trị 900 nếu có (`apps/core/tests/**`). Phần P3-be theo spec cha 8.1.
- **frontend-dev:** `apps/web/**` **trừ** `apps/web/lib/generated/**` và `apps/web/lib/docs.ts`. Cụ thể:
  - `package.json`, `package-lock.json`, `vitest.config.ts` (mới), `tests/**` (mới), `next.config.ts` (chỉ khi cần `allowedOrigins`)
  - `auth.ts`, `middleware.ts`, `types/next-auth.d.ts` (mới, augmentation)
  - `app/api/auth/[...nextauth]/route.ts`, `app/auth/expired/route.ts`, `app/login/page.tsx`, `app/login/actions.ts`, `app/config-error/page.tsx`, `app/me/page.tsx` (mới); `app/admin/**` (P3-web)
  - `lib/api.ts`, `lib/core-cache.ts`, `lib/excel-upsert.ts`, `lib/types.ts`, `lib/nav.ts`, `lib/vault/store.ts`, và mới: `lib/auth-config.ts`, `lib/core-jwt.ts`, `lib/session.ts`, `lib/auth-guard.ts`, `lib/permissions.ts`, `lib/redirect-safety.ts`, `lib/client-ip.ts`
  - `app/layout.tsx`, `app/actions.ts`, `app/actions-user.ts`, `app/actions-import.ts`, `app/actions-danger.ts`, `app/jira-actions.ts`, `app/vault-actions.ts`, `app/api/export/route.ts`
  - `app/data/page.tsx`, `app/team/page.tsx`, `app/team/participation/page.tsx`, `app/system/page.tsx`, `app/page.tsx`, `app/tasks/page.tsx`
  - `components/main-nav.tsx`, `components/user-menu.tsx` (mới), `components/forbidden-panel.tsx` (mới), `components/local-only-notice.tsx` (mới nếu chưa có), `components/core-import-panel.tsx`, `components/url-sync-manager.tsx`, `components/file-upload-manager.tsx`, `components/jira-connections-manager.tsx`, `components/jira-quick-sync.tsx`, `components/task-item.tsx`, `components/admin/**` (P3-web)
- **orchestrator:** `apps/web/lib/generated/openapi.d.ts` (P2.0, sau P3-be), `apps/web/lib/docs.ts` (đăng ký spec này), `docker-compose.yml` và `docker-compose.prod.yml` (rate limit default, truyền biến `AUTH_*`, `CORE_JWT_SECRET`, `GOOGLE_ALLOWED_HD`, `TRUST_FORWARDED_FOR` cho service `web`), `.env.example`, `Makefile` (target `web-test` chạy `npm test` trong container web), `docs/GOOGLE_OAUTH_SETUP.md`, `docs/PROXMOX_DEPLOY.md`, `docs/API_REFERENCE.md`, `docs/AI_HANDOFF_STATE.md`, `.agents/rules/web-conventions.md` (quy tắc guard Server Action, khoá cache có uid:sv).
- **Không ai sửa:** `lib/store/engine.ts`, `lib/store/json-file.ts`, `lib/task-scope.ts`, `data/**`.

## 6. Tiêu chí nghiệm thu (kiểm chứng được)

### 6.1. Tự động

- [ ] `cd apps/web && npx tsc --noEmit` → exit 0 (sau P2.0 `openapi.d.ts` mới).
- [ ] `cd apps/web && npm test` (hoặc `make web-test`) → exit 0, có đủ: T1-T8 (4.5.1), test `safeCallbackPath` (4.6), `clientIpFrom` (4.8), `vaultFilePath` (4.11), test tĩnh guard Server Action (4.7), test `lib/permissions.ts` khớp 9 giá trị của `core/permissions.py` (đọc file Python bằng regex `= "([a-z_]+:[a-z_]+)"`).
- [ ] `grep -rnE "X-Import-Secret|verifyImportSecret|import_secret|ownersFor|settings/current-users|settings/display-timezone|import/verify-secret" apps/web/lib apps/web/app apps/web/components --include=*.ts --include=*.tsx` → chỉ còn khớp ở nhánh local của `getCurrentUsersApi` nếu có, **không** khớp path core cũ hay header.
- [ ] `grep -rn "NEXT_PUBLIC_AUTH\|NEXT_PUBLIC_CORE_JWT\|NEXT_PUBLIC_GOOGLE" apps/web` → rỗng.
- [ ] `grep -n '"next-auth"\|"jose"\|"vitest"' apps/web/package.json` → phiên bản không có `^`/`~`.
- [ ] `grep -rnE "console\.(log|error|warn)\(.*(token|session|profile|account)" apps/web/auth.ts apps/web/lib` → rỗng.
- [ ] `uv run pytest -q` ở core vẫn pass sau P2.3; `make smoke` pass.

### 6.2. Build và runtime

- [ ] `docker compose build web` thành công. Cùng image: chạy `DATA_SOURCE=file` → `curl -sI localhost:3000/` trả 200 (không 302 `/login`), `curl -sI localhost:3000/api/auth/session` → 404; chạy `DATA_SOURCE=api` → `curl -sI localhost:3000/tasks` → 302 `Location: /login?callbackUrl=%2Ftasks` (chứng minh middleware đọc env lúc chạy).
- [ ] `DATA_SOURCE=api` thiếu `AUTH_SECRET` → `/tasks` trả 503 trang lỗi cấu hình có tên `AUTH_SECRET`, không có dữ liệu, log core không có request nào từ web.
- [ ] `curl -sI -H 'x-middleware-subrequest: middleware:middleware:middleware:middleware:middleware' localhost:3000/tasks` (api, không cookie) → vẫn 302.

### 6.3. Kịch bản tay (SSH tunnel `ssh -L 3000:localhost:3000`, OAuth client dev, `ADMIN_EMAILS=<email User>`)

1. Mở `http://localhost:3000/tasks` → về `/login?callbackUrl=%2Ftasks`; đăng nhập Google → về `/tasks`, thấy dữ liệu; menu có Team, Hệ thống.
2. `/login?callbackUrl=https://evil.example` và `//evil.example` → đăng nhập xong về `/`.
3. Tài khoản Google chưa mời → thông báo chung "chưa được cấp quyền"; `make psql` → `audit_log` có `login_denied`.
4. `make auth-invite EMAIL=<b> ROLE=member`; B đăng nhập ở cửa sổ ẩn danh. B không thấy menu Team/Hệ thống, mở thẳng `/team` → panel "Không đủ quyền". B tạo task cá nhân; A không thấy ở `/`, `/tasks?view=all`, `/trash` **kể cả khi A tải lại trong vòng 10 giây** (kiểm rào cache).
5. A hoàn thành một task work ở `/team?status=all` → trang cập nhật ngay (Server Action xoá được cache của trang, việc còn mở ở handoff mục 14).
6. Khoá B (`UPDATE users SET status='disabled'` hoặc API admin ở P3) → B bấm bất kỳ trang nào → `/login?error=session` ngay lần bấm kế tiếp; B bấm nút hoàn thành task (Server Action) → về trang đăng nhập.
7. Member gọi nhập Excel/URL → thông báo "không có quyền" và **không** có request tải URL trong log web.
8. Bấm 50 lần đổi filter `/tasks` trong một phút → không gặp 429; `make psql`/`redis-cli KEYS 'ratelimit:user:*'` có bucket theo user.
9. Két: A tạo két, B mở `/vault` → két trống; trên volume có `vault-<uid A>.json`.
10. `docker compose logs web api | grep -iE "eyJ|ya29\."` → rỗng.

### 6.4. Review

`code-reviewer` rồi `security-auditor` (bắt buộc). `db-reviewer` không cần (không có migration).

## 7. Rủi ro & câu hỏi cần User chốt

### 7.1. Câu hỏi (kèm khuyến nghị)

| # | Câu hỏi | Khuyến nghị |
|---|---|---|
| Q1 | Rào cache khi có JWT từng người: đưa `uid:sv` vào khoá (A) hay tắt cache khi có phiên (B)? | **A**, kèm test T1-T7. Lý do: giữ hiệu quả cho `/team` và filter, rò chéo bị chặn bằng khoá + test. Chọn B nếu muốn tối giản tuyệt đối |
| Q2 | Ngưỡng rate limit theo user? | **300/phút**. Deploy cùng P2, không trước |
| Q3 | `DATA_SOURCE=file` có cần đăng nhập không? | **Không** (giữ C4), chỉ thêm cảnh báo trong banner và runbook. Muốn file mode có đăng nhập (danh sách email trong env, không qua core) thì làm epic riêng |
| Q4 | Thêm `vitest` làm test runner cho web? | **Có** (devDependency, pin chính xác, kèm target `make web-test`). Không có runner thì "test khoá hành vi" không làm được |
| Q5 | Middleware chạy runtime `nodejs` (Next 15.5) thay vì Edge? | **Có**: đọc `process.env` lúc chạy chắc chắn trong image standalone, dùng chung code Node (`jose`, `net.isIP`) |
| Q6 | Auth.js v5 vẫn mang nhãn beta và dự án đã chuyển sang chế độ bảo trì (theo hiểu biết của architect, cần xác minh lúc cài). Giữ Q10 của spec cha? | **Giữ Auth.js v5, pin chính xác**, frontend-dev xác minh tình trạng và ghi vào báo cáo. Nếu bản mới nhất có lỗ hổng chưa vá hoặc không tương thích Next 15.5 thì dừng, báo lại để cân nhắc `openid-client` + `jose` |
| Q7 | Làm trang `/admin/users` ngay trong đợt P2 hay đợi backend P3? | **Đợi P3-be**; trong lúc đó mời bằng `make auth-invite`. Web không tự giả lập API chưa có |
| Q8 | Thêm biến `TRUST_FORWARDED_FOR` (mặc định `false`) để chỉ tin `X-Forwarded-For` khi có Caddy? | **Có**. Khi chạy SSH tunnel không có Caddy, tin XFF cho phép client tự đặt IP để né giới hạn đăng nhập theo IP |
| Q9 | `/auth/expired` đăng xuất bằng GET (người khác dụ bấm link có thể làm User bị đăng xuất)? | **Chấp nhận**: chỉ gây đăng xuất, không lộ hay ghi dữ liệu; đổi lại không có vòng lặp và không cần form |

### 7.2. Rủi ro

- **Rò dữ liệu chéo qua cache** nếu khoá thiếu danh tính. Giảm thiểu: `cachedGet` bắt buộc `identity`, test T1-T7, `security-auditor` rà, banner cảnh báo trong `core-cache.ts`.
- **Quên guard ở một Server Action mới.** Giảm thiểu: `coreFetch` không phiên là 401 (lớp 1), core đòi JWT (lớp 2), test tĩnh (lớp 3) đỏ ngay khi thêm action thiếu guard.
- **Auth.js v5 beta/bảo trì.** API callback có thể khác giữa các bản beta (đặc biệt việc truyền `uid` từ `signIn` sang `jwt`, đọc header trong callback). Pin chính xác; mọi chỗ phụ thuộc hành vi này có test hoặc kịch bản tay 6.3.
- **`openapi.d.ts` cũ** làm `tsc` báo lỗi hàng loạt hoặc che lỗi. P2.0 bắt buộc trước khi code.
- **Quyền hiển thị trễ tối đa 10 giây** (TTL cache) sau khi admin hạ role; ghi vẫn bị core chặn ngay. `/me` không cache nên khoá tài khoản có hiệu lực ngay.
- **Hạ rate limit trước khi P2 chạy** sẽ làm mọi người chung bucket 300 và gặp 429. Chỉ đổi trong cùng đợt deploy.
- **Server Action sau reverse proxy** bị từ chối nếu Caddy không giữ `Host`. Caddy mặc định giữ; nếu lỗi thì đặt `serverActions.allowedOrigins` (lúc build) theo host công khai.
- **`client_ip` null khi chạy tunnel**: mọi lượt đăng nhập chung bucket 20/phút. Chấp nhận ở giai đoạn một người dùng.
- **Chế độ file không có auth** vẫn là rủi ro vận hành nếu ai đó chạy nó trên VM mở LAN. Chỉ chặn được bằng cấu hình bind/firewall và runbook, không bằng code.

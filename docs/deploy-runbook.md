# Runbook deploy

Tài liệu này trả lời câu hỏi **"tôi đang ở tình huống X, phải chạy lệnh gì theo
đúng thứ tự"**. Mô hình nhánh, quy tắc fast-forward, và cách tạo `uat`/`prod`
nằm ở [docs/git-workflow.md](git-workflow.md) — không lặp lại ở đây. File này
chỉ nói về **thực thi trên server**: build, migrate, kiểm tra, và cách chẩn
đoán khi một bước thất bại.

## Tổng quan: deploy là gì trong hệ thống này

```
   máy dev                  máy UAT                  máy production
  ┌─────────┐    git push   ┌─────────┐   git push   ┌─────────┐
  │  main   │ ──────────►   │   uat   │ ──────────►  │  prod   │
  └─────────┘               └─────────┘              └─────────┘
       │                         │                         │
       │ make                    │ git pull --ff-only       │ git pull --ff-only
       │ bootstrap               │ make prod-build          │ make backup (!)
       ▼                         │ make prod-up             │ make prod-build
   dev stack                     │ make migrate              │ make prod-up
   (hot reload)                  │ make smoke                │ make migrate
                                 ▼                         │ make health
                             UAT đang chạy                  ▼
                                                        prod đang chạy
```

Ba điều cố định trong mọi case dưới đây:

1. **Deploy = checkout đúng commit + build lại image + áp migration + kiểm tra.**
   Không có bước nào "chỉnh tay trên server rồi quên ghi lại" — mọi thay đổi
   phải đi qua git trước, server chỉ `pull` và `build`.
2. **UAT và production chạy đúng một compose file** (`docker-compose.prod.yml`),
   khác nhau ở `.env`. Nếu quy trình của bạn khác nhau giữa hai môi trường ở
   bước nào ngoài giá trị `.env`, đó là dấu hiệu UAT không còn nghiệm thu đúng
   thứ sắp lên production.
3. **`make smoke` là cổng chặn, không phải gợi ý.** Nếu fail, dừng lại và sửa,
   đừng tiếp tục sang bước sau. Toàn bộ case dưới đây đều kết thúc bằng bước
   kiểm tra; đừng bỏ qua nó vì "chắc là ổn".

## Trước khi bắt đầu case nào

Hai bản checkout riêng, mỗi bản một nhánh (xem lý do đầy đủ ở
[git-workflow.md § Tách môi trường trên một node](git-workflow.md)):

```
/srv/builder-ai/uat    nhánh uat,  COMPOSE_PROJECT_NAME=builder-uat
/srv/builder-ai/prod   nhánh prod, COMPOSE_PROJECT_NAME=builder-prod
```

Mọi lệnh `make` trong các case dưới đây giả định bạn đang `cd` đúng vào một
trong hai thư mục này.

---

## Case 1 — Deploy lần đầu trên một máy mới

Dùng khi: máy chưa từng chạy stack này (server mới, hoặc clone sang Ubuntu
lần đầu). Lệnh cài Docker đầy đủ nằm ở
[README.md § Chạy trên Ubuntu](../README.md).

```bash
# 1. Cài Docker Engine — chi tiết đầy đủ ở README.md § Chạy trên Ubuntu
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker

# 2. Clone đúng nhánh môi trường
git clone -b prod https://github.com/<org>/<repo>.git /srv/builder-ai/prod
cd /srv/builder-ai/prod

# 3. Sinh .env với khoá ngẫu nhiên (POSTGRES_PASSWORD, API_KEY, CORE_JWT_SECRET,
#    AUTH_SECRET, INTEGRATION_SECRET_KEY). Sao lưu .env: mất INTEGRATION_SECRET_KEY
#    thì phải nhập lại mọi token tích hợp.
make env
# Sửa .env: COMPOSE_PROJECT_NAME=builder-prod, ENVIRONMENT=production,
# CORS_ORIGINS khớp domain thật. Xem bảng đầy đủ ở git-workflow.md.
# BẮT BUỘC đặt thêm biến đăng nhập (AUTH_URL, ADMIN_EMAILS, ...): xem
# "Cấu hình đăng nhập" ngay dưới khối lệnh này.

# 4. Build và dựng. Migration đã nằm sẵn trong git, KHÔNG chạy make migration-init.
make prod-build
make prod-up        # api tự chạy "alembic upgrade head" khi khởi động
make migrate        # chạy lại tường minh để thấy output và chắc chắn đã áp xong
make health
make smoke

# 5. Tạo tài khoản admin đầu tiên (chỉ cần nếu dùng đăng nhập nội bộ, không dùng Google)
make auth-create-local USERNAME=<ten> EMAIL=<email-trong-ADMIN_EMAILS> ROLE=admin
```

**Cấu hình đăng nhập (bắt buộc trước `make prod-up`).** Bản hiện tại luôn bắt đăng nhập;
thiếu biến nào dưới đây thì web hiện `/config-error` hoặc core không khởi động (fail closed).

| Biến trong `.env` | Ý nghĩa | Ai đặt |
|---|---|---|
| `AUTH_URL` | URL công khai của web, **đúng như người dùng gõ** (scheme + host + cổng), vd `http://192.168.100.203:3000` hoặc `https://<domain>`. Auth.js redirect về đúng URL này sau đăng nhập; sai host thì người dùng bị đẩy sang host khác. Không còn mặc định `localhost`, để trống thì web báo `/config-error` | **Tự điền** (`make env` chỉ chép giá trị mẫu `http://localhost:3000`, phải đổi) |
| `AUTH_SECRET` | Khoá Auth.js ký cookie phiên. Phải khác `API_KEY` và `CORE_JWT_SECRET` | `make env` sinh |
| `CORE_JWT_SECRET` | Khoá ký JWT HS256 web→core (≥ 32 ký tự). `web` và `api` dùng **cùng giá trị**. Thiếu thì core không khởi động | `make env` sinh |
| `ADMIN_EMAILS` | Email luôn là admin (phân cách dấu phẩy). Core upsert lúc khởi động. Email đầu tiên cũng là `SMOKE_EMAIL` của `make smoke` | **Tự điền**, mặc định trống |
| `INTEGRATION_SECRET_KEY` | Khoá Fernet mã hoá token Jira trong DB. Để trống thì tắt lưu token. **Mất khoá = nhập lại mọi token**, nên sao lưu | `make env` sinh |
| `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `GOOGLE_ALLOWED_HD` | Chỉ khi dùng đăng nhập Google. Để trống `AUTH_GOOGLE_*` thì nút Google không hiện. Hướng dẫn: [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md) | Tự điền, tuỳ chọn |

Máy đã có `.env` từ trước khi các biến này ra đời: `make env-fill` bổ sung
`INTEGRATION_SECRET_KEY`, `CORE_JWT_SECRET`, `AUTH_SECRET` còn thiếu, **không đổi biến đã có**.
Nó không đặt `AUTH_URL` hay `ADMIN_EMAILS`: hai biến đó luôn phải tự điền. Sau `make env-fill`
phải `make prod-up` để container nhận biến mới.

**Vì sao không còn `migration-init`.** `apps/core/migrations/versions/` đã chứa đủ chuỗi
migration trong git (từ `initial_schema` trở đi). Chạy `make migration-init` lúc này sẽ
autogenerate thêm một revision "initial schema" thứ hai, lệch với chuỗi hiện có và làm
`alembic upgrade head` có nhiều head hoặc chạy sai. Mọi máy mới, kể cả lần đầu, chỉ cần
`make migrate` (api cũng tự áp khi khởi động). Target `migration-init` còn trong Makefile
nhưng chỉ dành cho repo mà `versions/` trống thật sự; ở repo này đừng dùng.

Nếu đây là máy UAT thay vì prod, đổi `-b prod` thành `-b uat`, và `.env` đặt
`ENVIRONMENT=staging` (không phải `uat` — xem lý do ở
[git-workflow.md](git-workflow.md)).

## Case 2 — Deploy một update thường (không đổi schema, không đổi `.env`)

Dùng khi: `main` chỉ có thay đổi code (sửa UI, sửa logic, thêm field không
cần migration).

```bash
cd /srv/builder-ai/prod
git fetch origin
git log --oneline prod..origin/prod   # xem trước sắp lên gì

git pull --ff-only
make prod-build
make prod-up
make health
make smoke
```

Không có `make backup` ở đây vì không đổi schema — rủi ro dữ liệu bằng không.
Nếu bạn không chắc thay đổi có đụng migration không, giả định là **có** và
làm theo Case 3; backup thừa một lần không hại gì, thiếu một lần thì có.

## Case 3 — Deploy update có migration (đổi schema)

Dùng khi: commit sắp lên có file mới trong `apps/core/migrations/versions/`.

```bash
cd /srv/builder-ai/prod

# 1. BẮT BUỘC backup trước khi migrate. Đây là bước duy nhất khác Case 2.
make backup
# Xác nhận file đã tạo và không rỗng:
ls -lh backups/ | tail -n 1

git pull --ff-only
make prod-build
make prod-up

# 2. Migration chạy TỰ ĐỘNG khi container api khởi động (xem CMD trong
#    apps/core/Dockerfile: "alembic upgrade head && exec uvicorn ..."). Lệnh
#    `make migrate` dưới đây là chạy LẠI tường minh để thấy output rõ ràng
#    và biết chắc nó đã áp xong trước khi gọi make health.
make migrate
make health
make smoke
```

**Nếu `make migrate` báo lỗi**, container `api` có thể đang crash-loop vì
`alembic upgrade head` chạy lúc khởi động cũng fail. Xem log trước khi làm gì
khác:

```bash
make logs-api
```

Hai nguyên nhân thường gặp: migration mới xung đột với dữ liệu thật đang có
(ví dụ thêm cột `NOT NULL` không có default trên bảng đã có dòng), hoặc
migration được viết và test trên DB trống rồi quên trường hợp dữ liệu cũ.
Cách xử lý nằm ở Case 8 (rollback kèm migration).

## Case 4 — Đổi biến môi trường hoặc secret

Dùng khi: đổi `CORS_ORIGINS`, xoay `API_KEY`, đổi `TRASH_RETENTION_DAYS`, thêm
API key provider LLM, v.v. — không đổi code, không đổi schema.

```bash
cd /srv/builder-ai/prod
nano .env   # hoặc vi, sửa đúng biến cần đổi

# Hầu hết biến chỉ cần restart container đọc lại, KHÔNG cần build lại image
make prod-up    # docker compose up -d áp .env mới cho container đổi
make health
```

**Múi giờ:** hệ thống dùng một múi giờ duy nhất, là biến `TZ` trong `.env`. Cả `api`
(`display_timezone`) và `web` đọc nó lúc chạy, nên đổi `TZ` chỉ cần `make prod-up`, không
phải build lại image. Không còn biến `NEXT_PUBLIC_*` nào; nếu sau này thêm thì giá trị
bị nhúng lúc build và đổi nó phải `make prod-build`.

**Biến đăng nhập (`AUTH_URL`, `AUTH_SECRET`, `CORE_JWT_SECRET`, `ADMIN_EMAILS`).** Đổi các
biến này cũng chỉ cần `make prod-up`, nhưng có ràng buộc:

- `AUTH_URL` phải khớp URL người dùng gõ vào. Đổi domain hoặc IP thì đổi cả `AUTH_URL`,
  `CORS_ORIGINS` và redirect URI ở Google (nếu dùng Google).
- Đổi `AUTH_SECRET` làm **mọi phiên đăng nhập hết hiệu lực**, người dùng phải đăng nhập lại.
- `CORE_JWT_SECRET` phải giống nhau ở `web` và `api`; `make prod-up` đọc `.env` cho cả hai nên
  không lệch. Đừng restart riêng một service. Không dùng chung với `API_KEY` hay `AUTH_SECRET`.
- Thêm admin: thêm email vào `ADMIN_EMAILS` rồi `make prod-up` (core upsert lúc khởi động).
- `INTEGRATION_SECRET_KEY` **không xoay bằng cách thay giá trị**: đặt khoá mới vào
  `INTEGRATION_SECRET_KEY` và chuyển khoá cũ sang `INTEGRATION_SECRET_KEY_OLD`, nếu không token
  Jira đã lưu không giải mã được.

**Xoay `API_KEY`.** `API_KEY` được cả `api` (để validate) và `web` (để gọi
`api`) dùng, nên đổi nó phải restart cả hai cùng lúc — `make prod-up` làm đúng
việc này vì đọc `.env` cho toàn bộ service. Đừng chỉ `docker compose restart
api`, web sẽ gọi với key cũ và nhận toàn `401`.

Secret của UAT và prod **phải khác nhau**. Nếu dùng chung, một khoá lộ ở UAT
(môi trường ít được bảo vệ hơn) là lộ luôn cả production.

## Case 5 — Đổi dependency (thêm/nâng package)

### Python (`apps/core/pyproject.toml`)

```bash
cd /srv/builder-ai/prod   # hoặc làm trên máy dev rồi commit uv.lock
nano apps/core/pyproject.toml   # sửa dependency

make lock     # sinh lại uv.lock từ pyproject.toml, chạy TRONG container
make build    # build lại image với lock mới — make lock đã tự nhắc bước này
```

`make lock` chạy `uv lock` trong container `api` đang sống, nghĩa là bạn cần
stack đang `up` trước khi gọi nó. Lock file sinh ra nằm trên bind mount
(`./apps/core:/app`), nên nó xuất hiện ngay trên host — **commit `uv.lock`
cùng với `pyproject.toml`**, đừng để lock file tự sinh riêng trên từng máy.

### Node (`apps/web/package.json`)

```bash
nano apps/web/package.json
cd apps/web && npm install   # sinh lại package-lock.json trên host
cd ..
```

Commit cả `package.json` và `package-lock.json`, rồi deploy như Case 2 hoặc
3 — `prod-build` sẽ chạy `npm ci` bằng lock file đã commit (xem
`apps/web/Dockerfile`, stage `deps`). Không cần target `make` riêng cho Node
vì không có bước sinh lock tách biệt khỏi `npm install` như bên Python.

## Case 6 — Hotfix khẩn cấp (production đang lỗi, cần sửa ngay)

Quy trình **git** đầy đủ (tạo nhánh từ `prod`, merge, tag, back-merge đúng
thứ tự) nằm ở [git-workflow.md § Hotfix](git-workflow.md). Phần dưới đây là
bước **deploy** sau khi đã có tag hotfix.

```bash
cd /srv/builder-ai/prod

# Nếu hotfix có đổi schema, backup trước — không có ngoại lệ dù đang gấp
make backup

git fetch --tags origin
git pull --ff-only   # prod đã được release.sh fast-forward tới tag mới
make prod-build
make prod-up
make migrate   # vô hại nếu hotfix không đổi schema, alembic tự biết không có gì để áp
make health
make smoke
```

Sau khi xác nhận hotfix chạy ổn, **back-merge ngay** (bước git, không phải
bước deploy) theo đúng thứ tự ở git-workflow.md, rồi mới coi là xong việc.
Hotfix chưa back-merge là nợ kỹ thuật sẽ tự xuất hiện lại ở lần `promote-uat`
tiếp theo dưới dạng conflict hoặc cảnh báo của `make git-status`.

## Case 7 — Rollback code, KHÔNG đụng schema

Dùng khi: bản mới lên có bug về logic/UI, nhưng không đổi migration nào kể từ
bản chạy ổn trước đó.

```bash
cd /srv/builder-ai/prod
make rollback-info   # in ra tag trước đó và các lệnh gợi ý

git fetch --tags origin
git checkout <tag_truoc_do>   # ví dụ: git checkout v1.0.0
make prod-build
make prod-up
make health
```

Đây là trường hợp **duy nhất** được phép `git checkout` một tag cũ thay vì
`git pull --ff-only` — vì bạn đang cố tình lùi lại, không đi tới. Sau khi
service ổn định trở lại, nhánh `prod` local đang ở trạng thái "detached" so
với remote; đừng push gì từ đây. Sửa lỗi trên `main`, thăng cấp lại qua
`uat` → `prod` như bình thường, nhánh `prod` sẽ tự tiến lên đúng cách.

## Case 8 — Rollback kèm migration (schema đã đổi, cần lùi cả dữ liệu)

Đây là trường hợp **không có đường lùi tự động** — `release.sh rollback` chỉ
in hướng dẫn, không tự chạy gì, đúng là vì bước này luôn cần con người quyết
định dựa trên tình huống thật.

**Thứ tự bắt buộc: dừng traffic hỏng trước, rồi mới quyết định lùi gì.**

```bash
cd /srv/builder-ai/prod

# 1. Lùi code trước, giữ app chạy được (có thể lỗi một phần) trong khi quyết định
make rollback-info
git checkout <tag_truoc_do>
make prod-build
make prod-up
```

Giờ chọn một trong hai đường cho database, theo loại migration vừa lên:

**Đường A — migration là loại lùi được an toàn** (thêm cột nullable, thêm
bảng mới, thêm index): chạy `alembic downgrade`.

```bash
make downgrade     # lùi một bước
# Lùi nhiều bước: xem lịch sử rồi downgrade tới revision cụ thể
make history
docker compose exec -T api alembic downgrade <revision_id>
```

**Đường B — migration đã xoá cột/bảng, hoặc downgrade không viết đủ**: không
dùng `alembic downgrade`, restore từ bản backup đã chụp trước khi migrate
(đây là lý do Case 3 bắt `make backup` là bước **bắt buộc**, không tuỳ chọn).

```bash
# Dừng api để không có write mới trong lúc restore
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api web

# Giải nén và restore. ĐÈ TOÀN BỘ dữ liệu hiện tại — xác nhận đúng file trước khi chạy.
gunzip -c backups/builder_ai_<timestamp>.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

make prod-up   # dựng lại api, web
make health
```

Khoảng trống dữ liệu giữa lúc backup và lúc lỗi (mọi task/note tạo trong lúc
đó) sẽ mất theo Đường B. Nếu khoảng trống đó quan trọng, cân nhắc
`make export` ngay trước khi restore để giữ lại ít nhất bản JSON của trạng
thái hiện tại, dù không nhập lại được ngay.

## Case 9 — Bật thêm profile phụ (`llm` hoặc `monitoring`) trên môi trường đang chạy

Dùng khi: stack core đã chạy ổn, giờ muốn thêm LiteLLM hoặc Prometheus/Grafana
mà không động vào service đang có.

```bash
cd /srv/builder-ai/prod

# Điền phần biến môi trường tương ứng trong .env trước (xem .env.example):
#   profile llm:         LITELLM_MASTER_KEY, LITELLM_SALT_KEY, ANTHROPIC_API_KEY, ...
#   profile monitoring:  GRAFANA_ADMIN_PASSWORD, PROMETHEUS_PORT, ...

make llm-up     # hoặc: make mon-up
make ps         # xác nhận container mới ở trạng thái "healthy" hoặc "running"
```

Không cần `make prod-build` hay `down` service cũ — profile phụ là service
độc lập, bật thêm không ảnh hưởng `api`/`web`/`postgres`/`redis` đang chạy.

**Lưu ý rủi ro quyền hệ thống với `monitoring`.** `cadvisor` chạy
`privileged: true` và mount `/var/lib/docker`; `node-exporter` chạy
`pid: host`. Trên máy chia sẻ với workload khác hoặc máy không hoàn toàn do
bạn kiểm soát, cân nhắc kỹ trước khi bật — đây là mức quyền cao hơn hẳn phần
`core`.

**Đổi key LLM sau này** (xoay `ANTHROPIC_API_KEY` chẳng hạn) chỉ cần sửa
`.env` rồi `make llm-up` lại — compose tự nhận diện service không đổi cấu
hình container thì không restart, có đổi thì restart đúng service đó.

## Case 9b — Bật đăng nhập lần đầu trên prod đang chạy bản cũ

Dùng khi: prod đang chạy bản trước khi có đăng nhập (không có `AUTH_*`, `CORE_JWT_SECRET`),
giờ nâng lên bản có đăng nhập và đã có dữ liệu thật.

```bash
cd /srv/builder-ai/prod

make backup && ls -lh backups/ | tail -n 1   # bắt buộc: migration thêm bảng user, gán chủ dữ liệu

git pull --ff-only   # kéo code TRƯỚC: gen-env.sh bản cũ chưa sinh CORE_JWT_SECRET/AUTH_SECRET

make env-fill        # bổ sung CORE_JWT_SECRET, AUTH_SECRET, INTEGRATION_SECRET_KEY còn thiếu
nano .env            # tự điền AUTH_URL và ADMIN_EMAILS (+ AUTH_GOOGLE_* nếu dùng Google)

make prod-build
make prod-up
make migrate

# Gán chủ cho dữ liệu cũ (task/note tạo trước khi có user). Chạy thử trước:
make auth-bootstrap OWNER=<email-admin> DRY=1
make auth-bootstrap OWNER=<email-admin>

# Nếu dùng đăng nhập nội bộ: tạo tài khoản (in mật khẩu tạm MỘT lần, đăng nhập xong bị ép đổi)
make auth-create-local USERNAME=<ten> EMAIL=<email-admin> ROLE=admin

make health
make smoke
```

Kiểm tra bằng trình duyệt: mở `AUTH_URL`, phải thấy trang `/login`; đăng nhập xong phải về
**đúng host đó**, không phải `localhost`. Thấy `/config-error` nghĩa là thiếu biến (thường là
`AUTH_URL`). Bảng lỗi đầy đủ: [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md).

Rollback (Case 7/8) về bản không có đăng nhập thì các bảng user vẫn còn trong DB; nếu cần lùi
schema thì theo Case 8, và nhớ đã có `make backup` ở bước đầu.

## Case 10 — Chỉ cần máy khác trong LAN dùng chung, không phải case deploy thật

Dùng khi: bạn **không** đang dựng UAT/production. Chỉ muốn điện thoại hay
laptop khác trong nhà/văn phòng mở được app đang chạy trên máy mình, tạm thời.
Đây không phải một "case deploy" theo nghĩa các case trên — không có git
checkout, không có build riêng, không có environment riêng.

```bash
make lan-up     # mở cổng web ra mọi interface, không chỉ 127.0.0.1
make lan-down   # đóng lại, về như make up (chỉ 127.0.0.1)
```

Chi tiết cơ chế, cảnh báo bảo mật (không có đăng nhập ở Phase 1, nên chỉ bật
trên mạng tin tưởng toàn bộ thiết bị), và cách tìm IP máy đang chạy app nằm ở
[README.md § Chia sẻ trong LAN](../README.md#chia-sẻ-trong-lan-dùng-chung-từ-máy-khác-không-deploy-server-riêng).

**Khi nào thật sự cần một case deploy ở trên thay vì lệnh này**: cần máy
khác luôn truy cập được dù máy chính của bạn tắt, cần domain thật qua
Tailscale/Caddy, hoặc cần nhiều người dùng với quyền riêng (RBAC — chưa có ở
Phase 1). Khi đó mới cần Case 1 (deploy lần đầu) trên một máy chạy liên tục.

## Case 11 — Deploy fail giữa chừng, cần khôi phục trạng thái chạy được

Dùng khi: một lệnh trong Case 2/3/6 fail và bạn cần đưa service về lại trạng
thái phục vụ được, trước khi có thời gian điều tra kỹ.

```bash
cd /srv/builder-ai/prod
make ps              # xem service nào đang "Exited" hay "unhealthy"
make logs-api         # 100 dòng cuối, tìm traceback hoặc migration error
```

Phân loại theo điểm fail:

| Fail ở bước | Trạng thái hiện tại | Hành động |
|---|---|---|
| `prod-build` | Image cũ vẫn còn, container cũ vẫn chạy | An toàn — chưa `up` lại thì chưa ảnh hưởng gì đang chạy. Sửa lỗi build rồi thử lại. |
| `prod-up` (container không lên) | `docker compose` giữ nguyên container cũ nếu container mới không start được | Xem `make logs-api`/`make logs-web`. Nếu không sửa nhanh được, `git checkout <tag cũ>` rồi `make prod-build && make prod-up` để quay lại Case 7. |
| `make migrate` fail giữa transaction | Alembic chạy mỗi migration trong một transaction — fail giữa chừng thì transaction đó tự rollback, DB không ở trạng thái nửa vời của **một** migration, nhưng có thể dừng giữa **chuỗi nhiều** migration | Chạy `make history` để biết đã áp tới revision nào, sửa migration lỗi, chạy lại `make migrate`. Nếu không sửa được ngay, dùng Đường B của Case 8 để restore. |
| `make smoke` fail sau khi mọi thứ "lên" | Service đang chạy nhưng hành vi sai | Đừng công bố deploy xong. Đọc tên test fail trong output — chúng được đặt tên theo đúng hành vi kiểm tra (ví dụ "external_id trùng bị chặn 409"), nên tên test fail thường chỉ thẳng ra module lỗi. Rollback theo Case 7/8 nếu không sửa được trong vài phút. |

**Nguyên tắc chung khi không chắc:** service đang chạy ổn (dù là bản cũ) luôn
tốt hơn service đang nửa vời ở bản mới. Ưu tiên rollback nhanh về trạng thái
chạy được, điều tra kỹ sau, thay vì cố sửa trực tiếp trên production trong
lúc đang mất dịch vụ.

---

## Checklist trước mỗi lần deploy production

Dùng cho Case 2, 3, 6 — bất kỳ lần nào đưa code mới lên `prod`.

- [ ] Đã qua UAT và `make smoke` pass sạch trên UAT (không deploy thẳng từ
      `main` lên `prod`, bỏ qua `uat` — xem bất biến fast-forward ở
      git-workflow.md)
- [ ] Nếu có migration mới: đã `make backup` trên **production**, đã xác
      nhận file backup không rỗng (`ls -lh backups/`)
- [ ] Nếu có đổi biến đăng nhập hoặc bật login lần đầu: `AUTH_URL` đúng URL người dùng gõ,
      `ADMIN_EMAILS` có ít nhất một email, `CORE_JWT_SECRET`/`AUTH_SECRET` đã có (`make env-fill`)
      — xem Case 1 và Case 9b
- [ ] Nếu có đổi `NEXT_PUBLIC_*`: nhớ `make prod-build`, không chỉ `prod-up`
- [ ] Biết rõ cách rollback cho lần deploy này **trước khi** bắt đầu (Case 7
      nếu không đổi schema, Case 8 nếu có)
- [ ] Sau khi `prod-up`: chạy đủ `make health` **và** `make smoke`, không
      dừng ở health (health chỉ xác nhận service sống, không xác nhận hành
      vi đúng)
- [ ] Theo dõi `make logs-api` vài phút sau deploy nếu đây là thay đổi lớn

## Troubleshooting

**#1 — `make migrate` chạy "thành công" nhưng gọi API thì lỗi bảng không
tồn tại.** Thường là `make migrate` chạy trên DB/compose project khác với cái api đang dùng
(sai thư mục, `COMPOSE_PROJECT_NAME` lệch), hoặc `alembic_version` trỏ tới revision không còn
trong `versions/`. Kiểm: `make history` xem revision hiện tại, `make ps` xem đúng project.
Đừng chạy `make migration-init`: `versions/` đã có đủ migration trong git (xem Case 1).

**#1b — Web hiện `/config-error`, hoặc đăng nhập xong bị đẩy về `localhost`.**
`AUTH_URL` trống hoặc sai host. Đặt đúng URL người dùng gõ, rồi `make prod-up`
(compose tự tạo lại web khi env đổi, và target này giữ nguyên overlay LAN).

**#1c — Core không khởi động, log nhắc `CORE_JWT_SECRET`.** Thiếu hoặc < 32 ký tự. Chạy
`make env-fill` rồi `make prod-up`.

**#2 — Web chạy đúng ở local nhưng tab Tài liệu báo "không tìm thấy file" trên
server.** Thiếu mount `DOCS_DIR`. Đảm bảo đang dùng `docker-compose.prod.yml`
(có `volumes: !override` mount lại `README.md`, `docs/`, `.agents/rules/`, `.agents/skills/`
read-only) — nếu bạn tự viết compose khác, phải tự thêm ba mount này.

**#3 — Đổi `.env` nhưng container không nhận giá trị mới.** `docker compose
up -d` chỉ recreate container nếu nó phát hiện cấu hình đổi. Nếu nghi ngờ,
buộc recreate (`make prod-up` không có cờ này nên phải gọi compose trực tiếp, và phải
giữ overlay LAN giống target đó, nếu không web mất cổng LAN khi `.env` có `EXPOSE_LAN=true`):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  $(grep -q '^EXPOSE_LAN=true' .env 2>/dev/null && echo "-f docker-compose.lan.yml") \
  up -d --force-recreate api web
```

**#4 — `docker-compose.prod.yml` báo lỗi parse, phàn nàn về `!override`.**
Cần Docker Compose ≥ 2.24. Kiểm tra: `docker compose version --short`.

**#5 — UAT và production tranh nhau port hoặc volume khi chạy trên cùng
máy.** `COMPOSE_PROJECT_NAME` ở hai `.env` giống nhau, hoặc một trong hai
chưa đặt (compose sẽ lấy tên thư mục làm project name mặc định — hai thư mục
tên khác nhau thì vẫn an toàn, nhưng đặt tường minh để không phụ thuộc vào
tên thư mục). Đặt đúng theo bảng ở git-workflow.md: `builder-uat` và
`builder-prod`.

**#6 — `make lock` báo lỗi "service api is not running".** `uv lock` chạy
`docker compose exec` vào container đang sống. Chạy `make up` (hoặc
`make prod-up`) trước.

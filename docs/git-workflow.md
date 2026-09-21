# Mô hình Git và quy trình go-live

Tài liệu này mô tả cách code đi từ máy dev lên production, và tại sao chọn
cách đó thay vì các cách khác.

## Tổng quan

```
  feat/thêm-jira ──┐
  fix/lệch-timezone ┼── PR ──► main ──FF──► uat ──FF──► prod ──► tag v1.0.0
  chore/nâng-deps ──┘          │            │           │
                            máy dev      máy UAT    production
```

| Nhánh | Vai trò | Ai ghi vào | Môi trường |
|---|---|---|---|
| `feat/*`, `fix/*`, `chore/*` | Việc đang làm | bạn, trực tiếp | máy cá nhân |
| `main` | Trunk. Luôn ở trạng thái deploy được | qua PR (hoặc trực tiếp khi làm một mình) | `make up` ở local |
| `uat` | Bản đang được nghiệm thu | **chỉ** fast-forward từ `main` | máy UAT |
| `prod` | Bản đang chạy thật | **chỉ** fast-forward từ `uat` | production |

## Bất biến của mô hình

> `prod` là ancestor của `uat`, `uat` là ancestor của `main`.

Nói cách khác: mọi commit đang chạy trên production đều đã đi qua UAT, và mọi
commit trên UAT đều đã có trên trunk. Không có ngoại lệ ngoài lúc hotfix, và
ngay sau hotfix phải khôi phục lại.

Bất biến này không phải lời hứa mà là hệ quả của việc **chỉ cho phép
fast-forward**. Nếu `git merge --ff-only` thất bại, nghĩa là nhánh môi trường
đã có commit lạ — dừng lại, đừng tạo merge commit.

Kiểm tra bất cứ lúc nào:

```bash
make git-status
```

Lệnh này in ra ba nhánh đang ở commit nào, những gì đang chờ lên UAT, những gì
đang chờ go-live, và xác nhận chuỗi ancestor còn đúng.

## Vì sao không chọn mô hình khác

**Git Flow** (`develop` + `release/*` + `main` + `hotfix/*`) có nhánh
`release/*` để ổn định một bản phát hành trong khi `develop` vẫn chạy tiếp.
Ở đây `uat` đã làm đúng việc đó, nên thêm `develop` chỉ là một nhánh dài hạn
nữa phải đồng bộ mà không giải quyết vấn đề gì mới.

**Trunk-based thuần với tag** (chỉ `main`, deploy theo tag) sạch hơn về mặt
định danh artifact, nhưng trên server bạn phải có CI hoặc script để trả lời
"tag nào đang là prod". Với nhánh môi trường, server chỉ cần `git pull` trên
nhánh của nó. Ở bối cảnh on-premise chưa có CI runner, đó là lợi thế thật.
Mô hình này vẫn gắn tag trên `prod`, nên bạn có cả hai.

**Nhánh môi trường kiểu tự do** (merge qua lại giữa các nhánh) là thứ làm
mô hình này biến dạng sau vài tháng: prod drift khỏi main, không ai biết
chính xác đang chạy gì. Ràng buộc fast-forward loại bỏ khả năng đó.

## Thao tác thường ngày

### Làm một việc mới

```bash
git checkout main && git pull --ff-only
git checkout -b feat/them-webhook
# ... code, commit ...
git push -u origin feat/them-webhook
```

Mở PR vào `main`. Khi làm một mình có thể commit thẳng vào `main`, nhưng giữ
thói quen nhánh riêng để lúc có team không phải đổi cách làm.

### Đưa lên UAT

```bash
make promote-uat
```

Script sẽ: kiểm tra working tree sạch, fetch remote, xác nhận `uat` không tụt
so với remote, in danh sách commit sắp đưa lên, fast-forward, rồi push.

Trên máy UAT:

```bash
cd /srv/builder-ai/uat
git pull --ff-only
make prod-build && make prod-up
make migrate
make smoke
```

### Go-live

```bash
make promote-prod v=1.0.0
```

Script yêu cầu số phiên bản theo semver, từ chối nếu tag đã tồn tại, nhắc
bạn backup, fast-forward `prod` từ `uat`, gắn tag annotated `v1.0.0`, rồi push
kèm tag.

Nếu `main` đang có commit chưa lên `uat`, script sẽ nói rõ số lượng và **không**
đưa chúng vào lần go-live này. Đó là chủ ý: chỉ những gì đã nghiệm thu được đi.

Trên máy production:

```bash
cd /srv/builder-ai/prod
make backup                      # luôn làm trước khi migrate
git pull --ff-only
make prod-build && make prod-up
make migrate
make health
```

### Rollback

```bash
make rollback-info
```

In tag đang chạy, tag trước đó, và các lệnh cần chạy trên máy prod.

Điểm cần nhớ: **rollback code không rollback database.** Nếu release vừa rồi
có đổi schema thì phải `make downgrade` hoặc restore từ `backups/`. Đây là lý
do `make backup` là bước bắt buộc trước mỗi lần migrate trên prod.

Đừng force-push `prod` về commit cũ. Lịch sử của `prod` chính là lịch sử deploy,
viết lại nó là mất dấu vết. Cứ để `prod` trỏ bản mới, sửa trên `main`, rồi
thăng cấp lại.

## Hotfix

Có hai tình huống, và chọn sai đường sẽ làm vỡ bất biến.

### Trường hợp 1 — `main` chưa có gì chưa phát hành

Nếu `make git-status` cho thấy `main`, `uat`, `prod` cùng một commit: sửa bình
thường trên `main` rồi thăng cấp qua hai bước như thường lệ. Không cần nhánh
đặc biệt. Đây là trường hợp phổ biến và là đường nhanh nhất.

### Trường hợp 2 — `main` đang có việc chưa phát hành

Không thể fast-forward `prod` từ `main` vì sẽ kéo theo cả phần chưa nghiệm thu.
Phải tách nhánh từ `prod`:

```bash
git checkout -b hotfix/sua-loi-500 prod
# ... sửa, commit ...

git checkout prod
git merge --no-ff hotfix/sua-loi-500
git tag -a v1.0.1 -m "hotfix: sửa lỗi 500 ở /agenda"
git push origin prod --follow-tags
```

Xong deploy thì **back-merge ngay**, và đúng thứ tự này:

```bash
git checkout main && git merge --no-ff prod    # main nhận hotfix
git checkout uat  && git merge --ff-only main  # uat bắt kịp main
git push origin main uat
```

Thứ tự quan trọng. Merge `prod` vào `main` trước, rồi fast-forward `uat` từ
`main`, thì chuỗi ancestor được khôi phục hoàn toàn. Làm ngược lại (merge
`prod` vào `uat` trước) sẽ tạo hai merge commit khác nhau ở `uat` và `main`,
và `uat` không còn là ancestor của `main`.

`make git-status` sẽ cảnh báo nếu bạn quên bước back-merge.

## Bảo vệ nhánh trên GitHub

Đặt tại `Settings → Branches` hoặc `Settings → Rules → Rulesets`:

| Nhánh | Cấu hình |
|---|---|
| `main` | Require pull request, require status checks, chặn force-push |
| `uat` | Chặn force-push, chặn xoá nhánh, require linear history |
| `prod` | Như `uat`, thêm giới hạn ai được push |

`require linear history` là cách GitHub bắt buộc ràng buộc fast-forward ở phía
server, không chỉ dựa vào script phía client.

Lưu ý về gói: theo tài liệu GitHub, branch protection và rulesets dùng được
miễn phí trên **repo public**; với **repo private** cần gói Pro, Team hoặc
Enterprise. Nguồn: [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches)
và [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).
Nội dung đã được diễn giải lại cho phù hợp giấy phép.

Nếu repo đang private và chưa muốn nâng gói: script `scripts/release.sh` đã
chặn các lỗi thường gặp ở phía client, đủ dùng khi làm một mình. Khi có team
thì nên nâng gói hoặc chuyển repo sang public.

## Tách môi trường trên một node

Hai môi trường chạy cùng máy thì phải tách tên project, nếu không chúng dùng
chung volume, network và container name rồi tranh nhau.

Bố cục đề xuất: hai bản checkout riêng, mỗi bản một nhánh và một `.env`.

```
/srv/builder-ai/uat    → nhánh uat,  .env có COMPOSE_PROJECT_NAME=builder-uat
/srv/builder-ai/prod   → nhánh prod, .env có COMPOSE_PROJECT_NAME=builder-prod
```

```bash
sudo mkdir -p /srv/builder-ai && cd /srv/builder-ai
git clone -b uat  https://github.com/doanviethung1009/ai_assistant_personal.git uat
git clone -b prod https://github.com/doanviethung1009/ai_assistant_personal.git prod
cd uat  && make env    # rồi sửa .env theo bảng dưới
cd ../prod && make env
```

Khác biệt giữa hai `.env`:

| Biến | UAT | Production |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `builder-uat` | `builder-prod` |
| `ENVIRONMENT` | `staging` | `production` |
| `WEB_PORT` | `3100` | `3000` |
| `API_PORT` | `8100` | `8000` |
| `POSTGRES_PORT` | `5433` | `5432` |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| `CORS_ORIGINS` | `http://uat.local:3100` | `http://app.local:3000` |
| `API_KEY`, `POSTGRES_PASSWORD` | khoá riêng | khoá riêng |

`ENVIRONMENT` ở UAT phải là `staging`. `apps/core/app/core/config.py` khai báo
`Literal["development", "staging", "production"]`, đặt giá trị `uat` sẽ làm
app không khởi động được.

Khoá của UAT và prod phải khác nhau. Nếu dùng chung, một khoá lộ ở UAT là lộ
cả production.

## Vì sao UAT dùng lại `docker-compose.prod.yml`

Không có `docker-compose.uat.yml`, và đó là chủ ý.

`docker-compose.prod.yml` là thứ quyết định artifact: build target `prod`,
không bind mount source, không hot reload, uvicorn nhiều worker, không mở port
database ra host. Nếu UAT chạy một compose file khác thì UAT đang nghiệm thu
một artifact khác với cái sắp lên production — mất phần lớn giá trị của UAT.

Mọi khác biệt giữa hai môi trường là **cấu hình**, và cấu hình nằm trong `.env`.
Vì vậy cả hai nơi đều chạy đúng một lệnh:

```bash
make prod-build && make prod-up
```

## Giới hạn hiện tại: chưa có registry

Image được build tại chỗ trên từng máy, nên khi thăng cấp từ UAT lên prod,
production **build lại** từ cùng commit chứ không nhận đúng bits đã test.
Cùng commit và cùng lockfile thì gần như luôn cho ra image giống nhau, nhưng
"gần như" không phải "chắc chắn": base image có thể đã được cập nhật, và
`apt-get` trong Dockerfile lấy phiên bản mới nhất tại thời điểm build.

Đường nâng cấp khi cần đảm bảo chặt chẽ: dựng một registry, build một lần khi
thăng cấp lên UAT, rồi promote theo **image digest**.

```
main → CI build → registry:sha-abc123 → deploy UAT → deploy prod (cùng digest)
```

Lúc đó nhánh môi trường chỉ còn dùng để ghi lại lịch sử, còn thứ được promote
là digest. Chưa cần ở giai đoạn này, nhưng nên biết giới hạn đang ở đâu.

## Bảng lệnh

| Cần gì | Lệnh |
|---|---|
| Xem ba nhánh đang lệch nhau thế nào | `make git-status` |
| Đưa `main` lên UAT | `make promote-uat` |
| Go-live phiên bản mới | `make promote-prod v=1.0.0` |
| Hướng dẫn rollback | `make rollback-info` |
| Tạo nhánh môi trường lần đầu | `make git-init-branches` |

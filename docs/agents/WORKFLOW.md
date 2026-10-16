# Quy trình đa session (multi-session) không conflict

Repo này có một người làm, nhưng thường chạy song song nhiều session Claude Code. Tài liệu
này mô tả cách để các session **không sửa đè nhau, không đụng chung database hay cổng**, và
session sau đọc lại được việc session trước đã làm.

Khác với `docs/MULTI_AGENT_SYSTEM.md`: tài liệu đó nói về **subagent bên trong một session**
(orchestrator gọi architect, backend-dev...). Tài liệu này nói về **nhiều session độc lập**,
mỗi session ở một worktree riêng. Hai mô hình dùng cùng lúc được: mỗi session thợ vẫn có thể
gọi subagent trong worktree của nó.

**Cách khuyên dùng:** mở task qua **agent view** (mỗi task một session với worktree riêng do
Claude Code tạo ở `.claude/worktrees/`), rồi gọi `/start-task`. Skill nhận ra mình đang ở linked
worktree nên **không tạo worktree thứ hai**: chỉ claim task, đổi tên nhánh theo quy ước và dựng
Docker/DB/cổng riêng ngay tại đó. Chỉ khi đứng ở checkout chính, `/start-task` mới tạo worktree
`../<repo>-T<N>` (rồi User mở session mới ở đó).

## 1. Ba lớp cách ly

| Lớp | Cách ly bằng | Vì sao |
|---|---|---|
| Mã nguồn | Mỗi task một nhánh `<type>/T<N>-<slug>` và một git worktree `../<repo>-T<N>` | Hai session cùng ghi vào một working tree sẽ đè nhau, bất kể chia file thế nào |
| Dữ liệu | Compose project `builder-t<N>`: container, volume, network riêng. DB `builder_ai_t<N>` | Migration hay test của task này không chạm DB của task khác hay stack chính |
| Điều phối | `TASKS.md` trên nhánh `main`, ghi qua `scripts/agents/task-board.sh` | Mọi worktree chung một kho git, nên commit vào ref `main` thì session khác thấy ngay |

Bảng tài nguyên của task `T<N>` (N từ 1 đến 99):

| Tài nguyên | Giá trị | Ví dụ T12 |
|---|---|---|
| Nhánh | `<type>/T<N>-<slug>` | `feat/T12-note-tags` |
| Worktree | `../<repo>-T<N>` (từ checkout chính) hoặc chính worktree agent view đang đứng | `../ai_assistant_personal-T12` |
| Compose project | `builder-t<N>` | `builder-t12` (container `builder-t12-api`...) |
| Database | `builder_ai_t<N>`, test `builder_ai_t<N>_test` | `builder_ai_t12` |
| Cổng web / api | `3100+N` / `8100+N` | `3112` / `8112` |
| Cổng postgres / redis | `5500+N` / `6400+N` | `5512` / `6412` |

Stack chính (checkout không có `.env.worktree`) giữ nguyên tên `builder-ai` và cổng
3000/8000/5432/6379. Không task nào được trỏ vào stack chính. Với VM dev Proxmox (có dữ liệu
thật) chỉ đi qua các lệnh có kiểm soát ở mục 9 (`make devvm-*`), không tự SSH sửa tay.

### Cơ chế

- `scripts/agents/new-worktree.sh` sinh `.env.worktree` trong worktree (tên project, tên DB, cổng).
- `Makefile` thấy file đó thì `include` và `export` các biến, rồi gọi
  `docker compose -p builder-t<N> -f docker-compose.yml -f docker-compose.worktree.yml`.
  File override đổi tên container và network cố định thành tên theo project.
- Nhờ vậy **mọi lệnh `make` quen thuộc** (`make up`, `make migrate`, `make test`, `make smoke`,
  `make psql`) tự chạy trên stack của worktree, không phải nhớ cờ nào.
- `.env` của worktree được sinh mới bằng `scripts/gen-env.sh` (khoá ngẫu nhiên riêng), không
  chép từ checkout chính. Cần đăng nhập Google trong worktree thì tự bổ sung `AUTH_GOOGLE_*`.

## 2. Vai trò

- **Session điều phối** (thường mở ở checkout chính): chia việc thành task, thêm task vào
  bảng (`task-board.sh add`), ghi quyết định chung (`decide`), trả lời mục "Cần phối hợp",
  review và merge PR, cập nhật `docs/AI_HANDOFF_STATE.md`. Session điều phối không code tính năng.
- **Session thợ** (mở trong worktree của một task): chỉ làm đúng một task, chỉ sửa file trong
  phạm vi đã khai báo, cuối session viết handoff.

## 3. Vòng đời một task

```
todo ──claim──► claimed ──code──► in-progress ──PR──► review ──merge──► done
      start-task            (session thợ)      finish-task      cleanup-task
```

| Bước | Ai | Lệnh / skill |
|---|---|---|
| 1. Thêm task | điều phối | `scripts/agents/task-board.sh add T12 "Mô tả" "apps/web/app/notes/**"` |
| 2. Nhận task và dựng môi trường | thợ hoặc điều phối | skill `start-task` (claim rồi `new-worktree.sh`; ở linked worktree thì dùng luôn worktree đó, không tạo mới) |
| 3. Mở session trong worktree | User | Cách khuyên dùng: mở task từ agent view rồi `/start-task` (bỏ qua bước này). Từ checkout chính: `cd ../ai_assistant_personal-T12 && claude` |
| 4. Code và test | thợ | commit nhỏ, `make lint`, `make test`, `make smoke` |
| 5. Cập nhật theo main | thợ | skill `sync-main` (khi main có thay đổi liên quan) |
| 6. Mở PR | thợ | skill `finish-task` (lint, test, rebase hoặc merge origin/main, push sau khi User đồng ý, PR, trạng thái `review`, handoff) |
| 7. Review và merge | điều phối và User | subagent `code-reviewer`, merge trên GitHub |
| 8. Dọn | điều phối | skill `cleanup-task` (xoá Docker, worktree, nhánh; trạng thái `done`) |

Session nào kết thúc giữa chừng cũng phải chạy skill `handoff` để session sau tiếp tục được.

## 4. Luật bắt buộc

1. **Không code trên `main`.** Ngoại lệ duy nhất là commit bảng điều phối do `task-board.sh`
   tạo (chỉ đổi `TASKS.md`). Đừng checkout `main` ở worktree nào: script sẽ từ chối ghi bảng.
2. **Claim trước khi code.** Không làm task đã có người claim (`task-board.sh claim` tự từ chối).
3. **Chỉ sửa file trong phạm vi.** Cần sửa ngoài phạm vi thì
   `task-board.sh coord T12 "cần thêm field x vào lib/types.ts"` rồi dừng lại hỏi User.
4. **Không sửa file dùng chung** trừ khi phạm vi task ghi rõ: `uv.lock`, `package-lock.json`,
   `pyproject.toml`, `package.json`, `docker-compose*.yml`, `Makefile`, `.env.example`,
   `apps/core/alembic.ini`, `apps/core/migrations/**`, `CLAUDE.md`, `AGENTS.md`, `.agents/**`,
   `.claude/**`, `apps/web/lib/types.ts`, `apps/web/lib/api.ts`. Rule theo đường dẫn ở
   `.agents/rules/{migrations,root-config,core-shared}.md` nhắc lại khi mở các file này.
5. **Migration:** mỗi migration một file mới, tên có timestamp (tự sinh bằng `make migration`).
   Không sửa migration đã merge. Chỉ `make migrate` trong worktree của mình.
6. **Commit nhỏ, Conventional Commits** (skill `git-commit`). Rebase lên `origin/main` trước khi
   mở PR. `git push` luôn hỏi User.
7. **Kết thúc session phải viết handoff** (`docs/agents/handoffs/YYYY-MM-DD-T<N>.md`).

## 5. Khi phát hiện conflict

| Tình huống | Cách xử lý |
|---|---|
| Rebase/merge báo conflict ở file trong phạm vi task | Sửa, chạy lại `make lint` và `make test`, rồi `git rebase --continue` (hoặc `git commit` nếu đang merge) |
| Conflict ở file ngoài phạm vi (task khác sở hữu) | `git rebase --abort` (hoặc `git merge --abort`), ghi `task-board.sh coord`, hỏi User. Không tự chọn phía |
| Hai nhánh cùng sinh migration từ một `down_revision` (Alembic báo *multiple heads*) | Nhánh merge SAU sửa `down_revision` của migration mình trỏ vào head mới, chạy lại `make migrate` trên DB riêng. Không dùng `alembic merge` khi chưa hỏi User |
| `task-board.sh claim` báo task đã có người nhận | Chọn task khác, hoặc hỏi User. Không sửa tay bảng |
| `task-board.sh` báo `main` đang checkout ở worktree X | Đổi worktree X sang nhánh khác (`git switch <nhánh>`), chạy lại |
| Cổng đã có tiến trình nghe | `scripts/agents/list-worktrees.sh` xem ai đang dùng; thường là stack cũ của chính task đó |

## 6. Checklist trước khi mở PR

- [ ] `git diff --stat origin/main...HEAD` chỉ có file trong phạm vi task (hoặc đã ghi phối hợp và User đồng ý).
- [ ] Không đổi `TASKS.md` trong nhánh (bảng chỉ đổi qua `task-board.sh`).
- [ ] Đã cập nhật theo `origin/main` mới nhất (rebase nếu nhánh chưa push, merge nếu đã push), không còn conflict.
- [ ] `make lint` qua; `make test` qua; có đổi backend thì `make smoke` qua.
- [ ] Migration mới (nếu có): một head duy nhất (`make history`), có `downgrade()`, đã `make migrate` trên DB riêng.
- [ ] Docs liên quan đã cập nhật; file `.md` mới đã đăng ký trong `apps/web/lib/docs.ts`.
- [ ] Commit theo Conventional Commits, không có file rác hay secret.
- [ ] Handoff đã viết trong `docs/agents/handoffs/`.

## 7. Lệnh tham khảo

```bash
scripts/agents/task-board.sh show          # bảng hiện tại trên main
scripts/agents/task-board.sh next-id       # ID tiếp theo còn trống
scripts/agents/list-worktrees.sh           # worktree, DB, cổng, Docker, trạng thái
scripts/agents/new-worktree.sh T12 note-tags --type feat   # ở linked worktree tự dùng --here; --new để ép tạo mới
scripts/agents/remove-worktree.sh T12      # hỏi trước khi xoá volume DB
scripts/agents/task-board.sh sync          # sau khi PR merge: main local theo origin/main
```

Mọi script có `--help`, chạy lại nhiều lần không hỏng, và từ chối thao tác trên tài nguyên
không mang prefix `builder-t<N>` / `builder_ai_t<N>`.

## 8. Giới hạn đã biết

- Không có Docker local thì `new-worktree.sh` vẫn tạo nhánh, worktree và `.env.worktree`, bỏ qua
  bước dựng DB và báo rõ. Khi đó kiểm chứng backend đi theo mục 9 (chạy trên VM dev).
- Mỗi worktree build image `api`/`web` riêng lần đầu (chậm, tốn đĩa). `remove-worktree.sh` xoá image đó.
- Commit bảng nằm ở `main` local cho tới khi User push. `task-board.sh sync` gom chúng lên trên
  `origin/main` sau mỗi lần PR merge.
- Task chỉ đánh số T1..T99 vì cổng tính theo số task.

## 9. Máy không có Docker: local chỉ chạy nhanh web, kiểm chứng chính trên VM dev (T8)

Máy dev chính của dự án không cài Docker. Quy ước (User chốt 2026-10-16):

- **Local** chỉ để sửa và xem nhanh code **web**: `make devvm-web` chạy web trên host với
  `DATA_SOURCE=api`, gọi API của VM dev qua SSH tunnel. Không dựng core/DB ở local.
- **Kiểm chứng backend** chạy trên **VM dev Proxmox** (`ai-dev-01`), dùng backend của chính VM đó.

Hai cách chạy trên VM, **cách ly với DB thật** (ưu tiên, dùng cho mọi task đổi `apps/core`):

| Muốn biết | Lệnh | Cách ly bằng |
|---|---|---|
| ruff + migration lên head + pytest | `make devvm-test` (lọc: `make devvm-test K=tag`) | Postgres tạm trên tmpfs, network riêng, hàng đợi một lượt |
| smoke E2E qua HTTP thật | `make devvm-smoke [REF=<commit>]` | stack tạm riêng (cổng 18000), xuất đúng commit bằng `git archive` |

Ở máy có Docker thì `make lint`, `make test`, `make smoke` tương đương. CI GitHub
(`.github/workflows/ci.yml`) chạy lại ruff, alembic, pytest, tsc khi mở PR: đó là cổng cuối, đừng
dùng CI làm chỗ phát hiện lỗi đầu tiên (chậm, mỗi lần một PR).

**Xem backend của nhánh chạy thật** (khi cần mở giao diện với dữ liệu dev thật):

```bash
git push                                            # nhánh phải có trên origin (hỏi User như mọi lần push)
make devvm-branch BRANCH=feat/T12-x TASK=T12        # sao lưu DB, khoá, checkout nhánh trên VM
make devvm-web                                      # web của worktree gọi API dev (qua tunnel)
make devvm-restore                                  # XONG PHẢI TRẢ VỀ main, nhả khoá
make devvm-status                                   # ai đang giữ VM dev
```

Luật của `devvm-branch` (script `scripts/agents/dev-vm-branch.sh`, banner đầu file ghi đủ):

1. **Một nhánh tại một thời điểm.** Khoá `~/dev-branch.lock` trên VM; task khác phải chờ `restore`.
2. **Luôn sao lưu DB trước** (`make backup` trên VM, file ở `/srv/builder-ai/dev/backups/`).
3. **Từ chối nhánh có migration mới** trừ khi `--allow-migration`: `restore` chỉ đổi mã, không
   downgrade schema, nên migration đã chạy nằm lại trong DB thật. Thử migration bằng `make devvm-smoke`.
4. **Chỉ api đổi theo nhánh.** Container `web` trên VM là image dựng sẵn, không có mã web của nhánh;
   xem web của nhánh bằng `make devvm-web` ở worktree.
5. **`restore` không kéo `origin/main`** (tránh vô tình nâng schema DB thật); nâng dev lên main mới
   là việc riêng, có sao lưu.
6. VM chỉ ~3.4 GB RAM: không build image web/api trên VM để thử nhánh; mỗi lần một lượt test.

Việc cần Docker thật (sửa `docker-compose*.yml`, Dockerfile) thì không kiểm chứng được ở đây: ghi rõ
trong PR là chưa chạy, để CI hoặc User chạy ở máy có Docker.

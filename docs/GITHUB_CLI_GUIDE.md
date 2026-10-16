# GitHub CLI (`gh`): vận hành task, nhiều session và nhiều agent

> **Lưu ý:** quy ước "số issue là mã task" sẽ được `scripts/agents/task-board.sh` hỗ trợ sau T3. Cho đến lúc đó, `TASKS.md` và mã `T<N>` (nhánh `<type>/T<N>-<slug>`) vẫn là cơ chế claim chính thức; số issue dùng song song để theo dõi trên GitHub.

Tài liệu này giải thích `gh` là gì, các lệnh dùng hằng ngày, và cách dùng nó làm **bảng điều phối** khi chạy nhiều task, nhiều session Claude Code và nhiều subagent cùng lúc trên repo này.

Đọc cùng: `docs/agents/WORKFLOW.md` (worktree, DB/cổng riêng), `docs/git-workflow.md` (nhánh `main → uat → prod`), `docs/MAKE_COMMANDS.md` (lệnh `make`).

---

## 1. `gh` là gì, khác `git` ở đâu

| Công cụ | Làm việc với | Ví dụ |
|---|---|---|
| `git` | Mã nguồn và lịch sử commit, trên máy anh | `git switch`, `git commit`, `git push`, `git worktree` |
| `gh` | **Các thứ chỉ có trên GitHub**: issue, label, pull request, CI (Actions), review | `gh issue create`, `gh pr merge`, `gh pr checks` |

`git` không biết issue hay PR là gì. `gh` không thay `git`, nó bổ sung phần "quản lý dự án" để làm từ terminal thay vì bấm trên web. Claude Code cũng dùng `gh` để mở PR và đọc issue.

### Cài và đăng nhập (một lần)

```bash
brew install gh          # macOS
gh auth login            # chọn GitHub.com → HTTPS → đăng nhập qua trình duyệt
gh auth status           # kiểm tra đã đăng nhập, có quyền repo chưa
```

Mọi lệnh `gh` chạy trong thư mục repo sẽ tự hiểu repo là `doanviethung1009/ai_assistant_personal`. Ở thư mục khác thì thêm `-R doanviethung1009/ai_assistant_personal`.

---

## 2. Bốn khái niệm cần nắm

| Khái niệm | Là gì | Trong repo này dùng để |
|---|---|---|
| **Issue** | Một đầu việc có số (`#47`), tiêu đề, mô tả, bình luận | **Mỗi task là một issue.** Số issue là mã task duy nhất |
| **Label** | Nhãn gắn vào issue/PR | Trạng thái task: `in-progress`, `review`, `blocked` |
| **Pull request (PR)** | Đề nghị gộp một branch vào `main` | Mỗi task kết thúc bằng một PR, mô tả ghi `Closes #47` |
| **Checks (CI)** | Kiểm tra tự động chạy trên PR: workflow `CI` (`.github/workflows/ci.yml`) gồm job `backend` (ruff, alembic, pytest) và `web` | Theo quy ước, chỉ merge khi check xanh |

Liên kết giữa chúng là **một số duy nhất**:

```
Issue #47  →  branch docs/47-optimize  →  session "#47 docs"  →  PR "Closes #47"  →  merge  →  issue #47 tự đóng
```

---

## 3. Quy ước đặt tên

| Thứ | Quy ước | Ví dụ |
|---|---|---|
| Issue | Tiêu đề là kết quả mong muốn; mô tả có dòng `Phạm vi:` | `Tối ưu giao diện trang Task` |
| Branch | `<type>/<số-issue>-<slug>` (type theo Conventional Commits) | `feat/48-task-ui`, `docs/47-optimize`, `fix/52-login-redirect` |
| Session agent view | `#<số> <tên ngắn>` (đặt bằng `Ctrl+R`) | `#48 task UI` |
| PR | Tiêu đề theo Conventional Commits; mô tả có `Closes #<số>` | `feat(web): tối ưu giao diện trang Task` |

`Closes #48` (hoặc `Fixes #48`) trong mô tả PR làm GitHub tự đóng issue khi PR merge vào `main`.

### Label dùng cho trạng thái (tạo một lần)

```bash
gh label create in-progress --color FBCA04 --description "Đang có session làm"
gh label create review      --color 0E8A16 --description "Đã mở PR, chờ review"
gh label create blocked     --color D93F0B --description "Chờ User quyết hoặc chờ task khác"
gh label create migration   --color 5319E7 --description "Task có migration Alembic"
```

| Trạng thái | Dấu hiệu |
|---|---|
| Chờ làm | Issue mở, không có label trạng thái |
| Đang làm | Label `in-progress` |
| Chờ review | Label `review`, có PR liên kết |
| Bị chặn | Label `blocked` + bình luận lý do |
| Xong | Issue đóng (PR đã merge) |

Label `migration` giúp nhìn nhanh: **không bao giờ có hai issue `migration` cùng `in-progress`**.

---

## 4. Lệnh hằng ngày

### Issue

```bash
gh issue create --title "Tối ưu tài liệu docs/" \
  --body "Phạm vi: docs/*.md (trừ docs/agents/, docs/specs/)"   # tạo task
gh issue list                                   # mọi task đang mở
gh issue list --label in-progress               # task đang có người làm
gh issue list --state closed --limit 10         # 10 task xong gần nhất
gh issue view 47                                # đọc chi tiết + bình luận
gh issue view 47 --web                          # mở trên trình duyệt
gh issue edit 47 --add-label in-progress        # đổi trạng thái
gh issue edit 47 --remove-label in-progress --add-label review
gh issue comment 47 --body "Pha 1 xong, chờ duyệt."   # ghi chú/handoff ngắn
gh issue close 47 --comment "Huỷ: trùng #45"    # đóng tay khi huỷ
```

### Pull request

```bash
gh pr create --fill                          # mở PR từ branch hiện tại, lấy tiêu đề/mô tả từ commit
gh pr create --title "feat(web): ..." --body "Closes #48"
gh pr list                                   # PR đang mở
gh pr view 48                                # chi tiết PR
gh pr view 48 --json state,mergedAt          # PR đã merge chưa (dùng trong script)
gh pr diff 48 --name-only                    # PR sửa những file nào (kiểm phạm vi)
gh pr checks 48                              # CI xanh hay đỏ
gh pr checks 48 --watch                      # chờ CI chạy xong
gh pr merge 48 --squash --delete-branch      # gộp vào main, xoá branch trên GitHub
gh pr checkout 48                            # kéo branch của PR về máy để thử
```

### CI và repo

```bash
gh run list --limit 5            # các lần CI chạy gần nhất
gh run view <id> --log-failed    # xem log bước bị lỗi
gh repo view --web               # mở repo trên trình duyệt
```

### Đọc kết quả `gh pr view --json state`

| `state` | Nghĩa | Việc tiếp |
|---|---|---|
| `OPEN` | Chưa merge | Review, chờ CI |
| `MERGED` | Đã gộp vào `main` | `git pull`, dọn worktree/branch |
| `CLOSED` | Đóng mà không merge | Branch không vào `main`, đừng xoá nếu còn cần |

---

## 5. Ba tầng song song: task, session, agent

| Tầng | Là gì | Công cụ | Giới hạn |
|---|---|---|---|
| **Multi-task** | Nhiều đầu việc trong backlog | `gh issue` | Không giới hạn, chỉ là danh sách |
| **Multi-session** | Nhiều phiên Claude Code chạy cùng lúc, mỗi phiên một worktree | Agent view (`claude agents`) | **Tối đa 2 session thợ** (quy ước hiện tại, theo quota gói Pro) |
| **Multi-agent** | Subagent bên trong một session: `architect`, `backend-dev`, `frontend-dev`, `code-reviewer`, `db-reviewer`, `security-auditor`, `devops`, `work-tracker` (`.claude/agents/`) và `Explore` (có sẵn trong Claude Code) | Subagent | Tự do, nhưng mỗi subagent cũng tốn quota |

Nguyên tắc: **backlog thì dài, nhưng chỉ 2 issue `in-progress` cùng lúc.** Subagent dùng cho việc đọc nhiều hoặc review, để context của session chính gọn.

### Vai trò

| Vai | Ở đâu | Làm gì |
|---|---|---|
| **Điều phối** (User + 1 session) | Checkout chính, luôn ở `main` | Tạo issue, giao việc, review PR, merge. Không code |
| **Thợ** (≤ 2 session) | Agent view, worktree trong `.claude/worktrees/` | Làm đúng một issue, mở PR, hỏi trước khi push |
| **Subagent** | Trong session thợ | `Explore` đọc rộng, `code-reviewer` trước PR, `db-reviewer` khi có migration, `security-auditor` khi chạm auth |

---

## 6. Khi nào hai task chạy song song được

Phải thoả **cả ba**:

1. **Khác vùng file** (ví dụ một bên `docs/`, một bên `apps/web/app/tasks/**`).
2. **Không cùng có migration** (cùng lúc hai issue label `migration` sẽ sinh hai head Alembic).
3. **Không cùng sửa file dùng chung.** Danh sách chính thức nằm ở hai luật; khi có khác biệt thì luật thắng:
   - `.agents/rules/root-config.md` (cấu hình gốc): `Makefile`, `docker-compose*.yml`, `.env.example`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`, `TASKS.md`, `.claude/settings.json`, `.claude/agents/**`, `.agents/**`, `.github/**`, `infra/**`, lockfile và file khai báo dependency (`apps/core/pyproject.toml`, `apps/core/uv.lock`, `apps/web/package.json`, `apps/web/package-lock.json`).
   - `.agents/rules/core-shared.md` (lõi dùng chung): `apps/core/app/core/**`, `apps/core/app/db/**`, `apps/core/app/main.py`, `apps/core/app/schemas/common.py`, `apps/core/app/services/errors.py`, `apps/core/app/services/clock.py`, `apps/web/lib/api.ts`, `apps/web/lib/types.ts`, `apps/web/lib/generated/**`, `apps/web/app/actions.ts`, `apps/web/middleware.ts`, `apps/web/auth.ts`.
   - Ngoài hai luật, hai nơi **thực tế** hay bị hai task cùng đụng nên cũng nên giao cho một task: `apps/web/lib/docs.ts` (mỗi file `.md` mới phải đăng ký vào đây, AGENTS.md 3.3) và `scripts/agents/**`. Migration/model là vùng dùng chung riêng (`.agents/rules/migrations.md`).

Nếu hai task cần chung một file, **giao file đó cho đúng một task** và ghi vào phần `Phạm vi:` của issue. Task còn lại ghi rõ "không đụng file X".

---

## 7. Ví dụ vận hành: tối ưu tài liệu + tối ưu giao diện trang Task

### 7.1. Chia chủ file trước

| File giao nhau | Task docs | Task UI | Giao cho |
|---|---|---|---|
| `apps/web/lib/docs.ts` | Gộp/xoá tài liệu phải sửa danh sách tab Tài liệu | Không cần | Task docs |
| `docs/huong-dan-su-dung.md` | Thuộc `docs/` | Đổi UI phải cập nhật hướng dẫn (AGENTS.md 3.10) | Task UI |

### 7.2. Tạo issue

```bash
gh issue create --title "Tối ưu tài liệu docs/" --body "Phạm vi: docs/*.md (trừ docs/agents/, docs/specs/, docs/huong-dan-su-dung.md) + apps/web/lib/docs.ts. Không sửa apps/web khác."
# → #47

gh issue create --title "Tối ưu giao diện trang Task" --body "Phạm vi: apps/web/app/tasks/**, apps/web/components/task-*.tsx, apps/web/app/globals.css (nếu cần), docs/huong-dan-su-dung.md. Không sửa lib/api.ts, lib/types.ts, apps/core."
# → #48
```

### 7.3. Giao việc trong agent view

Mở `claude` ở checkout chính, để trống ô prompt, bấm `←`. Gõ từng prompt vào ô dưới cùng, mỗi prompt một lần `Enter`.

**#47 docs:**
```
Làm issue #47 (gh issue view 47). Gắn label in-progress.
Pha 1 (CHỈ ĐỌC): dùng subagent Explore kiểm kê docs/*.md trong phạm vi: file lỗi thời so với code trên main, trùng lặp, quá dài, chưa đăng ký trong apps/web/lib/docs.ts. Đăng bảng File | Vấn đề | Đề xuất | Ưu tiên lên issue bằng gh issue comment 47. DỪNG chờ tôi duyệt.
Pha 2: branch docs/47-optimize, sửa theo mục đã duyệt, sửa link nội bộ bị gãy, cập nhật docs.ts. Không đụng docs/huong-dan-su-dung.md. PR ghi "Closes #47", đổi label sang review. Hỏi tôi trước khi push.
```

**#48 task UI:**
```
Làm issue #48 (gh issue view 48). Gắn label in-progress.
Pha 1 (CHỈ ĐỌC): rà trang /tasks và task-item, task-section, task-summary: bố cục, khoảng cách, chữ, responsive, trạng thái loading/rỗng/lỗi, số lần gọi API. Đăng đề xuất theo ưu tiên lên issue. DỪNG chờ tôi duyệt.
Pha 2: branch feat/48-task-ui, sửa theo mục đã duyệt, chỉ trong phạm vi. Cập nhật docs/huong-dan-su-dung.md nếu đổi cách dùng. Chạy tsc + vitest, skill qc-uat, subagent code-reviewer. PR ghi "Closes #48", đổi label sang review. Hỏi tôi trước khi push.
```

Đặt tên hai dòng bằng `Ctrl+R`: `#47 docs`, `#48 task UI`.

### 7.4. Theo dõi

```
Needs input
 ✻ #47 docs      Bảng kiểm kê đã đăng lên issue, chờ duyệt
Working
 ✽ #48 task UI   Đang đọc components/task-item.tsx
```

- Đọc đề xuất: `gh issue view 47` hoặc chọn dòng rồi `Space`.
- Duyệt: trả lời trong session, ví dụ "Duyệt mục 1, 2, 4; bỏ mục 3. Làm pha 2."
- Task UI: yêu cầu session chạy web để xem bằng mắt trước khi duyệt PR.

### 7.5. Merge

```bash
gh pr list                                # thấy PR của #47 và #48
gh pr diff <số-PR> --name-only            # kiểm đúng phạm vi
gh pr checks <số-PR>                      # CI xanh
gh pr merge <số-PR> --squash --delete-branch
git pull                                  # ở checkout chính
```

Dọn worktree, DB riêng và branch của task đã merge: skill `cleanup-task`.

Sau PR đầu tiên, nhắn session còn lại: "main vừa có thay đổi, merge origin/main vào branch của bạn." Xong cả hai: xoá session trong agent view (`Ctrl+X` hai lần). Issue tự đóng nhờ `Closes #`.

---

## 8. Vòng làm việc mỗi ngày

| Lúc | Việc | Lệnh |
|---|---|---|
| Đầu ngày | Xem backlog và việc dở | `gh issue list`, `gh issue list --label in-progress`, `gh pr list` |
| | Chọn ≤ 2 issue theo mục 6 | Session điều phối: "Đề xuất 2 issue làm song song hôm nay" |
| | Giao việc | Agent view: `←`, gõ prompt, `Enter`, `Ctrl+R` đặt tên |
| Trong ngày | Trả lời session chờ | `claude agents`, lọc `s:blocked`, `Space` |
| | Review PR xanh | `gh pr checks`, `gh pr diff --name-only`, `gh pr merge` |
| Sau mỗi merge | Cập nhật | `git pull`; báo session còn lại merge `origin/main` |
| Cuối ngày | Task chưa xong | Trong session: `/handoff`, rồi `gh issue comment <số> --body "Dở: ..."` |

Hôm sau tiếp tục một issue dở: mở session mới và nói "Đọc gh issue view <số> và handoff mới nhất, làm tiếp".

---

## 9. Một task lớn: đọc trước, sửa sau

Task kiểu "rà và tối ưu toàn bộ X" không giao một lần. Làm hai pha:

1. **Issue kiểm kê (chỉ đọc)**: một session dùng subagent `Explore` đọc, đăng đề xuất lên issue, không tạo branch.
2. **Issue sửa theo nhóm**: User duyệt đề xuất, tạo 2–5 issue con, mỗi issue một nhóm file không chồng nhau. Ghi `Phần của #47` trong mô tả để liên kết.

Pha 1 chỉ đọc nên tốn ít quota và không sinh conflict; chạy song song với task khác thoải mái.

---

## 10. Quy tắc an toàn

| Quy tắc | Lý do |
|---|---|
| Checkout chính luôn ở `main`; `git status -sb` thấy `ahead` hoặc branch khác thì dừng hỏi | Checkout chính là nơi điều phối và `git pull` |
| Agent không push khi chưa hỏi; không force push (hook `.claude/hooks/guard-bash.sh` chặn mọi `git push` có `--force` hoặc `-f`, kể cả `--force-with-lease`) | Lịch sử chung trên GitHub không bị ghi đè |
| Cần force push thì User tự gõ `! git push --force-with-lease ...` | Chỉ người mới được viết lại lịch sử |
| Merge bằng `--squash` | Mỗi task một commit trên `main`, dễ revert |
| Sau squash merge, `git branch -d` báo "not fully merged" là bình thường; kiểm `gh pr view <số> --json state` = `MERGED` rồi mới `git branch -D` | Squash tạo commit mới nên git không nhận ra |
| Chạm VM dev hoặc dữ liệu thật: `pg_dump` trước, hỏi User | Dữ liệu dev là dữ liệu thật |

---

## 11. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `gh: To get started with GitHub CLI, please run: gh auth login` | Chưa đăng nhập | `gh auth login` |
| `gh pr create` báo PR đã tồn tại | Branch đã có PR | Push thêm commit là PR tự cập nhật |
| Issue không tự đóng sau merge | Mô tả PR thiếu `Closes #<số>`, hoặc PR merge vào nhánh khác `main` | `gh issue close <số>` |
| Push bị hook chặn "force push bị cấm" | Rebase branch đã push | Dùng merge `origin/main` thay rebase (skill `finish-task`, `sync-main`), hoặc User tự force push |
| `gh pr create` / `git commit` bị hook `guard-bash.sh` chặn dù không phải force push hay xoá volume | Hook quét cả chuỗi lệnh, nên cụm lệnh nguy hiểm nằm trong `--body` hay message cũng bị chặn | Diễn đạt lại câu chữ, đừng gỡ hook |
| `git worktree remove` từ chối | Còn file untracked hoặc session đang đứng trong đó | Đóng session; kiểm file; `--force` nếu chắc chắn là rác |
| Hai session sửa cùng một file | Phạm vi issue chồng nhau | Dừng một session, giao file cho một issue, ghi lại `Phạm vi:` |

---

## 12. Bảng tra nhanh

| Muốn | Lệnh |
|---|---|
| Tạo task | `gh issue create --title "..." --body "Phạm vi: ..."` |
| Xem việc đang làm | `gh issue list --label in-progress` |
| Xem session nào chờ mình | `claude agents` rồi gõ `s:blocked` |
| Xem PR chờ merge | `gh pr list` |
| Kiểm PR sửa đúng phạm vi | `gh pr diff <số> --name-only` |
| Kiểm CI | `gh pr checks <số>` |
| Merge | `gh pr merge <số> --squash --delete-branch` |
| PR đã merge chưa | `gh pr view <số> --json state` |
| Ghi chú dở dang | `gh issue comment <số> --body "..."` |

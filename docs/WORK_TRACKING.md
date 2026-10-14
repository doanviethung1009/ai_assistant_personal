# Quản lý công việc của dự án

Cách kiểm kê "đang làm / đã xong / chờ / treo" cho repo này. Gồm ba phần cùng nhau: tài liệu này, skill `work-tracking` (`.agents/skills/work-tracking/SKILL.md`) và subagent `work-tracker` (`.claude/agents/work-tracker.md`).

## Vì sao cần
Trạng thái nằm rải ở ba nơi: spec (`docs/specs/`), git (nhánh, thay đổi chưa commit) và `docs/AI_HANDOFF_STATE.md`. Mỗi nơi có thể lỗi thời; chỉ đối chiếu chéo mới biết thật.

## Mô hình trạng thái
| Trạng thái | Nghĩa | Bằng chứng |
|---|---|---|
| Chờ | Spec DRAFT chờ User duyệt, hoặc spec CHỐT chưa có code | dòng `Trạng thái:` trong spec |
| Đang làm | Có code chưa commit hoặc nhánh chưa merge | `git status`, `git branch --no-merged main` |
| Xong | Đã merge vào `main`, có docs, đã QC | `git log main`, handoff ghi đã kiểm |
| Treo | Ghi "chưa làm/chưa kiểm" nhưng không ai nhận | handoff không có nhánh/spec tương ứng |

"Code xong" chưa phải "Xong": theo AGENTS.md 3.10 còn phải có docs và QC.

## Cách dùng
- Hỏi nhanh: *"Dùng work-tracker kiểm tra đang làm gì, đã làm gì, còn treo gì."*
- Hoặc gọi skill: *"Dùng skill work-tracking."*
- Cuối session lớn: để orchestrator cập nhật `AI_HANDOFF_STATE.md` theo bước 5 của skill.

## Vòng đời một đầu việc
Spec DRAFT → User duyệt (CHỐT) → code (backend-dev/frontend-dev) → review (code-reviewer) → QC (`qc-uat`) → commit (`git-commit`) → merge → Xong. Mỗi mũi tên là một chỗ việc có thể bị treo.

## Ảnh chụp ngày 2026-10-13 (nhánh `feat/auth-multiuser`)
- **Đang làm:** epic đăng nhập đa người dùng (`docs/specs/auth-multiuser.md`, CHỐT): ~107 file thay đổi chưa commit, gồm migration `b2f7a9c1d4e6` (users, ownership) và `e8a3c6f2b1d7` (`tasks.reporter`); epic Jira reporter (`docs/specs/jira-reporter.md`, CHỐT) code xong, commit sau auth; giảm request/`/team` lai và skill `nextjs-rendering` (chưa commit).
- **Chờ:** `docs/specs/user-timezone.md` ghi DRAFT dù code đã vào `main` (spec lỗi thời, cần cập nhật); `docs/specs/proxmox-deploy.md` DRAFT còn Q1, Q6.
- **Xong (đã vào main):** đồng bộ Jira theo người, dải tóm tắt task và tab Tham dự dự án, múi giờ chọn được, sửa CI Trivy, hạ tầng Proxmox dev.
- **Treo:** thiếu `pyjwt` trong `pyproject.toml`/`uv.lock`, 3 lỗi E501, `dev-vm-backend-test.sh` hỏng; `make smoke`/`gen-types` chưa chạy; bản Python sửa project theo Company chưa làm; nâng `xlsx` (CVE); nhánh `feat/*` cũ chưa dọn.

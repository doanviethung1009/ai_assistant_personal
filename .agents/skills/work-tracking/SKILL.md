---
name: work-tracking
description: Quy trình kiểm kê và quản lý công việc của dự án - xác định việc đang làm, đã xong, đang chờ, bị treo từ spec, git và handoff; cập nhật AI_HANDOFF_STATE đúng chuẩn. Dùng khi User hỏi tiến độ ("đang làm gì", "đã làm gì", "còn gì"), bắt đầu/kết thúc session lớn, hoặc cần bàn giao.
---

# Quản lý công việc

Mục đích: trả lời đúng "đang làm gì / đã xong gì / còn treo gì" bằng bằng chứng, không bằng trí nhớ. Mô hình trạng thái và ví dụ: `docs/WORK_TRACKING.md`.

## Bước 1 - Thu thập (chỉ đọc)
```bash
git status --short
git branch --no-merged main
git log --oneline main..HEAD
git log --oneline -15
grep -n "Trạng thái" docs/specs/*.md
```
Rồi đọc các mục cuối `docs/AI_HANDOFF_STATE.md` (mục có chữ "chưa commit", "chưa merge", "Chưa làm", "Việc còn lại").

## Bước 2 - Phân loại (mỗi việc đúng một trạng thái)
| Trạng thái | Điều kiện |
|---|---|
| Đang làm | Có thay đổi chưa commit, hoặc nhánh chưa merge vào `main` |
| Chờ | Spec DRAFT chờ User duyệt, hoặc spec CHỐT chưa có code |
| Xong | Đã merge vào `main` và handoff ghi đã kiểm |
| Treo | Handoff ghi "chưa kiểm/chưa làm" nhưng không có nhánh/spec nhận |

Khác biệt "code xong" và "xong": code xong nhưng chưa QC (`qc-uat`), chưa có docs hoặc chưa merge thì vẫn là **Đang làm**.

## Bước 3 - Đối chiếu chéo
- Spec CHỐT mà không có commit/nhánh → Chờ hoặc Treo.
- Migration `??` chưa commit → thuộc epic nào? Thứ tự `down_revision` có đúng không?
- Handoff nói "chưa commit" nhưng `git log` đã có → handoff lỗi thời.

## Bước 4 - Báo cáo
Bảng theo 4 nhóm, mỗi dòng: việc, bằng chứng (nhánh/hash/file), việc kế tiếp. Tối đa 3 đề xuất ưu tiên. Không bịa phần trăm.

## Bước 5 - Cập nhật handoff (chỉ orchestrator)
Khi User cho phép, thêm một mục mới ở cuối `docs/AI_HANDOFF_STATE.md` theo mẫu: nhánh, spec, đã code, chưa kiểm, rủi ro, việc kế tiếp; sửa dòng "Bản cập nhật cuối cùng". Subagent `work-tracker` chỉ đề xuất, không tự sửa.

## Không làm
- Không commit/push chỉ để "đóng" một việc (xem skill `git-commit`).
- Không chuyển việc sang Xong khi chưa có `make smoke`/QC nếu việc đó chạm backend.

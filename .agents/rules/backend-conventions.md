---
# Claude Code đọc `paths`, Kiro/Antigravity đọc `fileMatchPattern` - giữ cả hai.
paths:
  - "apps/core/**"
  - "apps/**/*.py"
inclusion: fileMatch
fileMatchPattern: ["apps/core/**/*", "apps/**/*api*/**/*", "apps/**/*backend*/**/*", "apps/**/*.py"]
---

# Quy ước backend dễ vi phạm

Chỉ nạp khi đang sửa file trong `apps/core/`. Quy trình thêm entity mới
xuyên suốt backend+frontend nằm ở skill `add-entity` — tham khảo trước khi
thêm model mới, đừng tự suy luận lại từ đầu.

- **Route tĩnh trước route động.** Trong `api/v1/tasks.py`, `/agenda` và
  `/stats` phải khai báo trước `/{task_id}`, nếu không FastAPI khớp chuỗi
  "agenda" thành UUID và trả 422. Cùng quy tắc cho `api/v1/notes.py`
  (`/trash`, `/stats` trước `/{note_id}`).
- **Payload của `task_events` là JSONB.** Mọi giá trị đưa vào phải qua
  `_jsonable()` trong `task_service.py`. UUID, datetime, date, Enum đều
  không tự serialize được.
- **Khái niệm "hôm nay" luôn quy đổi qua `services/clock.py`.** DB lưu UTC.
  Múi giờ do người dùng chọn (lưu `app_settings`, env chỉ là mặc định), nên KHÔNG
  đọc `settings.display_timezone` trực tiếp: dùng `clock.display_tz()`. Query nào
  group theo ngày phải bọc `func.timezone(clock.display_tz().key, ...)` trước khi
  lấy `date()`, nếu không sẽ lệch với `reference_date`.
- **Quá hạn tính theo ngày địa phương với hạn cả ngày.** Task có `due_all_day`
  (Jira `duedate` chỉ có ngày) quá hạn khi ngày hạn < hôm nay theo múi giờ người
  dùng, không phải `due_at < now`. Dùng `_overdue_clause`/`_due_soon_clause` trong
  `task_service.py`, đừng tự viết lại điều kiện.
- **Không `create_all`.** Schema chỉ đổi qua Alembic.
- **Ràng buộc unique phải là partial index.** `UNIQUE (source, external_id)` có
  điều kiện `WHERE deleted_at IS NULL`. Áp dụng cho cả `tasks` và `notes`. Bản
  ghi xoá mềm không được chiếm chỗ, nếu không thì sync lại từ Jira hay Obsidian
  sẽ bị chặn.
- **Xoá là xoá mềm.** Mọi truy vấn nghiệp vụ phải lọc `deleted_at IS NULL`
  qua helper `_alive()`. Thiếu nó là bản ghi trong thùng rác lại hiện ở
  agenda, thống kê, hoặc kết quả tìm kiếm.
- **Nội dung note là dữ liệu, không phải code.** `note.content` chỉ được
  lưu và trả về. Không đưa vào shell, không `eval`, không nối vào câu SQL.
  Nếu sau này có tính năng "chạy note" thì nó phải là cơ chế riêng có xác
  nhận tường minh, không phải hệ quả của việc lưu note.
- **Cột enum khai báo qua `enum_column()` trong `db/base.py`.** Đừng tự gọi
  `SAEnum` với cấu hình riêng: lệch `native_enum` hay `length` giữa các bảng
  sẽ làm Alembic autogenerate sinh diff nhiễu mãi không hết.
- **Sửa model thì sửa cả `apps/web/lib/types.ts`** và bổ sung assertion vào
  `scripts/smoke-test.sh` — xem chi tiết đầy đủ ở skill `add-entity`.

Xong việc sửa backend thì chạy `make smoke`. Script gọi HTTP thật, kiểm tra
healthcheck, xác thực, vòng đời task/note, agenda, stats, ràng buộc dữ liệu,
và xoá dữ liệu tạm — cách nhanh nhất để biết có làm hỏng gì không.

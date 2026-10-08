# Spec: Lưu trữ note (Note Archive) — VÍ DỤ MẪU

- Trạng thái: **VÍ DỤ** (không triển khai). Dùng để xem một spec hoàn chỉnh trông thế nào; copy `_TEMPLATE.md` khi làm Epic thật.
- Tác giả: architect
- Các tên cột, route, hàm dưới đây bám theo code thật ở `apps/core/app/models/note.py`, `api/v1/notes.py`, `apps/web/app/actions.ts`.

## 1. Bối cảnh & phạm vi
- **Vấn đề:** note cũ không còn dùng hằng ngày nhưng chưa muốn xoá. Hiện chỉ có ghim hoặc xoá vào thùng rác, nên danh sách đầy dần và người dùng ngại xoá nhầm.
- **In-scope:** ẩn note khỏi danh sách mặc định, xem lại và bỏ lưu trữ; lọc theo trạng thái lưu trữ.
- **Out-of-scope:** tự động lưu trữ theo thời gian; lưu trữ hàng loạt; áp dụng cho Task.
- **Khác thùng rác:** note lưu trữ **không** bị job `purge` dọn, và không đụng đến `deleted_at`.

## 2. Thay đổi dữ liệu
| Bảng | Thay đổi | Index/Constraint | Ghi chú migration (downgrade?) |
|---|---|---|---|
| `notes` | Thêm cột `archived_at timestamptz NULL` | Index một phần `ix_notes_archived_at` trên `archived_at` `WHERE archived_at IS NOT NULL` | Cột nullable nên không cần backfill, không khoá bảng lâu. `downgrade()` = `drop_index` rồi `drop_column`, mất dữ liệu lưu trữ chấp nhận được vì chỉ là cờ hiển thị |

- Index `ix_notes_pinned_recent` hiện có (`is_pinned, updated_at` where `deleted_at IS NULL`) giữ nguyên; danh sách mặc định thêm điều kiện `archived_at IS NULL`. `db-reviewer` cần xác nhận kế hoạch truy vấn vẫn dùng được index này.
- Dùng skill `db-migration`; `make migration m="thêm notes.archived_at"` rồi `make migrate`.

## 3. API contract
| Method | Path | Request | Response | Lỗi |
|---|---|---|---|---|
| POST | `/api/v1/notes/{note_id}/archive` | không body | `NoteRead` (có `archived_at`) | 404 không thấy hoặc đã trong thùng rác; 409 đã lưu trữ rồi |
| POST | `/api/v1/notes/{note_id}/unarchive` | không body | `NoteRead` (`archived_at = null`) | 404; 409 chưa lưu trữ |
| GET | `/api/v1/notes` | thêm query `archived: bool \| None` (mặc định `false`) | `Page[NoteRead]` | 422 sai kiểu |

- `archived=false` (mặc định): chỉ note chưa lưu trữ. `archived=true`: chỉ note đã lưu trữ. Bỏ trống kèm `include_all`: **không làm**, tránh thêm tham số.
- Route tĩnh phải khai báo **trước** `/{note_id}` (xem `ops.md`); hai route mới chứa `{note_id}` nên không xung đột.
- `NoteRead` thêm `archived_at: datetime | None`. Sau khi sửa backend phải chạy `make gen-types`.
- Xoá note đang lưu trữ: cho phép, đi vào thùng rác như thường, `archived_at` giữ nguyên để khôi phục đúng trạng thái.

## 4. Thay đổi Web
- **Route:** `/notes` thêm tab "Đang dùng" / "Lưu trữ", truyền `?archived=true` qua search params, giữ nguyên filter khác khi chuyển tab.
- **Component:** nút "Lưu trữ" / "Bỏ lưu trữ" trong menu của mỗi note; nhãn trạng thái ở tab Lưu trữ.
- **Server Action:** `archiveNoteAction(id)` và `unarchiveNoteAction(id)` trong `app/actions.ts`, theo mẫu `toggleNotePinAction`, gọi qua `lib/api.ts` (hàm mới `archiveNote`, `unarchiveNote`). API key không rời server.
- **Phân trang:** giữ server-side `?page=`, 50 note/trang như hiện tại.
- Chế độ `DATA_SOURCE=file`: engine JSON cần field `archived_at` và bước migrate `SCHEMA_VERSION` (backfill `null`). Xem `lib/store/json-file.ts`.

## 5. Ownership (không agent nào sửa file của agent khác)
- **backend-dev:** `apps/core/app/models/note.py`, `schemas/note.py`, `services/note_service.py`, `api/v1/notes.py`, `apps/core/migrations/versions/*`, `scripts/smoke-test.sh` (thêm assertion).
- **frontend-dev:** `apps/web/app/notes/**`, `apps/web/app/actions.ts`, `apps/web/lib/api.ts`, `apps/web/lib/store/*`, `apps/web/lib/types.ts` (chỉ phần helper nếu cần), `apps/web/components/note-*`.
- **orchestrator:** `docs/API_REFERENCE.md`, `docs/huong-dan-su-dung.md`, `docs/AI_HANDOFF_STATE.md`.
- `apps/web/lib/generated/openapi.d.ts` do `make gen-types` sinh, không ai sửa tay.

## 6. Tiêu chí nghiệm thu (kiểm chứng được)
- [ ] `make lint` pass.
- [ ] `make migrate` rồi `make downgrade` rồi `make migrate` đều chạy sạch trên DB có dữ liệu.
- [ ] `make smoke` pass, có assertion mới: archive 200; archive lần hai 409; note đã archive vắng mặt ở `GET /notes` mặc định và có mặt ở `?archived=true`; unarchive đưa note về danh sách mặc định; xoá rồi khôi phục giữ nguyên `archived_at`.
- [ ] `make gen-types` rồi `cd apps/web && npx tsc --noEmit` pass.
- [ ] Kịch bản tay: lưu trữ một note ở `/notes`, chuyển tab Lưu trữ thấy note, bỏ lưu trữ thì note quay lại; filter và trang hiện tại được giữ khi đổi tab.
- [ ] `db-reviewer` và `code-reviewer` cùng ra 🟢.

## 7. Rủi ro & câu hỏi cần User chốt
1. Note đang **ghim** mà lưu trữ thì có tự bỏ ghim không? Đề xuất: giữ nguyên cờ ghim nhưng ẩn khỏi danh sách mặc định.
2. Có cần đếm số note lưu trữ trong `GET /notes/stats` không? Đề xuất: có, thêm khoá `archived`, nhưng đây là thay đổi contract nhỏ cần web cập nhật.
3. Có cho lưu trữ note `is_dangerous` không? Đề xuất: cho, vì không đổi nội dung.
4. Rủi ro kỹ thuật: bảng `notes` hiện nhỏ nên thêm index thường là đủ; nếu sau này lớn thì dùng `CREATE INDEX CONCURRENTLY` ngoài transaction của Alembic.

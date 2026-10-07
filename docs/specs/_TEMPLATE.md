# Spec: <Tên Epic>

- Trạng thái: DRAFT | CHỐT (User duyệt ngày ...)
- Tác giả: architect

## 1. Bối cảnh & phạm vi
- Vấn đề cần giải quyết:
- In-scope:
- Out-of-scope:

## 2. Thay đổi dữ liệu
| Bảng | Thay đổi | Index/Constraint | Ghi chú migration (downgrade?) |
|---|---|---|---|

## 3. API contract
| Method | Path | Request | Response | Lỗi |
|---|---|---|---|---|

## 4. Thay đổi Web
- Route / trang:
- Component:
- Server Action:

## 5. Ownership (không agent nào sửa file của agent khác)
- backend-dev: `apps/core/...`
- frontend-dev: `apps/web/...`
- orchestrator: `docs/...`, `apps/web/lib/docs.ts`

## 6. Tiêu chí nghiệm thu (kiểm chứng được)
- [ ] `make lint` pass
- [ ] `make smoke` pass, có assertion mới cho: ...
- [ ] `cd apps/web && npx tsc --noEmit` pass
- [ ] Kịch bản tay: ...

## 7. Rủi ro & câu hỏi cần User chốt
-

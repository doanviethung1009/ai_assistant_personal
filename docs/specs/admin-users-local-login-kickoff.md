# Prompt mở đầu: tài khoản nội bộ và trang admin (session mới)

Dán đoạn dưới vào session Claude Code mới, mở ở thư mục gốc repo, nhánh `feat/auth-multiuser`.

---

Hãy triển khai epic "tài khoản nội bộ (mật khẩu) và trang quản trị người dùng". Bạn là orchestrator.

1. Đọc theo thứ tự: `docs/NEW_AGENT_ONBOARDING.md`, `docs/AI_HANDOFF_STATE.md` (mục 17, 18), spec CHỐT `docs/specs/admin-users-local-login.md` (đọc hết, nhất là mục 8 điểm lệch và mục 9), rồi `docs/specs/web-authjs-login.md` (đặc biệt 3.x, 4.3, 4.5, 4.7, 4.12).
2. Quyết định đã chốt: Q1-Q13 theo khuyến nghị trong spec (email bắt buộc, core sinh mật khẩu tạm, một cách đăng nhập mỗi tài khoản, 12-128 ký tự, khoá 15 phút sau 5 lần sai, có công tắc `PASSWORD_LOGIN_ENABLED`, không cache `/admin`, tự đổi mật khẩu đăng xuất thiết bị khác, admin đặt lại mật khẩu admin khác có audit, tài khoản nội bộ được làm admin, chưa làm 2FA, chấp nhận giới hạn IP yếu khi qua tunnel). Đừng hỏi lại.
3. Trước khi code: kiểm tra đợt Auth.js trước đó. Chạy `git status`, `cd apps/web && npx tsc --noEmit && npm test`. Nếu hai agent review (`code-reviewer`, `security-auditor`) của đợt đó chưa có kết quả thì chạy lại và vá blocker/high trước, vì epic này sửa chung `auth.ts`, `/login`, layout, `lib/api.ts`. Hỏi User có muốn commit đợt trước (skill `git-commit`) để có điểm xuất phát sạch không.
4. Làm theo thứ tự pha trong spec: backend-dev (core, kèm `db-reviewer` cho migration) trước; frontend-dev sau, áp dụng mục 4.12 (ít gọi core, Suspense/`loading.tsx`, `useOptimistic`/`useTransition`, không waterfall); cuối cùng `code-reviewer` rồi `security-auditor`. Không chạy backend-dev và frontend-dev song song trên cùng file.
5. Lưu ý môi trường: máy dev có thể không có Docker/ruff nên không chạy được pytest, `make smoke`, `make gen-types`; hãy nói rõ cái gì chưa chạy. Không commit hay push khi User chưa cho phép. `.env.example` bị chặn quyền sửa, nhắc User thêm biến mới bằng tay.
6. Khi xong: cập nhật `docs/AI_HANDOFF_STATE.md`, `GOOGLE_OAUTH_SETUP.md`, `API_REFERENCE.md`, `.agents/rules/web-conventions.md` theo mục "docs cần cập nhật" của spec.

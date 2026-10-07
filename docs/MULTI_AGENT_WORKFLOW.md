# Kịch bản Demo: Làm việc với Multi-Agent (Nhiều AI Agent)

> **Bản chính hiện nay:** `MULTI_AGENT_SYSTEM.md` (cách hoạt động, cách dùng) và `MULTI_AGENT_TRIAL.md` (ví dụ chạy thật). File này giữ lại làm kịch bản demo kiểu "đóng vai" cho IDE không có subagent. Xem `INDEX.md` để biết nên đọc gì.

Khi dự án lớn lên, việc nhồi nhét cho một AI làm từ A-Z (từ Thiết kế, Code, Test đến Merge) trong cùng một prompt thường dẫn đến rủi ro: AI bị "ảo giác" (hallucination), quên context, hoặc tự ý phá vỡ kiến trúc. Giải pháp tối ưu là **Multi-Agent Workflow** (Phân chia vai trò).

Dưới đây là Vòng đời hoàn thiện một Epic (Ví dụ: Tính năng Giỏ hàng) với 5 bước phối hợp:

---

## 📐 Bước 1: Thiết kế Kiến trúc (Software Architect)
**Mục tiêu:** Định hình luồng dữ liệu trước khi code.
> *"Đóng vai `@.agents/roles/software-architect.md`. Hãy phân tích yêu cầu tính năng Giỏ hàng, vẽ sơ đồ Sequence Diagram, định nghĩa API Contract và chốt với tôi trước khi làm tiếp."*

---

## 🛠 Bước 2: Phát triển Tính năng (Backend/Frontend/DBA)
**Mục tiêu:** Code trên các nhánh `feat/*` dựa trên bản thiết kế.
> *"Đóng vai `@.agents/roles/database-architect.md`. Chạy skill db-migration để tạo bảng CartItem."*
> 
> *"Đóng vai `@.agents/roles/backend-engineer.md`. Viết API `/api/v1/cart` theo đúng Contract của Architect."*
> 
> *"Đóng vai `@.agents/roles/frontend-engineer.md`. Code UI trang Giỏ hàng kết nối với API Backend. Tuyệt đối không đụng vào `apps/core/`."*

---

## 🕵️ Bước 3: Kiểm thử & Bảo mật (QA Tester / Security Auditor)
**Mục tiêu:** Soi rác, bắt lỗi và tấn công thử (Pentest) tính năng vừa code.
> *"Đóng vai `@.agents/roles/qa-tester.md`. Hãy chạy skill `qc-uat` kiểm tra kỹ luồng thêm vào giỏ hàng xem có lỗi vặt không."*
> 
> *"Đóng vai `@.agents/roles/security-auditor.md`. Hãy rà soát xem API Giỏ hàng có nguy cơ SQL Injection hay lỗi phân quyền (RBAC) không."*

---

## 👑 Bước 4: Duyệt Code & Gộp nhánh (Tech Lead)
**Mục tiêu:** Người giữ cửa (Gatekeeper) quyết định đưa code lên Production. Tại sao cần role này? Vì Dev và QA thường tập trung vào tính năng (Micro), còn Tech Lead sẽ nhìn vào tính ổn định toàn cục (Macro).
> *"Đóng vai `@.agents/roles/tech-lead.md`. Các Agent Dev và QA đã làm xong nhánh `feat/cart`. Hãy dùng skill `pr-review` để soát lại toàn bộ kiến trúc một lần cuối. Nếu đạt chuẩn, hãy Merge vào nhánh `main` và sinh Changelog."*

---

## 🐳 Bước 5: Triển khai (DevOps Engineer)
**Mục tiêu:** Đóng gói và đưa sản phẩm ra ngoài.
> *"Đóng vai `@.agents/roles/devops-engineer.md`. Chạy skill `docker-deploy` để build lại image của Web và Backend, đảm bảo mọi cấu hình an toàn."*

---

## 🤖 Biến thể cho Claude Code: orchestrator + subagent

Năm bước trên dùng "đóng vai" (`@.agents/roles/*.md`), phù hợp IDE như Cursor hay Gemini. Với **Claude Code**, repo có sẵn subagent thật trong `.claude/agents/`, mỗi subagent chạy trong context riêng, có danh sách tool giới hạn. Session chính đóng vai **orchestrator**: chia việc, gọi subagent, tổng hợp, và là nơi duy nhất commit, cập nhật `docs/AI_HANDOFF_STATE.md`, đăng ký `lib/docs.ts`, ghi AI log.

### Bảng tương ứng giữa hai cách

| Bước | Đóng vai (IDE) | Subagent (Claude Code) | Tool được dùng | Ghi chú |
|---|---|---|---|---|
| 1. Thiết kế | `software-architect` | `architect` | Read, Grep, Glob, Write, Edit, WebFetch | Chỉ ra file `docs/specs/<epic>.md`, không viết code |
| 2a. Backend | `backend-engineer`, `database-architect` | `backend-dev` | + Bash | Chỉ sửa `apps/core/` |
| 2b. Frontend | `frontend-engineer` | `frontend-dev` | + Bash | Chỉ sửa `apps/web/` |
| 3. Kiểm thử DB | `database-architect` | `db-reviewer` | Read, Grep, Glob, Bash | Chỉ đọc: khoá bảng, mất dữ liệu, index, rollback |
| 4. Duyệt | `tech-lead`, `qa-tester`, `security-auditor` | `code-reviewer` | Read, Grep, Glob, Bash | Chỉ đọc, context sạch, review diff so với `main` |
| 5. Triển khai | `devops-engineer` | (không có) | | Orchestrator làm, theo skill `docker-deploy` |

### Quy trình 7 bước cho một Epic chạm từ 2 tầng

1. **User** mô tả Epic, nói rõ route và API nếu đã biết.
2. **architect** viết `docs/specs/<epic>.md` theo `docs/specs/_TEMPLATE.md`. Mục **Ownership** phải liệt kê file mỗi agent được sửa, không trùng nhau.
3. **User duyệt spec** (đổi trạng thái thành CHỐT). Chưa chốt thì không code.
4. **backend-dev** làm trước (model, migration, API), chạy `make lint` và `make smoke`, rồi `make gen-types` để web có type mới.
5. **frontend-dev** làm sau khi contract đã có. Chỉ chạy song song với backend khi spec đủ chi tiết, và mỗi agent dùng một git worktree riêng.
6. **db-reviewer** (nếu có migration hoặc đổi model) rồi **code-reviewer** trên toàn bộ diff. Reviewer không sửa file; orchestrator chuyển lỗi về dev agent.
7. **Orchestrator** cập nhật docs, ghi AI log, commit theo skill `git-commit`. `git push` luôn hỏi User.

### Prompt mẫu

```text
Epic: thêm tag cho Note. Dùng architect ra spec trong docs/specs/ rồi dừng chờ tôi duyệt.
```

```text
Spec note-tags đã CHỐT. Chạy backend-dev trước, xong thì frontend-dev, sau đó db-reviewer và code-reviewer. Tổng hợp lỗi, chưa commit.
```

### Khi nào KHÔNG cần subagent

Sửa 1–2 file trong một tầng thì orchestrator tự làm. Mỗi subagent tốn thêm một lượt khởi động context, nên chỉ đáng khi việc đủ lớn hoặc cần reviewer độc lập.

### Hàng rào bắt buộc

Hook `guard-bash.sh` và `no-patch-scripts.sh` áp dụng cho mọi subagent, và `git push` bị hỏi xác nhận. Chi tiết xem [Claude CLI Quickstart](CLAUDE_CLI_QUICKSTART.md).

---

## 💡 Tổng kết sức mạnh của mô hình này:
1. **Phân lập Context:** Mỗi Agent chỉ đọc và thao tác trên phần việc của nó (Frontend không đụng Backend, QA không tự tiện sửa Database).
2. **Chéo kiểm tra (Cross-check):** Code do Dev-Agent viết sẽ bị bắt lỗi bởi QA-Agent và bị từ chối bởi TechLead-Agent nếu kém chất lượng.
3. **Quản lý rủi ro:** Bạn không bao giờ sợ AI làm hỏng nhánh `main` vì đã có luồng kiểm soát (Tech Lead) và tài liệu rõ ràng.

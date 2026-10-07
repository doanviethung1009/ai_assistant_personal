# Hướng dẫn Quản lý AI Agent & Document trong Dự án

Tài liệu này hướng dẫn cách cấu hình, sử dụng và quản lý các AI models/agents trong dự án thông qua kiến trúc thư mục chuẩn `.agents/`.

## 1. Kiến trúc thư mục chuẩn cho AI (`.agents/`)

Để dự án hỗ trợ tốt nhất khi làm việc với nhiều Agent (Gemini, Claude, GPT-4, Cursor, AWS Q, v.v.), chuẩn chung được khuyến nghị là sử dụng thư mục **`.agents/`** tại gốc dự án (thay vì dùng thư mục custom lẻ tẻ như `.kiro`).

Hầu hết các nền tảng Agentic Coding hiện nay (như Antigravity) đều tự động nhận diện thư mục này.

```text
.agents/
  ├── rules/                 # Các luật (Steering Rules) tự động load khi code
  │   ├── comment-style.md   # Luật về comment, document
  │   └── backend-conventions.md # Luật chuyên biệt cho backend
  ├── skills/                # Các kỹ năng/quy trình mẫu (Checklist tự động)
  │   ├── add-entity/        # Skill: Tạo model/bảng mới xuyên suốt stack
  │   │   └── SKILL.md
  │   ├── git-commit/        # Skill: Quy trình commit và changelog
  │   │   └── SKILL.md
  │   └── rbac-implementation/ # Skill: Chuẩn mực viết code phân quyền (Role, Rule)
  │       └── SKILL.md
  └── plugins/               # Tích hợp sâu hơn (nếu có)
```

## 2. Cách làm việc với đa Mô hình (Multi-Model / Multi-Agent)

Khi bạn sử dụng nhiều model (ví dụ dùng Gemini cho logic lập trình phức tạp, dùng Claude cho refactor UI):

- **Đồng nhất chuẩn Rules**: Cả Gemini và Claude đều hiểu rất tốt định dạng Markdown. Việc quy hoạch vào `.agents/rules/*.md` với YAML frontmatter `fileMatchPattern` giúp **bất kỳ model nào** bạn gọi lên cũng sẽ tự động tuân thủ chung 1 bộ luật duy nhất.
- **System Prompt chung**: Tạo file `GEMINI.md` hoặc `AGENTS.md` tại gốc dự án để định nghĩa vai trò cốt lõi. Mọi model sẽ tự động đọc file này làm System Prompt.
- **Tương thích chéo (AWS, Cursor, v.v.)**: Các hệ thống như AWS Q hay Cursor rules hoàn toàn có thể trỏ vào (include) các file trong `.agents/` làm context. Nếu nền tảng bắt buộc dùng tên folder riêng (vd: `.cursorrules`), bạn chỉ cần copy nội dung hoặc tạo tham chiếu đến file trong `.agents/rules/`.

## 3. Quản lý Rules (`.agents/rules/`)

**Mục đích:** Ép AI hành xử theo đúng coding convention của team mà không cần phải nhắc lại trong mỗi Prompt.

**Khả năng mở rộng tự động (Scalability):**
Các file rules hiện tại đã được cấu hình YAML (fileMatchPattern) bằng các biểu thức chính quy (glob patterns) cực kỳ mạnh mẽ. 
Ví dụ: 
- `backend-conventions.md` tự động load không chỉ cho `apps/core/` mà còn cho bất kỳ thư mục nào chứa từ khoá `api`, `backend`, hoặc có file `.py`.
- `web-conventions.md` tự động load cho bất kỳ ứng dụng mới nào có thư mục chứa `web`, `ui`, `admin` hoặc bất kỳ file `.tsx` nào.
Nghĩa là: **Nếu ngày mai bạn tạo một ứng dụng mới (ví dụ: `apps/admin-panel` hoặc `apps/payment-api`), bạn KHÔNG CẦN phải cấu hình lại AI. Các Agent sẽ tự động nhận diện và nạp đúng các luật Backend/Frontend tương ứng vào bộ nhớ.**

**Cách viết Rule hiệu quả (dành cho người tạo Rule mới):**
- Thêm metadata ở đầu file để AI biết *khi nào* cần đọc rule này:
  ```yaml
  ---
  inclusion: fileMatch
  fileMatchPattern: ["apps/core/**/*", "apps/**/*.py"]
  ---
  ```
- **Viết theo cú pháp `NẾU ... THÌ ...`**:
  - *Sai*: "Phải viết docstring cho code."
  - *Đúng*: "NẾU bạn tạo mới hoặc sửa một hàm trong thư mục `apps/core/`, THÌ bạn BẮT BUỘC phải viết docstring giải thích lý do tồn tại của hàm."
- **Đưa ví dụ (Few-shot)**: Đưa ra 1 mẫu Tốt (✅) và 1 mẫu Xấu (❌) để Agent hiểu chính xác.

## 4. Quản lý Skills (`.agents/skills/`)

**Mục đích:** Dạy cho AI các quy trình thao tác nhiều bước phức tạp. Thay vì phải đưa một prompt dài 50 dòng mỗi khi cần tạo 1 module mới, bạn đóng gói nó thành 1 Skill.

**Cách tạo:**
1. Tạo thư mục: `.agents/skills/create-api/`
2. Tạo file `.agents/skills/create-api/SKILL.md`
3. Cấu trúc file SKILL:
   ```markdown
   ---
   name: "create-api"
   description: "Dùng để tạo một API RESTful mới bao gồm Schema, Route, Service."
   ---
   
   # Các bước thực hiện
   Khi User yêu cầu tạo API, bạn PHẢI thực hiện đúng các bước sau theo thứ tự:
   1. Đọc file `apps/core/models/` để hiểu Schema DB.
   2. Tạo file Schema Pydantic.
   3. Tạo file Service xử lý logic.
   4. Tạo Route FastAPI và nhúng vào `api/v1/router.py`.
   5. Báo cáo lại cho người dùng khi hoàn thành.
   ```

**Cách dùng:**
Khi prompt, bạn chỉ cần gõ: `Sử dụng kỹ năng create-api để làm chức năng tạo User mới`. Agent sẽ tự gọi skill này và thực thi chính xác 5 bước trên.

## 5. Dọn dẹp thư mục gốc (Scripts & Patches)

Dự án sinh ra rất nhiều file script tạm (`patch_*.py`, `fix_*.py`) trong quá trình AI sửa lỗi hoặc cào dữ liệu.

**Quy chuẩn kiến trúc:**
- **Tuyệt đối không để rác ở thư mục gốc.**
- Tất cả các script chạy một lần, script sửa lỗi tạm thời đã được gom gọn vào thư mục `scripts/patches/`.
- Các bash script chạy hệ thống (deploy, test) nằm tại `scripts/`.
- Dữ liệu tĩnh, data cào về nằm ở `data/`.

*Lưu ý: Nếu một file patch/fix thực sự cần dùng liên tục nhiều lần, hãy cấu trúc nó thành một CLI command bên trong `apps/core/` thay vì để nó trôi nổi ở ngoài.*

## 6. Tương thích Đa nền tảng (Universal Compatibility)

Dự án này được thiết kế để tương thích với **bất kỳ** nền tảng AI nào. `AGENTS.md` chính là "Source of Truth" (Nguồn chân lý). Chúng ta thiết lập cấu trúc "Một Gốc - Nhiều Nhánh" để duy trì luật tại một nơi duy nhất:

1. **OpenAI Codex Ecosystem (MỚI):** File `AGENTS.md` chính là cơ chế Native (bản địa) mà hệ sinh thái Codex (Codex CLI, Codex IDE, Codex App) tự động đọc. Chúng tôi cũng đã trang bị file `.codex/config.toml` để tối ưu dự án.
2. **Cursor IDE & Windsurf:** Đã có sẵn file cầu nối `.cursorrules`. Khi Editor mở dự án, nó đọc file này và tự chuyển hướng sang đọc `AGENTS.md`.
3. **Claude Code CLI (Terminal):** Tự động nhận diện file `CLAUDE.md`. File này sẽ ép Claude đọc `AGENTS.md`.
4. **GitHub Copilot Chat:** Đã thiết lập file `.github/copilot-instructions.md` để tiêm luật vào ngữ cảnh bên trong VS Code.
5. **ChatGPT / Claude Web:** Với bản Web, hãng không cho phép quét ổ cứng. Bạn tạo Custom GPT / Claude Project và copy nội dung `AGENTS.md` dán vào phần System Instructions.

---

## 7. Hướng dẫn Sử dụng Thực tế (How to Use)

Dưới đây là cẩm nang thao tác dành cho lập trình viên (Human) để kích hoạt sức mạnh của từng hệ sinh thái AI trong dự án này:

### A. Hệ sinh thái OpenAI Codex (CLI / App)
1. **Codex CLI:** Mở Terminal tại thư mục gốc, gõ lệnh `codex`. CLI sẽ tự động nạp `AGENTS.md` theo cơ chế native. Bạn có thể chat trực tiếp trên terminal để AI tự sửa code.
2. **Codex IDE Extension:** Cài đặt extension trong VS Code, mở Chat (hoặc Inline Edit). Nó sẽ tự động fallback đọc `AGENTS.md`.
*(Chi tiết vận hành chuyên sâu: Xem `docs/CODEX_OPERATING_GUIDE.md`)*

### B. Hệ sinh thái Anthropic Claude (CLI / IDE)
1. **Claude Code CLI:** Mở Terminal, gõ lệnh `claude`. Hệ thống sẽ đọc file `CLAUDE.md` và tự động `@import` các luật từ `AGENTS.md` nhờ cấu trúc Lazy-loading siêu tiết kiệm token.
2. **Claude IDE (RooCode / Cline):** Mở extension trong VS Code, Claude sẽ tự quét và nạp `CLAUDE.md`.
*(Chi tiết vận hành chuyên sâu: Xem `docs/CLAUDE_OPERATING_GUIDE.md`)*

### C. Các Agentic IDE (Cursor, Windsurf, Antigravity)
- **Cách dùng:** Mở thư mục dự án bằng IDE. Hệ thống sẽ tự động bắt tín hiệu từ `.cursorrules` (hoặc cấu hình workspace) và chuyển hướng đọc `AGENTS.md`.
- **Thao tác:** Nhấn `Cmd + I` (Composer) hoặc `Cmd + L` (Chat), ném yêu cầu (vd: "Thêm API tạo Task mới"). AI sẽ tự động đọc Handoff State, code, viết docs và tự kiểm thử.

### D. GitHub Copilot
- **Cách dùng:** Mở VS Code, bật Copilot Chat.
- **Thao tác:** Gõ `@workspace` kèm câu hỏi. Copilot sẽ tự động bị ép đọc luật từ `.github/copilot-instructions.md`. Mặc dù không tự trị (autonomous) mạnh như Cursor, Copilot vẫn sẽ code đúng chuẩn convention của dự án.

---

## 8. Quản lý Nhân cách (Agent Roles / Personas)

Để tối ưu hóa cho mô hình Multi-Agent (Nhiều AI cùng làm việc), hệ thống cung cấp sẵn 6 "Nhân cách" chuyên biệt tại thư mục `.agents/roles/`:

- 🎨 **`frontend-engineer.md`**: Chuyên gia thiết kế UI/UX, am hiểu Next.js, Tailwind, hoạt ảnh mượt mà.
- ⚙️ **`backend-engineer.md`**: Kiến trúc sư hệ thống, tối ưu FastAPI, luồng dữ liệu khắt khe.
- 🛡️ **`qa-tester.md`**: Kẻ đập phá hệ thống. Chuyên soi rác, bắt lỗi PR (`pr-review`) và test UAT.
- 🗄️ **`database-architect.md`**: Bậc thầy PostgreSQL, viết migration (Alembic) an toàn, tối ưu Query.
- 🐳 **`devops-engineer.md`**: Kỹ sư hạ tầng, nắm trùm Docker, CI/CD, Makefile và bảo mật Zero-Trust.
- 🧠 **`ai-rag-engineer.md`**: Chuyên gia LLM, làm việc với Vector Database (pgvector) và Prompt Engineering.

**Cách sử dụng:**
Khi giao việc, thay vì dùng Agent mặc định (Fullstack Architect từ `AGENTS.md`), bạn có thể gọi đích danh một nhân cách:
> *"Hãy đóng vai `@.agents/roles/database-architect.md` và chạy skill db-migration để tạo bảng Vault!"*

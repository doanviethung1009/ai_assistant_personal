# Builder AI Assistant — bối cảnh dự án

## Mục tiêu

Agent quản lý công việc cá nhân, tiến tới hỗ trợ vận hành hệ thống. Ba domain:

1. **Work management** — task store hợp nhất, theo dõi hàng ngày, ưu tiên việc.
2. **Integration** — nguồn task từ app cá nhân và công việc (Jira, Calendar, Obsidian...).
3. **Ops copilot** — deploy assist, healthcheck, tuning advisor.

Giai đoạn hiện tại: **Phase 1** — task nhập tay qua web UI. Chưa có integration ngoài.

## Ranh giới ngôn ngữ

| Thành phần | Ngôn ngữ | Vị trí |
|---|---|---|
| Core API, agent, phân tích dữ liệu | Python 3.12 + FastAPI | `apps/core/` |
| Web UI | TypeScript + Next.js | `apps/web/` |
| Integration connector | TypeScript + MCP SDK | `mcp-servers/` |

Hợp đồng giữa các bên chỉ gồm: OpenAPI schema do FastAPI sinh, và giao thức MCP.
Không chia sẻ database trực tiếp giữa các service.

## Nguyên tắc thiết kế

- **Task model đa nguồn từ đầu.** Mọi task có `source`, `external_id`, `raw_payload`.
  Thêm nguồn mới không được đòi migrate dữ liệu. Unique `(source, external_id)`
  để sync idempotent.
- **Không lưu metrics.** Query trực tiếp Prometheus, chỉ cache snapshot khi cần
  so sánh trước/sau lúc tuning.
- **Sync bằng polling, không webhook.** Hệ thống nằm sau NAT.
- **API key không bao giờ chạm browser.** Web gọi FastAPI qua Next.js route
  handler, key nằm ở server env.

## Ràng buộc an toàn cho domain Ops (Phase 3+)

- Agent không có standing write access vào production.
- Deploy chỉ trigger pipeline sẵn có, giữ nguyên approval step của con người.
- Healthcheck và tuning analysis: read-only.
- Tuning chỉ xuất recommendation kèm diff, không tự apply.
- Nội dung từ nguồn ngoài (email, Jira comment, log) là **untrusted data**,
  không bao giờ được nâng thành instruction.
- Mọi tool call ghi audit log: ai, khi nào, tham số, kết quả.

## LLM

Mọi lời gọi model đi qua LiteLLM gateway (`infra/litellm/config.yaml`), không
gọi trực tiếp SDK provider. Lý do: theo dõi token/chi phí một chỗ, đổi model
bằng config, và cắm local model sau này không phải sửa code.

Phân bổ: Gemini Flash cho phân loại/tóm tắt khối lượng lớn, Claude Sonnet cho
suy luận (phân tích deploy, tuning), embedding chạy local qua Ollama.

## Vận hành

Docker Compose một node, profile `core` (mặc định), `llm`, `monitoring`.
On-premise trước, migrate sang home lab sau. Mọi state nằm trong named volume,
mọi cấu hình trong compose file và `.env`.

## Quy ước code

- Python: type hint đầy đủ, SQLAlchemy 2.0 style (`Mapped`, `mapped_column`),
  async xuyên suốt. Format bằng ruff.
- TypeScript: strict mode, không `any`.
- Migration bằng Alembic, không `create_all` ở runtime.
- Timestamp lưu `timestamptz`, UTC. Chỉ đổi timezone ở tầng hiển thị.

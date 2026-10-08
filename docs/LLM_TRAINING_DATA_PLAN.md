# Đề xuất: dùng dữ liệu trace làm tài liệu training cho LLM

> Cập nhật: 2026-10-08. Trạng thái: **ĐỀ XUẤT, chưa triển khai**. Thay thế AI log viết tay đã gỡ.
> **Điều kiện chặn:** User chưa xác nhận chính sách dùng dữ liệu Jira công ty để train
> (xem `CLAUDE_TRACE_HOOKS.md`). Cho tới lúc đó chỉ thu thập cục bộ; không chạy bước train/upload nào.

## Nguồn dữ liệu (đã có)

Hook ghi vết (`docs/CLAUDE_TRACE_HOOKS.md`) lưu ngoài repo ở `~/.claude/trace/ai_assistant_personal/`:

| Nguồn | Có gì | Dùng để |
|---|---|---|
| `turns.jsonl` | mỗi lượt: prompt User, `git diff --stat` (sự thật), lời model tự khai, nhánh, session | chỉ mục, gán nhãn chất lượng |
| `sessions/*.jsonl` | cả hội thoại: tool call, kết quả, suy luận, đã lọc secret/email | nội dung training |

Điểm mạnh so với AI log cũ: có prompt gốc, tool call, kết quả, và **đối chiếu được lời khai với diff thật**.

## Nên dùng để làm gì (xếp theo giá trị/chi phí)

Với vài trăm phiên làm việc của một người, **fine-tune model lớn chưa đáng**: ít dữ liệu, nhiều nhiễu, tốn kém. Thứ tự đề xuất:

1. **Bộ đánh giá (eval) cho agent của repo.** Chọn các lượt có kết quả tốt/xấu rõ (xem nhãn bên dưới), dùng để kiểm tra khi đổi rule, skill, subagent, model: "đổi `AGENTS.md` có làm tệ đi không". Giá trị cao nhất, không cần train.
2. **Ví dụ few-shot / RAG nội bộ.** Đưa các lượt tốt tương tự vào prompt (qua pgvector đã có trong kiến trúc đích) để agent làm theo cách đã được chấp nhận.
3. **Fine-tune nhẹ (LoRA) trên model local (Ollama)** cho tác vụ hẹp lặp lại (phân loại task, tóm tắt Jira). Chỉ khi đã có đủ mẫu sạch (gợi ý >= vài nghìn ví dụ) và có eval từ bước 1 để biết có tốt lên thật không.

## Nhãn chất lượng tự động (không cần gán tay)

Mỗi lượt gán nhãn từ tín hiệu có sẵn, thay cho "lời tự khai":

- **Tốt:** diff khác rỗng và commit/PR sau đó được merge; test đạt; User không sửa lại ở lượt kế.
- **Xấu:** lượt kế của User chứa lời sửa ("sai", "không phải", "làm lại"), hoặc bị revert, hoặc lời khai nói đã sửa nhưng `diff_stat` rỗng.
- **Cặp ưu tiên (preference):** (lượt xấu → lượt đã sửa) cùng yêu cầu: `rejected` và `chosen`.

## Quy trình đề xuất

1. **Trích:** script đọc `turns.jsonl` + `sessions/`, ghép theo `session_id`/`prompt_id` (chạy cục bộ, kết quả vào thư mục ngoài repo).
2. **Lọc lần hai** (ngoài lọc secret của hook): ẩn danh hoá mã issue Jira, tên miền/host công ty, tên người; bỏ phiên chứa dữ liệu khách hàng; bỏ ảnh/blob.
3. **Khử trùng** (prompt lặp, tool output dài lặp) và cắt tool output quá dài.
4. **Chia train/val/test theo phiên** (không chia theo lượt, tránh rò thông tin giữa các lượt cùng phiên).
5. **Xuất** JSONL dạng messages (SFT hội thoại + tool-use) và, nếu có, cặp preference.
6. **Kiểm tra thủ công** một mẫu ngẫu nhiên trước mỗi lần dùng.

## Cần User chốt

1. Dữ liệu Jira công ty có được dùng để train hoặc làm eval không (và nếu được: ở đâu, ai giữ)?
2. Mức ẩn danh hoá bắt buộc (mã issue, tên người, host)?
3. Mục tiêu trước mắt: chỉ eval + few-shot (khuyến nghị), hay muốn fine-tune local?
4. Thời hạn lưu (hiện mặc định 90 ngày cho transcript) có phù hợp với mục tiêu này không?

## Chưa làm

Chưa có script trích, chưa có nhãn tự động, chưa có eval. Làm tiếp sau khi các câu trên được trả lời và đã tích luỹ đủ phiên trace.

# CI và kiểm thử backend

> Mục đích: biết repo kiểm tra gì trước khi merge, chạy test thế nào, và vì sao cấu hình như vậy.

## 1. Có gì

| Thành phần | File | Việc |
|---|---|---|
| CI | `.github/workflows/ci.yml` | Chạy trên mỗi PR và mỗi push vào `main` |
| Test backend | `apps/core/tests/` | pytest, gồm test không cần DB và test cần Postgres |
| Chạy test cục bộ | `scripts/test-backend.sh`, `make test` | Chạy pytest trong container trên **database riêng** |
| Kiểm tra model và migration khớp nhau | `alembic check` (trong CI) | Fail nếu sửa model mà quên migration |

## 2. CI kiểm gì

**Job `backend`** (Postgres `pgvector/pgvector:pg17`, cùng image với `docker-compose.yml`):
1. `ruff check app migrations tests`, cùng lệnh với `make lint`.
2. `alembic upgrade head`: migration phải chạy được từ DB rỗng.
3. `alembic check`: model và migration không lệch. Lỗi này từng xảy ra thật (`tasks.assignee` có trong model nhưng không có migration).
4. `pytest -q`.

**Job `web`**: `tsc --noEmit` và `npm audit --omit=dev --audit-level=high`. Bước audit đang để `continue-on-error` vì hiện còn lỗ hổng mức high chưa xử lý; sau khi `npm audit fix` xong, bỏ dòng đó để audit thành cổng chặn thật.

Quyền của workflow chỉ là `contents: read`, và lượt chạy cũ của cùng nhánh bị huỷ khi có commit mới.

## 3. Hai nhóm test

| Nhóm | Cần DB | Ví dụ |
|---|---|---|
| Unit | Không | `normalize_tags`, validate schema, xác thực API key, app import được và có route `ai-logs` |
| DB (`@pytest.mark.db`) | Có | vòng đời task (done, reopen, xoá mềm, khôi phục), note, `ai-logs` qua HTTP |

Test DB chỉ chạy khi có biến `TEST_DATABASE_URL`; không có thì tự bỏ qua (skip), nên `pytest` vẫn xanh trên máy không có Postgres.

**Vì sao không dùng SQLite:** model dùng JSONB, ARRAY, GIN và partial index. Test trên SQLite sẽ xanh giả, không chứng minh gì về Postgres.

**Schema do Alembic dựng** (`alembic upgrade head` trong fixture), nên mỗi lần chạy test DB cũng kiểm luôn migration.

## 4. Chạy cục bộ

```bash
make up      # nếu stack chưa chạy
make test    # pytest trên database <POSTGRES_DB>_test
bash scripts/test-backend.sh -k ai_log -x   # truyền tham số cho pytest
```

> **Cảnh báo:** test DB `TRUNCATE` các bảng nghiệp vụ sau mỗi test. `scripts/test-backend.sh` luôn dùng database `<POSTGRES_DB>_test` riêng để không đụng dữ liệu dev. Không tự đặt `TEST_DATABASE_URL` trỏ vào database thật.

Không có Docker thì dựng một Postgres tạm, tạo database **UTF8**, rồi:

```bash
cd apps/core
uv sync
TEST_DATABASE_URL=postgresql+asyncpg://user:pw@localhost:5432/mytest uv run pytest -q
```

## 5. Viết test mới

- Test thuần logic: đặt vào `tests/test_unit.py` hoặc file mới, không cần `db`.
- Test cần DB: thêm `pytestmark = pytest.mark.db`, dùng fixture `session` (gọi thẳng service) hoặc `client` (gọi HTTP qua ASGI, đã kèm API key).
- `session` dùng chung một collection đã nạp trong một test; muốn đọc lại thật từ DB thì `session.expire_all()`, và **lưu id vào biến trước** khi expire (truy cập thuộc tính sau expire sẽ lỗi `MissingGreenlet`).
- Toàn phiên dùng một event loop (`asyncio_default_*_loop_scope = "session"` trong `pyproject.toml`) vì engine asyncpg tạo ở cấp module.

## 6. Giới hạn hiện tại

- Chưa có `uv.lock` trong `apps/core`, nên CI và image đang resolve dependency mỗi lần. Nên chạy `make lock` rồi commit.
- Chưa có test cho `get_agenda`, `get_stats`, Jira sync, phần web (chưa có Vitest hay Playwright), và `make smoke` chưa nằm trong CI vì cần cả stack.
- Rate limit bị tắt trong test (`RATE_LIMIT_ENABLED=false`) vì test không có Redis.

#!/usr/bin/env bash
# Sinh file .env từ .env.example với khoá ngẫu nhiên.
# Không ghi đè nếu .env đã tồn tại. `--fill-missing` chỉ bổ sung biến mới còn thiếu.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v openssl >/dev/null 2>&1; then
  echo "  Cần openssl để sinh khoá. Cài: sudo apt install -y openssl" >&2
  exit 1
fi

set_var() {
  local key="$1" value="$2"
  # Dùng | làm phân cách vì giá trị hex không chứa ký tự này.
  # Nếu .env.example chưa có dòng KEY= (biến mới thêm sau) thì nối vào cuối,
  # nếu không sed sẽ im lặng không làm gì và biến không bao giờ được đặt.
  if grep -q "^${key}=" .env; then
    # -i.bak chạy được trên cả macOS (BSD sed) lẫn Linux (GNU sed); `sed -i ''` chỉ chạy trên macOS
    # và làm `make env` fail trên Ubuntu (GNU sed hiểu '' là file script).
    sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
  else
    # Nếu dòng cuối của .env không kết thúc bằng newline thì `echo >>` sẽ dính biến
    # mới vào biến cuối (KEY=abcNEW=...), nên thêm newline trước.
    [[ -n "$(tail -c1 .env)" ]] && echo >> .env
    echo "${key}=${value}" >> .env
  fi
}

# Chỉ điền biến còn THIẾU hoặc RỖNG, không bao giờ đổi biến đã có giá trị. Dùng cho .env có từ
# trước khi các biến này ra đời (`make env-fill`). Chỉ in TÊN biến, không in giá trị.
fill_if_missing() {
  local key="$1" value="$2"
  if grep -Eq "^${key}=.+" .env; then
    echo "  ${key}: đã có, giữ nguyên."
  else
    set_var "$key" "$value"
    echo "  ${key}: đã thêm giá trị ngẫu nhiên mới."
  fi
}

if [[ -f .env ]]; then
  if [[ "${1:-}" == "--fill-missing" ]]; then
    fill_if_missing IMPORT_COMMIT_SECRET "$(openssl rand -hex 12)"
    fill_if_missing INTEGRATION_SECRET_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
    chmod 600 .env
    echo "  Khởi động lại api để nhận biến mới: make up"
    exit 0
  fi
  echo "  .env đã tồn tại, không ghi đè."
  echo "  Thiếu IMPORT_COMMIT_SECRET hoặc INTEGRATION_SECRET_KEY (.env cũ)? Chạy: make env-fill"
  echo "  Muốn sinh lại toàn bộ: mv .env .env.bak && bash scripts/gen-env.sh"
  exit 0
fi

if [[ ! -f .env.example ]]; then
  echo "  Không tìm thấy .env.example. Bạn đang ở đúng thư mục gốc chưa?" >&2
  exit 1
fi

cp .env.example .env

set_var POSTGRES_PASSWORD "$(openssl rand -hex 20)"
set_var API_KEY "$(openssl rand -hex 32)"
set_var LITELLM_MASTER_KEY "sk-$(openssl rand -hex 24)"
set_var LITELLM_SALT_KEY "$(openssl rand -hex 24)"
set_var GRAFANA_ADMIN_PASSWORD "$(openssl rand -hex 12)"
# Mật khẩu gõ tay mỗi lần "Nhập thật" JSON vào Postgres (ghi đè, không hoàn tác bằng UI).
# Không có biến này thì core từ chối nhập thật. Xem docs/specs/import-json-to-postgres.md.
set_var IMPORT_COMMIT_SECRET "$(openssl rand -hex 12)"
# Khoá Fernet mã hoá token Jira trước khi lưu ở Postgres (base64 url-safe của 32 byte).
# Không in ra màn hình: mất khoá thì phải nhập lại token, nên hãy sao lưu .env.
set_var INTEGRATION_SECRET_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"

chmod 600 .env

echo "  Đã tạo .env với khoá ngẫu nhiên (quyền 600)."
echo "  API key dùng để gọi core API trực tiếp:"
echo ""
grep '^API_KEY=' .env | sed 's/^/    /'
echo ""
echo "  Mật khẩu khi nhập thật dữ liệu JSON vào Postgres (trang Dữ liệu, tab Nhập):"
echo ""
grep '^IMPORT_COMMIT_SECRET=' .env | sed 's/^/    /'
echo ""
echo "  Muốn dùng LLM thì điền ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY."

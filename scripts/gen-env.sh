#!/usr/bin/env bash
# Sinh file .env từ .env.example với khoá ngẫu nhiên.
# Không ghi đè nếu .env đã tồn tại.

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo "  .env đã tồn tại, không ghi đè."
  echo "  Muốn sinh lại: mv .env .env.bak && bash scripts/gen-env.sh"
  exit 0
fi

if [[ ! -f .env.example ]]; then
  echo "  Không tìm thấy .env.example. Bạn đang ở đúng thư mục gốc chưa?" >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "  Cần openssl để sinh khoá. Cài: sudo apt install -y openssl" >&2
  exit 1
fi

cp .env.example .env

set_var() {
  local key="$1" value="$2"
  # Dùng | làm phân cách vì giá trị hex không chứa ký tự này
  sed -i '' "s|^${key}=.*|${key}=${value}|" .env
}

set_var POSTGRES_PASSWORD "$(openssl rand -hex 20)"
set_var API_KEY "$(openssl rand -hex 32)"
set_var LITELLM_MASTER_KEY "sk-$(openssl rand -hex 24)"
set_var LITELLM_SALT_KEY "$(openssl rand -hex 24)"
set_var GRAFANA_ADMIN_PASSWORD "$(openssl rand -hex 12)"

chmod 600 .env

echo "  Đã tạo .env với khoá ngẫu nhiên (quyền 600)."
echo "  API key dùng để gọi core API trực tiếp:"
echo ""
grep '^API_KEY=' .env | sed 's/^/    /'
echo ""
echo "  Muốn dùng LLM thì điền ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY."

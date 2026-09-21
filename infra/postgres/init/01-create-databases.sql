-- Chạy một lần khi volume postgres còn trống.
-- Tạo database riêng cho LiteLLM (spend tracking, virtual key).
-- LiteLLM tự chạy migration của nó khi khởi động.

SELECT 'CREATE DATABASE litellm'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec

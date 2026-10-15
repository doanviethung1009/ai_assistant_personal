import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Test thuần cho lớp auth/cache của web. "server-only" ném lỗi ngoài môi trường react-server nên
 * được thay bằng module rỗng; alias "@" khớp tsconfig.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
      "server-only": fileURLToPath(new URL("./tests/stubs/server-only.ts", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    // next-auth (ESM) import "next/server" không đuôi .js: Node thuần không resolve được, Vite thì được.
    // Cần khi test chạm CredentialsSignin/AuthError thật (lib/password-login.ts, app/login/actions.ts).
    server: { deps: { inline: [/next-auth/] } },
    include: ["tests/**/*.test.ts"],
  },
});

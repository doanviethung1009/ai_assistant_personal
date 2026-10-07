import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

/**
 * Đọc tài liệu markdown thật của repo để hiển thị trên web.
 *
 * Chủ ý là đọc file gốc thay vì chép nội dung vào JSX: tài liệu chỉ có một
 * nguồn sự thật, sửa README là web đổi theo, không bị lệch.
 *
 * Bảo mật: đường dẫn KHÔNG bao giờ lấy từ query string. Người dùng chỉ chọn
 * được `slug` trong danh sách cứng dưới đây, nên không có đường path traversal.
 */

export interface DocEntry {
  slug: string;
  title: string;
  description: string;
  category: string;
  /** Đường dẫn tương đối so với DOCS_DIR. */
  file: string;
}

export const DOCS: DocEntry[] = [
  {
    slug: "guide",
    title: "Hướng dẫn sử dụng",
    description:
      "Dành cho người dùng app: nhập task, làm việc hàng ngày, thùng rác, sao lưu, xử lý sự cố.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "huong-dan-su-dung.md"),
  },
  {
    slug: "readme",
    title: "README",
    description:
      "Cách chạy, kiến trúc, mô hình dữ liệu, quyết định thiết kế và lý do.",
    category: "Tổng quan & Hướng dẫn",
    file: "README.md",
  },
  {
    slug: "project-structure",
    title: "Cấu trúc dự án",
    description: "Giải thích các thư mục, file quan trọng và cách các rule được load tự động.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "PROJECT_STRUCTURE.md"),
  },
  {
    slug: "api-reference",
    title: "Tài liệu API Backend",
    description: "Danh sách và mô tả các endpoint (Tasks, Notes, Projects, v.v.) dành cho frontend và Agent.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "API_REFERENCE.md"),
  },
  {
    slug: "ai-logs",
    title: "Quy tắc Nhật ký AI (Task Trace)",
    description: "Cơ chế tự động lưu vết các quyết định, prompt và xử lý của Agent.",
    category: "Quy ước Code (AI Rules)",
    file: path.join(".agents", "rules", "ai-logger.md"),
  },
  {
    slug: "ai-real-world-example",
    title: "Ví dụ Thực chiến: Multi-App & Vault",
    description: "Case study mô tả quy trình 6 bước phối hợp 8 AI Agent để xây dựng hệ thống Két bảo mật và Portal thực tế.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "AI_REAL_WORLD_EXAMPLE.md"),
  },
  {
    slug: "ai-data-storage",
    title: "Lưu trữ Dữ liệu AI",
    description: "Kiến trúc lưu trữ 2 luồng: Trace Log (Markdown) và Entity (Database/JSON) dành cho AI.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "AI_DATA_STORAGE.md"),
  },
  {
    slug: "json-storage",
    title: "Cơ chế Migration JSON (SCHEMA_VERSION)",
    description: "Giải thích cách hệ thống nạp và bảo vệ file JSON cục bộ khi app được nâng cấp tính năng.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "JSON_STORAGE.md"),
  },
  {
    slug: "vault",
    title: "Két bảo mật (Vault)",
    description: "Cách lưu thông tin nhạy cảm: mã hoá AES-256 ở browser, mật khẩu master, che/hiện, tự khoá, giới hạn.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "VAULT.md"),
  },
  {
    slug: "project",
    title: "Bối cảnh dự án",
    description:
      "Mục tiêu, ranh giới ngôn ngữ, nguyên tắc thiết kế, ràng buộc an toàn cho phần Ops.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join(".agents", "rules", "project.md"),
  },
  {
    slug: "gitflow",
    title: "Mô hình Git và go-live",
    description:
      "Đường đi của code từ main qua uat tới prod, quy trình hotfix, rollback và tách môi trường.",
    category: "DevOps & Triển khai",
    file: path.join("docs", "git-workflow.md"),
  },
  {
    slug: "deploy",
    title: "Runbook deploy",
    description:
      "Thứ tự lệnh cho từng tình huống: deploy lần đầu, update có migration, đổi .env, hotfix, rollback, troubleshooting.",
    category: "DevOps & Triển khai",
    file: path.join("docs", "deploy-runbook.md"),
  },
  {
    slug: "ops",
    title: "Bản đồ code",
    description:
      "Vị trí từng thành phần, bảng lệnh Makefile, và nơi tìm quy ước chi tiết.",
    category: "DevOps & Triển khai",
    file: path.join(".agents", "rules", "ops.md"),
  },
  {
    slug: "status",
    title: "Trạng thái bàn giao",
    description:
      "Phần nào đã verify, phần nào chưa, bug đã sửa, rủi ro còn lại.",
    category: "DevOps & Triển khai",
    file: path.join(".agents", "rules", "status.md"),
  },
  {
    slug: "agents",
    title: "AGENTS (System Prompt)",
    description:
      "Luật tối cao và bản đồ tư duy bắt buộc mọi AI Agent phải đọc trước khi làm việc.",
    category: "Quy ước Code (AI Rules)",
    file: "AGENTS.md",
  },
  {
    slug: "agent-prompts",
    title: "Thư viện Prompt mẫu",
    description:
      "Các mẫu câu lệnh giao tiếp với AI tối ưu nhất (Tạo chức năng, Debug, Refactor, Commit).",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "AGENT_PROMPT_EXAMPLES.md"),
  },
  {
    slug: "create-ai-customizations",
    title: "Cách tạo Skills, Rules & Hooks",
    description:
      "Hướng dẫn chi tiết (step-by-step) cách tự tạo thêm Rule, Skill, Hook và cấu hình Plugin MCP cho dự án.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "CREATE_AI_CUSTOMIZATIONS.md"),
  },
  {
    slug: "multi-agent-workflow",
    title: "Demo: Multi-Agent Workflow",
    description:
      "Kịch bản thực tế cách chia việc (phân quyền) cho nhiều AI Agent phối hợp phát triển 1 tính năng lớn.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "MULTI_AGENT_WORKFLOW.md"),
  },
  {
    slug: "ai-agent-guide",
    title: "Hướng dẫn AI Agent",
    description: "Cách tổ chức và quản lý AI Agent, Multi-model, Rules, và Skills chuẩn.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "AI_AGENT_GUIDE.md"),
  },
  {
    slug: "new-agent-onboarding",
    title: "Nhập môn AI Agent Mới",
    description: "Cẩm nang quy định cách một AI mới lấy thông tin, tuân thủ Rules, và vòng lặp công việc.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "NEW_AGENT_ONBOARDING.md"),
  },
  {
    slug: "project-review",
    title: "Bản đồ Hệ thống (Master Blueprint)",
    description: "Tài liệu nén (token-optimized) chứa toàn cảnh kiến trúc, chức năng, UI/UX để AI đọc nhanh.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "project-review.md"),
  },
  {
    slug: "comment-style",
    title: "Quy ước comment",
    description:
      "Cách viết comment/docstring: banner section, cảnh báo an toàn, docstring giải thích WHY. Tự nạp khi sửa file code.",
    category: "Quy ước Code (AI Rules)",
    file: path.join(".agents", "rules", "comment-style.md"),
  },
  {
    slug: "backend-conventions",
    title: "Quy ước backend",
    description:
      "Route tĩnh/động, JSONB event, xoá mềm, partial unique index. Tự nạp khi sửa apps/core/.",
    category: "Quy ước Code (AI Rules)",
    file: path.join(".agents", "rules", "backend-conventions.md"),
  },
  {
    slug: "web-conventions",
    title: "Quy ước web",
    description:
      "API key không xuống browser, globalThis cho store, SCHEMA_VERSION. Tự nạp khi sửa apps/web/.",
    category: "Quy ước Code (AI Rules)",
    file: path.join(".agents", "rules", "web-conventions.md"),
  },
  {
    slug: "skill-git-commit",
    title: "Skill: quy trình commit",
    description:
      "Conventional Commits, checklist trước khi commit, hook kiểm tra, changelog.",
    category: "Kỹ năng AI (Skills)",
    file: path.join(".agents", "skills", "git-commit", "SKILL.md"),
  },
  {
    slug: "skill-add-entity",
    title: "Skill: thêm entity mới",
    description:
      "Checklist 15 bước thêm model mới xuyên suốt backend và frontend.",
    category: "Kỹ năng AI (Skills)",
    file: path.join(".agents", "skills", "add-entity", "SKILL.md"),
  },
  {
    slug: "skill-qc-uat",
    title: "Skill: QC & Nghiệm thu",
    description:
      "Quy trình kiểm thử chất lượng giao diện, logic và dữ liệu trước khi bàn giao.",
    category: "Kỹ năng AI (Skills)",
    file: path.join(".agents", "skills", "qc-uat", "SKILL.md"),
  },
  {
    slug: "jira-api-knowledge",
    title: "Kiến thức & API Jira",
    description:
      "Lưu trữ các kiến thức và luồng API tích hợp Jira (Sync/Fetch), phục vụ mở rộng Agent Skills.",
    category: "Kiến trúc & Tích hợp",
    file: path.join("docs", "JIRA_API_KNOWLEDGE.md"),
  },
  {
    slug: "architecture-patterns",
    title: "Kiến trúc Hệ thống (Patterns)",
    description:
      "Tư vấn và phân tích kiến trúc Monolith, Microservices, Micro-frontends, và cơ chế đồng bộ Real-time.",
    category: "Kiến trúc & Tích hợp",
    file: path.join("docs", "ARCHITECTURE_PATTERNS.md"),
  },
  {
    slug: "target-architecture",
    title: "Đề xuất Kiến trúc Mục tiêu",
    description:
      "Bản thiết kế kiến trúc chuẩn bị cho giai đoạn hoàn thiện Task, Notes (pgvector) và Vault (Zero-Knowledge).",
    category: "Kiến trúc & Tích hợp",
    file: path.join("docs", "TARGET_ARCHITECTURE.md"),
  },
  {
    slug: "docker-architecture",
    title: "Kiến trúc Docker & Deploy",
    description:
      "Giải mã định nghĩa các file Docker (Rootless, Standalone, pgvector) và cách điều khiển hạ tầng.",
    category: "DevOps & Triển khai",
    file: path.join("docs", "DOCKER_ARCHITECTURE.md"),
  },
  {
    slug: "deployment-strategies",
    title: "Chiến lược Triển khai (Deploy)",
    description:
      "Tư vấn và so sánh các phương pháp vận hành: Local, Docker Compose VPS, và Serverless Vercel.",
    category: "DevOps & Triển khai",
    file: path.join("docs", "DEPLOYMENT_STRATEGIES.md"),
  },
  {
    slug: "platform-alternatives",
    title: "Đánh giá Nền tảng (Platforms)",
    description:
      "Phân tích Core Platform hiện tại (NextJS, FastAPI, Docker) và đề xuất các phương án công nghệ thay thế (Go, K8s, Supabase).",
    category: "Kiến trúc & Tích hợp",
    file: path.join("docs", "PLATFORM_ALTERNATIVES.md"),
  },
  {
    slug: "claude-operating-guide",
    title: "Cẩm nang vận hành Claude (IDE/CLI)",
    description: "Tài liệu chuyên sâu về cách Claude khám phá bối cảnh dự án, nạp luật và quản lý skills.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "CLAUDE_OPERATING_GUIDE.md"),
  },
  {
    slug: "spec-example-note-archive",
    title: "Spec mẫu: Lưu trữ note",
    description: "Một spec hoàn chỉnh do architect viết (schema, API, web, Ownership, nghiệm thu) để làm mẫu cho Epic thật. Không triển khai.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "specs", "EXAMPLE-note-archive.md"),
  },
  {
    slug: "claude-cli-quickstart",
    title: "Claude CLI Quickstart (multi-agent)",
    description: "Chạy Claude Code với cấu hình multi-agent của repo: subagent, hook an toàn, quyền và quy trình commit/push.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "CLAUDE_CLI_QUICKSTART.md"),
  },
  {
    slug: "codex-operating-guide",
    title: "Cẩm nang vận hành OpenAI Codex",
    description: "Tài liệu chuyên sâu về cơ chế hoạt động của Codex CLI/IDE và cách nạp hệ thống Agent.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "CODEX_OPERATING_GUIDE.md"),
  },
  {
    slug: "pdlc",
    title: "Quy trình Phát triển Sản phẩm (PDLC)",
    description: "Vòng đời khép kín 6 bước từ lúc lên ý tưởng (Ideation) đến khi Go-Live cho hệ thống Multi-Agent.",
    category: "Tổng quan & Hướng dẫn",
    file: path.join("docs", "PRODUCT_DEVELOPMENT_LIFECYCLE.md"),
  }
];

/** Thư mục gốc chứa tài liệu. Mặc định là gốc repo, tính từ apps/web. */
function docsDir(): string {
  return process.env.DOCS_DIR
    ? path.resolve(process.env.DOCS_DIR)
    : path.resolve(process.cwd(), "..", "..");
}

export function findDoc(slug: string | undefined): DocEntry {
  return DOCS.find((doc) => doc.slug === slug) ?? DOCS[0]!;
}

export interface DocContent {
  entry: DocEntry;
  /** Nội dung markdown, hoặc null nếu không đọc được. */
  markdown: string | null;
  error: string | null;
  resolvedPath: string;
}

export async function readDoc(entry: DocEntry): Promise<DocContent> {
  const resolvedPath = path.join(docsDir(), entry.file);

  try {
    const markdown = await readFile(resolvedPath, "utf8");
    return { entry, markdown, error: null, resolvedPath };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    const reason =
      code === "ENOENT"
        ? "Không tìm thấy file. Nếu đang chạy trong container, kiểm tra DOCS_DIR đã được mount chưa."
        : error instanceof Error
          ? error.message
          : String(error);
    return { entry, markdown: null, error: reason, resolvedPath };
  }
}

/** Bỏ front matter YAML để không hiện dấu --- ở đầu trang. */
export function stripFrontMatter(markdown: string): string {
  if (!markdown.startsWith("---")) return markdown;
  const end = markdown.indexOf("\n---", 3);
  if (end === -1) return markdown;
  return markdown.slice(end + 4).trimStart();
}

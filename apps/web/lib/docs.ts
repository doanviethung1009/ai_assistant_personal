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
  /** Đường dẫn tương đối so với DOCS_DIR. */
  file: string;
}

export const DOCS: DocEntry[] = [
  {
    slug: "guide",
    title: "Hướng dẫn sử dụng",
    description:
      "Dành cho người dùng app: nhập task, làm việc hàng ngày, thùng rác, sao lưu, xử lý sự cố.",
    file: path.join("docs", "huong-dan-su-dung.md"),
  },
  {
    slug: "readme",
    title: "README",
    description:
      "Cách chạy, kiến trúc, mô hình dữ liệu, quyết định thiết kế và lý do.",
    file: "README.md",
  },
  {
    slug: "gitflow",
    title: "Mô hình Git và go-live",
    description:
      "Đường đi của code từ main qua uat tới prod, quy trình hotfix, rollback và tách môi trường.",
    file: path.join("docs", "git-workflow.md"),
  },
  {
    slug: "project",
    title: "Bối cảnh dự án",
    description:
      "Mục tiêu, ranh giới ngôn ngữ, nguyên tắc thiết kế, ràng buộc an toàn cho phần Ops.",
    file: path.join(".kiro", "steering", "project.md"),
  },
  {
    slug: "ops",
    title: "Bản đồ code",
    description:
      "Vị trí từng thành phần và danh sách quy ước dễ vi phạm khi sửa code.",
    file: path.join(".kiro", "steering", "ops.md"),
  },
  {
    slug: "status",
    title: "Trạng thái bàn giao",
    description:
      "Phần nào đã verify, phần nào chưa, bug đã sửa, rủi ro còn lại.",
    file: path.join(".kiro", "steering", "status.md"),
  },
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

import { NextResponse } from "next/server";

import {
  buildJson,
  buildNotesCsv,
  buildProjectsCsv,
  buildTasksCsv,
} from "@/lib/store/transfer";
import { authEnabled } from "@/lib/auth-config";
import { requireSession } from "@/lib/auth-guard";
import { readVaultRaw } from "@/lib/vault/store";

/**
 * Tải dữ liệu về máy.
 *
 *   GET /api/export?format=json                 toàn bộ, giữ nguyên nhật ký
 *   GET /api/export?format=csv&entity=tasks     task, mở được bằng Excel
 *   GET /api/export?format=csv&entity=projects  project
 *   GET /api/export?format=csv&entity=notes     sổ tay
 *
 * Chế độ api: BẮT BUỘC có phiên (không phiên → 401 JSON, middleware không bảo vệ được vì đây là
 * tải file). `entity=vault` trả két của chính người đăng nhập (ciphertext); các entity khác ở api
 * trả 501 vì store cục bộ không phải dữ liệu thật (dùng trang Dữ liệu). Chế độ file/memory không có
 * đăng nhập: chỉ dùng trên máy dev, không mở cho người khác truy cập.
 */

export const dynamic = "force-dynamic";

function stamp(): string {
  return new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
}

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const format = params.get("format") ?? "json";
  const entity = params.get("entity") ?? "all";

  const auth = await requireSession();
  if (!auth.ok) {
    return NextResponse.json({ detail: "Chưa đăng nhập" }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }
  if (authEnabled() && !(format === "json" && entity === "vault")) {
    return NextResponse.json({ detail: "Dùng trang Dữ liệu" }, { status: 501 });
  }

  try {
    let body: string;
    let filename: string;
    let contentType: string;

    if (format === "json" && entity === "all") {
      body = await buildJson();
      filename = `builder-data-${stamp()}.json`;
      contentType = "application/json; charset=utf-8";
    } else if (format === "json" && entity === "vault") {
      // Chỉ ciphertext, không có plaintext hay mật khẩu nên an toàn để sao lưu
      const raw = await readVaultRaw(auth.user.local ? null : auth.user.uid);
      if (!raw) {
        return NextResponse.json({ detail: "Két chưa được tạo." }, { status: 404 });
      }
      body = raw;
      filename = `builder-vault-${stamp()}.json`;
      contentType = "application/json; charset=utf-8";
    } else if (format === "csv" && entity === "projects") {
      body = await buildProjectsCsv();
      filename = `builder-projects-${stamp()}.csv`;
      contentType = "text/csv; charset=utf-8";
    } else if (format === "csv" && entity === "notes") {
      body = await buildNotesCsv();
      filename = `builder-notes-${stamp()}.csv`;
      contentType = "text/csv; charset=utf-8";
    } else if (format === "csv") {
      body = await buildTasksCsv();
      filename = `builder-tasks-${stamp()}.csv`;
      contentType = "text/csv; charset=utf-8";
    } else {
      return NextResponse.json(
        { detail: `format không hỗ trợ: ${format}. Dùng json hoặc csv.` },
        { status: 400 },
      );
    }

    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    // Câu chung: message lỗi có thể chứa đường dẫn file hay chi tiết nội bộ. Chỉ log tên lỗi.
    console.error("xuất dữ liệu thất bại", error instanceof Error ? error.name : "unknown");
    return NextResponse.json({ detail: "Xuất dữ liệu thất bại" }, { status: 500 });
  }
}

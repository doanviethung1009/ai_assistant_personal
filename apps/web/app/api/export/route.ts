import { NextResponse } from "next/server";

import {
  buildJson,
  buildNotesCsv,
  buildProjectsCsv,
  buildTasksCsv,
} from "@/lib/store/transfer";

/**
 * Tải dữ liệu về máy.
 *
 *   GET /api/export?format=json                 toàn bộ, giữ nguyên nhật ký
 *   GET /api/export?format=csv&entity=tasks     task, mở được bằng Excel
 *   GET /api/export?format=csv&entity=projects  project
 *   GET /api/export?format=csv&entity=notes     sổ tay
 *
 * Route này không có xác thực riêng, giống mọi trang khác của web app. Nó an
 * toàn vì cả app chỉ bind vào localhost. Nếu sau này đưa web ra mạng thì
 * phải thêm auth trước, vì đây là đường tải toàn bộ dữ liệu.
 */

export const dynamic = "force-dynamic";

function stamp(): string {
  return new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
}

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const format = params.get("format") ?? "json";
  const entity = params.get("entity") ?? "all";

  try {
    let body: string;
    let filename: string;
    let contentType: string;

    if (format === "json") {
      body = await buildJson();
      filename = `builder-data-${stamp()}.json`;
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
    return NextResponse.json(
      {
        detail:
          error instanceof Error ? error.message : "Xuất dữ liệu thất bại",
      },
      { status: 500 },
    );
  }
}

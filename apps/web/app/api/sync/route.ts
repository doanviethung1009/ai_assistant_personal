import { NextResponse } from "next/server";
import { syncFromUrlAction } from "@/app/actions";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const url = searchParams.get("url");

  if (!url) {
    return NextResponse.json({ error: "Missing 'url' query parameter" }, { status: 400 });
  }

  try {
    const res = await syncFromUrlAction(url);
    if (res.ok) {
      return NextResponse.json({ success: true, count: res.count });
    } else {
      return NextResponse.json({ success: false, error: res.error }, { status: 500 });
    }
  } catch (error) {
    return NextResponse.json({ success: false, error: String(error) }, { status: 500 });
  }
}

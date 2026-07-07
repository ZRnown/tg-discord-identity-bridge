import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/app/api/_lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const token = process.env.BRIDGE_AUTH_TOKEN || "";
  if (!token) {
    return NextResponse.json({ authenticated: true });
  }

  return NextResponse.json({
    authenticated: req.cookies.get(AUTH_COOKIE)?.value === token,
  });
}

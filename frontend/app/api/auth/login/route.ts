import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/app/api/_lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const token = process.env.BRIDGE_AUTH_TOKEN || "";
  if (!token) {
    return NextResponse.json({ ok: true });
  }

  const body = await req.json().catch(() => ({}));
  const username = process.env.BRIDGE_AUTH_USERNAME || "admin";

  if (body?.username !== username || body?.password !== token) {
    return NextResponse.json({ error: "用户名或密码错误" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(AUTH_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  return res;
}

import { NextRequest, NextResponse } from "next/server";

const AUTH_TOKEN = process.env.BRIDGE_AUTH_TOKEN || "";
export const AUTH_COOKIE = "bridge_auth";

export async function requireAuth(req: NextRequest): Promise<NextResponse | null> {
  if (!AUTH_TOKEN) return null;

  const header = req.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  const cookieToken = req.cookies.get(AUTH_COOKIE)?.value || "";

  if (token === AUTH_TOKEN || cookieToken === AUTH_TOKEN) return null;

  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

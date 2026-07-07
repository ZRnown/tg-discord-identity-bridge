import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/api/_lib/auth";
import { loadBridgeConfig } from "@/src/bridgeConfig";
import { bridgeEngine } from "@/src/bridgeEngine";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const authErr = await requireAuth(req);
  if (authErr) return authErr;
  try {
    const config = await loadBridgeConfig();
    const status = bridgeEngine.getStatus();
    return NextResponse.json({
      state: config.bridgeState || "stopped",
      logs: status.logs.slice(-30),
      discordAccounts: config.discordAccounts.map(a => ({
        ...a,
        token: undefined, // 不暴露 token
      })),
      capturedTelegramUsers: config.capturedTelegramUsers || [],
    });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

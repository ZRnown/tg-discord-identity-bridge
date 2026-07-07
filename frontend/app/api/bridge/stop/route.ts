import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/api/_lib/auth";
import { loadBridgeConfig, saveBridgeConfig } from "@/src/bridgeConfig";
import { bridgeEngine } from "@/src/bridgeEngine";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const authErr = await requireAuth(req);
  if (authErr) return authErr;
  try {
    await bridgeEngine.stop();
    const config = await loadBridgeConfig();
    config.bridgeState = "stopped";
    await saveBridgeConfig(config);
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

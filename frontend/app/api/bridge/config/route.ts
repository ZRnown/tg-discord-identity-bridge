import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/api/_lib/auth";
import { loadBridgeConfig, saveBridgeConfig, BridgeConfig } from "@/src/bridgeConfig";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const authErr = await requireAuth(req);
  if (authErr) return authErr;
  const config = await loadBridgeConfig();
  return NextResponse.json(config);
}

export async function POST(req: NextRequest) {
  const authErr = await requireAuth(req);
  if (authErr) return authErr;
  try {
    const body = await req.json();
    const current = await loadBridgeConfig();

    // 合并前端提交的配置（保留 bridgeState 等运行时状态）
    const merged: BridgeConfig = {
      ...current,
      ...body,
      bridgeState: current.bridgeState, // 不让前端覆盖运行状态
    };

    await saveBridgeConfig(merged);
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

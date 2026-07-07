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
    const config = await loadBridgeConfig();

    // 基本校验
    if (!config.telegram.apiId || !config.telegram.apiHash || !config.telegram.phoneNumber) {
      return NextResponse.json({ error: "请先配置 Telegram API ID / Hash / 手机号" }, { status: 400 });
    }
    if (config.discordAccounts.length === 0) {
      return NextResponse.json({ error: "请先导入至少一个 Discord 账号" }, { status: 400 });
    }
    if (config.groupMappings.length === 0) {
      return NextResponse.json({ error: "请先添加至少一条群组映射" }, { status: 400 });
    }

    config.bridgeState = "starting";
    await saveBridgeConfig(config);

    // 启动桥接引擎
    await bridgeEngine.start(config);

    config.bridgeState = "running";
    await saveBridgeConfig(config);

    return NextResponse.json({ ok: true });
  } catch (e: any) {
    const config = await loadBridgeConfig();
    config.bridgeState = "stopped";
    await saveBridgeConfig(config);
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

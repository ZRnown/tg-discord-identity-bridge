import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/api/_lib/auth";
import { loadBridgeConfig, saveBridgeConfig } from "@/src/bridgeConfig";
import { telegramLoginManager } from "@/src/telegramLoginManager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const authErr = await requireAuth(req);
  if (authErr) return authErr;
  try {
    const body = await req.json();
    const config = await loadBridgeConfig();

    // 如果有 code，则确认验证码
    if (body.code) {
      const result = await telegramLoginManager.confirmCode(
        body.code,
        body.twoFactorPassword,
      );
      if (result.ok) {
        config.telegram.sessionString = result.sessionString;
        config.telegram.connected = true;
        await saveBridgeConfig(config);
        return NextResponse.json({ ok: true });
      }
      if (result.needPassword) {
        return NextResponse.json({ needPassword: true });
      }
      return NextResponse.json({ error: result.error || "验证失败" }, { status: 400 });
    }

    // 否则发送验证码
    const { apiId, apiHash, phoneNumber } = body;
    if (apiId) config.telegram.apiId = String(apiId);
    if (apiHash) config.telegram.apiHash = apiHash;
    if (phoneNumber) config.telegram.phoneNumber = phoneNumber;
    if (body.twoFactorPassword !== undefined) config.telegram.twoFactorPassword = body.twoFactorPassword;
    await saveBridgeConfig(config);

    // 如果已有 session，直接连接
    if (config.telegram.sessionString) {
      const ok = await telegramLoginManager.connectWithSession(config.telegram);
      if (ok) {
        config.telegram.connected = true;
        await saveBridgeConfig(config);
        return NextResponse.json({ ok: true });
      }
      // session 失效，重新登录
      config.telegram.sessionString = "";
      await saveBridgeConfig(config);
    }

    const result = await telegramLoginManager.sendCode(config.telegram);
    if (result.needCode) {
      return NextResponse.json({ needCode: true });
    }
    if (result.ok) {
      config.telegram.sessionString = result.sessionString;
      config.telegram.connected = true;
      await saveBridgeConfig(config);
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: result.error || "发送验证码失败" }, { status: 400 });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

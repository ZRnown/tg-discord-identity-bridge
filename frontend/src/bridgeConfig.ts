/**
 * Bridge Config — 精简的 TG→Discord 身份桥配置
 *
 * 独立于 admi 原有 config.ts，存储在 .data/bridge-config.json
 * 仅包含：Telegram 单账号 + Discord 账号数组 + 群映射 + 延时/typing 设置
 */
import { promises as fs } from "fs";
import path from "node:path";

export const DEFAULT_TELEGRAM_API_ID = "2040";
export const DEFAULT_TELEGRAM_API_HASH = "b18441a1ff607e10a989891a5462e627";

export interface TelegramAccountConfig {
  apiId: string;
  apiHash: string;
  phoneNumber: string;
  twoFactorPassword?: string;
  sessionString?: string;   // Telethon session string
  connected?: boolean;
}

export interface DiscordBridgeAccount {
  id: string;
  token: string;
  name: string;
  avatarUrl?: string;
  discordUserId?: string;
  tgUserId?: string;
  roleName?: string;
  state?: "idle" | "online" | "sending" | "error";
  errorMessage?: string;
}

export interface GroupMapping {
  id: string;
  tgGroupId: string;
  discordChannelId: string;
  note?: string;
}

export interface DelayConfig {
  minSeconds: number;
  maxSeconds: number;
}

export interface TypingConfig {
  enabled: boolean;
  durationSeconds?: number; // typing 持续时长（默认用延时值）
}

export interface CapturedTelegramUser {
  id: string;
  name: string;
  username: string;
  photoUrl?: string;
  groupId: string;
  lastSeenAt: string;
}

export interface ContentFilterConfig {
  blockedKeywords: string[];
  ocrBlockedKeywords: string[];
  caseSensitive: boolean;
  blockOnOcrHit: boolean;
}

export interface BridgeConfig {
  telegram: TelegramAccountConfig;
  discordAccounts: DiscordBridgeAccount[];
  groupMappings: GroupMapping[];
  capturedTelegramUsers: CapturedTelegramUser[];
  contentFilter: ContentFilterConfig;
  delay: DelayConfig;
  typing: TypingConfig;
  bridgeState?: "stopped" | "starting" | "running";
}

const CONFIG_PATH = path.resolve(process.cwd(), ".data", "bridge-config.json");

export const DEFAULT_CONFIG: BridgeConfig = {
  telegram: {
    apiId: DEFAULT_TELEGRAM_API_ID,
    apiHash: DEFAULT_TELEGRAM_API_HASH,
    phoneNumber: "",
    twoFactorPassword: "",
    sessionString: "",
    connected: false,
  },
  discordAccounts: [],
  groupMappings: [],
  capturedTelegramUsers: [],
  contentFilter: {
    blockedKeywords: [],
    ocrBlockedKeywords: [],
    caseSensitive: false,
    blockOnOcrHit: true,
  },
  delay: { minSeconds: 1, maxSeconds: 5 },
  typing: { enabled: true },
  bridgeState: "stopped",
};

export async function loadBridgeConfig(): Promise<BridgeConfig> {
  try {
    const buf = await fs.readFile(CONFIG_PATH, "utf-8");
    const parsed = JSON.parse(buf.toString());
    const merged = { ...DEFAULT_CONFIG, ...parsed };
    merged.telegram = {
      ...DEFAULT_CONFIG.telegram,
      ...(parsed.telegram || {}),
      apiId: parsed.telegram?.apiId || DEFAULT_TELEGRAM_API_ID,
      apiHash: parsed.telegram?.apiHash || DEFAULT_TELEGRAM_API_HASH,
    };
    merged.contentFilter = {
      blockedKeywords: Array.isArray(parsed.contentFilter?.blockedKeywords)
        ? parsed.contentFilter.blockedKeywords
        : [],
      ocrBlockedKeywords: Array.isArray(parsed.contentFilter?.ocrBlockedKeywords)
        ? parsed.contentFilter.ocrBlockedKeywords
        : [],
      caseSensitive: parsed.contentFilter?.caseSensitive === true,
      blockOnOcrHit: parsed.contentFilter?.blockOnOcrHit !== false,
    };
    return merged;
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export async function saveBridgeConfig(config: BridgeConfig): Promise<void> {
  const dir = path.dirname(CONFIG_PATH);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

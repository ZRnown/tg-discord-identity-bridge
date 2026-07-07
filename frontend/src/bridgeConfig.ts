/**
 * Bridge Config — 精简的 TG→Discord 身份桥配置
 *
 * 独立于 admi 原有 config.ts，存储在 .data/bridge-config.json
 * 仅包含：Telegram 单账号 + Discord 账号数组 + 群映射 + 延时/typing 设置
 */
import { promises as fs } from "fs";
import path from "node:path";

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

export interface BridgeConfig {
  telegram: TelegramAccountConfig;
  discordAccounts: DiscordBridgeAccount[];
  groupMappings: GroupMapping[];
  delay: DelayConfig;
  typing: TypingConfig;
  bridgeState?: "stopped" | "starting" | "running";
}

const CONFIG_PATH = path.resolve(process.cwd(), ".data", "bridge-config.json");

export const DEFAULT_CONFIG: BridgeConfig = {
  telegram: {
    apiId: "",
    apiHash: "",
    phoneNumber: "",
    twoFactorPassword: "",
    sessionString: "",
    connected: false,
  },
  discordAccounts: [],
  groupMappings: [],
  delay: { minSeconds: 1, maxSeconds: 5 },
  typing: { enabled: true },
  bridgeState: "stopped",
};

export async function loadBridgeConfig(): Promise<BridgeConfig> {
  try {
    const buf = await fs.readFile(CONFIG_PATH, "utf-8");
    const parsed = JSON.parse(buf.toString());
    return { ...DEFAULT_CONFIG, ...parsed };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export async function saveBridgeConfig(config: BridgeConfig): Promise<void> {
  const dir = path.dirname(CONFIG_PATH);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

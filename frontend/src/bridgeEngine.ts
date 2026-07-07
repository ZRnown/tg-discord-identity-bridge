/**
 * Bridge Engine — TG→Discord 身份桥核心引擎
 *
 * 流程:
 *  1. 启动 Python (Telethon) 监听 Telegram 群消息，通过 stdout 输出 JSON 事件
 *  2. 收到消息事件 → 获取 TG 发送者的用户名 + 头像
 *  3. 选一个 Discord 账号 → 修改其用户名和头像（匹配 TG 用户）
 *  4. 随机延时 + 正在输入效果
 *  5. 在目标 Discord 频道发送消息
 */
import { spawn, ChildProcess } from "child_process";
import { resolvePythonBin } from "./pythonRuntime";
import { loadBridgeConfig, saveBridgeConfig, BridgeConfig, DiscordBridgeAccount } from "./bridgeConfig";
import path from "node:path";
import https from "https";
import http from "http";
import { URL } from "url";

interface LogEntry {
  text: string;
  level: "info" | "success" | "error" | "warn";
  timestamp: number;
}

interface TgMessageEvent {
  type: "message";
  groupId: string;
  senderName: string;
  senderUsername: string;
  senderPhotoUrl?: string;
  text: string;
  timestamp: number;
}

class BridgeEngine {
  private pythonProcess: ChildProcess | null = null;
  private discordClients: Map<string, any> = new Map(); // accountId -> selfbot client
  private logs: LogEntry[] = [];
  private running = false;
  private accountRotationIndex = 0;
  private avatarCache: Map<string, Buffer> = new Map();

  getStatus() {
    return {
      running: this.running,
      logs: this.logs.slice(-100),
    };
  }

  private log(text: string, level: LogEntry["level"] = "info") {
    this.logs.push({ text, level, timestamp: Date.now() });
    if (this.logs.length > 500) this.logs.shift();
    console.log(`[Bridge] ${text}`);
  }

  async start(config: BridgeConfig) {
    if (this.running) {
      this.log("桥接已在运行中", "warn");
      return;
    }

    this.running = true;
    this.log("正在启动桥接...", "info");

    // 1. 登录所有 Discord 账号
    await this.connectDiscordAccounts(config.discordAccounts);

    // 2. 启动 Telegram 监听
    await this.startTelegramListener(config);

    this.log("桥接已启动，正在监听 Telegram 消息", "success");
  }

  async stop() {
    this.running = false;
    this.log("正在停止桥接...", "info");

    // 停止 Telegram 监听
    if (this.pythonProcess) {
      this.pythonProcess.kill("SIGTERM");
      this.pythonProcess = null;
    }

    // 断开所有 Discord 连接
    for (const [id, client] of this.discordClients) {
      try {
        await client.destroy();
      } catch {}
    }
    this.discordClients.clear();

    // 更新账号状态
    const config = await loadBridgeConfig();
    for (const acc of config.discordAccounts) {
      acc.state = "idle";
    }
    await saveBridgeConfig(config);

    this.log("桥接已停止", "info");
  }

  // ============ Discord 账号连接 ============
  private async connectDiscordAccounts(accounts: DiscordBridgeAccount[]) {
    const { Client } = await import("discord.js-selfbot-v13");
    const config = await loadBridgeConfig();

    for (const acc of accounts) {
      try {
        const client = new Client({
          restTimeOffset: 0,
        });

        await new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("登录超时(15s)")), 15000);
          client.once("ready", () => {
            clearTimeout(timeout);
            resolve();
          });
          client.once("error", (err: Error) => {
            clearTimeout(timeout);
            reject(err);
          });
          client.login(acc.token).catch(reject);
        });

        this.discordClients.set(acc.id, client);
        acc.state = "online";
        acc.errorMessage = "";
        this.log(`Discord 账号 ${acc.name} 已上线 (ID: ${acc.id})`, "success");
      } catch (e: any) {
        acc.state = "error";
        acc.errorMessage = e.message;
        this.log(`Discord 账号 ${acc.name} 登录失败: ${e.message}`, "error");
      }
    }

    await saveBridgeConfig(config);
  }

  // ============ Telegram 监听 ============
  private async startTelegramListener(config: BridgeConfig) {
    const pythonBin = resolvePythonBin() || "python";
    const scriptPath = path.join(process.cwd(), "scripts", "tg_listener.py");

    const params = JSON.stringify({
      apiId: config.telegram.apiId,
      apiHash: config.telegram.apiHash,
      phoneNumber: config.telegram.phoneNumber,
      sessionString: config.telegram.sessionString || "",
      twoFactorPassword: config.telegram.twoFactorPassword || "",
      groupIds: config.groupMappings.map(m => m.tgGroupId).filter(Boolean),
    });

    this.pythonProcess = spawn(pythonBin, [scriptPath, params], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    let buffer = "";

    this.pythonProcess.stdout?.on("data", (data) => {
      buffer += data.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const event = JSON.parse(trimmed);
          this.handleTgEvent(event, config).catch(e => {
            this.log(`处理消息失败: ${e.message}`, "error");
          });
        } catch {
          // Non-JSON output, log it
          if (trimmed.startsWith("[")) {
            this.log(trimmed, "info");
          }
        }
      }
    });

    this.pythonProcess.stderr?.on("data", (data) => {
      const text = data.toString().trim();
      if (text) this.log(`[Python] ${text}`, "warn");
    });

    this.pythonProcess.on("close", (code) => {
      this.log(`Telegram 监听进程退出 (code: ${code})`, code === 0 ? "info" : "error");
      this.running = false;
    });

    this.pythonProcess.on("error", (err) => {
      this.log(`Telegram 监听启动失败: ${err.message}`, "error");
      this.running = false;
    });
  }

  // ============ 处理 Telegram 消息事件 ============
  private async handleTgEvent(event: TgMessageEvent, config: BridgeConfig) {
    if (event.type !== "message") return;

    // 查找对应的群组映射
    const mapping = config.groupMappings.find(m => m.tgGroupId === event.groupId);
    if (!mapping) {
      return; // 没有对应的映射，忽略
    }

    this.log(`收到 TG 消息 [${event.senderName}]: ${event.text.slice(0, 50)}...`, "info");

    // 选择一个 Discord 账号（轮转）
    const availableAccounts = config.discordAccounts.filter(a => a.state === "online");
    if (availableAccounts.length === 0) {
      this.log("没有可用的 Discord 账号", "error");
      return;
    }

    const account = availableAccounts[this.accountRotationIndex % availableAccounts.length];
    this.accountRotationIndex++;

    const client = this.discordClients.get(account.id);
    if (!client) {
      this.log(`Discord 账号 ${account.name} 客户端未找到`, "error");
      return;
    }

    try {
      // 1. 修改 Discord 账号身份（用户名 + 头像）
      await this.updateDiscordIdentity(client, account, event);

      // 2. 随机延时
      const delaySeconds = this.randomDelay(config.delay.minSeconds, config.delay.maxSeconds);
      this.log(`等待 ${delaySeconds.toFixed(1)} 秒后发送...`, "info");
      await this.sleep(delaySeconds * 1000);

      // 3. 正在输入效果
      if (config.typing.enabled) {
        const channel = await client.channels.fetch(mapping.discordChannelId);
        if (channel && channel.type === "GUILD_TEXT") {
          await channel.sendTyping();
          this.log("触发'正在输入'效果", "info");
        }
      }

      // 4. 发送消息
      const channel = await client.channels.fetch(mapping.discordChannelId);
      if (!channel) {
        this.log(`Discord 频道 ${mapping.discordChannelId} 未找到`, "error");
        return;
      }

      account.state = "sending";
      await saveBridgeConfig(config);

      const sentMsg = await channel.send(event.text || "（图片/媒体消息）");
      this.log(`消息已发送到 Discord 频道 [${mapping.discordChannelId}]，使用账号 ${account.name}`, "success");

      account.state = "online";
      await saveBridgeConfig(config);

    } catch (e: any) {
      this.log(`发送失败: ${e.message}`, "error");
      account.state = "error";
      account.errorMessage = e.message;
      await saveBridgeConfig(config);
    }
  }

  // ============ 修改 Discord 账号身份 ============
  private async updateDiscordIdentity(client: any, account: DiscordBridgeAccount, event: TgMessageEvent) {
    try {
      // 修改用户名
      const newName = event.senderName || event.senderUsername || "Unknown";
      const currentName = client.user?.username;
      if (currentName !== newName) {
        // discord.js-selfbot-v13: editUser method
        await client.user.setUsername(newName).catch((e: Error) => {
          this.log(`修改用户名失败: ${e.message}`, "warn");
        });
      }

      // 修改头像
      if (event.senderPhotoUrl) {
        const avatarBuffer = await this.downloadImage(event.senderPhotoUrl);
        if (avatarBuffer) {
          const base64 = avatarBuffer.toString("base64");
          const ext = event.senderPhotoUrl.includes(".png") ? "png" : "jpg";
          await client.user.setAvatar(`data:image/${ext};base64,${base64}`).catch((e: Error) => {
            this.log(`修改头像失败: ${e.message}`, "warn");
          });
        }
      }
    } catch (e: any) {
      this.log(`修改身份失败: ${e.message}`, "warn");
    }
  }

  // ============ 工具方法 ============
  private randomDelay(min: number, max: number): number {
    const lo = Math.min(min, max);
    const hi = Math.max(min, max);
    return lo + Math.random() * (hi - lo);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private async downloadImage(url: string): Promise<Buffer | null> {
    // Check cache
    if (this.avatarCache.has(url)) {
      return this.avatarCache.get(url)!;
    }

    return new Promise((resolve) => {
      const lib = url.startsWith("https") ? https : http;
      lib.get(url, (res) => {
        if (res.statusCode !== 200) {
          resolve(null);
          return;
        }
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const buf = Buffer.concat(chunks);
          this.avatarCache.set(url, buf);
          // Limit cache size
          if (this.avatarCache.size > 50) {
            const firstKey = this.avatarCache.keys().next().value;
            if (firstKey) this.avatarCache.delete(firstKey);
          }
          resolve(buf);
        });
      }).on("error", () => resolve(null));
    });
  }
}

export const bridgeEngine = new BridgeEngine();

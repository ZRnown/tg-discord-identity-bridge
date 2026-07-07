/**
 * Telegram Login Manager
 *
 * Uses a Python subprocess (Telethon) to handle Telegram user client login.
 * - sendCode(): start login flow, get phone code
 * - confirmCode(): verify code, optionally 2FA password, return session string
 * - connectWithSession(): connect with an existing session string
 */
import { spawn, ChildProcess } from "child_process";
import { resolvePythonBin } from "./pythonRuntime";
import path from "node:path";
import { TelegramAccountConfig } from "./bridgeConfig";

interface LoginResult {
  ok?: boolean;
  needCode?: boolean;
  needPassword?: boolean;
  sessionString?: string;
  error?: string;
}

let pythonBin: string | null = null;
let pendingLogin: { process: ChildProcess; resolver: (result: LoginResult) => void } | null = null;

function getPythonBin(): string | null {
  if (pythonBin) return pythonBin;
  pythonBin = resolvePythonBin();
  return pythonBin;
}

function getScriptPath(): string {
  return path.join(process.cwd(), "scripts", "tg_login.py");
}

/**
 * Send a verification code to the phone number.
 * Returns { needCode: true } on success.
 */
export async function sendCode(tg: TelegramAccountConfig): Promise<LoginResult> {
  return runLoginScript({
    action: "send_code",
    apiId: tg.apiId,
    apiHash: tg.apiHash,
    phoneNumber: tg.phoneNumber,
    sessionString: tg.sessionString || "",
    twoFactorPassword: tg.twoFactorPassword || "",
  });
}

/**
 * Confirm the verification code (and optionally 2FA password).
 * Returns { ok: true, sessionString } on success.
 */
export async function confirmCode(code: string, twoFactorPassword?: string): Promise<LoginResult> {
  // code + 2FA handled in the same script call
  const config = await import("./bridgeConfig").then(m => m.loadBridgeConfig());
  return runLoginScript({
    action: "confirm_code",
    apiId: config.telegram.apiId,
    apiHash: config.telegram.apiHash,
    phoneNumber: config.telegram.phoneNumber,
    sessionString: config.telegram.sessionString || "",
    code,
    twoFactorPassword: twoFactorPassword || config.telegram.twoFactorPassword || "",
  });
}

/**
 * Connect with an existing session string (verify it still works).
 */
export async function connectWithSession(tg: TelegramAccountConfig): Promise<boolean> {
  const result = await runLoginScript({
    action: "connect",
    apiId: tg.apiId,
    apiHash: tg.apiHash,
    phoneNumber: tg.phoneNumber,
    sessionString: tg.sessionString || "",
  });
  return !!result.ok;
}

function runLoginScript(params: Record<string, any>): Promise<LoginResult> {
  return new Promise((resolve, reject) => {
    const bin = getPythonBin();
    if (!bin) {
      reject(new Error("Python not found. Install Python or set PYTHON_BIN."));
      return;
    }
    const scriptPath = getScriptPath();
    const proc = spawn(bin, [scriptPath, JSON.stringify(params)], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    let stdout = "";
    let stderr = "";
    let settled = false;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      callback();
    };

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      finish(() => {
        try {
          const result = JSON.parse(stdout.trim().split("\n").pop() || "{}");
          resolve(result);
        } catch {
          reject(new Error(stderr || `Python script exited with code ${code}`));
        }
      });
    });

    proc.on("error", (err) => {
      finish(() => {
        reject(new Error(`Failed to spawn Python: ${err.message}`));
      });
    });

    // Set a timeout
    timeout = setTimeout(() => {
      finish(() => {
        proc.kill();
        reject(new Error("Telegram 登录超时（20 秒）。请检查手机号、代理或 Telegram 网络连通性。"));
      });
    }, 20000);
  });
}

export const telegramLoginManager = {
  sendCode,
  confirmCode,
  connectWithSession,
};

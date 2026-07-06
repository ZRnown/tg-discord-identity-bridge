# TG → Discord Identity Bridge

将 Telegram 群组的消息转发到 Discord — **不使用 Webhook**，而是通过 `discord.py-self` 自托管批量的 Discord 账号，自动同步 TG 用户的头像、昵称映射到 Discord selfbot 账号，让消息在 Discord 中以"真人"身份出现。

## 核心思路

```
Telegram Group (100 users)
         │
         ▼  Telethon 监听
   ┌─────────────┐
   │ TG Listener  │ 提取: user_id, first_name, last_name, avatar, group_id
   └──────┬──────┘
          │
          ▼
   ┌──────────────┐
   │ Identity      │ 建立 TG user → DS account 的映射
   │ Mapper        │ 支持 auto / manual 模式
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │ Sync Engine   │ 下载 TG 头像 → 裁剪/缩放
   │               │ → discord.py-self 设置 DS 账号的 avatar + nickname
   └──────┬───────┘
          │
          ├─→ Role Assigner: 按 TG group → DS guild role
          │
          └─→ Message Forwarder: TG 消息 → DS channel (以映射的 selfbot 身份发送)
```

## 和 Webhook 方案的区别

| | Webhook 方式 | Selfbot Identity Bridge |
|---|---|---|
| 消息发送者 | Webhook 机器人 (统一名称) | 独立 Discord 用户 (真人感) |
| 头像显示 | Webhook 统一头像 | 和 TG 用户一致的头像 |
| 昵称 | Webhook 名 | 和 TG 用户一致的昵称 |
| 角色 | 无 | 可按 TG group 分配 Discord 角色 |
| 消息编辑/删除 | 受限 | 天然支持 |
| 风险 | 无 | 需注意 Discord ToS (自用号，非 spam) |

## 项目结构

```
tg-discord-identity-bridge/
├── bridge/                         # Python backend
│   ├── main.py                     # 主入口，协调所有组件
│   ├── tg_listener.py              # Telethon 客户端，监听群组 + 拉取成员信息
│   ├── ds_selfbot_pool.py          # discord.py-self 批量账号池管理
│   ├── identity_mapper.py          # TG 用户 → DS 账号映射引擎
│   ├── sync_engine.py              # 头像/昵称同步
│   ├── role_assigner.py            # Discord guild 角色分配
│   ├── message_forwarder.py        # 消息转发
│   ├── cli.py                      # 命令行工具
│   └── __init__.py
├── frontend/                       # Next.js 管理面板
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── package.json
│   └── next.config.js
├── config.sample.json              # 配置模板
├── requirements.txt                # Python 依赖
├── start.bat / start.sh            # 启动脚本
└── README.md
```

## 快速开始

### 1. 获取凭证

**Telegram:**
- 去 https://my.telegram.org 创建应用，获取 `api_id` 和 `api_hash`

**Discord:**
- 准备若干 Discord 普通账号（非 Bot）
- 对每个账号，在浏览器 DevTools → Network 中找到请求头里的 `Authorization` token

### 2. 配置

```bash
cp config.sample.json config.json
# 编辑 config.json 填入你的凭证
```

```json
{
  "telegram": {
    "api_id": 12345678,
    "api_hash": "your_telegram_api_hash"
  },
  "groups": [{
    "id": -1001234567890,
    "label": "My Group",
    "discord_channels": [{"channel_id": "987654321098765432"}]
  }],
  "discord_accounts": [
    {"id": "acc01", "name": "selfbot-01", "token": "DISCORD_USER_TOKEN", "proxy": "socks5://..."}
  ],
  "sync": {"enabled": true, "interval_seconds": 300},
  "roles": {
    "enabled": true,
    "guild_id": "123456789012345678",
    "default_role": "Bridge Member",
    "group_roles": {"-1001234567890": "TG Member"}
  },
  "forwarding": {"enabled": true, "max_messages_per_minute": 30}
}
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动

```bash
# 完整启动 (监听 + 同步 + 转发)
python -m bridge

# 管理命令
python -m bridge add-account      # 添加 Discord selfbot 账号
python -m bridge list-accounts    # 列出所有账号
python -m bridge add-group        # 添加要监听的 TG 群组
python -m bridge sync-once        # 执行一次同步
```

### 前端面板 (可选)

```bash
cd frontend
pnpm install && pnpm dev     # → http://localhost:3001
```

## 核心功能详解

### TG 监听 (`tg_listener.py`)

- 基于 Telethon
- 监听指定群组的所有消息
- 首次启动扫描群组所有成员 (user_id, first_name, last_name, username, avatar)
- 消息事件类型: `NewMessage`, `MessageEdited`, `MessageDeleted`

### Discord Selfbot 池 (`ds_selfbot_pool.py`)

- 基于 `discord.py-self`
- 批量管理多个 Discord 用户账号
- 支持 SOCKS5/HTTP 代理 (每个账号独立代理)
- 连接池自动重连、速率控制
- 对外暴露: `send_message`, `edit_profile`, `add_role`, 等

### 身份映射 (`identity_mapper.py`)

映射模式:
- **auto**: 自动匹配 — 基于 user_id 哈希映射到可用的 DS 账号池
- **manual**: 手动指定 — 在 `config.mappings.pairs` 中明确 TX user → DS account

映射算法 (auto 模式):
1. 收集所有 TG 成员 + 所有可用 DS 账号
2. 对每个 TG 用户，如果已存在映射则保留，否则分配到空闲账号
3. 保存映射状态到 `mappings.json`

### 同步引擎 (`sync_engine.py`)

每个同步周期:
1. 从 TG 重新拉取成员列表
2. 对每个映射的 TG→DS pair:
   - 检查 TG 头像是否变化 (对比 hash)
   - 如有变化: 下载 TG 头像 → 裁剪/缩放 (128×128) → DS `edit(avatar=...)`
   - 检查昵称是否变化 → DS `edit(username=... 或 guild nick=...)`
3. 记录最后同步时间

### 角色分配 (`role_assigner.py`)

- 按 TG group 映射到 Discord guild role
- 例如: 来自 "VIP群" 的 TG 用户 → 其 selfbot 在 Discord 获得 "VIP" 角色
- 支持 default_role (所有 bridge selfbot 都有的基础角色)

### 消息转发 (`message_forwarder.py`)

- TG 新消息 → Discord channel
- 消息由对应的 selfbot 发送 (不是 webhook)
- 支持:
  - 文本消息
  - 图片/视频/文档附件
  - 回复链 (Discord reply)
  - 消息编辑同步
  - 速率限制

## 注意事项

- **Discord ToS**: selfbot 违反 Discord 服务条款，仅用于学习研究，风险自负
- 建议使用代理池分散 IP
- 不要在大型公开群组使用 (容易触发 Discord 风控)
- 首次登录 TG 需要交互式验证码 (手机)
- TG API ID/Hash 和 DS Token 请勿提交到公开仓库

## License

MIT

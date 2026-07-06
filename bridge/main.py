"""
tg-discord-identity-bridge  ─  Telegram → Discord 身份桥接引擎

Architecture:
  tg_listener    : Telethon client, listens to target groups, extracts member list + messages
  ds_pool        : Pool of discord.py-self selfbot clients (one per Discord account)
  identity_mapper: Maps TG user → Discord selfbot account (by config or auto-assign)
  sync_engine    : Updates each selfbot's avatar + nickname to match its mapped TG user
  role_assigner  : Assigns Discord roles by TG group membership
  msg_forwarder  : Reads TG messages → each selfbot posts as the mapped identity
  ipc            : JSON-RPC over stdout for the Next.js frontend
"""

import asyncio
import sys
import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Path setup ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Logging ─────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_LINES: List[str] = []  # ring buffer for the dashboard
MAX_LOG_LINES = 500


def log(level: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, file=sys.stderr, flush=True)
    LOG_LINES.append(line)
    if len(LOG_LINES) > MAX_LOG_LINES:
        del LOG_LINES[: len(LOG_LINES) - MAX_LOG_LINES]


# ── Config ──────────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        log("WARN", f"config.json not found at {cfg_path}, using defaults")
        return {}
    with open(cfg_path) as f:
        return json.load(f)


CONFIG = load_config()

# ── IPC ─────────────────────────────────────────────────────────────────
# When running as `python -m bridge.ipc <command>`, reply with JSON to stdout.
# The Next.js API route spawns these IPC processes for dashboard data.

_ipc_state: Dict[str, Any] = {
    "accounts": {},
    "mappings": [],
    "groups": [],
    "running": False,
}


if len(sys.argv) > 2 and sys.argv[1] == "ipc":
    _cmd = sys.argv[2]
    _payload_raw = os.environ.get("BRIDGE_IPC_PAYLOAD", "{}")
    _payload = json.loads(_payload_raw) if _payload_raw else {}
    # For IPC mode we just read state from a shared file
    _state_path = ROOT / ".state.json"
    _state = {}
    if _state_path.exists():
        _state = json.loads(_state_path.read_text())

    if _cmd == "accounts/list":
        print(json.dumps(list(_state.get("accounts", {}).values())))
    elif _cmd == "accounts/add":
        print(json.dumps({"status": "ipc_only", "message": "add accounts via config.json or CLI"}))
    elif _cmd == "accounts/delete":
        print(json.dumps({"status": "ipc_only", "message": "delete accounts via config.json or CLI"}))
    elif _cmd == "mappings/list":
        print(json.dumps(_state.get("mappings", [])))
    elif _cmd == "groups/list":
        print(json.dumps(_state.get("groups", [])))
    elif _cmd == "logs":
        limit = _payload.get("limit", 20)
        print(json.dumps(LOG_LINES[-limit:] if LOG_LINES else []))
    elif _cmd == "config/get":
        print(json.dumps(CONFIG))
    elif _cmd == "sync/trigger":
        print(json.dumps({"status": "sync_triggered"}))
    elif _cmd == "status":
        print(json.dumps({"running": _ipc_state.get("running", False), "ts": time.time()}))
    else:
        print(json.dumps({"error": f"unknown ipc command: {_cmd}"}))
    sys.exit(0)


# ── Imports (lazy, after IPC fast-path) ─────────────────────────────────
from bridge.tg_listener import TelegramListener
from bridge.ds_pool import DiscordSelfbotPool
from bridge.identity_mapper import IdentityMapper
from bridge.sync_engine import SyncEngine
from bridge.role_assigner import RoleAssigner
from bridge.message_forwarder import MessageForwarder


# ── Main App ────────────────────────────────────────────────────────────
class BridgeApp:
    """Orchestrates all components."""

    def __init__(self) -> None:
        self.cfg = CONFIG
        self.tg_listener: Optional[TelegramListener] = None
        self.ds_pool: Optional[DiscordSelfbotPool] = None
        self.mapper: Optional[IdentityMapper] = None
        self.sync_engine: Optional[SyncEngine] = None
        self.role_assigner: Optional[RoleAssigner] = None
        self.forwarder: Optional[MessageForwarder] = None
        self._running = False

    async def start(self) -> None:
        log("INFO", "=== TG→Discord Identity Bridge starting ===")

        # 1. Start Telegram listener
        tg_cfg = self.cfg.get("telegram", {})
        self.tg_listener = TelegramListener(
            api_id=tg_cfg.get("api_id", 0),
            api_hash=tg_cfg.get("api_hash", ""),
            session_path=str(ROOT / "tg_session"),
            monitored_groups=self.cfg.get("groups", []),
        )
        await self.tg_listener.connect()
        log("INFO", "Telegram listener connected")

        # 2. Discover TG members
        all_members: Dict[int, dict] = {}  # tg_user_id → member_info
        for group in self.cfg.get("groups", []):
            members = await self.tg_listener.get_members(group["id"])
            for m in members:
                all_members[m["user_id"]] = m
        log("INFO", f"Discovered {len(all_members)} unique Telegram members across {len(self.cfg.get('groups',[]))} groups")

        # 3. Start Discord selfbot pool
        ds_accounts = self.cfg.get("discord_accounts", [])
        self.ds_pool = DiscordSelfbotPool(ds_accounts)
        await self.ds_pool.start_all()
        log("INFO", f"Discord pool: {len(ds_accounts)} accounts, {len(self.ds_pool.ready_clients)} ready")

        # 4. Identity mapper
        self.mapper = IdentityMapper(
            tg_members=all_members,
            ds_accounts=ds_accounts,
            mapping_cfg=self.cfg.get("mappings", {}),
        )
        mappings = self.mapper.compute()
        log("INFO", f"Identity mappings computed: {len(mappings)} pairs")

        # 5. Sync engine (avatar + nickname)
        if self.cfg.get("sync", {}).get("enabled", True):
            self.sync_engine = SyncEngine(
                mapper=self.mapper,
                ds_pool=self.ds_pool,
                tg_listener=self.tg_listener,
            )
            await self.sync_engine.sync_all()
            log("INFO", "Initial identity sync complete")

        # 6. Role assigner
        if self.cfg.get("roles", {}).get("enabled", True):
            self.role_assigner = RoleAssigner(
                mapper=self.mapper,
                ds_pool=self.ds_pool,
                role_cfg=self.cfg.get("roles", {}),
            )
            await self.role_assigner.assign_all()
            log("INFO", "Role assignment complete")

        # 7. Message forwarder
        if self.cfg.get("forwarding", {}).get("enabled", True):
            self.forwarder = MessageForwarder(
                tg_listener=self.tg_listener,
                mapper=self.mapper,
                ds_pool=self.ds_pool,
                forward_cfg=self.cfg.get("forwarding", {}),
                group_cfg=self.cfg.get("groups", []),
            )
            self.forwarder.start()
            log("INFO", "Message forwarder started")

        # 8. Set up periodic re-sync
        resync_interval = self.cfg.get("sync", {}).get("interval_seconds", 300)
        asyncio.create_task(self._periodic_sync(resync_interval))

        # 9. Set up TG member change watcher
        asyncio.create_task(self._watch_member_changes())

        self._running = True
        _ipc_state["running"] = True
        _ipc_state["accounts"] = {a["id"]: a for a in ds_accounts}
        _ipc_state["mappings"] = [
            {"tg_user_id": tg_id, "tg_name": m["tg_name"], "discord_account_id": m["ds_account_id"], "discord_name": m["ds_name"], "synced": m["synced"]}
            for tg_id, m in self.mapper.tg_to_ds.items()
        ]
        _ipc_state["groups"] = self.cfg.get("groups", [])

        log("INFO", "=== Bridge running ===")

    async def _periodic_sync(self, interval: int) -> None:
        while self._running:
            await asyncio.sleep(interval)
            if self.sync_engine:
                log("INFO", f"Periodic re-sync ({interval}s)")
                await self.sync_engine.sync_all()
                if self.role_assigner:
                    await self.role_assigner.assign_all()

    async def _watch_member_changes(self) -> None:
        """Watch for TG member join/leave and auto-rebalance mappings."""
        if not self.tg_listener:
            return
        async for event in self.tg_listener.watch_member_events():
            log("INFO", f"TG member event: {event['type']} user={event.get('user_id')}")
            if self.mapper and self.sync_engine:
                self.mapper.handle_member_event(event)
                await self.sync_engine.sync_user(event["user_id"])

    async def stop(self) -> None:
        log("INFO", "Shutting down...")
        self._running = False
        _ipc_state["running"] = False
        if self.forwarder:
            self.forwarder.stop()
        if self.ds_pool:
            await self.ds_pool.stop_all()
        if self.tg_listener:
            await self.tg_listener.disconnect()
        log("INFO", "Bridge stopped")


# ── Entrypoint ──────────────────────────────────────────────────────────
async def main():
    app = BridgeApp()
    loop = asyncio.get_running_loop()

    def shutdown():
        log("INFO", "Received shutdown signal")
        asyncio.ensure_future(app.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            pass

    try:
        await app.start()
        # Keep alive
        while app._running:
            await asyncio.sleep(1)
    except Exception as e:
        log("ERROR", f"Fatal: {e}")
        raise
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())

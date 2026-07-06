"""
CLI  ─  tg-discord-identity-bridge command-line interface.

Usage:
  python -m bridge                       # start the bridge
  python -m bridge check                  # check config & connectivity
  python -m bridge add-account            # interactively add a Discord selfbot account
  python -m bridge list-accounts          # list all configured accounts
  python -m bridge add-group              # add a TG group to monitor
  python -m bridge sync-once              # run one sync cycle then exit
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_cfg() -> dict:
    p = ROOT / "config.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _save_cfg(cfg: dict) -> None:
    p = ROOT / "config.json"
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def cmd_add_account() -> None:
    """Interactively add a Discord selfbot account."""
    cfg = _load_cfg()
    accounts = cfg.setdefault("discord_accounts", [])

    print("=== Add Discord Selfbot Account ===")
    name = input("Account name (label): ").strip()
    token = input("Discord user token: ").strip()
    proxy = input("Proxy URL (optional, press Enter to skip): ").strip()

    import hashlib
    acc_id = hashlib.md5(token.encode()).hexdigest()[:12]

    accounts.append({
        "id": acc_id,
        "name": name or acc_id,
        "token": token,
        "proxy": proxy or None,
    })
    _save_cfg(cfg)
    print(f"Account '{name}' added (id={acc_id})")
    print(f"Total accounts: {len(accounts)}")


def cmd_list_accounts() -> None:
    """List all configured Discord selfbot accounts."""
    cfg = _load_cfg()
    accounts = cfg.get("discord_accounts", [])
    if not accounts:
        print("No accounts configured.")
        return

    print(f"{'ID':<14} {'Name':<20} {'Proxy':<30}")
    print("-" * 64)
    for a in accounts:
        proxy = a.get("proxy") or "-"
        print(f"{a['id']:<14} {a['name']:<20} {proxy:<30}")
    print(f"\n{len(accounts)} account(s) total")


def cmd_add_group() -> None:
    """Add a Telegram group to monitor."""
    cfg = _load_cfg()
    groups = cfg.setdefault("groups", [])

    print("=== Add Telegram Group ===")
    gid = input("Group ID (e.g., -1001234567890): ").strip()
    label = input("Group label/name: ").strip()
    dc_channels = input("Discord channel IDs for forwarding (comma-separated): ").strip()

    channels = []
    for ch in dc_channels.split(","):
        ch = ch.strip()
        if ch:
            channels.append({"channel_id": ch})

    groups.append({
        "id": int(gid) if gid.lstrip("-").isdigit() else gid,
        "label": label,
        "discord_channels": channels,
    })
    _save_cfg(cfg)
    print(f"Group '{label}' added, forwarding to {len(channels)} Discord channel(s)")


def cmd_sync_once() -> None:
    """Run a single sync cycle and exit."""
    from bridge.main import BridgeApp
    async def _run():
        app = BridgeApp()
        # Quick start without full forwarding
        await app.tg_listener.connect()
        members = {}
        for g in app.cfg.get("groups", []):
            m = await app.tg_listener.get_members(g["id"])
            for u in m:
                members[u["user_id"]] = u
        app.mapper = app.mapper.__class__(members, app.cfg.get("discord_accounts", []), app.cfg.get("mappings", {}))
        app.mapper.compute()

        await app.ds_pool.start_all()
        app.sync_engine = app.sync_engine.__class__(app.mapper, app.ds_pool, app.tg_listener)
        await app.sync_engine.sync_all()

        if app.cfg.get("roles", {}).get("enabled"):
            app.role_assigner = app.role_assigner.__class__(app.mapper, app.ds_pool, app.cfg.get("roles", {}))
            await app.role_assigner.assign_all()

        await app.stop()
    asyncio.run(_run())


COMMANDS = {
    "add-account": cmd_add_account,
    "list-accounts": cmd_list_accounts,
    "add-group": cmd_add_group,
    "sync-once": cmd_sync_once,
}


def main():
    if len(sys.argv) < 2:
        # Default: start the full bridge
        from bridge.main import main as bridge_main
        asyncio.run(bridge_main())
        return

    cmd = sys.argv[1]
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    elif cmd == "help":
        print("Commands: add-account, list-accounts, add-group, sync-once")
        print("Run without arguments to start the full bridge.")
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: add-account, list-accounts, add-group, sync-once")


if __name__ == "__main__":
    main()

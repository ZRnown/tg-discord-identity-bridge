"""
Identity mapper  ─  maps Telegram users to Discord selfbot accounts.

Strategy (configurable):
  - manual : Explicit mapping from config.
  - auto    : Round-robin / hash-based auto-assign.
  - per_group : One TG group → one Discord guild, auto-assign within guild.

The mapper maintains a live state that syncs with the dashboard.
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger as _log


class IdentityMapper:
    """Maps Telegram identity → Discord selfbot account."""

    def __init__(
        self,
        tg_members: Dict[int, dict],
        ds_accounts: List[dict],
        mapping_cfg: dict,
    ) -> None:
        self.tg_members = tg_members  # tg_user_id → {username, display_name, has_photo, group_id,...}
        self.ds_accounts = ds_accounts  # [{id, name, token, proxy,...}]
        self.mapping_cfg = mapping_cfg
        self.mode = mapping_cfg.get("mode", "auto")  # "manual" | "auto" | "per_group"

        # Core mapping: tg_user_id → {ds_account_id, tg_name, ds_name, synced, group_id, ...}
        self.tg_to_ds: Dict[int, dict] = {}

        # Reverse: ds_account_id → tg_user_id
        self.ds_to_tg: Dict[str, int] = {}

        # Track used DS accounts
        self._used_ds_ids: set = set()

    def compute(self) -> Dict[int, dict]:
        """Compute or refresh all mappings. Returns tg_to_ds."""
        if self.mode == "manual":
            self._compute_manual()
        elif self.mode == "per_group":
            self._compute_per_group()
        else:  # auto
            self._compute_auto()

        _log.info(f"Mapping complete: {len(self.tg_to_ds)} TG users → DS accounts")
        return self.tg_to_ds

    def _compute_manual(self) -> None:
        """Read explicit mappings from config. Unmapped users are left unassigned."""
        explicit: List[dict] = self.mapping_cfg.get("pairs", [])
        available_ids = {a["id"] for a in self.ds_accounts}

        for pair in explicit:
            tg_id = pair["tg_user_id"]
            ds_id = pair["discord_account_id"]
            if ds_id not in available_ids:
                _log.warning(f"Manual mapping references unknown DS account: {ds_id}")
                continue
            tg_user = self.tg_members.get(tg_id)
            self.tg_to_ds[tg_id] = {
                "ds_account_id": ds_id,
                "ds_name": next((a["name"] for a in self.ds_accounts if a["id"] == ds_id), ds_id),
                "tg_name": tg_user.get("display_name", f"TG-{tg_id}") if tg_user else f"TG-{tg_id}",
                "tg_username": tg_user.get("username", "") if tg_user else "",
                "tg_has_photo": tg_user.get("has_photo", False) if tg_user else False,
                "group_id": tg_user.get("group_id", 0) if tg_user else 0,
                "synced": False,
                "mode": "manual",
            }
            self.ds_to_tg[ds_id] = tg_id
            self._used_ds_ids.add(ds_id)

    def _compute_auto(self) -> None:
        """Auto-assign: round-robin TG users onto available DS accounts."""
        available = [a for a in self.ds_accounts if a["id"] not in self._used_ds_ids]
        if not available:
            _log.warning("No available DS accounts for auto-assignment")
            return

        idx = 0
        for tg_id, tg_user in self.tg_members.items():
            if tg_id in self.tg_to_ds:
                continue
            ds = available[idx % len(available)]
            self.tg_to_ds[tg_id] = {
                "ds_account_id": ds["id"],
                "ds_name": ds["name"],
                "tg_name": tg_user.get("display_name", f"TG-{tg_id}"),
                "tg_username": tg_user.get("username", ""),
                "tg_has_photo": tg_user.get("has_photo", False),
                "group_id": tg_user.get("group_id", 0),
                "synced": False,
                "mode": "auto",
            }
            self.ds_to_tg[ds["id"]] = tg_id
            self._used_ds_ids.add(ds["id"])
            idx += 1

    def _compute_per_group(self) -> None:
        """Map TG members within each group to DS accounts assigned to that group's guild."""
        group_guilds: dict = self.mapping_cfg.get("group_guilds", {})  # group_id → guild_id
        guild_ds_map: dict = self.mapping_cfg.get("guild_ds_map", {})  # guild_id → [ds_account_id,...]

        # For each group, find which DS accounts are assigned to its guild
        for tg_id, tg_user in self.tg_members.items():
            if tg_id in self.tg_to_ds:
                continue
            gid = tg_user.get("group_id", 0)
            guild_id = group_guilds.get(str(gid), group_guilds.get(gid))
            if not guild_id:
                continue  # no guild mapping for this group
            ds_ids = guild_ds_map.get(str(guild_id), guild_ds_map.get(guild_id, []))
            if not ds_ids:
                continue  # no DS accounts assigned to this guild

            # Hash-based assignment (deterministic per user)
            hash_val = int(hashlib.md5(str(tg_id).encode()).hexdigest(), 16)
            ds_id = ds_ids[hash_val % len(ds_ids)]
            self.tg_to_ds[tg_id] = {
                "ds_account_id": ds_id,
                "ds_name": next((a["name"] for a in self.ds_accounts if a["id"] == ds_id), ds_id),
                "tg_name": tg_user.get("display_name", f"TG-{tg_id}"),
                "tg_username": tg_user.get("username", ""),
                "tg_has_photo": tg_user.get("has_photo", False),
                "group_id": gid,
                "synced": False,
                "mode": "per_group",
            }
            self.ds_to_tg[ds_id] = tg_id
            self._used_ds_ids.add(ds_id)

    def handle_member_event(self, event: dict) -> None:
        """Handle a TG member join/leave event. Add or remove from mapping."""
        event_type = event.get("type")
        tg_id = event.get("user_id")
        if not tg_id:
            return

        if event_type == "join":
            tg_user = {
                "user_id": tg_id,
                "display_name": event.get("display_name", f"TG-{tg_id}"),
                "username": event.get("username", ""),
                "has_photo": event.get("has_photo", False),
                "group_id": event.get("group_id", 0),
            }
            self.tg_members[tg_id] = tg_user
            self._compute_auto()  # re-compute to assign new user
        elif event_type == "leave":
            self.tg_members.pop(tg_id, None)
            entry = self.tg_to_ds.pop(tg_id, None)
            if entry:
                self.ds_to_tg.pop(entry["ds_account_id"], None)

    def get_ds_account_for_tg(self, tg_user_id: int) -> Optional[str]:
        """Given a TG user ID, return the Discord account ID that impersonates them."""
        entry = self.tg_to_ds.get(tg_user_id)
        return entry["ds_account_id"] if entry else None

    def get_tg_user_for_ds(self, ds_account_id: str) -> Optional[int]:
        """Given a Discord account ID, return the TG user it impersonates."""
        return self.ds_to_tg.get(ds_account_id)

    def get_mapping_for_dashboard(self) -> List[dict]:
        """Return a list of mappings suitable for the dashboard."""
        return [
            {
                "tg_user_id": tg_id,
                "tg_name": info.get("tg_name", ""),
                "tg_username": info.get("tg_username", ""),
                "discord_account_id": info.get("ds_account_id", ""),
                "discord_name": info.get("ds_name", ""),
                "group_id": info.get("group_id", 0),
                "synced": info.get("synced", False),
                "mode": info.get("mode", "auto"),
            }
            for tg_id, info in self.tg_to_ds.items()
        ]

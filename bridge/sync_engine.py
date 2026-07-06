"""
Sync engine  ─  syncs Discord selfbot avatars and nicknames to match Telegram users.

For each mapping (TG user → DS account):
  1. Download the TG user's profile photo via Telethon
  2. Upload it as the DS selfbot's avatar via discord.py-self
  3. Set the DS selfbot's global username and per-guild nickname
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger as _log


class SyncEngine:
    """Drives the identity sync pipeline: TG → avatar/nickname → Discord."""

    def __init__(
        self,
        mapper: Any,       # IdentityMapper
        ds_pool: Any,      # DiscordSelfbotPool
        tg_listener: Any,  # TelegramListener
    ) -> None:
        self.mapper = mapper
        self.ds_pool = ds_pool
        self.tg_listener = tg_listener
        self.sync_state: Dict[int, Dict[str, Any]] = {}  # tg_id → sync status
        self._avatar_cache: Dict[int, bytes] = {}        # tg_id → raw avatar bytes

    async def sync_all(self) -> Dict[int, dict]:
        """Run a full sync cycle: all mapped users get avatar + name updated."""
        results: Dict[int, dict] = {}

        for tg_id, mapping in self.mapper.tg_to_ds.items():
            ds_id = mapping["ds_account_id"]
            result = await self.sync_user(tg_id, ds_id)
            results[tg_id] = result

        synced = sum(1 for r in results.values() if r.get("success"))
        failed = len(results) - synced
        _log.info(f"Sync cycle complete: {synced} ok, {failed} failed")
        return results

    async def sync_user(self, tg_user_id: int, ds_account_id: Optional[str] = None) -> Dict[str, Any]:
        """Sync a single user's identity to their mapped Discord account."""
        ds_id = ds_account_id or self.mapper.get_ds_account_for_tg(tg_user_id)
        if not ds_id:
            return {"success": False, "error": "no mapping"}

        mapping = self.mapper.tg_to_ds.get(tg_user_id, {})
        tg_name = mapping.get("tg_name", f"TG-{tg_user_id}")

        result = {"success": True, "tg_user_id": tg_user_id, "ds_account_id": ds_id, "steps": []}

        # 1. Sync avatar (if available)
        if mapping.get("tg_has_photo"):
            avatar_result = await self._sync_avatar(tg_user_id, ds_id)
            result["steps"].append(avatar_result)
            if not avatar_result.get("success"):
                result["success"] = False

        # 2. Sync global username
        name_result = await self._sync_username(tg_user_id, ds_id, tg_name)
        result["steps"].append(name_result)

        # 3. Sync per-guild nickname (if configured)
        group_id = mapping.get("group_id", 0)
        guild_result = await self._sync_guild_nickname(tg_user_id, ds_id, tg_name, group_id)
        if guild_result:
            result["steps"].append(guild_result)

        # Update sync state
        self.sync_state[tg_user_id] = {
            "ds_account_id": ds_id,
            "last_sync": True,
            "tg_name": tg_name,
            "result": result,
        }

        # Update mapping
        if result["success"]:
            self.mapper.tg_to_ds[tg_user_id]["synced"] = True

        return result

    async def _sync_avatar(self, tg_user_id: int, ds_id: str) -> Dict[str, Any]:
        """Download TG avatar → upload as Discord avatar."""
        try:
            # Download TG avatar
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name

            ok = await self.tg_listener.download_avatar(tg_user_id, tmp_path)
            if not ok:
                return {"step": "avatar", "success": False, "error": "download failed"}

            # Read into bytes
            with open(tmp_path, "rb") as f:
                avatar_bytes = f.read()

            # Cache
            self._avatar_cache[tg_user_id] = avatar_bytes

            # Upload to Discord
            ok = await self.ds_pool.edit_profile(ds_id, avatar_bytes=avatar_bytes)
            if not ok:
                return {"step": "avatar", "success": False, "error": "discord upload failed"}

            # Cleanup
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

            return {"step": "avatar", "success": True}
        except Exception as e:
            return {"step": "avatar", "success": False, "error": str(e)}

    async def _sync_username(self, tg_user_id: int, ds_id: str, tg_name: str) -> Dict[str, Any]:
        """Set the Discord selfbot's global username to match the TG display name."""
        # Discord usernames have constraints:
        #  - 2-32 chars
        #  - alphanumeric, underscore, period (no spaces in global name)
        # For global username we use the underscore version
        safe_name = self._sanitize_username(tg_name)
        try:
            ok = await self.ds_pool.edit_profile(ds_id, username=safe_name)
            return {"step": "username", "success": ok, "username": safe_name}
        except Exception as e:
            return {"step": "username", "success": False, "error": str(e)}

    async def _sync_guild_nickname(
        self, tg_user_id: int, ds_id: str, tg_name: str, group_id: int
    ) -> Optional[Dict[str, Any]]:
        """Set per-guild nickname to TG display name (guild nicknames allow spaces)."""
        # Look up what guild this TG group maps to
        group_guilds = self.mapper.mapping_cfg.get("group_guilds", {})
        guild_id = group_guilds.get(str(group_id), group_guilds.get(group_id))
        if not guild_id:
            return None

        try:
            ok = await self.ds_pool.set_guild_nickname(ds_id, int(guild_id), tg_name)
            return {"step": "guild_nickname", "success": ok, "guild_id": guild_id, "nickname": tg_name}
        except Exception as e:
            return {"step": "guild_nickname", "success": False, "error": str(e)}

    @staticmethod
    def _sanitize_username(name: str) -> str:
        """Convert a TG display name to a Discord-safe username."""
        import re
        # Discord global username: 2-32 chars, a-z0-9._ only, lowercase
        cleaned = re.sub(r"[^a-zA-Z0-9._]", "_", name)
        cleaned = cleaned.strip("._")
        if len(cleaned) < 2:
            cleaned = cleaned + "00"
        if len(cleaned) > 32:
            cleaned = cleaned[:32]
        return cleaned.lower()

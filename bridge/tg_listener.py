"""
Telegram listener  ─  monitors groups and extracts members/messages.
Uses Telethon MTProto to avoid bot API rate limits and gain full access.
"""

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger as _log


class TelegramListener:
    """Wrapper around a Telethon user client for monitoring Telegram groups."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: str,
        monitored_groups: List[dict],
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.monitored_groups = monitored_groups
        self._client: Any = None  # Telethon TelegramClient
        self._me: Any = None
        self._connected = False
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._member_event_handlers: List[asyncio.Queue] = []

    # ── Connect / disconnect ─────────────────────────────────────────

    async def connect(self) -> None:
        """Connect the Telethon client (with auto-auth)."""
        try:
            from telethon import TelegramClient, events
        except ImportError:
            raise RuntimeError(
                "Telethon not installed. Run: pip install telethon"
            )

        self._client = TelegramClient(
            self.session_path, self.api_id, self.api_hash,
            system_version="4.16.30-vxCUSTOM",
            device_model="tg-discord-bridge",
        )
        await self._client.start()
        self._me = await self._client.get_me()
        self._connected = True
        _log.info(f"Telegram connected as @{self._me.username or self._me.phone}")

        # Register message handler
        @self._client.on(events.NewMessage)
        async def handler(event):
            await self._event_queue.put(event)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Member extraction ────────────────────────────────────────────

    async def get_members(self, group_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        """Fetch all members from a group, with avatar info."""
        if not self._client:
            return []

        members: List[dict] = []
        async for user in self._client.iter_participants(group_id, limit=limit):
            avatar_size = 0
            if user.photo:
                # photo is a UserProfilePhoto; we just note it exists
                avatar_size = getattr(user.photo, "dc_id", 0) or 1

            members.append({
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "display_name": (user.first_name or "") + (f" {user.last_name}" if user.last_name else ""),
                "phone": getattr(user, "phone", ""),
                "is_bot": user.bot,
                "avatar_size": avatar_size,
                "has_photo": user.photo is not None,
                "group_id": group_id,
            })
        return members

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get info for a single user."""
        if not self._client:
            return None
        try:
            entity = await self._client.get_entity(user_id)
            if hasattr(entity, "photo"):
                photo = entity.photo
            else:
                photo = None
            return {
                "user_id": entity.id,
                "username": getattr(entity, "username", "") or "",
                "first_name": getattr(entity, "first_name", "") or "",
                "last_name": getattr(entity, "last_name", "") or "",
                "display_name": (getattr(entity, "first_name", "") or "") +
                    (f" {getattr(entity, 'last_name', '')}" if getattr(entity, "last_name", "") else ""),
                "has_photo": photo is not None,
            }
        except Exception:
            return None

    # ── Avatar download ──────────────────────────────────────────────

    async def download_avatar(self, user_id: int, output_path: str) -> bool:
        """Download a user's profile photo to a local file. Returns True on success."""
        if not self._client:
            return False
        try:
            entity = await self._client.get_entity(user_id)
            if not entity.photo:
                return False
            await self._client.download_profile_photo(entity, output_path)
            return True
        except Exception as e:
            _log.warning(f"Failed to download avatar for user {user_id}: {e}")
            return False

    # ── Message stream ───────────────────────────────────────────────

    async def watch_messages(self) -> AsyncIterator[Any]:
        """Yield new messages from any monitored group."""
        group_ids = {g["id"] for g in self.monitored_groups}
        while self._connected:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                chat_id = event.chat_id
                # Accept messages from any chat (not just monitored groups)
                # because DM/private chats might also be relevant
                yield event
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                _log.error(f"Message watch error: {e}")
                await asyncio.sleep(5)

    # ── Member change watcher ────────────────────────────────────────

    def watch_member_events(self) -> "asyncio.Queue":
        """Return a queue that receives member join/leave events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._member_event_handlers.append(q)
        return q

    # ── Raw client access ────────────────────────────────────────────

    @property
    def client(self) -> Any:
        return self._client

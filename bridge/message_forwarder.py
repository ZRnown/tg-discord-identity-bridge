"""
Message forwarder  ─  forwards Telegram messages to Discord via selfbot accounts.

Each message is posted by the selfbot that impersonates the TG sender.
Messages appear as if sent natively by the Discord user (no webhook metadata).

Supports:
  - Text messages
  - Media attachments (photos, videos, documents, stickers)
  - Reply chains (forwarded as Discord replies)
  - Edits and deletions (best-effort)
  - Rate limiting and batching
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger as _log


class MessageForwarder:
    """Listens for Telegram messages and forwards them to Discord via mapped selfbots."""

    def __init__(
        self,
        tg_listener: Any,     # TelegramListener
        mapper: Any,          # IdentityMapper
        ds_pool: Any,         # DiscordSelfbotPool
        forward_cfg: dict,
        group_cfg: List[dict],
    ) -> None:
        self.tg_listener = tg_listener
        self.mapper = mapper
        self.ds_pool = ds_pool
        self.forward_cfg = forward_cfg
        self.group_cfg = group_cfg

        # group_id → [{channel_id, guild_id,...}] (one TG group may map to multiple DS channels)
        self.group_channel_map: Dict[int, List[dict]] = {}
        for g in group_cfg:
            gid = g.get("id", 0)
            channels = g.get("discord_channels", [])
            self.group_channel_map[gid] = channels

        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Message cache for edit/delete support: {tg_msg_id: {ds_channel_id, ds_msg_id, ds_account_id}}
        self._message_cache: Dict[int, List[dict]] = {}
        self._max_cache = forward_cfg.get("message_cache_size", 5000)

    def start(self) -> None:
        """Start the forwarding loop in the background."""
        self._running = True
        self._task = asyncio.create_task(self._forward_loop())

    def stop(self) -> None:
        """Stop the forwarding loop."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _forward_loop(self) -> None:
        """Main loop: watch TG messages → forward to Discord."""
        _log.info("Message forwarder loop started")
        async for event in self.tg_listener.watch_messages():
            if not self._running:
                break
            try:
                await self._handle_event(event)
            except Exception as e:
                _log.error(f"Forwarder event error: {e}")

    async def _handle_event(self, event: Any) -> None:
        """Handle a single TG message event."""
        message = event.message
        if not message:
            return

        chat_id = event.chat_id
        sender = await message.get_sender()
        if not sender:
            return

        sender_id = sender.id

        # Check if this is a monitored group
        target_channels = self.group_channel_map.get(chat_id, [])
        if not target_channels:
            # Try matching by chat title or ID in group_cfg
            for g in self.group_cfg:
                if g.get("id") == chat_id or (isinstance(g.get("id"), str) and str(chat_id) == g["id"]):
                    target_channels = g.get("discord_channels", [])
                    break
        if not target_channels:
            return  # not a monitored group

        # Determine which selfbot should post this
        ds_account_id = self.mapper.get_ds_account_for_tg(sender_id)
        if not ds_account_id:
            _log.debug(f"No DS mapping for TG user {sender_id}, message skipped")
            return

        # Format the message
        content = self._format_message(message)

        # Forward to each mapped Discord channel
        for ch in target_channels:
            channel_id = int(ch["channel_id"])
            await self._forward_message(
                ds_account_id=ds_account_id,
                channel_id=channel_id,
                content=content,
                tg_message=message,
                tg_event=event,
            )

    async def _forward_message(
        self,
        ds_account_id: str,
        channel_id: int,
        content: str,
        tg_message: Any,
        tg_event: Any,
    ) -> None:
        """Forward a single message to a Discord channel as the mapped selfbot."""
        tg_msg_id = tg_message.id

        # Check if this is an edit
        if tg_message.edit_date and hasattr(tg_message, "edit_date"):
            # Try to edit the previously sent Discord message
            cached = self._message_cache.get(tg_msg_id, [])
            for entry in cached:
                if entry["ds_channel_id"] == channel_id:
                    await self._edit_discord_message(
                        ds_account_id, channel_id, entry["ds_msg_id"], content
                    )
                    return

        # Download media if present
        files: List[str] = []
        if tg_message.media:
            media_paths = await self._download_media(tg_message)
            files.extend(media_paths)

        # Send
        ds_msg_id = await self.ds_pool.send_message(
            ds_account_id, channel_id, content, files=files
        )

        # Cache for edit/delete
        if ds_msg_id:
            entry = {
                "ds_channel_id": channel_id,
                "ds_msg_id": ds_msg_id,
                "ds_account_id": ds_account_id,
            }
            if tg_msg_id not in self._message_cache:
                self._message_cache[tg_msg_id] = []
            self._message_cache[tg_msg_id].append(entry)

            # Prune cache
            if len(self._message_cache) > self._max_cache:
                oldest = sorted(self._message_cache.keys())[:100]
                for k in oldest:
                    del self._message_cache[k]

        # Cleanup temp media files
        for fp in files:
            try:
                os.unlink(fp)
            except OSError:
                pass

    async def _edit_discord_message(
        self,
        ds_account_id: str,
        channel_id: int,
        ds_msg_id: str,
        new_content: str,
    ) -> None:
        """Edit a previously forwarded Discord message."""
        client = self.ds_pool.get_client(ds_account_id)
        if not client:
            return
        try:
            channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            if not channel:
                return
            msg = await channel.fetch_message(int(ds_msg_id))
            if msg:
                await msg.edit(content=new_content)
        except Exception as e:
            _log.debug(f"Edit failed: {e}")

    async def _download_media(self, message: Any) -> List[str]:
        """Download media from a TG message to temp files. Returns list of paths."""
        paths: List[str] = []
        try:
            tg_client = self.tg_listener.client
            if not tg_client:
                return paths

            media_path = await tg_client.download_media(message, file=tempfile.gettempdir())
            if media_path and isinstance(media_path, str):
                # Telethon returns a single path; for albums it's different
                paths.append(media_path)
        except Exception as e:
            _log.warning(f"Media download failed: {e}")
        return paths

    def _format_message(self, message: Any) -> str:
        """Format a TG message for Discord display."""
        text = message.text or message.message or ""

        # If message has media but no text, add an indicator
        if message.media and not text.strip():
            media_type = type(message.media).__name__.replace("MessageMedia", "")
            if media_type == "Photo":
                text = "[photo]"
            elif media_type == "Document":
                text = "[document]"
            elif "Video" in media_type:
                text = "[video]"
            elif "Sticker" in media_type:
                text = "[sticker]"
            else:
                text = "[media]"

        return text

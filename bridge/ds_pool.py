"""
Discord selfbot pool  ─  manages a pool of discord.py-self clients.
Each selfbot account runs in its own event loop thread with isolated state.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

from loguru import logger as _log


@dataclass
class SelfbotInstance:
    """State for one selfbot account."""
    account_id: str
    account_name: str
    token: str
    proxy: Optional[str] = None
    client: Any = None  # discord.Client (discord.py-self)
    ready: bool = False
    last_error: str = ""
    guilds: List[Dict[str, Any]] = field(default_factory=list)
    user_info: Dict[str, Any] = field(default_factory=dict)
    # Rate-limit tracking
    request_count: int = 0
    request_window_start: float = 0.0


class DiscordSelfbotPool:
    """Manages a collection of selfbot accounts, each as an isolated discord.py-self client.

    Uses ThreadPoolExecutor so each selfbot runs its own asyncio event loop on its own thread,
    avoiding the single-threaded bottleneck of discord.py's blocking calls.
    """

    MAX_REQUESTS_PER_MINUTE = 30  # per-account safety cap
    MAX_CONCURRENT_LOGINS = 5     # stagger logins

    def __init__(self, accounts: List[dict]) -> None:
        self._accounts: Dict[str, SelfbotInstance] = {}
        self._executor = ThreadPoolExecutor(max_workers=max(1, len(accounts)))
        self._futures: Dict[str, Any] = {}

        for acc in accounts:
            inst = SelfbotInstance(
                account_id=acc.get("id", acc.get("token", "")[:16]),
                account_name=acc.get("name", "unnamed"),
                token=acc.get("token", ""),
                proxy=acc.get("proxy"),
            )
            self._accounts[inst.account_id] = inst

    # ── Start / stop ─────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all selfbot clients, staggered to avoid rate limits."""
        sem = asyncio.Semaphore(self.MAX_CONCURRENT_LOGINS)

        async def _start_one(inst: SelfbotInstance):
            async with sem:
                loop = asyncio.get_running_loop()
                fut = loop.run_in_executor(self._executor, self._run_selfbot_sync, inst)
                self._futures[inst.account_id] = fut

        tasks = [_start_one(inst) for inst in self._accounts.values() if not inst.ready]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            # Wait a beat for all to register readiness
            await asyncio.sleep(2)

    def _run_selfbot_sync(self, inst: SelfbotInstance) -> None:
        """Run a single selfbot in its own thread + event loop."""
        try:
            import discord
        except ImportError:
            inst.last_error = "discord.py-self not installed"
            _log.error(f"[{inst.account_name}] discord.py-self not installed. Run: pip install discord.py-self")
            return

        async def _login():
            try:
                # discord.py-self monkey-patches discord.py to use user tokens
                intents = discord.Intents.default()
                intents.message_content = True
                intents.members = True
                intents.guilds = True

                inst.client = discord.Client(intents=intents)

                @inst.client.event
                async def on_ready():
                    inst.ready = True
                    inst.user_info = {
                        "id": str(inst.client.user.id),
                        "name": str(inst.client.user),
                        "display_name": inst.client.user.display_name,
                        "avatar_url": str(inst.client.user.display_avatar.url) if inst.client.user.display_avatar else "",
                    }
                    # Collect guilds
                    inst.guilds = [
                        {"id": str(g.id), "name": g.name}
                        for g in inst.client.guilds
                    ]
                    _log.info(
                        f"[{inst.account_name}] ready as {inst.client.user} "
                        f"({len(inst.guilds)} guilds)"
                    )

                @inst.client.event
                async def on_disconnect():
                    inst.ready = False
                    _log.warning(f"[{inst.account_name}] disconnected")

                proxy_url = inst.proxy or None
                await inst.client.start(inst.token, bot=False)
            except Exception as e:
                inst.last_error = str(e)
                inst.ready = False
                _log.error(f"[{inst.account_name}] login failed: {e}")

        try:
            asyncio.run(_login())
        except Exception as e:
            inst.last_error = str(e)
            _log.error(f"[{inst.account_name}] event loop crashed: {e}")

    async def stop_all(self) -> None:
        """Gracefully stop all selfbot clients."""
        for inst in self._accounts.values():
            if inst.client and inst.ready:
                try:
                    await inst.client.close()
                except Exception:
                    pass
            inst.ready = False
        self._executor.shutdown(wait=False)

    # ── Lookup ───────────────────────────────────────────────────────

    def get_client(self, account_id: str) -> Optional[Any]:
        """Get the discord.py Client for a given account ID."""
        inst = self._accounts.get(account_id)
        return inst.client if inst and inst.ready else None

    def get_user_info(self, account_id: str) -> Dict[str, Any]:
        """Get the logged-in user info for an account."""
        inst = self._accounts.get(account_id)
        return inst.user_info if inst else {}

    @property
    def ready_clients(self) -> Dict[str, Any]:
        """Return {account_id: client} for all ready selfbots."""
        return {
            aid: inst.client
            for aid, inst in self._accounts.items()
            if inst.ready and inst.client
        }

    @property
    def all_accounts(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": inst.account_id,
                "name": inst.account_name,
                "ready": inst.ready,
                "guilds": len(inst.guilds),
                "error": inst.last_error if not inst.ready else "",
            }
            for inst in self._accounts.values()
        ]

    # ── Profile editing ──────────────────────────────────────────────

    async def edit_profile(
        self,
        account_id: str,
        *,
        username: Optional[str] = None,
        avatar_bytes: Optional[bytes] = None,
        bio: Optional[str] = None,
    ) -> bool:
        """
        Edit the selfbot's own profile: username (nickname on current guild), avatar, bio.
        Returns True on success.
        """
        inst = self._accounts.get(account_id)
        if not inst or not inst.ready or not inst.client:
            _log.warning(f"[{account_id}] not ready for profile edit")
            return False

        try:
            # Rate-limit check
            now = time.time()
            if now - inst.request_window_start > 60:
                inst.request_count = 0
                inst.request_window_start = now
            if inst.request_count >= self.MAX_REQUESTS_PER_MINUTE:
                wait = 60 - (now - inst.request_window_start)
                _log.warning(f"[{inst.account_name}] rate limit cooldown ({wait:.0f}s)")
                await asyncio.sleep(max(1, wait))
                inst.request_count = 0
                inst.request_window_start = time.time()
            inst.request_count += 1

            if username is not None:
                await inst.client.user.edit(username=username)

            if avatar_bytes is not None:
                await inst.client.user.edit(avatar=avatar_bytes)

            if bio is not None:
                await inst.client.user.edit(bio=bio)

            _log.info(f"[{inst.account_name}] profile updated: username={username}, avatar={'yes' if avatar_bytes else 'no'}")
            return True

        except Exception as e:
            inst.last_error = str(e)
            _log.error(f"[{inst.account_name}] profile edit failed: {e}")
            return False

    async def set_guild_nickname(
        self, account_id: str, guild_id: int, nickname: str
    ) -> bool:
        """Set the selfbot's server-specific nickname in a guild."""
        inst = self._accounts.get(account_id)
        if not inst or not inst.ready or not inst.client:
            return False

        try:
            guild = inst.client.get_guild(guild_id)
            if not guild:
                _log.warning(f"[{inst.account_name}] guild {guild_id} not found")
                return False
            member = guild.me
            if not member:
                return False
            await member.edit(nick=nickname)
            _log.info(f"[{inst.account_name}] guild nickname set to '{nickname}' in {guild.name}")
            return True
        except Exception as e:
            inst.last_error = str(e)
            _log.error(f"[{inst.account_name}] guild nickname edit failed: {e}")
            return False

    async def send_message(
        self,
        account_id: str,
        channel_id: int,
        content: str,
        *,
        embed: Optional[Any] = None,
        files: Optional[List[str]] = None,
        reference: Optional[Any] = None,
    ) -> Optional[str]:
        """Send a message as this selfbot. Returns the new message ID or None."""
        inst = self._accounts.get(account_id)
        if not inst or not inst.ready or not inst.client:
            return None

        try:
            now = time.time()
            if now - inst.request_window_start > 60:
                inst.request_count = 0
                inst.request_window_start = now
            inst.request_count += 1

            channel = inst.client.get_channel(channel_id)
            if not channel:
                channel = await inst.client.fetch_channel(channel_id)
            if not channel:
                _log.warning(f"[{inst.account_name}] channel {channel_id} not found")
                return None

            discord_files = []
            if files:
                for fp in files:
                    discord_files.append(await discord.File(fp).to_dict())

            msg = await channel.send(
                content=content,
                embed=embed,
                files=discord_files if discord_files else None,
                reference=reference,
            )
            _log.debug(f"[{inst.account_name}] message sent → channel {channel_id}")
            return str(msg.id)
        except Exception as e:
            inst.last_error = str(e)
            _log.error(f"[{inst.account_name}] send message failed: {e}")
            return None

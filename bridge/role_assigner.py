"""
Role assigner  ─  assigns Discord server roles to selfbot accounts.

Logic:
  - Each TG group maps to a set of Discord roles (via config).
  - When a selfbot impersonates a TG user from group X,
    it gets the role(s) associated with group X.
  - Roles are assigned via discord.py-self's guild member role management.

Supports:
  - Per-group role mapping
  - Default role for all bridge accounts
  - Remove stale roles on re-assign
"""

from typing import Any, Dict, List, Set

from loguru import logger as _log


class RoleAssigner:
    """Manages Discord role assignment for selfbot accounts in target guilds."""

    def __init__(
        self,
        mapper: Any,     # IdentityMapper
        ds_pool: Any,    # DiscordSelfbotPool
        role_cfg: dict,
    ) -> None:
        self.mapper = mapper
        self.ds_pool = ds_pool
        self.role_cfg = role_cfg

        # role_cfg structure:
        # {
        #   "enabled": true,
        #   "guild_id": 123456...,          # target guild
        #   "default_role": "Bridge Member", # role name or ID all selfbots get
        #   "group_roles": {                # TG group_id → Discord role name/ID
        #     "-100123456": "VIP",
        #     "-100789012": "Moderator"
        #   }
        # }
        self.guild_id = role_cfg.get("guild_id")
        self.default_role = role_cfg.get("default_role")
        self.group_roles: Dict[str, str] = {}
        for k, v in role_cfg.get("group_roles", {}).items():
            self.group_roles[str(k)] = str(v)

    async def assign_all(self) -> Dict[str, List[str]]:
        """Assign roles to all mapped selfbot accounts. Returns {ds_id: [role_names]}."""
        if not self.guild_id:
            _log.warning("No guild_id configured for role assignment")
            return {}

        results: Dict[str, List[str]] = {}

        for tg_id, mapping in self.mapper.tg_to_ds.items():
            ds_id = mapping["ds_account_id"]
            roles = await self.assign_roles(ds_id, tg_id)
            results[ds_id] = roles

        assigned = sum(1 for roles in results.values() if roles)
        _log.info(f"Roles assigned: {assigned}/{len(results)} accounts")
        return results

    async def assign_roles(self, ds_account_id: str, tg_user_id: int) -> List[str]:
        """Assign roles to a single selfbot account based on its mapped TG user."""
        client = self.ds_pool.get_client(ds_account_id)
        if not client:
            return []

        try:
            guild_id_int = int(self.guild_id)
            guild = client.get_guild(guild_id_int)
            if not guild:
                _log.warning(f"Guild {self.guild_id} not found for account {ds_account_id}")
                return []

            member = guild.me
            if not member:
                _log.warning(f"Selfbot {ds_account_id} is not a member of guild {self.guild_id}")
                return []

            # Determine which roles to assign
            target_role_names: Set[str] = set()

            # Default role for all bridge accounts
            if self.default_role:
                target_role_names.add(self.default_role)

            # Group-based role
            mapping = self.mapper.tg_to_ds.get(tg_user_id, {})
            group_id = mapping.get("group_id", 0)
            group_role = self.group_roles.get(str(group_id))
            if group_role:
                target_role_names.add(group_role)

            # Resolve role objects
            role_map = self._build_role_map(guild)

            # Collect current roles (excluding @everyone)
            current_role_ids: Set[int] = set()
            for role in member.roles:
                if role.name != "@everyone":
                    current_role_ids.add(role.id)

            # Calculate desired role IDs
            desired_role_ids: Set[int] = set()
            assigned_names: List[str] = []
            for role_name in target_role_names:
                role_id = role_map.get(role_name) or role_map.get(role_name.lower())
                if role_id:
                    desired_role_ids.add(role_id)
                    assigned_names.append(role_name)
                else:
                    _log.warning(f"Role '{role_name}' not found in guild {guild.name}")

            # Add roles (discord.py-self API)
            to_add = desired_role_ids - current_role_ids
            for rid in to_add:
                role = guild.get_role(rid)
                if role:
                    await member.add_roles(role)
                    _log.info(f"[{ds_account_id}] role added: {role.name}")

            # Remove stale roles (keep default + group roles, remove others bridge-assigned)
            bridge_role_ids = self._get_all_bridge_role_ids(role_map)
            to_remove = (current_role_ids & bridge_role_ids) - desired_role_ids
            for rid in to_remove:
                role = guild.get_role(rid)
                if role:
                    await member.remove_roles(role)
                    _log.info(f"[{ds_account_id}] stale role removed: {role.name}")

            return assigned_names

        except Exception as e:
            _log.error(f"Role assignment failed for {ds_account_id}: {e}")
            return []

    def _build_role_map(self, guild: Any) -> Dict[str, int]:
        """Build {role_name_lower: role_id} for the guild."""
        mapping: Dict[str, int] = {}
        for role in guild.roles:
            mapping[role.name.lower()] = role.id
            mapping[role.name] = role.id  # also exact
        return mapping

    def _get_all_bridge_role_ids(self, role_map: Dict[str, int]) -> Set[int]:
        """Get all role IDs that the bridge manages."""
        ids: Set[int] = set()
        if self.default_role:
            rid = role_map.get(self.default_role) or role_map.get(self.default_role.lower())
            if rid:
                ids.add(rid)
        for role_name in self.group_roles.values():
            rid = role_map.get(role_name) or role_map.get(role_name.lower())
            if rid:
                ids.add(rid)
        return ids

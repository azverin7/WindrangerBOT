import asyncio
import datetime
import logging
import secrets
from typing import Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from pymongo import UpdateOne

from core.config import DEVELOPER_ID
from utils.embeds import WindrangerEmbed
from utils.matchmaking import balance_teams_by_mmr
from utils.checks import is_privileged

logger = logging.getLogger('windranger.lobby')

def is_dummy_player(uid: str | int) -> bool:
    return str(uid).startswith("1000000000000000")

async def get_locales(bot, guild_id: Optional[int], user_id: int) -> Tuple[Optional[str], Optional[str]]:
    user_loc = await bot.db.get_user_locale(user_id)
    guild_loc = None
    if guild_id:
        config = await bot.db.get_guild_config(guild_id)
        guild_loc = config.get("locale")
    return user_loc, guild_loc

async def resolve_locale(bot, interaction: discord.Interaction) -> discord.Locale:
    u_loc, g_loc = await get_locales(bot, interaction.guild_id, interaction.user.id)
    res_str = (
        u_loc or 
        g_loc or 
        (interaction.locale.value if interaction.locale else None) or 
        (interaction.guild_locale.value if interaction.guild_locale else None)
    )
    try:
        return discord.Locale(res_str) if res_str else bot.i18n.default_locale
    except ValueError:
        return bot.i18n.default_locale

async def _t(bot, interaction: discord.Interaction, key: str, **kwargs) -> str:
    u_loc, g_loc = await get_locales(bot, interaction.guild_id, interaction.user.id)
    return bot.i18n.get_context_string(interaction, "lobby", key, db_user_locale=u_loc, db_guild_locale=g_loc, **kwargs)

class AdminLobbyView(discord.ui.View):
    def __init__(self, bot, lobby: dict, message: discord.Message, emojis: dict, locale: discord.Locale):
        super().__init__(timeout=None)
        self.bot = bot
        self.lobby = lobby
        self.lobby_id = lobby["_id"]
        self.message = message
        self.emojis = emojis
        self.locale = locale

        btn_cancel = discord.ui.Button(
            label=self.bot.i18n.get_string(self.locale, "lobby", "btn_cancel"), 
            style=discord.ButtonStyle.danger, 
            custom_id="admin_cancel"
        )
        btn_cancel.callback = self.btn_cancel
        self.add_item(btn_cancel)

        if not lobby.get("shuffled"):
            btn_start = discord.ui.Button(
                label=self.bot.i18n.get_string(self.locale, "lobby", "btn_start"), 
                style=discord.ButtonStyle.primary, 
                custom_id="admin_start"
            )
            btn_start.callback = self.btn_start
            self.add_item(btn_start)
        else:
            btn_win_rad = discord.ui.Button(
                label=self.bot.i18n.get_string(self.locale, "lobby", "btn_win_radiant"), 
                style=discord.ButtonStyle.success, 
                custom_id="admin_win_radiant"
            )
            btn_win_rad.callback = self.btn_win_radiant
            self.add_item(btn_win_rad)

            btn_win_dir = discord.ui.Button(
                label=self.bot.i18n.get_string(self.locale, "lobby", "btn_win_dire"), 
                style=discord.ButtonStyle.success, 
                custom_id="admin_win_dire"
            )
            btn_win_dir.callback = self.btn_win_dire
            self.add_item(btn_win_dir)

    async def btn_start(self, interaction: discord.Interaction):
        await interaction.response.defer()
        db = self.bot.db.active_lobbies
        lobby = await db.find_one({"_id": self.lobby_id})

        if lobby.get("shuffled"):
            return await interaction.followup.send(await _t(self.bot, interaction, "already_started"), ephemeral=True)

        slots = lobby["slots"]
        if not all(len(slots[p]) == 2 for p in ("pos1", "pos2", "pos3", "pos4", "pos5")):
            return await interaction.followup.send(await _t(self.bot, interaction, "slots_not_full"), ephemeral=True)

        all_uids = lobby.get("all_players", [])
        if not all_uids:
            all_uids = [uid for players in slots.values() for uid in players]

        users_cursor = self.bot.db.users.find({"_id": {"$in": all_uids}, "guild_id": str(interaction.guild.id)})
        
        user_mmrs = {uid: 1000 for uid in all_uids}
        async for udoc in users_cursor:
            user_mmrs[udoc["_id"]] = udoc.get("mmr", 1000)

        radiant, dire = balance_teams_by_mmr(slots, user_mmrs)
        password = str(secrets.randbelow(9000) + 1000)
        
        guild = interaction.guild
        category = self.message.channel.category
        short_id = self.lobby_id.split('_')[1] if '_' in self.lobby_id else self.lobby_id
        host = guild.get_member(int(lobby["host_id"]))

        radiant_vc = None
        dire_vc = None

        try:
            radiant_name = self.bot.i18n.get_string(self.locale, "lobby", "vc_radiant", short_id=short_id)
            dire_name = self.bot.i18n.get_string(self.locale, "lobby", "vc_dire", short_id=short_id)
            radiant_vc = await guild.create_voice_channel(name=radiant_name, category=category)
            dire_vc = await guild.create_voice_channel(name=dire_name, category=category)
        except discord.Forbidden:
            return await interaction.followup.send(await _t(self.bot, interaction, "no_vc_perms"), ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"Failed to create VCs for lobby {self.lobby_id}: {e}")
            if radiant_vc: await radiant_vc.delete()
            if dire_vc: await dire_vc.delete()
            return await interaction.followup.send(await _t(self.bot, interaction, "vc_api_error"), ephemeral=True)

        lobby.update({
            "shuffled": True,
            "radiant": radiant,
            "dire": dire,
            "password": password,
            "radiant_vc": radiant_vc.id,
            "dire_vc": dire_vc.id
        })

        await db.update_one({"_id": self.lobby_id}, {"$set": lobby})

        move_tasks = []
        for team, vc in [(radiant, radiant_vc), (dire, dire_vc)]:
            team_name = "radiant" if vc == radiant_vc else "dire"
            for uid in team.values():
                if is_dummy_player(uid):
                    continue
                    
                m = guild.get_member(int(uid))
                if not m:
                    continue
                    
                if m.voice:
                    move_tasks.append(m.move_to(vc))
                
                user_loc_str = await self.bot.db.get_user_locale(uid)
                u_loc = discord.Locale(user_loc_str) if user_loc_str else self.locale
                
                embed_dm = WindrangerEmbed.dm_info(self.bot.i18n, u_loc, self.lobby_id, password, team_name, host, guild, radiant, dire, self.emojis)
                try:
                    await m.send(embed=embed_dm)
                except discord.Forbidden:
                    logger.info(f"Could not send DM to {m.display_name} (DMs disabled).")

        if move_tasks:
            await asyncio.gather(*move_tasks, return_exceptions=True)

        embed = WindrangerEmbed.post_shuffle(self.bot.i18n, self.locale, self.lobby_id, host, guild, radiant, dire, self.emojis)
        main_view = LobbyView(self.bot, self.lobby_id, self.emojis, self.locale)
        for child in main_view.children:
            child.disabled = True
            
        try:
            await self.message.pin()
            async for history_msg in self.message.channel.history(limit=5):
                if history_msg.type == discord.MessageType.pins_add and history_msg.author == self.bot.user:
                    await history_msg.delete()
        except discord.HTTPException:
            pass
            
        await asyncio.gather(
            self.message.edit(embed=embed, view=main_view),
            interaction.edit_original_response(view=self)
        )
        
        for child in self.children:
            child.disabled = True
            
        await interaction.followup.send(await _t(self.bot, interaction, "match_started"), ephemeral=True)

    async def btn_cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        db = self.bot.db
        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        
        if lobby:
            guild = self.message.guild
            config = await db.get_guild_config(guild.id)
            waiting_room_id = config.get("waiting_room_id")
            waiting_room = guild.get_channel(int(waiting_room_id)) if waiting_room_id else None

            move_tasks = []
            delete_tasks = []
            
            for vc_key in ("radiant_vc", "dire_vc"):
                if vc_id := lobby.get(vc_key):
                    if vc := guild.get_channel(vc_id):
                        if waiting_room:
                            move_tasks.extend([member.move_to(waiting_room) for member in vc.members])
                        delete_tasks.append(vc.delete())

            if move_tasks:
                await asyncio.gather(*move_tasks, return_exceptions=True)
            if delete_tasks:
                await asyncio.gather(*delete_tasks, return_exceptions=True)

        await db.active_lobbies.delete_one({"_id": self.lobby_id})
        
        try: 
            if self.message.pinned:
                await self.message.unpin()
            await self.message.delete()
        except discord.NotFound: 
            pass
            
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(await _t(self.bot, interaction, "lobby_cancelled"), ephemeral=True)

    async def btn_win_radiant(self, interaction: discord.Interaction):
        await self.finish_match(interaction, "radiant")

    async def btn_win_dire(self, interaction: discord.Interaction):
        await self.finish_match(interaction, "dire")

    async def finish_match(self, interaction: discord.Interaction, winner: str):
        await interaction.response.defer()
        db = self.bot.db
        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        
        if not lobby:
            return await interaction.followup.send(await _t(self.bot, interaction, "lobby_not_found"), ephemeral=True)
            
        guild = self.message.guild
        radiant = lobby["radiant"]
        dire = lobby["dire"]
        
        config = await db.get_guild_config(guild.id)
        current_season = config.get("current_season", 1)
        
        all_players_data = []
        for is_radiant_win, team in [(winner == "radiant", radiant), (winner == "dire", dire)]:
            for pos, uid in team.items():
                if uid and not is_dummy_player(uid):
                    all_players_data.append({"uid": uid, "pos": pos, "is_winner": is_radiant_win})

        uids_to_fetch = [p["uid"] for p in all_players_data]
        users_cursor = db.users.find({"_id": {"$in": uids_to_fetch}, "guild_id": str(guild.id)})
        existing_users = {doc["_id"]: doc async for doc in users_cursor}

        bulk_ops = []
        for p_data in all_players_data:
            uid = p_data["uid"]
            pos = p_data["pos"]
            is_winner = p_data["is_winner"]
            
            user = existing_users.get(uid, {})
            
            mmr_change = 25 if is_winner else -25
            current_mmr = user.get("mmr", 1000)
            new_mmr = current_mmr + mmr_change
            
            win_inc = 1 if is_winner else 0
            loss_inc = 0 if is_winner else 1
            
            current_streak = user.get("streak", 0)
            if is_winner:
                new_streak = current_streak + 1 if current_streak >= 0 else 1
            else:
                new_streak = current_streak - 1 if current_streak <= 0 else -1
                
            update_data = {
                "$inc": {
                    "matches": 1, 
                    "wins": win_inc, 
                    "losses": loss_inc,
                    f"roles.{pos}.matches": 1,
                    f"roles.{pos}.wins": win_inc
                },
                "$set": {
                    "mmr": new_mmr,
                    "streak": new_streak,
                    "guild_id": str(guild.id),
                    "season": current_season
                },
                "$setOnInsert": {
                    "offenses": 0
                }
            }
            bulk_ops.append(UpdateOne({"_id": uid, "guild_id": str(guild.id)}, update_data, upsert=True))

        if bulk_ops:
            await db.users.bulk_write(bulk_ops)

        history_doc = {
            "lobby_id": self.lobby_id,
            "guild_id": str(guild.id),
            "season": current_season,
            "host_id": lobby["host_id"],
            "radiant": radiant,
            "dire": dire,
            "winner": winner,
            "timestamp": discord.utils.utcnow()
        }
        await db.match_history.insert_one(history_doc)
        
        waiting_room_id = config.get("waiting_room_id")
        waiting_room = guild.get_channel(int(waiting_room_id)) if waiting_room_id else None

        move_tasks = []
        delete_tasks = []
        
        for vc_key in ("radiant_vc", "dire_vc"):
            if vc_id := lobby.get(vc_key):
                if vc := guild.get_channel(vc_id):
                    if waiting_room:
                        move_tasks.extend([mem.move_to(waiting_room) for mem in vc.members])
                    delete_tasks.append(vc.delete())

        if move_tasks:
            await asyncio.gather(*move_tasks, return_exceptions=True)
        if delete_tasks:
            await asyncio.gather(*delete_tasks, return_exceptions=True)
                
        await db.active_lobbies.delete_one({"_id": self.lobby_id})
        host = guild.get_member(int(lobby["host_id"]))
        
        embed = WindrangerEmbed.match_result(self.bot.i18n, self.locale, self.lobby_id, host, guild, radiant, dire, winner, self.emojis)
        history_channel_id = config.get("history_channel_id")
        history_channel = guild.get_channel(int(history_channel_id)) if history_channel_id else None

        if history_channel:
            await history_channel.send(embed=embed)
            try: 
                if self.message.pinned:
                    await self.message.unpin()
                await self.message.delete()
            except discord.HTTPException: 
                pass
        else:
            try:
                if self.message.pinned:
                    await self.message.unpin()
                await self.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
            
        if stats_cog := self.bot.get_cog("StatsCog"):
            await stats_cog.update_leaderboard(guild)
        
        for child in self.children:
            child.disabled = True
            
        winner_localized = self.bot.i18n.get_string(self.locale, "lobby", winner)
        await asyncio.gather(
            interaction.edit_original_response(view=self),
            interaction.followup.send(await _t(self.bot, interaction, "match_finished", winner=winner_localized), ephemeral=True)
        )

class LobbyView(discord.ui.View):
    def __init__(self, bot, lobby_id: str, emojis: dict, locale: discord.Locale):
        super().__init__(timeout=None)
        self.bot = bot
        self.lobby_id = lobby_id
        self.emojis = emojis
        self.locale = locale

        positions = ["pos1", "pos2", "pos3", "pos4", "pos5"]
        for pos in positions:
            btn = discord.ui.Button(
                label=self.bot.i18n.get_string(self.locale, "lobby", pos), 
                style=discord.ButtonStyle.secondary, 
                custom_id=pos, 
                row=0
            )
            btn.callback = self.make_join_callback(pos)
            self.add_item(btn)

        btn_leave = discord.ui.Button(
            label=self.bot.i18n.get_string(self.locale, "lobby", "btn_leave"), 
            style=discord.ButtonStyle.red, 
            custom_id="btn_leave", 
            row=1
        )
        btn_leave.callback = self.handle_leave
        self.add_item(btn_leave)

    def make_join_callback(self, pos: str):
        async def callback(interaction: discord.Interaction):
            await self.handle_join(interaction, pos)
        return callback

    async def handle_join(self, interaction: discord.Interaction, pos: str):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        db = self.bot.db
        guild_id = str(interaction.guild.id)
        
        config = await db.get_guild_config(guild_id)
        if waiting_room_id := config.get("waiting_room_id"):
            waiting_vc = interaction.guild.get_channel(int(waiting_room_id))
            if waiting_vc:
                member = interaction.guild.get_member(interaction.user.id)
                if not member or not member.voice or member.voice.channel.id != int(waiting_room_id):
                    msg = await _t(self.bot, interaction, "join_vc_first", vc_mention=waiting_vc.mention)
                    return await interaction.followup.send(msg, ephemeral=True)

        user_data = await db.users.find_one({"_id": user_id, "guild_id": guild_id})
        if user_data and (ban_expires := user_data.get("ban_expires")):
            if ban_expires.replace(tzinfo=datetime.timezone.utc) > discord.utils.utcnow():
                expire_time = discord.utils.format_dt(ban_expires.replace(tzinfo=datetime.timezone.utc), "F")
                msg = await _t(self.bot, interaction, "banned", expire_time=expire_time)
                return await interaction.followup.send(msg, ephemeral=True)
        
        existing_lobby = await db.active_lobbies.find_one({
            "guild_id": guild_id,
            "_id": {"$ne": self.lobby_id},
            "all_players": user_id
        })

        if existing_lobby:
            short_id = existing_lobby["_id"].split('_')[1] if "_" in existing_lobby["_id"] else existing_lobby["_id"]
            msg = await _t(self.bot, interaction, "already_in_lobby", short_id=short_id)
            return await interaction.followup.send(msg, ephemeral=True)

        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        if not lobby or lobby.get("shuffled"):
            return await interaction.followup.send(await _t(self.bot, interaction, "lobby_closed"), ephemeral=True)

        slots = lobby["slots"]
        all_players = lobby.get("all_players", [])

        for p, players in slots.items():
            if user_id in players:
                if p == pos:
                    return
                players.remove(user_id)

        if len(slots[pos]) >= 2:
            return await interaction.followup.send(await _t(self.bot, interaction, "pos_taken"), ephemeral=True)

        slots[pos].append(user_id)
        if user_id not in all_players:
            all_players.append(user_id)
            
        is_full = all(len(slots[p]) == 2 for p in ["pos1", "pos2", "pos3", "pos4", "pos5"])
        
        host = interaction.guild.get_member(int(lobby["host_id"]))
        locale = await resolve_locale(self.bot, interaction)
        embed = WindrangerEmbed.pre_shuffle(self.bot.i18n, locale, self.lobby_id, host, interaction.guild, slots, self.emojis)

        await db.active_lobbies.update_one(
            {"_id": self.lobby_id}, 
            {"$set": {"slots": slots, "all_players": all_players}}
        )
        await interaction.message.edit(embed=embed, view=self)
        
        if is_full:
            msg = await _t(self.bot, interaction, "lobby_full", host_id=lobby['host_id'])
            await interaction.channel.send(msg)

    async def handle_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.active_lobbies
        lobby = await db.find_one({"_id": self.lobby_id})

        if not lobby or lobby.get("shuffled"):
            return await interaction.followup.send(await _t(self.bot, interaction, "cannot_leave_started"), ephemeral=True)

        user_id = str(interaction.user.id)
        found = False
        slots = lobby["slots"]
        all_players = lobby.get("all_players", [])

        for players in slots.values():
            if user_id in players:
                players.remove(user_id)
                found = True
                break

        if not found:
            return

        if user_id in all_players:
            all_players.remove(user_id)

        await db.update_one(
            {"_id": self.lobby_id}, 
            {"$set": {"slots": slots, "all_players": all_players}}
        )
        
        host = interaction.guild.get_member(int(lobby["host_id"]))
        locale = await resolve_locale(self.bot, interaction)
        embed = WindrangerEmbed.pre_shuffle(self.bot.i18n, locale, self.lobby_id, host, interaction.guild, slots, self.emojis)
        
        await interaction.message.edit(embed=embed, view=self)

class LobbyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_emojis = ['pos1', 'pos2', 'pos3', 'pos4', 'pos5', 'radi', 'dire', 'dota']
        
        self.ctx_menu = app_commands.ContextMenu(
            name="Manage Lobby",
            callback=self.manage_lobby_ctx,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_load(self):
        try:
            cursor = self.bot.db.active_lobbies.find({
                "shuffled": False, 
                "message_id": {"$ne": None}
            })
            
            async for lobby in cursor:
                guild = self.bot.get_guild(int(lobby["guild_id"]))
                if guild:
                    emojis = await self._update_guild_emojis(guild)
                    config = await self.bot.db.get_guild_config(guild.id)
                    guild_loc = config.get("locale")
                    
                    try:
                        locale = discord.Locale(guild_loc) if guild_loc else self.bot.i18n.default_locale
                    except ValueError:
                        locale = self.bot.i18n.default_locale

                    self.bot.add_view(
                        LobbyView(self.bot, lobby["_id"], emojis, locale),
                        message_id=int(lobby["message_id"])
                    )
            logger.info("Persistent views restored successfully.")
        except Exception as e:
            logger.error(f"Failed to restore persistent views: {e}", exc_info=True)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def _update_guild_emojis(self, guild: discord.Guild) -> dict:
        found_emojis = {}
        for emoji in guild.emojis:
            if emoji.name in self.target_emojis:
                found_emojis[emoji.name] = str(emoji) 
        if found_emojis:
            await self.bot.db.settings.update_one(
                {"_id": str(guild.id)}, {"$set": {"emojis": found_emojis}}, upsert=True
            )
            self.bot.db.clear_guild_cache(guild.id)
        return found_emojis

    async def check_host_perms(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if user.id == int(DEVELOPER_ID):
            return True
        if isinstance(user, discord.Member) and user.guild_permissions.administrator:
            return True
        if interaction.guild and user.id == interaction.guild.owner_id:
            return True
            
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        if config:
            gh_role_id = config.get("grand_host_role_id")
            if gh_role_id and (gh_role := interaction.guild.get_role(int(gh_role_id))) and gh_role in user.roles:
                return True
                
            h_role_id = config.get("host_role_id")
            if h_role_id and (h_role := interaction.guild.get_role(int(h_role_id))) and h_role in user.roles:
                return True
        return False

    async def manage_lobby_ctx(self, interaction: discord.Interaction, message: discord.Message):
        lobby = await self.bot.db.active_lobbies.find_one({"message_id": str(message.id)})
        
        if not lobby:
            return await interaction.response.send_message(await _t(self.bot, interaction, "not_active_lobby"), ephemeral=True)
            
        is_host = await self.check_host_perms(interaction)
        if lobby.get("host_id") != str(interaction.user.id) and not is_host:
            return await interaction.response.send_message(await _t(self.bot, interaction, "no_perms_manage"), ephemeral=True)
            
        emojis = await self._update_guild_emojis(interaction.guild)
        locale = await resolve_locale(self.bot, interaction)
        view = AdminLobbyView(self.bot, lobby, message, emojis, locale)
        
        msg = await _t(self.bot, interaction, "manage_panel", lobby_id=lobby['_id'])
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @app_commands.command(name="lobby", description="Create a new 5v5 lobby")
    @is_privileged()
    async def create_lobby(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        config = await self.bot.db.get_guild_config(guild.id)
        
        reg_channel_id = config.get("reg_channel_id")
        if not reg_channel_id:
            return await interaction.followup.send(await _t(self.bot, interaction, "no_infra"), ephemeral=True)

        reg_channel = guild.get_channel(int(reg_channel_id))
        if not reg_channel:
            try:
                reg_channel = await guild.fetch_channel(int(reg_channel_id))
            except discord.NotFound:
                pass
                
        if not reg_channel:
            return await interaction.followup.send(await _t(self.bot, interaction, "reg_channel_not_found"), ephemeral=True)

        emojis = await self._update_guild_emojis(guild)
        lobby_seq = await self.bot.db.get_next_lobby_id(guild.id)
        lobby_id = f"lobby_{lobby_seq}"

        lobby_data = {
            "_id": lobby_id,
            "guild_id": str(guild.id),
            "host_id": str(interaction.user.id), 
            "message_id": None,                  
            "shuffled": False,
            "all_players": [],
            "slots": {"pos1": [], "pos2": [], "pos3": [], "pos4": [], "pos5": []},
            "radiant": {},
            "dire": {}
        }
        await self.bot.db.active_lobbies.insert_one(lobby_data)
        
        locale = await resolve_locale(self.bot, interaction)
        view = LobbyView(self.bot, lobby_id, emojis, locale)
        embed = WindrangerEmbed.pre_shuffle(self.bot.i18n, locale, lobby_id, interaction.user, guild, lobby_data["slots"], emojis)

        msg = await reg_channel.send(embed=embed, view=view)
        await self.bot.db.active_lobbies.update_one({"_id": lobby_id}, {"$set": {"message_id": str(msg.id)}})
        
        await interaction.followup.send(await _t(self.bot, interaction, "lobby_created", channel_id=reg_channel.id), ephemeral=True)

    @app_commands.command(name="fill", description="[ADMIN] Fill the last lobby with bots")
    @is_privileged()
    async def fill_lobby(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.active_lobbies
        
        lobby = await db.find_one({"guild_id": str(interaction.guild.id), "shuffled": False}, sort=[("_id", -1)])
        
        if not lobby:
            return await interaction.followup.send(await _t(self.bot, interaction, "no_open_lobbies"), ephemeral=True)

        dummy_ids = [str(100000000000000000 + i) for i in range(10)]
        slots = lobby["slots"]
        all_players = lobby.get("all_players", [])
        
        idx = 0
        for pos in ["pos1", "pos2", "pos3", "pos4", "pos5"]:
            while len(slots[pos]) < 2:
                dummy_id = dummy_ids[idx]
                slots[pos].append(dummy_id)
                all_players.append(dummy_id)
                idx += 1

        await db.update_one(
            {"_id": lobby["_id"]}, 
            {"$set": {"slots": slots, "all_players": all_players}}
        )
        
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        reg_channel = interaction.guild.get_channel(int(config["reg_channel_id"]))
        if not reg_channel:
            try:
                reg_channel = await interaction.guild.fetch_channel(int(config["reg_channel_id"]))
            except discord.NotFound:
                pass
                
        try:
            msg = await reg_channel.fetch_message(int(lobby["message_id"]))
            host = interaction.guild.get_member(int(lobby["host_id"]))
            emojis = await self._update_guild_emojis(interaction.guild)
            locale = await resolve_locale(self.bot, interaction)
            embed = WindrangerEmbed.pre_shuffle(self.bot.i18n, locale, lobby["_id"], host, interaction.guild, slots, emojis)
            
            view = LobbyView(self.bot, lobby["_id"], emojis, locale)
            await msg.edit(embed=embed, view=view)
            
            await reg_channel.send(await _t(self.bot, interaction, "lobby_full", host_id=lobby['host_id']))
            await interaction.followup.send(await _t(self.bot, interaction, "lobby_filled"), ephemeral=True)
        except discord.NotFound:
            await db.delete_one({"_id": lobby["_id"]})
            await interaction.followup.send(await _t(self.bot, interaction, "ghost_lobby"), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(await _t(self.bot, interaction, "update_error", e=str(e)), ephemeral=True)

async def setup(bot):
    await bot.add_cog(LobbyCog(bot))
import asyncio
import datetime
import random
import logging
from typing import Union, Optional

import discord
from discord.ext import commands

from database.mongo import db
from utils.factory import UIHandler
from utils.checks import is_privileged

logger = logging.getLogger('windranger.lobby')

class LobbyView(discord.ui.View):
    def __init__(self, cog, l_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.l_id = l_id

    async def _handle_click(self, interaction: discord.Interaction, pos: str):
        if pos == "out":
            changed = await self.cog.perform_leave(interaction.user, self.l_id, interaction.guild_id)
            if changed: await self.cog.update_lobby_message(self.l_id, interaction.guild)
        else:
            res = await self.cog.perform_join(interaction.user, self.l_id, pos, interaction.guild_id)
            if res is True: await self.cog.update_lobby_message(self.l_id, interaction.guild)
            elif isinstance(res, str) and res != "IGNORE":
                return await interaction.response.send_message(res, ephemeral=True)
        
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(label="1", custom_id="btn_pos1", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await self._handle_click(i, "1")
    @discord.ui.button(label="2", custom_id="btn_pos2", style=discord.ButtonStyle.primary)
    async def b2(self, i, b): await self._handle_click(i, "2")
    @discord.ui.button(label="3", custom_id="btn_pos3", style=discord.ButtonStyle.primary)
    async def b3(self, i, b): await self._handle_click(i, "3")
    @discord.ui.button(label="4", custom_id="btn_pos4", style=discord.ButtonStyle.primary)
    async def b4(self, i, b): await self._handle_click(i, "4")
    @discord.ui.button(label="5", custom_id="btn_pos5", style=discord.ButtonStyle.primary)
    async def b5(self, i, b): await self._handle_click(i, "5")
    @discord.ui.button(emoji="❌", custom_id="btn_out", style=discord.ButtonStyle.danger)
    async def bout(self, i, b): await self._handle_click(i, "out")

class LobbyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_channel(self, ctx: commands.Context) -> bool:
        config = await db.get_guild_config(ctx.guild.id)
        return ctx.channel.id == config.get("reg_channel_id")

    async def _check_commands_enabled(self, guild_id: int) -> bool:
        config = await db.get_guild_config(guild_id)
        return config.get("view_mode", 1) in [1, 3, 5]

    async def update_lobby_message(self, l_id: int, guild: discord.Guild):
        lobby = await db.lobbies.find_one({"lobby_id": l_id, "active": False, "guild_id": guild.id})
        if not lobby: return
        
        config = await db.get_guild_config(guild.id)
        ch_id = lobby.get("channel_id") or config.get("reg_channel_id")
        channel = guild.get_channel(ch_id)
        if not channel: return

        v_mode = config.get("view_mode", 1)
        view = LobbyView(self, l_id) if v_mode in [2, 3] else None

        try:
            msg = await channel.fetch_message(lobby["status_msg_id"])
            await msg.edit(embed=UIHandler.create_lobby_embed(lobby, guild), view=view)
        except discord.NotFound: pass

    async def perform_join(self, user: Union[discord.Member, discord.User], l_id: int, role_key: str, guild_id: int) -> Union[bool, str]:
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user.id) if guild else None
        
        config = await db.get_guild_config(guild_id)
        vc_id = config.get("waiting_vc_id")
        if vc_id and member:
            waiting_vc = guild.get_channel(int(vc_id))
            if waiting_vc and (not getattr(member, 'voice', None) or getattr(member.voice, 'channel', None) != waiting_vc):
                return f"Сначала зайди в {waiting_vc.mention}!"

        player_data = await db.players.find_one({"user_id": user.id, "guild_id": guild_id})
        if player_data and player_data.get("bans", {}).get(str(guild_id), False):
            return "IGNORE"

        is_busy = await db.lobbies.find_one({"all_players": user.id, "active": False, "guild_id": guild_id})
        if is_busy and is_busy["lobby_id"] != l_id:
            return f"Ты уже в лобби #{is_busy['lobby_id']}."

        pull_roles = {f"roles.{i}": user.id for i in range(1, 6) if str(i) != role_key}
        
        res = await db.lobbies.update_one(
            {
                "lobby_id": l_id, 
                "active": False, 
                "guild_id": guild_id, 
                f"roles.{role_key}.1": {"$exists": False} 
            },
            {
                "$pull": pull_roles,
                "$addToSet": {
                    f"roles.{role_key}": user.id, 
                    "all_players": user.id
                }
            }
        )
        
        return True if res.modified_count > 0 else "IGNORE"

    async def perform_leave(self, user: Union[discord.Member, discord.User], l_id: int, guild_id: int) -> bool:
        res = await db.lobbies.update_one(
            {"lobby_id": l_id, "active": False, "guild_id": guild_id},
            {"$pull": {"roles.1": user.id, "roles.2": user.id, "roles.3": user.id, "roles.4": user.id, "roles.5": user.id, "all_players": user.id}}
        )
        return res.modified_count > 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        
        config = await db.get_guild_config(message.guild.id)
        if message.channel.id != config.get("reg_channel_id"): return

        if message.author.guild_permissions.administrator: return
        if "host_role_id" in config:
            host_role = message.guild.get_role(config["host_role_id"])
            if host_role and host_role in message.author.roles: return

        allowed_cmds = ("!out", "!leave", "!start", "!s", "!1", "!2", "!3", "!4", "!5")
        if not message.content.lower().startswith(allowed_cmds):
            try: await message.delete()
            except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id: return
        
        lobby = await db.lobbies.find_one({"status_msg_id": payload.message_id, "active": False})
        if not lobby: return
        
        config = await db.get_guild_config(payload.guild_id)
        if config.get("view_mode", 1) not in [4, 5]: return 

        guild = self.bot.get_guild(payload.guild_id)
        if not guild: return
        
        member = guild.get_member(payload.user_id)
        if not member: return

        channel = guild.get_channel(payload.channel_id)
        role_key = None
        
        if payload.emoji.name in ["pos1", "1️⃣"]: role_key = "1"
        elif payload.emoji.name in ["pos2", "2️⃣"]: role_key = "2"
        elif payload.emoji.name in ["pos3", "3️⃣"]: role_key = "3"
        elif payload.emoji.name in ["pos4", "4️⃣"]: role_key = "4"
        elif payload.emoji.name in ["pos5", "5️⃣"]: role_key = "5"
        elif payload.emoji.name == "❌": role_key = "out"

        if role_key in ["1", "2", "3", "4", "5"]:
            res = await self.perform_join(member, lobby["lobby_id"], role_key, payload.guild_id)
            if res is True: await self.update_lobby_message(lobby["lobby_id"], guild)
            elif isinstance(res, str) and channel and res != "IGNORE":
                await channel.send(f"{member.mention}, {res}", delete_after=3)
        elif role_key == "out":
            changed = await self.perform_leave(member, lobby["lobby_id"], payload.guild_id)
            if changed: await self.update_lobby_message(lobby["lobby_id"], guild)

        try:
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction(payload.emoji, member)
        except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        lobby = await db.lobbies.find_one_and_delete({"status_msg_id": payload.message_id, "active": False})
        if lobby:
            for vc_id in lobby.get("voice_channels", []):
                vc = self.bot.get_channel(vc_id)
                if vc:
                    try: await vc.delete()
                    except discord.HTTPException: pass

    async def _text_join(self, ctx: commands.Context, pos: str, l_id: Optional[int] = None):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if not await self._check_commands_enabled(ctx.guild.id): return

        if l_id is None:
            lobby = await db.lobbies.find_one({"active": False, "guild_id": ctx.guild.id}, sort=[("lobby_id", -1)])
        else:
            lobby = await db.lobbies.find_one({"lobby_id": l_id, "active": False, "guild_id": ctx.guild.id})
            
        if not lobby: return await ctx.send("Открытое лобби не найдено.", delete_after=3)

        res = await self.perform_join(ctx.author, lobby["lobby_id"], pos, ctx.guild.id)
        if res is True: await self.update_lobby_message(lobby["lobby_id"], ctx.guild)
        elif isinstance(res, str) and res != "IGNORE": await ctx.send(f"{ctx.author.mention}, {res}", delete_after=3)

    @commands.command(name="1")
    async def pos1(self, ctx, l_id: Optional[int] = None): await self._text_join(ctx, "1", l_id)
    @commands.command(name="2")
    async def pos2(self, ctx, l_id: Optional[int] = None): await self._text_join(ctx, "2", l_id)
    @commands.command(name="3")
    async def pos3(self, ctx, l_id: Optional[int] = None): await self._text_join(ctx, "3", l_id)
    @commands.command(name="4")
    async def pos4(self, ctx, l_id: Optional[int] = None): await self._text_join(ctx, "4", l_id)
    @commands.command(name="5")
    async def pos5(self, ctx, l_id: Optional[int] = None): await self._text_join(ctx, "5", l_id)

    @commands.command(name="out", aliases=["leave"])
    async def leave_lobby_command(self, ctx: commands.Context, l_id: Optional[int] = None):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if not await self._check_commands_enabled(ctx.guild.id): return

        query = {"all_players": ctx.author.id, "active": False, "guild_id": ctx.guild.id}
        if l_id: query["lobby_id"] = l_id

        lobby = await db.lobbies.find_one(query)
        if not lobby: return await ctx.send(f"{ctx.author.mention}, ты не находишься в лобби.", delete_after=3)

        changed = await self.perform_leave(ctx.author, lobby["lobby_id"], ctx.guild.id)
        if changed: await self.update_lobby_message(lobby["lobby_id"], ctx.guild)

    @commands.command(name="create", aliases=["c"])
    @is_privileged()
    async def create_lobby(self, ctx: commands.Context):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        l_id = await db.get_next_lobby_id(ctx.guild.id)
        lobby_doc = {
            "lobby_id": l_id, 
            "guild_id": ctx.guild.id, 
            "channel_id": ctx.channel.id, 
            "host_id": ctx.author.id, 
            "active": False,
            "roles": {"1": [], "2": [], "3": [], "4": [], "5": []}, 
            "all_players": [], 
            "status_msg_id": None
        }

        config = await db.get_guild_config(ctx.guild.id)
        v_mode = config.get("view_mode", 1)
        
        view = LobbyView(self, l_id) if v_mode in [2, 3] else None
        msg = await ctx.send(embed=UIHandler.create_lobby_embed(lobby_doc, ctx.guild), view=view)
        
        lobby_doc["status_msg_id"] = msg.id
        await db.lobbies.insert_one(lobby_doc)

        if v_mode in [4, 5]:
            for pos_str in ["1", "2", "3", "4", "5"]:
                emoji = UIHandler.get_role_emoji(ctx.guild, pos_str)
                if emoji: await msg.add_reaction(emoji)
            await msg.add_reaction("❌")

    @commands.command(name="fill")
    @is_privileged()
    async def fill_lobby(self, ctx: commands.Context, l_id: Optional[int] = None):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if l_id is None:
            lobby = await db.lobbies.find_one({"active": False, "guild_id": ctx.guild.id}, sort=[("lobby_id", -1)])
        else:
            lobby = await db.lobbies.find_one({"lobby_id": l_id, "active": False, "guild_id": ctx.guild.id})

        if not lobby: return await ctx.send("Открытое лобби не найдено.", delete_after=3)

        fake_id = 1
        for pos_str in ["1", "2", "3", "4", "5"]:
            while len(lobby["roles"][pos_str]) < 2:
                while fake_id in lobby["all_players"]: fake_id += 1
                lobby["roles"][pos_str].append(fake_id)
                lobby["all_players"].append(fake_id)

        await db.lobbies.update_one(
            {"_id": lobby["_id"]},
            {"$set": {"roles": lobby["roles"], "all_players": lobby["all_players"]}}
        )
        await self.update_lobby_message(lobby["lobby_id"], ctx.guild)

    async def _distribute_players(self, guild, l_id, lobby_pass, started_time, radiant, dire, rad_vc, dire_vc, host_id):
        for team_dict, vc, team_name in [(radiant, rad_vc, "Radiant"), (dire, dire_vc, "Dire")]:
            for p_id in team_dict.values():
                member = guild.get_member(p_id)
                if member:
                    try:
                        await member.move_to(vc)
                    except discord.HTTPException:
                        pass
                    
                    try:
                        dm_embed = UIHandler.create_dm_embed(
                            l_id=l_id, pw=lobby_pass, side=team_name, guild=guild, 
                            radiant=radiant, dire=dire, host_id=host_id, started_at=started_time
                        )
                        await member.send(embed=dm_embed)
                    except discord.HTTPException:
                        pass
                    
                    await asyncio.sleep(0.3)

    @commands.command(name="start", aliases=["s"])
    async def start_match(self, ctx: commands.Context, l_id: Optional[int] = None):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if l_id is None:
            cursor = db.lobbies.find({"active": False, "guild_id": ctx.guild.id, "all_players": {"$size": 10}})
            filled_lobbies = await cursor.to_list(length=None)

            if not filled_lobbies: return await ctx.send("На данный момент нет заполненных лобби (10/10).", delete_after=5)
            elif len(filled_lobbies) > 1:
                available_ids = ", ".join([str(l["lobby_id"]) for l in filled_lobbies])
                return await ctx.send(f"Найдено несколько готовых лобби: **{available_ids}**. Укажите нужный ID: `!s <ID>`", delete_after=7)
            else:
                lobby = filled_lobbies[0]
                l_id = lobby["lobby_id"]
        else:
            lobby = await db.lobbies.find_one({"lobby_id": l_id, "active": False, "guild_id": ctx.guild.id})
            if not lobby: return await ctx.send(f"Открытое лобби #{l_id} не найдено.", delete_after=5)
            if len(lobby.get("all_players", [])) != 10: return await ctx.send(f"Лобби #{l_id} еще не заполнено.", delete_after=5)

        radiant, dire = UIHandler.balance_teams_random(lobby["roles"])
        started_time = discord.utils.utcnow()
        lobby_pass = str(random.randint(1000, 9999))

        cat_id = ctx.channel.category_id
        category = ctx.guild.get_channel(cat_id) if cat_id else None

        rad_vc, dire_vc = None, None
        try:
            rad_vc = await ctx.guild.create_voice_channel(f"Radiant #{l_id}", category=category)
            dire_vc = await ctx.guild.create_voice_channel(f"Dire #{l_id}", category=category)
        except discord.HTTPException as e:
            if rad_vc:
                try: await rad_vc.delete()
                except discord.HTTPException: pass
            if dire_vc:
                try: await dire_vc.delete()
                except discord.HTTPException: pass
            logger.error(f"Failed to create VCs for lobby {l_id}: {e}")
            return await ctx.send("Ошибка создания голосовых каналов. Проверьте права бота.", delete_after=5)

        await db.lobbies.update_one(
            {"_id": lobby["_id"]},
            {"$set": {
                "radiant": radiant,
                "dire": dire,
                "active": True,
                "started_at": started_time,
                "password": lobby_pass,
                "voice_channels": [rad_vc.id, dire_vc.id]
            }}
        )

        lobby.update({
            "radiant": radiant, 
            "dire": dire, 
            "active": True, 
            "started_at": started_time, 
            "password": lobby_pass, 
            "voice_channels": [rad_vc.id, dire_vc.id]
        })

        try:
            msg = await ctx.channel.fetch_message(lobby["status_msg_id"])
            await msg.edit(embed=UIHandler.create_lobby_embed(lobby, ctx.guild), view=None)
            await msg.clear_reactions()
            await msg.pin()
            async for history_msg in ctx.channel.history(limit=5):
                if history_msg.type == discord.MessageType.pins_add and history_msg.author == self.bot.user:
                    try: await history_msg.delete()
                    except discord.HTTPException: pass
        except discord.HTTPException as e: 
            logger.error(f"Failed updating lobby message: {e}")

        self.bot.loop.create_task(self._distribute_players(
            ctx.guild, l_id, lobby_pass, started_time, 
            radiant, dire, rad_vc, dire_vc, lobby["host_id"]
        ))
        
        await ctx.send(f"Матч #{l_id} запускается. Созданы каналы, рассылаю пароли...", delete_after=5)

    @commands.command(name="cancel")
    @is_privileged()
    async def cancel_lobby(self, ctx: commands.Context, l_id: int):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        lobby = await db.lobbies.find_one_and_delete({"lobby_id": l_id, "guild_id": ctx.guild.id})
        if not lobby: return await ctx.send(f"Лобби #{l_id} не найдено.", delete_after=5)

        config = await db.get_guild_config(ctx.guild.id)
        waiting_vc = ctx.guild.get_channel(config.get("waiting_vc_id"))

        for vc_id in lobby.get("voice_channels", []):
            vc = self.bot.get_channel(vc_id)
            if vc:
                if waiting_vc:
                    for m in vc.members:
                        try: await m.move_to(waiting_vc)
                        except discord.HTTPException: pass
                try: await vc.delete()
                except discord.HTTPException: pass

        try:
            msg = await ctx.channel.fetch_message(lobby["status_msg_id"])
            await msg.delete()
        except discord.HTTPException: pass
        
        await ctx.send(f"Лобби #{l_id} отменено.", delete_after=5)

    @commands.command(name="win", aliases=["end"])
    @is_privileged()
    async def match_win(self, ctx: commands.Context, l_id: int, winner: str):
        if not await self._check_channel(ctx): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        winner = winner.lower()
        if winner not in ["radiant", "dire"]: return await ctx.send("Укажите победителя: `radiant` или `dire`.", delete_after=5)

        lobby = await db.lobbies.find_one_and_delete({"lobby_id": l_id, "active": True, "guild_id": ctx.guild.id})
        if not lobby: return await ctx.send(f"Лобби #{l_id} не найдено.", delete_after=5)

        stats_cog = self.bot.get_cog("StatsCog")
        if stats_cog:
            for pos, p_id in lobby.get(winner, {}).items():
                if p_id > 1000: await db.process_match_result(p_id, True, pos, ctx.guild.id)
            loser = "dire" if winner == "radiant" else "radiant"
            for pos, p_id in lobby.get(loser, {}).items():
                if p_id > 1000: await db.process_match_result(p_id, False, pos, ctx.guild.id)
            await stats_cog.update_leaderboard(ctx.guild)

        match_id = await db.get_next_match_id(ctx.guild.id)
        config = await db.get_guild_config(ctx.guild.id)
        
        archive_doc = {
            "match_id": match_id, "guild_id": ctx.guild.id, "lobby_id": l_id,
            "season": config.get("current_season", 1), "host_id": lobby.get("host_id"),
            "radiant": lobby.get("radiant", {}), "dire": lobby.get("dire", {}),
            "winner": winner, "started_at": lobby.get("started_at"),
            "ended_at": discord.utils.utcnow()
        }
        await db.history.insert_one(archive_doc)

        history_cog = self.bot.get_cog("HistoryCog")
        hist_ch = ctx.guild.get_channel(config.get("history_channel_id"))
        if history_cog and hist_ch: await hist_ch.send(embed=history_cog._build_match_embed(archive_doc, ctx.guild))

        waiting_vc = ctx.guild.get_channel(config.get("waiting_vc_id"))
        for vc_id in lobby.get("voice_channels", []):
            vc = self.bot.get_channel(vc_id)
            if vc:
                if waiting_vc:
                    for m in vc.members:
                        try: await m.move_to(waiting_vc)
                        except discord.HTTPException: pass
                try: await vc.delete()
                except discord.HTTPException: pass

        try:
            msg = await ctx.channel.fetch_message(lobby["status_msg_id"])
            if msg.pinned: await msg.unpin()
            await msg.delete()
        except discord.HTTPException: pass

        await ctx.send(f"Матч #{l_id} завершен. Запись №{match_id} сохранена.", delete_after=5)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LobbyCog(bot))
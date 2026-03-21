import random
import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from pymongo import UpdateOne, ReturnDocument
from utils.embeds import WindrangerEmbed
from utils.matchmaking import balance_teams_by_mmr

class AdminLobbyView(discord.ui.View):
    def __init__(self, bot, lobby: dict, message: discord.Message, emojis: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.lobby = lobby
        self.lobby_id = lobby["_id"]
        self.message = message
        self.emojis = emojis

        btn_cancel = discord.ui.Button(label="Отменить лобби", style=discord.ButtonStyle.danger, custom_id="admin_cancel")
        btn_cancel.callback = self.btn_cancel
        self.add_item(btn_cancel)

        if not lobby.get("shuffled"):
            btn_start = discord.ui.Button(label="▶️ Запустить матч", style=discord.ButtonStyle.primary, custom_id="admin_start")
            btn_start.callback = self.btn_start
            self.add_item(btn_start)
        else:
            btn_win_rad = discord.ui.Button(label="🏆 Победитель: Свет", style=discord.ButtonStyle.success, custom_id="admin_win_radiant")
            btn_win_rad.callback = self.btn_win_radiant
            self.add_item(btn_win_rad)

            btn_win_dir = discord.ui.Button(label="🏆 Победитель: Тьма", style=discord.ButtonStyle.success, custom_id="admin_win_dire")
            btn_win_dir.callback = self.btn_win_dire
            self.add_item(btn_win_dir)

    async def btn_start(self, interaction: discord.Interaction):
        await interaction.response.defer()
        db = self.bot.db.active_lobbies
        lobby = await db.find_one({"_id": self.lobby_id})

        if lobby.get("shuffled"):
            return await interaction.followup.send("❌ Лобби уже запущено.", ephemeral=True)

        slots = lobby["slots"]
        if not all(len(slots[p]) == 2 for p in ("pos1", "pos2", "pos3", "pos4", "pos5")):
            return await interaction.followup.send("❌ Нельзя запустить лобби: не все слоты заняты (нужно 10/10).", ephemeral=True)

        all_uids = [uid for players in slots.values() for uid in players]
        users_cursor = self.bot.db.users.find({"_id": {"$in": all_uids}, "guild_id": str(interaction.guild.id)})
        
        user_mmrs = {uid: 1000 for uid in all_uids}
        async for udoc in users_cursor:
            user_mmrs[udoc["_id"]] = udoc.get("mmr", 1000)

        radiant, dire = balance_teams_by_mmr(slots, user_mmrs)

        password = str(random.randint(1000, 9999))
        lobby.update({
            "shuffled": True,
            "radiant": radiant,
            "dire": dire,
            "password": password
        })

        guild = interaction.guild
        category = self.message.channel.category
        short_id = self.lobby_id.split('_')[1]
        host = guild.get_member(int(lobby["host_id"]))

        try:
            vc_results = await asyncio.gather(
                guild.create_voice_channel(name=f"🟩 Radiant #{short_id}", category=category),
                guild.create_voice_channel(name=f"🟥 Dire #{short_id}", category=category),
                return_exceptions=True
            )
            
            radiant_vc, dire_vc = vc_results
            if isinstance(radiant_vc, Exception) or isinstance(dire_vc, Exception):
                raise discord.Forbidden("Failed to create channels")

            lobby["radiant_vc"] = radiant_vc.id
            lobby["dire_vc"] = dire_vc.id

            move_tasks = []
            dm_tasks = []

            for team, vc in [(radiant, radiant_vc), (dire, dire_vc)]:
                team_name = "Radiant" if vc == radiant_vc else "Dire"
                for uid in team.values():
                    m = guild.get_member(int(uid))
                    if not m:
                        continue
                    if m.voice:
                        move_tasks.append(m.move_to(vc))
                    if not m.bot and not str(uid).startswith("1000000000000000"):
                        embed_dm = WindrangerEmbed.dm_info(self.lobby_id, password, team_name, host, guild, radiant, dire, self.emojis)
                        dm_tasks.append(m.send(embed=embed_dm))

            if move_tasks:
                await asyncio.gather(*move_tasks, return_exceptions=True)
            if dm_tasks:
                await asyncio.gather(*dm_tasks, return_exceptions=True)

        except discord.Forbidden:
            await interaction.channel.send("⚠️ У бота нет прав на создание голосовых каналов или перемещение пользователей.")

        await db.update_one({"_id": self.lobby_id}, {"$set": lobby})

        embed = WindrangerEmbed.post_shuffle(self.lobby_id, host, guild, radiant, dire, self.emojis)
        main_view = LobbyView(self.bot, self.lobby_id, self.emojis)
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
            
        await interaction.followup.send("✅ Матч запущен! Пароли разосланы, команды отбалансированы по MMR, каналы созданы.", ephemeral=True)

    async def btn_cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        db = self.bot.db
        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        
        if lobby:
            guild = self.message.guild
            settings = await db.settings.find_one({"_id": str(guild.id)})
            waiting_room_id = settings.get("waiting_room_id") if settings else None
            waiting_room = guild.get_channel(waiting_room_id) if waiting_room_id else None

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
        await interaction.followup.send("🗑️ Лобби отменено, каналы удалены.", ephemeral=True)

    async def btn_win_radiant(self, interaction: discord.Interaction):
        await self.finish_match(interaction, "radiant")

    async def btn_win_dire(self, interaction: discord.Interaction):
        await self.finish_match(interaction, "dire")

    async def finish_match(self, interaction: discord.Interaction, winner: str):
        await interaction.response.defer()
        db = self.bot.db
        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        
        if not lobby:
            return await interaction.followup.send("❌ Лобби не найдено или уже завершено.", ephemeral=True)
            
        guild = self.message.guild
        radiant = lobby["radiant"]
        dire = lobby["dire"]
        settings = await db.settings.find_one({"_id": str(guild.id)})
        current_season = settings.get("current_season", 1) if settings else 1
        
        all_players_data = []
        for is_radiant_win, team in [(winner == "radiant", radiant), (winner == "dire", dire)]:
            for pos, uid in team.items():
                if uid and not str(uid).startswith("1000000000000000"):
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
        
        waiting_room_id = settings.get("waiting_room_id") if settings else None
        waiting_room = guild.get_channel(waiting_room_id) if waiting_room_id else None

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
        
        embed = WindrangerEmbed.match_result(self.lobby_id, host, guild, radiant, dire, winner, self.emojis)
        history_channel_id = settings.get("history_channel_id") if settings else None
        history_channel = guild.get_channel(history_channel_id) if history_channel_id else None

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
        await asyncio.gather(
            interaction.edit_original_response(view=self),
            interaction.followup.send(f"✅ Матч завершен! Победили **{'Свет' if winner == 'radiant' else 'Тьма'}**.\nМатч записан в историю.", ephemeral=True)
        )

class LobbyView(discord.ui.View):
    def __init__(self, bot, lobby_id: str, emojis: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.lobby_id = lobby_id
        self.emojis = emojis

    @discord.ui.button(label="Pos 1", style=discord.ButtonStyle.secondary, custom_id="pos1", row=0)
    async def btn_pos1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction, "pos1")

    @discord.ui.button(label="Pos 2", style=discord.ButtonStyle.secondary, custom_id="pos2", row=0)
    async def btn_pos2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction, "pos2")

    @discord.ui.button(label="Pos 3", style=discord.ButtonStyle.secondary, custom_id="pos3", row=0)
    async def btn_pos3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction, "pos3")

    @discord.ui.button(label="Pos 4", style=discord.ButtonStyle.secondary, custom_id="pos4", row=0)
    async def btn_pos4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction, "pos4")

    @discord.ui.button(label="Pos 5", style=discord.ButtonStyle.secondary, custom_id="pos5", row=0)
    async def btn_pos5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction, "pos5")

    @discord.ui.button(label="Покинуть", style=discord.ButtonStyle.red, custom_id="btn_leave", row=1)
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_leave(interaction)

    async def handle_join(self, interaction: discord.Interaction, pos: str):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        db = self.bot.db
        guild_id = str(interaction.guild.id)
        
        settings = await db.settings.find_one({"_id": guild_id})
        if settings and (waiting_room_id := settings.get("waiting_room_id")):
            waiting_vc = interaction.guild.get_channel(waiting_room_id)
            if waiting_vc:
                member = interaction.guild.get_member(interaction.user.id)
                if not member or not member.voice or member.voice.channel.id != waiting_room_id:
                    return await interaction.followup.send(f"❌ Сначала зайди в голосовой канал {waiting_vc.mention}!", ephemeral=True)

        user_data = await db.users.find_one({"_id": user_id, "guild_id": guild_id})
        if user_data and (ban_expires := user_data.get("ban_expires")):
            if ban_expires.replace(tzinfo=datetime.timezone.utc) > discord.utils.utcnow():
                expire_time = discord.utils.format_dt(ban_expires.replace(tzinfo=datetime.timezone.utc), "F")
                return await interaction.followup.send(f"❌ Вы забанены в матчмейкинге. Блокировка спадет: {expire_time}.", ephemeral=True)
        
        existing_lobby = await db.active_lobbies.find_one({
            "guild_id": guild_id,
            "_id": {"$ne": self.lobby_id},
            "$or": [
                {f"slots.pos{i}": user_id} for i in range(1, 6)
            ] + [
                {f"radiant.pos{i}": user_id} for i in range(1, 6)
            ] + [
                {f"dire.pos{i}": user_id} for i in range(1, 6)
            ]
        })

        if existing_lobby:
            short_id = existing_lobby["_id"].split('_')[1] if "_" in existing_lobby["_id"] else existing_lobby["_id"]
            return await interaction.followup.send(f"❌ Вы уже находитесь в лобби `#{short_id}`. Сначала покиньте его или завершите матч.", ephemeral=True)

        lobby = await db.active_lobbies.find_one({"_id": self.lobby_id})
        if not lobby or lobby.get("shuffled"):
            return await interaction.followup.send("❌ Лобби закрыто или уже запущено.", ephemeral=True)

        slots = lobby["slots"]

        for p, players in slots.items():
            if user_id in players:
                if p == pos:
                    return
                players.remove(user_id)

        if len(slots[pos]) >= 2:
            return await interaction.followup.send("❌ Эта позиция уже занята.", ephemeral=True)

        slots[pos].append(user_id)
        is_full = all(len(slots[p]) == 2 for p in ["pos1", "pos2", "pos3", "pos4", "pos5"])
        
        host = interaction.guild.get_member(int(lobby["host_id"]))
        embed = WindrangerEmbed.pre_shuffle(self.lobby_id, host, interaction.guild, slots, self.emojis)

        await db.active_lobbies.update_one({"_id": self.lobby_id}, {"$set": {"slots": slots}})
        await interaction.message.edit(embed=embed, view=self)
        
        if is_full:
            await interaction.channel.send(f"🎉 Лобби 10/10 собрано! <@{lobby['host_id']}>, запусти матч через `⚙️ Управление лобби`.")

    async def handle_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.active_lobbies
        lobby = await db.find_one({"_id": self.lobby_id})

        if not lobby or lobby.get("shuffled"):
            return await interaction.followup.send("❌ Нельзя покинуть запущенное лобби.", ephemeral=True)

        user_id = str(interaction.user.id)
        found = False
        slots = lobby["slots"]

        for players in slots.values():
            if user_id in players:
                players.remove(user_id)
                found = True
                break

        if not found:
            return

        await db.update_one({"_id": self.lobby_id}, {"$set": {"slots": slots}})
        
        host = interaction.guild.get_member(int(lobby["host_id"]))
        embed = WindrangerEmbed.pre_shuffle(self.lobby_id, host, interaction.guild, slots, self.emojis)
        
        await interaction.message.edit(embed=embed, view=self)

class LobbyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_emojis = ['pos1', 'pos2', 'pos3', 'pos4', 'pos5', 'radi', 'dire', 'dota']
        
        self.ctx_menu = app_commands.ContextMenu(
            name="Управление лобби",
            callback=self.manage_lobby_ctx,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def _update_guild_emojis(self, guild: discord.Guild):
        found_emojis = {}
        for emoji in guild.emojis:
            if emoji.name in self.target_emojis:
                found_emojis[emoji.name] = str(emoji) 
        if found_emojis:
            await self.bot.db.settings.update_one(
                {"_id": str(guild.id)}, {"$set": {"emojis": found_emojis}}, upsert=True
            )
        return found_emojis

    async def check_host_perms(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            return True
        if interaction.user.id == interaction.guild.owner_id:
            return True
            
        settings = await self.bot.db.settings.find_one({"_id": str(interaction.guild.id)})
        if settings and (host_role_id := settings.get("host_role_id")):
            role = interaction.guild.get_role(host_role_id)
            if role and role in interaction.user.roles:
                return True
        return False

    async def manage_lobby_ctx(self, interaction: discord.Interaction, message: discord.Message):
        lobby = await self.bot.db.active_lobbies.find_one({"message_id": str(message.id)})
        
        if not lobby:
            return await interaction.response.send_message("❌ Это сообщение не является активным лобби.", ephemeral=True)
            
        is_host = await self.check_host_perms(interaction)
        if lobby.get("host_id") != str(interaction.user.id) and not is_host:
            return await interaction.response.send_message("❌ У вас нет прав для управления этим лобби.", ephemeral=True)
            
        emojis = await self._update_guild_emojis(interaction.guild)
        view = AdminLobbyView(self.bot, lobby, message, emojis)
        
        await interaction.response.send_message(
            f"🔧 **Панель управления лобби ID:** `{lobby['_id']}`\nВыберите действие ниже:", 
            view=view, 
            ephemeral=True
        )

    @app_commands.command(name="lobby", description="Создать новое лобби 5v5")
    @app_commands.default_permissions(manage_messages=True)
    async def create_lobby(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild = interaction.guild
        settings = await self.bot.db.settings.find_one({"_id": str(guild.id)})
        
        if not settings or not settings.get("reg_channel_id"):
            return await interaction.followup.send("❌ Инфраструктура не настроена. Используйте `/setup`.", ephemeral=True)

        emojis = await self._update_guild_emojis(guild)
        
        counter = await self.bot.db.counters.find_one_and_update(
            {"_id": "lobby_sequence"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        lobby_seq = counter["seq"]
        lobby_id = f"lobby_{lobby_seq}"

        lobby_data = {
            "_id": lobby_id,
            "guild_id": str(guild.id),
            "host_id": str(interaction.user.id), 
            "message_id": None,                  
            "shuffled": False,
            "slots": {"pos1": [], "pos2": [], "pos3": [], "pos4": [], "pos5": []},
            "radiant": {},
            "dire": {}
        }
        await self.bot.db.active_lobbies.insert_one(lobby_data)
        
        view = LobbyView(self.bot, lobby_id, emojis)
        embed = WindrangerEmbed.pre_shuffle(lobby_id, interaction.user, guild, lobby_data["slots"], emojis)

        reg_channel = guild.get_channel(settings["reg_channel_id"])
        if not reg_channel:
            return await interaction.followup.send("❌ Канал регистрации не найден. Повторите `/setup`.", ephemeral=True)

        msg = await reg_channel.send(embed=embed, view=view)
        await self.bot.db.active_lobbies.update_one({"_id": lobby_id}, {"$set": {"message_id": str(msg.id)}})
        
        await interaction.followup.send(f"✅ Лобби создано в <#{reg_channel.id}>!")
        await asyncio.sleep(10)
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

    @app_commands.command(name="fill", description="[ADMIN] Заполнить последнее лобби ботами")
    @app_commands.default_permissions(administrator=True)
    async def fill_lobby(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.active_lobbies
        
        lobby = await db.find_one({"guild_id": str(interaction.guild.id), "shuffled": False}, sort=[("_id", -1)])
        
        if not lobby:
            return await interaction.followup.send("❌ Нет открытых лобби для заполнения.")

        dummy_ids = [str(100000000000000000 + i) for i in range(10)]
        slots = lobby["slots"]
        
        idx = 0
        for pos in ["pos1", "pos2", "pos3", "pos4", "pos5"]:
            while len(slots[pos]) < 2:
                slots[pos].append(dummy_ids[idx])
                idx += 1

        await db.update_one({"_id": lobby["_id"]}, {"$set": {"slots": slots}})
        
        settings = await self.bot.db.settings.find_one({"_id": str(interaction.guild.id)})
        reg_channel = interaction.guild.get_channel(settings["reg_channel_id"])
        
        try:
            msg = await reg_channel.fetch_message(int(lobby["message_id"]))
            host = interaction.guild.get_member(int(lobby["host_id"]))
            emojis = await self._update_guild_emojis(interaction.guild)
            embed = WindrangerEmbed.pre_shuffle(lobby["_id"], host, interaction.guild, slots, emojis)
            
            view = LobbyView(self.bot, lobby["_id"], emojis)
            await msg.edit(embed=embed, view=view)
            
            await reg_channel.send(f"🎉 Лобби 10/10 собрано! <@{lobby['host_id']}>, запусти матч через `⚙️ Управление лобби`.")
            await interaction.followup.send("✅ Лобби успешно заполнено.")
        except discord.NotFound:
            await db.delete_one({"_id": lobby["_id"]})
            await interaction.followup.send("❌ Найдены устаревшие данные о лобби («призрак»). База данных очищена. Попробуйте выполнить команду `/fill` ещё раз.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Ошибка обновления сообщения: {e}")

        await asyncio.sleep(10)
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

async def setup(bot):
    await bot.add_cog(LobbyCog(bot))
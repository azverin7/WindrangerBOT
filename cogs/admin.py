import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
from core.config import DEVELOPER_ID

logger = logging.getLogger('windranger.admin')

def is_admin_or_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        user = interaction.user
        if user.id == int(DEVELOPER_ID):
            return True
            
        guild = interaction.guild
        if not guild:
            return False
            
        if user.id == guild.owner_id:
            return True
            
        if isinstance(user, discord.Member) and user.guild_permissions.administrator:
            return True
            
        settings = await interaction.client.db.get_guild_config(guild.id)
        if settings and (host_role_id := settings.get("host_role_id")):
            role = guild.get_role(int(host_role_id))
            if role and role in user.roles:
                return True
                
        return False
    return app_commands.check(predicate)

def is_owner_or_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        if user_id == int(DEVELOPER_ID):
            return True
        if interaction.guild and user_id == interaction.guild.owner_id:
            return True
        return False
    return app_commands.check(predicate)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _cleanup_infrastructure(self, guild: discord.Guild) -> int:
        settings = await self.bot.db.get_guild_config(guild.id)
        target_categories = set()

        if settings and (reg_channel_id := settings.get("reg_channel_id")):
            reg_channel = guild.get_channel(int(reg_channel_id))
            if reg_channel and reg_channel.category:
                target_categories.add(reg_channel.category)

        for cat in guild.categories:
            cat_name = cat.name.lower()
            if any(keyword in cat_name for keyword in ("dota", "closes", "inhouses")):
                target_categories.add(cat)

        deleted_count = 0

        for cat in target_categories:
            for channel in cat.channels:
                try:
                    await channel.delete()
                    deleted_count += 1
                except discord.HTTPException as e:
                    logger.warning(f"Failed to delete channel {channel.id}: {e}")
            try:
                await cat.delete()
                deleted_count += 1
            except discord.HTTPException as e:
                logger.warning(f"Failed to delete category {cat.id}: {e}")

        return deleted_count

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ У вас нет прав для использования этой команды.", ephemeral=True)
        else:
            logger.error(f"AppCommand error in AdminCog: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Произошла внутренняя ошибка.", ephemeral=True)

    @app_commands.command(name="setup", description="[ADMIN] Снести старую инфраструктуру лобби и создать новую")
    @app_commands.default_permissions(administrator=True)
    @is_admin_or_dev()
    async def setup_infra(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        await self._cleanup_infrastructure(guild)

        category = await guild.create_category("dota 2 closes space")
        hist_ch = await guild.create_text_channel("history", category=category)
        stats_ch = await guild.create_text_channel("stats", category=category)
        lb_ch = await guild.create_text_channel("leaderboard", category=category)
        reg_ch = await guild.create_text_channel("registration", category=category)
        wait_vc = await guild.create_voice_channel("Ожидание клоза", category=category)

        role = discord.utils.get(guild.roles, name="host")
        if not role:
            role = await guild.create_role(name="host", color=discord.Color.blue())

        await self.bot.db.settings.update_one(
            {"_id": str(guild.id)},
            {"$set": {
                "reg_channel_id": reg_ch.id,
                "history_channel_id": hist_ch.id,
                "stats_channel_id": stats_ch.id,
                "leaderboard_channel_id": lb_ch.id,
                "waiting_room_id": wait_vc.id,
                "host_role_id": role.id
            }},
            upsert=True
        )
        
        self.bot.db.clear_cache(guild.id)

        try:
            await interaction.followup.send("✅ Старая инфраструктура удалена, новая успешно создана и привязана к базе.")
        except discord.NotFound:
            pass

    @app_commands.command(name="clear", description="[HOST] Очистить сообщения в текущем канале")
    @app_commands.describe(amount="Количество сообщений для удаления (1-100)")
    @is_admin_or_dev()
    async def clear_chat(self, interaction: discord.Interaction, amount: int = 10):
        if not (1 <= amount <= 100):
            return await interaction.response.send_message("⚠️ Укажите количество от 1 до 100.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"🧹 Чат очищен. Удалено сообщений: **{len(deleted)}**.")
        except discord.Forbidden:
            await interaction.followup.send("❌ У бота нет прав на удаление сообщений (Manage Messages) в этом канале.")
        except discord.HTTPException as e:
            logger.error(f"Failed to clear chat in {interaction.channel.id}: {e}")
            await interaction.followup.send("❌ Произошла ошибка при попытке очистить чат сервера.")

    @app_commands.command(name="cleanup_infra", description="[ADMIN] Удалить все каналы и категории бота (без создания новых)")
    @app_commands.default_permissions(administrator=True)
    @is_admin_or_dev()
    async def cleanup_infra(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        deleted_count = await self._cleanup_infrastructure(guild)

        await self.bot.db.settings.update_one(
            {"_id": str(guild.id)},
            {"$unset": {
                "reg_channel_id": "",
                "history_channel_id": "",
                "stats_channel_id": "",
                "leaderboard_channel_id": "",
                "waiting_room_id": ""
            }}
        )
        
        self.bot.db.clear_cache(guild.id)

        try:
            await interaction.followup.send(f"✅ Инфраструктура удалена. Удалено объектов: **{deleted_count}**.")
        except discord.NotFound:
            pass

    @app_commands.command(name="hard_reset", description="[OWNER] ПОЛНЫЙ ВАЙП БАЗЫ. Удаляет статистику, лобби, историю и сбрасывает сезон.")
    @app_commands.describe(confirm="Напишите CONFIRM заглавными буквами для подтверждения")
    @is_owner_or_dev()
    async def hard_reset_server(self, interaction: discord.Interaction, confirm: str):
        if confirm != "CONFIRM":
            return await interaction.response.send_message(
                "⚠️ **ВНИМАНИЕ:** Эта команда безвозвратно удалит ВСЮ статистику, историю матчей, лобби и обнулит сезоны.\n"
                "Для подтверждения вызовите команду снова и впишите `CONFIRM`.", 
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)

        try:
            cursor = self.bot.db.active_lobbies.find({"guild_id": guild_id})
            
            async for lobby in cursor:
                for vc_key in ("radiant_vc", "dire_vc"):
                    if vc_id := lobby.get(vc_key):
                        if vc := interaction.guild.get_channel(int(vc_id)):
                            try:
                                await vc.delete()
                            except discord.HTTPException as e:
                                logger.warning(f"Failed to delete VC {vc_id} during hard reset: {e}")

            await self.bot.db.users.delete_many({"guild_id": guild_id})
            await self.bot.db.match_history.delete_many({"guild_id": guild_id})
            await self.bot.db.active_lobbies.delete_many({"guild_id": guild_id})
            await self.bot.db.settings.delete_one({"_id": f"counters_{guild_id}"})
            
            await self.bot.db.settings.update_one(
                {"_id": guild_id}, 
                {"$set": {"current_season": 1}}
            )

            if stats_cog := self.bot.get_cog("StatsCog"):
                await stats_cog.update_leaderboard(interaction.guild)

            logger.info(f"HARD RESET executed by {interaction.user.id} on Guild: {guild_id}")
            try:
                await interaction.followup.send("✅ База данных сервера полностью очищена. Сезоны сброшены, статистика удалена.")
            except discord.NotFound:
                pass

        except Exception as e:
            logger.error(f"Error during hard reset on guild {guild_id}: {e}", exc_info=True)
            try:
                await interaction.followup.send("❌ Произошла критическая ошибка при очистке базы данных.")
            except discord.NotFound:
                pass

    @app_commands.command(name="unban", description="[HOST] Снять блокировку регистрации с игрока")
    @is_admin_or_dev()
    async def unban_player(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        result = await self.bot.db.users.update_one(
            {"_id": str(member.id), "guild_id": str(interaction.guild.id)},
            {"$unset": {"ban_expires": ""}}
        )
        
        if result.modified_count > 0:
            await interaction.followup.send(f"✅ Блокировка снята с игрока {member.mention}.")
        else:
            await interaction.followup.send(f"⚠️ Игрок {member.mention} не был забанен или не найден в БД.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
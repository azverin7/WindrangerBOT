import discord
from discord.ext import commands
from discord import app_commands
import logging

from utils.embeds import WindrangerEmbed
from utils.checks import is_privileged

logger = logging.getLogger('windranger.stats')

class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_top_players(self, guild_id: str, season: int, limit: int = 10) -> list:
        cursor = self.bot.db.users.find(
            {"guild_id": guild_id, "season": season, "matches": {"$gt": 0}}
        ).sort([("mmr", -1), ("wins", -1)]).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_leaderboard(self, guild: discord.Guild):
        config = await self.bot.db.get_guild_config(guild.id)
        lb_channel_id = config.get("leaderboard_channel_id")
        if not lb_channel_id:
            return
            
        channel = guild.get_channel(int(lb_channel_id))
        if not channel:
            return

        current_season = config.get("current_season", 1)
        tops = await self._get_top_players(str(guild.id), current_season)
        
        embed = WindrangerEmbed.leaderboard(guild, tops, current_season)
        
        msg_id = config.get("leaderboard_msg_id")
        msg = None
        
        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
            except discord.NotFound:
                pass
        
        if msg:
            try:
                await msg.edit(embed=embed)
            except discord.HTTPException as e:
                logger.error(f"Failed to edit leaderboard message in {guild.id}: {e}")
        else:
            try:
                new_msg = await channel.send(embed=embed)
                await self.bot.db.settings.update_one(
                    {"_id": str(guild.id)}, 
                    {"$set": {"leaderboard_msg_id": str(new_msg.id)}}
                )
                self.bot.db.clear_cache(guild.id)
            except discord.HTTPException as e:
                logger.error(f"Failed to send new leaderboard message in {guild.id}: {e}")

    @app_commands.command(name="stats", description="Показать статистику игрока в текущем сезоне")
    async def show_stats(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        target = member or interaction.user
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        
        p_data = await self.bot.db.users.find_one({
            "_id": str(target.id), 
            "guild_id": guild_id,
            "season": current_season
        })
        
        if not p_data or p_data.get("matches", 0) == 0:
            who = "У Вас" if target == interaction.user else f"У {target.display_name}"
            return await interaction.followup.send(f"❌ {who} пока нет сыгранных матчей в Сезоне {current_season}.")

        pts = p_data["mmr"]
        players_above = await self.bot.db.users.count_documents({
            "guild_id": guild_id,
            "season": current_season,
            "mmr": {"$gt": pts},
            "matches": {"$gt": 0}
        })
        rank_int = players_above + 1

        emojis = config.get("emojis", {})
        embed = WindrangerEmbed.player_stats(target, p_data, rank_int, emojis)
        embed.title = f"📊 Сезон {current_season} | Статистика: {target.display_name}"
        embed.set_footer(text=f"Запросил: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="top", description="Показать топ-10 игроков текущего сезона")
    async def show_top(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        
        tops = await self._get_top_players(guild_id, current_season)
        
        if not tops:
            return await interaction.followup.send(f"❌ В Сезоне {current_season} еще нет сыгранных матчей.")

        embed = WindrangerEmbed.leaderboard(interaction.guild, tops, current_season)
        embed.set_footer(text=f"Запросил: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_mmr", description="[ADMIN] Установить MMR игроку вручную")
    @is_privileged()
    async def set_mmr(self, interaction: discord.Interaction, member: discord.Member, mmr: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        
        await self.bot.db.users.update_one(
            {"_id": str(member.id), "guild_id": guild_id},
            {"$set": {"mmr": mmr, "season": current_season}},
            upsert=True
        )
        await self.update_leaderboard(interaction.guild)
        await interaction.followup.send(f"✅ MMR игрока {member.display_name} в сезоне {current_season} изменен на **{mmr}**.")

async def setup(bot):
    await bot.add_cog(StatsCog(bot))
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import WindrangerEmbed
from utils.checks import is_privileged
from core.config import DEFAULT_MMR

logger = logging.getLogger('windranger.stats')

class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_locale(self, interaction: discord.Interaction) -> discord.Locale:
        u_loc = await self.bot.db.get_user_locale(interaction.user.id)
        g_loc = None
        if interaction.guild_id:
            config = await self.bot.db.get_guild_config(interaction.guild_id)
            g_loc = config.get("locale")
            
        res_str = (
            u_loc or 
            g_loc or 
            (interaction.locale.value if interaction.locale else None) or 
            (interaction.guild_locale.value if interaction.guild_locale else None)
        )
        try:
            return discord.Locale(res_str) if res_str else self.bot.i18n.default_locale
        except ValueError:
            return self.bot.i18n.default_locale

    async def _get_top_players(self, guild_id: str, season: int, limit: int = 10) -> list:
        cursor = self.bot.db.users.find(
            {"guild_id": guild_id, "season": season, "matches": {"$gt": 0}}
        ).sort([("mmr", -1)]).limit(limit)
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
        
        g_loc = config.get("locale")
        res_str = g_loc or (guild.preferred_locale.value if guild.preferred_locale else None)
        try:
            locale = discord.Locale(res_str) if res_str else self.bot.i18n.default_locale
        except ValueError:
            locale = self.bot.i18n.default_locale
            
        embed = WindrangerEmbed.leaderboard(self.bot.i18n, locale, guild, tops, current_season)
        
        msg_id = config.get("leaderboard_msg_id")
        
        if msg_id:
            try:
                partial_msg = channel.get_partial_message(int(msg_id))
                await partial_msg.edit(embed=embed)
                return
            except discord.HTTPException as e:
                logger.warning(f"Failed to edit leaderboard message in {guild.id}: {e}")

        try:
            new_msg = await channel.send(embed=embed)
            await self.bot.db.settings.update_one(
                {"_id": str(guild.id)}, 
                {"$set": {"leaderboard_msg_id": str(new_msg.id)}}
            )
            self.bot.db.clear_guild_cache(guild.id)
        except discord.HTTPException as e:
            logger.error(f"Failed to send new leaderboard message in {guild.id}: {e}")

    @app_commands.command(name="stats", description="Show player statistics for the current season")
    async def show_stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        guild_id = str(interaction.guild.id)
        config = await self.bot.db.get_guild_config(guild_id)
        
        stats_ch_id = config.get("stats_channel_id")
        if stats_ch_id and interaction.channel_id != int(stats_ch_id):
            msg = self.bot.i18n.get_context_string(interaction, "stats", "err_wrong_channel", channel_id=stats_ch_id)
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()
        target = member or interaction.user
        current_season = config.get("current_season", 1)
        
        p_data = await self.bot.db.users.find_one({
            "_id": str(target.id), 
            "guild_id": guild_id,
            "season": current_season
        })
        
        if not p_data or p_data.get("matches", 0) == 0:
            who_key = "you" if target == interaction.user else "target"
            who_str = self.bot.i18n.get_context_string(interaction, "stats", who_key, name=target.display_name)
            msg = self.bot.i18n.get_context_string(interaction, "stats", "no_matches", who=who_str, season=current_season)
            return await interaction.followup.send(msg)

        pts = p_data.get("mmr", DEFAULT_MMR)
        players_above = await self.bot.db.users.count_documents({
            "guild_id": guild_id,
            "season": current_season,
            "mmr": {"$gt": pts},
            "matches": {"$gt": 0}
        })
        rank_int = players_above + 1

        emojis = config.get("emojis", {})
        locale = await self._get_locale(interaction)
        
        embed = WindrangerEmbed.player_stats(self.bot.i18n, locale, target, p_data, rank_int, emojis)
        
        title_str = self.bot.i18n.get_context_string(interaction, "stats", "embed_title", season=current_season, name=target.display_name)
        embed.title = title_str
        
        req_str = self.bot.i18n.get_context_string(interaction, "stats", "requested_by", name=interaction.user.display_name)
        embed.set_footer(text=req_str, icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="top_season", description="Show top 10 players for a specific season")
    @app_commands.describe(season="Season number")
    async def top_season(self, interaction: discord.Interaction, season: int):
        guild_id = str(interaction.guild.id)
        config = await self.bot.db.get_guild_config(guild_id)
        
        stats_ch_id = config.get("stats_channel_id")
        if stats_ch_id and interaction.channel_id != int(stats_ch_id):
            msg = self.bot.i18n.get_context_string(interaction, "stats", "err_wrong_channel", channel_id=stats_ch_id)
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()
        
        tops = await self._get_top_players(guild_id, season)
        locale = await self._get_locale(interaction)
        
        embed = WindrangerEmbed.leaderboard(self.bot.i18n, locale, interaction.guild, tops, season)
        
        req_str = self.bot.i18n.get_context_string(interaction, "stats", "requested_by", name=interaction.user.display_name)
        embed.set_footer(text=req_str, icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_pts", description="[ADMIN] Manually set a player's PTS")
    @is_privileged()
    async def set_pts(self, interaction: discord.Interaction, member: discord.Member, pts: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        
        await self.bot.db.users.update_one(
            {"_id": str(member.id), "guild_id": guild_id},
            {"$set": {"mmr": pts, "season": current_season}},
            upsert=True
        )
        await self.update_leaderboard(interaction.guild)
        
        msg = self.bot.i18n.get_context_string(interaction, "stats", "pts_updated", name=member.display_name, season=current_season, pts=pts)
        await interaction.followup.send(msg)

    @app_commands.command(name="refresh_lb", description="[ADMIN] Force refresh or restore the leaderboard message")
    @is_privileged()
    async def refresh_leaderboard_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_leaderboard(interaction.guild)
        
        msg = self.bot.i18n.get_context_string(interaction, "stats", "lb_refreshed")
        await interaction.followup.send(msg)

async def setup(bot):
    await bot.add_cog(StatsCog(bot))
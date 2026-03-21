from typing import Optional, List
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import WindrangerEmbed

logger = logging.getLogger('windranger.history')

class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
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

    async def season_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[int]]:
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        current_season = config.get("current_season", 1)
        
        locale = await self._get_locale(interaction)
        seasons = range(current_season, 0, -1)
        
        choices = []
        for s in seasons:
            if current in str(s):
                name = self.bot.i18n.get_string(locale, "history", "season_choice", season=s)
                choices.append(app_commands.Choice(name=name, value=s))
                
        return choices[:25]

    @app_commands.command(name="history", description="Show match history for the server")
    @app_commands.describe(limit="Number of matches (max 10)", season="Season number (default: current)")
    @app_commands.autocomplete(season=season_autocomplete)
    async def show_history(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5, season: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        config = await self.bot.db.get_guild_config(guild_id)
        target_season = season or config.get("current_season", 1)
        
        cursor = self.bot.db.match_history.find({
            "guild_id": guild_id,
            "season": target_season
        }).sort("timestamp", -1).limit(limit)
        
        matches = await cursor.to_list(length=limit)

        if not matches:
            msg = self.bot.i18n.get_context_string(interaction, "history", "history_empty", season=target_season)
            return await interaction.followup.send(msg)

        emojis = config.get("emojis", {})
        locale = await self._get_locale(interaction)

        embeds = []
        for match in matches:
            host = interaction.guild.get_member(int(match["host_id"]))
            embed = WindrangerEmbed.match_result(
                self.bot.i18n, locale, match["lobby_id"], host, interaction.guild, 
                match["radiant"], match["dire"], match["winner"], emojis
            )
            short_id = match['lobby_id'].split('_')[1] if '_' in match['lobby_id'] else match['lobby_id']
            embed.title = self.bot.i18n.get_string(locale, "history", "history_title", season=target_season, short_id=short_id)
            embeds.append(embed)

        await interaction.followup.send(embeds=embeds)

    @app_commands.command(name="season_stats", description="Show player statistics for a specific season")
    @app_commands.describe(season="Season number", member="Player (leave empty for your own stats)")
    @app_commands.autocomplete(season=season_autocomplete)
    async def show_season_stats(self, interaction: discord.Interaction, season: int, member: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        
        target = member or interaction.user
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        
        is_current = season == current_season
        query = {
            "_id": str(target.id) if is_current else f"{target.id}_s{season}",
            "guild_id": guild_id
        }
        if not is_current:
            query["season"] = season

        p_data = await self.bot.db.users.find_one(query)
        
        if not p_data or p_data.get("matches", 0) == 0:
            who_key = "you" if target == interaction.user else "target"
            who_str = self.bot.i18n.get_context_string(interaction, "history", who_key, name=target.display_name)
            msg = self.bot.i18n.get_context_string(interaction, "history", "season_stats_empty", who=who_str, season=season)
            return await interaction.followup.send(msg)

        pts = p_data.get("mmr", 1000)
        
        rank_query = {
            "guild_id": guild_id,
            "mmr": {"$gt": pts},
            "matches": {"$gt": 0},
            "season": season
        }

        players_above = await self.bot.db.users.count_documents(rank_query)
        rank_int = players_above + 1

        emojis = config.get("emojis", {})
        locale = await self._get_locale(interaction)

        embed = WindrangerEmbed.player_stats(self.bot.i18n, locale, target, p_data, rank_int, emojis)
        embed.title = self.bot.i18n.get_string(locale, "history", "season_stats_title", season=season, name=target.display_name)
        
        req_str = self.bot.i18n.get_string(locale, "history", "requested_by", name=interaction.user.display_name)
        embed.set_footer(text=req_str, icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HistoryCog(bot))
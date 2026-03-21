from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands
import logging

from utils.embeds import WindrangerEmbed

logger = logging.getLogger('windranger.history')

class PaginationView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0
        self.original_interaction = original_interaction
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("❌ Это не ваша панель истории.", ephemeral=True)
            return False
        return True

    def _update_buttons(self):
        self.btn_prev.disabled = self.current_page == 0
        self.btn_next.disabled = self.current_page == len(self.embeds) - 1
        self.lbl_page.label = f"Стр. {self.current_page + 1}/{len(self.embeds)}"

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary, custom_id="prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Стр. 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="lbl")
    async def lbl_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass 

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.original_interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass

class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def season_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[int]]:
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        current_season = config.get("current_season", 1)
        
        seasons = range(current_season, 0, -1)
        return [app_commands.Choice(name=f"Сезон {s}", value=s) for s in seasons if current in str(s)][:25]

    @app_commands.command(name="history", description="Показать историю последних матчей сервера")
    @app_commands.describe(limit="Количество матчей (до 20)", season="Номер сезона (по умолчанию текущий)")
    @app_commands.autocomplete(season=season_autocomplete)
    async def show_history(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 5, season: Optional[int] = None):
        await interaction.response.defer()
        
        guild_id = str(interaction.guild.id)
        config = await self.bot.db.get_guild_config(guild_id)
        target_season = season or config.get("current_season", 1)
        
        cursor = self.bot.db.match_history.find({
            "guild_id": guild_id,
            "season": target_season
        }).sort("timestamp", -1).limit(limit)
        
        matches = await cursor.to_list(length=limit)

        if not matches:
            return await interaction.followup.send(f"❌ История матчей для Сезона {target_season} пуста.")

        emojis = config.get("emojis", {})

        embeds = []
        for match in matches:
            host = interaction.guild.get_member(int(match["host_id"]))
            embed = WindrangerEmbed.match_result(
                match["lobby_id"], host, interaction.guild, 
                match["radiant"], match["dire"], match["winner"], emojis
            )
            short_id = match['lobby_id'].split('_')[1] if '_' in match['lobby_id'] else match['lobby_id']
            embed.title = f"🕒 Сезон {target_season} | Клоз #{short_id}"
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = PaginationView(interaction, embeds)
            await interaction.followup.send(embed=embeds[0], view=view)

    @app_commands.command(name="season_stats", description="Показать статистику игрока за конкретный сезон")
    @app_commands.describe(season="Номер сезона", member="Игрок (оставьте пустым для своей статистики)")
    @app_commands.autocomplete(season=season_autocomplete)
    async def show_season_stats(self, interaction: discord.Interaction, season: int, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        
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
            who = "У Вас" if target == interaction.user else f"У {target.display_name}"
            return await interaction.followup.send(f"❌ {who} нет сыгранных матчей в Сезоне {season}.")

        pts = p_data.get("mmr", 1000)
        
        rank_query = {
            "guild_id": guild_id,
            "mmr": {"$gt": pts},
            "matches": {"$gt": 0}
        }
        
        if not is_current:
            rank_query["season"] = season
        else:
            rank_query["season"] = {"$exists": False} 

        players_above = await self.bot.db.users.count_documents(rank_query)
        rank_int = players_above + 1

        emojis = config.get("emojis", {})

        embed = WindrangerEmbed.player_stats(target, p_data, rank_int, emojis)
        embed.title = f"📊 Сезон {season} | Статистика: {target.display_name}"
        embed.set_footer(text=f"Запросил: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HistoryCog(bot))
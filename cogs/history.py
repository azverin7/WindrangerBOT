from typing import Optional

import discord
from discord.ext import commands

from database.mongo import db
from core.config import ROLE_MAP, E_MEDALS, E_TROPHY
from utils.factory import UIHandler

class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_match_embed(self, match: dict, guild: discord.Guild) -> discord.Embed:
        return UIHandler.create_match_embed(match, guild)

    @commands.command(name="match")
    async def show_match(self, ctx: commands.Context, match_id: int):
        query = {
            "guild_id": ctx.guild.id,
            "$or": [{"match_id": match_id}, {"lobby_id": match_id}]
        }
        match = await db.history.find_one(query)
            
        if not match:
            return await ctx.send(f"Клоз №{match_id} не найден на этом сервере.", delete_after=5)

        embed = self._build_match_embed(match, ctx.guild)
        await ctx.send(embed=embed)

    @commands.command(name="history")
    async def show_history(self, ctx: commands.Context, limit: int = 5, season: Optional[int] = None):
        limit = max(1, min(limit, 10))
        
        query = {"guild_id": ctx.guild.id}
        if season is not None:
            query["season"] = season

        cursor = db.history.find(query).sort("ended_at", -1).limit(limit)
        matches = await cursor.to_list(length=limit)

        if not matches:
            return await ctx.send("История клозов по вашему запросу пуста.", delete_after=5)

        embeds = [self._build_match_embed(m, ctx.guild) for m in matches]
        await ctx.send(embeds=embeds)

    @commands.command(name="season_stats")
    async def show_season_stats(self, ctx: commands.Context, season: int, member: Optional[discord.Member] = None):
        target = member or ctx.author
        
        config = await db.settings.find_one({"_id": str(ctx.guild.id)}) or {}
        current_season = config.get("current_season", 1)

        is_current = (season == current_season)
        collection = db.players if is_current else db.archived_players
        
        query_params = {"user_id": target.id, "guild_id": ctx.guild.id}
        if not is_current:
            query_params["season"] = season

        p_data = await collection.find_one(query_params)
        
        if not p_data:
            who = "У Вас" if target == ctx.author else f"у {target.display_name}"
            return await ctx.send(f"{who} нет сыгранных клозов на этом сервере в Сезоне {season}.", delete_after=5)

        pts = p_data.get("pts", 1000)
        total = p_data.get("matches", 0)
        wins = p_data.get("wins", 0)
        losses = p_data.get("losses", 0)
        streak = p_data.get("streak", 0)
        
        if total == 0:
            rank_display = "--"
        else:
            rank_query = {"guild_id": ctx.guild.id, "pts": {"$gt": pts}, "matches": {"$gt": 0}}
            if not is_current:
                rank_query["season"] = season
            players_above = await collection.count_documents(rank_query)
            rank_int = players_above + 1
            rank_display = E_MEDALS.get(rank_int, f"#{rank_int}")

        raw_wr = (wins / total) if total > 0 else 0
        wr_percent = int(raw_wr * 100)

        embed = discord.Embed(
            title=f"Архив Сезона {season}: {target.display_name}", 
            color=0x3498db,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Ранг", value=f"**{rank_display}**", inline=True)
        embed.add_field(name="Очки (PTS)", value=f"**{pts}**", inline=True)
        embed.add_field(name="Винрейт", value=f"**{wr_percent}%**", inline=True)
        
        embed.add_field(name="Всего игр", value=f"**{total}**", inline=True)
        embed.add_field(name="Стрик", value=f"**{streak}**", inline=True)
        embed.add_field(name="W / L", value=f"**{wins} / {losses}**", inline=True)

        embed.add_field(name="\u200b", value="**Статистика по позициям:**", inline=False)

        p_roles = p_data.get("roles", {})

        for pos_id in range(1, 6):
            pos_str = str(pos_id)
            r_stats = p_roles.get(pos_str, {})
            r_w = r_stats.get("wins", 0)
            r_m = r_stats.get("matches", 0)
            r_l = r_m - r_w
            
            role_icon = UIHandler.get_role_emoji(ctx.guild, pos_str)
            icon_name = f"{role_icon}" if role_icon else f"Поз {pos_str}"
            
            if r_m == 0:
                wr_str = "--%"
            else:
                wr_str = f"{int((r_w / r_m) * 100)}%"

            val_str = f"**{r_w}/{r_l}**\n{wr_str}"

            embed.add_field(
                name=icon_name, 
                value=val_str, 
                inline=True
            )

        footer_icon = ctx.guild.icon.url if ctx.guild.icon else None
        embed.set_footer(text=f"Запросил: {ctx.author.display_name}", icon_url=footer_icon)
        
        await ctx.send(embed=embed)

    @commands.command(name="season_top")
    async def show_season_top(self, ctx: commands.Context, season: int):
        config = await db.settings.find_one({"_id": str(ctx.guild.id)}) or {}
        current_season = config.get("current_season", 1)

        is_current = (season == current_season)

        if is_current:
            cursor = db.players.find({
                "guild_id": ctx.guild.id, 
                "matches": {"$gt": 0}
            }).sort("pts", -1).limit(10)
        else:
            cursor = db.archived_players.find({
                "guild_id": ctx.guild.id, 
                "season": season, 
                "matches": {"$gt": 0}
            }).sort("pts", -1).limit(10)
        
        tops = await cursor.to_list(length=10)

        title_prefix = "Топ-10 игроков" if is_current else f"Итоги Сезона {season}"
        embed = discord.Embed(title=f"{title_prefix}: {ctx.guild.name}", color=0xf1c40f)
        
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        
        desc_lines = []
        
        if not tops:
            desc_lines.append(f"*Данные для Сезона {season} не найдены.*")
        else:
            for i in range(1, 11):
                if i <= len(tops):
                    p = tops[i-1]
                    pts = p.get("pts", 1000)
                    w = p.get("wins", 0)
                    l = p.get("losses", 0)
                    total = w + l
                    wr = int((w / total) * 100) if total > 0 else 0
                    
                    line = f"**{i}.** <@{p['user_id']}> • **{pts} PTS** • **{w}W / {l}L ({wr}%)**"
                    desc_lines.append(line)
                else:
                    desc_lines.append(f"**{i}.** *Свободный слот*")

        embed.description = "\n\n".join(desc_lines)
        embed.set_footer(text=f"Запросил: {ctx.author.display_name} • Сезон {season}")

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HistoryCog(bot))
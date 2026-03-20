from typing import Optional

import discord
from discord.ext import commands
import logging

from core.config import ROLE_MAP, E_MEDALS, E_TROPHY
from database.mongo import db
from utils.factory import UIHandler

logger = logging.getLogger('windranger.stats')

class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await db.get_guild_config(message.guild.id)
        if not config or message.channel.id != config.get("stats_channel_id"):
            return

        if not message.content.lower().startswith(("!stats", "!rank")):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    async def _check_channel(self, ctx: commands.Context, channel_type: str) -> bool:
        config = await db.get_guild_config(ctx.guild.id)
        if not config: return False
        
        target_id = config.get(f"{channel_type}_channel_id")
        return ctx.channel.id == target_id

    async def update_leaderboard(self, guild: discord.Guild) -> None:
        config = await db.get_guild_config(guild.id)
        if not config: return
        
        lb_channel_id = config.get("leaderboard_channel_id")
        channel = guild.get_channel(lb_channel_id) if lb_channel_id else None
        if not channel: return

        cursor = db.players.find({"guild_id": guild.id, "matches": {"$gt": 0}}).sort("pts", -1).limit(10)
        tops = await cursor.to_list(length=10)

        embed = discord.Embed(title=f"Топ-10 игроков: {guild.name}", color=0xf1c40f)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        desc_lines = []
        
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
        embed.set_footer(text=f"Обновлено: {discord.utils.utcnow().strftime('%H:%M:%S')}")

        msg_id = config.get("leaderboard_msg_id")
        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound: pass 

        new_msg = await channel.send(embed=embed)
        await db.settings.update_one({"_id": str(guild.id)}, {"$set": {"leaderboard_msg_id": new_msg.id}})
        db.clear_cache(guild.id)

    @commands.command(name="stats", aliases=["rank"])
    async def show_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if not await self._check_channel(ctx, "stats"): return
        
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
            
        target = member or ctx.author
        p_data = await db.players.find_one({"user_id": target.id, "guild_id": ctx.guild.id})
        
        if not p_data:
            who = "У Вас" if target == ctx.author else f"у {target.display_name}"
            return await ctx.send(f"{who} пока нет сыгранных клозов на этом сервере.", delete_after=5)

        pts = p_data.get("pts", 1000)
        total = p_data.get("matches", 0)
        wins = p_data.get("wins", 0)
        losses = p_data.get("losses", 0)
        streak = p_data.get("streak", 0)
        
        if total == 0:
            rank_display = "--"
        else:
            players_above = await db.players.count_documents({
                "guild_id": ctx.guild.id,
                "pts": {"$gt": pts},
                "matches": {"$gt": 0}
            })
            rank_int = players_above + 1
            rank_display = E_MEDALS.get(rank_int, f"#{rank_int}")

        raw_wr = (wins / total) if total > 0 else 0
        wr_percent = int(raw_wr * 100)

        embed = discord.Embed(
            title=f"Статистика: {target.display_name}", 
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

    @commands.command(name="top")
    async def force_top(self, ctx: commands.Context):
        if not await self._check_channel(ctx, "leaderboard"): return
        try: await ctx.message.delete()
        except discord.HTTPException: pass
        await self.update_leaderboard(ctx.guild)
        
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
from typing import Optional

import discord
from discord.ext import commands

from database.mongo import db

class ResetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="hard_reset")
    @commands.has_permissions(administrator=True)
    async def hard_reset_server(self, ctx: commands.Context, confirm: Optional[str] = None):
        if confirm != "CONFIRM":
            return await ctx.send(
                "⚠️ **ВНИМАНИЕ:** Эта команда безвозвратно удалит ВСЮ статистику, историю клозов и активные лобби на этом сервере.\n"
                "Для подтверждения введите: `!hard_reset CONFIRM`"
            )

        msg = await ctx.send("🔥 Выполняется полное уничтожение данных сервера...")

        await db.players.delete_many({"guild_id": ctx.guild.id})
        await db.archived_players.delete_many({"guild_id": ctx.guild.id})
        await db.history.delete_many({"guild_id": ctx.guild.id})
        await db.lobbies.delete_many({"guild_id": ctx.guild.id})

        await db.settings.update_one(
            {"_id": str(ctx.guild.id)},
            {"$set": {"current_season": 1}}
        )

        try:
            await db.counters.delete_many({"guild_id": ctx.guild.id})
        except:
            pass

        stats_cog = self.bot.get_cog("StatsCog")
        if stats_cog:
            await stats_cog.update_leaderboard(ctx.guild)

        await msg.edit(content="✅ База данных сервера полностью очищена.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ResetCog(bot))
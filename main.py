import asyncio
import logging

import discord
from discord.ext import commands
import uvloop

from core.bot import WindrangerBot
from core.logger import setup_logging
from core.config import DISCORD_TOKEN

logger = logging.getLogger('windranger.main')

bot = WindrangerBot()

@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context) -> None:
    try:
        await ctx.message.delete()
    except discord.HTTPException as e:
        logger.warning(f"Failed to delete sync command message: {e}")

    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} app commands.")
        msg = await ctx.send(f"✅ Synced {len(synced)} commands.")
        
        try:
            await msg.delete(delay=5.0)
        except discord.HTTPException:
            pass
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)
        try:
            msg = await ctx.send(f"❌ Sync error: {e}")
            await msg.delete(delay=5.0)
        except discord.HTTPException:
            pass

async def main() -> None:
    setup_logging()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
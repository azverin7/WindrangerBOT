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
async def sync(ctx):
    await ctx.message.delete()
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано {len(synced)} слэш-команд.")
        msg = await ctx.send(f"✅ Синхронизировано {len(synced)} команд.")
        await msg.delete(delay=5)
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)
        msg = await ctx.send(f"❌ Ошибка синхронизации: {e}")
        await msg.delete(delay=5)

async def main():
    setup_logging()
    
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
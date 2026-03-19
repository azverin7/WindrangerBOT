import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from core.bot import WindrangerBot
from core.logger import setup_logging
from core.config import TOKEN

async def main():
    setup_logging()
    bot = WindrangerBot()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
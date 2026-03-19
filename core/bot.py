import discord
from discord.ext import commands
import logging
import sys
from pathlib import Path
from database.mongo import db
from utils.checks import SilentCheckFailure

logger = logging.getLogger('windranger.bot')

class WindrangerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        if not await db.connect_and_init():
            sys.exit(1)

        DISABLED_COGS = [""]
        cogs_dir = Path(__file__).parent.parent / "cogs"
        
        for file_path in cogs_dir.glob("*.py"):
            if not file_path.name.startswith("__"):
                cog_name = f"cogs.{file_path.stem}"
                if cog_name in DISABLED_COGS:
                    continue
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"LOADED: {cog_name}")
                except Exception as e:
                    logger.error(f"FAILED TO LOAD {cog_name}: {e}")

        try:
            active_lobbies = await db.lobbies.find({"active": False}).to_list(length=None)
            lobby_cog = self.get_cog("LobbyCog")
            if lobby_cog:
                from cogs.lobby import LobbyView
                for lobby in active_lobbies:
                    self.add_view(LobbyView(lobby_cog, lobby["lobby_id"]))
        except Exception as e:
            logger.error(f"Failed to restore persistent views: {e}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
            
        if isinstance(error, SilentCheckFailure):
            try: await ctx.message.delete()
            except discord.HTTPException: pass
            return

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"⚠️ Ошибка: Пропущен обязательный аргумент `{error.param.name}`.", delete_after=5)
            
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("⚠️ Ошибка: У вас недостаточно прав для использования этой команды.", delete_after=5)
            
        if isinstance(error, commands.BadArgument):
            return await ctx.send("⚠️ Ошибка: Неверный формат аргумента.", delete_after=5)

        logger.error(f"COMMAND ERROR in !{ctx.command}: {error}")

    async def on_ready(self):
        logger.info(f"SYSTEM ONLINE: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} servers.")
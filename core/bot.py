import sys
from pathlib import Path
import logging
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

from database.mongo import Database

logger = logging.getLogger('windranger.bot')

class SilentCheckFailure(app_commands.CheckFailure):
    pass

class WindrangerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db = Database()
        self.disabled_cogs: List[str] = []

    async def setup_hook(self) -> None:
        if not await self.db.connect_and_init():
            logger.critical("Database initialization failed. Shutting down.")
            sys.exit(1)

        cogs_dir = Path(__file__).parent.parent / "cogs"
        
        for file_path in cogs_dir.glob("*.py"):
            if not file_path.name.startswith("__"):
                cog_name = f"cogs.{file_path.stem}"
                
                if cog_name in self.disabled_cogs:
                    logger.info(f"SKIPPED (DISABLED): {cog_name}")
                    continue
                    
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"LOADED: {cog_name}")
                except Exception as e:
                    logger.error(f"FAILED TO LOAD {cog_name}: {e}", exc_info=True)

        self.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SilentCheckFailure):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer(ephemeral=True)
                    await interaction.delete_original_response()
                except discord.HTTPException:
                    pass
            return

        if isinstance(error, app_commands.MissingPermissions):
            msg = "⚠️ У вас недостаточно прав для использования этой команды."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "⚠️ У бота нет необходимых прав для выполнения этой команды."
        else:
            msg = "❌ Произошла внутренняя системная ошибка."
            cmd_name = interaction.command.name if interaction.command else 'Unknown'
            logger.error(f"Command error in {cmd_name}: {error}", exc_info=True)

        if interaction.response.is_done():
            try:
                await interaction.followup.send(msg, ephemeral=True)
            except discord.HTTPException:
                pass
        else:
            try:
                await interaction.response.send_message(msg, ephemeral=True)
            except discord.HTTPException:
                pass

    async def on_ready(self):
        logger.info(f"SYSTEM ONLINE: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} servers.")
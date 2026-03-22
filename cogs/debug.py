import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.config import DEVELOPER_ID
from utils.embeds import WindrangerEmbed
from cogs.lobby import LobbyView

logger = logging.getLogger('windranger.debug')

def is_developer():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == int(DEVELOPER_ID)
    return app_commands.check(predicate)

class DebugCog(commands.Cog):
    def __init__(self, bot):
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

    @app_commands.command(name="fill", description="[DEBUG] Fill the latest lobby with dummy players")
    @is_developer()
    async def fill_lobby(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        db = self.bot.db.active_lobbies
        guild_id = str(interaction.guild.id)
        
        max_retries = 3
        lobby = None
        
        for _ in range(max_retries):
            lobby = await db.find_one({"guild_id": guild_id, "shuffled": False}, sort=[("_id", -1)])
            
            if not lobby:
                msg = self.bot.i18n.get_context_string(interaction, "lobby", "no_open_lobbies")
                return await interaction.followup.send(msg, ephemeral=True)

            slots = lobby["slots"]
            all_players = lobby.get("all_players", [])
            current_version = lobby.get("version", 1)
            
            dummy_start = 100000000000000000
            idx = 0
            
            for pos in ["pos1", "pos2", "pos3", "pos4", "pos5"]:
                while len(slots[pos]) < 2:
                    dummy_id = str(dummy_start + idx)
                    if dummy_id not in all_players:
                        slots[pos].append(dummy_id)
                        all_players.append(dummy_id)
                    idx += 1

            res = await db.update_one(
                {"_id": lobby["_id"], "version": current_version},
                {"$set": {"slots": slots, "all_players": all_players, "version": current_version + 1}}
            )
            
            if res.modified_count > 0:
                lobby["slots"] = slots
                lobby["all_players"] = all_players
                break
        else:
            msg = self.bot.i18n.get_context_string(interaction, "lobby", "update_error", e="OCC failed after 3 retries")
            return await interaction.followup.send(msg, ephemeral=True)

        config = await self.bot.db.get_guild_config(interaction.guild.id)
        reg_channel_id = config.get("reg_channel_id")
        
        if not reg_channel_id:
            msg = self.bot.i18n.get_context_string(interaction, "lobby", "no_infra")
            return await interaction.followup.send(msg, ephemeral=True)

        reg_channel = interaction.guild.get_channel(int(reg_channel_id))
        if not reg_channel:
            try:
                reg_channel = await interaction.guild.fetch_channel(int(reg_channel_id))
            except discord.NotFound:
                msg = self.bot.i18n.get_context_string(interaction, "lobby", "reg_channel_not_found")
                return await interaction.followup.send(msg, ephemeral=True)

        try:
            msg_obj = await reg_channel.fetch_message(int(lobby["message_id"]))
            host = interaction.guild.get_member(int(lobby["host_id"]))
            emojis = config.get("emojis", {})
            locale = await self._get_locale(interaction)
            
            embed = WindrangerEmbed.pre_shuffle(self.bot.i18n, locale, lobby["_id"], host, interaction.guild, lobby["slots"], emojis)
            view = LobbyView(self.bot, lobby["_id"], emojis, locale)
            
            await msg_obj.edit(embed=embed, view=view)
            
            full_msg = self.bot.i18n.get_string(locale, "lobby", "lobby_full", host_id=lobby['host_id'])
            await reg_channel.send(full_msg)
            
            success_msg = self.bot.i18n.get_context_string(interaction, "lobby", "lobby_filled")
            await interaction.followup.send(success_msg, ephemeral=True)
            
        except discord.NotFound:
            await db.delete_one({"_id": lobby["_id"]})
            err_msg = self.bot.i18n.get_context_string(interaction, "lobby", "ghost_lobby")
            await interaction.followup.send(err_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to update message for filled lobby {lobby['_id']}: {e}", exc_info=True)
            err_msg = self.bot.i18n.get_context_string(interaction, "lobby", "update_error", e=str(e))
            await interaction.followup.send(err_msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(DebugCog(bot))
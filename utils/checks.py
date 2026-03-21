import discord
from discord import app_commands

from core.config import DEVELOPER_ID

def is_privileged():
    async def predicate(interaction: discord.Interaction) -> bool:
        user = interaction.user
        if user.id == int(DEVELOPER_ID):
            return True
            
        guild = interaction.guild
        if not guild:
            return False
            
        if user.id == guild.owner_id:
            return True
            
        if isinstance(user, discord.Member) and user.guild_permissions.administrator:
            return True
            
        settings = await interaction.client.db.get_guild_config(guild.id)
        if settings:
            gh_role_id = settings.get("grand_host_role_id")
            if gh_role_id and (gh_role := guild.get_role(int(gh_role_id))) and gh_role in user.roles:
                return True
                
            h_role_id = settings.get("host_role_id")
            if h_role_id and (h_role := guild.get_role(int(h_role_id))) and h_role in user.roles:
                return True
                
        return False
    return app_commands.check(predicate)
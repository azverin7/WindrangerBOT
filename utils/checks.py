import discord
from discord import app_commands
from core.config import DEVELOPER_ID

class SilentCheckFailure(app_commands.CheckFailure):
    pass

def is_privileged(grand_only: bool = False):
    async def predicate(interaction: discord.Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild

        if not guild:
            raise SilentCheckFailure()

        if user.id == int(DEVELOPER_ID) or user.id == guild.owner_id:
            return True

        if isinstance(user, discord.Member) and user.guild_permissions.administrator:
            return True

        if not grand_only:
            config = await interaction.client.db.get_guild_config(guild.id)
            if host_role_id := config.get("host_role_id"):
                role = guild.get_role(host_role_id)
                if role and isinstance(user, discord.Member) and role in user.roles:
                    return True

        raise SilentCheckFailure()
        
    return app_commands.check(predicate)
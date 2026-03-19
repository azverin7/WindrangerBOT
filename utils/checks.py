import discord
from discord.ext import commands
from core.config import DEVELOPER_ID
from database.mongo import db

class SilentCheckFailure(commands.CheckFailure):
    pass

def is_privileged(grand_only: bool = False):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id == ctx.guild.owner_id or ctx.author.id == DEVELOPER_ID:
            return True
            
        if ctx.author.guild_permissions.administrator:
            return True
            
        config = await db.get_guild_config(ctx.guild.id)
        host_role_id = config.get("host_role_id")
        
        if host_role_id and not grand_only:
            role = ctx.guild.get_role(host_role_id)
            if role and role in ctx.author.roles:
                return True
                
        raise SilentCheckFailure()
        
    return commands.check(predicate)
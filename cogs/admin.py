import logging
import datetime
import asyncio
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import InsertOne, UpdateOne

from core.config import DEVELOPER_ID, DEFAULT_MMR

logger = logging.getLogger('windranger.admin')

def _base_role_check(role_keys: tuple[str, ...]):
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
        if not settings:
            return False
            
        for key in role_keys:
            role_id = settings.get(key)
            if role_id and (role := guild.get_role(int(role_id))) and role in user.roles:
                return True
                
        return False
    return app_commands.check(predicate)

def is_admin_or_dev():
    return _base_role_check(("grand_host_role_id", "host_role_id"))

def is_grand_host_or_admin():
    return _base_role_check(("grand_host_role_id",))

def is_owner_or_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        if user_id == int(DEVELOPER_ID):
            return True
        if interaction.guild and user_id == interaction.guild.owner_id:
            return True
        return False
    return app_commands.check(predicate)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.ban_expiration_worker.start()

    async def cog_unload(self):
        self.ban_expiration_worker.cancel()

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

    @tasks.loop(minutes=5.0)
    async def ban_expiration_worker(self):
        now = discord.utils.utcnow()
        cursor = self.bot.db.users.find({"ban_expires": {"$lte": now}})
        
        affected_guilds = set()
        bulk_ops = []
        
        async for user_doc in cursor:
            guild_id = user_doc.get("guild_id")
            user_id = user_doc.get("_id")
            
            if not guild_id or not user_id:
                continue
                
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                config = await self.bot.db.get_guild_config(guild.id)
                if ban_role_id := config.get("ban_role_id"):
                    ban_role = guild.get_role(int(ban_role_id))
                    member = guild.get_member(int(user_id))
                    if ban_role and member and ban_role in member.roles:
                        try:
                            await member.remove_roles(ban_role)
                        except discord.HTTPException as e:
                            logger.warning(f"Worker failed to remove ban role from {user_id}: {e}")
                affected_guilds.add(guild)

            bulk_ops.append(UpdateOne(
                {"_id": user_id, "guild_id": guild_id},
                {"$unset": {"ban_expires": "", "ban_reason": "", "ban_penalty": ""}}
            ))

        if bulk_ops:
            try:
                await self.bot.db.users.bulk_write(bulk_ops)
            except Exception as e:
                logger.error(f"Failed to execute bulk update in ban_expiration_worker: {e}")

        update_tasks = [self.update_ban_list(guild) for guild in affected_guilds]
        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)

    @ban_expiration_worker.before_loop
    async def before_ban_expiration_worker(self):
        await self.bot.wait_until_ready()

    async def update_ban_list(self, guild: discord.Guild):
        config = await self.bot.db.get_guild_config(guild.id)
        bl_channel_id = config.get("banlist_channel_id")
        if not bl_channel_id:
            return
            
        channel = guild.get_channel(int(bl_channel_id))
        if not channel:
            return

        g_loc = config.get("locale")
        res_str = g_loc or (guild.preferred_locale.value if guild.preferred_locale else None)
        try:
            locale = discord.Locale(res_str) if res_str else self.bot.i18n.default_locale
        except ValueError:
            locale = self.bot.i18n.default_locale

        now = discord.utils.utcnow()
        cursor = self.bot.db.users.find({
            "guild_id": str(guild.id), 
            "ban_expires": {"$gt": now}
        }).sort("ban_expires", 1)

        embed = discord.Embed(
            title=self.bot.i18n.get_string(locale, "admin", "banlist_title"),
            color=discord.Color.dark_red(),
            timestamp=now
        )
        
        desc = ""
        async for user_doc in cursor:
            uid = user_doc["_id"]
            expires = user_doc["ban_expires"].replace(tzinfo=datetime.timezone.utc)
            reason = user_doc.get("ban_reason", "N/A")
            penalty = user_doc.get("ban_penalty", 0)
            
            time_str = discord.utils.format_dt(expires, 'f')
            entry = self.bot.i18n.get_string(
                locale, "admin", "banlist_entry", 
                uid=uid, time=time_str, reason=reason, penalty=penalty
            )
            
            if len(desc) + len(entry) > 4000:
                break
            desc += entry

        if not desc:
            desc = f"*{self.bot.i18n.get_string(locale, 'admin', 'banlist_empty')}*"

        embed.description = desc
        msg_id = config.get("banlist_msg_id")
        
        if msg_id:
            try:
                partial_msg = channel.get_partial_message(int(msg_id))
                await partial_msg.edit(embed=embed)
                return
            except discord.HTTPException:
                pass

        try:
            new_msg = await channel.send(embed=embed)
            await self.bot.db.settings.update_one(
                {"_id": str(guild.id)}, 
                {"$set": {"banlist_msg_id": str(new_msg.id)}}
            )
            self.bot.db.clear_guild_cache(guild.id)
        except discord.HTTPException as e:
            logger.error(f"Failed to send banlist message in {guild.id}: {e}")

    async def _cleanup_infrastructure(self, guild: discord.Guild) -> int:
        settings = await self.bot.db.get_guild_config(guild.id)
        target_categories = set()

        if settings:
            if cat_id := settings.get("infra_category_id"):
                try:
                    cat = guild.get_channel(int(cat_id)) or await guild.fetch_channel(int(cat_id))
                    if cat and isinstance(cat, discord.CategoryChannel):
                        target_categories.add(cat)
                except discord.NotFound:
                    pass
            
            for key in ("reg_channel_id", "banlist_channel_id"):
                if ch_id := settings.get(key):
                    try:
                        ch = guild.get_channel(int(ch_id)) or await guild.fetch_channel(int(ch_id))
                        if ch and ch.category:
                            target_categories.add(ch.category)
                    except discord.NotFound:
                        pass

        for cat in guild.categories:
            cat_name = cat.name.lower()
            if any(keyword in cat_name for keyword in ("dota", "closes", "inhouses")):
                target_categories.add(cat)

        deleted_count = 0

        for cat in target_categories:
            for channel in cat.channels:
                try:
                    await channel.delete()
                    deleted_count += 1
                except discord.HTTPException as e:
                    logger.warning(f"Failed to delete channel {channel.id}: {e}")
            try:
                await cat.delete()
                deleted_count += 1
            except discord.HTTPException as e:
                logger.warning(f"Failed to delete category {cat.id}: {e}")

        return deleted_count

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                msg = self.bot.i18n.get_context_string(interaction, "admin", "err_no_perms")
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            logger.error(f"AppCommand error in AdminCog: {error}", exc_info=True)
            if not interaction.response.is_done():
                msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
                await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="setup", description="cmd_setup_desc")
    @app_commands.default_permissions(administrator=True)
    @is_admin_or_dev()
    async def setup_infra(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        await self._cleanup_infrastructure(guild)

        settings = await self.bot.db.get_guild_config(guild.id)
        g_loc = settings.get("locale") if settings else None
        
        res_str = (
            g_loc or 
            (interaction.guild_locale.value if interaction.guild_locale else None) or 
            (interaction.locale.value if interaction.locale else None)
        )
        try:
            locale = discord.Locale(res_str) if res_str else self.bot.i18n.default_locale
        except ValueError:
            locale = self.bot.i18n.default_locale

        cat_name = self.bot.i18n.get_string(locale, "admin", "cat_name")
        wait_vc_name = self.bot.i18n.get_string(locale, "admin", "wait_vc_name")
        ch_history_name = self.bot.i18n.get_string(locale, "admin", "ch_history")
        ch_stats_name = self.bot.i18n.get_string(locale, "admin", "ch_stats")
        ch_lb_name = self.bot.i18n.get_string(locale, "admin", "ch_leaderboard")
        ch_reg_name = self.bot.i18n.get_string(locale, "admin", "ch_registration")
        ch_banlist_name = self.bot.i18n.get_string(locale, "admin", "ch_banlist")
        role_close_ban_name = self.bot.i18n.get_string(locale, "admin", "role_close_ban")
        
        rules_title = self.bot.i18n.get_string(locale, "admin", "reg_rules_title")
        rules_desc = self.bot.i18n.get_string(locale, "admin", "reg_rules_desc")

        try:
            gh_role = discord.utils.get(guild.roles, name="grand host")
            if not gh_role:
                gh_role = await guild.create_role(name="grand host", color=discord.Color.purple(), hoist=True)

            h_role = discord.utils.get(guild.roles, name="host")
            if not h_role:
                h_role = await guild.create_role(name="host", color=discord.Color.blue())

            ban_role_id = settings.get("ban_role_id") if settings else None
            ban_role = guild.get_role(int(ban_role_id)) if ban_role_id else None
            if not ban_role:
                ban_role = discord.utils.get(guild.roles, name=role_close_ban_name)
                if not ban_role:
                    ban_role = await guild.create_role(name=role_close_ban_name, color=discord.Color.dark_red())
        except discord.HTTPException as e:
            logger.error(f"Failed to create roles in {guild.id}: {e}")
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
            return await interaction.followup.send(msg)

        bot_member = guild.me
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=False, 
                use_application_commands=False, 
                connect=True, 
                speak=True
            ),
            ban_role: discord.PermissionOverwrite(
                connect=False, 
                send_messages=False, 
                use_application_commands=False
            ),
            h_role: discord.PermissionOverwrite(
                send_messages=True, 
                use_application_commands=True
            ),
            gh_role: discord.PermissionOverwrite(
                send_messages=True, 
                use_application_commands=True
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=True, 
                embed_links=True, 
                manage_messages=True, 
                manage_channels=True, 
                connect=True, 
                move_members=True, 
                use_application_commands=True
            )
        }

        try:
            category = await guild.create_category(cat_name, overwrites=overwrites)
            
            lb_ch = await guild.create_text_channel(ch_lb_name, category=category)
            
            stats_overwrites = overwrites.copy()
            stats_overwrites[guild.default_role] = discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=False, 
                use_application_commands=True, 
                connect=True, 
                speak=True
            )
            stats_ch = await guild.create_text_channel(ch_stats_name, category=category, overwrites=stats_overwrites)
            
            banlist_ch = await guild.create_text_channel(ch_banlist_name, category=category)
            
            hist_ch = await guild.create_text_channel(ch_history_name, category=category)
            
            reg_ch = await guild.create_text_channel(ch_reg_name, category=category)
            
            wait_vc = await guild.create_voice_channel(wait_vc_name, category=category)
            
        except discord.HTTPException as e:
            logger.error(f"Failed to create channels in {guild.id}: {e}")
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
            return await interaction.followup.send(msg)

        rules_embed = discord.Embed(
            title=rules_title, 
            description=rules_desc, 
            color=discord.Color.gold()
        )
        try:
            await reg_ch.send(embed=rules_embed)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send rules embed to {reg_ch.id}: {e}")

        await self.bot.db.settings.update_one(
            {"_id": str(guild.id)},
            {"$set": {
                "infra_category_id": category.id,
                "reg_channel_id": reg_ch.id,
                "history_channel_id": hist_ch.id,
                "stats_channel_id": stats_ch.id,
                "leaderboard_channel_id": lb_ch.id,
                "banlist_channel_id": banlist_ch.id,
                "waiting_room_id": wait_vc.id,
                "grand_host_role_id": gh_role.id,
                "host_role_id": h_role.id,
                "ban_role_id": ban_role.id
            }},
            upsert=True
        )
        
        self.bot.db.clear_guild_cache(guild.id)
        await self.update_ban_list(guild)

        try:
            msg = self.bot.i18n.get_context_string(interaction, "admin", "setup_success")
            await interaction.followup.send(msg)
        except discord.NotFound:
            pass

    @app_commands.command(name="add_host", description="cmd_add_host_desc")
    @is_grand_host_or_admin()
    async def add_host(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        
        h_role_id = config.get("host_role_id")
        if not h_role_id or not (h_role := interaction.guild.get_role(int(h_role_id))):
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_no_host_role")
            return await interaction.followup.send(msg)

        try:
            await member.add_roles(h_role)
            msg = self.bot.i18n.get_context_string(interaction, "admin", "host_added", mention=member.mention)
            await interaction.followup.send(msg)
        except discord.HTTPException as e:
            logger.error(f"Failed to add host role to {member.id}: {e}")
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
            await interaction.followup.send(msg)

    @app_commands.command(name="remove_host", description="cmd_remove_host_desc")
    @is_grand_host_or_admin()
    async def remove_host(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.get_guild_config(interaction.guild.id)
        
        h_role_id = config.get("host_role_id")
        if not h_role_id or not (h_role := interaction.guild.get_role(int(h_role_id))):
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_no_host_role")
            return await interaction.followup.send(msg)

        try:
            await member.remove_roles(h_role)
            msg = self.bot.i18n.get_context_string(interaction, "admin", "host_removed", mention=member.mention)
            await interaction.followup.send(msg)
        except discord.HTTPException as e:
            logger.error(f"Failed to remove host role from {member.id}: {e}")
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
            await interaction.followup.send(msg)

    @app_commands.command(name="punish", description="cmd_punish_desc")
    @app_commands.describe(
        member="cmd_punish_arg_member", 
        hours="cmd_punish_arg_hours",
        minutes="cmd_punish_arg_minutes",
        reason="cmd_punish_arg_reason",
        penalty="cmd_punish_arg_penalty"
    )
    @is_admin_or_dev()
    async def punish_player(self, interaction: discord.Interaction, member: discord.Member, hours: int, minutes: int, reason: str, penalty: int = 0):
        if hours < 0 or minutes < 0 or (hours == 0 and minutes == 0):
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_invalid_duration")
            if msg == "admin:err_invalid_duration":
                msg = "❌ Укажите длительность бана больше нуля (часы или минуты)."
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        locale = await self._get_locale(interaction)
        
        expires_at = discord.utils.utcnow() + datetime.timedelta(hours=hours, minutes=minutes)
        
        await self.bot.db.users.update_one(
            {"_id": str(member.id), "guild_id": guild_id},
            {
                "$set": {
                    "ban_expires": expires_at,
                    "ban_reason": reason,
                    "ban_penalty": abs(penalty)
                },
                "$inc": {"mmr": -abs(penalty), "offenses": 1}
            },
            upsert=True
        )

        config = await self.bot.db.get_guild_config(interaction.guild.id)
        ban_role_id = config.get("ban_role_id")
        ban_role = interaction.guild.get_role(int(ban_role_id)) if ban_role_id else None

        if not ban_role:
            role_close_ban_name = self.bot.i18n.get_string(locale, "admin", "role_close_ban")
            ban_role = discord.utils.get(interaction.guild.roles, name=role_close_ban_name)
            
            if not ban_role:
                try:
                    ban_role = await interaction.guild.create_role(name=role_close_ban_name, color=discord.Color.dark_red())
                except discord.HTTPException as e:
                    logger.error(f"Failed to dynamically create ban role: {e}")
            
            if ban_role:
                await self.bot.db.settings.update_one(
                    {"_id": guild_id},
                    {"$set": {"ban_role_id": ban_role.id}}
                )
                if cat_id := config.get("infra_category_id"):
                    cat = interaction.guild.get_channel(int(cat_id))
                    if isinstance(cat, discord.CategoryChannel):
                        try:
                            await cat.set_permissions(ban_role, connect=False, send_messages=False)
                        except discord.HTTPException:
                            pass

        if ban_role:
            try:
                await member.add_roles(ban_role)
            except discord.HTTPException as e:
                logger.warning(f"Failed to assign ban role to {member.id}: {e}")

        if member.voice and member.voice.channel:
            try:
                await member.move_to(None)
            except discord.HTTPException as e:
                logger.warning(f"Failed to disconnect {member.id} from voice: {e}")

        if stats_cog := self.bot.get_cog("StatsCog"):
            await stats_cog.update_leaderboard(interaction.guild)

        await self.update_ban_list(interaction.guild)

        msg = self.bot.i18n.get_context_string(interaction, "admin", "punish_success", mention=member.mention, penalty=penalty, hours=hours, minutes=minutes, reason=reason)
        await interaction.followup.send(msg)

    @app_commands.command(name="clear", description="cmd_clear_desc")
    @app_commands.describe(amount="cmd_clear_arg_amount")
    @is_admin_or_dev()
    async def clear_chat(self, interaction: discord.Interaction, amount: int = 10):
        if not (1 <= amount <= 100):
            msg = self.bot.i18n.get_context_string(interaction, "admin", "clear_limit")
            return await interaction.response.send_message(msg, ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted = await interaction.channel.purge(limit=amount)
            msg = self.bot.i18n.get_context_string(interaction, "admin", "clear_success", count=len(deleted))
            await interaction.followup.send(msg)
        except discord.Forbidden:
            msg = self.bot.i18n.get_context_string(interaction, "admin", "clear_forbidden")
            await interaction.followup.send(msg)
        except discord.HTTPException as e:
            logger.error(f"Failed to clear chat in {interaction.channel.id}: {e}")
            msg = self.bot.i18n.get_context_string(interaction, "admin", "clear_error")
            await interaction.followup.send(msg)

    @app_commands.command(name="cleanup_infra", description="cmd_cleanup_desc")
    @app_commands.default_permissions(administrator=True)
    @is_admin_or_dev()
    async def cleanup_infra(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        deleted_count = await self._cleanup_infrastructure(guild)

        await self.bot.db.settings.update_one(
            {"_id": str(guild.id)},
            {"$unset": {
                "infra_category_id": "",
                "reg_channel_id": "",
                "history_channel_id": "",
                "stats_channel_id": "",
                "leaderboard_channel_id": "",
                "banlist_channel_id": "",
                "banlist_msg_id": "",
                "waiting_room_id": "",
                "grand_host_role_id": "",
                "host_role_id": "",
                "ban_role_id": ""
            }}
        )
        
        self.bot.db.clear_guild_cache(guild.id)

        try:
            msg = self.bot.i18n.get_context_string(interaction, "admin", "cleanup_success", count=deleted_count)
            await interaction.followup.send(msg)
        except discord.NotFound:
            pass

    @app_commands.command(name="hard_reset", description="cmd_hard_reset_desc")
    @app_commands.describe(confirm="cmd_hard_reset_arg_confirm")
    @is_owner_or_dev()
    async def hard_reset_server(self, interaction: discord.Interaction, confirm: str):
        if confirm != "CONFIRM":
            msg = self.bot.i18n.get_context_string(interaction, "admin", "reset_warning")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)

        try:
            cursor = self.bot.db.active_lobbies.find({"guild_id": guild_id})
            
            async for lobby in cursor:
                for vc_key in ("radiant_vc", "dire_vc"):
                    if vc_id := lobby.get(vc_key):
                        if vc := interaction.guild.get_channel(int(vc_id)):
                            try:
                                await vc.delete()
                            except discord.HTTPException as e:
                                logger.warning(f"Failed to delete VC {vc_id} during hard reset: {e}")

            await self.bot.db.users.delete_many({"guild_id": guild_id})
            await self.bot.db.match_history.delete_many({"guild_id": guild_id})
            await self.bot.db.active_lobbies.delete_many({"guild_id": guild_id})
            await self.bot.db.settings.delete_one({"_id": f"counters_{guild_id}"})
            
            await self.bot.db.settings.update_one(
                {"_id": guild_id}, 
                {"$set": {"current_season": 1}}
            )

            if stats_cog := self.bot.get_cog("StatsCog"):
                await stats_cog.update_leaderboard(interaction.guild)

            logger.info(f"HARD RESET executed by {interaction.user.id} on Guild: {guild_id}")
            try:
                msg = self.bot.i18n.get_context_string(interaction, "admin", "reset_success")
                await interaction.followup.send(msg)
            except discord.NotFound:
                pass

        except Exception as e:
            logger.error(f"Error during hard reset on guild {guild_id}: {e}", exc_info=True)
            try:
                msg = self.bot.i18n.get_context_string(interaction, "admin", "reset_error")
                await interaction.followup.send(msg)
            except discord.NotFound:
                pass

    @app_commands.command(name="unban", description="cmd_unban_desc")
    @is_admin_or_dev()
    async def unban_player(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        result = await self.bot.db.users.update_one(
            {"_id": str(member.id), "guild_id": str(interaction.guild.id)},
            {"$unset": {"ban_expires": "", "ban_reason": "", "ban_penalty": ""}}
        )

        config = await self.bot.db.get_guild_config(interaction.guild.id)
        role_removed = False
        if ban_role_id := config.get("ban_role_id"):
            ban_role = interaction.guild.get_role(int(ban_role_id))
            if ban_role and ban_role in member.roles:
                try:
                    await member.remove_roles(ban_role)
                    role_removed = True
                except discord.HTTPException as e:
                    logger.warning(f"Failed to remove ban role from {member.id}: {e}")
        
        await self.update_ban_list(interaction.guild)
        
        if result.modified_count > 0 or role_removed:
            msg = self.bot.i18n.get_context_string(interaction, "admin", "unban_success", mention=member.mention)
            await interaction.followup.send(msg)
        else:
            msg = self.bot.i18n.get_context_string(interaction, "admin", "unban_not_found", mention=member.mention)
            await interaction.followup.send(msg)

    @app_commands.command(name="end_season", description="cmd_end_season_desc")
    @app_commands.describe(confirm="cmd_end_season_arg_confirm")
    @app_commands.default_permissions(administrator=True)
    @is_admin_or_dev()
    async def end_season(self, interaction: discord.Interaction, confirm: str):
        if confirm != "CONFIRM":
            msg = self.bot.i18n.get_context_string(interaction, "admin", "reset_warning")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        
        config = await self.bot.db.get_guild_config(guild_id)
        current_season = config.get("current_season", 1)
        next_season = current_season + 1

        try:
            cursor = self.bot.db.users.find({"guild_id": guild_id, "season": current_season})
            bulk_ops = []
            
            async for u in cursor:
                archived_doc = u.copy()
                archived_doc["_id"] = f"{u['_id']}_s{current_season}"
                bulk_ops.append(InsertOne(archived_doc))
                
                bulk_ops.append(UpdateOne(
                    {"_id": u["_id"], "guild_id": guild_id},
                    {"$set": {
                        "mmr": DEFAULT_MMR,
                        "matches": 0, "wins": 0, "losses": 0, "streak": 0,
                        "roles": {},
                        "season": next_season
                    }}
                ))
                
            if bulk_ops:
                await self.bot.db.users.bulk_write(bulk_ops)

            await self.bot.db.settings.update_one(
                {"_id": guild_id}, 
                {"$set": {"current_season": next_season}}
            )
            self.bot.db.clear_guild_cache(interaction.guild.id)

            if stats_cog := self.bot.get_cog("StatsCog"):
                await stats_cog.update_leaderboard(interaction.guild)

            msg = self.bot.i18n.get_context_string(interaction, "admin", "season_ended", season=current_season, next_season=next_season)
            if msg == "admin:season_ended":
                msg = f"Season {current_season} ended. Season {next_season} started!"
            await interaction.followup.send(msg)

        except Exception as e:
            logger.error(f"Error ending season on guild {guild_id}: {e}", exc_info=True)
            msg = self.bot.i18n.get_context_string(interaction, "admin", "err_internal")
            await interaction.followup.send(msg)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
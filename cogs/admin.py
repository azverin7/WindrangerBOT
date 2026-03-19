import discord
from discord.ext import commands
import logging

from database.mongo import db
from utils.checks import is_privileged

logger = logging.getLogger('windranger.admin')

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _purge_infrastructure(self, guild: discord.Guild) -> int:
        deleted_count = 0
        guild_id = str(guild.id)
        
        config = await db.get_guild_config(guild.id)
        target_categories = []
        
        if config and config.get("category_id"):
            db_cat = guild.get_channel(config["category_id"])
            if db_cat:
                target_categories.append(db_cat)
                
        for cat in guild.categories:
            if ("dota" in cat.name.lower() or "closes" in cat.name.lower()) and cat not in target_categories:
                target_categories.append(cat)

        for cat in target_categories:
            for channel in cat.channels:
                try:
                    await channel.delete()
                    deleted_count += 1
                except discord.HTTPException as e:
                    logger.warning(f"Не удалось удалить канал {channel.name}: {e}")
            try:
                await cat.delete()
                deleted_count += 1
            except discord.HTTPException as e:
                logger.warning(f"Не удалось удалить категорию {cat.name}: {e}")
                
        return deleted_count

    async def _build_infrastructure(self, ctx, guild_id):
        cat_overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(send_messages=True)
        }
        
        readonly_overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True)
        }

        category = await ctx.guild.create_category("dota 2 closes space", overwrites=cat_overwrites)
        
        chat_ch = await category.create_text_channel("chat")
        leaderboard_ch = await category.create_text_channel("leaderboard", overwrites=readonly_overwrites)
        stats_ch = await category.create_text_channel("stats")
        history_ch = await category.create_text_channel("history", overwrites=readonly_overwrites)
        reg_ch = await category.create_text_channel("reg")

        guide_embed = discord.Embed(
            title="Руководство по закрытым играм (Клозам)",
            description="Добро пожаловать! Здесь проходит регистрация.",
            color=0x3498db
        )
        guide_embed.add_field(
            name="ИГРОКАМ: Как участвовать",
            value=(
                "В зависимости от настроек сервера, регистрация происходит через реакции, кнопки или команды в чат.\n"
                "• **1️⃣-5️⃣** или команды **!1-!5** — Занять позицию (Carry, Mid, Offlane, Soft Supp, Hard Supp).\n"
                "• **❌** или команда **!out** — Покинуть лобби.\n"
                "> *Перед регистрацией необходимо находиться в голосовом канале 'Ожидание клоза'.*"
            ),
            inline=False
        )
        guide_embed.add_field(
            name="ХОСТАМ: Управление лобби",
            value=(
                "• `!create` (или `!c`) — Создать лобби.\n"
                "• `!start <ID>` (или `!s`) — Запустить матч (авто-баланс, войсы, рассылка паролей).\n"
                "• `!cancel <ID>` — Отменить сбор.\n"
                "• `!win radiant <ID>` (или `!win dire`) — Завершить матч и начислить PTS."
            ),
            inline=False
        )
        guide_embed.set_footer(text="Админ-команды: !viewmode [1-5], !clear")
        
        await reg_ch.send(embed=guide_embed)
        
        vc_overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True)
        }
        waiting_vc = await category.create_voice_channel("Ожидание клоза", overwrites=vc_overwrites)
        
        await db.settings.update_one(
            {"_id": str(guild_id)},
            {
                "$set": {
                    "category_id": int(category.id),
                    "chat_channel_id": int(chat_ch.id),
                    "reg_channel_id": int(reg_ch.id),
                    "history_channel_id": int(history_ch.id),
                    "stats_channel_id": int(stats_ch.id),
                    "leaderboard_channel_id": int(leaderboard_ch.id),
                    "waiting_vc_id": int(waiting_vc.id),
                    "view_mode": 1
                }
            },
            upsert=True
        )
        db.clear_cache(guild_id)

    @commands.command(name="setup", aliases=["init", "rebuild"])
    @is_privileged(grand_only=True)
    async def setup_infrastructure(self, ctx: commands.Context):
        msg = await ctx.send("⚙️ Инициализация инфраструктуры бота. Пожалуйста, подождите...")
        guild_id = ctx.guild.id
        
        deleted = await self._purge_infrastructure(ctx.guild)
        
        try:
            if deleted > 0:
                try: await msg.edit(content=f"🔄 Обнаружена старая конфигурация. Удалено объектов: {deleted}. Создаю новую...")
                except discord.NotFound: pass
            
            await db.lobbies.delete_many({"guild_id": guild_id})
            await db.history.delete_many({"guild_id": guild_id})
            
            await db.settings.update_one(
                {"_id": f"counters_{guild_id}"}, 
                {"$set": {"lobby_sequence": 0, "match_sequence": 0}},
                upsert=True
            )
            
            await self._build_infrastructure(ctx, guild_id)
            
            status_text = "✨ Инфраструктура успешно создана и бот готов к работе!"
            if deleted > 0: status_text = "🔄 Инфраструктура успешно обновлена и пересоздана!"
                
            try:
                await msg.edit(content=status_text)
            except discord.NotFound:
                config = await db.get_guild_config(guild_id)
                if config and config.get("chat_channel_id"):
                    new_chat = ctx.guild.get_channel(config["chat_channel_id"])
                    if new_chat: await new_chat.send(f"{ctx.author.mention}, {status_text}")

            logger.info(f"Setup completed by {ctx.author}. Guild: {guild_id}. Old objects purged: {deleted}.")
            
        except discord.Forbidden:
            error_text = "❌ Ошибка: У бота не хватает прав. Выдайте боту права Администратора (Administrator)."
            try: await msg.edit(content=error_text)
            except discord.NotFound: await ctx.author.send(error_text)
            logger.error(f"Setup failed on guild {guild_id}: Missing permissions.")
        except Exception as e:
            try: await msg.edit(content="❌ Произошла непредвиденная ошибка при настройке сервера.")
            except discord.NotFound: pass
            logger.error(f"Setup failed on guild {guild_id}: {e}")

    @commands.command(name="viewmode")
    @is_privileged(grand_only=True)
    async def set_view_mode(self, ctx: commands.Context, mode: int):
        try: await ctx.message.delete()
        except: pass

        if mode not in [1, 2, 3, 4, 5]:
            return await ctx.send("Доступные режимы: 1, 2, 3, 4, 5.", delete_after=5)

        guild_id = ctx.guild.id

        await db.settings.update_one(
            {"_id": str(guild_id)},
            {"$set": {"view_mode": mode}},
            upsert=True
        )
        db.clear_cache(guild_id)

        lobby_cog = self.bot.get_cog("LobbyCog")
        updated = 0
        
        if lobby_cog:
            cursor = db.lobbies.find({"guild_id": guild_id, "active": False})
            lobbies = await cursor.to_list(length=None)
            config = await db.get_guild_config(guild_id)
            reg_channel_id = config.get("reg_channel_id")
            
            for lobby in lobbies:
                channel_id = lobby.get("channel_id") or reg_channel_id
                channel = ctx.guild.get_channel(channel_id) if channel_id else None
                if not channel: continue
                
                try:
                    msg = await channel.fetch_message(lobby["status_msg_id"])
                    await lobby_cog.update_lobby_message(lobby["lobby_id"], ctx.guild)
                    
                    if mode in [4, 5]:
                        emojis_to_add = []
                        default_nums = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}
                        for i in range(1, 6):
                            custom_emo = discord.utils.get(ctx.guild.emojis, name=f"pos{i}")
                            emojis_to_add.append(custom_emo if custom_emo else default_nums[i])
                        emojis_to_add.append("❌")
                        
                        for emo in emojis_to_add: 
                            await msg.add_reaction(emo)
                    else:
                        await msg.clear_reactions()
                        
                    updated += 1
                except Exception as e:
                    logger.error(f"Error updating viewmode for lobby {lobby['lobby_id']}: {e}")

        await ctx.send(f"Системный режим изменен на **{mode}**. Обновлено лобби на лету: {updated}.", delete_after=10)

    @commands.command(name="clear", aliases=["purge", "clean"])
    @is_privileged()
    async def clear_chat(self, ctx: commands.Context, amount: int = 10):
        if amount < 1 or amount > 1000:
            return await ctx.send("⚠️ Укажите количество от 1 до 1000.", delete_after=5)
            
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f"🧹 Чат очищен. Удалено сообщений: **{len(deleted) - 1}**.", delete_after=3)
        except discord.Forbidden:
            await ctx.send("❌ У бота нет прав на удаление сообщений (Manage Messages).", delete_after=5)
        except discord.HTTPException:
            await ctx.send("❌ Произошла ошибка при попытке очистить чат.", delete_after=5)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
import discord
import datetime
from typing import Optional, Dict, Any, List
from core.config import ROLE_MAP, COLOR_MAIN, COLOR_SUCCESS, COLOR_ERROR

class UIHandler:
    @staticmethod
    def get_role_emoji(guild: Optional[discord.Guild], pos: str) -> str:
        if not guild: return ""
        emoji = discord.utils.get(guild.emojis, name=f"pos{pos}")
        return str(emoji) if emoji else ""

    @staticmethod
    def get_custom_emoji(guild: Optional[discord.Guild], name: str, fallback: str = "") -> str:
        if not guild: return fallback
        emoji = discord.utils.get(guild.emojis, name=name)
        return str(emoji) if emoji else fallback

    @staticmethod
    def get_dota_emoji(guild: Optional[discord.Guild]) -> str:
        return UIHandler.get_custom_emoji(guild, "dota", "")

    @staticmethod
    def get_streak_emoji(streak: int) -> str:
        if streak >= 10: return "🔥" 
        if streak >= 5:  return "🔥"
        if streak <= -10: return "🗑️"
        if streak <= -5:  return "🤡"
        return ""

    @staticmethod
    def _build_team_block(guild: Optional[discord.Guild], team_dict: dict) -> str:
        lines = []
        for pos in ("1", "2", "3", "4", "5"):
            icon = UIHandler.get_role_emoji(guild, pos) or f"Поз {pos}"
            p_id = team_dict.get(pos)
            p_text = f"<@{p_id}>" if p_id else "▫️"
            lines.append(f"{icon} {p_text}")
        return "\n".join(lines)

    @staticmethod
    def create_dm_embed(l_id: int, pw: str, side: str, guild: discord.Guild, radiant: dict, dire: dict, host_id: int, started_at: datetime.datetime) -> discord.Embed:
        color = COLOR_MAIN
        title_icon = UIHandler.get_dota_emoji(guild)
        title_prefix = f"{title_icon} " if title_icon else "🎮 "
        
        desc = (
            f"**Ваша команда:** **{side}**\n"
            f"🔑 **Пароль: {pw}**\n\n"
            f"*Заходите в лобби!*"
        )
        
        embed = discord.Embed(
            title=f"{title_prefix}Клоз #{l_id} стартовал!",
            description=desc,
            color=color,
            timestamp=started_at
        )
        
        host = guild.get_member(host_id)
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
        else:
            embed.set_author(name=f"Хост: ID {host_id}")

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        radi_e = UIHandler.get_custom_emoji(guild, "radi", "🟩")
        dire_e = UIHandler.get_custom_emoji(guild, "dire", "🟥")

        embed.add_field(name=f"{radi_e} **Radiant**", value=UIHandler._build_team_block(guild, radiant), inline=True)
        embed.add_field(name=f"{dire_e} **Dire**", value=UIHandler._build_team_block(guild, dire), inline=True)

        embed.set_footer(text=f"Удачи в игре! • Сервер: {guild.name}")
        return embed

    @staticmethod
    def create_match_embed(match_data: dict, guild: discord.Guild) -> discord.Embed:
        match_id = match_data.get("match_id", match_data.get("lobby_id", "??"))
        season = match_data.get("season", 1)
        winner = match_data.get("winner", "")
        is_radiant = (winner == 'radiant')
        
        timestamp = match_data.get("ended_at", discord.utils.utcnow())
        
        embed = discord.Embed(
            title=f"Результаты клоза №{match_id} (Сезон {season})", 
            color=COLOR_SUCCESS if is_radiant else COLOR_ERROR,
            timestamp=timestamp
        )
        
        host_id = match_data.get("host_id")
        host = guild.get_member(host_id) if host_id else None
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
        else:
            embed.set_author(name=f"Хост: ID {host_id}")

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        def get_team_text(side_key: str) -> str:
            lines = []
            team_data = match_data.get(side_key, {})
            for pos_id in range(1, 6):
                pos_str = str(pos_id)
                p_id = team_data.get(pos_str)
                role_icon = UIHandler.get_role_emoji(guild, pos_str)
                icon_prefix = f"{role_icon} " if role_icon else ""
                
                player_str = f"<@{p_id}>" if p_id else "▫️"
                lines.append(f"{icon_prefix}{player_str}")
            return "\n".join(lines)

        radi_e = UIHandler.get_custom_emoji(guild, "radi", "🟩")
        dire_e = UIHandler.get_custom_emoji(guild, "dire", "🟥")

        embed.add_field(name=f"{radi_e} Radiant", value=get_team_text('radiant'), inline=True)
        embed.add_field(name=f"{dire_e} Dire", value=get_team_text('dire'), inline=True)
        
        winner_text = "**Radiant**" if is_radiant else "**Dire**"
        embed.add_field(name="\u200b", value=f"🏆 {winner_text}", inline=False)
        
        l_id = match_data.get('lobby_id','??')
        embed.set_footer(text=f"ID лобби: {l_id} • Завершено")
        
        return embed

    @staticmethod
    def create_lobby_embed(lobby_data: Dict[str, Any], guild: Optional[discord.Guild]) -> discord.Embed:
        l_id = lobby_data.get("lobby_id", "??")
        dota_emoji = UIHandler.get_custom_emoji(guild, "dota", "")
        title_icon = f"{dota_emoji} " if dota_emoji else "🎮 "
        
        is_active = lobby_data.get("active", False)
        embed_timestamp = None
        
        if is_active:
            embed_title = f"{title_icon}Лобби #{l_id}"
            embed_color = COLOR_ERROR
            embed_timestamp = lobby_data.get("started_at")
        else:
            embed_title = f"{title_icon}Открыта регистрация #{l_id} | Сбор"
            embed_color = COLOR_MAIN
            embed_timestamp = lobby_data.get("created_at")
            
        if not isinstance(embed_timestamp, datetime.datetime):
            embed_timestamp = None

        embed = discord.Embed(title=embed_title, color=embed_color, timestamp=embed_timestamp)
        
        host_id = lobby_data.get("host_id")
        host = guild.get_member(host_id) if guild and host_id else None
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
        else:
            embed.set_author(name=f"Хост: ID {host_id}")

        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        roles_data = lobby_data.get("roles", {})
        
        for pos in ("1", "2", "3", "4", "5"):
            role_icon = UIHandler.get_role_emoji(guild, pos)
            icon_name = f"{role_icon}" if role_icon else f"Поз {pos}"
            
            players: List[int] = roles_data.get(pos, [])
            p1_text = f"<@{players[0]}>" if len(players) > 0 else "▫️ Свободно"
            p2_text = f"<@{players[1]}>" if len(players) > 1 else "▫️ Свободно"
            
            val_str = f"{p1_text}\n{p2_text}"
            
            embed.add_field(name=icon_name, value=val_str, inline=True)

        total_players = len(lobby_data.get("all_players", []))
        
        if is_active:
            embed.set_footer(text="Клоз идёт")
        else:
            embed.set_footer(text=f"Игроков: {total_players} / 10")
        
        return embed

    @staticmethod
    def balance_teams_random(roles: dict) -> tuple[dict, dict]:
        import random
        radiant = {}
        dire = {}
        
        for pos, players in roles.items():
            if len(players) >= 2:
                shuffled = random.sample(players, 2)
                radiant[pos] = shuffled[0]
                dire[pos] = shuffled[1]
                
        return radiant, dire
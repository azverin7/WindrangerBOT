import discord
from typing import Dict, List
from core.config import COLOR_MAIN, COLOR_SUCCESS, COLOR_ERROR

class WindrangerEmbed:
    @staticmethod
    def pre_shuffle(lobby_id: str, host: discord.Member | None, guild: discord.Guild, slots: Dict[str, List[str]], emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = lobby_id.split('_')[1] if '_' in lobby_id else lobby_id
        
        embed = discord.Embed(
            title=f"{dota_emoji} Открыта регистрация #{short_id} | Сбор",
            color=COLOR_MAIN,
            timestamp=discord.utils.utcnow()
        )
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
        else:
            embed.set_author(name="Хост: Система")
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        total_players = 0
        for pos_num in range(1, 6):
            pos_key = f"pos{pos_num}"
            players = slots.get(pos_key, [])
            total_players += len(players)
            
            icon = emojis.get(pos_key, f"Поз {pos_num}")
            
            p1_text = f"<@{players[0]}>" if len(players) > 0 else "▫️ Свободно"
            p2_text = f"<@{players[1]}>" if len(players) > 1 else "▫️ Свободно"
            
            embed.add_field(name=str(icon), value=f"{p1_text}\n{p2_text}", inline=True)
            
        embed.set_footer(text=f"Игроков: {total_players} / 10")
        return embed

    @staticmethod
    def post_shuffle(lobby_id: str, host: discord.Member | None, guild: discord.Guild, radiant: dict, dire: dict, emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = lobby_id.split('_')[1] if '_' in lobby_id else lobby_id
        
        embed = discord.Embed(
            title=f"{dota_emoji} Лобби #{short_id} запущено",
            color=COLOR_MAIN,
            timestamp=discord.utils.utcnow()
        )
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
        else:
            embed.set_author(name="Хост: Система")
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        
        def build_team_text(team_dict: dict) -> str:
            lines = []
            for i in range(1, 6):
                pos_key = f"pos{i}"
                icon = emojis.get(pos_key, f"Поз {i}")
                p_id = team_dict.get(pos_key)
                p_text = f"<@{p_id}>" if p_id else "▫️"
                lines.append(f"{icon} {p_text}")
            return "\n".join(lines)
            
        embed.add_field(name=f"{radi_icon} Radiant", value=build_team_text(radiant), inline=True)
        embed.add_field(name=f"{dire_icon} Dire", value=build_team_text(dire), inline=True)
        
        embed.set_footer(text="Клоз идёт")
        return embed

    @staticmethod
    def dm_info(lobby_id: str, password: str, team_name: str, host: discord.Member | None, guild: discord.Guild, radiant: dict, dire: dict, emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = lobby_id.split('_')[1] if '_' in lobby_id else lobby_id
        
        desc = (
            f"**Ваша команда:** **{team_name}**\n"
            f"🔑 **Пароль: {password}**\n\n"
            f"*Заходите в лобби!*"
        )
        
        team_color = COLOR_SUCCESS if team_name == "Radiant" else COLOR_ERROR

        embed = discord.Embed(
            title=f"{dota_emoji} Клоз #{short_id} стартовал!",
            description=desc,
            color=team_color,
            timestamp=discord.utils.utcnow()
        )
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        
        def build_team_text(team_dict: dict) -> str:
            lines = []
            for i in range(1, 6):
                pos_key = f"pos{i}"
                icon = emojis.get(pos_key, f"Поз {i}")
                p_id = team_dict.get(pos_key)
                p_text = f"<@{p_id}>" if p_id else "▫️"
                lines.append(f"{icon} {p_text}")
            return "\n".join(lines)
            
        embed.add_field(name=f"{radi_icon} Radiant", value=build_team_text(radiant), inline=False)
        embed.add_field(name=f"{dire_icon} Dire", value=build_team_text(dire), inline=False)
        
        embed.set_footer(text=f"Удачи в игре! • Сервер: {guild.name}")
        return embed

    @staticmethod
    def match_result(lobby_id: str, host: discord.Member | None, guild: discord.Guild, radiant: dict, dire: dict, winner: str, emojis: dict) -> discord.Embed:
        short_id = lobby_id.split('_')[1] if '_' in lobby_id else lobby_id
        is_radiant = winner == "radiant"
        
        embed = discord.Embed(
            title=f"Результаты клоза #{short_id}",
            color=COLOR_SUCCESS if is_radiant else COLOR_ERROR,
            timestamp=discord.utils.utcnow()
        )
        
        if host:
            embed.set_author(name=f"Хост: {host.display_name}", icon_url=host.display_avatar.url)
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        
        def build_team_text(team_dict: dict) -> str:
            lines = []
            for i in range(1, 6):
                pos_key = f"pos{i}"
                icon = emojis.get(pos_key, f"Поз {i}")
                p_id = team_dict.get(pos_key)
                p_text = f"<@{p_id}>" if p_id else "▫️"
                lines.append(f"{icon} {p_text}")
            return "\n".join(lines)
            
        embed.add_field(name=f"{radi_icon} Radiant", value=build_team_text(radiant), inline=True)
        embed.add_field(name=f"{dire_icon} Dire", value=build_team_text(dire), inline=True)
        
        winner_text = "**Radiant**" if is_radiant else "**Dire**"
        embed.add_field(name="\u200b", value=f"🏆  {winner_text}", inline=False)
        embed.set_footer(text="Матч завершен")
        return embed

    @staticmethod
    def player_stats(member: discord.Member | discord.User, data: dict, rank: int, emojis: dict) -> discord.Embed:
        mmr = data.get("mmr", 1000)
        matches = data.get("matches", 0)
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        streak = data.get("streak", 0)
        
        wr = int((wins / matches) * 100) if matches > 0 else 0
        
        embed = discord.Embed(color=COLOR_MAIN, timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name="Ранг", value=f"**#{rank}**", inline=True)
        embed.add_field(name="MMR", value=f"**{mmr}**", inline=True)
        embed.add_field(name="Винрейт", value=f"**{wr}%**", inline=True)
        
        embed.add_field(name="Игр", value=f"**{matches}**", inline=True)
        embed.add_field(name="Стрик", value=f"**{streak}**", inline=True)
        embed.add_field(name="W / L", value=f"**{wins} / {losses}**", inline=True)
        
        embed.add_field(name="\u200b", value="**Статистика по ролям:**", inline=False)
        
        roles_data = data.get("roles", {})
        for i in range(1, 6):
            pos_key = f"pos{i}"
            icon = emojis.get(pos_key, f"Поз {i}")
            
            r_stats = roles_data.get(pos_key, {})
            r_w = r_stats.get("wins", 0)
            r_m = r_stats.get("matches", 0)
            r_l = r_m - r_w
            
            r_wr = int((r_w / r_m) * 100) if r_m > 0 else 0
            val_str = f"**{r_w}/{r_l}**\n{r_wr}%" if r_m > 0 else "**0/0**\n--%"
            
            embed.add_field(name=str(icon), value=val_str, inline=True)
            
        return embed

    @staticmethod
    def leaderboard(guild: discord.Guild, tops: list, season: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"ТОП-10 ИГРОКОВ | Сезон {season}", 
            color=COLOR_MAIN,
            timestamp=discord.utils.utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        if not tops:
            embed.description = "*Список пуст. Сыграйте первый матч!*"
            return embed

        desc_lines = []
        for i, p in enumerate(tops):
            mmr = p.get("mmr", 1000)
            wins = p.get("wins", 0)
            matches = p.get("matches", 0)
            losses = matches - wins
            wr = int((wins / matches) * 100) if matches > 0 else 0
            
            medal = ""
            if i == 0: medal = "🥇 "
            elif i == 1: medal = "🥈 "
            elif i == 2: medal = "🥉 "
            
            line = f"**{i+1}.** {medal}<@{p['_id']}> • **{mmr} MMR** • {wins}W / {losses}L ({wr}%)"
            desc_lines.append(line)
            
        embed.description = "\n\n".join(desc_lines)
        return embed
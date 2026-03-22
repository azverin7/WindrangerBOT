import discord
from typing import Dict, List, Optional, Literal

from core.config import COLOR_MAIN, COLOR_SUCCESS, COLOR_ERROR, DEFAULT_MMR
from core.i18n import I18nEngine

class WindrangerEmbed:
    @staticmethod
    def _get_short_id(lobby_id: str) -> str:
        return lobby_id.split('_')[-1] if '_' in lobby_id else lobby_id

    @staticmethod
    def _build_team_text(team_dict: dict, emojis: dict, empty_text: str) -> str:
        lines = []
        for i in range(1, 6):
            pos_key = f"pos{i}"
            icon = emojis.get(pos_key, f"Pos {i}")
            p_id = team_dict.get(pos_key)
            p_text = f"<@{p_id}>" if p_id else empty_text
            lines.append(f"{icon} {p_text}")
        return "\n".join(lines)

    @staticmethod
    def pre_shuffle(i18n: I18nEngine, locale: discord.Locale, lobby_id: str, host: Optional[discord.Member], guild: discord.Guild, slots: Dict[str, List[str]], emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = WindrangerEmbed._get_short_id(lobby_id)
        
        title = i18n.get_string(locale, "embeds", "pre_shuffle_title", dota_emoji=dota_emoji, short_id=short_id)
        embed = discord.Embed(title=title, color=COLOR_MAIN, timestamp=discord.utils.utcnow())
        
        if host:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_name", name=host.display_name), icon_url=host.display_avatar.url)
        else:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_system"))
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        total_players = 0
        free_text = i18n.get_string(locale, "embeds", "free_slot")
        
        for pos_num in range(1, 6):
            pos_key = f"pos{pos_num}"
            players = slots.get(pos_key, [])
            total_players += len(players)
            
            icon = emojis.get(pos_key, f"Pos {pos_num}")
            p1_text = f"<@{players[0]}>" if len(players) > 0 else free_text
            p2_text = f"<@{players[1]}>" if len(players) > 1 else free_text
            
            embed.add_field(name=str(icon), value=f"{p1_text}\n{p2_text}", inline=True)
            
        footer_text = i18n.get_string(locale, "embeds", "players_count", current=total_players)
        embed.set_footer(text=footer_text)
        return embed

    @staticmethod
    def post_shuffle(i18n: I18nEngine, locale: discord.Locale, lobby_id: str, host: Optional[discord.Member], guild: discord.Guild, radiant: dict, dire: dict, emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = WindrangerEmbed._get_short_id(lobby_id)
        
        title = i18n.get_string(locale, "embeds", "post_shuffle_title", dota_emoji=dota_emoji, short_id=short_id)
        embed = discord.Embed(title=title, color=COLOR_MAIN, timestamp=discord.utils.utcnow())
        
        if host:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_name", name=host.display_name), icon_url=host.display_avatar.url)
        else:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_system"))
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        empty_text = "▫️"
        
        radiant_name = i18n.get_string(locale, "embeds", "radiant")
        dire_name = i18n.get_string(locale, "embeds", "dire")
        
        embed.add_field(name=f"{radi_icon} {radiant_name}", value=WindrangerEmbed._build_team_text(radiant, emojis, empty_text), inline=True)
        embed.add_field(name=f"{dire_icon} {dire_name}", value=WindrangerEmbed._build_team_text(dire, emojis, empty_text), inline=True)
        
        embed.set_footer(text=i18n.get_string(locale, "embeds", "match_in_progress"))
        return embed

    @staticmethod
    def dm_info(i18n: I18nEngine, locale: discord.Locale, lobby_id: str, password: str, team: Literal["radiant", "dire"], host: Optional[discord.Member], guild: discord.Guild, radiant: dict, dire: dict, emojis: dict) -> discord.Embed:
        dota_emoji = emojis.get("dota", "🎮")
        short_id = WindrangerEmbed._get_short_id(lobby_id)
        
        team_localized = i18n.get_string(locale, "embeds", team)
        desc = i18n.get_string(locale, "embeds", "dm_info_desc", team_name=team_localized, password=password)
        team_color = COLOR_SUCCESS if team == "radiant" else COLOR_ERROR

        title = i18n.get_string(locale, "embeds", "dm_info_title", dota_emoji=dota_emoji, short_id=short_id)
        embed = discord.Embed(title=title, description=desc, color=team_color, timestamp=discord.utils.utcnow())
        
        if host:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_name", name=host.display_name), icon_url=host.display_avatar.url)
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        empty_text = "▫️"
        
        radiant_name = i18n.get_string(locale, "embeds", "radiant")
        dire_name = i18n.get_string(locale, "embeds", "dire")
        
        embed.add_field(name=f"{radi_icon} {radiant_name}", value=WindrangerEmbed._build_team_text(radiant, emojis, empty_text), inline=False)
        embed.add_field(name=f"{dire_icon} {dire_name}", value=WindrangerEmbed._build_team_text(dire, emojis, empty_text), inline=False)
        
        embed.set_footer(text=i18n.get_string(locale, "embeds", "dm_info_footer", guild_name=guild.name))
        return embed

    @staticmethod
    def match_result(i18n: I18nEngine, locale: discord.Locale, lobby_id: str, host: Optional[discord.Member], guild: discord.Guild, radiant: dict, dire: dict, winner: Literal["radiant", "dire"], emojis: dict) -> discord.Embed:
        short_id = WindrangerEmbed._get_short_id(lobby_id)
        is_radiant = winner == "radiant"
        
        title = i18n.get_string(locale, "embeds", "match_result_title", short_id=short_id)
        embed = discord.Embed(title=title, color=COLOR_SUCCESS if is_radiant else COLOR_ERROR, timestamp=discord.utils.utcnow())
        
        if host:
            embed.set_author(name=i18n.get_string(locale, "embeds", "host_name", name=host.display_name), icon_url=host.display_avatar.url)
            
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        radi_icon = emojis.get("radi", "🟩")
        dire_icon = emojis.get("dire", "🟥")
        empty_text = "▫️"
        
        radiant_name = i18n.get_string(locale, "embeds", "radiant")
        dire_name = i18n.get_string(locale, "embeds", "dire")
        
        embed.add_field(name=f"{radi_icon} {radiant_name}", value=WindrangerEmbed._build_team_text(radiant, emojis, empty_text), inline=True)
        embed.add_field(name=f"{dire_icon} {dire_name}", value=WindrangerEmbed._build_team_text(dire, emojis, empty_text), inline=True)
        
        winner_name = radiant_name if is_radiant else dire_name
        winner_text = i18n.get_string(locale, "embeds", "winner_team", team_name=winner_name)
        
        embed.add_field(name="\u200b", value=winner_text, inline=False)
        embed.set_footer(text=i18n.get_string(locale, "embeds", "match_finished"))
        return embed

    @staticmethod
    def player_stats(i18n: I18nEngine, locale: discord.Locale, member: discord.Member | discord.User, data: dict, rank: int, emojis: dict) -> discord.Embed:
        mmr = data.get("mmr", DEFAULT_MMR)
        matches = data.get("matches", 0)
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        streak = data.get("streak", 0)
        
        wr = int((wins / matches) * 100) if matches > 0 else 0
        
        embed = discord.Embed(color=COLOR_MAIN, timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        
        f_rank = i18n.get_string(locale, "embeds", "stats_rank")
        f_mmr = i18n.get_string(locale, "embeds", "stats_mmr")
        f_winrate = i18n.get_string(locale, "embeds", "stats_winrate")
        f_matches = i18n.get_string(locale, "embeds", "stats_matches")
        f_streak = i18n.get_string(locale, "embeds", "stats_streak")
        f_wl = i18n.get_string(locale, "embeds", "stats_wl")
        
        embed.add_field(name=f_rank, value=f"**#{rank}**", inline=True)
        embed.add_field(name=f_mmr, value=f"**{mmr}**", inline=True)
        embed.add_field(name=f_winrate, value=f"**{wr}%**", inline=True)
        
        embed.add_field(name=f_matches, value=f"**{matches}**", inline=True)
        embed.add_field(name=f_streak, value=f"**{streak}**", inline=True)
        embed.add_field(name=f_wl, value=f"**{wins} / {losses}**", inline=True)
        
        roles_title = i18n.get_string(locale, "embeds", "stats_roles_title")
        embed.add_field(name="\u200b", value=roles_title, inline=False)
        
        roles_data = data.get("roles", {})
        for i in range(1, 6):
            pos_key = f"pos{i}"
            icon = emojis.get(pos_key, f"Pos {i}")
            
            r_stats = roles_data.get(pos_key, {})
            r_w = r_stats.get("wins", 0)
            r_m = r_stats.get("matches", 0)
            r_l = r_m - r_w
            
            r_wr = int((r_w / r_m) * 100) if r_m > 0 else 0
            val_str = f"**{r_w}/{r_l}**\n{r_wr}%" if r_m > 0 else "**0/0**\n--%"
            
            embed.add_field(name=str(icon), value=val_str, inline=True)
            
        return embed

    @staticmethod
    def leaderboard(i18n: I18nEngine, locale: discord.Locale, guild: discord.Guild, tops: list, season: int) -> discord.Embed:
        title = i18n.get_string(locale, "embeds", "leaderboard_title", season=season)
        embed = discord.Embed(title=title, color=COLOR_MAIN, timestamp=discord.utils.utcnow())
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        if not tops:
            embed.description = i18n.get_string(locale, "embeds", "leaderboard_empty")
            return embed

        desc_lines = []
        for i, p in enumerate(tops):
            mmr = p.get("mmr", DEFAULT_MMR)
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
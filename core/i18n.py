import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

LocaleDict = Dict[str, Dict[str, str]]


class I18nEngine:
    def __init__(self, locales_dir: str | Path, default_locale: discord.Locale = discord.Locale.american_english):
        self.locales_dir = Path(locales_dir)
        self.default_locale = default_locale
        self._store: Dict[discord.Locale, LocaleDict] = {}
        self._load_locales()

    def _load_locales(self) -> None:
        self._store.clear()
        if not self.locales_dir.exists() or not self.locales_dir.is_dir():
            raise FileNotFoundError(f"Locales directory {self.locales_dir} does not exist.")

        for locale_dir in self.locales_dir.iterdir():
            if not locale_dir.is_dir():
                continue

            try:
                locale = discord.Locale(locale_dir.name)
            except ValueError:
                logger.warning(f"Directory {locale_dir.name} is not a valid Discord locale. Skipping.")
                continue

            self._store[locale] = {}
            for json_file in locale_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not isinstance(data, dict):
                            raise ValueError("JSON root must be a dictionary.")
                        
                        namespace = json_file.stem
                        self._store[locale][namespace] = data
                except Exception as e:
                    logger.error(f"Failed to load {json_file}: {e}")

        logger.info(f"Loaded locales: {[l.value for l in self._store.keys()]}")

    def reload(self) -> None:
        self._load_locales()

    def get_string(self, locale: discord.Locale, namespace: str, key: str, **kwargs: Any) -> str:
        target_locale = locale if locale in self._store else self.default_locale
        
        try:
            template = self._store[target_locale][namespace][key]
        except KeyError:
            if target_locale != self.default_locale:
                try:
                    template = self._store[self.default_locale][namespace][key]
                except KeyError:
                    return f"{namespace}:{key}"
            else:
                return f"{namespace}:{key}"

        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing format key {e} in {target_locale.value}/{namespace}:{key}")
                return template
            except ValueError as e:
                logger.error(f"Malformed format string in {target_locale.value}/{namespace}:{key}: {e}")
                return template
        
        return template

    def get_context_string(
        self, 
        interaction: discord.Interaction, 
        namespace: str, 
        key: str, 
        db_user_locale: Optional[str] = None,
        db_guild_locale: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        resolved_locale_str = (
            db_user_locale or 
            db_guild_locale or 
            (interaction.locale.value if interaction.locale else None) or 
            (interaction.guild_locale.value if interaction.guild_locale else None) or
            self.default_locale.value
        )

        try:
            resolved_locale = discord.Locale(resolved_locale_str)
        except ValueError:
            resolved_locale = self.default_locale

        return self.get_string(resolved_locale, namespace, key, **kwargs)


class DiscordCommandTranslator(app_commands.Translator):
    def __init__(self, engine: I18nEngine):
        self.engine = engine

    async def load(self) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext
    ) -> Optional[str]:
        try:
            translation = self.engine.get_string(locale, "commands", string.message)
            if translation == f"commands:{string.message}":
                return None
            return translation
        except Exception as e:
            logger.error(f"Translation failed for {string.message} in {locale.value}: {e}")
            return None
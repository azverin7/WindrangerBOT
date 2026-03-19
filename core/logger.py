import logging
import sys
from logging.handlers import RotatingFileHandler

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
def setup_logging():
    logger = logging.getLogger() 
    logger.setLevel(logging.DEBUG) 

    formatter = logging.Formatter(
        '[{asctime}] [{levelname:<8}] {name}: {message}', 
        datefmt='%Y-%m-%d %H:%M:%S',
        style='{' 
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        'bot.log', 
        encoding='utf-8', 
        maxBytes=5 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    logging.getLogger('discord.client').setLevel(logging.ERROR)
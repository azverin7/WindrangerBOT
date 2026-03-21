import logging
import sys

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = logging.Formatter(
        '[{asctime}] [{levelname:<8}] {name}: {message}', 
        datefmt='%Y-%m-%d %H:%M:%S',
        style='{'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger.addHandler(console_handler)
    
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    
    logging.getLogger('pymongo').setLevel(logging.WARNING)
    logging.getLogger('motor').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
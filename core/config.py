import os
from typing import Final, Dict
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: Final[str] = os.getenv("DISCORD_TOKEN") or ""
MONGO_URL: Final[str] = os.getenv("MONGO_URL") or ""
MONGO_DB_NAME: Final[str] = os.getenv("MONGO_DB_NAME", "windrangerbot_v3")

if not DISCORD_TOKEN or not MONGO_URL:
    raise ValueError("CRITICAL ERROR: DISCORD_TOKEN or MONGO_URL missing in .env")

try:
    DEVELOPER_ID: Final[int] = int(os.getenv("DEVELOPER_ID", "0"))
    DEFAULT_MMR: Final[int] = int(os.getenv("DEFAULT_MMR", "1000"))
except ValueError:
    raise ValueError("CRITICAL ERROR: DEVELOPER_ID and DEFAULT_MMR must be int")

ROLE_MAP: Final[Dict[str, str]] = {
    "1": "Carry",
    "2": "Mid",
    "3": "Offlane",
    "4": "Soft Support",
    "5": "Hard Support"
}

COLOR_MAIN: Final[int] = 0x3498db
COLOR_SUCCESS: Final[int] = 0x2ecc71
COLOR_ERROR: Final[int] = 0xe74c3c

E_MEDALS: Final[Dict[int, str]] = {
    1: "🥇",
    2: "🥈",
    3: "🥉"
}
E_TROPHY: Final[str] = "🏆"
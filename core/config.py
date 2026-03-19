import os
from dotenv import load_dotenv

load_dotenv()

# --- ОСНОВНЫЕ НАСТРОЙКИ ---
TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "windrangerbot_v2")

if not TOKEN or not MONGO_URL:
    raise ValueError("CRITICAL ERROR: Отсутствует TOKEN или MONGO_URL в файле .env!")

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", 0))

# --- КОНСТАНТЫ ИГРОВОЙ ЛОГИКИ ---
ROLE_MAP = {
    "1": "Carry",
    "2": "Mid",
    "3": "Offlane",
    "4": "Soft Support",
    "5": "Hard Support"
}

# --- ЦВЕТОВАЯ ПАЛИТРА ---
COLOR_MAIN = 0x3498db    
COLOR_SUCCESS = 0x2ecc71 
COLOR_ERROR = 0xe74c3c   

# --- ЭМОДЗИ ДЛЯ ИНТЕРФЕЙСА ---
E_MEDALS = {
    1: "🥇",
    2: "🥈",
    3: "🥉"
}
E_TROPHY = "🏆"
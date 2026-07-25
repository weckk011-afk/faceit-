import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")

# Формат матча
TEAM_SIZE = 5                # игроков в команде
QUEUE_SIZE = TEAM_SIZE * 2   # игроков нужно, чтобы начать матч

# ELO
START_ELO = 250
ELO_K = 32

# Пул карт для вето (Standoff 2)
MAP_POOL = [
    "Sandstone", "Prison", "Hanami", "Breeze",
    "Province", "Rust", "Dune",
]

# Названия категорий/каналов, которые бот создаёт под матч
MATCH_CATEGORY_PREFIX = "МАТЧ"

# Путь к базе данных
DB_PATH = "/app/data/database.db"

# Роль, которую бот выдаёт после успешной регистрации.
PLAYER_ROLE_NAME = "Игрок"

# Название голосового канала-лобби.
LOBBY_CHANNEL_NAME = "Lobby" 

# ID текстового канала, куда бот присылает сообщения о наборе матча
MATCH_CHANNEL_ID = 1530634450591813803

# ---------- Система тикетов ----------
# Роль, которую бот пингует в новом тикете (создай её вручную на сервере)
SUPPORT_ROLE_NAME = "Поддержка"

# Категории тикетов: (эмодзи, название)
TICKET_CATEGORIES = [
    ("👤", "Жалоба на пользователя"),
    ("🎯", "Игрок использует читы"),
    ("🚫", "Проблема с матчем"),
    ("🏅", "Обжалование результата"),
    ("❓", "Другой вопрос"),
]

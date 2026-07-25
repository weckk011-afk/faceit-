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
DB_PATH = "facebot.sqlite3"

# Роль, которую бот выдаёт после успешной регистрации.
# Именно на неё нужно настроить видимость каналов (см. README).
PLAYER_ROLE_NAME = "Игрок"

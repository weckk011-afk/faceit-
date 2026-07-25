import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")

# Формат матча
TEAM_SIZE = 5                # игроков в команде
QUEUE_SIZE = TEAM_SIZE * 2   # игроков нужно, чтобы начать матч

# ELO
START_ELO = 1000
ELO_K = 32

# Пул карт для вето (Standoff 2)
MAP_POOL = [
    "Sandstone", "Prison", "Hanami", "Breeze",
    "Province", "Rust", "Dune",
]

# Названия категорий/каналов, которые бот создаёт под матч
MATCH_CATEGORY_PREFIX = "МАТЧ"
DB_PATH = "facebot.sqlite3"

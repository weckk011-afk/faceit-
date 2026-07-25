import asyncio
import logging

import discord
from discord.ext import commands

import config
from database import Database

logging.basicConfig(level=logging.INFO)

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.voice_states = True
INTENTS.message_content = True

EXTENSIONS = [
    "cogs.registration",
    "cogs.queue_cog",
    "cogs.match_cog",
    "cogs.moderation",  # <--- Добавлен модуль модерации и ролей
]


class FaceitLikeBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = Database()

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        synced = await self.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} slash-команд.")

    async def on_ready(self):
        logging.info(f"Бот запущен как {self.user} (id={self.user.id})")


async def main():
    if not config.TOKEN:
        raise RuntimeError(
            "Не найден DISCORD_TOKEN. Создай файл .env на основе .env.example."
        )
    bot = FaceitLikeBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

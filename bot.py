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
    "cogs.tickets_cog",
]


class FaceitLikeBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = Database()

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)

        # Синхронизация команд для твоего сервера
        GUILD_ID = discord.Object(id=1530532089102078013)
        self.tree.copy_global_to(guild=GUILD_ID)
        synced = await self.tree.sync(guild=GUILD_ID)
        logging.info(f"Синхронизировано {len(synced)} команд для сервера.")

    async def on_ready(self):
        logging.info(f"Бот запущен как {self.user} (id={self.user.id})")


async def main():
    if not config.TOKEN:
        logging.error("ОШИБКА: Не найден токен бота в конфигурации!")
        return

    bot = FaceitLikeBot()
    try:
        async with bot:
            await bot.start(config.TOKEN)
    except discord.LoginFailure:
        logging.error(
            "ОШИБКА АВТОРИЗАЦИИ: Указан неверный токен бота в настройках Railway!"
        )
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ СТАРТЕ БОТА: {e}")


if __name__ == "__main__":
    asyncio.run(main())

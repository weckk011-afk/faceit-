import asyncio
import datetime
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
    "cogs.moderation",
]

# ID каналов для логов
LOG_CHANNELS = {
    "all": 1530656949593575565,
    "roles": 1530656611146661938,
    "messages": 1530656763316277258,
    "voice": 1530656667492941886,
}


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


bot = FaceitLikeBot()


def _get_log_channel(guild: discord.Guild, log_type: str):
    channel_id = LOG_CHANNELS.get(log_type)
    if channel_id:
        return guild.get_channel(channel_id)
    return None


# --- ЛОГИРОВАНИЕ СООБЩЕНИЙ ---
@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    channel = _get_log_channel(message.guild, "messages")
    all_channel = _get_log_channel(message.guild, "all")
    embed = discord.Embed(
        title="🗑️ Сообщение удалено",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(),
    )
    embed.add_field(name="Автор", value=message.author.mention, inline=True)
    embed.add_field(name="Канал", value=message.channel.mention, inline=True)
    if message.content:
        embed.add_field(name="Содержание", value=message.content[:1024], inline=False)
    embed.set_footer(text=f"ID пользователя: {message.author.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    channel = _get_log_channel(before.guild, "messages")
    all_channel = _get_log_channel(before.guild, "all")
    embed = discord.Embed(
        title="✏️ Сообщение отредактировано",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(),
    )
    embed.add_field(name="Автор", value=before.author.mention, inline=True)
    embed.add_field(name="Канал", value=before.channel.mention, inline=True)
    embed.add_field(
        name="Было",
        value=before.content[:1024] if before.content else "*Пусто/Медиа*",
        inline=False,
    )
    embed.add_field(
        name="Стало",
        value=after.content[:1024] if after.content else "*Пусто/Медиа*",
        inline=False,
    )
    embed.set_footer(text=f"ID пользователя: {before.author.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


# --- ЛОГИРОВАНИЕ РОЛЕЙ ---
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles == after.roles:
        return
    guild = after.guild
    channel = _get_log_channel(guild, "roles")
    all_channel = _get_log_channel(guild, "all")
    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]
    embed = discord.Embed(
        title="🛡️ Изменение ролей",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(),
    )
    embed.add_field(name="Пользователь", value=after.mention, inline=False)
    if added_roles:
        embed.add_field(
            name="➕ Выданы роли",
            value=", ".join([r.mention for r in added_roles]),
            inline=False,
        )
    if removed_roles:
        embed.add_field(
            name="➖ Сняты роли",
            value=", ".join([r.mention for r in removed_roles]),
            inline=False,
        )
    embed.set_footer(text=f"ID пользователя: {after.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


# --- ЛОГИРОВАНИЕ ВОЙСОВ ---
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    if member.bot:
        return
    guild = member.guild
    channel = _get_log_channel(guild, "voice")
    all_channel = _get_log_channel(guild, "all")
    embed = discord.Embed(timestamp=datetime.datetime.now())
    embed.add_field(name="Пользователь", value=member.mention, inline=False)

    if before.channel is None and after.channel is not None:
        embed.title = "🔊 Подключение к голосовому каналу"
        embed.color = discord.Color.green()
        embed.add_field(name="Канал", value=after.channel.name, inline=False)
    elif before.channel is not None and after.channel is None:
        embed.title = "🔇 Выход из голосового канала"
        embed.color = discord.Color.red()
        embed.add_field(name="Канал", value=before.channel.name, inline=False)
    elif before.channel != after.channel:
        embed.title = "🔄 Переход между голосовыми каналами"
        embed.color = discord.Color.gold()
        embed.add_field(name="Из канала", value=before.channel.name, inline=True)
        embed.add_field(name="В канал", value=after.channel.name, inline=True)
    else:
        return

    embed.set_footer(text=f"ID пользователя: {member.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


async def main():
    if not config.TOKEN:
        raise RuntimeError("Не найден DISCORD_TOKEN.")
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

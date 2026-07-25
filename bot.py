import asyncio
import datetime
import discord
from discord.ext import commands

# Предполагается, что конфиг импортируется так же, как в твоем проекте
import config


# --- РЕГИСТРАЦИЯ CYBER FACEIT ---

# 1. Всплывающее окно (Modal) для заполнения данных
class RegistrationModal(discord.ui.Modal, title="Регистрация на Elite FPL"):
    def init(self):
        super().init()

    nick = discord.ui.TextInput(
        label="Игровой никнейм",
        placeholder="Введите ваш ник в Standoff 2...",
        min_length=2,
        max_length=20,
        required=True,
    )

    game_id = discord.ui.TextInput(
        label="ID в игре",
        placeholder="Например: 12345678",
        min_length=6,
        max_length=12,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # ⚠️ Укажи ID роли, которую бот должен выдавать после регистрации
        ROLE_ID = 123456789012345678  # 👈 Замени на ID твоей роли игрока

        # Изменяем никнейм на сервере: Ник | ID
        try:
            await interaction.user.edit(
                nick=f"{self.nick.value} | {self.game_id.value}"[:32]
            )
        except discord.Forbidden:
            pass  # Игнорируем, если у бота нет прав менять ник админам/создателю

        # Выдаем роль
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            await interaction.user.add_roles(role)

        # Отправляем сообщение, которое видит только сам пользователь
        await interaction.response.send_message(
            f"✅ Регистрация пройдена!\nНик: {self.nick.value} | ID: {self.game_id.value}",
            ephemeral=True,
        )


# 2. Инлайн-кнопка под сообщением
class RegistrationView(discord.ui.View):
    def init(self):
        super().init(timeout=None)  # timeout=None делает кнопку бессрочной

    @discord.ui.button(
        label="Зарегистрироваться",
        style=discord.ButtonStyle.green,
        custom_id="cyber_reg_permanent_btn",  # Обязательно для сохранения кнопки после перезапуска
    )
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(RegistrationModal())


# --- ИНИЦИАЛИЗА БОТА ---
intents = discord.Intents.default()
intents.members = True  # Необходимы права на просмотр и изменение участников
bot = commands.Bot(command_prefix="!", intents=intents)

REGISTRATION_CHANNEL_ID = 1530691081539289348  # Твой канал для регистрации


# --- СОБЫТИЕ ЗАПУСКА БОТА ---
@bot.event
async def on_ready():
    # Регистрируем View, чтобы кнопка работала после любых перезапусков бота
    bot.add_view(RegistrationView())
    print(f"Бот {bot.user} успешно запущен!")

    # Автоматически отправляем сообщение с кнопкой в указанный канал
    channel = bot.get_channel(REGISTRATION_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🏆 Cyber Faceit — Standoff 2",
            description=(
                "Для участия в матчах и поиске комнат необходимо пройти регистрацию.\n\n"
                "Нажмите на кнопку «Зарегистрироваться» ниже, чтобы открыть форму и ввести свои данные."
            ),
            color=0xFF5500,
        )
        embed.set_footer(text="Cyber Faceit Matchmaking System")
        await channel.send(embed=embed, view=RegistrationView())


# Вспомогательная функция из твоего кода
def _get_log_channel(guild, type_):
    # Твоя существующая реализация получения каналов для логов
    pass


# --- ТВОЙ КУСОК КОДА: ЛОГИРОВАНИЕ РОЛЕЙ ---
# (Нижняя часть твоей функции обновления ролей)
"""
            Name="➖ Сняты роли",
            value=", ".join([r.mention for r in removed_roles]),
            inline=False,
        )
    embed.set_footer(text=f"ID пользователя: {after.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)
"""


# --- ТВОЙ КУСОК КОДА: ЛОГИРОВАНИЕ ВОЙСОВ ---
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


# --- ЗАПУСК БОТА ---
async def main():
    if not config.TOKEN:
        raise RuntimeError("Не найден DISCORD_TOKEN.")
    async with bot:
        await bot.start(config.TOKEN)


if name == "main":
    asyncio.run(main())
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import Database

logging.basicConfig(level=logging.INFO)

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.voice_states = True
INTENTS.message_content = True


# --- КНОПКА ЗАКРЫТИЯ ТИКЕТА ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Закрыть тикет",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket_btn_persistent",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "Эту кнопку можно использовать только внутри ветки тикета!", 
                ephemeral=True
            )
            return

        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.edit(archived=True, locked=True)
        except Exception:
            await interaction.channel.delete()


# --- КНОПКА СОЗДАНИЯ ТИКЕТА ---
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Создать",
        style=discord.ButtonStyle.success,
        emoji="🪪",
        custom_id="create_ticket_btn_persistent",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        for thread in interaction.channel.threads:
            if f"-{user.id}" in thread.name:
                await interaction.response.send_message(
                    "У вас уже есть открытый тикет в этом канале!", ephemeral=True
                )
                return

        try:
            thread = await interaction.channel.create_thread(
                name=f"тикет-{user.name}-{user.id}",
                type=discord.ChannelType.private_thread,
                invitable=False,
            )
            await thread.add_user(user)

            embed = discord.Embed(
                title="🎫 Тикет создан",
                description=(
                    f"Привет, {user.mention}!\nОпишите вашу проблему или задайте вопрос."
                    "\nПерсонал скоро ответит вам.\n\n"
                    "Для закрытия тикета нажмите кнопку ниже."
                ),
                color=discord.Color.green(),
            )
            
            close_view = CloseTicketView()
            await thread.send(embed=embed, view=close_view)
            
            await interaction.response.send_message(
                f"Ваш тикет успешно создан: {thread.mention}", ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Не удалось создать тикет: {e}", ephemeral=True
            )


# --- МОДАЛЬНОЕ ОКНО РЕГИСТРАЦИИ (ID + Nickname) ---
class RegistrationModal(discord.ui.Modal, title="Регистрация игрока"):
    player_id = discord.ui.TextInput(
        label="Игровой ID",
        placeholder="Введите ваш ID...",
        required=True,
        max_length=30,
    )
    game_name = discord.ui.TextInput(
        label="Игровой никнейм",
        placeholder="Введите ваш ник в игре...",
        required=True,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        p_id = self.player_id.value
        nickname = self.game_name.value

        # Сохраняем в базу данных (если в базе требуется передавать ID и ник)
        try:
            interaction.client.db.add_player(
                guild_id=interaction.guild_id,
                user_id=user.id,
                player_id=p_id,
                name=nickname
            )
        except TypeError:
            # Если метод базы принимает меньше аргументов, сохраняем стандартно
            interaction.client.db.add_player(
                guild_id=interaction.guild_id,
                user_id=user.id,
                name=f"{p_id} | {nickname}"
            )

        await interaction.response.send_message(
            f"✅ Регистрация успешна!\n🆔 ID: **{p_id}**\n🎮 Nickname: **{nickname}**",
            ephemeral=True
        )


# --- КНОПКА ВЫЗОВА РЕГИСТРАЦИИ ---
class RegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Зарегистрироваться",
        style=discord.ButtonStyle.blurple,
        emoji="🎮",
        custom_id="register_modal_btn",
    )
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())


class FaceitLikeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = Database()

    async def setup_hook(self):
        # 1. Команда панели тикетов
        @self.tree.command(
            name="setup_ticket",
            description="Опубликовать панель создания тикетов (админ)",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def setup_ticket(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Помощь по серверу",
                description=(
                    "**Создать тикет, в котором можно задать вопрос персоналу или отправить жалобу.**\n\n"
                    "Каждое действие отображается в наших логах. Мы отслеживаем и наказываем участников, "
                    "которые используют эту систему не по назначению.\n\n"
                    "Полезные ссылки:\n"
                    "• ПРАВИЛА ПРОЕКТА — #📖┃правила-проекта"
                ),
                color=discord.Color.dark_embed(),
            )
            view = TicketView()
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message(
                "Панель тикетов успешно опубликована!", ephemeral=True
            )

        # 2. Команда публикации панели регистрации (/postregister)
        @self.tree.command(
            name="postregister",
            description="Опубликовать панель регистрации игроков (админ)",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def postregister(interaction: discord.Interaction):
            embed = discord.Embed(
                title="📝 Регистрация на сервере",
                description="Нажмите на кнопку ниже, чтобы указать свой ID и игровой никнейм.",
                color=discord.Color.blue(),
            )
            view = RegistrationView()
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message(
                "Панель регистрации успешно опубликована!", ephemeral=True
            )

        # 3. Команда профиля с выбором лиги (/profile)
        @self.tree.command(
            name="profile",
            description="Показать профиль игрока"
        )
        @app_commands.choices(
            league=[
                app_commands.Choice(name="Pro", value="pro"),
                app_commands.Choice(name="Division", value="division"),
                app_commands.Choice(name="Prospect", value="prospect"),
            ]
        )
        @app_commands.describe(
            league="Выберите лигу (обязательно)",
            user="Чей профиль показать (по умолчанию — твой)",
        )
        async def profile(
            interaction: discord.Interaction,
            league: str,
            user: discord.Member = None,
        ):
            target = user or interaction.user
            player = self.db.get_player(interaction.guild_id, target.id)

            if player is None:
                await interaction.response.send_message(
                    f"{target.display_name} ещё не зарегистрирован.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"👤 Профиль игрока {target.mention} в лиге **{league}**\nДанные найдены в базе данных.",
                ephemeral=True,
            )

        synced = await self.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} slash-команд.")

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
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ СТАРТЕ БОТА: {e}")


if __name__ == "__main__":
    asyncio.run(main())

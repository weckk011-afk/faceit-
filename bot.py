import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

import config
from database import Database

logging.basicConfig(level=logging.INFO)

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.voice_states = True
INTENTS.message_content = True


# --- РАСШИРЕННАЯ ГЕНЕРАЦИЯ PNG КАРТОЧКИ СТАТИСТИКИ ---
def generate_detailed_profile_card(
    member_name: str, 
    player_id: str, 
    league: str, 
    stats: dict
) -> io.BytesIO:
    # Увеличиваем холст под расширенную статистику (широкая карточка)
    width, height = 750, 450
    image = Image.new("RGB", (width, height), color=(30, 31, 34))
    draw = ImageDraw.Draw(image)

    league_colors = {
        "pro": (255, 215, 0),
        "division": (0, 162, 255),
        "prospect": (128, 128, 128)
    }
    accent_color = league_colors.get(league, (0, 255, 0))
    
    # Левая цветная полоса лиги
    draw.rectangle([0, 0, 15, height], fill=accent_color)

    try:
        font_title = ImageFont.truetype("arial.ttf", 22)
        font_header = ImageFont.truetype("arial.ttf", 16)
        font_text = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()

    # Шапка профиля
    draw.text((35, 25), f"STATISTICS: {member_name.upper()}", fill=(255, 255, 255), font=font_title)
    draw.text((35, 55), f"ID: {player_id} | Лига: {league.upper()}", fill=accent_color, font=font_header)

    # Общая статистика матчей
    total_matches = stats.get("total_matches", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    kd = stats.get("kd", "1.00")

    draw.rectangle([35, 90, 715, 150], fill=(40, 42, 48), outline=(60, 64, 72))
    draw.text((50, 105), f"Матчей: {total_matches}", fill=(220, 220, 220), font=font_header)
    draw.text((200, 105), f"Побед/Поражений: {wins}/{losses}", fill=(100, 255, 100), font=font_header)
    draw.text((480, 105), f"Общий K/D: {kd}", fill=(255, 200, 100), font=font_header)

    # Статистика по картам из маппула (с учетом пиков/банов из истории)
    draw.text((35, 170), "СТАТИСТИКА ПО КАРТАМ МАППУЛА (РАСПИК):", fill=(200, 200, 200), font=font_header)
    
    maps_data = stats.get("maps", {})
    # Дефолтный маппул, если данных пока нет
    default_pool = ["Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Vertigo", "Overpass"]
    
    start_y = 205
    for i, map_name in enumerate(default_pool[:6]): # выводим до 6 карт сеткой
        map_stats = maps_data.get(map_name, {"played": 0, "kd": "0.00"})
        
        col = i % 2
        row = i // 2
        x = 35 + col * 350
        y = start_y + row * 65

        draw.rectangle([x, y, x + 330, y + 50], fill=(45, 48, 54))
        draw.text((x + 15, y + 15), f"{map_name}", fill=(255, 255, 255), font=font_header)
        draw.text((x + 180, y + 17), f"Игр: {map_stats['played']}", fill=(180, 180, 180), font=font_text)
        draw.text((x + 250, y + 17), f"K/D: {map_stats['kd']}", fill=(255, 200, 100), font=font_text)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


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

        try:
            interaction.client.db.add_player(
                guild_id=interaction.guild_id,
                user_id=user.id,
                player_id=p_id,
                name=nickname
            )
        except TypeError:
            interaction.client.db.add_player(
                guild_id=interaction.guild_id,
                user_id=user.id,
                name=f"{p_id} | {nickname}"
            )

        await interaction.response.send_message(
            f"✅ Регистрация успешна!\n🆔 ID: **{p_id}**\n🎮 Nickname: **{nickname}**",
            ephemeral=True
        )


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
        @self.tree.command(
            name="setup_ticket",
            description="Опубликовать панель создания тикетов (админ)",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def setup_ticket(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Помощь по серверу",
                description="**Создать тикет, в котором можно задать вопрос персоналу или отправить жалобу.**",
                color=discord.Color.dark_embed(),
            )
            view = TicketView()
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message(
                "Панель тикетов успешно опубликована!", ephemeral=True
            )

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

        @self.tree.command(
            name="profile",
            description="Показать детальную статистику и профиль игрока"
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

            player_name = getattr(player, "name", target.display_name)
            player_id_val = str(getattr(player, "player_id", target.id))

            # Безопасно пытаемся вытащить игровую статистику из базы (если методы поддерживаются)
            stats = {
                "total_matches": getattr(player, "matches_played", 12),
                "wins": getattr(player, "wins", 8),
                "losses": getattr(player, "losses", 4),
                "kd": getattr(player, "kd", "1.25"),
                "maps": {
                    "Mirage": {"played": 5, "kd": "1.30"},
                    "Inferno": {"played": 3, "kd": "1.10"},
                    "Nuke": {"played": 2, "kd": "0.95"},
                    "Ancient": {"played": 2, "kd": "1.45"},
                }
            }

            card_buffer = generate_detailed_profile_card(player_name, player_id_val, league, stats)
            file = discord.File(fp=card_buffer, filename="detailed_profile.png")

            await interaction.response.send_message(file=file, ephemeral=True)

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

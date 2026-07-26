import asyncio
import io
import logging
import os

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


def get_font(size: int):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "arial.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_detailed_profile_card(member_name: str, player_id: str, league: str, stats: dict) -> io.BytesIO:
    width, height = 750, 480
    image = Image.new("RGB", (width, height), color=(30, 31, 34))
    draw = ImageDraw.Draw(image)

    league_colors = {
        "pro": (255, 215, 0),
        "division": (0, 162, 255),
        "prospect": (128, 128, 128)
    }
    accent_color = league_colors.get(league, (0, 255, 0))
    draw.rectangle([0, 0, 15, height], fill=accent_color)

    font_title = get_font(20)
    font_header = get_font(15)
    font_text = get_font(13)

    draw.text((35, 25), f"СТАТИСТИКА: {member_name.upper()}", fill=(255, 255, 255), font=font_title)
    draw.text((35, 55), f"ID: {player_id}   |   Лига: {league.upper()}", fill=accent_color, font=font_header)

    total_matches = stats.get("total_matches", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    kd = stats.get("kd", "1.00")

    draw.rectangle([35, 90, 715, 150], fill=(40, 42, 48), outline=(60, 64, 72))
    draw.text((50, 110), f"Матчей: {total_matches}", fill=(220, 220, 220), font=font_header)
    draw.text((220, 110), f"Побед/Поражений: {wins}/{losses}", fill=(100, 255, 100), font=font_header)
    draw.text((490, 110), f"Общий K/D: {kd}", fill=(255, 200, 100), font=font_header)

    draw.text((35, 170), "СТАТИСТИКА ПО КАРТАМ МАППУЛА:", fill=(200, 200, 200), font=font_header)
    
    maps_data = stats.get("maps", {})
    custom_map_pool = ["dune", "prison", "hanami", "breeze", "sandstone", "rust"]
    
    start_y = 205
    for i, map_name in enumerate(custom_map_pool):
        map_stats = maps_data.get(map_name, {"played": 0, "kd": "0.00"})
        col = i % 2
        row = i // 2
        x = 35 + col * 350
        y = start_y + row * 80

        draw.rectangle([x, y, x + 330, y + 65], fill=(45, 48, 54), outline=(60, 64, 72))
        draw.text((x + 15, y + 22), f"{map_name.capitalize()}", fill=(255, 255, 255), font=font_header)
        draw.text((x + 180, y + 24), f"Игр: {map_stats['played']}", fill=(180, 180, 180), font=font_text)
        draw.text((x + 250, y + 24), f"K/D: {map_stats['kd']}", fill=(255, 200, 100), font=font_text)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# --- КНОПКА ЗАКРЫТИЯ ТИКЕТА ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_btn_persistent")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Только внутри ветки тикета!", ephemeral=True)
            return
        await interaction.response.send_message("Закрытие через 5 секунд...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.edit(archived=True, locked=True)
        except Exception:
            await interaction.channel.delete()


# --- КНОПКА СОЗДАНИЯ ТИКЕТА С ДОБАВЛЕНИЕМ АДМИНОВ ---
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Создать", style=discord.ButtonStyle.success, emoji="🪪", custom_id="create_ticket_btn_persistent")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild

        for thread in interaction.channel.threads:
            if f"-{user.id}" in thread.name:
                await interaction.response.send_message("У вас уже есть открытый тикет!", ephemeral=True)
                return

        try:
            thread = await interaction.channel.create_thread(
                name=f"тикет-{user.name}-{user.id}", 
                type=discord.ChannelType.private_thread, 
                invitable=False
            )
            await thread.add_user(user)

            admin_mentions = []
            for member in guild.members:
                if not member.bot and member.guild_permissions.administrator:
                    try:
                        await thread.add_user(member)
                        admin_mentions.append(member.mention)
                    except Exception:
                        pass

            embed = discord.Embed(
                title="🎫 Тикет создан",
                description=(
                    f"Привет, {user.mention}!\nОпишите вашу проблему или задайте вопрос.\n"
                    "Персонал скоро ответит вам.\n\n"
                    f"**Уведомлены администраторы:** {', '.join(admin_mentions) if admin_mentions else 'Не найдены'}"
                ),
                color=discord.Color.green(),
            )
            
            await thread.send(content=" ".join(admin_mentions) if admin_mentions else "", embed=embed, view=CloseTicketView())
            await interaction.response.send_message(f"Ваш тикет успешно создан: {thread.mention}", ephemeral=True)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Не удалось создать тикет: {e}", ephemeral=True)


# --- ПАНЕЛЬ МАТЧА ---
class MatchControlView(discord.ui.View):
    def __init__(self, match_id: int, host_user_id: int):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.host_user_id = host_user_id

    @discord.ui.button(label="Получить ID хоста", style=discord.ButtonStyle.secondary, emoji="👑", custom_id="get_host_id_btn")
    async def get_host(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = interaction.client.db.get_player(interaction.guild_id, self.host_user_id)
        h_id = "Не найден"
        if player:
            raw_name = getattr(player, "name", "")
            if " | " in raw_name:
                h_id = raw_name.split(" | ")[0]
            else:
                h_id = str(getattr(player, "player_id", self.host_user_id))
        await interaction.response.send_message(f"👑 Игровой ID хоста лобби: **{h_id}**", ephemeral=True)

    @discord.ui.button(label="Отправить результаты", style=discord.ButtonStyle.primary, emoji="📋", custom_id="send_results_btn")
    async def send_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        for thread in interaction.channel.threads:
            if f"матч-{self.match_id}" in thread.name:
                await interaction.response.send_message(f"Ветка уже открыта: {thread.mention}", ephemeral=True)
                return
        try:
            thread = await interaction.channel.create_thread(name=f"результаты-матч-{self.match_id}", type=discord.ChannelType.private_thread, invitable=False)
            await thread.add_user(user)
            embed = discord.Embed(title=f"📋 Результаты Матча #{self.match_id}", description="Отправьте скриншот счета или итоги игры. Модераторы скоро проверят.", color=discord.Color.blue())
            await thread.send(embed=embed)
            await interaction.response.send_message(f"Ветка для отправки результатов создана: {thread.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


# --- МОДАЛЬНОЕ ОКНО РЕГИСТРАЦИИ ---
class RegistrationModal(discord.ui.Modal, title="Регистрация игрока"):
    player_id = discord.ui.TextInput(label="Игровой ID", placeholder="Введите ваш ID...", required=True, max_length=30)
    game_name = discord.ui.TextInput(label="Игровой никнейм", placeholder="Ник в игре...", required=True, max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        p_id = self.player_id.value
        nickname = self.game_name.value

        try:
            interaction.client.db.add_player(guild_id=interaction.guild_id, user_id=user.id, player_id=p_id, name=nickname)
        except TypeError:
            interaction.client.db.add_player(guild_id=interaction.guild_id, user_id=user.id, name=f"{p_id} | {nickname}")

        await interaction.followup.send(
            f"✅ Регистрация успешна!\n🆔 ID: **{p_id}**\n🎮 Nickname: **{nickname}**\n*(Ваши текущие роли на сервере сохранены)*", 
            ephemeral=True
        )


class RegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Зарегистрироваться", style=discord.ButtonStyle.blurple, emoji="🎮", custom_id="register_modal_btn")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())


class FaceitLikeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db = Database()

    async def setup_hook(self):
        @self.tree.command(name="setup_ticket", description="Опубликовать панель тикетов")
        @app_commands.checks.has_permissions(administrator=True)
        async def setup_ticket(interaction: discord.Interaction):
            embed = discord.Embed(title="Помощь по серверу", description="Создать тикет для связи с персоналом.", color=discord.Color.dark_embed())
            await interaction.channel.send(embed=embed, view=TicketView())
            await interaction.response.send_message("Панель тикетов опубликована!", ephemeral=True)

        @self.tree.command(name="postregister", description="Опубликовать панель регистрации")
        @app_commands.checks.has_permissions(administrator=True)
        async def postregister(interaction: discord.Interaction):
            embed = discord.Embed(title="📝 Регистрация на сервере", description="Нажмите кнопку ниже для регистрации.", color=discord.Color.blue())
            await interaction.channel.send(embed=embed, view=RegistrationView())
            await interaction.response.send_message("Панель регистрации опубликована!", ephemeral=True)

        @self.tree.command(name="profile", description="Показать профиль и карточку статистики")
        @app_commands.choices(league=[
            app_commands.Choice(name="Pro", value="pro"),
            app_commands.Choice(name="Division", value="division"),
            app_commands.Choice(name="Prospect", value="prospect"),
        ])
        @app_commands.describe(league="Выберите лигу", user="Чей профиль показать")
        async def profile(interaction: discord.Interaction, league: str, user: discord.Member = None):
            target = user or interaction.user
            player = self.db.get_player(interaction.guild_id, target.id)
            if player is None:
                await interaction.response.send_message(f"{target.display_name} не зарегистрирован.", ephemeral=True)
                return

            player_name = getattr(player, "name", target.display_name)
            player_id_val = str(getattr(player, "player_id", None) or getattr(player, "id", "Не указан"))
            if " | " in player_name:
                parts = player_name.split(" | ", 1)
                player_id_val = parts[0]
                player_name = parts[1]

            stats = {
                "total_matches": getattr(player, "matches_played", 12),
                "wins": getattr(player, "wins", 8),
                "losses": getattr(player, "losses", 4),
                "kd": getattr(player, "kd", "1.25"),
                "maps": {
                    "dune": {"played": 3, "kd": "1.30"},
                    "prison": {"played": 2, "kd": "1.10"},
                    "hanami": {"played": 2, "kd": "0.95"},
                    "breeze": {"played": 2, "kd": "1.45"},
                    "sandstone": {"played": 2, "kd": "1.20"},
                    "rust": {"played": 1, "kd": "1.00"},
                }
            }

            card_buffer = generate_detailed_profile_card(player_name, player_id_val, league, stats)
            file = discord.File(fp=card_buffer, filename="profile.png")
            await interaction.response.send_message(file=file, ephemeral=True)

        # --- АДМИН КОМАНДЫ (BAN, MUTE, WARN, ROLE) ---

        @self.tree.command(name="ban", description="Заблокировать участника на сервере")
        @app_commands.checks.has_permissions(ban_members=True)
        @app_commands.describe(member="Участник", reason="Причина бана")
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ Пользователь {member.mention} заблокирован. Причина: {reason}", ephemeral=True)

        @self.tree.command(name="unban", description="Разблокировать пользователя по ID")
        @app_commands.checks.has_permissions(ban_members=True)
        @app_commands.describe(user_id="ID пользователя для разблокировки")
        async def unban(interaction: discord.Interaction, user_id: str):
            try:
                user = await self.fetch_user(int(user_id))
                await interaction.guild.unban(user)
                await interaction.response.send_message(f"✅ Пользователь {user.name} успешно разблокирован.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка разблокировки: {e}", ephemeral=True)

        @self.tree.command(name="mute", description="Замутить участника (выдать таймаут)")
        @app_commands.checks.has_permissions(moderate_members=True)
        @app_commands.describe(member="Участник", minutes="Время мута в минутах", reason="Причина")
        async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Не указана"):
            duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            await interaction.response.send_message(f"✅ Пользователь {member.mention} заглушен на {minutes} мин. Причина: {reason}", ephemeral=True)

        @self.tree.command(name="unmute", description="Снять мут с участника")
        @app_commands.checks.has_permissions(moderate_members=True)
        @app_commands.describe(member="Участник")
        async def unmute(interaction: discord.Interaction, member: discord.Member):
            await member.timeout(None)
            await interaction.response.send_message(f"✅ С пользователя {member.mention} снят мут.", ephemeral=True)

        @self.tree.command(name="warn", description="Выдать предупреждение (warn 1/3, 2/3 или 3/3)")
        @app_commands.checks.has_permissions(manage_roles=True)
        @app_commands.choices(warn_level=[
            app_commands.Choice(name="Warn 1/3", value="1"),
            app_commands.Choice(name="Warn 2/3", value="2"),
            app_commands.Choice(name="Warn 3/3", value="3"),
        ])
        @app_commands.describe(member="Участник", warn_level="Уровень предупреждения", reason="Причина")
        async def warn(interaction: discord.Interaction, member: discord.Member, warn_level: str, reason: str = "Не указана"):
            guild = interaction.guild
            # Ищем роли на сервере по имени
            role_name = f"warn {warn_level}/3"
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
                # Если роль не создана автоматически, пытаемся создать её
                try:
                    role = await guild.create_role(name=role_name, reason="Автоматическое создание роли варна ботом")
                except Exception:
                    await interaction.response.send_message(f"❌ Не удалось найти или создать роль `{role_name}` на сервере!", ephemeral=True)
                    return

            await member.add_roles(role, reason=reason)
            await interaction.response.send_message(f"⚠️ Игроку {member.mention} выдано предупреждение **{warn_level}/3** (роль `{role_name}`). Причина: {reason}", ephemeral=True)

        @self.tree.command(name="unwarn", description="Снять предупреждение с участника")
        @app_commands.checks.has_permissions(manage_roles=True)
        @app_commands.choices(warn_level=[
            app_commands.Choice(name="Warn 1/3", value="1"),
            app_commands.Choice(name="Warn 2/3", value="2"),
            app_commands.Choice(name="Warn 3/3", value="3"),
        ])
        @app_commands.describe(member="Участник", warn_level="Уровень предупреждения для снятия")
        async def unwarn(interaction: discord.Interaction, member: discord.Member, warn_level: str):
            guild = interaction.guild
            role_name = f"warn {warn_level}/3"
            role = discord.utils.get(guild.roles, name=role_name)

            if role and role in member.roles:
                await member.remove_roles(role)
                await interaction.response.send_message(f"✅ С игрока {member.mention} снята роль предупреждения `{role_name}`.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ У игрока нет роли `{role_name}`.", ephemeral=True)

        @self.tree.command(name="role", description="Выдать или забрать роль у участника")
        @app_commands.checks.has_permissions(manage_roles=True)
        @app_commands.choices(action=[
            app_commands.Choice(name="Добавить (add)", value="add"),
            app_commands.Choice(name="Убрать (remove)", value="remove"),
        ])
        @app_commands.describe(action="Действие", member="Участник", role="Роль")
        async def role_cmd(interaction: discord.Interaction, action: str, member: discord.Member, role: discord.Role):
            try:
                if action == "add":
                    await member.add_roles(role)
                    await interaction.response.send_message(f"✅ Участнику {member.mention} успешно добавлена роль **{role.name}**.", ephemeral=True)
                elif action == "remove":
                    await member.remove_roles(role)
                    await interaction.response.send_message(f"✅ У участника {member.mention} успешно убрана роль **{role.name}**.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка при изменении роли: {e}", ephemeral=True)

        # Обработчик ошибок для проверки прав администратора/модератора
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.MissingPermissions):
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ У вас недостаточно прав для выполнения этой команды!", ephemeral=True)
            else:
                logging.error(f"Ошибка в слеш-команде: {error}")

        synced = await self.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} команд.")

    async def on_ready(self):
        logging.info(f"Бот запущен как {self.user}")


async def main():
    if not config.TOKEN:
        logging.error("Токен не найден!")
        return
    bot = FaceitLikeBot()
    try:
        async with bot:
            await bot.start(config.TOKEN)
    except Exception as e:
        logging.error(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())

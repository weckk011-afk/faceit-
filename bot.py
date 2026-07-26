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
    local_font = "arial.ttf"
    if os.path.exists(local_font):
        try:
            return ImageFont.truetype(local_font, size)
        except Exception:
            pass

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
                
    logging.warning("Внимание: Не найден шрифт с поддержкой кириллицы! Положите файл arial.ttf в папку бота.")
    return ImageFont.load_default()


def generate_detailed_profile_card(member_name: str, player_id: str, league: str, stats: dict) -> io.BytesIO:
    width, height = 900, 1180
    image = Image.new("RGB", (width, height), color=(15, 16, 20))
    draw = ImageDraw.Draw(image)

    # Шрифты
    font_title = get_font(44)   # Крупный никнейм (~1/4 ширины)
    font_header = get_font(16)
    font_text = get_font(15)
    font_small = get_font(12)
    font_big = get_font(32)
    font_num = get_font(24)

    # --- 1. ШАПКА ПРОФИЛЯ ---
    draw.rounded_rectangle([30, 20, 870, 150], radius=12, fill=(24, 26, 32), outline=(40, 43, 52), width=1)
    
    # Квадрат для аватара
    draw.rounded_rectangle([45, 35, 135, 135], radius=8, fill=(50, 53, 63))
    draw.text((155, 58), member_name, fill=(255, 255, 255), font=font_title)
    draw.text((155, 112), f"ID: {player_id}", fill=(130, 135, 145), font=font_medium)

    draw.text((680, 65), league.upper(), fill=(255, 215, 0), font=font_big)

    # --- 2. СЕКЦИЯ СТАТИСТИКИ (Statistic) ---
    draw.text((30, 175), "Statistic", fill=(180, 185, 195), font=font_header)
    
    # Блок K/D круговой
    draw.rounded_rectangle([30, 205, 310, 320], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    kd_val = str(stats.get("kd", "0.00"))
    draw.text((50, 238), kd_val, fill=(255, 255, 255), font=font_big)
    draw.text((150, 236), "Kill/Deaths", fill=(140, 145, 155), font=font_small)
    kills = stats.get("kills", 0)
    deaths = stats.get("deaths", 0)
    draw.text((150, 262), f"K = {kills}    D = {deaths}", fill=(180, 185, 195), font=font_small)

    # Блок Level / прогресс
    draw.rounded_rectangle([330, 205, 870, 320], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    draw.text((360, 230), "Level", fill=(140, 145, 155), font=font_text)
    draw.text((810, 225), "0", fill=(220, 100, 100), font=font_num)
    draw.rounded_rectangle([360, 277, 840, 287], radius=4, fill=(50, 40, 50))
    draw.rounded_rectangle([360, 277, 360, 287], radius=4, fill=(230, 50, 110))

    # Плашки стат
    metrics = [
        ("Rating", str(stats.get("rating", "0.00")), "None", 30, 335),
        ("AVG", str(stats.get("avg", "0")), "None", 319, 335),
        ("Impact", str(stats.get("impact", "0.00")), "None", 608, 335),
        ("KPR", str(stats.get("kpr", "0.00")), "None", 30, 445),
        ("Assists", str(stats.get("assists", "0")), "None", 319, 445),
        ("SVR", str(stats.get("svr", "0.00")), "None", 608, 445),
    ]

    for label, val, sub, x, y in metrics:
        draw.rounded_rectangle([x, y, x + 262, y + 95], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
        draw.text((x + 18, y + 14), label, fill=(140, 145, 155), font=font_small)
        draw.text((x + 18, y + 36), val, fill=(255, 255, 255), font=font_num)
        draw.text((x + 18, y + 68), sub, fill=(110, 115, 125), font=font_small)

    # --- 3. СЕКЦИЯ КАРТ (Map Statistic) ---
    draw.text((30, 560), "Map Statistic", fill=(180, 185, 195), font=font_header)

    # Общий Винрейт
    draw.rounded_rectangle([30, 590, 310, 705], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    wr_val = 0
    draw.text((50, 623), f"{wr_val}%", fill=(255, 255, 255), font=font_big)
    draw.text((150, 617), "Win Rate", fill=(140, 145, 155), font=font_small)
    draw.text((150, 643), f"W = {wins}    L = {losses}", fill=(180, 185, 195), font=font_small)

    # Best Map
    draw.rounded_rectangle([330, 590, 870, 705], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    draw.text((360, 613), "None", fill=(255, 255, 255), font=font_num)
    draw.text((360, 643), "W = 0    L = 0", fill=(140, 145, 155), font=font_small)
    draw.text((360, 667), "K/D = 0.00    W/R = 0%", fill=(255, 200, 100), font=font_small)
    draw.text((790, 617), "BEST MAP", fill=(100, 105, 115), font=font_small)

    # ВСЕ 7 КАРТ (Сетка 3 колонки, 7-я карта на последнем ряду по центру/справа)
    mini_maps = [
        ("Sandstone", "0", "0", "0.00", "0%", 30, 725),
        ("Province", "0", "0", "0.00", "0%", 319, 725),
        ("Prison", "0", "0", "0.00", "0%", 608, 725),
        ("Hanami", "0", "0", "0.00", "0%", 30, 840),
        ("Breeze", "0", "0", "0.00", "0%", 319, 840),
        ("Dune", "0", "0", "0.00", "0%", 608, 840),
        ("Rust", "0", "0", "0.00", "0%", 30, 955), # 7-я карта
    ]

    for m_name, m_w, m_l, m_kd, m_wr, x, y in mini_maps:
        draw.rounded_rectangle([x, y, x + 262, y + 100], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
        draw.text((x + 18, y + 12), m_name, fill=(255, 255, 255), font=font_text)
        draw.text((x + 18, y + 38), f"W = {m_w}   L = {m_l}", fill=(140, 145, 155), font=font_small)
        draw.text((x + 18, y + 65), f"K/D = {m_kd}", fill=(210, 190, 110), font=font_small)
        draw.text((x + 135, y + 65), f"W/R = {m_wr}", fill=(210, 190, 110), font=font_small)

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


# --- КНОПКА СОЗДАНИЯ ТИКЕТА ---
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
            await interaction.response.defer(ephemeral=True)

            target = user or interaction.user
            player = self.db.get_player(interaction.guild_id, target.id)
            if player is None:
                await interaction.followup.send(f"{target.display_name} не зарегистрирован.", ephemeral=True)
                return

            player_name = getattr(player, "name", target.display_name)
            player_id_val = str(getattr(player, "player_id", None) or getattr(player, "id", "Не указан"))
            if " | " in player_name:
                parts = player_name.split(" | ", 1)
                player_id_val = parts[0]
                player_name = parts[1]

            stats = {
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "kd": "0.00",
                "kills": 0,
                "deaths": 0,
                "rating": "0.00",
                "avg": "0",
                "impact": "0.00",
                "kpr": "0.00",
                "assists": 0,
                "svr": "0.00"
            }

            try:
                card_buffer = generate_detailed_profile_card(player_name, player_id_val, league, stats)
                file = discord.File(fp=card_buffer, filename="profile.png")
                await interaction.followup.send(file=file, ephemeral=True)
            except Exception as e:
                logging.error(f"Ошибка при создании профиля: {e}")
                await interaction.followup.send("❌ Произошла ошибка при генерации карточки профиля.", ephemeral=True)

        # --- АДМИН КОМАНДЫ ---

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
            role_name = f"warn {warn_level}/3"
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
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

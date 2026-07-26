import asyncio
import datetime
import io
import logging
import os

import aiohttp
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

# ==============================================================================
# ЭМОДЗИ УРОВНЕЙ (СЕРВЕРНЫЕ)
# ------------------------------------------------------------------------------
# Загрузи 10 эмодзи на сервер (Server Settings -> Emoji), затем в любом
# текстовом канале напиши "\:имя_эмодзи:" (с обратным слэшем) - Discord
# пришлёт полную запись вида "<:lvl1:123456789012345678>". Вставь эти
# строки сюда вместо "REPLACE_ME".
# ==============================================================================
LEVEL_EMOJIS = {
    1: "<:lvl1:1530900138761912501>",
    2: "<:lvl2:1530909226388688966>",
    3: "<:lvl3:1530909273121620099>",
    4: "<:lvl4:1530909327634993323>",
    5: "<:lvl5:1530909379883303014>",
    6: "<:lvl6:1530909442047082536>",
    7: "<:lvl7:1530909546955145216>",
    8: "<:lvl8:1530909635228467380>",
    9: "<:lvl9:1530909690706399392>",
    10: "<:lvl10:1530909728438485142>",
}


def level_emoji(level: int) -> str:
    emoji = LEVEL_EMOJIS.get(level, "REPLACE_ME")
    return emoji if emoji != "REPLACE_ME" else "❓"


def get_font(size: int):
    font_paths = [
        "arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
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

    logging.warning("⚠️ ВНИМАНИЕ: Шрифт не найден! Положите файл arial.ttf в папку с ботом.")
    return ImageFont.load_default()


def calculate_level_and_progress(league: str, elo: int):
    """
    Вычисляет текущий уровень, границы ELO и процент прогресса на основе лиги.
    """
    league = league.lower()

    if league == "pro":
        thresholds = [0, 399, 699, 999, 1299, 1599, 1899, 2199, 2599, 2799]
    else:  # Для prospect и division
        thresholds = [0, 200, 400, 600, 900, 1100, 1400, 1600, 1800, 2000]

    for i in range(9, -1, -1):
        if elo >= thresholds[i]:
            level = i + 1
            min_elo = thresholds[i]

            if level < 10:
                max_elo = thresholds[i + 1]
                progress_percent = (elo - min_elo) / (max_elo - min_elo)
            else:
                max_elo = min_elo
                progress_percent = 1.0

            return level, min_elo, max_elo, progress_percent

    return 1, 0, thresholds[1], 0.0


async def fetch_level_icon_bytes(session: aiohttp.ClientSession, url: str) -> bytes | None:
    """Асинхронная (не блокирующая event loop) загрузка иконки уровня."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        logging.warning(f"Не удалось подгрузить иконку уровня: {e}")
    return None


async def generate_detailed_profile_card(
    session: aiohttp.ClientSession, member_name: str, player_id: str, stats: dict, league: str
) -> io.BytesIO:
    width, height = 900, 1180
    image = Image.new("RGB", (width, height), color=(15, 16, 20))
    draw = ImageDraw.Draw(image)

    font_title = get_font(49)
    font_id = get_font(20)
    font_header = get_font(16)
    font_text = get_font(15)
    font_small = get_font(12)
    font_big = get_font(32)
    font_num = get_font(24)

    # --- 1. ШАПКА ПРОФИЛЯ ---
    draw.rounded_rectangle([30, 20, 870, 160], radius=12, fill=(24, 26, 32), outline=(40, 43, 52), width=1)
    draw.rounded_rectangle([45, 35, 145, 135], radius=8, fill=(50, 53, 63))
    draw.text((170, 45), member_name, fill=(255, 255, 255), font=font_title)
    draw.text((175, 110), f"ID: {player_id}", fill=(130, 135, 145), font=font_id)

    # --- 2. СЕКЦИЯ СТАТИСТИКИ ---
    draw.text((30, 185), "Statistic", fill=(180, 185, 195), font=font_header)

    # Блок K/D
    draw.rounded_rectangle([30, 215, 310, 330], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    kd_val = str(stats.get("kd", "0.00"))
    draw.text((50, 248), kd_val, fill=(255, 255, 255), font=font_big)
    draw.text((150, 246), "Kill/Deaths", fill=(140, 145, 155), font=font_small)
    draw.text((150, 272), f"K = {stats.get('kills', 0)}    D = {stats.get('deaths', 0)}", fill=(180, 185, 195), font=font_small)

    # === БЛОК УРОВНЯ И ПРОГРЕССА ===
    draw.rounded_rectangle([330, 215, 870, 330], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))

    try:
        elo_rating = int(float(stats.get("rating", 299)))
    except ValueError:
        elo_rating = 299

    level, min_elo, max_elo, progress = calculate_level_and_progress(league, elo_rating)

    # Уровень теперь подписан цифрой на карточке (эмодзи выводится отдельно, в тексте сообщения,
    # т.к. Pillow не умеет рисовать кастомные Discord-эмодзи как изображение без доп. загрузки).
    draw.text((360, 250), f"Lvl {level}", fill=(255, 200, 100), font=font_big)

    draw.text((450, 235), f"Level {level}", fill=(255, 255, 255), font=font_text)
    draw.text((450, 260), f"{elo_rating} ELO", fill=(140, 145, 155), font=font_small)

    if level < 10:
        draw.text((790, 260), f"{max_elo} ELO", fill=(140, 145, 155), font=font_small)
    else:
        draw.text((790, 260), "MAX", fill=(220, 100, 100), font=font_small)

    bar_x1, bar_y1 = 450, 287
    bar_x2, bar_y2 = 840, 297

    draw.rounded_rectangle([bar_x1, bar_y1, bar_x2, bar_y2], radius=4, fill=(50, 40, 50))

    fill_width = int((bar_x2 - bar_x1) * progress)
    if fill_width > 0:
        fill_width = max(fill_width, 8)
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x1 + fill_width, bar_y2], radius=4, fill=(230, 50, 110))

    # Плашки стат
    metrics = [
        ("Rating", str(stats.get("rating", "299")), "None", 30, 345),
        ("AVG", str(stats.get("avg", "0")), "None", 319, 345),
        ("Impact", str(stats.get("impact", "0.00")), "None", 608, 345),
        ("KPR", str(stats.get("kpr", "0.00")), "None", 30, 455),
        ("Assists", str(stats.get("assists", "0")), "None", 319, 455),
        ("SVR", str(stats.get("svr", "0.00")), "None", 608, 455),
    ]

    for label, val, sub, x, y in metrics:
        draw.rounded_rectangle([x, y, x + 262, y + 95], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
        draw.text((x + 18, y + 14), label, fill=(140, 145, 155), font=font_small)
        draw.text((x + 18, y + 36), val, fill=(255, 255, 255), font=font_num)
        draw.text((x + 18, y + 68), sub, fill=(110, 115, 125), font=font_small)

    # --- 3. СЕКЦИЯ КАРТ ---
    draw.text((30, 570), "Map Statistic", fill=(180, 185, 195), font=font_header)

    draw.rounded_rectangle([30, 600, 310, 715], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    draw.text((50, 633), "0%", fill=(255, 255, 255), font=font_big)
    draw.text((150, 627), "Win Rate", fill=(140, 145, 155), font=font_small)
    draw.text((150, 653), f"W = {stats.get('wins', 0)}    L = {stats.get('losses', 0)}", fill=(180, 185, 195), font=font_small)

    draw.rounded_rectangle([330, 600, 870, 715], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
    draw.text((360, 623), "None", fill=(255, 255, 255), font=font_num)
    draw.text((360, 653), "W = 0    L = 0", fill=(140, 145, 155), font=font_small)
    draw.text((360, 677), "K/D = 0.00    W/R = 0%", fill=(255, 200, 100), font=font_small)
    draw.text((790, 627), "BEST MAP", fill=(100, 105, 115), font=font_small)

    wide_maps = [
        ("Sandstone", "0", "0", "0.00", "0%", 30, 735),
        ("Province", "0", "0", "0.00", "0%", 465, 735),
        ("Prison", "0", "0", "0.00", "0%", 30, 850),
        ("Hanami", "0", "0", "0.00", "0%", 465, 850),
    ]

    for m_name, m_w, m_l, m_kd, m_wr, x, y in wide_maps:
        draw.rounded_rectangle([x, y, x + 405, y + 100], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
        draw.text((x + 18, y + 12), m_name, fill=(255, 255, 255), font=font_text)
        draw.text((x + 18, y + 38), f"W = {m_w}   L = {m_l}", fill=(140, 145, 155), font=font_small)
        draw.text((x + 18, y + 65), f"K/D = {m_kd}", fill=(210, 190, 110), font=font_small)
        draw.text((x + 220, y + 65), f"W/R = {m_wr}", fill=(210, 190, 110), font=font_small)

    standard_maps = [
        ("Breeze", "0", "0", "0.00", "0%", 30, 965),
        ("Dune", "0", "0", "0.00", "0%", 319, 965),
        ("Rust", "0", "0", "0.00", "0%", 608, 965),
    ]

    for m_name, m_w, m_l, m_kd, m_wr, x, y in standard_maps:
        draw.rounded_rectangle([x, y, x + 262, y + 100], radius=10, fill=(24, 26, 32), outline=(40, 43, 52))
        draw.text((x + 18, y + 12), m_name, fill=(255, 255, 255), font=font_text)
        draw.text((x + 18, y + 38), f"W = {m_w}   L = {m_l}", fill=(140, 145, 155), font=font_small)
        draw.text((x + 18, y + 65), f"K/D = {m_kd}", fill=(210, 190, 110), font=font_small)
        draw.text((x + 135, y + 65), f"W/R = {m_wr}", fill=(210, 190, 110), font=font_small)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# --- КНОПКИ ТИКЕТОВ И МОДАЛКИ ---
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
                invitable=False,
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
            logging.error(f"Ошибка создания тикета: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Не удалось создать тикет: {e}", ephemeral=True)


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
            ephemeral=True,
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
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        # Общая aiohttp-сессия для неблокирующей загрузки иконок и т.п.
        self.http_session = aiohttp.ClientSession()

        # Регистрируем persistent views, иначе кнопки перестанут отвечать после рестарта бота
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        self.add_view(RegistrationView())

        @self.tree.command(name="setup_ticket", description="Опубликовать панель тикетов")
        @app_commands.checks.has_permissions(administrator=True)
        async def setup_ticket(interaction: discord.Interaction):
            embed = discord.Embed(title="Помощь по серверу", description="Создать тикет для связи с персоналом.", color=discord.Color.dark_theme())
            await interaction.channel.send(embed=embed, view=TicketView())
            await interaction.response.send_message("Панель тикетов опубликована!", ephemeral=True)

        @self.tree.command(name="postregister", description="Опубликовать панель регистрации")
        @app_commands.checks.has_permissions(administrator=True)
        async def postregister(interaction: discord.Interaction):
            embed = discord.Embed(title="📝 Регистрация на сервере", description="Нажмите кнопку ниже для регистрации.", color=discord.Color.blue())
            await interaction.channel.send(embed=embed, view=RegistrationView())
            await interaction.response.send_message("Панель регистрации опубликована!", ephemeral=True)

        @self.tree.command(name="profile", description="Показать профиль и карточку статистики")
        @app_commands.describe(league="Выберите лигу (обязательно)", user="Чей профиль показать")
        @app_commands.choices(league=[
            app_commands.Choice(name="pro", value="pro"),
            app_commands.Choice(name="division", value="division"),
            app_commands.Choice(name="prospect", value="prospect"),
        ])
        async def profile(interaction: discord.Interaction, league: app_commands.Choice[str], user: discord.Member = None):
            await interaction.response.defer(ephemeral=True)

            target = user or interaction.user
            player = self.db.get_player(interaction.guild_id, target.id)
            if player is None:
                await interaction.followup.send(f"{target.display_name} не зарегистрирован.", ephemeral=True)
                return

            player_name = target.display_name
            player_id_val = "Не указан"

            if hasattr(player, "player_id"):
                player_id_val = str(player.player_id)
                player_name = str(getattr(player, "name", target.display_name))
            elif isinstance(player, tuple):
                if len(player) >= 4:
                    player_id_val = str(player[2])
                    player_name = str(player[3])
                elif len(player) == 3:
                    player_id_val = str(player[1])
                    player_name = str(player[2])

            if " | " in player_name and (player_id_val == "Не указан" or not player_id_val):
                parts = player_name.split(" | ", 1)
                player_id_val = parts[0]
                player_name = parts[1]

            stats = {
                "total_matches": 0, "wins": 0, "losses": 0, "kd": "0.00",
                "kills": 0, "deaths": 0, "rating": "299", "avg": "0",
                "impact": "0.00", "kpr": "0.00", "assists": 0, "svr": "0.00",
            }

            try:
                card_buffer = await generate_detailed_profile_card(self.http_session, player_name, player_id_val, stats, league.value)
                file = discord.File(fp=card_buffer, filename="profile.png")

                elo_rating = int(float(stats.get("rating", 299)))
                level, *_ = calculate_level_and_progress(league.value, elo_rating)
                msg_content = f"🏆 **Лига:** {league.name.upper()} | {level_emoji(level)} Уровень {level}"

                await interaction.followup.send(content=msg_content, file=file, ephemeral=True)
            except Exception as e:
                logging.error(f"Ошибка при создании профиля: {e}", exc_info=True)
                await interaction.followup.send("❌ Произошла ошибка при генерации карточки профиля.", ephemeral=True)

        @self.tree.command(name="ranks", description="Показать список рангов и систему ELO")
        async def ranks(interaction: discord.Interaction):
            prospect_division_thresholds = [
                (0, 199), (200, 399), (400, 599), (600, 899), (900, 1099),
                (1100, 1399), (1400, 1599), (1600, 1799), (1800, 1999), (2000, None),
            ]
            pro_thresholds = [
                (0, 398), (399, 698), (699, 998), (999, 1298), (1299, 1598),
                (1599, 1898), (1899, 2198), (2199, 2598), (2599, 2798), (2799, None),
            ]

            def format_block(title: str, thresholds: list) -> str:
                lines = [f"**{title}**"]
                for i, (lo, hi) in enumerate(thresholds, start=1):
                    rng = f"[{lo}-{hi}]" if hi is not None else f"[{lo}+]"
                    lines.append(f"{level_emoji(i)} - {rng}")
                return "\n".join(lines)

            description = (
                format_block("@prospect league", prospect_division_thresholds)
                + "\n\n"
                + format_block("@division league", prospect_division_thresholds)
                + "\n\n"
                + format_block("@pro league", pro_thresholds)
            )

            embed = discord.Embed(
                title="Список рангов",
                description=description,
                color=discord.Color.dark_theme(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
        @app_commands.describe(member="Участник", minutes="Время мута в минутах (1-40320)", reason="Причина")
        async def mute(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "Не указана"):
            duration = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
            try:
                await member.timeout(duration, reason=reason)
                await interaction.response.send_message(f"✅ Пользователь {member.mention} заглушен на {minutes} мин. Причина: {reason}", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.response.send_message(f"❌ Не удалось выдать таймаут: {e}", ephemeral=True)

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
                    await interaction.response.send_message(f"❌ Не удалось найти роль `{role_name}` на сервере!", ephemeral=True)
                    return

            await member.add_roles(role, reason=reason)
            await interaction.response.send_message(f"⚠️ Игроку {member.mention} выдано предупреждение **{warn_level}/3**. Причина: {reason}", ephemeral=True)

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
                await interaction.response.send_message(f"✅ С игрока {member.mention} снята роль `{role_name}`.", ephemeral=True)
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
                    await interaction.response.send_message(f"✅ Участнику {member.mention} добавлена роль **{role.name}**.", ephemeral=True)
                elif action == "remove":
                    await member.remove_roles(role)
                    await interaction.response.send_message(f"✅ У участника {member.mention} убрана роль **{role.name}**.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка при изменении роли: {e}", ephemeral=True)

        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.MissingPermissions):
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ У вас недостаточно прав для выполнения этой команды!", ephemeral=True)
            else:
                logging.error(f"Ошибка в слеш-команде: {error}", exc_info=True)

        synced = await self.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} команд.")

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

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

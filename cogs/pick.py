# ==========================================================
# pick.py
# СИСТЕМА ПИКОВ ИГРОКОВ
# ==========================================================

import asyncio
import discord
import config


# ==========================================================
# НАСТРОЙКИ
# ==========================================================

PICK_CHANNEL_ID = 1530634450591813803

LOBBY_CHANNEL_NAME = "Lobby"

TEAM_T_PREFIX = "team voice T"
TEAM_CT_PREFIX = "team voice CT"

VOICE_DELETE_DELAY = 5 * 60


# ==========================================================
# АКТИВНЫЕ ПИКИ
# ==========================================================

active_picks = {}


# ==========================================================
# СЕССИЯ ПИКА
# ==========================================================

class PickSession:

    def __init__(self, guild_id, players):

        self.guild_id = guild_id

        # 10 игроков
        self.players = players

        # капитаны
        self.captain_a = None
        self.captain_b = None

        # команды
        self.team_a = []
        self.team_b = []

        # чей ход
        self.turn = None

        # карты
        self.maps = config.MAP_POOL.copy()
        self.selected_map = None

        # ID игры
        self.match_id = None

        # войсы
        self.voice_t = None
        self.voice_ct = None

        # сообщение с пиками
        self.pick_message = None

        # сообщение с картой
        self.map_message = None


# ==========================================================
# ЗАПУСК ПИКА
# ==========================================================

async def start_pick(bot, guild, players):

    if guild.id in active_picks:

        return


    if len(players) != 10:

        return


    session = PickSession(
        guild_id=guild.id,
        players=players
    )


    # Первые два игрока становятся капитанами

    session.captain_a = players[0]
    session.captain_b = players[1]


    # Капитаны автоматически входят в свои команды

    session.team_a.append(session.captain_a)
    session.team_b.append(session.captain_b)


    # Первый ход капитана A

    session.turn = session.captain_a.id


    active_picks[guild.id] = session


    channel = bot.get_channel(PICK_CHANNEL_ID)


    if channel is None:

        print(
            f"[PICK] Не найден канал {PICK_CHANNEL_ID}"
        )

        return


    embed = discord.Embed(

        title="🎮 НОВЫЙ МАТЧ",

        description=(

            "10 игроков собрано!\n\n"

            f"🔵 **Капитан T:** "
            f"{session.captain_a.mention}\n"

            f"🔴 **Капитан CT:** "
            f"{session.captain_b.mention}\n\n"

            "📢 Начинается пик игроков.\n"

            f"👉 Сейчас ход капитана "
            f"{session.captain_a.mention}"

        ),

        color=discord.Color.blue()

    )


    message = await channel.send(

        embed=embed,

        view=PickPlayerView(
            guild.id
        )

    )


    session.pick_message = message


# ==========================================================
# ОБНОВЛЕНИЕ СООБЩЕНИЯ ПИКА
# ==========================================================

async def update_pick_message(bot, session):

    if not session.pick_message:

        return


    team_a_text = "\n".join(

        f"• {player.mention}"

        for player in session.team_a

    )


    team_b_text = "\n".join(

        f"• {player.mention}"

        for player in session.team_b

    )


    available = [

        player

        for player in session.players

        if player not in session.team_a

        and player not in session.team_b

    ]


    current_captain = (

        session.captain_a

        if session.turn == session.captain_a.id

        else session.captain_b

    )


    embed = discord.Embed(

        title="🎯 ПИК ИГРОКОВ",

        description=(

            f"👉 Сейчас выбирает: "
            f"{current_captain.mention}\n\n"

            f"🔵 **TEAM T**\n"
            f"{team_a_text}\n\n"

            f"🔴 **TEAM CT**\n"
            f"{team_b_text}\n\n"

            f"👥 Осталось игроков: "
            f"**{len(available)}**"

        ),

        color=discord.Color.blurple()

    )


    try:

        await session.pick_message.edit(

            embed=embed,

            view=PickPlayerView(
                session.guild_id
            )

        )

    except discord.NotFound:

        pass


# ==========================================================
# КНОПКА ПИКА ИГРОКА
# ==========================================================

class PickPlayerView(discord.ui.View):

    def __init__(self, guild_id):

        super().__init__(
            timeout=None
        )

        self.guild_id = guild_id


    @discord.ui.button(

        label="Пикнуть игрока",

        style=discord.ButtonStyle.primary,

        custom_id="pick_player_button"

    )

    async def pick_player(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button

    ):

        session = active_picks.get(
            self.guild_id
        )


        if not session:

            await interaction.response.send_message(

                "❌ Активный матч не найден.",

                ephemeral=True

            )

            return


        # Проверка капитана

        if interaction.user.id not in [

            session.captain_a.id,

            session.captain_b.id

        ]:

            await interaction.response.send_message(

                "❌ Только капитаны могут выбирать игроков.",

                ephemeral=True

            )

            return


        # Проверка очереди

        if interaction.user.id != session.turn:

            await interaction.response.send_message(

                "❌ Сейчас ход другого капитана.",

                ephemeral=True

            )

            return


        # Доступные игроки

        available = [

            player

            for player in session.players

            if player not in session.team_a

            and player not in session.team_b

        ]


        if not available:

            await interaction.response.send_message(

                "❌ Больше нет доступных игроков.",

                ephemeral=True

            )

            return


        await interaction.response.send_message(

            "Выбери игрока:",

            view=PlayerSelectView(

                self.guild_id,

                available,

                interaction.user.id

            ),

            ephemeral=True

        )


# ==========================================================
# ВЫБОР ИГРОКА
# ==========================================================

class PlayerSelectView(discord.ui.View):

    def __init__(

        self,

        guild_id,

        players,

        captain_id

    ):

        super().__init__(

            timeout=60

        )


        self.guild_id = guild_id

        self.players = players

        self.captain_id = captain_id


        options = []


        for player in players:

            options.append(

                discord.SelectOption(

                    label=player.display_name[:100],

                    value=str(player.id)

                )

            )


        select = discord.ui.Select(

            placeholder="Выбери игрока",

            options=options,

            min_values=1,

            max_values=1

        )


        select.callback = self.select_player


        self.add_item(select)


    async def select_player(

        self,

        interaction: discord.Interaction

    ):

        session = active_picks.get(

            self.guild_id

        )


        if not session:

            await interaction.response.send_message(

                "❌ Матч уже закончился.",

                ephemeral=True

            )

            return


        # Проверяем капитана ещё раз

        if interaction.user.id != self.captain_id:

            await interaction.response.send_message(

                "❌ Это меню выбора принадлежит другому капитану.",

                ephemeral=True

            )

            return


        # Проверяем очередность

        if session.turn != interaction.user.id:

            await interaction.response.send_message(

                "❌ Сейчас ход другого капитана.",

                ephemeral=True

            )

            return


        player_id = int(

            self.children[0].values[0]

        )


        player = discord.utils.get(

            session.players,

            id=player_id

        )


        if player is None:

            await interaction.response.send_message(

                "❌ Игрок не найден.",

                ephemeral=True

            )

            return


        # Проверяем, что игрок ещё свободен

        if (

            player in session.team_a

            or player in session.team_b

        ):

            await interaction.response.send_message(

                "❌ Этот игрок уже выбран.",

                ephemeral=True

            )

            return


        # Добавляем игрока в команду

        if interaction.user.id == session.captain_a.id:

            session.team_a.append(player)

            session.turn = session.captain_b.id

            team_name = "TEAM T"

        else:

            session.team_b.append(player)

            session.turn = session.captain_a.id

            team_name = "TEAM CT"


        await interaction.response.send_message(

            f"✅ {player.mention} выбран в **{team_name}**.",

            ephemeral=True

        )


        # Проверяем завершение

        if (

            len(session.team_a) == 5

            and len(session.team_b) == 5

        ):

            await finish_player_pick(

                interaction.client,

                session

            )

            return


        await update_pick_message(

            interaction.client,

            session

        )


# ==========================================================
# ЗАВЕРШЕНИЕ ПИКА ИГРОКОВ
# ==========================================================

async def finish_player_pick(

    bot,

    session

):

    channel = bot.get_channel(

        PICK_CHANNEL_ID

    )


    if channel is None:

        return


    team_a_text = "\n".join(

        player.mention

        for player in session.team_a

    )


    team_b_text = "\n".join(

        player.mention

        for player in session.team_b

    )


    embed = discord.Embed(

        title="✅ ПИК ИГРОКОВ ЗАВЕРШЁН",

        description=(

            "🔵 **TEAM T**\n"

            f"{team_a_text}\n\n"

            "🔴 **TEAM CT**\n"

            f"{team_b_text}\n\n"

            "🗺 Теперь капитаны должны выбрать карту."

        ),

        color=discord.Color.green()

    )


    message = await channel.send(

        embed=embed,

        view=MapPickView(

            session.guild_id

        )

    )


    session.map_message = message


# ==========================================================
# КНОПКА ВЫБОРА КАРТЫ
# ==========================================================

class MapPickView(discord.ui.View):

    def __init__(self, guild_id):

        super().__init__(

            timeout=None

        )

        self.guild_id = guild_id


    @discord.ui.button(

        label="🗺 Выбрать карту",

        style=discord.ButtonStyle.success,

        custom_id="choose_map_button"

    )

    async def choose_map(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button

    ):

        session = active_picks.get(

            self.guild_id

        )


        if not session:

            await interaction.response.send_message(

                "❌ Матч не найден.",

                ephemeral=True

            )

            return


        # Только капитаны

        if interaction.user.id not in [

            session.captain_a.id,

            session.captain_b.id

        ]:

            await interaction.response.send_message(

                "❌ Только капитаны могут выбирать карту.",

                ephemeral=True

            )

            return


        await interaction.response.send_message(

            "Выберите карту:",

            view=MapSelectView(

                self.guild_id,

                interaction.user.id

            ),

            ephemeral=True

        )


# ==========================================================
# SELECT КАРТЫ
# ==========================================================

class MapSelectView(discord.ui.View):

    def __init__(

        self,

        guild_id,

        captain_id

    ):

        super().__init__(

            timeout=60

        )


        self.guild_id = guild_id

        self.captain_id = captain_id


        options = [

            discord.SelectOption(

                label=map_name,

                value=map_name

            )

            for map_name in config.MAP_POOL

        ]


        select = discord.ui.Select(

            placeholder="Выберите карту",

            options=options

        )


        select.callback = self.choose_map


        self.add_item(select)


    async def choose_map(

        self,

        interaction: discord.Interaction

    ):

        session = active_picks.get(

            self.guild_id

        )


        if not session:

            await interaction.response.send_message(

                "❌ Матч не найден.",

                ephemeral=True

            )

            return


        # Проверяем капитана

        if interaction.user.id != self.captain_id:

            await interaction.response.send_message(

                "❌ Это меню принадлежит другому капитану.",

                ephemeral=True

            )

            return


        # Проверяем, что карта ещё не выбрана

        if session.selected_map:

            await interaction.response.send_message(

                "❌ Карта уже выбрана.",

                ephemeral=True

            )

            return


        selected_map = self.children[0].values[0]


        session.selected_map = selected_map


        await interaction.response.send_message(

            f"✅ Карта выбрана: **{selected_map}**",

            ephemeral=True

        )


        await create_match_and_voices(

            interaction.client,

            interaction.guild,

            session

        )


# ==========================================================
# СОЗДАНИЕ МАТЧА И ВОЙСОВ
# ==========================================================

async def create_match_and_voices(

    bot,

    guild,

    session

):

    # Создаём запись матча в БД

    try:

        session.match_id = bot.db.create_match(

            guild.id,

            [

                player.id

                for player in session.team_a

            ],

            [

                player.id

                for player in session.team_b

            ]

        )


        bot.db.set_match_map(

            session.match_id,

            session.selected_map

        )

    except Exception as error:

        print(

            f"[PICK] Ошибка создания матча в БД: {error}"

        )


    # Создаём войсы

    try:

        overwrites = {

            guild.default_role: discord.PermissionOverwrite(

                connect=False,

                view_channel=False

            )

        }


        # Войс Team T

        session.voice_t = await guild.create_voice_channel(

            name=(

                f"{TEAM_T_PREFIX} "

                f"{session.match_id}"

            ),

            overwrites=overwrites

        )


        # Войс Team CT

        session.voice_ct = await guild.create_voice_channel(

            name=(

                f"{TEAM_CT_PREFIX} "

                f"{session.match_id}"

            ),

            overwrites=overwrites

        )


        # Разрешаем игрокам видеть свои войсы

        for player in session.team_a:

            await session.voice_t.set_permissions(

                player,

                connect=True,

                view_channel=True

            )


        for player in session.team_b:

            await session.voice_ct.set_permissions(

                player,

                connect=True,

                view_channel=True

            )


        # Перемещаем игроков

        for player in session.team_a:

            member = guild.get_member(

                player.id

            )


            if member and member.voice:

                await member.move_to(

                    session.voice_t

                )


        for player in session.team_b:

            member = guild.get_member(

                player.id

            )


            if member and member.voice:

                await member.move_to(

                    session.voice_ct

                )


        # Сохраняем войсы в БД

        try:

            bot.db.set_match_channels(

                session.match_id,

                0,

                PICK_CHANNEL_ID,

                session.voice_t.id,

                session.voice_ct.id

            )

        except Exception as error:

            print(

                f"[PICK] Ошибка сохранения войсов: {error}"

            )


    except Exception as error:

        print(

            f"[PICK] Ошибка создания войсов: {error}"

        )


    await send_match_card(

        bot,

        session

    )


# ==========================================================
# ФИНАЛЬНАЯ КАРТОЧКА МАТЧА
# ==========================================================

async def send_match_card(

    bot,

    session

):

    channel = bot.get_channel(

        PICK_CHANNEL_ID

    )


    if channel is None:

        return


    team_a_text = "\n".join(

        player.mention

        for player in session.team_a

    )


    team_b_text = "\n".join(

        player.mention

        for player in session.team_b

    )


    embed = discord.Embed(

        title="🔥 МАТЧ ГОТОВ",

        description=(

            f"🆔 **Игра:** `{session.match_id}`\n\n"

            f"🗺 **Карта:** "
            f"`{session.selected_map}`\n\n"

            f"🔵 **TEAM T**\n"
            f"{team_a_text}\n\n"

            f"🔴 **TEAM CT**\n"
            f"{team_b_text}\n\n"

            "🎧 Игроки были перемещены в свои голосовые каналы."

        ),

        color=discord.Color.gold()

    )


    await channel.send(

        embed=embed,

        view=MatchButtons(

            session.match_id

        )

    )


# ==========================================================
# КНОПКИ МАТЧА
# ==========================================================

class MatchButtons(discord.ui.View):

    def __init__(self, match_id):

        super().__init__(

            timeout=None

        )

        self.match_id = match_id


    # ------------------------------------------------------

    # ПОЛУЧИТЬ ID

    # ------------------------------------------------------

    @discord.ui.button(

        label="🆔 Получить ID",

        style=discord.ButtonStyle.primary,

        custom_id="get_standoff_id"

    )

    async def get_id(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button

    ):

        player = interaction.client.db.get_player(

            interaction.guild.id,

            interaction.user.id

        )


        if not player:

            await interaction.response.send_message(

                "❌ Ты не зарегистрирован.",

                ephemeral=True

            )

            return


        standoff_id = player["standoff_id"]


        if not standoff_id:

            await interaction.response.send_message(

                "❌ У тебя не указан игровой ID.",

                ephemeral=True

            )

            return


        await interaction.response.send_message(

            f"🆔 Твой ID: `{standoff_id}`",

            ephemeral=True

        )


    # ------------------------------------------------------

    # ОТПРАВИТЬ РЕЗУЛЬТАТЫ

    # ------------------------------------------------------

    @discord.ui.button(

        label="📤 Отправить результаты",

        style=discord.ButtonStyle.success,

        custom_id="send_match_results"

    )

    async def send_results(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button

    ):

        await interaction.response.send_modal(

            ResultsModal(

                self.match_id

            )

        )


# ==========================================================
# ФОРМА РЕЗУЛЬТАТОВ
# ==========================================================

class ResultsModal(discord.ui.Modal):

    def __init__(self, match_id):

        super().__init__(

            title="Отправить результаты"

        )


        self.match_id = match_id


        self.result = discord.ui.TextInput(

            label="Результат матча",

            placeholder="Например: Team T 13 - 9 Team CT",

            required=True,

            max_length=100

        )


        self.add_item(

            self.result

        )


    async def on_submit(

        self,

        interaction: discord.Interaction

    ):

        await interaction.response.send_message(

            "✅ Результат отправлен.",

            ephemeral=True

        )


        # Через 5 минут удаляем войсы

        asyncio.create_task(

            delete_match_voices_after_delay(

                interaction.client,

                interaction.guild,

                self.match_id

            )

        )


# ==========================================================
# УДАЛЕНИЕ ВОЙСОВ ЧЕРЕЗ 5 МИНУТ
# ==========================================================

async def delete_match_voices_after_delay(

    bot,

    guild,

    match_id

):

    await asyncio.sleep(

        VOICE_DELETE_DELAY

    )


    try:

        match = bot.db.get_match(

            match_id

        )


        if not match:

            return


        voice_ids = [

            match["voice1_id"],

            match["voice2_id"]

        ]


        for voice_id in voice_ids:

            if not voice_id:

                continue


            channel = guild.get_channel(

                voice_id

            )


            if channel:

                try:

                    await channel.delete(

                        reason="Матч завершён"

                    )

                except discord.NotFound:

                    pass


        # Удаляем активный пик

        active_picks.pop(

            guild.id,

            None

        )


    except Exception as error:

        print(

            f"[PICK] Ошибка удаления войсов: {error}"

        )
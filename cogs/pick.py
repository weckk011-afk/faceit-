# ==========================================================
# PICK.PY
# СИСТЕМА ПИКА ИГРОКОВ FACEIT LIKE
# ==========================================================

import discord
import config


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

        # Все 10 игроков
        self.players = players

        # Капитаны
        self.captain_a = None
        self.captain_b = None

        # Команды
        self.team_a = []
        self.team_b = []

        # Кто ходит сейчас
        self.turn = None

        # Карта
        self.maps = config.MAP_POOL.copy()
        self.selected_map = None

        # Сообщения
        self.pick_message = None
        self.map_message = None

        # Завершён ли пик
        self.finished = False


# ==========================================================
# ЗАПУСК ПИКА
# ==========================================================

async def start_pick(bot, guild, players):

    if len(players) != 10:

        print(
            f"[PICK] Ошибка: для матча нужно 10 игроков, "
            f"сейчас {len(players)}"
        )

        return


    # Создаём сессию
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


    # Первым ходит капитан A
    session.turn = session.captain_a.id


    # Сохраняем активную сессию
    active_picks[guild.id] = session


    # Канал для матчей
    channel = bot.get_channel(
        config.MATCH_CHANNEL_ID
    )


    if channel is None:

        print(
            "[PICK] Ошибка: MATCH_CHANNEL_ID не найден"
        )

        return


    # Создаём Embed
    embed = discord.Embed(

        title="🎮 НОВЫЙ МАТЧ НАЙДЕН",

        description=(

            "🔥 Собрано 10 игроков!\n\n"

            f"🔵 **Капитан Team A:** "
            f"{session.captain_a.mention}\n"

            f"🔴 **Капитан Team B:** "
            f"{session.captain_b.mention}\n\n"

            "🎯 Начинается пик игроков.\n"

            f"👉 Сейчас ходит "
            f"{session.captain_a.mention}"

        ),

        color=discord.Color.blue()
    )


    # Отправляем сообщение
    message = await channel.send(

        embed=embed,

        view=PickPlayerView(
            guild.id
        )
    )


    session.pick_message = message


# ==========================================================
# КНОПКА «ПИКНУТЬ ИГРОКА»
# ==========================================================

class PickPlayerView(
    discord.ui.View
):


    def __init__(
        self,
        guild_id
    ):

        super().__init__(
            timeout=None
        )

        self.guild_id = guild_id


    @discord.ui.button(

        label="🎯 Пикнуть игрока",

        style=discord.ButtonStyle.primary,

        custom_id="pick_player_button"
    )
    async def pick_player(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button
    ):


        # Получаем сессию
        session = active_picks.get(
            self.guild_id
        )


        # Если сессии нет
        if session is None:

            await interaction.response.send_message(

                "❌ Активный матч не найден.",

                ephemeral=True
            )

            return


        # Если пик уже завершён
        if session.finished:

            await interaction.response.send_message(

                "❌ Пик уже завершён.",

                ephemeral=True
            )

            return


        # Пользователь
        user = interaction.user


        # Проверяем капитана
        if user.id not in [

            session.captain_a.id,

            session.captain_b.id

        ]:

            await interaction.response.send_message(

                "❌ Только капитаны могут выбирать игроков.",

                ephemeral=True
            )

            return


        # Проверяем очередь хода
        if user.id != session.turn:

            current_captain = (

                session.captain_a

                if session.turn == session.captain_a.id

                else session.captain_b
            )


            await interaction.response.send_message(

                f"⏳ Сейчас ход капитана "
                f"{current_captain.mention}",

                ephemeral=True
            )

            return


        # Получаем свободных игроков
        available_players = [

            player

            for player in session.players

            if player not in session.team_a

            and player not in session.team_b

        ]


        # Если игроков не осталось
        if not available_players:

            await finish_pick(

                interaction.client,

                session
            )

            return


        # Открываем меню выбора
        await interaction.response.send_message(

            "🎯 **Выберите игрока:**",

            view=PlayerSelectView(

                guild_id=self.guild_id,

                players=available_players,

                captain_id=user.id
            ),

            ephemeral=True
        )


# ==========================================================
# ВЫБОР ИГРОКА ИЗ МЕНЮ
# ==========================================================

class PlayerSelectView(

    discord.ui.View
):


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

        self.captain_id = captain_id


        # Создаём варианты
        options = []


        for player in players:

            options.append(

                discord.SelectOption(

                    label=player.display_name[:100],

                    value=str(player.id),

                    description=f"Выбрать {player.display_name}"[:100]
                )
            )


        # Меню
        select = discord.ui.Select(

            placeholder="Выберите игрока",

            options=options,

            min_values=1,

            max_values=1
        )


        # Callback
        select.callback = self.select_player


        # Добавляем меню
        self.add_item(select)


    async def select_player(

        self,

        interaction: discord.Interaction
    ):


        # Получаем сессию
        session = active_picks.get(

            self.guild_id
        )


        if session is None:

            await interaction.response.send_message(

                "❌ Матч не найден.",

                ephemeral=True
            )

            return


        # Проверяем, что выбирает именно капитан
        if interaction.user.id != self.captain_id:

            await interaction.response.send_message(

                "❌ Только капитан может выбрать игрока.",

                ephemeral=True
            )

            return


        # Проверяем, что сейчас его ход
        if session.turn != interaction.user.id:

            await interaction.response.send_message(

                "❌ Сейчас ход другого капитана.",

                ephemeral=True
            )

            return


        # Получаем ID выбранного игрока
        selected_id = int(

            self.children[0].values[0]
        )


        # Находим игрока
        selected_player = discord.utils.get(

            session.players,

            id=selected_id
        )


        if selected_player is None:

            await interaction.response.send_message(

                "❌ Игрок не найден.",

                ephemeral=True
            )

            return


        # Проверяем, что игрок ещё свободен
        if (

            selected_player in session.team_a

            or selected_player in session.team_b

        ):

            await interaction.response.send_message(

                "❌ Этот игрок уже выбран.",

                ephemeral=True
            )

            return


        # Если ходил капитан A
        if interaction.user.id == session.captain_a.id:

            session.team_a.append(

                selected_player
            )


            session.turn = session.captain_b.id


            next_captain = session.captain_b


        # Если ходил капитан B
        else:

            session.team_b.append(

                selected_player
            )


            session.turn = session.captain_a.id


            next_captain = session.captain_a


        # Сообщение капитану
        await interaction.response.send_message(

            f"✅ Ты выбрал "
            f"{selected_player.mention}\n\n"

            f"⏳ Теперь ходит "
            f"{next_captain.mention}",

            ephemeral=True
        )


        # Проверяем конец пика
        await check_pick_end(

            interaction.client,

            session
        )


# ==========================================================
# ПРОВЕРКА ЗАВЕРШЕНИЯ ПИКА
# ==========================================================

async def check_pick_end(

    bot,

    session
):


    # Если в каждой команде по 5 игроков
    if (

        len(session.team_a) == 5

        and len(session.team_b) == 5

    ):

        await finish_pick(

            bot,

            session
        )


# ==========================================================
# ЗАВЕРШЕНИЕ ПИКА И ВЫБОР КАРТЫ
# ==========================================================

async def finish_pick(

    bot,

    session
):


    # Чтобы не вызвать дважды
    if session.finished:

        return


    # Пик игроков завершён
    session.finished = True


    # Получаем канал
    channel = bot.get_channel(

        config.MATCH_CHANNEL_ID
    )


    if channel is None:

        return


    # Формируем список Team A
    team_a_text = "\n".join(

        player.mention

        for player in session.team_a
    )


    # Формируем список Team B
    team_b_text = "\n".join(

        player.mention

        for player in session.team_b
    )


    # Embed
    embed = discord.Embed(

        title="🎯 ПИК ИГРОКОВ ЗАВЕРШЁН",

        color=discord.Color.green()
    )


    embed.add_field(

        name="🔵 TEAM A",

        value=team_a_text,

        inline=True
    )


    embed.add_field(

        name="🔴 TEAM B",

        value=team_b_text,

        inline=True
    )


    embed.set_footer(

        text="Теперь капитаны должны выбрать карту"
    )


    # Отправляем сообщение
    await channel.send(

        embed=embed,

        view=MapPickView(

            session.guild_id
        )
    )


# ==========================================================
# КНОПКА ВЫБОРА КАРТЫ
# ==========================================================

class MapPickView(

    discord.ui.View
):


    def __init__(

        self,

        guild_id
    ):

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


        # Получаем сессию
        session = active_picks.get(

            self.guild_id
        )


        if session is None:

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


        # Отправляем меню карты
        await interaction.response.send_message(

            "🗺 **Выберите карту:**",

            view=MapSelectView(

                self.guild_id
            ),

            ephemeral=True
        )


# ==========================================================
# МЕНЮ ВЫБОРА КАРТЫ
# ==========================================================

class MapSelectView(

    discord.ui.View
):


    def __init__(

        self,

        guild_id
    ):

        super().__init__(

            timeout=60
        )


        self.guild_id = guild_id


        # Карты из config.py
        options = [

            discord.SelectOption(

                label=map_name,

                value=map_name
            )

            for map_name in config.MAP_POOL
        ]


        # Меню
        select = discord.ui.Select(

            placeholder="Выберите карту",

            options=options,

            min_values=1,

            max_values=1
        )


        # Callback
        select.callback = self.choose


        # Добавляем
        self.add_item(select)


    async def choose(

        self,

        interaction: discord.Interaction
    ):


        # Получаем сессию
        session = active_picks.get(

            self.guild_id
        )


        if session is None:

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

                "❌ Только капитаны могут выбрать карту.",

                ephemeral=True
            )

            return


        # Если карта уже выбрана
        if session.selected_map is not None:

            await interaction.response.send_message(

                "❌ Карта уже выбрана.",

                ephemeral=True
            )

            return


        # Получаем выбранную карту
        selected_map = self.children[0].values[0]


        # Сохраняем карту
        session.selected_map = selected_map


        # Ответ
        await interaction.response.send_message(

            f"✅ Выбрана карта: **{selected_map}**",

            ephemeral=True
        )


        # Создаём итоговую карточку
        await send_match_card(

            interaction.client,

            session
        )


# ==========================================================
# ИТОГОВАЯ КАРТОЧКА МАТЧА
# ==========================================================

async def send_match_card(

    bot,

    session
):


    # Получаем канал
    channel = bot.get_channel(

        config.MATCH_CHANNEL_ID
    )


    if channel is None:

        return


    # Team A
    team_a_text = "\n".join(

        player.mention

        for player in session.team_a
    )


    # Team B
    team_b_text = "\n".join(

        player.mention

        for player in session.team_b
    )


    # Embed
    embed = discord.Embed(

        title="🔥 МАТЧ ГОТОВ",

        description=(

            f"🗺 **Карта:** "
            f"**{session.selected_map}**"

        ),

        color=discord.Color.gold()
    )


    embed.add_field(

        name="🔵 TEAM A",

        value=team_a_text,

        inline=True
    )


    embed.add_field(

        name="🔴 TEAM B",

        value=team_b_text,

        inline=True
    )


    embed.set_footer(

        text="Используйте кнопки ниже"
    )


    # Отправляем карточку
    await channel.send(

        embed=embed,

        view=MatchButtons()
    )


# ==========================================================
# КНОПКИ МАТЧА
# ==========================================================

class MatchButtons(

    discord.ui.View
):


    def __init__(

        self
    ):

        super().__init__(

            timeout=None
        )


    # ======================================================
    # ПОЛУЧИТЬ ID
    # ======================================================

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


        # Получаем игрока из базы
        player = interaction.client.db.get_player(

            interaction.guild.id,

            interaction.user.id
        )


        # Если игрок не зарегистрирован
        if player is None:

            await interaction.response.send_message(

                "❌ Ты не зарегистрирован в боте.",

                ephemeral=True
            )

            return


        # Если ID отсутствует
        if not player["standoff_id"]:

            await interaction.response.send_message(

                "❌ У тебя не указан Standoff 2 ID.",

                ephemeral=True
            )

            return


        # Отправляем ID
        await interaction.response.send_message(

            f"🆔 Твой Standoff 2 ID:\n"
            f"`{player['standoff_id']}`",

            ephemeral=True
        )


    # ======================================================
    # ОТПРАВИТЬ РЕЗУЛЬТАТЫ
    # ======================================================

    @discord.ui.button(

        label="📤 Отправить результаты",

        style=discord.ButtonStyle.success,

        custom_id="send_match_result"
    )
    async def send_results(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button
    ):


        # Открываем форму
        await interaction.response.send_modal(

            ResultModal()
        )


# ==========================================================
# ФОРМА РЕЗУЛЬТАТА
# ==========================================================

class ResultModal(

    discord.ui.Modal,

    title="📤 Отправить результаты"
):


    result = discord.ui.TextInput(

        label="Результат матча",

        placeholder="Например: Team A 13 : 8 Team B",

        required=True,

        max_length=100
    )


    screenshot = discord.ui.TextInput(

        label="Ссылка на скриншот",

        placeholder="Вставьте ссылку на скриншот результата",

        required=False,

        max_length=500
    )


    async def on_submit(

        self,

        interaction: discord.Interaction
    ):


        # Отправляем результат
        await interaction.response.send_message(

            "✅ Результат отправлен.",

            ephemeral=True
        )


        # Канал результатов
        channel = interaction.client.get_channel(

            config.RESULTS_CHANNEL_ID
        )


        if channel is None:

            return


        # Embed результата
        embed = discord.Embed(

            title="📊 РЕЗУЛЬТАТ МАТЧА",

            color=discord.Color.green()
        )


        embed.add_field(

            name="🏆 Результат",

            value=self.result.value,

            inline=False
        )


        if self.screenshot.value:

            embed.add_field(

                name="🖼 Скриншот",

                value=self.screenshot.value,

                inline=False
            )


        embed.add_field(

            name="👤 Отправил",

            value=interaction.user.mention,

            inline=False
        )


        await channel.send(

            embed=embed
        )
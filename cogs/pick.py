# ==========================================================
# СИСТЕМА ПИКОВ ИГРОКОВ FACEIT LIKE
# ==========================================================

active_picks = {}


class PickSession:
    def __init__(self, guild_id, players):
        self.guild_id = guild_id

        # все 10 игроков
        self.players = players

        # капитаны
        self.captain_a = None
        self.captain_b = None

        # команды
        self.team_a = []
        self.team_b = []

        self.turn = None

        # карта
        self.maps = config.MAP_POOL.copy()
        self.selected_map = None


# ==============================
# запуск матча
# ==============================

async def start_pick(bot, guild, players):

    session = PickSession(
        guild.id,
        players
    )


    # первые два игрока становятся капитанами
    session.captain_a = players[0]
    session.captain_b = players[1]

    session.team_a.append(players[0])
    session.team_b.append(players[1])


    active_picks[guild.id] = session


    channel = bot.get_channel(config.MATCH_CHANNEL_ID)


    embed = discord.Embed(
        title="🎮 Новый матч найден",
        description=(
            "10 игроков собрано!\n\n"
            f"🔵 Капитан A: {players[0].mention}\n"
            f"🔴 Капитан B: {players[1].mention}\n\n"
            "Начинается пик игроков."
        ),
        color=discord.Color.blue()
    )


    await channel.send(
        embed=embed,
        view=PickPlayerView(guild.id)
    )



# ==========================================================
# КНОПКИ ПИКА
# ==========================================================


class PickPlayerView(discord.ui.View):

    def __init__(self,guild_id):
        super().__init__(timeout=None)
        self.guild_id=guild_id


    @discord.ui.button(
        label="Пикнуть игрока",
        style=discord.ButtonStyle.primary,
        custom_id="pick_player"
    )
    async def pick(
        self,
        interaction:discord.Interaction,
        button:discord.ui.Button
    ):


        session = active_picks.get(self.guild_id)


        if not session:
            await interaction.response.send_message(
                "Матч не найден",
                ephemeral=True
            )
            return



        user = interaction.user



        # проверка капитана

        if user.id not in [
            session.captain_a.id,
            session.captain_b.id
        ]:

            await interaction.response.send_message(
                "Ты не капитан",
                ephemeral=True
            )
            return



        # кто ходит

        if session.turn is None:
            session.turn = user.id


        if session.turn != user.id:

            await interaction.response.send_message(
                "Сейчас ход другого капитана",
                ephemeral=True
            )
            return



        # список доступных игроков


        available = [
            p for p in session.players
            if p not in session.team_a
            and p not in session.team_b
        ]



        if not available:

            await finish_pick(interaction.client,session)
            return



        await interaction.response.send_message(
            "Выберите игрока:",
            view=PlayerSelectView(
                self.guild_id,
                available
            ),
            ephemeral=True
        )




class PlayerSelectView(discord.ui.View):

    def __init__(
        self,
        guild_id,
        players
    ):

        super().__init__(timeout=60)

        self.guild_id=guild_id


        options=[]

        for p in players:

            options.append(
                discord.SelectOption(
                    label=p.display_name,
                    value=str(p.id)
                )
            )


        self.select = discord.ui.Select(
            placeholder="Игрок",
            options=options
        )


        self.select.callback=self.select_player

        self.add_item(self.select)



    async def select_player(
        self,
        interaction:discord.Interaction
    ):


        session=active_picks[self.guild_id]


        player_id=int(
            self.select.values[0]
        )


        player=discord.utils.get(
            session.players,
            id=player_id
        )



        if interaction.user.id == session.captain_a.id:

            session.team_a.append(player)

            session.turn=session.captain_b.id


        else:

            session.team_b.append(player)

            session.turn=session.captain_a.id



        await interaction.response.send_message(
            f"✅ {player.mention} выбран",
            ephemeral=True
        )


        await check_pick_end(interaction.client,session)





async def check_pick_end(bot,session):


    if len(session.team_a)==5 and len(session.team_b)==5:

        await finish_pick(
            bot,
            session
        )



async def finish_pick(bot,session):


    channel=bot.get_channel(
        config.MATCH_CHANNEL_ID
    )


    embed=discord.Embed(
        title="🎯 Пики завершены",
        description=(
            "🔵 Team A\n"
            +
            "\n".join(
                x.mention for x in session.team_a
            )
            +
            "\n\n"
            "🔴 Team B\n"
            +
            "\n".join(
                x.mention for x in session.team_b
            )
            +
            "\n\nТеперь выбор карты."
        ),
        color=discord.Color.green()
    )


    await channel.send(
        embed=embed,
        view=MapPickView(session.guild_id)
    )





# ==========================================================
# ВЫБОР КАРТЫ
# ==========================================================


class MapPickView(discord.ui.View):

    def __init__(self,guild_id):

        super().__init__(timeout=None)

        self.guild_id=guild_id



    @discord.ui.button(
        label="Выбрать карту",
        style=discord.ButtonStyle.green,
        custom_id="map_pick"
    )
    async def map_pick(
        self,
        interaction,
        button
    ):


        session=active_picks[self.guild_id]


        await interaction.response.send_message(
            "Выберите карту",
            view=MapSelectView(self.guild_id),
            ephemeral=True
        )





class MapSelectView(discord.ui.View):

    def __init__(self,guild_id):

        super().__init__(timeout=60)

        self.guild_id=guild_id


        options=[
            discord.SelectOption(
                label=m,
                value=m
            )
            for m in config.MAP_POOL
        ]


        select=discord.ui.Select(
            placeholder="Карта",
            options=options
        )


        select.callback=self.choose

        self.add_item(select)



    async def choose(self,interaction):


        session=active_picks[self.guild_id]


        session.selected_map=self.children[0].values[0]


        await interaction.response.send_message(
            "Карта выбрана",
            ephemeral=True
        )


        await send_match_card(
            interaction.client,
            session
        )





# ==========================================================
# КАРТОЧКА МАТЧА
# ==========================================================


async def send_match_card(bot,session):


    channel=bot.get_channel(
        config.MATCH_CHANNEL_ID
    )


    embed=discord.Embed(
        title="🔥 Матч готов",
        color=discord.Color.gold()
    )


    embed.add_field(
        name="🗺 Карта",
        value=session.selected_map,
        inline=False
    )


    embed.add_field(
        name="🔵 Team A",
        value="\n".join(
            x.mention for x in session.team_a
        )
    )


    embed.add_field(
        name="🔴 Team B",
        value="\n".join(
            x.mention for x in session.team_b
        )
    )


    await channel.send(
        embed=embed,
        view=MatchButtons()
    )



class MatchButtons(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="🆔 Получить ID",
        style=discord.ButtonStyle.primary
    )
    async def get_id(
        self,
        interaction,
        button
    ):


        player=interaction.client.db.get_player(
            interaction.guild.id,
            interaction.user.id
        )


        if not player:

            await interaction.response.send_message(
                "Ты не зарегистрирован",
                ephemeral=True
            )

            return


        await interaction.response.send_message(
            f"🆔 Твой ID: `{player['standoff_id']}`",
            ephemeral=True
        )



    @discord.ui.button(
        label="📤 Отправить результаты",
        style=discord.ButtonStyle.green
    )
    async def results(
        self,
        interaction,
        button
    ):

        await interaction.response.send_message(
            "Отправь скрин результата в этот канал.",
            ephemeral=True
        )
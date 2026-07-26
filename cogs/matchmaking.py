import asyncio
import discord
from discord.ext import commands
from discord import app_commands

import config


# ============================================================
# ТЕКУЩИЙ МАТЧ
# ============================================================

active_draft = {}


# ============================================================
# КНОПКА ВХОДА В ЛОББИ
# ============================================================

class LobbyView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)


    @discord.ui.button(
        label="🎮 Войти в матч",
        style=discord.ButtonStyle.success,
        custom_id="join_match"
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        db = interaction.client.db
        guild = interaction.guild

        added = db.queue_add(
            guild.id,
            interaction.user.id
        )


        if not added:
            await interaction.response.send_message(
                "❌ Ты уже в ожидании матча",
                ephemeral=True
            )
            return


        await interaction.response.send_message(
            "✅ Ты добавлен в поиск матча",
            ephemeral=True
        )


        players = db.queue_list(guild.id)


        # ===============================
        # 10 ИГРОКОВ СОБРАЛОСЬ
        # ===============================

        if len(players) >= config.QUEUE_SIZE:

            ids = [
                p["user_id"]
                for p in players[:10]
            ]


            db.queue_clear_users(
                guild.id,
                ids
            )


            await start_draft(
                interaction.client,
                guild,
                ids
            )



# ============================================================
# ЗАПУСК РАСПИКА
# ============================================================


async def start_draft(bot, guild, player_ids):

    db = bot.db


    players = []


    for uid in player_ids:

        p = db.get_player(
            guild.id,
            uid
        )

        if p:
            players.append(p)



    # сортировка по elo
    players.sort(
        key=lambda x: x["elo"],
        reverse=True
    )


    captain1 = players[0]
    captain2 = players[1]


    active_draft[guild.id] = {

        "captain1": captain1["user_id"],
        "captain2": captain2["user_id"],

        "team1": [
            captain1["user_id"]
        ],

        "team2": [
            captain2["user_id"]
        ],

        "players": [
            p["user_id"]
            for p in players[2:]
        ],

        "turn": captain1["user_id"],

    }



    channel = bot.get_channel(
        config.MATCH_CHANNEL_ID
    )


    embed = discord.Embed(
        title="🎮 Новый распик",
        description=
        f"""
👑 Капитаны:

🔵 **{captain1['nickname']}**
🔴 **{captain2['nickname']}**


Ход капитана:

**{captain1['nickname']}**

Выберите игрока:
""",
        color=discord.Color.blue()
    )


    await channel.send(
        embed=embed,
        view=PickPlayerView(
            guild.id
        )
    )



# ============================================================
# ВЫБОР ИГРОКА
# ============================================================


class PickPlayerView(discord.ui.View):

    def __init__(self,guild_id):

        super().__init__(
            timeout=None
        )

        self.guild_id = guild_id



    async def interaction_check(
        self,
        interaction
    ):

        draft = active_draft.get(
            self.guild_id
        )


        if not draft:
            return False


        if interaction.user.id != draft["turn"]:

            await interaction.response.send_message(
                "❌ Сейчас не твой пик",
                ephemeral=True
            )

            return False


        return True
        # ============================================================
# КНОПКИ ИГРОКОВ ДЛЯ ПИКА
# ============================================================


class PlayerButton(discord.ui.Button):

    def __init__(
        self,
        user_id: int,
        nickname: str,
        guild_id: int
    ):

        super().__init__(
            label=nickname,
            style=discord.ButtonStyle.primary,
            custom_id=f"pick_{user_id}"
        )

        self.user_id = user_id
        self.guild_id = guild_id



    async def callback(
        self,
        interaction: discord.Interaction
    ):

        draft = active_draft.get(
            self.guild_id
        )

        if not draft:
            await interaction.response.send_message(
                "❌ Распик уже завершён",
                ephemeral=True
            )
            return


        if interaction.user.id != draft["turn"]:

            await interaction.response.send_message(
                "❌ Сейчас не твой пик",
                ephemeral=True
            )

            return



        # добавляем игрока в команду

        if draft["turn"] == draft["captain1"]:

            draft["team1"].append(
                self.user_id
            )

            draft["turn"] = draft["captain2"]


        else:

            draft["team2"].append(
                self.user_id
            )

            draft["turn"] = draft["captain1"]



        # удаляем игрока из списка

        draft["players"].remove(
            self.user_id
        )



        # если игроков больше нет
        if len(draft["players"]) == 0:

            await finish_pick(
                interaction.client,
                interaction.guild
            )

            return



        await update_pick_message(
            interaction.message,
            interaction.client,
            self.guild_id
        )



        await interaction.response.defer()



# ============================================================
# СОЗДАНИЕ КНОПОК ИГРОКОВ
# ============================================================


async def build_pick_view(
    bot,
    guild_id
):

    view = PickPlayerView(
        guild_id
    )


    draft = active_draft[guild_id]


    for uid in draft["players"]:

        player = bot.db.get_player(
            guild_id,
            uid
        )

        if player:

            view.add_item(
                PlayerButton(
                    uid,
                    player["nickname"],
                    guild_id
                )
            )


    return view



# ============================================================
# ОБНОВЛЕНИЕ СООБЩЕНИЯ ПИКА
# ============================================================


async def update_pick_message(
    message,
    bot,
    guild_id
):

    draft = active_draft[guild_id]


    player = bot.db.get_player(
        guild_id,
        draft["turn"]
    )


    embed = discord.Embed(
        title="🎮 Распик игроков",
        description=
        f"""
🔵 Тим {bot.db.get_player(
guild_id,
draft['captain1']
)['nickname']}

👤 {len(draft['team1'])}/5


🔴 Тим {bot.db.get_player(
guild_id,
draft['captain2']
)['nickname']}

👤 {len(draft['team2'])}/5


Сейчас выбирает:

👑 **{player['nickname']}**
""",
        color=discord.Color.blurple()
    )


    await message.edit(
        embed=embed,
        view=await build_pick_view(
            bot,
            guild_id
        )
    )



# ============================================================
# ЗАВЕРШЕНИЕ ПИКОВ
# ============================================================


async def finish_pick(
    bot,
    guild
):

    draft = active_draft[guild.id]


    db = bot.db


    team1 = draft["team1"]
    team2 = draft["team2"]



    match_id = db.create_match(
        guild.id,
        team1,
        team2
    )


    draft["match_id"] = match_id


    await start_map_vote(
        bot,
        guild
    )



# ============================================================
# ВЫБОР КАРТЫ
# ============================================================


class MapButton(discord.ui.Button):

    def __init__(
        self,
        map_name,
        guild_id
    ):

        super().__init__(
            label=map_name,
            style=discord.ButtonStyle.secondary
        )

        self.map_name = map_name
        self.guild_id = guild_id



    async def callback(
        self,
        interaction: discord.Interaction
    ):

        draft = active_draft[
            self.guild_id
        ]


        interaction.client.db.set_match_map(
            draft["match_id"],
            self.map_name
        )


        draft["map"] = self.map_name



        await create_match_card(
            interaction.client,
            interaction.guild
        )


        await interaction.response.send_message(
            f"🗺 Карта выбрана: **{self.map_name}**",
            ephemeral=True
        )



class MapVoteView(discord.ui.View):

    def __init__(
        self,
        guild_id
    ):

        super().__init__(
            timeout=None
        )


        for m in config.MAP_POOL:

            self.add_item(
                MapButton(
                    m,
                    guild_id
                )
            )



async def start_map_vote(
    bot,
    guild
):

    channel = bot.get_channel(
        config.MATCH_CHANNEL_ID
    )


    embed = discord.Embed(
        title="🗺 Выбор карты",
        description=
        "Капитаны выбирают карту",
        color=discord.Color.green()
    )


    await channel.send(
        embed=embed,
        view=MapVoteView(
            guild.id
        )
    )
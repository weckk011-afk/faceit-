import json

import discord
from discord import app_commands
from discord.ext import commands

import config


def balance_teams(players: list[dict]) -> tuple[list[dict], list[dict]]:
    """Змейка-драфт по ELO: сильнейший в команду A, следующие двое — в B и A по очереди,
    так суммарный рейтинг команд получается максимально близким."""
    ordered = sorted(players, key=lambda p: p["elo"], reverse=True)
    team_a, team_b = [], []
    turn_a = True
    for p in ordered:
        if turn_a:
            team_a.append(p)
        else:
            team_b.append(p)
        turn_a = not turn_a
    return team_a, team_b


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


class VetoView(discord.ui.View):
    """Интерактивное вето карт кнопками — по очереди капитаны банят карты,
    пока не останется одна."""

    def __init__(self, cog: "MatchCog", match_id: int, captain1: int, captain2: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.match_id = match_id
        self.captains = [captain1, captain2]
        self.turn_index = 0  # чей ход банить
        self.remaining_maps = list(config.MAP_POOL)
        for map_name in self.remaining_maps:
            self.add_item(self._make_button(map_name))

    def _make_button(self, map_name: str) -> discord.ui.Button:
        button = discord.ui.Button(label=map_name, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            await self._on_ban(interaction, map_name, button)

        button.callback = callback
        return button

    async def _on_ban(self, interaction: discord.Interaction, map_name: str, button: discord.ui.Button):
        current_captain = self.captains[self.turn_index % 2]
        if interaction.user.id != current_captain:
            await interaction.response.send_message(
                f"Сейчас не твоя очередь банить. Ходит <@{current_captain}>.",
                ephemeral=True,
            )
            return

        self.remaining_maps.remove(map_name)
        button.disabled = True
        button.style = discord.ButtonStyle.danger
        button.label = f"❌ {map_name}"
        self.turn_index += 1

        if len(self.remaining_maps) == 1:
            final_map = self.remaining_maps[0]
            for child in self.children:
                child.disabled = True
            self.cog.db.set_match_map(self.match_id, final_map)
            await interaction.response.edit_message(
                content=f"🗺️ Карта выбрана: **{final_map}**", view=self
            )
            self.stop()
            await self.cog.on_map_decided(self.match_id, final_map)
            return

        next_captain = self.captains[self.turn_index % 2]
        await interaction.response.edit_message(
            content=f"Забанена **{map_name}**. Ход <@{next_captain}> "
                    f"({len(self.remaining_maps)} карт осталось).",
            view=self,
        )


class MatchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def start_match(self, guild: discord.Guild, player_ids: list[int]):
        players = []
        for uid in player_ids:
            row = self.db.get_player(guild.id, uid)
            if row is None:
                self.db.create_player(guild.id, uid, str(uid))
                row = self.db.get_player(guild.id, uid)
            players.append(dict(row))

        team_a, team_b = balance_teams(players)
        team_a_ids = [p["user_id"] for p in team_a]
        team_b_ids = [p["user_id"] for p in team_b]

        match_id = self.db.create_match(guild.id, team_a_ids, team_b_ids)

        category = await guild.create_category(f"{config.MATCH_CATEGORY_PREFIX} #{match_id}")
        text_channel = await category.create_text_channel(f"матч-{match_id}-инфо")
        voice1 = await category.create_voice_channel(f"Команда A — матч {match_id}")
        voice2 = await category.create_voice_channel(f"Команда B — матч {match_id}")
        self.db.set_match_channels(match_id, category.id, text_channel.id, voice1.id, voice2.id)

        # капитаны — игрок с наивысшим ELO в каждой команде
        captain_a = max(team_a, key=lambda p: p["elo"])
        captain_b = max(team_b, key=lambda p: p["elo"])

        elo_a = sum(p["elo"] for p in team_a) / len(team_a)
        elo_b = sum(p["elo"] for p in team_b) / len(team_b)

        embed = discord.Embed(
            title=f"Матч #{match_id} собран!",
            description=f"Голосовые каналы: {voice1.mention} / {voice2.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name=f"Команда A (капитан {captain_a['nickname']}, ср. ELO {elo_a:.0f})",
            value="\n".join(f"<@{p['user_id']}> — {p['elo']}" for p in team_a),
            inline=True,
        )
        embed.add_field(
            name=f"Команда B (капитан {captain_b['nickname']}, ср. ELO {elo_b:.0f})",
            value="\n".join(f"<@{p['user_id']}> — {p['elo']}" for p in team_b),
            inline=True,
        )
        mentions = " ".join(f"<@{uid}>" for uid in player_ids)
        await text_channel.send(content=mentions, embed=embed)

        # авто-перемещение игроков, если они уже в голосовом канале на сервере
        for p in team_a:
            member = guild.get_member(p["user_id"])
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(voice1)
                except discord.HTTPException:
                    pass
        for p in team_b:
            member = guild.get_member(p["user_id"])
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(voice2)
                except discord.HTTPException:
                    pass

        view = VetoView(self, match_id, captain_a["user_id"], captain_b["user_id"])
        await text_channel.send(
            content=f"🗺️ **Вето карт.** Первым банит <@{captain_a['user_id']}>.",
            view=view,
        )

    async def on_map_decided(self, match_id: int, map_name: str):
        match = self.db.get_match(match_id)
        channel = self.bot.get_channel(match["text_channel_id"])
        if channel:
            await channel.send(
                f"Карта для матча #{match_id}: **{map_name}**. Удачи, GLHF! "
                f"Когда матч завершится, капитан или админ вводит `/matchscore {match_id} <A/B>`."
            )

    @app_commands.command(name="matchscore", description="Сообщить результат матча и обновить рейтинг")
    @app_commands.describe(match_id="ID матча", winner="Победившая команда: A или B")
    @app_commands.choices(winner=[
        app_commands.Choice(name="Команда A", value="A"),
        app_commands.Choice(name="Команда B", value="B"),
    ])
    async def matchscore(self, interaction: discord.Interaction, match_id: int, winner: app_commands.Choice[str]):
        match = self.db.get_match(match_id)
        if match is None or match["status"] != "active":
            await interaction.response.send_message("Матч не найден или уже завершён.", ephemeral=True)
            return

        team_a = json.loads(match["team1"])
        team_b = json.loads(match["team2"])
        all_players = team_a + team_b

        if interaction.user.id not in all_players and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Только участник матча или админ может сообщить результат.", ephemeral=True
            )
            return

        guild_id = interaction.guild_id
        elo_a = sum(self.db.get_player(guild_id, uid)["elo"] for uid in team_a) / len(team_a)
        elo_b = sum(self.db.get_player(guild_id, uid)["elo"] for uid in team_b) / len(team_b)

        a_won = winner.value == "A"
        exp_a = expected_score(elo_a, elo_b)
        exp_b = 1 - exp_a
        score_a = 1 if a_won else 0
        score_b = 1 if not a_won else 0

        for uid in team_a:
            player = self.db.get_player(guild_id, uid)
            new_elo = round(player["elo"] + config.ELO_K * (score_a - exp_a))
            self.db.record_result(guild_id, uid, a_won, new_elo)
        for uid in team_b:
            player = self.db.get_player(guild_id, uid)
            new_elo = round(player["elo"] + config.ELO_K * (score_b - exp_b))
            self.db.record_result(guild_id, uid, not a_won, new_elo)

        self.db.finish_match(match_id, 1 if a_won else 2)

        await interaction.response.send_message(
            f"✅ Матч #{match_id} завершён. Победила команда **{winner.value}**. Рейтинг обновлён."
        )

        # удаляем каналы матча через минуту, чтобы игроки успели прочитать
        category = interaction.guild.get_channel(match["category_id"])
        if category:
            for ch in list(category.channels) + [category]:
                try:
                    await ch.delete(reason=f"Матч #{match_id} завершён")
                except discord.HTTPException:
                    pass

    @app_commands.command(name="cancelmatch", description="Отменить матч без изменения рейтинга (админ)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cancelmatch(self, interaction: discord.Interaction, match_id: int):
        match = self.db.get_match(match_id)
        if match is None:
            await interaction.response.send_message("Матч не найден.", ephemeral=True)
            return
        self.db.cancel_match(match_id)
        category = interaction.guild.get_channel(match["category_id"])
        if category:
            for ch in list(category.channels) + [category]:
                try:
                    await ch.delete(reason=f"Матч #{match_id} отменён")
                except discord.HTTPException:
                    pass
        await interaction.response.send_message(f"Матч #{match_id} отменён.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchCog(bot))

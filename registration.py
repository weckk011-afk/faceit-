import discord
from discord import app_commands
from discord.ext import commands

import config


class Registration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    def ensure_player(self, guild_id: int, user: discord.abc.User):
        player = self.db.get_player(guild_id, user.id)
        if player is None:
            self.db.create_player(guild_id, user.id, user.display_name)
            player = self.db.get_player(guild_id, user.id)
        return player

    @app_commands.command(name="register", description="Зарегистрироваться в системе рейтинга")
    @app_commands.describe(standoff_id="Твой ник или ID в Standoff 2 (необязательно)")
    async def register(self, interaction: discord.Interaction, standoff_id: str = None):
        existing = self.db.get_player(interaction.guild_id, interaction.user.id)
        if existing:
            if standoff_id and not existing["standoff_id"]:
                self.db.set_standoff_id(interaction.guild_id, interaction.user.id, standoff_id)
            await interaction.response.send_message(
                "Ты уже зарегистрирован. Используй /profile чтобы посмотреть статистику "
                "или /setuid чтобы обновить ник в Standoff 2.",
                ephemeral=True,
            )
            return
        self.db.create_player(
            interaction.guild_id, interaction.user.id, interaction.user.display_name, standoff_id
        )
        extra = f" Ник в Standoff 2: **{standoff_id}**." if standoff_id else ""
        await interaction.response.send_message(
            f"Готово! Ты зарегистрирован со стартовым рейтингом **{config.START_ELO}**.{extra}",
            ephemeral=True,
        )

    @app_commands.command(name="setuid", description="Указать/обновить свой ник или ID в Standoff 2")
    @app_commands.describe(standoff_id="Твой ник или ID в Standoff 2")
    async def setuid(self, interaction: discord.Interaction, standoff_id: str):
        player = self.ensure_player(interaction.guild_id, interaction.user)
        self.db.set_standoff_id(interaction.guild_id, interaction.user.id, standoff_id)
        await interaction.response.send_message(
            f"Ник в Standoff 2 обновлён: **{standoff_id}**.", ephemeral=True
        )

    @app_commands.command(name="profile", description="Показать профиль игрока")
    @app_commands.describe(user="Чей профиль показать (по умолчанию — твой)")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        player = self.db.get_player(interaction.guild_id, target.id)
        if player is None:
            await interaction.response.send_message(
                f"{target.display_name} ещё не зарегистрирован (/register).",
                ephemeral=True,
            )
            return

        total = player["wins"] + player["losses"]
        winrate = (player["wins"] / total * 100) if total else 0.0

        embed = discord.Embed(
            title=f"Профиль — {player['nickname']}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        if player["standoff_id"]:
            embed.add_field(name="Ник в Standoff 2", value=player["standoff_id"], inline=False)
        embed.add_field(name="Рейтинг (ELO)", value=str(player["elo"]), inline=True)
        embed.add_field(name="Матчей", value=str(player["matches_played"]), inline=True)
        embed.add_field(name="Winrate", value=f"{winrate:.1f}%", inline=True)
        embed.add_field(name="Победы", value=str(player["wins"]), inline=True)
        embed.add_field(name="Поражения", value=str(player["losses"]), inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Топ игроков по рейтингу")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = self.db.get_leaderboard(interaction.guild_id, limit=10)
        if not rows:
            await interaction.response.send_message("Пока никто не зарегистрирован.")
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            lines.append(f"**{i}.** {row['nickname']} — {row['elo']} ELO "
                         f"({row['wins']}W/{row['losses']}L)")

        embed = discord.Embed(
            title="🏆 Топ игроков сервера",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Registration(bot))

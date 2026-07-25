import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.profile_card import generate_profile_card


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

    async def get_or_create_player_role(self, guild: discord.Guild) -> discord.Role:
        role = discord.utils.get(guild.roles, name=config.PLAYER_ROLE_NAME)
        if role is None:
            role = await guild.create_role(
                name=config.PLAYER_ROLE_NAME,
                reason="Роль для зарегистрированных игроков (создана автоматически ботом)",
            )
        return role

    async def grant_player_role(self, interaction: discord.Interaction):
        role = await self.get_or_create_player_role(interaction.guild)
        member = interaction.user
        if isinstance(member, discord.Member) and role not in member.roles:
            try:
                await member.add_roles(role, reason="Успешная регистрация в /register")
            except discord.Forbidden:
                pass  # у бота не хватает прав/роль бота ниже целевой — админ должен поправить вручную

    @app_commands.command(name="register", description="Зарегистрироваться в системе рейтинга")
    @app_commands.describe(standoff_id="Твой ник или ID в Standoff 2 (обязательно)")
    async def register(self, interaction: discord.Interaction, standoff_id: str):
        existing = self.db.get_player(interaction.guild_id, interaction.user.id)
        if existing:
            self.db.set_standoff_id(interaction.guild_id, interaction.user.id, standoff_id)
            await self.grant_player_role(interaction)
            await interaction.response.send_message(
                "Ты уже зарегистрирован. Используй /profile чтобы посмотреть статистику "
                "или /setuid чтобы обновить ник в Standoff 2.",
                ephemeral=True,
            )
            return
        self.db.create_player(
            interaction.guild_id, interaction.user.id, interaction.user.display_name, standoff_id
        )
        await self.grant_player_role(interaction)
        extra = f" Ник в Standoff 2: **{standoff_id}**."
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
    @app_commands.command(name="setkd", description="Указать свою статистику килы/смерти (K/D)")
    @app_commands.describe(kills="Количество килов (суммарно)", deaths="Количество смертей (суммарно)")
    async def setkd(self, interaction: discord.Interaction, kills: int, deaths: int):
        if kills < 0 or deaths < 0:
            await interaction.response.send_message("Числа не могут быть отрицательными.", ephemeral=True)
            return
        player = self.db.get_player(interaction.guild_id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                "Сначала зарегистрируйся: /register", ephemeral=True
            )
            return
        self.db.set_kd(interaction.guild_id, interaction.user.id, kills, deaths)
        await interaction.response.send_message(
            f"Обновлено: K/D {kills}/{deaths}.", ephemeral=True
        )
   
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

        await interaction.response.defer()
        buffer = await generate_profile_card(target, player)
        file = discord.File(buffer, filename="profile.png")
        await interaction.followup.send(file=file)

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

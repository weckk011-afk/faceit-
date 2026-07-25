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

    async def get_or_create_player_role(
        self, guild: discord.Guild
    ) -> discord.Role:
        role = discord.utils.get(guild.roles, name=config.PLAYER_ROLE_NAME)
        if role is None:
            role = await guild.create_role(
                name=config.PLAYER_ROLE_NAME,
                reason=(
                    "Роль для зарегистрированных игроков (создана"
                    " автоматически ботом)"
                ),
            )
        return role

    async def grant_player_role(self, interaction: discord.Interaction):
        role = await self.get_or_create_player_role(interaction.guild)
        member = interaction.user
        if isinstance(member, discord.Member) and role not in member.roles:
            try:
                await member.add_roles(
                    role, reason="Успешная регистрация в /register"
                )
            except discord.Forbidden:
                pass

    @app_commands.command(
        name="register", description="Зарегистрироваться в системе рейтинга"
    )
    @app_commands.describe(
        standoff_id="Твой ник или ID в Standoff 2 (обязательно)"
    )
    async def register(
        self, interaction: discord.Interaction, standoff_id: str
    ):
        existing = self.db.get_player(
            interaction.guild_id, interaction.user.id
        )
        if existing:
            self.db.set_standoff_id(
                interaction.guild_id, interaction.user.id, standoff_id
            )
            await self.grant_player_role(interaction)
            await interaction.response.send_message(
                "Ты уже зарегистрирован. Используй /profile чтобы посмотреть"
                " статистику или /setuid чтобы обновить ник в Standoff 2.",
                ephemeral=True,
            )
            return
        self.db.create_player(
            interaction.guild_id,
            interaction.user.id,
            interaction.user.display_name,
            standoff_id,
        )
        await self.grant_player_role(interaction)
        extra = f" Ник в Standoff 2: **{standoff_id}**."
        await interaction.response.send_message(
            "Готово! Ты зарегистрирован со стартовым рейтингом"
            f" **{config.START_ELO}**.{extra}",
            ephemeral=True,
        )

    @app_commands.command(
        name="setuid",
        description="Указать/обновить свой ник или ID в Standoff 2",
    )
    @app_commands.describe(standoff_id="Твой ник или ID в Standoff 2")
    async def setuid(self, interaction: discord.Interaction, standoff_id: str):
        player = self.ensure_player(interaction.guild_id, interaction.user)
        self.db.set_standoff_id(
            interaction.guild_id, interaction.user.id, standoff_id
        )
        await interaction.response.send_message(
            f"Ник в Standoff 2 обновлён: **{standoff_id}**.", ephemeral=True
        )

    @app_commands.command(
        name="setwl", description="Установить количество побед и поражений"
    )
    @app_commands.describe(
        wins="Количество побед", losses="Количество поражений"
    )
    async def setwl(
        self, interaction: discord.Interaction, wins: int, losses: int
    ):
        if wins < 0 or losses < 0:
            await interaction.response.send_message(
                "Значения не могут быть отрицательными!", ephemeral=True
            )
            return

        player = self.db.get_player(interaction.guild_id, interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                "Сначала зарегистрируйся: /register", ephemeral=True
            )
            return

        self.db.set_wl(interaction.guild_id, interaction.user.id, wins, losses)
        await interaction.response.send_message(
            f"Обновлено: Победы/Поражения **{wins}** / **{losses}**."
        )

    @app_commands.command(name="profile", description="Показать профиль игрока")
    @app_commands.describe(
        league="Выберите лигу", user="Чей профиль показать (необязательно)"
    )
    @app_commands.choices(
        league=[
            app_commands.Choice(name="Pro", value="Pro"),
            app_commands.Choice(name="Division", value="Division"),
            app_commands.Choice(name="Prospect", value="Prospect"),
        ]
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        league: app_commands.Choice[str],
        user: discord.Member = None,
    ):
        target = user or interaction.user
        selected_league = league.value

        # Роли на сервере для каждой лиги
        REQUIRED_ROLES = {
            "Pro": "pro league",
            "Division": "division",
            "Prospect": "prospect",
        }

        required_role_name = REQUIRED_ROLES[selected_league]

        # Проверяем наличие роли у игрока
        has_role = any(
            role.name.lower() == required_role_name for role in target.roles
        )

        # Приватная ошибка (видит только отправитель)
        if not has_role:
            await interaction.response.send_message(
                f"У {target.mention} нет роли!", ephemeral=True
            )
            return

        player = self.db.get_player(interaction.guild_id, target.id)

        # Приватная ошибка (видит только отправитель)
        if player is None:
            await interaction.response.send_message(
                f"**{target.display_name}** ещё не зарегистрирован!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        buffer = await generate_profile_card(
            target, player, league_name=selected_league
        )
        file = discord.File(buffer, filename="profile.png")
        await interaction.followup.send(file=file)

    @app_commands.command(
        name="leaderboard", description="Топ игроков по рейтингу"
    )
    async def leaderboard(self, interaction: discord.Interaction):
        rows = self.db.get_leaderboard(interaction.guild_id, limit=10)
        if not rows:
            await interaction.response.send_message(
                "Пока никто не зарегистрирован."
            )
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            lines.append(
                f"**{i}.** {row['nickname']} — {row['elo']} ELO "
                f"({row['wins']}W/{row['losses']}L)"
            )

        embed = discord.Embed(
            title="🏆 Топ игроков сервера",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Registration(bot))


import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.profile_card import generate_profile_card


class RegisterModal(discord.ui.Modal, title="Регистрация"):
    nickname = discord.ui.TextInput(
        label="Никнейм",
        placeholder="Например: MegaSniper",
        max_length=32,
        required=True,
    )
    standoff_id = discord.ui.TextInput(
        label="ID в Standoff 2",
        placeholder="Твой ID/ник в игре",
        max_length=64,
        required=True,
    )

    def __init__(self, cog: "Registration"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        nickname_value = self.nickname.value.strip()
        standoff_id_value = self.standoff_id.value.strip()
        db = self.cog.db

        existing = db.get_player(interaction.guild_id, interaction.user.id)
        if existing:
            db.update_nickname(
                interaction.guild_id, interaction.user.id, nickname_value
            )
            db.set_standoff_id(
                interaction.guild_id, interaction.user.id, standoff_id_value
            )
        else:
            db.create_player(
                interaction.guild_id,
                interaction.user.id,
                nickname_value,
                standoff_id_value,
            )

        await self.cog.grant_player_role(interaction)

        await interaction.response.send_message(
            f"✅ Готово! Зарегистрирован как **{nickname_value}** "
            f"(ID в Standoff 2: **{standoff_id_value}**).",
            ephemeral=True,
        )


class RegisterButtonView(discord.ui.View):

    def __init__(self, cog: "Registration"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="📝 Регистрация",
        style=discord.ButtonStyle.success,
        custom_id="facebot_register_button",
    )
    async def register_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Проверяем, зарегистрирован ли уже пользователь в базе
        existing = self.cog.db.get_player(interaction.guild_id, interaction.user.id)
        if existing:
            await interaction.response.send_message(
                "❌ Вы уже зарегистрированы!", ephemeral=True
            )
            return

        await interaction.response.send_modal(RegisterModal(self.cog))


class ConfirmResetView(discord.ui.View):

    def __init__(self, cog: "Registration"):
        super().__init__(timeout=30)
        self.cog = cog

    @discord.ui.button(
        label="⚠️ Да, снять регистрацию у всех",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Только админ может это подтвердить.", ephemeral=True
            )
            return

        db = self.cog.db
        count = db.delete_all_players(interaction.guild_id)

        role = discord.utils.get(
            interaction.guild.roles, name=config.PLAYER_ROLE_NAME
        )
        removed_roles = 0
        if role is not None:
            for member in list(role.members):
                try:
                    await member.remove_roles(
                        role, reason="Массовый сброс регистрации"
                    )
                    removed_roles += 1
                except discord.HTTPException:
                    pass

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Готово. Удалено профилей: **{count}**. Снята роль у **{removed_roles}** участников.",
            view=self,
        )

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Отменено, ничего не удалено.", view=self
        )


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
                reason="Роль для зарегистрированных игроков (создана автоматически ботом)",
            )
        return role

    async def grant_player_role(self, interaction: discord.Interaction):
        role = await self.get_or_create_player_role(interaction.guild)
        member = interaction.user
        if isinstance(member, discord.Member) and role not in member.roles:
            try:
                await member.add_roles(role, reason="Успешная регистрация")
            except discord.Forbidden:
                pass

    @app_commands.command(
        name="resetregistrations",
        description="Снять регистрацию у ВСЕХ игроков сервера (админ)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetregistrations(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "⚠️ Это удалит рейтинг и регистрацию **у всех** игроков сервера и снимет роль "
            f'"{config.PLAYER_ROLE_NAME}". Действие необратимо. Подтверди:',
            view=ConfirmResetView(self),
            ephemeral=True,
        )

    @app_commands.command(
        name="postregister",
        description="Опубликовать кнопку регистрации в этом канале (админ)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def postregister(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Регистрация",
            description="Нажми кнопку ниже и укажи свой никнейм и ID в Standoff 2, "
            "чтобы получить доступ к остальным каналам сервера.",
            color=discord.Color.blurple(),
        )
        view = RegisterButtonView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            "Кнопка регистрации опубликована.", ephemeral=True
        )

    @app_commands.command(
        name="setuid", description="Указать/обновить свой ник или ID в Standoff 2"
    )
    @app_commands.describe(standoff_id="Твой ник или ID в Standoff 2")
    async def setuid(
        self, interaction: discord.Interaction, standoff_id: str
    ):
        player = self.ensure_player(interaction.guild_id, interaction.user)
        self.db.set_standoff_id(
            interaction.guild_id, interaction.user.id, standoff_id
        )
        await interaction.response.send_message(
            f"Ник в Standoff 2 обновлён: **{standoff_id}**.", ephemeral=True
        )

    @app_commands.command(name="profile", description="Показать профиль игрока")
    @app_commands.describe(
        user="Чей профиль показать (по умолчанию — твой)"
    )
    async def profile(
        self, interaction: discord.Interaction, user: discord.Member = None
    ):
        target = user or interaction.user
        player = self.db.get_player(interaction.guild_id, target.id)
        if player is None:
            await interaction.response.send_message(
                f"{target.display_name} ещё не зарегистрирован.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        buffer = await generate_profile_card(target, player)
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
    cog = Registration(bot)
    await bot.add_cog(cog)
    bot.add_view(RegisterButtonView(cog))

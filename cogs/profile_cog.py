import discord
from discord import app_commands
from discord.ext import commands


class ProfileCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="profile", description="Показать профиль игрока"
    )
    @app_commands.choices(
        league=[
            app_commands.Choice(name="Pro", value="pro"),
            app_commands.Choice(name="Division", value="division"),
            app_commands.Choice(name="Prospect", value="prospect"),
        ]
    )
    @app_commands.describe(
        league="Выберите лигу (обязательно)",
        user="Чей профиль показать (по умолчанию — твой)",
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        league: str,
        user: discord.Member = None,
    ):
        target = user or interaction.user
        player = self.bot.db.get_player(interaction.guild_id, target.id)

        if player is None:
            await interaction.response.send_message(
                f"{target.display_name} ещё не зарегистрирован.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Профиль игрока {target.mention} в лиге **{league}**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))

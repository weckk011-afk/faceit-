import discord
from discord import app_commands
from discord.ext import commands

import config


class QueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    def _is_registered(self, guild_id: int, user: discord.abc.User) -> bool:
        return self.db.get_player(guild_id, user.id) is not None

    @app_commands.command(name="queue", description="Встать в очередь на матч 5x5")
    async def queue_join(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id

        if not self._is_registered(guild_id, interaction.user):
            await interaction.response.send_message(
                "Сначала нужно зарегистрироваться: используй /register и укажи свой ник "
                "в Standoff 2.",
                ephemeral=True,
            )
            return

        added = self.db.queue_add(guild_id, interaction.user.id)
        if not added:
            await interaction.response.send_message(
                "Ты уже в очереди. Используй /leavequeue чтобы выйти.", ephemeral=True
            )
            return

        rows = self.db.queue_list(guild_id)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} встал(а) в очередь "
            f"({len(rows)}/{config.QUEUE_SIZE})."
        )

        if len(rows) >= config.QUEUE_SIZE:
            selected = [row["user_id"] for row in rows[: config.QUEUE_SIZE]]
            self.db.queue_clear_users(guild_id, selected)
            match_cog = self.bot.get_cog("MatchCog")
            await match_cog.start_match(interaction.guild, selected)

    @app_commands.command(name="leavequeue", description="Выйти из очереди")
    async def queue_leave(self, interaction: discord.Interaction):
        removed = self.db.queue_remove(interaction.guild_id, interaction.user.id)
        if removed:
            await interaction.response.send_message("Ты вышел(а) из очереди.", ephemeral=True)
        else:
            await interaction.response.send_message("Ты не был(а) в очереди.", ephemeral=True)

    @app_commands.command(name="queuestatus", description="Показать текущую очередь")
    async def queue_status(self, interaction: discord.Interaction):
        rows = self.db.queue_list(interaction.guild_id)
        if not rows:
            await interaction.response.send_message("Очередь пуста.")
            return
        lines = [f"<@{row['user_id']}>" for row in rows]
        await interaction.response.send_message(
            f"**Очередь ({len(rows)}/{config.QUEUE_SIZE}):**\n" + "\n".join(lines)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))

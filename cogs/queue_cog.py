import discord
from discord import app_commands
from discord.ext import commands

import config


class QueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self._processing_lobby: set[int] = set()  # guild_id, чтобы не запустить матч дважды

    def _is_registered(self, guild_id: int, user_id: int) -> bool:
        return self.db.get_player(guild_id, user_id) is not None

    def _get_lobby_channel(self, guild: discord.Guild):
        return discord.utils.get(guild.voice_channels, name=config.LOBBY_CHANNEL_NAME)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member.bot:
            return

        guild = member.guild
        lobby = self._get_lobby_channel(guild)
        if lobby is None:
            return

        just_joined_lobby = after.channel is not None and after.channel.id == lobby.id and (
            before.channel is None or before.channel.id != lobby.id
        )

        # если зашёл в лобби, но не зарегистрирован — выкидываем и просим зарегистрироваться
        if just_joined_lobby and not self._is_registered(guild.id, member.id):
            try:
                await member.move_to(None, reason="Не зарегистрирован")
            except discord.HTTPException:
                pass
            try:
                await member.send(
                    "Чтобы встать в лобби на матч, сначала зарегистрируйся на сервере: "
                    "используй команду /register и укажи свой ник в Standoff 2."
                )
            except discord.Forbidden:
                pass
            return

        # если изменение затронуло лобби (зашёл или вышел) — проверяем, не набралось ли 10
        touches_lobby = (before.channel and before.channel.id == lobby.id) or (
            after.channel and after.channel.id == lobby.id
        )
        if touches_lobby:
            await self._check_lobby(guild, lobby)

    async def _check_lobby(self, guild: discord.Guild, lobby):
        if guild.id in self._processing_lobby:
            return

        members_in_lobby = [m for m in lobby.members if not m.bot]
        registered = [m for m in members_in_lobby if self._is_registered(guild.id, m.id)]

        if len(registered) >= config.QUEUE_SIZE:
            self._processing_lobby.add(guild.id)
            try:
                selected = registered[: config.QUEUE_SIZE]
                match_cog = self.bot.get_cog("MatchCog")
                await match_cog.start_match(guild, [m.id for m in selected])
            finally:
                self._processing_lobby.discard(guild.id)

    @app_commands.command(name="lobbystatus", description="Кто сейчас в голосовом лобби")
    async def lobbystatus(self, interaction: discord.Interaction):
        lobby = self._get_lobby_channel(interaction.guild)
        if lobby is None:
            await interaction.response.send_message(
                f"Голосовой канал \"{config.LOBBY_CHANNEL_NAME}\" не найден на сервере. "
                f"Создай голосовой канал с таким именем.",
                ephemeral=True,
            )
            return

        members = [m for m in lobby.members if not m.bot]
        if not members:
            await interaction.response.send_message(f"В лобби ({lobby.mention}) сейчас никого нет.")
            return

        lines = [f"<@{m.id}>" for m in members]
        await interaction.response.send_message(
            f"**В лобби ({len(members)}/{config.QUEUE_SIZE}):**\n" + "\n".join(lines)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))

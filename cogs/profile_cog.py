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
        player = self.db.get_player(interaction.guild_id, target.id)
        if player is None:
            await interaction.response.send_message(
                f"{target.display_name} ещё не зарегистрирован.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Здесь можно передать лигу в генератор карточки или вывести в ответе
        # Например, передаем league в функцию генерации (если она это поддерживает)
        buffer = await generate_profile_card(target, player, league=league)
        file = discord.File(buffer, filename="profile.png")
        await interaction.followup.send(file=file)

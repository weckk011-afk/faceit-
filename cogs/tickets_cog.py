import discord
from discord.ext import commands


class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Создать",
        style=discord.ButtonStyle.success,
        emoji="🪪",
        custom_id="create_ticket_btn",
    )
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guild = interaction.guild
        user = interaction.user

        # Проверяем, нет ли уже открытой ветки у этого пользователя в этом канале
        for thread in interaction.channel.threads:
            if f"-{user.id}" in thread.name:
                await interaction.response.send_message(
                    "У вас уже есть открытый тикет в этом канале!", ephemeral=True
                )
                return

        # Создаем приватную ветку (скрытую от других обычных участников)
        try:
            thread = await interaction.channel.create_thread(
                name=f"тикет-{user.name}-{user.id}",
                type=discord.ChannelType.private_thread,
                invitable=False,
            )

            # Добавляем пользователя в ветку
            await thread.add_user(user)

            # Отправляем приветственное сообщение в ветку
            embed = discord.Embed(
                title="🎫 Тикет создан",
                description=(
                    f"Привет, {user.mention}!\nОпишите вашу проблему или задайте вопрос."
                    "\nПерсонал скоро ответит вам."
                ),
                color=discord.Color.green(),
            )
            await thread.send(embed=embed)

            await interaction.response.send_message(
                f"Ваш тикет успешно создан: {thread.mention}", ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Не удалось создать тикет: {e}", ephemeral=True
            )


class TicketCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="setup_ticket")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, ctx):
        """Команда для отправки панели тикетов в текущий канал"""
        await ctx.message.delete()

        embed = discord.Embed(
            title="Помощь по серверу",
            description=(
                "**Создать тикет, в котором можно задать вопрос персоналу или отправить жалобу.**\n\n"
                "Каждое действие отображается в наших логах и видно кто создал / удалил какой-либо тикет. "
                "Мы отслеживаем и наказываем участников, которые используют эту систему не по назначению "
                "(наказания варьируются от предупреждений до дисциплинарного наказания.)\n\n"
                "Полезные ссылки:\n"
                "• ПРАВИЛА ПРОЕКТА — #📖┃правила-проекта"
            ),
            color=discord.Color.dark_embed(),
        )
        embed.set_image(
            url="https://i.imgur.com/your_banner_image.png"
        )  # Замени на свою картинку-баннер если нужно

        view = TicketView()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))

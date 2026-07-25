import discord
from discord import app_commands
from discord.ext import commands

import config


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, cog: "TicketsCog"):
        options = [
            discord.SelectOption(label=label, emoji=emoji, value=label)
            for emoji, label in config.TICKET_CATEGORIES
        ]
        super().__init__(
            placeholder="Выберите категорию...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.create_ticket(interaction, self.values[0])


class TicketCategoryView(discord.ui.View):
    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=60)
        self.add_item(TicketCategorySelect(cog))


class CreateTicketButtonView(discord.ui.View):
    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="📩 Создать",
        style=discord.ButtonStyle.success,
        custom_id="facebot_create_ticket_button",
    )
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Выберите, к какой категории относится ваш вопрос:",
            view=TicketCategoryView(self.cog),
            ephemeral=True,
        )


class CloseTicketView(discord.ui.View):
    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🔒 Закрыть тикет",
        style=discord.ButtonStyle.danger,
        custom_id="facebot_close_ticket_button",
    )
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def create_ticket(self, interaction: discord.Interaction, category: str):
        guild = interaction.guild
        parent_channel = interaction.channel

        ticket_id = self.db.create_ticket(guild.id, interaction.user.id, category)

        thread = await parent_channel.create_thread(
            name=f"тикет-{ticket_id} | {category}"[:100],
            type=discord.ChannelType.public_thread,
            reason=f"Тикет #{ticket_id} от {interaction.user}",
        )
        self.db.set_ticket_thread(ticket_id, thread.id)

        try:
            await thread.add_user(interaction.user)
        except discord.HTTPException:
            pass

        support_role = discord.utils.get(guild.roles, name=config.SUPPORT_ROLE_NAME)
        mention = support_role.mention if support_role else ""

        embed = discord.Embed(
            title=f"🎫 Тикет #{ticket_id}",
            description=f"**Категория:** {category}\n**Автор:** {interaction.user.mention}\n\n"
                        f"Опиши подробно свой вопрос/проблему. Поддержка ответит здесь.",
            color=discord.Color.red(),
        )
        await thread.send(
            content=f"{interaction.user.mention} {mention}".strip(),
            embed=embed,
            view=CloseTicketView(self),
        )

        await interaction.response.send_message(
            f"Тикет создан: {thread.mention}", ephemeral=True
        )

    async def close_ticket(self, interaction: discord.Interaction):
        thread = interaction.channel
        ticket = self.db.get_ticket_by_thread(thread.id)

        is_author = ticket is not None and ticket["user_id"] == interaction.user.id
        is_staff = interaction.user.guild_permissions.manage_guild or (
            discord.utils.get(interaction.guild.roles, name=config.SUPPORT_ROLE_NAME)
            in getattr(interaction.user, "roles", [])
        )

        if not (is_author or is_staff):
            await interaction.response.send_message(
                "Только автор тикета или поддержка может его закрыть.", ephemeral=True
            )
            return

        if ticket is not None:
            self.db.close_ticket(ticket["id"])

        await interaction.response.send_message("🔒 Тикет закрыт и заархивирован.")
        try:
            await thread.edit(archived=True, locked=True, reason=f"Закрыт пользователем {interaction.user}")
        except discord.HTTPException:
            pass

    @app_commands.command(name="postticket", description="Опубликовать кнопку создания тикета в этом канале (админ)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def postticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Техническая поддержка",
            description="Нажми кнопку ниже, чтобы создать тикет и выбрать категорию вопроса.",
            color=discord.Color.red(),
        )
        view = CreateTicketButtonView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("Кнопка создания тикета опубликована.", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = TicketsCog(bot)
    await bot.add_cog(cog)
    bot.add_view(CreateTicketButtonView(cog))
    bot.add_view(CloseTicketView(cog))

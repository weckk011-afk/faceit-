import asyncio
import discord
from discord.ext import commands
import config


class MapVetoView(discord.ui.View):

    def __init__(self, map_pool, team1_cap, team2_cap, match_data):
        super().__init__(timeout=180)
        self.map_pool = list(map_pool)
        self.team1_cap = team1_cap
        self.team2_cap = team2_cap
        self.match_data = match_data
        self.current_turn = team1_cap  # Начинает капитан 1 команды
        self.banned_maps = []
        self.selected_map = None
        self.message = None

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for map_name in self.map_pool:
            btn = discord.ui.Button(
                label=map_name, style=discord.ButtonStyle.secondary
            )
            btn.callback = self.make_callback(map_name)
            self.add_item(btn)

    def make_callback(self, map_name):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in [
                self.team1_cap.id,
                self.team2_cap.id,
            ]:
                await interaction.response.send_message(
                    "❌ Только капитаны могут проводить вето карт!",
                    ephemeral=True,
                )
                return

            if interaction.user.id != self.current_turn.id:
                await interaction.response.send_message(
                    "⏳ Сейчас не ваша очередь ходить!", ephemeral=True
                )
                return

            # Логика вето: если карт больше 1, баним. Последняя остается.
            if len(self.map_pool) > 1:
                self.map_pool.remove(map_name)
                self.banned_maps.append(map_name)

                # Меняем очередь
                self.current_turn = (
                    self.team2_cap
                    if self.current_turn == self.team1_cap
                    else self.team1_cap
                )

                if len(self.map_pool) == 1:
                    self.selected_map = self.map_pool[0]
                    self.stop()
                else:
                    self.update_buttons()
                    await interaction.response.edit_message(
                        content=self.get_text(), view=self
                    )
            else:
                self.stop()

        return callback

    def get_text(self):
        turn_name = (
            self.team2_cap.display_name
            if self.current_turn == self.team1_cap
            else self.team1_cap.display_name
        )
        # Если осталась одна карта
        if len(self.map_pool) == 1:
            return (
                f"⚔️ **МАП-ВЕТО ЗАВЕРШЕНО!**\n🗺️ Выбранная карта:"
                f" **{self.map_pool[0]}**"
            )

        text = f"⚔️ **МАП-ВЕТО (Standoff 2)**\n"
        text += (
            f"🔴 Капитан 1: {self.team1_cap.mention}\n🔵 Капитан 2:"
            f" {self.team2_cap.mention}\n\n"
        )
        if self.banned_maps:
            text += f"❌ Забаненные карты: {', '.join(self.banned_maps)}\n"
        text += (
            f"📌 **Сейчас банит капитан:** {self.current_turn.mention}"
            f" ({turn_name})\n\nВыберите карту для бана:"
        )
        return text


class MatchCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_match_process(
        self,
        guild: discord.Guild,
        match_id: int,
        team_1: list[discord.Member],
        team_2: list[discord.Member],
    ):
        match_channel = guild.get_channel(config.MATCH_CHANNEL_ID)
        if not match_channel:
            return

        cap_1 = team_1[0]
        cap_2 = team_2[0]

        # 4. Раскид по войсам ДОЛЖЕН БЫТЬ ПОСЛЕ МАПВЕТО
        # Сначала запускаем вето карт в текстовом канале матча
        view = MapVetoView(config.MAP_POOL, cap_1, cap_2, None)
        msg = await match_channel.send(content=view.get_text(), view=view)
        view.message = msg

        # Ждем завершения вето (до 3 минут)
        await view.wait()

        chosen_map = view.selected_map or config.MAP_POOL[0]

        # Определяем имена команд по никам капитанов (Пункт 6)
        team1_name = f"Команда [ {cap_1.display_name} ]"
        team2_name = f"Команда [ {cap_2.display_name} ]"

        # 1. Создание закрытых войсов (Пункт 1)
        overwrites_category = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
        }
        for member in team_1 + team_2:
            overwrites_category[member] = discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True
            )

        category = await guild.create_category(
            f"{config.MATCH_CATEGORY_PREFIX} #{match_id}",
            overwrites=overwrites_category,
        )

        # Права для конкретных команд в их каналы
        ov_t1 = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }
        for m in team_1:
            ov_t1[m] = discord.PermissionOverwrite(
                view_channel=True, connect=True
            )

        ov_t2 = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }
        for m in team_2:
            ov_t2[m] = discord.PermissionOverwrite(
                view_channel=True, connect=True
            )

        vc_1 = await guild.create_voice_channel(
            team1_name, category=category, overwrites=ov_t1
        )
        vc_2 = await guild.create_voice_channel(
            team2_name, category=category, overwrites=ov_t2
        )

        # Отправляем информацию о старте матча с именами капитанов
        embed = discord.Embed(
            title=f"🎮 МАТЧ #{match_id} НАЧАЛСЯ!",
            description=f"🗺️ **Карта:** {chosen_map}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name=f"🔴 {team1_name}",
            value="\n".join([p.mention for p in team_1]),
            inline=True,
        )
        embed.add_field(
            name=f"🔵 {team2_name}",
            value="\n".join([p.mention for p in team_2]),
            inline=True,
        )

        match_msg = await match_channel.send(embed=embed)

        # Сохраняем матч в БД (Пункт 2 и 3)
        self.bot.db.create_match(
            match_id, chosen_map, [p.id for p in team_1], [p.id for p in team_2]
        )

        # Симуляция завершения матча (или триггер через админ-команду/кнопку)
        # Здесь мы имитируем сохранение результатов в историю:
        await self.finish_match_workflow(
            guild, match_id, category, [vc_1, vc_2], match_channel, team_1, team_2
        )

    async def finish_match_workflow(
        self,
        guild: discord.Guild,
        match_id: int,
        category: discord.CategoryChannel,
        voice_channels: list,
        match_channel: discord.TextChannel,
        team_1: list,
        team_2: list,
    ):
        # (Этот метод вызывается, когда матч завершается и результаты летят в историю)

        # 5. После отправки результатов открывается ветка ТОЛЬКО для роли admin (Пункт 5)
        admin_role = discord.utils.get(guild.roles, name="admin")

        # Создаем приватную ветку (thread) в канале матча
        thread = await match_channel.create_thread(
            name=f"match-{match_id}-results",
            type=discord.ChannelType.private_thread,
            reason="Match results review for admins",
        )

        # Настраиваем допуск в ветку только для роли admin
        if admin_role:
            # Добавляем администраторов в ветку
            for member in guild.members:
                if admin_role in member.roles:
                    try:
                        await thread.add_user(member)
                    except:
                        pass

        await thread.send(
            f"🔒 Ветка результатов матча **#{match_id}**.\nДоступна только"
            " администрации."
        )

        # 3. Войсы пропадают через 5 минут после регистрации в историю (Пункт 3)
        await asyncio.sleep(300)  # 300 секунд = 5 минут

        try:
            for vc in voice_channels:
                await vc.delete(reason="Match ended 5 minutes ago")
            if category:
                await category.delete(
                    reason="Match category cleaned up after 5 minutes"
                )
        except Exception as e:
            print(f"Ошибка при удалении каналов матча #{match_id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchCog(bot))

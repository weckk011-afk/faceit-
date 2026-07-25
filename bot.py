name="➖ Сняты роли",
            value=", ".join([r.mention for r in removed_roles]),
            inline=False,
        )
    embed.set_footer(text=f"ID пользователя: {after.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


# --- ЛОГИРОВАНИЕ ВОЙСОВ ---
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    if member.bot:
        return
    guild = member.guild
    channel = _get_log_channel(guild, "voice")
    all_channel = _get_log_channel(guild, "all")
    embed = discord.Embed(timestamp=datetime.datetime.now())
    embed.add_field(name="Пользователь", value=member.mention, inline=False)

    if before.channel is None and after.channel is not None:
        embed.title = "🔊 Подключение к голосовому каналу"
        embed.color = discord.Color.green()
        embed.add_field(name="Канал", value=after.channel.name, inline=False)
    elif before.channel is not None and after.channel is None:
        embed.title = "🔇 Выход из голосового канала"
        embed.color = discord.Color.red()
        embed.add_field(name="Канал", value=before.channel.name, inline=False)
    elif before.channel != after.channel:
        embed.title = "🔄 Переход между голосовыми каналами"
        embed.color = discord.Color.gold()
        embed.add_field(name="Из канала", value=before.channel.name, inline=True)
        embed.add_field(name="В канал", value=after.channel.name, inline=True)
    else:
        return

    embed.set_footer(text=f"ID пользователя: {member.id}")
    for target in [channel, all_channel]:
        if target:
            await target.send(embed=embed)


async def main():
    if not config.TOKEN:
        raise RuntimeError("Не найден DISCORD_TOKEN.")
    async with bot:
        await bot.start(config.TOKEN)


if name == "__main__":
    asyncio.run(main())
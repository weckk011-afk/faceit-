import datetime
import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------
    # HELPER: GET OR CREATE WARN ROLES
    # ---------------------------------------------------------
    async def _get_or_create_warn_roles(
        self, guild: discord.Guild
    ) -> dict[str, discord.Role]:
        """Creates warn 1/3, warn 2/3, warn 3/3 roles if they don't exist."""
        warn_names = ["warn 1/3", "warn 2/3", "warn 3/3"]
        roles = {}

        for name in warn_names:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                try:
                    role = await guild.create_role(
                        name=name,
                        reason="Auto-created warning system role",
                        color=discord.Color.dark_orange(),
                    )
                except discord.Forbidden:
                    pass
            roles[name] = role

        return roles

    # ---------------------------------------------------------
    # ROLE MANAGEMENT COMMANDS (/role add, /role remove)
    # ---------------------------------------------------------
    role_group = app_commands.Group(
        name="role", description="Role management commands"
    )

    @role_group.command(name="add", description="Add a role to a user")
    @app_commands.describe(user="Select user", role="Select role to add")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
    ):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ Cannot assign a role higher than or equal to the bot's"
                " highest role.",
                ephemeral=True,
            )
            return

        if role in user.roles:
            await interaction.response.send_message(
                f"⚠️ {user.mention} already has the **{role.name}** role.",
                ephemeral=True,
            )
            return

        try:
            await user.add_roles(role)
            await interaction.response.send_message(
                f"✅ Added **{role.name}** role to {user.mention}.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to add this role.", ephemeral=True
            )

    @role_group.command(name="remove", description="Remove a role from a user")
    @app_commands.describe(user="Select user", role="Select role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
    ):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ Cannot remove a role higher than or equal to the bot's"
                " highest role.",
                ephemeral=True,
            )
            return

        if role not in user.roles:
            await interaction.response.send_message(
                f"⚠️ {user.mention} does not have the **{role.name}** role.",
                ephemeral=True,
            )
            return

        try:
            await user.remove_roles(role)
            await interaction.response.send_message(
                f"✅ Removed **{role.name}** role from {user.mention}.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to remove this role.", ephemeral=True
            )

    # ---------------------------------------------------------
    # WARN SYSTEM (/warn, /unwarn WITH ROLES & RESTRICTIONS)
    # ---------------------------------------------------------
    @app_commands.command(
        name="warn", description="Issue a warning to a user (role-based 1-3)"
    )
    @app_commands.describe(
        user="Select user to warn", reason="Reason for warning"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ):
        if (
            user.top_role >= interaction.user.top_role
            and interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "❌ You cannot warn a user with an equal or higher role.",
                ephemeral=True,
            )
            return

        warn_roles = await self._get_or_create_warn_roles(interaction.guild)

        r1 = warn_roles.get("warn 1/3")
        r2 = warn_roles.get("warn 2/3")
        r3 = warn_roles.get("warn 3/3")

        # Check current warning state
        user_roles = user.roles

        try:
            if r3 in user_roles:
                await interaction.response.send_message(
                    f"⚠️ **{user.mention}** already has **3/3 warnings** and"
                    " active restrictions!",
                    ephemeral=True,
                )
                return

            elif r2 in user_roles:
                # Upgrade from 2/3 -> 3/3
                roles_to_remove = [r for r in [r1, r2] if r in user_roles]
                if roles_to_remove:
                    await user.remove_roles(*roles_to_remove)
                if r3:
                    await user.add_roles(r3)

                # Mute/Restrict for 24 hours on 3/3 warnings
                timeout_duration = datetime.timedelta(days=1)
                await user.timeout(
                    timeout_duration, reason=f"Reached 3/3 warnings. {reason}"
                )

                try:
                    await user.send(
                        f"🚨 You received your **3rd warning** in"
                        f" **{interaction.guild.name}**.\n**Reason:**"
                        f" {reason}\n⛔ **You have been muted for 24 hours!**"
                    )
                except discord.Forbidden:
                    pass

                await interaction.response.send_message(
                    f"🚨 **{user.mention}** received **warn 3/3**!\n**Reason:**"
                    f" {reason}\n⛔ **Account restricted (Muted for 24 hours"
                    " via Timeout).**"
                )

            elif r1 in user_roles:
                # Upgrade from 1/3 -> 2/3
                await user.remove_roles(r1)
                if r2:
                    await user.add_roles(r2)

                try:
                    await user.send(
                        f"⚠️ You received your **2nd warning** (2/3) in"
                        f" **{interaction.guild.name}**.\n**Reason:** {reason}"
                    )
                except discord.Forbidden:
                    pass

                await interaction.response.send_message(
                    f"⚠️ **{user.mention}** received **warn 2/3**.\n**Reason:**"
                    f" {reason}"
                )

            else:
                # 0 -> 1/3
                if r1:
                    await user.add_roles(r1)

                try:
                    await user.send(
                        f"⚠️ You received a warning (1/3) in"
                        f" **{interaction.guild.name}**.\n**Reason:** {reason}"
                    )
                except discord.Forbidden:
                    pass

                await interaction.response.send_message(
                    f"⚠️ **{user.mention}** received **warn 1/3**.\n**Reason:**"
                    f" {reason}"
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to manage roles or timeout this user."
                " Ensure the bot role is placed HIGHER than the warn roles.",
                ephemeral=True,
            )

    @app_commands.command(
        name="unwarn", description="Remove a warning level from a user"
    )
    @app_commands.describe(
        user="Select user to unwarn", reason="Reason for unwarn"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Warning forgiven",
    ):
        warn_roles = await self._get_or_create_warn_roles(interaction.guild)

        r1 = warn_roles.get("warn 1/3")
        r2 = warn_roles.get("warn 2/3")
        r3 = warn_roles.get("warn 3/3")

        user_roles = user.roles

        try:
            if r3 in user_roles:
                # 3/3 -> 2/3 (and lift timeout)
                await user.remove_roles(r3)
                if r2:
                    await user.add_roles(r2)

                if user.is_timed_out():
                    await user.timeout(None, reason="Warning level reduced")

                await interaction.response.send_message(
                    f"✅ Reduced warnings for **{user.mention}** to"
                    f" **2/3**.\n**Reason:** {reason}\n🔊 **Timeout"
                    " restriction removed.**"
                )

            elif r2 in user_roles:
                # 2/3 -> 1/3
                await user.remove_roles(r2)
                if r1:
                    await user.add_roles(r1)

                await interaction.response.send_message(
                    f"✅ Reduced warnings for **{user.mention}** to"
                    f" **1/3**.\n**Reason:** {reason}"
                )

            elif r1 in user_roles:
                # 1/3 -> 0
                await user.remove_roles(r1)
                await interaction.response.send_message(
                    f"✅ Cleared all warnings for **{user.mention}**"
                    f" (**0/3**).\n**Reason:** {reason}"
                )

            else:
                await interaction.response.send_message(
                    f"⚠️ **{user.mention}** has no active warnings.",
                    ephemeral=True,
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to manage roles for this user.",
                ephemeral=True,
            )

    # ---------------------------------------------------------
    # OTHER MODERATION COMMANDS (/mute, /unmute, /ban, /unban)
    # ---------------------------------------------------------
    @app_commands.command(
        name="mute", description="Mute (timeout) a user with a duration"
    )
    @app_commands.describe(
        user="Select user to mute",
        duration="Select mute duration",
        reason="Reason for mute",
    )
    @app_commands.choices(
        duration=[
            app_commands.Choice(name="60 Seconds", value="60s"),
            app_commands.Choice(name="5 Minutes", value="5m"),
            app_commands.Choice(name="15 Minutes", value="15m"),
            app_commands.Choice(name="1 Hour", value="1h"),
            app_commands.Choice(name="12 Hours", value="12h"),
            app_commands.Choice(name="1 Day", value="1d"),
            app_commands.Choice(name="1 Week", value="7d"),
        ]
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: app_commands.Choice[str],
        reason: str = "No reason provided",
    ):
        if (
            user.top_role >= interaction.user.top_role
            and interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "❌ You cannot mute a user with an equal or higher role.",
                ephemeral=True,
            )
            return

        durations = {
            "60s": datetime.timedelta(seconds=60),
            "5m": datetime.timedelta(minutes=5),
            "15m": datetime.timedelta(minutes=15),
            "1h": datetime.timedelta(hours=1),
            "12h": datetime.timedelta(hours=12),
            "1d": datetime.timedelta(days=1),
            "7d": datetime.timedelta(days=7),
        }

        delta = durations.get(duration.value, datetime.timedelta(minutes=15))

        try:
            await user.timeout(delta, reason=reason)
            await interaction.response.send_message(
                f"🔇 **{user.mention}** has been muted for **{duration.name}**.\n**Reason:**"
                f" {reason}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to mute this user.", ephemeral=True
            )

    @app_commands.command(
        name="unmute", description="Unmute (remove timeout) a user"
    )
    @app_commands.describe(
        user="Select user to unmute", reason="Reason for unmute"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ):
        if not user.is_timed_out():
            await interaction.response.send_message(
                f"⚠️ {user.mention} is not currently muted.", ephemeral=True
            )
            return

        try:
            await user.timeout(None, reason=reason)
            await interaction.response.send_message(
                f"🔊 **{user.mention}** has been unmuted.\n**Reason:** {reason}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to unmute this user.",
                ephemeral=True,
            )

    @app_commands.command(
        name="ban", description="Ban a member from the server"
    )
    @app_commands.describe(user="Select user to ban", reason="Reason for ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ):
        if (
            user.top_role >= interaction.user.top_role
            and interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "❌ You cannot ban a user with an equal or higher role.",
                ephemeral=True,
            )
            return

        try:
            await user.ban(reason=reason)
            await interaction.response.send_message(
                f"🔨 **{user.mention}** has been banned.\n**Reason:** {reason}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to ban this user.", ephemeral=True
            )

    @app_commands.command(name="unban", description="Unban a user by User ID")
    @app_commands.describe(
        user_id="ID of the user to unban", reason="Reason for unban"
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided",
    ):
        try:
            target_id = int(user_id)
            user_obj = discord.Object(id=target_id)
            await interaction.guild.unban(user_obj, reason=reason)
            await interaction.response.send_message(
                f"🔓 User with ID `<{user_id}>` has been unbanned.\n**Reason:**"
                f" {reason}"
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid User ID. Please provide numbers only.",
                ephemeral=True,
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ User not found in ban list.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to unban users.", ephemeral=True
            )

    # ---------------------------------------------------------
    # ERROR HANDLER FOR MISSING PERMISSIONS
    # ---------------------------------------------------------
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You do not have permission to use this command.",
                ephemeral=True,
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

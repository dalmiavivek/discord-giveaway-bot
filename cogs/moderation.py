import re
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

COLOR_DARK = discord.Color(0x2B2D31)

class Moderation(commands.Cog, name="Moderation"):
    """Server moderation and advanced message purging."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- ADVANCED PURGE COMMAND GROUP ---

    @commands.group(name="purge", aliases=["clear", "clean"], invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_group(self, ctx: commands.Context, amount: int = 10):
        """Purge recent messages from the current channel (1-500)."""
        if amount < 1:
            await ctx.send("❌ Please specify a positive number of messages to purge.", ephemeral=True)
            return

        if amount > 500:
            await ctx.send("❌ You can purge a maximum of 500 messages at once.", ephemeral=True)
            return

        # Delete trigger message if not already deleted
        try:
            await ctx.message.delete()
        except Exception:
            pass

        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"🧹 Purged `{len(deleted)}` message(s).")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="user", aliases=["member"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_user(self, ctx: commands.Context, member: discord.Member, amount: int = 50):
        """Purge messages sent only by a specific user."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: m.author.id == member.id)
        msg = await ctx.send(f"🧹 Purged `{len(deleted)}` message(s) from {member.mention}.")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="bots", aliases=["bot"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, ctx: commands.Context, amount: int = 50):
        """Purge messages sent only by bots."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: m.author.bot)
        msg = await ctx.send(f"🤖 Purged `{len(deleted)}` bot message(s).")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="links", aliases=["link", "urls"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_links(self, ctx: commands.Context, amount: int = 50):
        """Purge messages containing website URLs/links."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        url_regex = re.compile(r"https?://\S+|discord\.gg/\S+", re.IGNORECASE)
        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: bool(url_regex.search(m.content)))
        msg = await ctx.send(f"🔗 Purged `{len(deleted)}` message(s) containing links.")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="files", aliases=["attachments", "images"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_files(self, ctx: commands.Context, amount: int = 50):
        """Purge messages containing images or file attachments."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: len(m.attachments) > 0)
        msg = await ctx.send(f"📎 Purged `{len(deleted)}` message(s) with attachments.")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="contains", aliases=["match"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, ctx: commands.Context, text: str, amount: int = 50):
        """Purge messages containing specific text/keywords."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: text.lower() in m.content.lower())
        msg = await ctx.send(f"🔍 Purged `{len(deleted)}` message(s) containing `{text}`.")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    @purge_group.command(name="humans", aliases=["users"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_humans(self, ctx: commands.Context, amount: int = 50):
        """Purge messages sent only by human members (ignores bots)."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        limit = min(amount, 500)
        deleted = await ctx.channel.purge(limit=limit, check=lambda m: not m.author.bot)
        msg = await ctx.send(f"👤 Purged `{len(deleted)}` human message(s).")
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except Exception:
            pass

    # --- SLASH PURGE COMMAND ---

    @app_commands.command(name="purge", description="Purge messages from the current channel")
    @app_commands.describe(
        amount="Number of messages to check/purge (1-100)",
        user="Only purge messages from this member (optional)",
        bots_only="Only purge bot messages (optional)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_purge(
        self,
        interaction: discord.Interaction,
        amount: int = 10,
        user: Optional[discord.Member] = None,
        bots_only: Optional[bool] = False
    ):
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def check_msg(m: discord.Message) -> bool:
            if user and m.author.id != user.id:
                return False
            if bots_only and not m.author.bot:
                return False
            return True

        deleted = await interaction.channel.purge(limit=amount, check=check_msg)
        await interaction.followup.send(f"🧹 Successfully purged `{len(deleted)}` message(s).", ephemeral=True)

    # --- STANDARD MODERATION COMMANDS ---

    @commands.hybrid_command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @commands.has_permissions(kick_members=True)
    async def kick_member(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ You cannot kick a member with an equal or higher role.")
            return
        await member.kick(reason=reason)
        await ctx.send(f"👢 Kicked **{member.display_name}** | Reason: {reason}")

    @commands.hybrid_command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason for ban")
    @commands.has_permissions(ban_members=True)
    async def ban_member(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ You cannot ban a member with an equal or higher role.")
            return
        await member.ban(reason=reason)
        await ctx.send(f"🔨 Banned **{member.display_name}** | Reason: {reason}")

    @commands.hybrid_command(name="unban", description="Unban a user by their Discord user ID")
    @app_commands.describe(user_id="Discord ID of the user to unban")
    @commands.has_permissions(ban_members=True)
    async def unban_user(self, ctx: commands.Context, user_id: str):
        if not user_id.isdigit():
            await ctx.send("❌ Please provide a valid numeric User ID.")
            return
        user = await self.bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned **{user.display_name}** (`{user.id}`).")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

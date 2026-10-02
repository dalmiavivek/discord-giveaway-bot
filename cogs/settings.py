import os
import sys
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database

# Discord dark theme color matching the clean layout
COLOR_DARK = discord.Color(0x2B2D31)

DEFAULT_BANNER_URL = "https://raw.githubusercontent.com/dalmiavivek/discord-giveaway-bot/main/assets/banner.png"

def get_banner_url(bot: commands.Bot) -> str:
    env_banner = os.getenv("BOT_BANNER_URL")
    if env_banner:
        return env_banner
    if bot.user and getattr(bot.user, "banner", None):
        return bot.user.banner.url
    return DEFAULT_BANNER_URL

def get_creator_name(bot: commands.Bot) -> str:
    env_creator = os.getenv("BOT_CREATOR")
    if env_creator:
        return env_creator
    if getattr(bot, "application", None) and getattr(bot.application, "owner", None):
        return bot.application.owner.name
    return "dalmiavivek"

def get_home_embed(prefix: str, bot: commands.Bot) -> discord.Embed:
    bot_name = bot.user.display_name if bot.user else "LoveAffair"
    creator = get_creator_name(bot)
    banner_url = get_banner_url(bot)

    description = (
        f"I'm **{bot_name}**, your ultimate Discord companion!\n"
        f"Created by `{creator}`. My Prefix for this server is `{prefix}`\n\n"
        f"> **Command Categories**\n\n"
        f"🎉 **Giveaways** — Interactive & requirement-based giveaways\n"
        f"🎫 **Tickets** — Support panel, staff alerts & dual transcripts\n"
        f"📈 **Activity Tracker** — Message & voice channel activity tracking\n"
        f"🛡️ **Moderation & Admin** — Server management, cleanups & permissions\n"
        f"⚙️ **Config & Utility** — Server prefix, bot latency & statistics"
    )

    embed = discord.Embed(description=description, color=COLOR_DARK)
    if banner_url:
        embed.set_image(url=banner_url)
    return embed

def get_category_embed(category: str, prefix: str, bot: commands.Bot) -> discord.Embed:
    bot_name = bot.user.display_name if bot.user else "LoveAffair"
    banner_url = get_banner_url(bot)

    category_data = {
        "giveaways": (
            "Giveaways",
            (
                f"🎉 `{prefix}gstart <duration> <winners> <prize>`\n"
                f"Start an interactive giveaway with one-click button entry.\n"
                f"*Example: `{prefix}gstart 1h 1w Discord Nitro`*\n\n"
                f"🎉 `/giveaway start`\n"
                f"Start an advanced giveaway with requirements:\n"
                f"• `required_role` — Restrict to specific server role\n"
                f"• `min_messages` — Enforce chat message requirement\n"
                f"• `min_vc_minutes` — Enforce voice channel activity\n\n"
                f"🎉 `{prefix}gend <giveaway_id>` or `/giveaway end`\n"
                f"End an active giveaway early and pick winners.\n\n"
                f"🎉 `{prefix}greroll <giveaway_id> [winners]` or `/giveaway reroll`\n"
                f"Reroll one or more new winners from eligible entries.\n\n"
                f"🎉 `{prefix}glist` or `/giveaway list`\n"
                f"View all active giveaways in this server."
            )
        ),
        "tickets": (
            "Tickets",
            (
                f"🎫 `{prefix}ticketsetup` or `/ticket setup`\n"
                f"Deploy the interactive ticket creation panel with reason modal.\n\n"
                f"🎫 `{prefix}ticketstaff <@role>` or `/ticket setstaff`\n"
                f"Configure the staff role to receive pings when tickets open.\n\n"
                f"🎫 `{prefix}ticketadd <@member>` or `/ticket add`\n"
                f"Add a member to the current ticket channel.\n\n"
                f"🎫 `{prefix}ticketremove <@member>` or `/ticket remove`\n"
                f"Remove a member from the ticket channel.\n\n"
                f"🎫 `{prefix}ticketclose` or `/ticket close`\n"
                f"Close ticket and automatically DM dual transcripts (.html & .txt) to creator and closer.\n\n"
                f"🎫 `{prefix}delete` or `/ticket delete`\n"
                f"Permanently delete the closed ticket channel."
            )
        ),
        "activity": (
            "Activity Tracker",
            (
                f"📈 `{prefix}stats [@member]` or `/user-stats`\n"
                f"View tracked message count and total voice channel time.\n\n"
                f"📈 **Real-Time Tracking & Requirements:**\n"
                f"• Automatically counts messages sent across all text channels.\n"
                f"• Automatically logs active minutes spent in voice channels.\n"
                f"• Integrates with `/giveaway start` (`min_messages` & `min_vc_minutes`)."
            )
        ),
        "admin": (
            "Moderation & Admin",
            (
                f"🛡️ `{prefix}clear <amount>` or `/clear`\n"
                f"Purge recent messages from the current channel (1-100).\n\n"
                f"🛡️ `{prefix}kick <@member> [reason]` or `/kick`\n"
                f"Kick a member from the server.\n\n"
                f"🛡️ `{prefix}ban <@member> [reason]` or `/ban`\n"
                f"Ban a member from the server.\n\n"
                f"🛡️ `{prefix}delete` or `/ticket delete`\n"
                f"Permanently delete a closed ticket channel."
            )
        ),
        "utility": (
            "Config & Utility",
            (
                f"⚙️ `{prefix}setprefix <new_prefix>`\n"
                f"Change the command prefix for this server (e.g. `!`, `$`, `?`).\n\n"
                f"⚙️ `{prefix}prefix`\n"
                f"View the active server prefix.\n\n"
                f"⚙️ `{prefix}ping` or `/ping`\n"
                f"Check bot websocket latency and response time.\n\n"
                f"⚙️ `{prefix}botinfo` or `/botinfo`\n"
                f"View server count, total members, and bot statistics."
            )
        ),
    }

    if category not in category_data:
        return get_home_embed(prefix, bot)

    title, body = category_data[category]
    description = (
        f"I'm **{bot_name}**, your ultimate Discord companion!\n"
        f"My Prefix for this server is `{prefix}`\n\n"
        f"> **{title} Commands**\n\n"
        f"{body}"
    )

    embed = discord.Embed(description=description, color=COLOR_DARK)
    embed.set_footer(text="Select 'Home' in the dropdown below to return to categories.")
    if banner_url:
        embed.set_image(url=banner_url)
    return embed

class HelpSelect(discord.ui.Select):
    def __init__(self, prefix: str, bot: commands.Bot):
        self.prefix = prefix
        self.bot = bot
        options = [
            discord.SelectOption(
                label="Home",
                description="Return to the category overview",
                emoji="🏠",
                value="home"
            ),
            discord.SelectOption(
                label="Giveaways",
                description="Interactive & requirement-based giveaways",
                emoji="🎉",
                value="giveaways"
            ),
            discord.SelectOption(
                label="Tickets",
                description="Support panel, staff alerts & transcripts",
                emoji="🎫",
                value="tickets"
            ),
            discord.SelectOption(
                label="Activity Tracker",
                description="Message & voice channel tracking",
                emoji="📈",
                value="activity"
            ),
            discord.SelectOption(
                label="Moderation & Admin",
                description="Server management & channel cleanup",
                emoji="🛡️",
                value="admin"
            ),
            discord.SelectOption(
                label="Config & Utility",
                description="Server prefix, bot latency & statistics",
                emoji="⚙️",
                value="utility"
            ),
        ]
        super().__init__(
            placeholder="Select a command category...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "home":
            embed = get_home_embed(self.prefix, self.bot)
        else:
            embed = get_category_embed(choice, self.prefix, self.bot)

        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, prefix: str, bot: commands.Bot):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(prefix, bot))

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="setprefix", description="Change the bot command prefix for this server")
    @app_commands.describe(new_prefix="The new command prefix (e.g. !, ?, g!, $)")
    @commands.has_permissions(manage_guild=True)
    async def set_prefix(self, ctx: commands.Context, new_prefix: str):
        if len(new_prefix) > 5:
            await ctx.send("❌ Prefix cannot be longer than 5 characters.")
            return

        database.set_guild_prefix(ctx.guild.id, new_prefix)
        await ctx.send(f"✅ Prefix for **{ctx.guild.name}** updated to: `{new_prefix}`")

    @commands.hybrid_command(name="prefix", description="Show the current command prefix for this server")
    async def show_prefix(self, ctx: commands.Context):
        prefix = database.get_guild_prefix(ctx.guild.id) if ctx.guild else "!"
        await ctx.send(f"ℹ️ Current prefix for this server is: `{prefix}` (You can also mention the bot: @{self.bot.user.display_name})")

    @commands.hybrid_command(name="ping", description="Check bot latency and connection")
    async def ping_command(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: `{latency}ms`")

    @commands.hybrid_command(name="botinfo", description="View bot statistics and system info")
    async def botinfo_command(self, ctx: commands.Context):
        embed = discord.Embed(
            title=f"ℹ️ {self.bot.user.display_name} Statistics",
            color=COLOR_DARK
        )
        embed.add_field(name="🌐 Servers", value=str(len(self.bot.guilds)), inline=True)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        embed.add_field(name="👥 Members", value=str(total_members), inline=True)
        embed.add_field(name="🏓 Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🐍 Python", value=sys.version.split()[0], inline=True)
        embed.add_field(name="📚 discord.py", value=discord.__version__, inline=True)
        banner_url = get_banner_url(self.bot)
        if banner_url:
            embed.set_image(url=banner_url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clear", description="Delete messages from current channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @commands.has_permissions(manage_messages=True)
    async def clear_messages(self, ctx: commands.Context, amount: int = 5):
        if amount < 1 or amount > 100:
            await ctx.send("❌ Please provide a number between 1 and 100.", ephemeral=True)
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"🧹 Purged `{len(deleted) - 1}` message(s).")
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass

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

    @commands.hybrid_command(name="help", description="View section-by-section help and command list")
    @app_commands.describe(section="Specific section to view (optional)")
    async def help_command(self, ctx: commands.Context, section: Optional[str] = None):
        prefix = database.get_guild_prefix(ctx.guild.id) if ctx.guild else "!"
        
        if section:
            sec = section.lower().strip()
            if sec in ["giveaway", "giveaways", "gstart"]:
                embed = get_category_embed("giveaways", prefix, self.bot)
            elif sec in ["ticket", "tickets"]:
                embed = get_category_embed("tickets", prefix, self.bot)
            elif sec in ["activity", "tracker", "stats", "counter"]:
                embed = get_category_embed("activity", prefix, self.bot)
            elif sec in ["admin", "mod", "moderation"]:
                embed = get_category_embed("admin", prefix, self.bot)
            elif sec in ["setting", "settings", "utility", "config", "prefix"]:
                embed = get_category_embed("utility", prefix, self.bot)
            else:
                embed = get_home_embed(prefix, self.bot)
        else:
            embed = get_home_embed(prefix, self.bot)

        view = HelpView(prefix, self.bot)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

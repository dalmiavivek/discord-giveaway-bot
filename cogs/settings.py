import os
import sys
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database

# Discord dark theme color matching the Paradox style
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
    return "knownazcrazy"

def get_home_embed(prefix: str, bot: commands.Bot) -> discord.Embed:
    bot_name = bot.user.display_name if bot.user else "Paradox"
    creator = get_creator_name(bot)
    banner_url = get_banner_url(bot)

    description = (
        f"I'm **{bot_name}**, your ultimate Discord companion!\n"
        f"Created by `{creator}`. My Prefix for this server is `{prefix}`\n\n"
        f"> **Command Categories**\n\n"
        f"🔧 **Admin** - Server administration\n"
        f"ℹ️ **Info** - Information & stats\n"
        f"🛠️ **Moderation** - Moderation tools\n"
        f"⚙️ **Utility** - Useful utilities\n"
        f"🤖 **AutoMod** - Automated moderation\n"
        f"🎉 **Giveaway** - Host giveaways\n"
        f"🎧 **Voice** - Voice management\n"
        f"👥 **Welcome** - Welcome systems\n"
        f"⚡ **Counter** - Activity tracking\n"
        f"🔊 **Voice Leveling** - Leveling for voice activity\n"
        f"🎫 **Ticket** - Support tickets\n"
        f"✨ **Vanity Roles** - Status role systems\n"
        f"🏷️ **Guild Tags** - Guild tag role systems\n"
        f"🔨 **Boycott** - Boycott system\n"
        f"🎮 **Fun** - Entertainment commands"
    )

    embed = discord.Embed(description=description, color=COLOR_DARK)
    if banner_url:
        embed.set_image(url=banner_url)
    return embed

def get_category_embed(category: str, prefix: str, bot: commands.Bot) -> discord.Embed:
    bot_name = bot.user.display_name if bot.user else "Paradox"
    banner_url = get_banner_url(bot)

    category_data = {
        "admin": (
            "Admin",
            (
                f"🔧 `{prefix}setprefix <new_prefix>`\n"
                f"Change the command prefix for this server.\n\n"
                f"🔧 `{prefix}ticketsetup` or `/ticket setup`\n"
                f"Deploy the interactive support ticket panel.\n\n"
                f"🔧 `{prefix}ticketstaff <@role>` or `/ticket setstaff`\n"
                f"Configure the staff role to receive ticket pings.\n\n"
                f"🔧 `{prefix}delete` or `/ticket delete`\n"
                f"Permanently delete a closed ticket channel."
            )
        ),
        "info": (
            "Info",
            (
                f"ℹ️ `{prefix}botinfo` or `/botinfo`\n"
                f"Display bot latency, server count, and version info.\n\n"
                f"ℹ️ `{prefix}ping` or `/ping`\n"
                f"Check bot response time and websocket latency.\n\n"
                f"ℹ️ `{prefix}prefix`\n"
                f"Show the active prefix for this server."
            )
        ),
        "moderation": (
            "Moderation",
            (
                f"🛠️ `{prefix}clear <amount>` or `/clear`\n"
                f"Delete multiple messages from the current channel (1-100).\n\n"
                f"🛠️ `{prefix}kick <@member> [reason]` or `/kick`\n"
                f"Kick a member from the server.\n\n"
                f"🛠️ `{prefix}ban <@member> [reason]` or `/ban`\n"
                f"Ban a member from the server."
            )
        ),
        "utility": (
            "Utility",
            (
                f"⚙️ `{prefix}setprefix <new_prefix>`\n"
                f"Change server prefix (e.g. `!`, `$`, `?`).\n\n"
                f"⚙️ `{prefix}prefix`\n"
                f"View the current prefix.\n\n"
                f"⚙️ `{prefix}ping`\n"
                f"Check bot latency and API heartbeat."
            )
        ),
        "automod": (
            "AutoMod",
            (
                f"🤖 **Automated Server Protection**\n"
                f"• Rate-limiting spam detection.\n"
                f"• Anti-Invite and unauthorized link filtering.\n"
                f"• Automated role assignment upon verification."
            )
        ),
        "giveaway": (
            "Giveaway",
            (
                f"🎉 `{prefix}gstart <duration> <winners> <prize>`\n"
                f"Quick giveaway start (e.g. `{prefix}gstart 1h 1w Nitro`).\n\n"
                f"🎉 `/giveaway start`\n"
                f"Start with requirements (`min_messages`, `min_vc_minutes`, `role`).\n\n"
                f"🎉 `{prefix}gend <id>` or `/giveaway end`\n"
                f"End an active giveaway early and pick winners.\n\n"
                f"🎉 `{prefix}greroll <id> [winners]` or `/giveaway reroll`\n"
                f"Reroll new winners for an ended giveaway.\n\n"
                f"🎉 `{prefix}glist` or `/giveaway list`\n"
                f"List all currently running giveaways."
            )
        ),
        "voice": (
            "Voice",
            (
                f"🎧 **Voice Channel Tracking**\n"
                f"• Automatically logs active time spent in voice channels.\n"
                f"• Check your voice stats with `{prefix}stats` or `/user-stats`.\n"
                f"• Enforce voice requirements for giveaways (`min_vc_minutes`)."
            )
        ),
        "welcome": (
            "Welcome",
            (
                f"👥 **Welcome System**\n"
                f"• Automated greeting embeds for newly joined members.\n"
                f"• Auto-assign initial member roles upon joining."
            )
        ),
        "counter": (
            "Counter",
            (
                f"⚡ `{prefix}stats [@member]` or `/user-stats`\n"
                f"View tracked message count and total voice channel time.\n\n"
                f"⚡ **Real-Time Activity Counters**\n"
                f"Counts messages and voice time for requirement-locked giveaways."
            )
        ),
        "voice_leveling": (
            "Voice Leveling",
            (
                f"🔊 **Voice Leveling System**\n"
                f"• Earn XP and activity ranking while hanging out in voice channels.\n"
                f"• AFK channel detection and anti-spam voice safeguards."
            )
        ),
        "ticket": (
            "Ticket",
            (
                f"🎫 `{prefix}ticketsetup` or `/ticket setup`\n"
                f"Deploy interactive ticket panel with reason modal.\n\n"
                f"🎫 `{prefix}ticketstaff <@role>` or `/ticket setstaff`\n"
                f"Configure staff role to ping when tickets open.\n\n"
                f"🎫 `{prefix}ticketadd <@member>` or `/ticket add`\n"
                f"Add a member to the current ticket.\n\n"
                f"🎫 `{prefix}ticketremove <@member>` or `/ticket remove`\n"
                f"Remove a member from the ticket.\n\n"
                f"🎫 `{prefix}ticketclose` or `/ticket close`\n"
                f"Close ticket and automatically DM dual HTML & TXT transcripts.\n\n"
                f"🎫 `{prefix}delete` or `/ticket delete`\n"
                f"Permanently delete closed ticket channel."
            )
        ),
        "vanity": (
            "Vanity Roles",
            (
                f"✨ **Vanity Roles System**\n"
                f"• Automatically rewards members who add server invite to their status.\n"
                f"• Real-time status detection and role sync."
            )
        ),
        "guild_tags": (
            "Guild Tags",
            (
                f"🏷️ **Guild Tag Roles**\n"
                f"• Grants custom roles to members wearing server clan/guild tags."
            )
        ),
        "boycott": (
            "Boycott",
            (
                f"🔨 **Boycott / Blacklist Protection**\n"
                f"• Blocks blacklisted users or alt accounts from entering giveaways."
            )
        ),
        "fun": (
            "Fun",
            (
                f"🎮 `{prefix}ping` — Check bot response latency\n"
                f"🎮 Entertainment & mini-games for community engagement."
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
            discord.SelectOption(label="Home", description="Return to main category overview", emoji="🏠", value="home"),
            discord.SelectOption(label="Admin", description="Server administration", emoji="🔧", value="admin"),
            discord.SelectOption(label="Info", description="Information & stats", emoji="ℹ️", value="info"),
            discord.SelectOption(label="Moderation", description="Moderation tools", emoji="🛠️", value="moderation"),
            discord.SelectOption(label="Utility", description="Useful utilities", emoji="⚙️", value="utility"),
            discord.SelectOption(label="AutoMod", description="Automated moderation", emoji="🤖", value="automod"),
            discord.SelectOption(label="Giveaway", description="Host giveaways", emoji="🎉", value="giveaway"),
            discord.SelectOption(label="Voice", description="Voice management", emoji="🎧", value="voice"),
            discord.SelectOption(label="Welcome", description="Welcome systems", emoji="👥", value="welcome"),
            discord.SelectOption(label="Counter", description="Activity tracking", emoji="⚡", value="counter"),
            discord.SelectOption(label="Voice Leveling", description="Leveling for voice activity", emoji="🔊", value="voice_leveling"),
            discord.SelectOption(label="Ticket", description="Support tickets", emoji="🎫", value="ticket"),
            discord.SelectOption(label="Vanity Roles", description="Status role systems", emoji="✨", value="vanity"),
            discord.SelectOption(label="Guild Tags", description="Guild tag role systems", emoji="🏷️", value="guild_tags"),
            discord.SelectOption(label="Boycott", description="Boycott system", emoji="🔨", value="boycott"),
            discord.SelectOption(label="Fun", description="Entertainment commands", emoji="🎮", value="fun"),
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
            embed = get_category_embed(sec, prefix, self.bot)
        else:
            embed = get_home_embed(prefix, self.bot)

        view = HelpView(prefix, self.bot)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

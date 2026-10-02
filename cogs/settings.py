import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database

def get_home_embed(prefix: str, bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(
        title="🤖 LoveAffair Bot — Help Center",
        description=(
            f"Welcome to the **LoveAffair** help menu!\n"
            f"• **Current Prefix:** `{prefix}`\n"
            f"• **Slash Commands:** Fully supported (`/`)\n\n"
            f"Use the **dropdown menu below** to browse commands section-by-section."
        ),
        color=discord.Color.gold()
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="📚 Command Sections",
        value=(
            f"🎉 **Giveaways** — Create & manage giveaways with requirements\n"
            f"🎫 **Tickets** — Private channels, staff notifications, & transcripts\n"
            f"📊 **Activity & Stats** — Track message counts & voice channel time\n"
            f"⚙️ **Configuration** — Change server prefix & preferences"
        ),
        inline=False
    )
    embed.add_field(
        name="💡 Quick Tips",
        value=(
            f"• You can also type `{prefix}help <section>` directly (e.g. `{prefix}help giveaway`).\n"
            f"• Mentioning the bot `@LoveAffair` works as a prefix anywhere."
        ),
        inline=False
    )
    embed.set_footer(text="Select a category from the dropdown below to explore!")
    return embed

def get_giveaway_embed(prefix: str) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Giveaway Commands",
        description="Host fair, interactive giveaways with optional role and activity requirements.",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="🚀 Starting Giveaways",
        value=(
            f"• **Quick Start (Prefix):**\n"
            f"  `{prefix}gstart <duration> <winners> <prize>`\n"
            f"  *Example:* `{prefix}gstart 1h 1w Discord Nitro`\n\n"
            f"• **Requirement-Based (Slash Command):**\n"
            f"  `/giveaway start`\n"
            f"  *Options:* `prize`, `duration`, `winners`, `required_role`, `min_messages`, `min_vc_minutes`"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ Managing Giveaways",
        value=(
            f"• **End Early:** `{prefix}gend <id>` or `/giveaway end`\n"
            f"• **Reroll Winner:** `{prefix}greroll <id> [winners]` or `/giveaway reroll`\n"
            f"• **List Active:** `{prefix}glist` or `/giveaway list`"
        ),
        inline=False
    )
    embed.set_footer(text="Users join giveaways by clicking the '🎉 Enter Giveaway' button.")
    return embed

def get_ticket_embed(prefix: str) -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Support Ticket Commands",
        description="Comprehensive private ticket system with staff notifications, modal reason input, and dual transcripts.",
        color=discord.Color.brand_green()
    )
    embed.add_field(
        name="🛠️ Setup & Staff",
        value=(
            f"• **Deploy Panel:** `/ticket setup` or `{prefix}ticketsetup`\n"
            f"• **Set Staff Role:** `/ticket setstaff <role>` or `{prefix}ticketstaff @role`\n"
            f"  *(Staff members are pinged whenever a new ticket is opened)*"
        ),
        inline=False
    )
    embed.add_field(
        name="👥 User & Ticket Management",
        value=(
            f"• **Add Member:** `/ticket add <member>` or `{prefix}ticketadd @member`\n"
            f"• **Remove Member:** `/ticket remove <member>` or `{prefix}ticketremove @member`\n"
            f"• **Close Ticket:** `/ticket close` or `{prefix}ticketclose`\n"
            f"• **Delete Channel:** `/ticket delete` or `{prefix}delete`"
        ),
        inline=False
    )
    embed.add_field(
        name="📄 Dual Transcripts (HTML & TXT)",
        value=(
            "When closing, transcripts are automatically sent to both the **Creator** and **Closer** in their DMs:\n"
            "• 🌐 **HTML Transcript** — Opens in your web browser with a full Discord-styled chat UI.\n"
            "• 📄 **TXT Transcript** — Clean plain-text archive."
        ),
        inline=False
    )
    embed.set_footer(text="Tickets are never deleted automatically; staff click 'Delete Ticket' when ready.")
    return embed

def get_activity_embed(prefix: str) -> discord.Embed:
    embed = discord.Embed(
        title="📊 Activity & Stats Commands",
        description="Automatic tracking of members' messages and voice channel time per server.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="💬 Activity Commands",
        value=(
            f"• **Check Stats:** `{prefix}stats [@member]` or `/user-stats [member]`\n"
            f"• Shows total messages sent & hours/minutes spent in Voice Channels."
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 How Requirements Work",
        value=(
            "When creating requirement-based giveaways with `/giveaway start`:\n"
            "• `min_messages`: Only members with enough messages can enter.\n"
            "• `min_vc_minutes`: Only members with enough voice channel time can enter.\n"
            "If a user does not meet the requirements, the bot sends them a private breakdown."
        ),
        inline=False
    )
    embed.set_footer(text="Activity tracking runs automatically in real time.")
    return embed

def get_settings_embed(prefix: str) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Bot Configuration",
        description="Customize server-specific settings and prefixes.",
        color=discord.Color.dark_grey()
    )
    embed.add_field(
        name="🔧 Prefix Commands",
        value=(
            f"• **Set Prefix:** `{prefix}setprefix <new_prefix>` or `/setprefix <new_prefix>`\n"
            f"• **View Prefix:** `{prefix}prefix` or `/prefix`\n"
            f"• Supports prefixes up to 5 characters (e.g. `!`, `?`, `$`, `g!`)."
        ),
        inline=False
    )
    embed.set_footer(text="Prefixes are saved in SQLite and persist across bot restarts.")
    return embed

class HelpSelect(discord.ui.Select):
    def __init__(self, prefix: str, bot: commands.Bot):
        self.prefix = prefix
        self.bot = bot
        options = [
            discord.SelectOption(
                label="Home / Overview",
                description="Main menu and bot information",
                emoji="🏠",
                value="home"
            ),
            discord.SelectOption(
                label="Giveaways",
                description="Start, end, reroll, and manage giveaways",
                emoji="🎉",
                value="giveaways"
            ),
            discord.SelectOption(
                label="Tickets",
                description="Support tickets, staff roles, and HTML/TXT transcripts",
                emoji="🎫",
                value="tickets"
            ),
            discord.SelectOption(
                label="Activity & Stats",
                description="Tracked messages and voice channel time",
                emoji="📊",
                value="activity"
            ),
            discord.SelectOption(
                label="Configuration",
                description="Server prefix and bot settings",
                emoji="⚙️",
                value="settings"
            ),
        ]
        super().__init__(
            placeholder="📂 Select a section to view commands...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "home":
            embed = get_home_embed(self.prefix, self.bot)
        elif choice == "giveaways":
            embed = get_giveaway_embed(self.prefix)
        elif choice == "tickets":
            embed = get_ticket_embed(self.prefix)
        elif choice == "activity":
            embed = get_activity_embed(self.prefix)
        elif choice == "settings":
            embed = get_settings_embed(self.prefix)
        else:
            embed = get_home_embed(self.prefix, self.bot)

        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, prefix: str, bot: commands.Bot):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(prefix, bot))

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="setprefix", description="Change the bot command prefix for this server")
    @app_commands.describe(new_prefix="The new command prefix (e.g. !, ?, g!)")
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

    @commands.hybrid_command(name="help", description="View section-by-section help and command list")
    @app_commands.describe(section="Specific section to view (optional)")
    @app_commands.choices(section=[
        app_commands.Choice(name="🎉 Giveaways", value="giveaways"),
        app_commands.Choice(name="🎫 Tickets", value="tickets"),
        app_commands.Choice(name="📊 Activity & Stats", value="activity"),
        app_commands.Choice(name="⚙️ Configuration", value="settings"),
    ])
    async def help_command(self, ctx: commands.Context, section: Optional[str] = None):
        prefix = database.get_guild_prefix(ctx.guild.id) if ctx.guild else "!"
        
        # If user directly specified a section (e.g. !help giveaway)
        if section:
            sec = section.lower().strip()
            if sec in ["giveaway", "giveaways", "gstart"]:
                embed = get_giveaway_embed(prefix)
            elif sec in ["ticket", "tickets"]:
                embed = get_ticket_embed(prefix)
            elif sec in ["activity", "stats"]:
                embed = get_activity_embed(prefix)
            elif sec in ["setting", "settings", "config", "prefix"]:
                embed = get_settings_embed(prefix)
            else:
                embed = get_home_embed(prefix, self.bot)
        else:
            embed = get_home_embed(prefix, self.bot)

        view = HelpView(prefix, self.bot)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

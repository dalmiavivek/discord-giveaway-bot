import os
import time
import re
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Union
import database

COLOR_DARK = discord.Color(0x2B2D31)

def parse_duration_to_days(duration_str: Optional[str]) -> Optional[float]:
    """Parse string like '7d', '30 days', '12h', 'permanent' to number of days."""
    if not duration_str:
        return 7.0  # default 7 days
    
    val = duration_str.lower().strip()
    if val in ["perm", "permanent", "lifetime", "forever", "0"]:
        return None
    
    # Check for formats like '7d', '12h', '30m'
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([dhwmy]?)$", val)
    if match:
        number = float(match.group(1))
        unit = match.group(2)
        if unit == "h":
            return number / 24.0
        elif unit == "w":
            return number * 7.0
        elif unit == "m":
            return number * 30.0
        elif unit == "y":
            return number * 365.0
        else: # default 'd'
            return number
            
    return 7.0

def get_authorized_managers(bot: commands.Bot) -> set:
    """Return set of user IDs authorized to manage No-Prefix."""
    managers = set(database.get_np_managers())
    
    # Read from environment variable
    env_managers = os.getenv("AUTHORIZED_NP_USERS")
    if env_managers:
        for uid in env_managers.split(","):
            uid = uid.strip()
            if uid.isdigit():
                managers.add(int(uid))
                
    # Fallback to bot application owner
    if getattr(bot, "application", None) and getattr(bot.application, "owner", None):
        managers.add(bot.application.owner.id)
        
    return managers

def is_manager(author_id: int, bot: commands.Bot) -> bool:
    return author_id in get_authorized_managers(bot)

class NoPrefix(commands.Cog, name="NoPrefix"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="np", aliases=["npr"], invoke_without_command=True)
    async def np_group(self, ctx: commands.Context):
        """No-Prefix (NPR) management command group."""
        prefix = database.get_guild_prefix(ctx.guild.id) if ctx.guild else "!"
        embed = discord.Embed(
            title="⚡ No-Prefix (NPR) System",
            description=(
                "Users with **No-Prefix (NPR)** status can run any bot command without typing any prefix!\n\n"
                f"**Available Commands:**\n"
                f"• `{prefix}np add <@member> [days]` — Grant No-Prefix for specified days\n"
                f"• `{prefix}np remove <@member>` — Revoke No-Prefix\n"
                f"• `{prefix}np check [@member]` — Check No-Prefix status & expiry\n"
                f"• `{prefix}np list` — View all users with active No-Prefix\n"
                f"• `{prefix}np managers` — View authorized manager accounts\n"
                f"• `{prefix}np setmanager <@member>` — Add an authorized manager account (max 2)"
            ),
            color=COLOR_DARK
        )
        embed.set_footer(text="Only the 2 authorized manager accounts can grant or revoke No-Prefix.")
        await ctx.send(embed=embed)

    @np_group.command(name="add")
    async def np_add(self, ctx: commands.Context, member: discord.User, duration: Optional[str] = "7d"):
        """Grant No-Prefix to a member for some days."""
        if not is_manager(ctx.author.id, self.bot):
            embed = discord.Embed(
                title="⛔ Access Denied",
                description="Only the **2 authorized Manager Accounts** are permitted to grant No-Prefix (NPR).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        days = parse_duration_to_days(duration)
        expires_at = database.add_no_prefix(member.id, ctx.author.id, days)

        embed = discord.Embed(
            title="✨ No-Prefix (NPR) Granted",
            description=f"Successfully granted **No-Prefix** status to {member.mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 User", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(name="🛡️ Granted By", value=f"{ctx.author.mention}", inline=True)
        
        if expires_at:
            timestamp_int = int(expires_at)
            embed.add_field(
                name="⏳ Duration",
                value=f"**{days:.1f} Day(s)**\nExpires: <t:{timestamp_int}:F> (<t:{timestamp_int}:R>)",
                inline=False
            )
        else:
            embed.add_field(name="⏳ Duration", value="**Permanent / Lifetime**", inline=False)

        embed.set_footer(text=f"{member.display_name} can now run commands without typing any prefix!")
        await ctx.send(embed=embed)

    @np_group.command(name="remove")
    async def np_remove(self, ctx: commands.Context, member: discord.User):
        """Revoke No-Prefix from a member."""
        if not is_manager(ctx.author.id, self.bot):
            embed = discord.Embed(
                title="⛔ Access Denied",
                description="Only the **2 authorized Manager Accounts** are permitted to revoke No-Prefix (NPR).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        removed = database.remove_no_prefix(member.id)
        if removed:
            embed = discord.Embed(
                title="🗑️ No-Prefix (NPR) Revoked",
                description=f"Successfully revoked No-Prefix status from {member.mention}.",
                color=COLOR_DARK
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"ℹ️ {member.mention} did not have active No-Prefix status.")

    @np_group.command(name="list")
    async def np_list(self, ctx: commands.Context):
        """List all users who currently have active No-Prefix."""
        entries = database.get_all_no_prefix()
        if not entries:
            embed = discord.Embed(
                title="⚡ Active No-Prefix (NPR) Users",
                description="*No users currently have active No-Prefix status.*",
                color=COLOR_DARK
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"⚡ Active No-Prefix (NPR) Users ({len(entries)})",
            color=COLOR_DARK
        )

        lines = []
        for idx, entry in enumerate(entries, 1):
            user_id = entry["user_id"]
            expires_at = entry["expires_at"]
            if expires_at:
                exp_text = f"Expires <t:{int(expires_at)}:R>"
            else:
                exp_text = "Permanent"
            lines.append(f"**{idx}.** <@{user_id}> (`{user_id}`) — {exp_text}")

        embed.description = "\n".join(lines[:25]) # show top 25
        embed.set_footer(text="These users can run bot commands without any prefix.")
        await ctx.send(embed=embed)

    @np_group.command(name="check")
    async def np_check(self, ctx: commands.Context, member: Optional[discord.User] = None):
        """Check if you or another user has active No-Prefix."""
        target = member or ctx.author
        entry = database.get_no_prefix_user(target.id)

        if not entry:
            embed = discord.Embed(
                title="⚡ No-Prefix Status",
                description=f"❌ {target.mention} does **not** have active No-Prefix (NPR) status.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        expires_at = entry["expires_at"]
        embed = discord.Embed(
            title="⚡ No-Prefix Status: Active",
            description=f"✅ {target.mention} has active **No-Prefix (NPR)** status!",
            color=discord.Color.green()
        )
        if expires_at:
            exp_int = int(expires_at)
            embed.add_field(name="⏳ Expiration", value=f"<t:{exp_int}:F> (<t:{exp_int}:R>)", inline=False)
        else:
            embed.add_field(name="⏳ Expiration", value="Permanent / Lifetime", inline=False)
        embed.add_field(name="🛡️ Granted By", value=f"<@{entry['added_by']}>", inline=True)
        await ctx.send(embed=embed)

    @np_group.command(name="managers")
    async def np_managers(self, ctx: commands.Context):
        """View the authorized manager accounts who can grant No-Prefix."""
        mgr_ids = get_authorized_managers(self.bot)
        if not mgr_ids:
            await ctx.send("ℹ️ No manager accounts configured yet.")
            return

        embed = discord.Embed(
            title="🛡️ Authorized No-Prefix Managers",
            description="Only these designated accounts have permission to grant or revoke No-Prefix:\n\n" +
                        "\n".join([f"• <@{uid}> (`{uid}`)" for uid in mgr_ids]),
            color=COLOR_DARK
        )
        embed.set_footer(text="Max 2 manager accounts can be configured.")
        await ctx.send(embed=embed)

    @np_group.command(name="setmanager")
    async def np_set_manager(self, ctx: commands.Context, member: discord.User):
        """Add an authorized manager account (max 2 managers)."""
        current_managers = get_authorized_managers(self.bot)
        
        # Only existing managers or bot application owner can add another manager
        if ctx.author.id not in current_managers:
            await ctx.send("⛔ Only an existing authorized manager can add another manager account.")
            return

        db_managers = database.get_np_managers()
        if len(db_managers) >= 2:
            await ctx.send(f"❌ Maximum of 2 manager accounts allowed. Remove one first using `{ctx.prefix}np removemanager <@user>`.")
            return

        database.add_np_manager(member.id)
        await ctx.send(f"✅ Added {member.mention} (`{member.id}`) as an authorized No-Prefix manager account.")

    @np_group.command(name="removemanager")
    async def np_remove_manager(self, ctx: commands.Context, member: discord.User):
        """Remove a manager account."""
        current_managers = get_authorized_managers(self.bot)
        if ctx.author.id not in current_managers:
            await ctx.send("⛔ Only an existing authorized manager can remove a manager account.")
            return

        removed = database.remove_np_manager(member.id)
        if removed:
            await ctx.send(f"✅ Removed {member.mention} from authorized manager accounts.")
        else:
            await ctx.send(f"ℹ️ {member.mention} was not found in the custom managers list.")

async def setup(bot: commands.Bot):
    await bot.add_cog(NoPrefix(bot))

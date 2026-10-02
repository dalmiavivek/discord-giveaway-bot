import discord
from discord import app_commands
from discord.ext import commands
import database

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

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context):
        prefix = database.get_guild_prefix(ctx.guild.id) if ctx.guild else "!"
        embed = discord.Embed(
            title="🎁 Discord Giveaway Bot — Help",
            description=f"Server Prefix: `{prefix}` | You can also use **Slash Commands** (`/`)",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="🎉 Giveaway Commands",
            value=(
                f"• `{prefix}gstart <duration> <winners> <prize>` — Start a giveaway\n"
                f"• `/giveaway start` — Start a giveaway with role, message, or VC requirements\n"
                f"• `{prefix}gend <giveaway_id>` or `/giveaway end` — End a giveaway early\n"
                f"• `{prefix}greroll <giveaway_id> [winners]` or `/giveaway reroll` — Pick new winners\n"
                f"• `{prefix}glist` or `/giveaway list` — View all active giveaways"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Activity & Stats",
            value=(
                f"• `{prefix}stats [@member]` or `/user-stats` — View message and voice channel stats"
            ),
            inline=False
        )

        embed.add_field(
            name="🎫 Ticket Commands",
            value=(
                f"• `/ticket setup` or `{prefix}ticketsetup` — Deploy ticket panel\n"
                f"• `/ticket setstaff <role>` or `{prefix}ticketstaff` — Set staff role to ping\n"
                f"• `/ticket add <member>` or `{prefix}ticketadd` — Add user to ticket\n"
                f"• `/ticket remove <member>` or `{prefix}ticketremove` — Remove user from ticket\n"
                f"• `/ticket close` or `{prefix}ticketclose` — Close ticket & send transcript\n"
                f"• `/ticket delete` or `{prefix}ticketdelete` — Permanently delete ticket channel"
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Configuration",
            value=(
                f"• `{prefix}setprefix <new_prefix>` — Change server prefix\n"
                f"• `{prefix}prefix` — View current server prefix"
            ),
            inline=False
        )

        embed.set_footer(text="Tip: Click the '🎉 Enter Giveaway' button on any giveaway message to participate!")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

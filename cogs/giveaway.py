import discord
from discord import app_commands
from discord.ext import commands, tasks
import time
import re
import random
import database
from emojis import get_button_emoji

def parse_duration(duration_str: str) -> Optional[int]:
    """Parse duration strings like '1d', '2h30m', '45s' into total seconds."""
    regex = re.compile(r'((?P<days>\d+)\s*d)?\s*((?P<hours>\d+)\s*h)?\s*((?P<minutes>\d+)\s*m)?\s*((?P<seconds>\d+)\s*s)?', re.IGNORECASE)
    parts = regex.fullmatch(duration_str.strip())
    if not parts or not any(parts.groupdict().values()):
        return None
    time_params = {name: int(param) for name, param in parts.groupdict().items() if param}
    days = time_params.get("days", 0)
    hours = time_params.get("hours", 0)
    minutes = time_params.get("minutes", 0)
    seconds = time_params.get("seconds", 0)
    total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total_seconds if total_seconds > 0 else None

def format_seconds(seconds: int) -> str:
    """Format seconds into readable string (e.g. 1h 20m)."""
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    res = []
    if days:
        res.append(f"{days}d")
    if hours:
        res.append(f"{hours}h")
    if minutes:
        res.append(f"{minutes}m")
    if sec and not res:
        res.append(f"{sec}s")
    return " ".join(res) if res else "0m"

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        # Custom ID ensures persistence across bot restarts
        self.enter_button.custom_id = f"giveaway_enter:{giveaway_id}"

    @discord.ui.button(
        label="Enter Giveaway",
        emoji=get_button_emoji("GIVEAWAY_ENTER", "🎉"),
        style=discord.ButtonStyle.success
    )
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = database.get_giveaway(self.giveaway_id)
        if not gw or gw["ended"]:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            guild = interaction.guild
            member = guild.get_member(interaction.user.id) if guild else None

        if not member:
            await interaction.response.send_message("❌ Could not verify server membership.", ephemeral=True)
            return

        # Check requirements
        failed_requirements = []
        
        # 1. Role requirement
        req_role_id = gw["required_role_id"]
        if req_role_id:
            role = interaction.guild.get_role(req_role_id)
            if role and role not in member.roles:
                failed_requirements.append(f"• **Role Required:** {role.mention} (You don't have this role)")

        # 2. Activity requirements (Messages & VC time)
        min_msgs = gw["min_messages"]
        min_vc = gw["min_vc_seconds"]
        
        if min_msgs > 0 or min_vc > 0:
            stats = database.get_user_activity(interaction.guild_id, member.id)
            if min_msgs > 0 and stats["message_count"] < min_msgs:
                failed_requirements.append(
                    f"• **Messages:** {min_msgs} required (You have {stats['message_count']})"
                )
            if min_vc > 0 and stats["vc_seconds"] < min_vc:
                needed_str = format_seconds(min_vc)
                have_str = format_seconds(stats["vc_seconds"])
                failed_requirements.append(
                    f"• **Voice Channel Time:** {needed_str} required (You have {have_str})"
                )

        if failed_requirements:
            msg = "❌ **You do not meet the entry requirements:**\n" + "\n".join(failed_requirements)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Handle entry toggle (leave if already entered)
        if database.is_user_entered(self.giveaway_id, member.id):
            database.remove_entry(self.giveaway_id, member.id)
            entry_count = database.get_entry_count(self.giveaway_id)
            await interaction.response.send_message(
                f"🗑️ You have left the giveaway for **{gw['prize']}**.",
                ephemeral=True
            )
        else:
            database.add_entry(self.giveaway_id, member.id)
            entry_count = database.get_entry_count(self.giveaway_id)
            await interaction.response.send_message(
                f"🎉 **You have entered the giveaway for {gw['prize']}!** Good luck!\n*(Click the button again if you want to leave)*",
                ephemeral=True
            )

        # Update entry count on the embed
        try:
            channel = interaction.guild.get_channel(gw["channel_id"])
            if channel:
                msg = await channel.fetch_message(gw["message_id"])
                if msg and msg.embeds:
                    embed = msg.embeds[0]
                    # Update the Entries field
                    for i, field in enumerate(embed.fields):
                        if field.name == "Entries":
                            embed.set_field_at(i, name="Entries", value=f"**{entry_count}**", inline=True)
                            break
                    await msg.edit(embed=embed)
        except Exception:
            pass

class Giveaway(commands.GroupCog, group_name="giveaway", group_description="Commands for managing giveaways"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    async def end_giveaway_helper(self, gw: dict):
        giveaway_id = gw["id"]
        guild = self.bot.get_guild(gw["guild_id"])
        if not guild:
            database.mark_giveaway_ended(giveaway_id)
            return

        channel = guild.get_channel(gw["channel_id"])
        if not channel:
            database.mark_giveaway_ended(giveaway_id)
            return

        try:
            message = await channel.fetch_message(gw["message_id"])
        except Exception:
            message = None

        entries = database.get_entries(giveaway_id)
        winners_count = gw["winners_count"]
        prize = gw["prize"]

        # Select winners
        if entries:
            num_winners = min(winners_count, len(entries))
            winner_ids = random.sample(entries, num_winners)
            winner_mentions = [f"<@{uid}>" for uid in winner_ids]
            winners_str = ", ".join(winner_mentions)
        else:
            winner_ids = []
            winners_str = "No participants entered."

        # Mark ended in DB
        database.mark_giveaway_ended(giveaway_id)

        # Update the original message
        if message:
            embed = discord.Embed(
                title=f"🎁 GIVEAWAY ENDED: {prize}",
                description=(
                    f"**Winner(s):** {winners_str}\n"
                    f"**Hosted by:** <@{gw['host_id']}>\n"
                    f"**Total Entries:** {len(entries)}"
                ),
                color=discord.Color.dark_grey()
            )
            embed.set_footer(text=f"Giveaway ID: {giveaway_id} • Ended")
            
            # Disable buttons
            disabled_view = discord.ui.View()
            btn = discord.ui.Button(label="Giveaway Ended", style=discord.ButtonStyle.secondary, disabled=True)
            disabled_view.add_item(btn)
            
            try:
                await message.edit(embed=embed, view=disabled_view)
            except Exception:
                pass

        # Announce winner in channel
        if winner_ids:
            await channel.send(
                f"🎉 Congratulations {winners_str}! You won the giveaway for **{prize}**! 🎁\n"
                f"Giveaway link: {message.jump_url if message else 'N/A'}"
            )
        else:
            await channel.send(f"⚠️ The giveaway for **{prize}** ended, but there were no valid entries.")

    @tasks.loop(seconds=5)
    async def check_giveaways(self):
        expired = database.get_expired_giveaways()
        for gw in expired:
            try:
                await self.end_giveaway_helper(gw)
            except Exception as e:
                print(f"Error resolving giveaway {gw['id']}: {e}")

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="start", description="Start a new giveaway with optional role, message, or VC requirements")
    @app_commands.describe(
        prize="What is being given away?",
        duration="Duration of the giveaway (e.g. 10m, 1h, 2d, 1d12h)",
        winners="Number of winners (default: 1)",
        channel="Channel to host the giveaway in (default: current channel)",
        required_role="Role required to enter (optional)",
        min_messages="Minimum server messages required to enter (optional)",
        min_vc_minutes="Minimum server voice channel minutes required to enter (optional)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: Optional[int] = 1,
        channel: Optional[discord.TextChannel] = None,
        required_role: Optional[discord.Role] = None,
        min_messages: Optional[int] = 0,
        min_vc_minutes: Optional[int] = 0
    ):
        seconds = parse_duration(duration)
        if not seconds:
            await interaction.response.send_message(
                "❌ Invalid duration format! Use formats like `30s`, `15m`, `2h`, `1d`, or `1d6h`.",
                ephemeral=True
            )
            return

        if winners < 1:
            await interaction.response.send_message("❌ Number of winners must be at least 1.", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        end_time = time.time() + seconds
        end_timestamp = int(end_time)
        min_vc_seconds = (min_vc_minutes or 0) * 60

        # Save to DB first to get giveaway ID
        gw_id = database.create_giveaway(
            channel_id=target_channel.id,
            guild_id=interaction.guild_id,
            prize=prize,
            winners_count=winners,
            end_time=end_time,
            host_id=interaction.user.id,
            required_role_id=required_role.id if required_role else None,
            min_messages=min_messages or 0,
            min_vc_seconds=min_vc_seconds
        )

        # Build Embed
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize} 🎉",
            description=(
                f"Click the button below to participate!\n\n"
                f"⏰ **Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\n"
                f"👑 **Hosted by:** {interaction.user.mention}\n"
                f"🏆 **Winners:** {winners}"
            ),
            color=discord.Color.gold()
        )

        # Add Requirements section if any
        requirements = []
        if required_role:
            requirements.append(f"• **Role:** {required_role.mention}")
        if min_messages and min_messages > 0:
            requirements.append(f"• **Messages:** {min_messages}+ messages")
        if min_vc_minutes and min_vc_minutes > 0:
            requirements.append(f"• **Voice Activity:** {min_vc_minutes}+ minutes in VC")

        if requirements:
            embed.add_field(name="📋 Entry Requirements", value="\n".join(requirements), inline=False)

        embed.add_field(name="Entries", value="**0**", inline=True)
        embed.set_footer(text=f"Giveaway ID: {gw_id} • Click below to enter!")

        # Create persistent View
        view = GiveawayView(gw_id)
        msg = await target_channel.send(embed=embed, view=view)

        # Update message ID in DB
        database.set_giveaway_message_id(gw_id, msg.id)
        
        # Also register the view dynamically in the bot's persistent views
        self.bot.add_view(view)

        await interaction.response.send_message(
            f"✅ Giveaway **#{gw_id}** for **{prize}** created successfully in {target_channel.mention}!",
            ephemeral=True
        )

    @app_commands.command(name="end", description="End a giveaway early and pick winners immediately")
    @app_commands.describe(giveaway_id="The ID of the giveaway to end")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        gw = database.get_giveaway(giveaway_id)
        if not gw:
            await interaction.response.send_message(f"❌ Giveaway with ID `#{giveaway_id}` not found.", ephemeral=True)
            return

        if gw["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ This giveaway belongs to another server.", ephemeral=True)
            return

        if gw["ended"]:
            await interaction.response.send_message("❌ This giveaway has already ended.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.end_giveaway_helper(gw)
        await interaction.followup.send(f"✅ Giveaway `#{giveaway_id}` has been ended!")

    @app_commands.command(name="reroll", description="Reroll new winner(s) for an ended giveaway")
    @app_commands.describe(
        giveaway_id="The ID of the ended giveaway",
        winners="Number of new winners to select (default: 1)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        winners: Optional[int] = 1
    ):
        gw = database.get_giveaway(giveaway_id)
        if not gw:
            await interaction.response.send_message(f"❌ Giveaway with ID `#{giveaway_id}` not found.", ephemeral=True)
            return

        if gw["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ This giveaway belongs to another server.", ephemeral=True)
            return

        entries = database.get_entries(giveaway_id)
        if not entries:
            await interaction.response.send_message("❌ Cannot reroll: there are no entries in this giveaway.", ephemeral=True)
            return

        winners_count = max(1, winners or 1)
        selected_winners = random.sample(entries, min(winners_count, len(entries)))
        mentions = [f"<@{uid}>" for uid in selected_winners]
        winners_str = ", ".join(mentions)

        channel = interaction.guild.get_channel(gw["channel_id"])
        if channel:
            await channel.send(
                f"🎲 **REROLL!** Congratulations {winners_str}! You are the new winner(s) for **{gw['prize']}**! 🎁"
            )
            await interaction.response.send_message(f"✅ Rerolled {len(selected_winners)} winner(s)!", ephemeral=True)
        else:
            await interaction.response.send_message(f"🎉 New Winner(s): {winners_str}", ephemeral=True)

    @app_commands.command(name="list", description="List all active giveaways in this server")
    async def giveaway_list(self, interaction: discord.Interaction):
        active = [g for g in database.get_active_giveaways() if g["guild_id"] == interaction.guild_id]
        if not active:
            await interaction.response.send_message("ℹ️ There are currently no active giveaways in this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎉 Active Giveaways",
            color=discord.Color.blue()
        )
        for g in active:
            end_ts = int(g["end_time"])
            channel = interaction.guild.get_channel(g["channel_id"])
            channel_str = channel.mention if channel else f"#{g['channel_id']}"
            entries_count = database.get_entry_count(g["id"])
            embed.add_field(
                name=f"ID #{g['id']} — {g['prize']}",
                value=(
                    f"**Channel:** {channel_str}\n"
                    f"**Ends:** <t:{end_ts}:R>\n"
                    f"**Winners:** {g['winners_count']}\n"
                    f"**Entries:** {entries_count}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Traditional Prefix Commands ---

    @commands.command(name="gstart", aliases=["giveaway"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_start(self, ctx: commands.Context, duration: str = None, winners: str = None, *, prize: str = None):
        """Start a giveaway using prefix: !gstart <duration> <winners> <prize>"""
        if not duration or not winners or not prize:
            prefix = database.get_guild_prefix(ctx.guild.id)
            await ctx.send(
                f"ℹ️ **Usage:** `{prefix}gstart <duration> <winners> <prize>`\n"
                f"**Example:** `{prefix}gstart 1h 1w Discord Nitro`\n"
                f"*(For role/message/VC requirements, use `/giveaway start`)*"
            )
            return

        # Parse winners if written like '1w' or '1'
        winners_clean = winners.lower().rstrip("w").rstrip("winners")
        try:
            winners_count = int(winners_clean)
        except ValueError:
            await ctx.send("❌ Invalid number of winners. Example: `!gstart 1h 1w Discord Nitro`")
            return

        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send("❌ Invalid duration! Use formats like `30s`, `15m`, `2h`, `1d`.")
            return

        if winners_count < 1:
            await ctx.send("❌ Number of winners must be at least 1.")
            return

        end_time = time.time() + seconds
        end_timestamp = int(end_time)

        gw_id = database.create_giveaway(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            prize=prize,
            winners_count=winners_count,
            end_time=end_time,
            host_id=ctx.author.id
        )

        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize} 🎉",
            description=(
                f"Click the button below to participate!\n\n"
                f"⏰ **Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\n"
                f"👑 **Hosted by:** {ctx.author.mention}\n"
                f"🏆 **Winners:** {winners_count}"
            ),
            color=discord.Color.gold()
        )
        embed.add_field(name="Entries", value="**0**", inline=True)
        embed.set_footer(text=f"Giveaway ID: {gw_id} • Click below to enter!")

        view = GiveawayView(gw_id)
        msg = await ctx.send(embed=embed, view=view)

        database.set_giveaway_message_id(gw_id, msg.id)
        self.bot.add_view(view)

    @commands.command(name="gend")
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_end(self, ctx: commands.Context, giveaway_id: int):
        """End a giveaway early: !gend <giveaway_id>"""
        gw = database.get_giveaway(giveaway_id)
        if not gw or gw["guild_id"] != ctx.guild.id:
            await ctx.send(f"❌ Giveaway `#{giveaway_id}` not found in this server.")
            return
        if gw["ended"]:
            await ctx.send("❌ This giveaway has already ended.")
            return

        await self.end_giveaway_helper(gw)
        await ctx.send(f"✅ Giveaway `#{giveaway_id}` has been ended!")

    @commands.command(name="greroll")
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_reroll(self, ctx: commands.Context, giveaway_id: int, winners: Optional[int] = 1):
        """Reroll winner(s) for an ended giveaway: !greroll <giveaway_id> [winners]"""
        gw = database.get_giveaway(giveaway_id)
        if not gw or gw["guild_id"] != ctx.guild.id:
            await ctx.send(f"❌ Giveaway `#{giveaway_id}` not found in this server.")
            return

        entries = database.get_entries(giveaway_id)
        if not entries:
            await ctx.send("❌ Cannot reroll: there are no entries in this giveaway.")
            return

        winners_count = max(1, winners or 1)
        selected_winners = random.sample(entries, min(winners_count, len(entries)))
        mentions = [f"<@{uid}>" for uid in selected_winners]
        winners_str = ", ".join(mentions)

        channel = ctx.guild.get_channel(gw["channel_id"])
        if channel:
            await channel.send(
                f"🎲 **REROLL!** Congratulations {winners_str}! You are the new winner(s) for **{gw['prize']}**! 🎁"
            )
        await ctx.send(f"✅ Rerolled {len(selected_winners)} winner(s)!")

    @commands.command(name="glist")
    async def prefix_giveaway_list(self, ctx: commands.Context):
        """List active giveaways: !glist"""
        active = [g for g in database.get_active_giveaways() if g["guild_id"] == ctx.guild.id]
        if not active:
            await ctx.send("ℹ️ There are currently no active giveaways in this server.")
            return

        embed = discord.Embed(title="🎉 Active Giveaways", color=discord.Color.blue())
        for g in active:
            end_ts = int(g["end_time"])
            channel = ctx.guild.get_channel(g["channel_id"])
            channel_str = channel.mention if channel else f"#{g['channel_id']}"
            entries_count = database.get_entry_count(g["id"])
            embed.add_field(
                name=f"ID #{g['id']} — {g['prize']}",
                value=(
                    f"**Channel:** {channel_str}\n"
                    f"**Ends:** <t:{end_ts}:R>\n"
                    f"**Winners:** {g['winners_count']}\n"
                    f"**Entries:** {entries_count}"
                ),
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))

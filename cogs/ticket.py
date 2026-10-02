import discord
from discord import app_commands
from discord.ext import commands
import io
import time
import asyncio
from datetime import datetime
from typing import Optional
import database
from transcript_generator import generate_html_transcript

class TicketReasonModal(discord.ui.Modal, title="Create Support Ticket"):
    reason = discord.ui.TextInput(
        label="Reason for Opening Ticket",
        style=discord.TextStyle.paragraph,
        placeholder="Please describe what you need help with (e.g. Giveaway Claim, General Support)...",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        settings = database.get_ticket_settings(guild.id)
        ticket_num = database.increment_ticket_counter(guild.id)
        channel_name = f"ticket-{user.name[:10]}-{ticket_num:04d}".lower()

        # Permission Overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        # Add support role overwrite if configured
        support_role = None
        if settings.get("support_role_id"):
            support_role = guild.get_role(settings["support_role_id"])

        # Auto-detect role named "Staff", "Support", "Admin", or "Moderator" if not explicitly configured
        if not support_role:
            for r in guild.roles:
                if r.name.lower() in ["staff", "support", "admin", "moderator", "mod", "ticket staff"]:
                    support_role = r
                    break

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )

        category = None
        if settings.get("category_id"):
            category = guild.get_channel(settings["category_id"])

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"Ticket #{ticket_num:04d} | Creator: {user.display_name} ({user.id})"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot lacks permission to create channels! Please check bot role hierarchy and permissions.", ephemeral=True)
            return

        # Record ticket in database
        database.create_ticket(guild.id, ticket_channel.id, user.id, ticket_num)

        # Build initial ticket embed
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_num:04d}",
            description=(
                f"Welcome {user.mention}! Support staff will be with you shortly.\n\n"
                f"**Subject / Reason:**\n{self.reason.value}\n\n"
                f"Use the buttons below to manage this ticket."
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Click 'Close' to end this ticket and generate a transcript.")

        # Explicitly ping staff role so staff receive instant push / audio notification
        if support_role:
            ping_content = f"{support_role.mention} 🔔 **New Ticket Alert!** {user.mention} opened a ticket."
        else:
            ping_content = f"{user.mention}"

        await ticket_channel.send(content=ping_content, embed=embed, view=TicketControlView())

        await interaction.followup.send(
            f"✅ Your ticket has been created: {ticket_channel.mention}",
            ephemeral=True
        )

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📩 Open Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:create"
    )
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user already has an active open ticket
        existing = database.get_user_open_ticket(interaction.guild_id, interaction.user.id)
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            if ch:
                await interaction.response.send_message(
                    f"❌ You already have an open ticket in {ch.mention}!",
                    ephemeral=True
                )
                return
            else:
                # Channel was deleted manually without closing in DB
                database.close_ticket(existing["channel_id"], interaction.user.id)

        # Open the modal
        await interaction.response.send_modal(TicketReasonModal())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close"
    )
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        await interaction.response.defer()

        # Generate HTML transcript
        transcript_file = await generate_html_transcript(interaction.channel, ticket, closed_by=interaction.user)

        # Close in DB
        database.close_ticket(interaction.channel_id, interaction.user.id)

        # Send to log channel if configured
        settings = database.get_ticket_settings(interaction.guild_id)
        if settings.get("log_channel_id"):
            log_channel = interaction.guild.get_channel(settings["log_channel_id"])
            if log_channel:
                log_embed = discord.Embed(
                    title=f"📋 Ticket Closed: #{ticket['ticket_number']:04d}",
                    description=(
                        f"**Creator:** <@{ticket['user_id']}>\n"
                        f"**Closed By:** {interaction.user.mention}\n"
                        f"**Channel:** {interaction.channel.name}\n\n"
                        f"📁 *Interactive HTML transcript attached below.*"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_channel.send(embed=log_embed, file=transcript_file)
                except Exception as e:
                    print(f"Error logging transcript: {e}")

        # Send HTML transcript directly to user DM
        target_user = interaction.guild.get_member(ticket["user_id"])
        if not target_user:
            try:
                target_user = await interaction.client.fetch_user(ticket["user_id"])
            except Exception:
                target_user = None

        if target_user:
            try:
                dm_file = await generate_html_transcript(interaction.channel, ticket, closed_by=interaction.user)
                dm_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed",
                    description=(
                        f"Your ticket in **{interaction.guild.name}** has been closed.\n\n"
                        f"• **Closed By:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                        f"• **An interactive HTML transcript of your conversation is attached below.**\n"
                        f"*(Download and open the file in your browser to view the Discord-styled chat)*"
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text=f"{interaction.guild.name} Support")
                await target_user.send(embed=dm_embed, file=dm_file)
            except discord.Forbidden:
                print(f"Cannot DM user {ticket['user_id']} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM: {e}")

        # Send HTML transcript directly to ticket closer DM (if different from creator)
        closer = interaction.user
        if closer and (target_user is None or closer.id != target_user.id):
            try:
                closer_file = await generate_html_transcript(interaction.channel, ticket, closed_by=closer)
                closer_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed (Staff Copy)",
                    description=(
                        f"You closed ticket **#{ticket['ticket_number']:04d}** in **{interaction.guild.name}**.\n\n"
                        f"• **Creator:** <@{ticket['user_id']}>\n"
                        f"• **Channel:** #{interaction.channel.name}\n"
                        f"• **An interactive HTML transcript of the ticket is attached below.**"
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                closer_embed.set_footer(text=f"{interaction.guild.name} Staff Logs")
                await closer.send(embed=closer_embed, file=closer_file)
            except discord.Forbidden:
                print(f"Cannot DM closer {closer.id} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM to closer: {e}")

        # Lock ticket creator from chatting
        creator = interaction.guild.get_member(ticket["user_id"])
        if creator:
            try:
                await interaction.channel.set_permissions(
                    creator,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            except Exception:
                pass

        # Post closure control panel with Delete, Transcript, and Reopen buttons
        # Note: Channel will NOT delete until staff clicks the Delete Ticket button!
        closed_embed = discord.Embed(
            title=f"🔒 Ticket Closed — #{ticket['ticket_number']:04d}",
            description=(
                f"This ticket was closed by {interaction.user.mention}.\n"
                f"• An interactive HTML transcript has been sent to the creator's DM.\n\n"
                f"**Staff Actions:**\n"
                f"• Click **🗑️ Delete Ticket** when you are ready to permanently delete this channel.\n"
                f"• Click **🔓 Re-open** to unlock and continue this ticket.\n"
                f"• Click **📋 HTML Transcript** to download the chat archive."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.utcnow()
        )
        await interaction.channel.send(embed=closed_embed, view=ClosedTicketControlView())

    @discord.ui.button(
        label="📋 HTML Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:transcript"
    )
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_html_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is the interactive HTML transcript:**\n*(Open in your browser to view the Discord-styled chat)*", file=file)

class ClosedTicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🗑️ Delete Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:delete"
    )
    async def delete_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🗑️ **Deleting ticket channel in 3 seconds...**")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception:
            pass

    @discord.ui.button(
        label="📋 HTML Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:closed_transcript"
    )
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_html_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is the interactive HTML transcript:**\n*(Open in your browser to view the Discord-styled chat)*", file=file)

    @discord.ui.button(
        label="🔓 Re-open",
        style=discord.ButtonStyle.success,
        custom_id="ticket:reopen"
    )
    async def reopen_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        database.reopen_ticket(interaction.channel_id)

        # Restore permissions for creator
        creator = interaction.guild.get_member(ticket["user_id"])
        if creator:
            await interaction.channel.set_permissions(
                creator,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        embed = discord.Embed(
            title="🔓 Ticket Re-opened",
            description=f"Ticket #{ticket['ticket_number']:04d} has been re-opened by {interaction.user.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=TicketControlView())

class Ticket(commands.GroupCog, group_name="ticket", group_description="Commands for managing the support ticket system"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Deploy the interactive ticket creation panel")
    @app_commands.describe(
        channel="Channel to post the ticket panel into (default: current channel)",
        category="Category where new ticket channels will be created",
        support_role="Role that gets pinged and has access to tickets",
        log_channel="Channel where closed ticket transcripts will be posted"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        category: Optional[discord.CategoryChannel] = None,
        support_role: Optional[discord.Role] = None,
        log_channel: Optional[discord.TextChannel] = None
    ):
        target_channel = channel or interaction.channel
        
        database.set_ticket_settings(
            guild_id=interaction.guild_id,
            category_id=category.id if category else None,
            support_role_id=support_role.id if support_role else None,
            log_channel_id=log_channel.id if log_channel else None
        )

        embed = discord.Embed(
            title="🎫 Support Tickets",
            description=(
                "Need assistance or want to claim a giveaway prize?\n\n"
                "Click the **📩 Open Ticket** button below to create a private channel with our staff team!"
            ),
            color=discord.Color.brand_green()
        )
        embed.set_footer(text="Staff will assist you as soon as possible.")

        view = TicketPanelView()
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"✅ Ticket panel deployed successfully in {target_channel.mention}!",
            ephemeral=True
        )

    @app_commands.command(name="add", description="Add a user to the current ticket channel")
    @app_commands.describe(member="Member to add to this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        )
        await interaction.response.send_message(f"✅ Added {member.mention} to this ticket.")

    @app_commands.command(name="remove", description="Remove a user from the current ticket channel")
    @app_commands.describe(member="Member to remove from this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention} from this ticket.")

    @app_commands.command(name="close", description="Close the current ticket channel")
    async def ticket_close_cmd(self, interaction: discord.Interaction):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        view = TicketControlView()
        # Trigger the close button directly
        await view.close_ticket_button(interaction, None)

    # --- Traditional Prefix Commands ---

    @commands.command(name="ticketsetup")
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_setup(self, ctx: commands.Context):
        """Setup ticket panel in current channel: !ticketsetup"""
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description=(
                "Need assistance or want to claim a giveaway prize?\n\n"
                "Click the **📩 Open Ticket** button below to create a private channel with our staff team!"
            ),
            color=discord.Color.brand_green()
        )
        embed.set_footer(text="Staff will assist you as soon as possible.")
        view = TicketPanelView()
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()

    @commands.command(name="ticketadd")
    @commands.has_permissions(manage_messages=True)
    async def prefix_ticket_add(self, ctx: commands.Context, member: discord.Member):
        """Add user to current ticket: !ticketadd @member"""
        ticket = database.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        await ctx.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        )
        await ctx.send(f"✅ Added {member.mention} to this ticket.")

    @commands.command(name="ticketremove")
    @commands.has_permissions(manage_messages=True)
    async def prefix_ticket_remove(self, ctx: commands.Context, member: discord.Member):
        """Remove user from current ticket: !ticketremove @member"""
        ticket = database.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✅ Removed {member.mention} from this ticket.")

    @commands.command(name="ticketclose")
    async def prefix_ticket_close(self, ctx: commands.Context):
        """Close current ticket: !ticketclose"""
        ticket = database.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        # Generate HTML transcript
        transcript_file = await generate_html_transcript(ctx.channel, ticket, closed_by=ctx.author)

        database.close_ticket(ctx.channel.id, ctx.author.id)

        settings = database.get_ticket_settings(ctx.guild.id)
        if settings.get("log_channel_id"):
            log_channel = ctx.guild.get_channel(settings["log_channel_id"])
            if log_channel:
                log_embed = discord.Embed(
                    title=f"📋 Ticket Closed: #{ticket['ticket_number']:04d}",
                    description=(
                        f"**User:** <@{ticket['user_id']}>\n"
                        f"**Closed By:** {ctx.author.mention}\n"
                        f"**Channel:** {ctx.channel.name}\n\n"
                        f"📁 *Interactive HTML transcript attached below.*"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_channel.send(embed=log_embed, file=transcript_file)
                except Exception:
                    pass

        # Send HTML transcript directly to user DM
        target_user = ctx.guild.get_member(ticket["user_id"])
        if not target_user:
            try:
                target_user = await ctx.bot.fetch_user(ticket["user_id"])
            except Exception:
                target_user = None

        if target_user:
            try:
                dm_file = await generate_html_transcript(ctx.channel, ticket, closed_by=ctx.author)
                dm_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed",
                    description=(
                        f"Your ticket in **{ctx.guild.name}** has been closed.\n\n"
                        f"• **Closed By:** {ctx.author.mention} (`{ctx.author.name}`)\n"
                        f"• **An interactive HTML transcript of your conversation is attached below.**\n"
                        f"*(Download and open the file in your browser to view the Discord-styled chat)*"
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text=f"{ctx.guild.name} Support")
                await target_user.send(embed=dm_embed, file=dm_file)
            except discord.Forbidden:
                print(f"Cannot DM user {ticket['user_id']} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM: {e}")

        # Send HTML transcript directly to ticket closer DM (if different from creator)
        closer = ctx.author
        if closer and (target_user is None or closer.id != target_user.id):
            try:
                closer_file = await generate_html_transcript(ctx.channel, ticket, closed_by=closer)
                closer_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed (Staff Copy)",
                    description=(
                        f"You closed ticket **#{ticket['ticket_number']:04d}** in **{ctx.guild.name}**.\n\n"
                        f"• **Creator:** <@{ticket['user_id']}>\n"
                        f"• **Channel:** #{ctx.channel.name}\n"
                        f"• **An interactive HTML transcript of the ticket is attached below.**"
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                closer_embed.set_footer(text=f"{ctx.guild.name} Staff Logs")
                await closer.send(embed=closer_embed, file=closer_file)
            except discord.Forbidden:
                print(f"Cannot DM closer {closer.id} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM to closer: {e}")

        # Lock ticket creator from chatting
        creator = ctx.guild.get_member(ticket["user_id"])
        if creator:
            try:
                await ctx.channel.set_permissions(
                    creator,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            except Exception:
                pass

        # Post closure control panel with Delete, Transcript, and Reopen buttons
        closed_embed = discord.Embed(
            title=f"🔒 Ticket Closed — #{ticket['ticket_number']:04d}",
            description=(
                f"This ticket was closed by {ctx.author.mention}.\n"
                f"• An automated transcript has been sent to the creator's DM.\n\n"
                f"**Staff Actions:**\n"
                f"• Click **🗑️ Delete Ticket** to permanently delete this channel.\n"
                f"• Click **🔓 Re-open** to unlock and continue this ticket."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.utcnow()
        )
        await ctx.send(embed=closed_embed, view=ClosedTicketControlView())

    @app_commands.command(name="delete", description="Permanently delete the current ticket channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_delete_cmd(self, interaction: discord.Interaction):
        ticket = database.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        await interaction.response.send_message("🗑️ **Deleting ticket channel in 3 seconds...**")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception:
            pass

    @commands.command(name="ticketdelete", aliases=["tdelete"])
    @commands.has_permissions(manage_channels=True)
    async def prefix_ticket_delete(self, ctx: commands.Context):
        """Delete current ticket channel: !ticketdelete"""
        ticket = database.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        await ctx.send("🗑️ **Deleting ticket channel in 3 seconds...**")
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f"Ticket deleted by {ctx.author}")
        except Exception:
            pass

    @app_commands.command(name="setstaff", description="Set the staff role to be pinged when new tickets open")
    @app_commands.describe(role="Staff/Support role to ping")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_set_staff(self, interaction: discord.Interaction, role: discord.Role):
        database.set_support_role(interaction.guild_id, role.id)
        await interaction.response.send_message(f"✅ Staff role set to {role.mention}! Staff will now be automatically pinged whenever a new ticket is opened.")

    @commands.command(name="ticketstaff", aliases=["setstaff"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_set_staff(self, ctx: commands.Context, role: discord.Role):
        """Set staff role: !ticketstaff @Role"""
        database.set_support_role(ctx.guild.id, role.id)
        await ctx.send(f"✅ Staff role set to {role.mention}! Staff will now be automatically pinged whenever a new ticket is opened.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))

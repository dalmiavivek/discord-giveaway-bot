import re
import discord
from discord import app_commands
from discord.ext import commands
import io
import time
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import database
from transcript_generator import generate_html_transcript, generate_txt_transcript
from emojis import get_button_emoji

async def recover_ticket_from_channel(channel: discord.TextChannel) -> Optional[Dict[str, Any]]:
    """Self-heal / reconstruct ticket in database if it was lost due to bot restart."""
    if not isinstance(channel, discord.TextChannel):
        return None

    # Check if channel is already in database
    ticket = database.get_ticket_by_channel(channel.id)
    if ticket:
        return ticket

    settings = database.get_ticket_settings(channel.guild.id)
    is_ticket = False
    ticket_num = 1
    user_id = None

    # 1. Check category
    if channel.category:
        if settings.get("category_id") and channel.category_id == settings["category_id"]:
            is_ticket = True
        elif any(w in channel.category.name.lower() for w in ["ticket", "support", "claim"]):
            is_ticket = True

    # 2. Check topic
    if channel.topic:
        m = re.search(r"Ticket #(\d+).*?\((\d+)\)", channel.topic)
        if m:
            is_ticket = True
            ticket_num = int(m.group(1))
            user_id = int(m.group(2))
        elif "ticket" in channel.topic.lower():
            is_ticket = True
            m_num = re.search(r"Ticket #(\d+)", channel.topic, re.IGNORECASE)
            if m_num:
                ticket_num = int(m_num.group(1))
            m_u = re.search(r"\((\d{15,22})\)", channel.topic)
            if m_u:
                user_id = int(m_u.group(1))

    # 3. Check channel name: e.g. "ticket-username-0001" or "closed-username-0001"
    if channel.name.startswith(("ticket-", "closed-")):
        is_ticket = True
        m_name = re.search(r"(\d+)$", channel.name)
        if m_name and not ticket_num:
            try:
                ticket_num = int(m_name.group(1))
            except Exception:
                pass

    # 4. Check initial messages in history
    first_bot_msg = None
    try:
        async for msg in channel.history(limit=5, oldest_first=True):
            if msg.author.id == channel.guild.me.id:
                first_bot_msg = msg
                if msg.embeds:
                    for emb in msg.embeds:
                        if emb.title and "ticket" in emb.title.lower():
                            is_ticket = True
                            if not ticket_num:
                                m_t = re.search(r"#(\d+)", emb.title)
                                if m_t:
                                    ticket_num = int(m_t.group(1))
                        if emb.description and not user_id:
                            m_desc = re.search(r"<@!?(\d+)>", emb.description)
                            if m_desc:
                                user_id = int(m_desc.group(1))
                if msg.content and not user_id:
                    m_mentions = re.findall(r"<@!?(\d+)>", msg.content)
                    for uid in m_mentions:
                        if int(uid) != channel.guild.me.id:
                            user_id = int(uid)
                            break
            if is_ticket and user_id:
                break
    except Exception:
        pass

    if not is_ticket:
        return None

    # If user_id wasn't found, look in permission overwrites
    if not user_id:
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Role) or target.id == channel.guild.default_role.id:
                continue
            if target.id == channel.guild.me.id:
                continue
            if getattr(target, "bot", False):
                continue
            if overwrite.view_channel is True or overwrite.send_messages is True:
                user_id = target.id
                break

    # Fallback to guild owner and 1 so tracking NEVER fails for valid ticket channels
    if not user_id:
        user_id = channel.guild.owner_id
    if not ticket_num:
        ticket_num = 1

    # Determine status (check channel name, topic, and permissions)
    is_closed = False
    if channel.name.startswith("closed-") or (channel.topic and "[closed]" in channel.topic.lower()):
        is_closed = True
    else:
        member = channel.guild.get_member(user_id)
        if member:
            perms = channel.overwrites_for(member)
            if perms.send_messages is False:
                is_closed = True

    status = "closed" if is_closed else "open"

    # Re-insert into database
    with database.get_connection() as conn:
        conn.execute("""
            INSERT INTO tickets (guild_id, channel_id, user_id, ticket_number, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                status = excluded.status
        """, (channel.guild.id, channel.id, user_id, ticket_num, status, time.time()))
        conn.commit()

    # Update ticket counter in settings if higher
    if settings.get("ticket_counter", 0) < ticket_num:
        with database.get_connection() as conn:
            conn.execute("""
                INSERT INTO ticket_settings (guild_id, ticket_counter)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    ticket_counter = MAX(ticket_counter, ?)
            """, (channel.guild.id, ticket_num, ticket_num))
            conn.commit()

    # If category wasn't remembered in ticket_settings, save it now!
    if channel.category_id and not settings.get("category_id"):
        database.set_ticket_settings(
            guild_id=channel.guild.id,
            category_id=channel.category_id
        )

    return database.get_ticket_by_channel(channel.id)

class TicketRenameModal(discord.ui.Modal, title="Rename Ticket Channel"):
    new_name = discord.ui.TextInput(
        label="New Ticket Channel Name",
        style=discord.TextStyle.short,
        placeholder="e.g. claim-nitro, resolved, vip-help",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        clean = re.sub(r"[^a-zA-Z0-9_\-]", "-", self.new_name.value.strip().lower()).strip("-")
        if not clean:
            await interaction.response.send_message("❌ Please provide a valid channel name.", ephemeral=True)
            return

        clean = clean[:100]
        old_name = interaction.channel.name

        try:
            await interaction.channel.edit(name=clean, reason=f"Ticket renamed by {interaction.user}")
            embed = discord.Embed(
                title="✏️ Ticket Renamed",
                description=f"Ticket channel was renamed from `#{old_name}` to **#{clean}** by {interaction.user.mention}.",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot lacks permission to edit channel names.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to rename channel: {e}", ephemeral=True)

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

        try:
            settings = database.get_ticket_settings(guild.id)
            ticket_num = database.increment_ticket_counter(guild.id)
            clean_username = re.sub(r"[^a-zA-Z0-9_\-]", "", user.name.lower()) or "user"
            channel_name = f"ticket-{clean_username[:10]}-{ticket_num:04d}"

            # Permission Overwrites
            creator = guild.get_member(user.id)
            if not creator:
                try:
                    creator = await guild.fetch_member(user.id)
                except Exception:
                    creator = user

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                creator: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
            }

            bot_member = guild.me or guild.get_member(interaction.client.user.id)
            if bot_member:
                overwrites[bot_member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    manage_messages=True
                )

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
                if not category:
                    try:
                        category = await guild.fetch_channel(settings["category_id"])
                    except Exception:
                        category = None

            if not category:
                # Auto-detect category with 'ticket' or 'support' in the name
                for cat in guild.categories:
                    if any(w in cat.name.lower() for w in ["ticket", "support", "claim"]):
                        category = cat
                        database.set_ticket_settings(guild.id, category_id=cat.id)
                        break

            if not category:
                # Auto-create category if none exists
                try:
                    category = await guild.create_category("Tickets", reason="Support Ticket System")
                    database.set_ticket_settings(guild.id, category_id=category.id)
                except Exception:
                    category = None

            ticket_channel = None
            try:
                ticket_channel = await guild.create_text_channel(
                    name=channel_name,
                    category=category if isinstance(category, discord.CategoryChannel) else None,
                    overwrites=overwrites,
                    topic=f"Ticket #{ticket_num:04d} | Creator: {user.display_name} ({user.id})"
                )
            except discord.HTTPException:
                # Fallback: if category is full (50 channels limit) or invalid, retry without category
                try:
                    ticket_channel = await guild.create_text_channel(
                        name=channel_name,
                        category=None,
                        overwrites=overwrites,
                        topic=f"Ticket #{ticket_num:04d} | Creator: {user.display_name} ({user.id})"
                    )
                except Exception as inner_e:
                    await interaction.followup.send(f"❌ Failed to create ticket channel: {inner_e}", ephemeral=True)
                    return
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to create ticket channel: {e}", ephemeral=True)
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

            # Send confirmation with direct jump button (NEVER mention channel ID to prevent #unknown)
            jump_view = discord.ui.View()
            jump_view.add_item(discord.ui.Button(
                label=f"Open #{ticket_channel.name}",
                url=ticket_channel.jump_url,
                style=discord.ButtonStyle.link,
                emoji="🎫"
            ))

            await interaction.followup.send(
                f"✅ Your ticket **#{ticket_channel.name}** has been created!\n👉 [Click here to open #{ticket_channel.name}]({ticket_channel.jump_url})",
                view=jump_view,
                ephemeral=True
            )
        except Exception as err:
            print(f"Error creating ticket: {err}")
            await interaction.followup.send(f"❌ Failed to create ticket: {err}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self, label: str = "Open Ticket", emoji: Optional[str] = None):
        super().__init__(timeout=None)
        self.clear_items()

        btn_emoji = None
        if emoji:
            if emoji.startswith("<") and emoji.endswith(">"):
                try:
                    btn_emoji = discord.PartialEmoji.from_str(emoji)
                except Exception:
                    btn_emoji = emoji
            else:
                btn_emoji = emoji
        else:
            btn_emoji = get_button_emoji("TICKET_OPEN", "✅")

        button = discord.ui.Button(
            label=label,
            emoji=btn_emoji,
            style=discord.ButtonStyle.secondary,  # Sleek dark charcoal style matching Discord dark mode
            custom_id="ticket:create"
        )
        button.callback = self.open_ticket_callback
        self.add_item(button)

    async def open_ticket_callback(self, interaction: discord.Interaction):
        # Check if user already has an active open ticket
        existing = database.get_user_open_ticket(interaction.guild_id, interaction.user.id)
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            if not ch:
                try:
                    ch = await interaction.guild.fetch_channel(existing["channel_id"])
                except Exception:
                    ch = None

            # If channel doesn't exist in Discord, is deleted, or doesn't start with ticket-
            if not ch or not ch.name.startswith("ticket-"):
                database.close_ticket(existing["channel_id"], interaction.user.id)
            elif not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild):
                # Non-admin user: check if channel is accessible to them
                perms = ch.permissions_for(interaction.user)
                if not perms.view_channel or not perms.send_messages:
                    database.close_ticket(existing["channel_id"], interaction.user.id)
                else:
                    jump_view = discord.ui.View()
                    jump_view.add_item(discord.ui.Button(
                        label=f"Go to #{ch.name}",
                        url=ch.jump_url,
                        style=discord.ButtonStyle.link,
                        emoji="🎫"
                    ))
                    await interaction.response.send_message(
                        f"❌ You already have an active ticket: [#{ch.name}]({ch.jump_url})",
                        view=jump_view,
                        ephemeral=True
                    )
                    return
            else:
                # Admins and server owners: auto-close previous test record and proceed
                database.close_ticket(existing["channel_id"], interaction.user.id)

        # Open the modal
        await interaction.response.send_modal(TicketReasonModal())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close",
        emoji=get_button_emoji("TICKET_CLOSE", "🔒"),
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close"
    )
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        await interaction.response.defer()

        # Generate transcripts in both HTML and TXT formats
        log_html = await generate_html_transcript(interaction.channel, ticket, closed_by=interaction.user)
        log_txt = await generate_txt_transcript(interaction.channel, ticket, closed_by=interaction.user)

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
                        f"📁 *Both HTML (interactive) and TXT transcripts attached below.*"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_channel.send(embed=log_embed, files=[log_html, log_txt])
                except Exception as e:
                    print(f"Error logging transcript: {e}")

        # Send both HTML and TXT transcripts directly to user DM
        target_user = interaction.guild.get_member(ticket["user_id"])
        if not target_user:
            try:
                target_user = await interaction.client.fetch_user(ticket["user_id"])
            except Exception:
                target_user = None

        if target_user:
            try:
                dm_html = await generate_html_transcript(interaction.channel, ticket, closed_by=interaction.user)
                dm_txt = await generate_txt_transcript(interaction.channel, ticket, closed_by=interaction.user)
                dm_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed",
                    description=(
                        f"Your ticket in **{interaction.guild.name}** has been closed.\n\n"
                        f"• **Closed By:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                        f"• **Transcripts:** Attached below in both formats:\n"
                        f"  - 🌐 `.html` (Open in any web browser for a Discord-styled view)\n"
                        f"  - 📄 `.txt` (Plain text format)"
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text=f"{interaction.guild.name} Support")
                await target_user.send(embed=dm_embed, files=[dm_html, dm_txt])
            except discord.Forbidden:
                print(f"Cannot DM user {ticket['user_id']} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM: {e}")

        # Send both HTML and TXT transcripts to ticket closer DM (if different from creator)
        closer = interaction.user
        if closer and (target_user is None or closer.id != target_user.id):
            try:
                closer_html = await generate_html_transcript(interaction.channel, ticket, closed_by=closer)
                closer_txt = await generate_txt_transcript(interaction.channel, ticket, closed_by=closer)
                closer_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed (Staff Copy)",
                    description=(
                        f"You closed ticket **#{ticket['ticket_number']:04d}** in **{interaction.guild.name}**.\n\n"
                        f"• **Creator:** <@{ticket['user_id']}>\n"
                        f"• **Channel:** #{interaction.channel.name}\n"
                        f"• **Transcripts:** Attached below in both `.html` and `.txt` formats."
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                closer_embed.set_footer(text=f"{interaction.guild.name} Staff Logs")
                await closer.send(embed=closer_embed, files=[closer_html, closer_txt])
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

        # Post closure control panel with Delete, HTML, TXT, and Reopen buttons
        closed_embed = discord.Embed(
            title=f"🔒 Ticket Closed — #{ticket['ticket_number']:04d}",
            description=(
                f"This ticket was closed by {interaction.user.mention}.\n"
                f"• Transcripts (HTML & TXT) have been sent to the creator's DM.\n\n"
                f"**Staff Actions:**\n"
                f"• Click **🗑️ Delete Ticket** when you are ready to permanently delete this channel.\n"
                f"• Click **🔓 Re-open** to unlock and continue this ticket.\n"
                f"• Download transcript: **🌐 HTML** or **📄 TXT** below."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.utcnow()
        )
        await interaction.channel.send(embed=closed_embed, view=ClosedTicketControlView())

    @discord.ui.button(
        label="HTML Transcript",
        emoji=get_button_emoji("TICKET_HTML", "🌐"),
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:html_transcript"
    )
    async def html_transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_html_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is your HTML transcript:**\n*(Open in any browser for a Discord-styled view)*", file=file)

    @discord.ui.button(
        label="TXT Transcript",
        emoji=get_button_emoji("TICKET_TXT", "📄"),
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:txt_transcript"
    )
    async def txt_transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_txt_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is your TXT transcript:**", file=file)

    @discord.ui.button(
        label="Rename",
        emoji=get_button_emoji("TICKET_RENAME", "✏️"),
        style=discord.ButtonStyle.primary,
        custom_id="ticket:rename"
    )
    async def rename_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_channels:
            settings = database.get_ticket_settings(interaction.guild_id)
            staff_role_id = settings.get("support_role_id")
            user_role_ids = [r.id for r in interaction.user.roles]
            if not staff_role_id or staff_role_id not in user_role_ids:
                await interaction.response.send_message("❌ Only support staff can rename ticket channels.", ephemeral=True)
                return

        await interaction.response.send_modal(TicketRenameModal())

class ClosedTicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Delete Ticket",
        emoji=get_button_emoji("TICKET_DELETE", "🗑️"),
        style=discord.ButtonStyle.danger,
        custom_id="ticket:delete"
    )
    async def delete_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await recover_ticket_from_channel(interaction.channel)
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
        label="Re-open",
        emoji=get_button_emoji("TICKET_REOPEN", "🔓"),
        style=discord.ButtonStyle.success,
        custom_id="ticket:reopen"
    )
    async def reopen_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await recover_ticket_from_channel(interaction.channel)
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

    @discord.ui.button(
        label="HTML Transcript",
        emoji=get_button_emoji("TICKET_HTML", "🌐"),
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:closed_html"
    )
    async def html_transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_html_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is your HTML transcript:**\n*(Open in any browser for a Discord-styled view)*", file=file)

    @discord.ui.button(
        label="TXT Transcript",
        emoji=get_button_emoji("TICKET_TXT", "📄"),
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:closed_txt"
    )
    async def txt_transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        file = await generate_txt_transcript(interaction.channel, ticket)
        await interaction.followup.send("📄 **Here is your TXT transcript:**", file=file)

    @discord.ui.button(
        label="Rename",
        emoji=get_button_emoji("TICKET_RENAME", "✏️"),
        style=discord.ButtonStyle.primary,
        custom_id="ticket:closed_rename"
    )
    async def closed_rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This channel is not a tracked ticket.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_channels:
            settings = database.get_ticket_settings(interaction.guild_id)
            staff_role_id = settings.get("support_role_id")
            user_role_ids = [r.id for r in interaction.user.roles]
            if not staff_role_id or staff_role_id not in user_role_ids:
                await interaction.response.send_message("❌ Only support staff can rename ticket channels.", ephemeral=True)
                return

        await interaction.response.send_modal(TicketRenameModal())

def build_ticket_panel_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    banner_url: Optional[str] = None
) -> discord.Embed:
    """Build support ticket panel embed with modern Discord styling."""
    embed_title = title or "🎫 Support Tickets"
    desc = description or (
        "**Need assistance or want to claim a giveaway prize?**\n\n"
        "Click the button below to create a private ticket with our staff team!\n\n"
        "• Private channel created exclusively for you\n"
        "• Direct assistance from staff members\n"
        "• Safe, secure, and recorded transcript"
    )
    embed = discord.Embed(
        title=embed_title,
        description=desc,
        color=discord.Color(0x2B2D31)
    )
    embed.set_footer(text="Staff will assist you as soon as possible.")
    if banner_url:
        embed.set_image(url=banner_url)

    return embed

class Ticket(commands.GroupCog, group_name="ticket", group_description="Commands for managing the support ticket system"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Deploy the interactive ticket creation panel")
    @app_commands.describe(
        channel="Channel to post the ticket panel into (default: current channel)",
        button_label="Custom text on the button (default: Open Ticket)",
        button_emoji="Custom emoji on the button (e.g. <:emoji_name:id> or 📩 or ✅)",
        banner_url="Image URL to display at the bottom of the embed",
        title="Custom panel title (default: 🎫 Support Tickets)",
        description="Custom panel description",
        category="Category where new ticket channels will be created",
        support_role="Role that gets pinged and has access to tickets",
        log_channel="Channel where closed ticket transcripts will be posted"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        button_label: Optional[str] = None,
        button_emoji: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        banner_url: Optional[str] = None,
        category: Optional[discord.CategoryChannel] = None,
        support_role: Optional[discord.Role] = None,
        log_channel: Optional[discord.TextChannel] = None
    ):
        target_channel = channel or interaction.channel
        settings = database.get_ticket_settings(interaction.guild_id)

        final_label = button_label or settings.get("button_label") or "Open Ticket"
        final_emoji = button_emoji or settings.get("button_emoji") or None
        final_banner = banner_url or settings.get("banner_url")

        database.set_ticket_settings(
            guild_id=interaction.guild_id,
            category_id=category.id if category else None,
            support_role_id=support_role.id if support_role else None,
            log_channel_id=log_channel.id if log_channel else None,
            button_label=final_label,
            button_emoji=final_emoji,
            banner_url=final_banner
        )

        embed = build_ticket_panel_embed(
            title=title,
            description=description,
            banner_url=final_banner
        )

        view = TicketPanelView(label=final_label, emoji=final_emoji)
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"✅ Ticket panel deployed successfully in {target_channel.mention}!",
            ephemeral=True
        )

    @app_commands.command(name="add", description="Add a user to the current ticket channel")
    @app_commands.describe(member="Member to add to this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await recover_ticket_from_channel(interaction.channel)
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
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention} from this ticket.")

    @app_commands.command(name="close", description="Close the current ticket channel")
    async def ticket_close_cmd(self, interaction: discord.Interaction):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        view = TicketControlView()
        # Trigger the close button directly
        await view.close_ticket_button(interaction, None)

    @app_commands.command(name="reset", description="Reset stuck ticket records so users can open tickets")
    @app_commands.describe(user="Optional user to reset, or leave empty to reset all")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_reset_cmd(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        with database.get_connection() as conn:
            if user:
                conn.execute("UPDATE tickets SET status = 'closed' WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, user.id))
                await interaction.response.send_message(f"✅ Reset all open ticket records for {user.mention}!", ephemeral=True)
            else:
                conn.execute("UPDATE tickets SET status = 'closed' WHERE guild_id = ?", (interaction.guild_id,))
                await interaction.response.send_message("✅ Successfully reset all open ticket records for this server!", ephemeral=True)

    # --- Traditional Prefix Commands ---

    @commands.command(name="ticketsetup")
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_setup(self, ctx: commands.Context):
        """Setup ticket panel in current channel: !ticketsetup"""
        settings = database.get_ticket_settings(ctx.guild.id)
        label = settings.get("button_label") or "Open Ticket"
        emoji = settings.get("button_emoji") or None
        banner = settings.get("banner_url")

        embed = build_ticket_panel_embed(banner_url=banner)
        view = TicketPanelView(label=label, emoji=emoji)
        await ctx.send(embed=embed, view=view)
        try:
            await ctx.message.delete()
        except discord.DiscordException:
            pass

    @commands.command(name="ticketemoji", aliases=["ticketsetemoji"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_emoji(self, ctx: commands.Context, emoji: str):
        """Set the custom button emoji for tickets: !ticketemoji <:name:id> or !ticketemoji 📩"""
        database.set_ticket_settings(
            guild_id=ctx.guild.id,
            button_emoji=emoji
        )
        await ctx.send(f"✅ Ticket button emoji updated to: {emoji}\nRun `!ticketsetup` to deploy the updated panel.")

    @commands.command(name="ticketbutton")
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_button(self, ctx: commands.Context, *, label: str):
        """Set the button text for tickets: !ticketbutton Open Ticket"""
        database.set_ticket_settings(
            guild_id=ctx.guild.id,
            button_label=label
        )
        await ctx.send(f"✅ Ticket button text updated to: **{label}**\nRun `!ticketsetup` to deploy the updated panel.")

    @commands.command(name="ticketadd")
    @commands.has_permissions(manage_messages=True)
    async def prefix_ticket_add(self, ctx: commands.Context, member: discord.Member):
        """Add user to current ticket: !ticketadd @member"""
        ticket = await recover_ticket_from_channel(ctx.channel)
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
        ticket = await recover_ticket_from_channel(ctx.channel)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✅ Removed {member.mention} from this ticket.")

    @commands.command(name="ticketclose")
    async def prefix_ticket_close(self, ctx: commands.Context):
        """Close current ticket: !ticketclose"""
        ticket = await recover_ticket_from_channel(ctx.channel)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        # Generate transcripts in both HTML and TXT formats
        log_html = await generate_html_transcript(ctx.channel, ticket, closed_by=ctx.author)
        log_txt = await generate_txt_transcript(ctx.channel, ticket, closed_by=ctx.author)

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
                        f"📁 *Both HTML (interactive) and TXT transcripts attached below.*"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_channel.send(embed=log_embed, files=[log_html, log_txt])
                except Exception:
                    pass

        # Send both HTML and TXT transcripts directly to user DM
        target_user = ctx.guild.get_member(ticket["user_id"])
        if not target_user:
            try:
                target_user = await ctx.bot.fetch_user(ticket["user_id"])
            except Exception:
                target_user = None

        if target_user:
            try:
                dm_html = await generate_html_transcript(ctx.channel, ticket, closed_by=ctx.author)
                dm_txt = await generate_txt_transcript(ctx.channel, ticket, closed_by=ctx.author)
                dm_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed",
                    description=(
                        f"Your ticket in **{ctx.guild.name}** has been closed.\n\n"
                        f"• **Closed By:** {ctx.author.mention} (`{ctx.author.name}`)\n"
                        f"• **Transcripts:** Attached below in both formats:\n"
                        f"  - 🌐 `.html` (Open in any web browser for a Discord-styled view)\n"
                        f"  - 📄 `.txt` (Plain text format)"
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text=f"{ctx.guild.name} Support")
                await target_user.send(embed=dm_embed, files=[dm_html, dm_txt])
            except discord.Forbidden:
                print(f"Cannot DM user {ticket['user_id']} (DMs closed)")
            except Exception as e:
                print(f"Error sending DM: {e}")

        # Send both HTML and TXT transcripts directly to ticket closer DM (if different from creator)
        closer = ctx.author
        if closer and (target_user is None or closer.id != target_user.id):
            try:
                closer_html = await generate_html_transcript(ctx.channel, ticket, closed_by=closer)
                closer_txt = await generate_txt_transcript(ctx.channel, ticket, closed_by=closer)
                closer_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket['ticket_number']:04d} Closed (Staff Copy)",
                    description=(
                        f"You closed ticket **#{ticket['ticket_number']:04d}** in **{ctx.guild.name}**.\n\n"
                        f"• **Creator:** <@{ticket['user_id']}>\n"
                        f"• **Channel:** #{ctx.channel.name}\n"
                        f"• **Transcripts:** Attached below in both `.html` and `.txt` formats."
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                closer_embed.set_footer(text=f"{ctx.guild.name} Staff Logs")
                await closer.send(embed=closer_embed, files=[closer_html, closer_txt])
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

    @commands.command(name="ticketreset", aliases=["ticketclear", "treset"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_ticket_reset(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Reset stuck open tickets: !ticketreset [optional @user]"""
        with database.get_connection() as conn:
            if user:
                conn.execute("UPDATE tickets SET status = 'closed' WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
                await ctx.send(f"✅ Reset all open ticket records for {user.mention}! They can now create tickets.")
            else:
                conn.execute("UPDATE tickets SET status = 'closed' WHERE guild_id = ?", (ctx.guild.id,))
                await ctx.send("✅ Successfully reset all open ticket records for this server! Anyone can now create tickets.")

    @app_commands.command(name="delete", description="Permanently delete the current ticket channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_delete_cmd(self, interaction: discord.Interaction):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        await interaction.response.send_message("🗑️ **Deleting ticket channel in 3 seconds...**")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception:
            pass

    @commands.command(name="delete", aliases=["ticketdelete", "tdelete"])
    @commands.has_permissions(manage_channels=True)
    async def prefix_ticket_delete(self, ctx: commands.Context):
        """Delete current ticket channel: !delete"""
        ticket = await recover_ticket_from_channel(ctx.channel)
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

    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(new_name="New name for the ticket channel (e.g. claim-nitro or issue-resolved)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_rename_cmd(self, interaction: discord.Interaction, new_name: str):
        ticket = await recover_ticket_from_channel(interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        clean = re.sub(r"[^a-zA-Z0-9_\-]", "-", new_name.strip().lower()).strip("-")
        if not clean:
            await interaction.response.send_message("❌ Please provide a valid channel name.", ephemeral=True)
            return

        clean = clean[:100]
        old_name = interaction.channel.name

        try:
            await interaction.channel.edit(name=clean, reason=f"Ticket renamed by {interaction.user}")
            embed = discord.Embed(
                title="✏️ Ticket Renamed",
                description=f"Ticket channel was renamed from `#{old_name}` to **#{clean}** by {interaction.user.mention}.",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot lacks permission to edit channel names.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to rename channel: {e}", ephemeral=True)

    @commands.command(name="rename", aliases=["ticketrename", "trename"])
    @commands.has_permissions(manage_channels=True)
    async def prefix_ticket_rename(self, ctx: commands.Context, *, new_name: str):
        """Rename the current ticket channel: !rename <new-name>"""
        ticket = await recover_ticket_from_channel(ctx.channel)
        if not ticket:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        clean = re.sub(r"[^a-zA-Z0-9_\-]", "-", new_name.strip().lower()).strip("-")
        if not clean:
            await ctx.send("❌ Please provide a valid channel name.")
            return

        clean = clean[:100]
        old_name = ctx.channel.name

        try:
            await ctx.channel.edit(name=clean, reason=f"Ticket renamed by {ctx.author}")
            embed = discord.Embed(
                title="✏️ Ticket Renamed",
                description=f"Ticket channel was renamed from `#{old_name}` to **#{clean}** by {ctx.author.mention}.",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot lacks permission to edit channel names.")
        except Exception as e:
            await ctx.send(f"❌ Failed to rename channel: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Self-heal tickets and clean up ghost open tickets on startup."""
        recovered = 0
        for guild in self.bot.guilds:
            settings = database.get_ticket_settings(guild.id)
            
            # If category_id is missing, auto-detect category named 'tickets' or 'support'
            if not settings.get("category_id"):
                for cat in guild.categories:
                    if any(w in cat.name.lower() for w in ["ticket", "support", "claim"]):
                        database.set_ticket_settings(guild.id, category_id=cat.id)
                        print(f"📁 Auto-detected ticket category '{cat.name}' for {guild.name}")
                        break

            # Purge ghost open tickets from DB where channel no longer exists
            with database.get_connection() as conn:
                open_rows = conn.execute(
                    "SELECT channel_id FROM tickets WHERE guild_id = ? AND status = 'open'",
                    (guild.id,)
                ).fetchall()
                for r in open_rows:
                    ch = guild.get_channel(r["channel_id"])
                    if not ch:
                        conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (r["channel_id"],))
                conn.commit()

            # Scan channels to recover genuine tickets
            for channel in guild.text_channels:
                is_ticket_name = bool(re.match(r"^(?:ticket|closed)-.+?-\d+$", channel.name))
                has_ticket_topic = bool(channel.topic and "Ticket #" in channel.topic)
                if is_ticket_name or has_ticket_topic:
                    existing = database.get_ticket_by_channel(channel.id)
                    if not existing:
                        rec = await recover_ticket_from_channel(channel)
                        if rec:
                            recovered += 1

        if recovered > 0:
            print(f"🛠️ Self-healed {recovered} ticket(s) after bot restart!")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Track whenever a ticket channel is deleted and identify who deleted it from Audit Log."""
        if not isinstance(channel, discord.TextChannel) or not channel.name.startswith(("ticket-", "closed-")):
            return

        # Mark ticket as closed in database
        database.close_ticket(channel.id, closed_by=0)

        # Audit log lookup to detect who deleted it (e.g. Anti-Nuke bot or staff member)
        deleter = "Unknown (Check Server Audit Log)"
        reason = "No reason provided"
        try:
            await asyncio.sleep(0.5)
            async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=5):
                if entry.target.id == channel.id:
                    deleter = f"{entry.user} ({entry.user.id})"
                    reason = entry.reason or "No reason provided"
                    break
        except Exception as e:
            deleter = f"Audit log inaccessible ({e})"

        print(f"🚨 [CHANNEL DELETED] #{channel.name} was deleted by: {deleter} | Reason: {reason}")

        # If log channel configured, notify server staff
        settings = database.get_ticket_settings(channel.guild.id)
        if settings.get("log_channel_id"):
            log_ch = channel.guild.get_channel(settings["log_channel_id"])
            if log_ch:
                embed = discord.Embed(
                    title="⚠️ Ticket Channel Deleted",
                    description=(
                        f"**Channel:** `#{channel.name}`\n"
                        f"**Deleted By:** {deleter}\n"
                        f"**Reason:** {reason}\n\n"
                        f"💡 *If this channel was deleted immediately after creation by an Anti-Nuke / Security bot "
                        f"(such as Wick, Security, or Carl-bot), please whitelist this bot or exempt it from Channel Spam limits.*"
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_ch.send(embed=embed)
                except Exception:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))

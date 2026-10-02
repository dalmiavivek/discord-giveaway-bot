import html
import io
import re
from datetime import datetime
from typing import Optional, List
import discord

def format_markdown(text: str) -> str:
    """Safely format basic Discord markdown into HTML."""
    if not text:
        return ""
    
    # 1. Escape HTML first for safety
    escaped = html.escape(text)

    # 2. Code blocks (```lang ... ```)
    def codeblock_repl(m):
        code = m.group(2)
        return f'<pre class="code-block"><code>{code}</code></pre>'
    escaped = re.sub(r'```([a-zA-Z0-9_+-]*)\n?(.*?)```', codeblock_repl, escaped, flags=re.DOTALL)

    # 3. Inline code (`code`)
    escaped = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', escaped)

    # 4. Bold + Italic (***text***)
    escaped = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', escaped)

    # 5. Bold (**text**)
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped)

    # 6. Italic (*text* or _text_)
    escaped = re.sub(r'\*(.*?)\*', r'<em>\1</em>', escaped)
    escaped = re.sub(r'(?<!\w)_(.*?)_(?!\w)', r'<em>\1</em>', escaped)

    # 7. Underline (__text__)
    escaped = re.sub(r'__(.*?)__', r'<u>\1</u>', escaped)

    # 8. Strikethrough (~~text~~)
    escaped = re.sub(r'~~(.*?)~~', r'<s>\1</s>', escaped)

    # 9. Spoilers (||text||)
    escaped = re.sub(r'\|\|(.*?)\|\|', r'<span class="spoiler" onclick="this.classList.toggle(\'revealed\')">\1</span>', escaped)

    # 10. Discord user/role mentions (<@12345> or <@&12345>)
    escaped = re.sub(r'&lt;@!?(\d+)&gt;', r'<span class="mention">@User</span>', escaped)
    escaped = re.sub(r'&lt;@&amp;(\d+)&gt;', r'<span class="mention">@Role</span>', escaped)
    escaped = re.sub(r'&lt;#(\d+)&gt;', r'<span class="mention">#channel</span>', escaped)

    # 11. Convert line breaks
    escaped = escaped.replace('\n', '<br>')

    return escaped

async def generate_html_transcript(
    channel: discord.TextChannel,
    ticket: dict,
    closed_by: Optional[discord.Member | discord.User] = None
) -> discord.File:
    """Generate a high-fidelity Discord Dark Mode HTML transcript for a ticket."""
    guild = channel.guild
    ticket_num = ticket.get("ticket_number", 0)
    created_at_dt = datetime.utcfromtimestamp(ticket.get("created_at", datetime.utcnow().timestamp()))
    closed_at_str = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")

    # Fetch messages
    messages: List[discord.Message] = []
    async for msg in channel.history(limit=1000, oldest_first=True):
        messages.append(msg)

    # Collect author details
    ticket_creator_id = ticket.get("user_id")
    creator_member = guild.get_member(ticket_creator_id)
    creator_name = creator_member.display_name if creator_member else f"User ({ticket_creator_id})"
    closed_by_name = closed_by.display_name if closed_by else "Staff"

    guild_icon_url = guild.icon.url if guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png"

    # Build Messages HTML
    messages_html = []
    last_author_id = None
    last_time = None

    for msg in messages:
        author = msg.author
        avatar_url = author.display_avatar.url if author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        msg_time_str = msg.created_at.strftime("%m/%d/%Y %I:%M %p")

        # Compact spacing if consecutive messages from same user within 5 minutes
        is_same_author = (author.id == last_author_id)
        is_recent = False
        if last_time and (msg.created_at - last_time).total_seconds() < 300:
            is_recent = True

        compact = is_same_author and is_recent
        last_author_id = author.id
        last_time = msg.created_at

        # Bot tag
        bot_tag = '<span class="bot-tag">BOT</span>' if author.bot else ''

        # Content HTML
        content_html = f'<div class="msg-text">{format_markdown(msg.clean_content)}</div>' if msg.clean_content else ''

        # Attachments HTML
        attachments_html = []
        for att in msg.attachments:
            ext = att.filename.split('.')[-1].lower()
            if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                attachments_html.append(
                    f'<div class="attachment-image-wrap">'
                    f'<a href="{att.url}" target="_blank">'
                    f'<img src="{att.url}" alt="{html.escape(att.filename)}" class="attachment-image" loading="lazy" />'
                    f'</a></div>'
                )
            else:
                attachments_html.append(
                    f'<div class="attachment-file">'
                    f'<span class="file-icon">📎</span>'
                    f'<a href="{att.url}" target="_blank" class="file-link">{html.escape(att.filename)}</a>'
                    f'<span class="file-size">({round(att.size / 1024, 1)} KB)</span>'
                    f'</div>'
                )
        attachments_block = "".join(attachments_html)

        # Embeds HTML
        embeds_html = []
        for emb in msg.embeds:
            color_hex = f"#{emb.color.value:06x}" if emb.color else "#2b2d31"
            title_html = f'<div class="embed-title">{html.escape(emb.title)}</div>' if emb.title else ''
            desc_html = f'<div class="embed-desc">{format_markdown(emb.description)}</div>' if emb.description else ''
            
            fields_html = []
            for f in emb.fields:
                inline_class = "embed-field-inline" if f.inline else ""
                fields_html.append(
                    f'<div class="embed-field {inline_class}">'
                    f'<div class="field-name">{html.escape(f.name)}</div>'
                    f'<div class="field-value">{format_markdown(f.value)}</div>'
                    f'</div>'
                )
            fields_block = f'<div class="embed-fields">{"".join(fields_html)}</div>' if fields_html else ''
            
            footer_html = ''
            if emb.footer and emb.footer.text:
                footer_html = f'<div class="embed-footer">{html.escape(emb.footer.text)}</div>'

            embeds_html.append(
                f'<div class="embed-container" style="border-left-color: {color_hex};">'
                f'{title_html}{desc_html}{fields_block}{footer_html}'
                f'</div>'
            )
        embeds_block = "".join(embeds_html)

        if not compact:
            msg_item = f'''
            <div class="message-group">
                <img class="avatar" src="{avatar_url}" alt="{html.escape(author.name)}" />
                <div class="message-body">
                    <div class="message-header">
                        <span class="username">{html.escape(author.display_name)}</span>
                        {bot_tag}
                        <span class="timestamp">{msg_time_str}</span>
                    </div>
                    {content_html}
                    {attachments_block}
                    {embeds_block}
                </div>
            </div>
            '''
        else:
            msg_item = f'''
            <div class="message-group compact">
                <div class="message-body compact-body">
                    {content_html}
                    {attachments_block}
                    {embeds_block}
                </div>
            </div>
            '''
        messages_html.append(msg_item)

    all_messages_rendered = "\n".join(messages_html)

    # Full HTML Document
    html_document = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ticket #{ticket_num:04d} Transcript — {html.escape(guild.name)}</title>
    <style>
        :root {{
            --bg-primary: #313338;
            --bg-secondary: #2b2d31;
            --bg-tertiary: #1e1f22;
            --text-normal: #dbdee1;
            --text-muted: #949ba4;
            --text-header: #f2f3f5;
            --brand-blurple: #5865f2;
            --brand-green: #23a55a;
            --border-subtle: #3f4147;
            --code-bg: #232428;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            font-family: "gg sans", "Noto Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 15px;
            line-height: 1.375rem;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }}
        header {{
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border-subtle);
            padding: 18px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        .header-left {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}
        .guild-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid var(--border-subtle);
        }}
        .header-title {{
            display: flex;
            flex-direction: column;
        }}
        .header-guild-name {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-header);
        }}
        .header-channel {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}
        .header-stats {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .pill {{
            background-color: var(--bg-tertiary);
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.8rem;
            color: var(--text-normal);
            border: 1px solid var(--border-subtle);
        }}
        .pill strong {{
            color: var(--text-header);
        }}
        .transcript-container {{
            max-width: 1050px;
            width: 100%;
            margin: 0 auto;
            padding: 24px 20px;
            flex-grow: 1;
        }}
        .message-group {{
            display: flex;
            gap: 16px;
            padding: 6px 0;
            margin-top: 10px;
        }}
        .message-group:hover {{
            background-color: rgba(2, 2, 2, 0.07);
        }}
        .message-group.compact {{
            margin-top: 0;
            padding: 2px 0 2px 56px;
        }}
        .avatar {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
        }}
        .message-body {{
            display: flex;
            flex-direction: column;
            width: 100%;
        }}
        .message-header {{
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .username {{
            font-weight: 600;
            color: var(--text-header);
            font-size: 0.95rem;
        }}
        .bot-tag {{
            background-color: var(--brand-blurple);
            color: #ffffff;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 3px;
            text-transform: uppercase;
            line-height: 1;
        }}
        .timestamp {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}
        .msg-text {{
            color: var(--text-normal);
            word-break: break-word;
        }}
        .mention {{
            background-color: rgba(88, 101, 242, 0.3);
            color: #c9cdfb;
            padding: 1px 4px;
            border-radius: 3px;
            font-weight: 500;
        }}
        .inline-code {{
            background-color: var(--code-bg);
            padding: 2px 5px;
            border-radius: 4px;
            font-family: Consolas, monospace;
            font-size: 0.88rem;
        }}
        .code-block {{
            background-color: var(--code-bg);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 10px 14px;
            margin: 6px 0;
            font-family: Consolas, monospace;
            font-size: 0.85rem;
            overflow-x: auto;
            color: #e3e5e8;
        }}
        .spoiler {{
            background-color: #202225;
            color: #202225;
            padding: 1px 4px;
            border-radius: 3px;
            cursor: pointer;
            user-select: none;
        }}
        .spoiler.revealed {{
            background-color: rgba(255, 255, 255, 0.1);
            color: var(--text-normal);
        }}
        .attachment-image-wrap {{
            margin-top: 8px;
        }}
        .attachment-image {{
            max-width: 480px;
            max-height: 340px;
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
            object-fit: cover;
        }}
        .attachment-file {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-subtle);
            padding: 8px 14px;
            border-radius: 6px;
            margin-top: 6px;
        }}
        .file-link {{
            color: #00a8fc;
            text-decoration: none;
            font-weight: 500;
        }}
        .file-link:hover {{
            text-decoration: underline;
        }}
        .file-size {{
            color: var(--text-muted);
            font-size: 0.75rem;
        }}
        .embed-container {{
            background-color: var(--bg-secondary);
            border-left: 4px solid var(--brand-blurple);
            border-radius: 4px;
            padding: 12px 16px;
            margin-top: 8px;
            max-width: 540px;
        }}
        .embed-title {{
            font-weight: 700;
            color: var(--text-header);
            margin-bottom: 6px;
        }}
        .embed-desc {{
            color: var(--text-normal);
            font-size: 0.9rem;
            margin-bottom: 8px;
        }}
        .embed-fields {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 8px;
        }}
        .embed-field {{
            flex: 1 1 100%;
        }}
        .embed-field-inline {{
            flex: 1 1 calc(50% - 12px);
            min-width: 140px;
        }}
        .field-name {{
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--text-header);
            margin-bottom: 2px;
        }}
        .field-value {{
            font-size: 0.85rem;
            color: var(--text-normal);
        }}
        .embed-footer {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 6px;
        }}
        footer {{
            background-color: var(--bg-secondary);
            border-top: 1px solid var(--border-subtle);
            text-align: center;
            padding: 14px;
            color: var(--text-muted);
            font-size: 0.8rem;
            margin-top: auto;
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <img class="guild-avatar" src="{guild_icon_url}" alt="{html.escape(guild.name)}" />
            <div class="header-title">
                <span class="header-guild-name">{html.escape(guild.name)}</span>
                <span class="header-channel">#{html.escape(channel.name)}</span>
            </div>
        </div>
        <div class="header-stats">
            <div class="pill">Ticket: <strong>#{ticket_num:04d}</strong></div>
            <div class="pill">Creator: <strong>{html.escape(creator_name)}</strong></div>
            <div class="pill">Closed by: <strong>{html.escape(closed_by_name)}</strong></div>
            <div class="pill">Messages: <strong>{len(messages)}</strong></div>
        </div>
    </header>

    <main class="transcript-container">
        {all_messages_rendered}
    </main>

    <footer>
        Ticket #{ticket_num:04d} • Created: {created_at_dt.strftime("%Y-%m-%d %H:%M:%S UTC")} • Closed: {closed_at_str} • Exported with LoveAffair Bot
    </footer>
</body>
</html>'''

    return discord.File(
        io.BytesIO(html_document.encode("utf-8")),
        filename=f"transcript-ticket-{ticket_num:04d}.html"
    )

async def generate_txt_transcript(
    channel: discord.TextChannel,
    ticket: dict,
    closed_by: Optional[discord.Member | discord.User] = None
) -> discord.File:
    """Generate a clean plain text (.txt) transcript for a ticket."""
    guild = channel.guild
    ticket_num = ticket.get("ticket_number", 0)
    created_at_dt = datetime.utcfromtimestamp(ticket.get("created_at", datetime.utcnow().timestamp()))
    closed_by_str = closed_by.name if closed_by else "Staff"

    lines = []
    lines.append(f"==================================================")
    lines.append(f"           TICKET #{ticket_num:04d} TRANSCRIPT")
    lines.append(f"==================================================")
    lines.append(f"Server:     {guild.name} ({guild.id})")
    lines.append(f"Channel:    #{channel.name}")
    lines.append(f"Creator ID: {ticket.get('user_id')}")
    lines.append(f"Created:    {created_at_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"Closed By:  {closed_by_str}")
    lines.append(f"Exported:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"==================================================\n")

    async for msg in channel.history(limit=1000, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author.name}#{msg.author.discriminator}" if msg.author.discriminator != "0" else msg.author.name
        bot_suffix = " [BOT]" if msg.author.bot else ""
        content = msg.clean_content or ""
        
        line = f"[{ts}] {author}{bot_suffix}: {content}"
        
        if msg.attachments:
            att_urls = ", ".join([att.url for att in msg.attachments])
            line += f" [Attachments: {att_urls}]"
            
        if msg.embeds:
            for emb in msg.embeds:
                emb_details = []
                if emb.title:
                    emb_details.append(f"Title: {emb.title}")
                if emb.description:
                    emb_details.append(f"Desc: {emb.description}")
                for f in emb.fields:
                    emb_details.append(f"{f.name}: {f.value}")
                if emb_details:
                    line += f" [Embed: {' | '.join(emb_details)}]"
                    
        lines.append(line)

    lines.append(f"\n==================== END OF TRANSCRIPT ====================")
    txt_content = "\n".join(lines)

    return discord.File(
        io.BytesIO(txt_content.encode("utf-8")),
        filename=f"transcript-ticket-{ticket_num:04d}.txt"
    )


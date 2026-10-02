# 🎁 Advanced Discord Giveaway Bot

A modern, full-featured Discord Giveaway Bot built with **Python 3.10+** and **`discord.py` v2**.

## ✨ Features

- **Interactive UI**: Users click a stylish `🎉 Enter Giveaway` button to participate.
- **Requirement-Based Giveaways**: Restrict giveaways based on:
  - 👑 **Role Requirement**: Must have a specific role (e.g. VIP, Subscriber).
  - 💬 **Message Count**: Must have sent a minimum number of server messages.
  - 🎙️ **Voice Channel (VC) Time**: Must have spent a minimum number of minutes in voice channels.
- **Persistent Storage (SQLite)**: Giveaways, participant entries, and activity stats survive bot reboots.
- **Reboot Resilience**: Active buttons automatically restore their event handlers when the bot restarts.
- **Slash Commands**: Modern Discord commands with autocomplete and descriptions.
- **Reroll & Management**: End giveaways early or reroll new winners on the fly.
- **Activity Tracker**: Built-in listener tracks user message counts and VC minutes per server.
- **Support Ticket System**: Complete private ticket manager with interactive creation panel, modal reason input, permission isolation, user management, and automated transcript exports on close.

---

## 📋 Commands

Both **Slash Commands** (`/`) and **Prefix Commands** (default: `!`, e.g. `!gstart`) are supported! You can also mention the bot instead of using a prefix (e.g. `@Bot help`).

### Prefix Commands (`!`)

| Command | Permission | Description |
| :--- | :--- | :--- |
| `!gstart <duration> <winners> <prize>` | Manage Server | Quick start a giveaway (e.g. `!gstart 1h 1w Discord Nitro`). |
| `!gend <giveaway_id>` | Manage Server | Instantly end a giveaway early. |
| `!greroll <giveaway_id> [winners]` | Manage Server | Pick new winner(s) for an ended giveaway. |
| `!glist` | Everyone | View all currently active giveaways in the server. |
| `!stats [@member]` | Everyone | Check message count and voice channel time. |
| `!ticketsetup` | Manage Server | Post the ticket creation panel with the "Open Ticket" button. |
| `!ticketstaff @role` | Manage Server | Set staff role to ping on new tickets. |
| `!ticketadd @member` | Manage Messages | Add a user to the current ticket channel. |
| `!ticketremove @member` | Manage Messages | Remove a user from the current ticket channel. |
| `!ticketclose` | Everyone in ticket | Close the ticket, send transcripts to DM & logs, and lock channel. |
| `!delete` | Manage Channels | Permanently delete the ticket channel (aliases: `!ticketdelete`, `!tdelete`). |
| `!setprefix <new_prefix>` | Manage Server | Change the command prefix for this server (stored in SQLite). |
| `!prefix` | Everyone | View the current prefix for this server. |
| `!help` | Everyone | Show all available commands in an embed. |

### Slash Commands (`/`)

| Command | Permission | Description |
| :--- | :--- | :--- |
| `/giveaway start` | Manage Server | Launch a giveaway with prize, duration, winners, and optional role/message/VC requirements. |
| `/giveaway end` | Manage Server | Instantly end a running giveaway and pick winners. |
| `/giveaway reroll` | Manage Server | Pick new winner(s) for an ended giveaway. |
| `/giveaway list` | Everyone | View all currently active giveaways in the server. |
| `/user-stats` | Everyone | Check your own or another member's message count and voice channel time. |
| `/ticket setup` | Manage Server | Deploy ticket panel with options for category, support role, and log channel. |
| `/ticket setstaff` | Manage Server | Set the staff role to ping on new tickets. |
| `/ticket add` | Manage Messages | Add a user to the current ticket channel. |
| `/ticket remove` | Manage Messages | Remove a user from the current ticket channel. |
| `/ticket close` | Everyone in ticket | Close ticket, generate text transcript, send to DM, and show delete button. |
| `/ticket delete` | Manage Channels | Permanently delete the ticket channel. |
| `/setprefix` | Manage Server | Change the command prefix for this server. |
| `/prefix` | Everyone | Show the current prefix. |

---

## 🚀 Setup & Installation

### 1. Create a Discord Bot Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give it a name (e.g., `Giveaway Master`).
3. In the left sidebar, navigate to **Bot**:
   - Click **Add Bot** (if prompted).
   - Under **Privileged Gateway Intents**, enable all three:
     - ✅ **Presence Intent**
     - ✅ **Server Members Intent**
     - ✅ **Message Content Intent**
   - Click **Reset Token** and copy your **Bot Token**.

### 2. Invite the Bot to Your Server
1. In the Developer Portal, go to **OAuth2** ➡️ **URL Generator**.
2. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `Manage Server`
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Read Message History`
   - ✅ `Use External Emojis`
   - ✅ `View Channels`
4. Copy the generated URL at the bottom and open it in your browser to invite the bot to your server.

---

### 3. Local Installation & Configuration

1. Clone or open the bot directory:
   ```bash
   cd /Users/vivekdalmia/.gemini/antigravity/scratch/discord-giveaway-bot
   ```

2. (Optional but recommended) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure your token:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and paste your bot token:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```

5. Run the bot:
   ```bash
   python3 main.py
   ```

---

## 🎯 How to Run a Giveaway with Requirements

### Example 1: Simple Giveaway
```
/giveaway start prize: Nitro Monthly duration: 2h winners: 1
```

### Example 2: Requirement Giveaway (Role + Messages + Voice Activity)
```
/giveaway start prize: Steam Game Key duration: 1d winners: 2 required_role: @Server Booster min_messages: 50 min_vc_minutes: 60
```
- Only members with the `@Server Booster` role who have sent at least **50 messages** and spent **60 minutes** in voice channels will be allowed to enter!
- If a user clicks `🎉 Enter Giveaway` and does not meet the requirements, the bot sends them a private ephemeral message explaining exactly which requirements they still need to meet.

---

## 🛠️ Project Structure

```
discord-giveaway-bot/
├── cogs/
│   ├── activity.py       # Message & voice channel tracking + stats commands
│   ├── giveaway.py       # Giveaway commands (slash & prefix), button view, and auto-ending loop
│   ├── settings.py       # Prefix configuration (!setprefix, /setprefix) & !help
│   └── ticket.py         # Ticket panel, modal, transcripts, and ticket controls
├── database.py           # SQLite storage for giveaways, tickets, activity, and prefixes
├── main.py               # Bot entry point, dynamic prefix resolver, and slash command sync
├── requirements.txt      # Python dependencies (discord.py, python-dotenv)
├── Procfile              # Cloud process declaration for Railway/Heroku
├── .env.example          # Environment variables template
└── README.md             # Setup and usage guide
```

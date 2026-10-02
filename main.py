import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database
from cogs.giveaway import GiveawayView
from cogs.ticket import TicketPanelView, TicketControlView

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

def get_prefix(bot: commands.Bot, message: discord.Message):
    if not message.guild:
        return commands.when_mentioned_or("!")(bot, message)
    prefix = database.get_guild_prefix(message.guild.id)
    return commands.when_mentioned_or(prefix)(bot, message)

class GiveawayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # 1. Initialize SQLite tables
        database.init_db()
        print("📁 Database initialized successfully.")

        # 2. Load Cogs
        await self.load_extension("cogs.giveaway")
        await self.load_extension("cogs.activity")
        await self.load_extension("cogs.settings")
        await self.load_extension("cogs.ticket")
        print("🧩 Cogs loaded: giveaway, activity, settings, ticket.")

        # 3. Re-register persistent views so buttons work after reboot
        active_giveaways = database.get_active_giveaways()
        for gw in active_giveaways:
            self.add_view(GiveawayView(gw["id"]))
        
        # Register persistent ticket views
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        print(f"🔄 Restored {len(active_giveaways)} active giveaway view(s) & ticket views.")

        # 4. Sync slash commands globally
        try:
            synced = await self.tree.sync()
            print(f"⚡ Synced {len(synced)} slash command(s).")
        except Exception as e:
            print(f"⚠️ Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"🤖 Logged in as {self.user} (ID: {self.user.id})")
        print(f"🌐 Connected to {len(self.guilds)} server(s).")
        
        # Set bot activity status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="giveaways | !help or /giveaway"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

async def main():
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN is missing!")
        print("👉 Please create a .env file and add DISCORD_TOKEN=your_token_here")
        print("   See .env.example for reference.")
        sys.exit(1)

    bot = GiveawayBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot shut down cleanly.")

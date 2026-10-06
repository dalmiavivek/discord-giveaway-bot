import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database
from presence import apply_bot_presence
from cogs.giveaway import GiveawayView
from cogs.ticket import TicketPanelView, TicketControlView, ClosedTicketControlView

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

def get_prefix(bot: commands.Bot, message: discord.Message):
    if not message.guild:
        return commands.when_mentioned_or("!", "$")(bot, message)
    
    guild_p = database.get_guild_prefix(message.guild.id)
    prefixes = [guild_p]
    if "$" not in prefixes:
        prefixes.append("$")
    if "!" not in prefixes:
        prefixes.append("!")
        
    if message.author and database.has_no_prefix(message.author.id):
        prefixes.append("")
        
    return commands.when_mentioned_or(*prefixes)(bot, message)

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
        await self.load_extension("cogs.noprefix")
        await self.load_extension("cogs.moderation")
        print("🧩 Cogs loaded: giveaway, activity, settings, ticket, noprefix, moderation.")

        # 3. Re-register persistent views so buttons work after reboot
        active_giveaways = database.get_active_giveaways()
        for gw in active_giveaways:
            self.add_view(GiveawayView(gw["id"]))
        
        # Register persistent ticket views
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        self.add_view(ClosedTicketControlView())
        print(f"🔄 Restored {len(active_giveaways)} active giveaway view(s) & ticket views.")

        # 4. Sync slash commands globally
        try:
            synced = await self.tree.sync()
            print(f"⚡ Synced {len(synced)} slash command(s).")
        except Exception as e:
            print(f"⚠️ Failed to sync commands: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        print(f"🎉 Joined new guild: {guild.name} (ID: {guild.id}) with {guild.member_count} members.")
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"⚡ Instantly synced slash commands to new guild: {guild.name}")
        except Exception as e:
            print(f"⚠️ Could not guild-sync slash commands on join: {e}")

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ You lack required permissions to use this command: `{perms}`")
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ I don't have the required permissions in this channel: `{perms}`\n👉 Please grant my role **Administrator** or permission to send messages/embeds.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`. Run `{ctx.prefix}help` for usage.")
        elif isinstance(error, commands.CheckFailure):
            pass
        else:
            print(f"⚠️ Command error in {ctx.command}: {error}")

    async def on_ready(self):
        print(f"🤖 Logged in as {self.user} (ID: {self.user.id})")
        print(f"🌐 Connected to {len(self.guilds)} server(s): {[g.name for g in self.guilds]}")
        
        # Auto-sync slash commands to all current guilds for instant availability
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except Exception:
                pass
        
        # Set dual bot presence (Custom Status under username + Purple Streaming / Watching)
        saved = database.get_bot_presence()
        await apply_bot_presence(
            bot=self,
            custom_status=saved.get("custom_status") or os.getenv("BOT_CUSTOM_STATUS") or "Serving for /loveaffair",
            activity_text=saved.get("activity_text") or os.getenv("BOT_ACTIVITY_TEXT") or "giveaways | !help or /giveaway",
            activity_type=saved.get("activity_type") or os.getenv("BOT_ACTIVITY_TYPE") or "streaming",
            status=saved.get("status") or os.getenv("BOT_STATUS") or "online"
        )

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

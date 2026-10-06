import os
import asyncio
import discord
from discord.ext import tasks
from typing import Optional, Dict, Any
import database

class PresenceManager:
    _instance = None

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.rotator_index = 0
        self.is_rotating = False
        PresenceManager._instance = self
        try:
            self.rotator_task.start()
        except RuntimeError:
            pass

    @classmethod
    def get_instance(cls, bot: Optional[discord.Client] = None):
        if cls._instance is None and bot is not None:
            cls._instance = PresenceManager(bot)
        return cls._instance

    @tasks.loop(seconds=20)
    async def rotator_task(self):
        if not self.is_rotating or not self.bot.is_ready():
            return
        
        saved = database.get_bot_presence()
        stream_text = saved.get("activity_text") or "giveaways | !help or /giveaway"
        custom_text = saved.get("custom_status") or "Serving for /loveaffair"
        
        try:
            if self.rotator_index % 2 == 0:
                # Step 1: Purple Streaming status
                stream = discord.Streaming(
                    name=stream_text,
                    url="https://www.twitch.tv/discord"
                )
                await self.bot.change_presence(activity=stream, status=discord.Status.online)
            else:
                # Step 2: Custom Status under username
                custom = discord.CustomActivity(name=custom_text)
                await self.bot.change_presence(activity=custom, status=discord.Status.online)
            
            self.rotator_index += 1
        except Exception as e:
            print(f"Error rotating bot status: {e}")

    @rotator_task.before_loop
    async def before_rotator(self):
        await self.bot.wait_until_ready()

    async def apply(
        self,
        mode: str = "streaming",
        custom_status: Optional[str] = None,
        activity_text: Optional[str] = None,
        status: str = "online"
    ):
        mode_lower = (mode or "streaming").lower()
        stream_text = activity_text or "giveaways | !help or /giveaway"
        custom_text = custom_status or "Serving for /loveaffair"
        
        st_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd
        }
        st_obj = st_map.get((status or "online").lower(), discord.Status.online)

        if mode_lower in ["rotate", "both", "cycle"]:
            self.is_rotating = True
            self.rotator_index = 0
            # Start with Purple Streaming right away
            stream = discord.Streaming(name=stream_text, url="https://www.twitch.tv/discord")
            await self.bot.change_presence(activity=stream, status=st_obj)
        elif mode_lower in ["streaming", "purple", "stream"]:
            self.is_rotating = False
            # Pure purple streaming status
            stream = discord.Streaming(name=stream_text, url="https://www.twitch.tv/discord")
            await self.bot.change_presence(activity=stream, status=st_obj)
        elif mode_lower == "custom":
            self.is_rotating = False
            custom = discord.CustomActivity(name=custom_text)
            await self.bot.change_presence(activity=custom, status=st_obj)
        elif mode_lower == "watching":
            self.is_rotating = False
            act = discord.Activity(type=discord.ActivityType.watching, name=stream_text)
            await self.bot.change_presence(activity=act, status=st_obj)
        elif mode_lower == "playing":
            self.is_rotating = False
            act = discord.Game(name=stream_text)
            await self.bot.change_presence(activity=act, status=st_obj)
        elif mode_lower == "listening":
            self.is_rotating = False
            act = discord.Activity(type=discord.ActivityType.listening, name=stream_text)
            await self.bot.change_presence(activity=act, status=st_obj)
        else:
            self.is_rotating = False
            stream = discord.Streaming(name=stream_text, url="https://www.twitch.tv/discord")
            await self.bot.change_presence(activity=stream, status=st_obj)

async def apply_bot_presence(
    bot: discord.Client,
    custom_status: Optional[str] = None,
    activity_text: Optional[str] = None,
    activity_type: str = "streaming",
    status: str = "online"
):
    manager = PresenceManager.get_instance(bot)
    await manager.apply(
        mode=activity_type,
        custom_status=custom_status,
        activity_text=activity_text,
        status=status
    )

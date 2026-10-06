import os
import discord
from typing import Optional, Dict, Any
import database

async def apply_bot_presence(
    bot: discord.Client,
    custom_status: Optional[str] = None,
    activity_text: Optional[str] = None,
    activity_type: str = "streaming",
    status: str = "online",
    stream_url: str = "https://twitch.tv/discord"
):
    """
    Applies dual presence to Discord:
    1. Custom Status: appears directly under the username / speech bubble.
    2. Rich Presence: Streaming (turns status badge purple 🟣), Watching, Playing, etc.
    """
    activities = []

    # 1. Custom status (type 4) - appears next to avatar and directly below username
    if custom_status:
        activities.append(discord.CustomActivity(name=custom_status))

    # 2. Secondary Rich Activity (Streaming sets the purple avatar indicator!)
    if activity_text:
        act_lower = (activity_type or "streaming").lower()
        if act_lower in ["streaming", "stream", "purple"]:
            activities.append(discord.Streaming(name=activity_text, url=stream_url))
        elif act_lower == "watching":
            activities.append(discord.Activity(type=discord.ActivityType.watching, name=activity_text))
        elif act_lower == "playing":
            activities.append(discord.Game(name=activity_text))
        elif act_lower == "listening":
            activities.append(discord.Activity(type=discord.ActivityType.listening, name=activity_text))
        elif act_lower == "competing":
            activities.append(discord.Activity(type=discord.ActivityType.competing, name=activity_text))

    status_lower = (status or "online").lower()
    status_mapping = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    status_obj = status_mapping.get(status_lower, discord.Status.online)

    # Send multi-presence payload directly to Gateway
    if hasattr(bot, "ws") and bot.ws and hasattr(bot.ws, "send"):
        activity_dicts = [a.to_dict() for a in activities]
        payload = {
            'op': bot.ws.PRESENCE,
            'd': {
                'activities': activity_dicts,
                'afk': False,
                'since': 0,
                'status': status_lower,
            },
        }
        sent = discord.utils._to_json(payload)
        await bot.ws.send(sent)

        # Update local caches for bot member
        for guild in bot.guilds:
            if guild.me:
                guild.me.activities = tuple(activities)
                guild.me.status = status_obj
    else:
        primary = activities[0] if activities else None
        await bot.change_presence(activity=primary, status=status_obj)

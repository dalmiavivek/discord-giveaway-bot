import os
import discord
from typing import Optional

# Custom Discord Emoji configuration
# Format for custom Discord emojis: "<:emoji_name:emoji_id>" or "<a:animated_name:emoji_id>"
# Format for standard unicode emojis: "📩", "🔒", "🎉", etc.
BUTTON_EMOJIS = {
    "TICKET_OPEN": os.getenv("EMOJI_TICKET_OPEN", "📩"),
    "TICKET_CLOSE": os.getenv("EMOJI_TICKET_CLOSE", "🔒"),
    "TICKET_RENAME": os.getenv("EMOJI_TICKET_RENAME", "✏️"),
    "TICKET_DELETE": os.getenv("EMOJI_TICKET_DELETE", "🗑️"),
    "TICKET_REOPEN": os.getenv("EMOJI_TICKET_REOPEN", "🔓"),
    "TICKET_HTML": os.getenv("EMOJI_TICKET_HTML", "🌐"),
    "TICKET_TXT": os.getenv("EMOJI_TICKET_TXT", "📄"),
    "GIVEAWAY_ENTER": os.getenv("EMOJI_GIVEAWAY_ENTER", "🎉"),
}

def get_button_emoji(key: str, fallback: str = "") -> Optional[discord.PartialEmoji | str]:
    """Retrieve emoji, parsing custom <:name:id> strings into PartialEmoji, with fallback."""
    raw = BUTTON_EMOJIS.get(key, fallback)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        try:
            return discord.PartialEmoji.from_str(raw)
        except Exception:
            return fallback
    return raw

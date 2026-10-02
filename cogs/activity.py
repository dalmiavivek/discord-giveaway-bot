import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database
from cogs.giveaway import format_seconds

class Activity(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages and direct messages
        if message.author.bot or not message.guild:
            return

        database.increment_message_count(message.guild.id, message.author.id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        if member.bot or not member.guild:
            return

        guild_id = member.guild.id
        user_id = member.id

        # User joined a voice channel from no channel
        if before.channel is None and after.channel is not None:
            # Avoid counting AFK channels if guild has one configured
            if member.guild.afk_channel and after.channel.id == member.guild.afk_channel.id:
                return
            database.start_vc_session(guild_id, user_id)

        # User disconnected from voice channel
        elif before.channel is not None and after.channel is None:
            database.end_vc_session(guild_id, user_id)

        # User moved to/from AFK channel
        elif before.channel is not None and after.channel is not None:
            if member.guild.afk_channel:
                if after.channel.id == member.guild.afk_channel.id:
                    database.end_vc_session(guild_id, user_id)
                elif before.channel.id == member.guild.afk_channel.id:
                    database.start_vc_session(guild_id, user_id)

    @app_commands.command(name="user-stats", description="Check your or another member's tracked activity stats (messages & VC time)")
    @app_commands.describe(member="Member whose stats to view (defaults to you)")
    async def user_stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        stats = database.get_user_activity(interaction.guild_id, target.id)
        
        vc_formatted = format_seconds(stats["vc_seconds"])

        embed = discord.Embed(
            title=f"📊 Activity Stats: {target.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💬 Messages Sent", value=f"**{stats['message_count']}** messages", inline=True)
        embed.add_field(name="🎙️ Voice Channel Time", value=f"**{vc_formatted}**", inline=True)
        embed.set_footer(text="These stats are used for requirement-based giveaways!")

        await interaction.response.send_message(embed=embed)

    @commands.command(name="stats", aliases=["mystats", "activity"])
    async def prefix_user_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check activity stats: !stats [@member]"""
        target = member or ctx.author
        stats = database.get_user_activity(ctx.guild.id, target.id)
        
        vc_formatted = format_seconds(stats["vc_seconds"])

        embed = discord.Embed(
            title=f"📊 Activity Stats: {target.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💬 Messages Sent", value=f"**{stats['message_count']}** messages", inline=True)
        embed.add_field(name="🎙️ Voice Channel Time", value=f"**{vc_formatted}**", inline=True)
        embed.set_footer(text="These stats are used for requirement-based giveaways!")

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Activity(bot))

import discord

from lavalink import (
    TrackLoadFailedEvent,
    TrackStartEvent,
    TrackEndEvent,
    DefaultPlayer,
    AudioTrack,
    listener
)
from utils.useful import format_time, get_yt_thumbnail
from utils.views import NowPlayingView
from utils.data import colors, err
from utils.base import BaseEmbed
from utils.db import GuildDB
from utils.main import Cade

def add_bot_events(client: Cade):
    events = BotEvents(client)

    for listener in [x for x in dir(events) if not x.startswith(("_", "client", "react_roles"))]:
        client.add_listener(getattr(events, listener))

class BotEvents:
    def __init__(self, client: Cade):
        self.client = client

        self.react_roles = {
            "1️⃣": 820126482684313620,  # he/him
            "2️⃣": 820126584442322984,  # she/her
            "3️⃣": 820126629945933874,  # they/them
        }

    async def on_guild_remove(self, guild: discord.Guild):
        # remove guild from database on leave
        await GuildDB(guild).remove()

    async def on_member_join(self, member: discord.Member):
        welcome_field = (await GuildDB(member.guild).get()).welcome

        # if the welcome field wasn't found / was disabled
        if not welcome_field:
            return

        welcome_msg, channel_id = welcome_field

        # get channel from id stored in "welcome"
        channel = await self.client.fetch_channel(channel_id)

        # insert mentions into message
        welcome_msg: str = welcome_msg.replace(r"{user}", member.mention)

        await channel.send(welcome_msg)

    async def on_raw_reaction_add(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.react_roles[event.emoji.name])

            # add the corresponding role from the reaction
            await event.member.add_roles(role)

    async def on_raw_reaction_remove(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.react_roles[event.emoji.name])

            # remove the corresponding role
            member = guild.get_member(event.user_id)
            await member.remove_roles(role)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member == member.guild.me:  # if bot was disconnected from vc
            player = self.client.lavalink.get_player(member)

            # if a player still exists, cancel it
            if not after.channel and player:
                player.queue.clear()
                await player.stop()

class TrackEvents:
    """Contains functions that are used when a track does something"""
    def __init__(self, client: Cade):
        self.client = client

    @listener(TrackLoadFailedEvent)
    async def on_track_load_failed(self, event: TrackLoadFailedEvent):
        """Event handler for when a spotify track can't be loaded"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        guild = self.client.get_guild(player.guild_id)
        channel = guild.get_channel(player.fetch("channel"))

        await channel.send(err.NO_SPOTIFY_ON_YT(track.title))
        await player.skip()

    @listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        """Event handler for when a track starts"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        if player.loop:
            return

        # get the channel, requester, and track duration
        guild = self.client.get_guild(player.guild_id)
        channel = guild.get_channel(player.fetch("channel"))
        requester = guild.get_member(track.requester)

        duration = format_time(ms = track.duration)

        # create the embed
        playing = discord.Embed(
            title = track.title,
            url = track.uri,
            description = f"Duration: `{duration}` | Sent by {requester.mention}",
            color = colors.PLAYING_TRACK
        )

        # add footer and thumbnail
        playing.set_author(name = "Now Playing", icon_url = requester.display_avatar)
        playing.set_thumbnail(url = get_yt_thumbnail(track.identifier))

        player.store("message", await channel.send(embed = playing))
        player.store("requester", track.requester)
        player.store("loopcount", 0)

    @listener(TrackEndEvent)
    async def on_track_end(self, event: TrackEndEvent):
        """Event handler for when a track ends"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        if player.loop:
            # increase loopcount by 1
            return player.store("loopcount", player.fetch("loopcount") + 1)

        guild = self.client.get_guild(player.guild_id)
        track_id = f"{guild.id}:{track.identifier}"

        # disable .nowplaying buttons for the track
        for view in self.client.persistent_views:
            if isinstance(view, NowPlayingView) and view.id == track_id and view.children[0].label != "skipped":
                await view.message.edit(view = view.disable("ended"))

        requester = player.fetch("requester")
        duration = format_time(ms = track.duration)

        # create "played track" embed
        played = BaseEmbed(
            title = track.title,
            url = track.uri,
            description = f"was played by <@{requester}> | Duration: `{duration}`"
        )

        # edit the original "now playing" message with the embed
        message: discord.Message = player.fetch("message")
        await message.edit(embed = played)
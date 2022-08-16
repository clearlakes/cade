import discord
from discord.ext import commands

from lavalink import (
    TrackLoadFailedEvent,
    TrackStartEvent,
    TrackEndEvent,
    DefaultPlayer,
    AudioTrack,
    listener
)

from utils.music.tracks import get_yt_thumbnail
from utils.dataclasses import colors, err
from utils.functions import format_time
from utils.views import NowPlayingView

class TrackEvents:
    """Contains functions that are used when a track does something"""
    def __init__(self, client: commands.Bot):
        self.client = client

    @listener(TrackLoadFailedEvent)
    async def on_track_load_failed(self, event: TrackLoadFailedEvent):
        """Event handler for when a spotify track can't be loaded"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        guild = self.client.get_guild(player.guild_id)
        channel = guild.get_channel(player.fetch('channel'))

        await channel.send(err.SPOTIFY_NF(track.title))
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
        channel = guild.get_channel(player.fetch('channel'))
        requester = guild.get_member(track.requester)

        duration = format_time(track.duration // 1000)

        # create the embed
        playing = discord.Embed(
            title = track.title,
            url = track.uri,
            description = f"Duration: `{duration}` | Sent by {requester.mention}",
            color = colors.PLAYING_TRACK
        )

        # add footer and thumbnail
        playing.set_author(name="Now Playing", icon_url = requester.display_avatar)
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
                view = view.disable("ended")
                await view.msg.edit(view = view)

        requester = player.fetch("requester")
        duration = format_time(track.duration // 1000)

        # create "played track" embed
        played = discord.Embed(
            title = track.title,
            url = track.uri,
            description = f"was played by <@{requester}> | Duration: `{duration}`",
            color = discord.Color.embed_background()
        )

        # edit the original "now playing" message with the embed
        message: discord.Message = player.fetch("message")
        await message.edit(embed = played)
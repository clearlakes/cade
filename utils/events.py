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
from utils.useful import format_time, get_yt_thumbnail, strip_pl_name
from utils.views import NowPlayingView
from utils.data import colors, err
from utils.base import BaseEmbed
from utils.db import GuildDB
from utils.main import Cade

def add_bot_events(client: Cade):
    bot_events = BotEvents(client)

    for listener_func in [x for x in dir(bot_events) if x.startswith("on")]:
        client.add_listener(getattr(bot_events, listener_func))

class BotEvents:
    def __init__(self, client: Cade):
        self.client = client

        self.fm_react_roles = {
            "1️⃣": 820126482684313620,  # he/him
            "2️⃣": 820126584442322984,  # she/her
            "3️⃣": 820126629945933874,  # they/them
        }

    async def on_guild_join(self, guild: discord.Guild):
        await GuildDB(guild).cancel_remove()  # cancel removal if the bot ever left before

    async def on_guild_remove(self, guild: discord.Guild):
        await GuildDB(guild).remove()  # removes the guild from the database 3 days after leaving

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
        if event.message_id == 820147742382751785:  # check if funny museum
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.fm_react_roles[event.emoji.name])

            # add the corresponding role
            await event.member.add_roles(role)

    async def on_raw_reaction_remove(self, event: discord.RawReactionActionEvent):
        if event.message_id == 820147742382751785:  # check if funny museum
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.fm_react_roles[event.emoji.name])

            # remove the corresponding role
            await guild.get_member(event.user_id).remove_roles(role)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member == member.guild.me:  # if bot was disconnected from vc
            player = self.client.lavalink.get_player(member)

            # if a player still exists, cancel it
            if not after.channel and player:
                player.queue.clear()
                await player.stop()

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await ctx.send(err.CMD_USAGE((await GuildDB(ctx.guild).get()).prefix, ctx.command))  # send command usage
        elif isinstance(error, (commands.CheckFailure, commands.DisabledCommand, commands.CommandNotFound)):
            return  # ignore errors that aren't important

        raise error

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

        playing = discord.Embed(
            description = f"**[{track.title}]({track.uri})**\n`{duration}` • {requester.mention}",
            color = colors.PLAYING_TRACK
        )

        playing.set_author(name = "Now Playing", icon_url = requester.display_avatar)
        playing.set_thumbnail(url = get_yt_thumbnail(track.identifier))

        player.store("prev_pl_name", player.fetch("pl_name"))
        player.store("pl_name", player.current.extra["pl_name"])

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
            if isinstance(view, NowPlayingView) and view.id == track_id and not view.is_finished():
                await view.disable("ended")

        requester = player.fetch("requester")
        duration = format_time(ms = track.duration)

        # create "played track" embed
        played = BaseEmbed(
            title = track.title,
            url = track.uri,
            description = f"was played by <@{requester}> | Duration: `{duration}`"
        )

        track_info = f"[{track.title}]({track.uri}) `{duration}`"

        played = BaseEmbed(
            description = f"Played {track_info} • <@{requester}>"
        )

        orig_message: discord.Message = player.fetch("message")

        # group track with others from the same playlist if they're from one
        if (pl := player.fetch("pl_name")) and pl == player.fetch("prev_pl_name"):
            channel = self.client.get_channel(player.fetch("channel"))  # find "played (track)" message
            message = [m async for m in channel.history(limit = 2)][-1]

            if (
                message.author == self.client.user and          # message is from the bot
                (em := message.embeds) and                      # message has an embed
                "Played" in (desc := em[0].description) and     # embed is of a played track(s)
                desc.count("\n") < 15                           # embed has less than 15 lines
            ):
                # add the playlist name if it's not there
                if "Played tracks from" not in desc:
                    desc = strip_pl_name(pl, desc).strip(f" • <@{requester}>")
                    desc = desc.replace("Played", f"<@{requester}> • Played tracks from **{pl}**:\n- ")

                # add the track's information
                desc += f"\n- {strip_pl_name(pl, track_info)}"
                new_embed = message.embeds[0].copy()
                new_embed.description = desc

                # edit the message and delete the "now playing" message
                await message.edit(embed = new_embed)
                await orig_message.delete()
                return

        # edit the original "now playing" message with the embed
        await orig_message.edit(embed = played)
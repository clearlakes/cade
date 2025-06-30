import discord
from discord.ext import commands
from lavalink import (
    AudioTrack,
    DefaultPlayer,
    QueueEndEvent,
    TrackEndEvent,
    TrackStartEvent,
    listener,
)

from .base import BaseEmbed, CadeElegy
from .db import GuildDB
from .useful import format_time, get_artwork_url, strip_pl_name
from .vars import colors, err, bot
from .views import NowPlayingView
from .tracks import _get_lyrics


async def _dc(player: DefaultPlayer, guild: discord.Guild):
    player.queue.clear()
    await player.stop()

    # disconnects the bot's voice client
    # without this it won't be able to connect again

    await guild.voice_client.disconnect(force=True)


class BotEvents:
    def __init__(self, client: CadeElegy):
        self.client = client

    def add(self):
        # adds all events to the bot
        for listener_func in [x for x in dir(self) if x.startswith("on")]:
            self.client.add_listener(getattr(self, listener_func))

    async def on_guild_join(self, guild: discord.Guild):
        await GuildDB(
            guild
        ).cancel_remove()  # cancel removal if the bot ever left before

    async def on_guild_remove(self, guild: discord.Guild):
        await GuildDB(
            guild
        ).remove()  # removes the guild from the database 3 days after leaving

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

    async def on_message(self, message: discord.Message):
        match message.content.lower():
            case str(x) if any(_ in x for _ in ["mold cade", "mold you cade", "moldy cade"]):
                await message.add_reaction(bot.CADEMOLDY)
            case str(x) if any(_ in x for _ in ["hi cade", "hey cade", "sorry cade"]):
                await message.add_reaction(bot.CADE)
            case str(x) if any(_ in x for _ in ["thank you cade", "love you cade", "love cade", "thanks cade"]):
                await message.add_reaction(bot.CADEHAPPY)
            case str(x) if any(_ in x for _ in ["hate you cade", "hate cade"]):
                await message.add_reaction(bot.CADEMAD)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        player = self.client.lavalink.get_player(member)

        if (
            player
            and before.channel
            and after.channel is None
            and (
                (before.channel.members == [member.guild.me] and not player.queue)
                or member == member.guild.me
            )
        ):
            # disconnect player if bot is alone and queue is empty / bot is disconnected
            await _dc(player, member.guild)

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await ctx.send(
                err.CMD_USAGE((await GuildDB(ctx.guild).get()).prefix, ctx.command)
            )  # send command usage
        elif isinstance(
            error,
            (commands.CheckFailure, commands.DisabledCommand, commands.CommandNotFound),
        ):
            return  # ignore errors that aren't important

        raise error

    async def on_member_update(self, before: discord.Member, after: discord.Member): ...


class TrackEvents:
    """contains functions that are used when a track does something"""

    def __init__(self, client: CadeElegy):
        self.client = client

    @listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        """event handler for when a track starts"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        if player.loop:
            return

        # get the channel, requester, and track duration
        guild = self.client.get_guild(player.guild_id)
        channel = guild.get_channel(player.fetch("channel"))
        requester = guild.get_member(track.requester)

        duration = format_time(ms=track.duration)

        vc = player.channel_id

        playing = discord.Embed(
            description=f"-# {bot.CONNECTION} Now playing:\n**[{track.title}]({track.uri})**\nby **{track.author}** • `{duration}`\n-# <#{vc}> • {requester.mention}",
            color=colors.PLAYING_TRACK,
        )

        if (await _get_lyrics(event.track))[0] == 200:
            playing.description += " • (lyrics available)"

        playing.set_thumbnail(url=get_artwork_url(track))

        player.store("prev_pl_name", player.fetch("pl_name"))
        player.store("pl_name", player.current.extra["pl_name"])

        player.store("message", await channel.send(embed=playing))
        player.store("requester", track.requester)
        player.store("loopcount", 0)

    @listener(TrackEndEvent)
    async def on_track_end(self, event: TrackEndEvent):
        """event handler for when a track ends"""
        player: DefaultPlayer = event.player
        track: AudioTrack = event.track

        if player.loop:
            # increase loopcount by 1
            return player.store("loopcount", player.fetch("loopcount") + 1)

        guild = self.client.get_guild(player.guild_id)
        track_id = f"{guild.id}:{track.identifier}"

        # disable .nowplaying buttons for the track
        for view in self.client.persistent_views:
            if (
                isinstance(view, NowPlayingView)
                and view.id == track_id
                and not view.is_finished()
            ):
                await view.disable("ended")

        requester = player.fetch("requester")
        duration = format_time(ms=track.duration)

        # create "played track" embed
        track_info = f"[{track.title}]({track.uri}) `{duration}`"
        played = BaseEmbed(description=f"-# Played {track_info} • <@{requester}>")

        orig_message: discord.Message = player.fetch("message")

        # group track with others from the same playlist if they're from one
        if (pl := player.fetch("pl_name")) and pl == player.fetch("prev_pl_name"):
            channel = self.client.get_channel(
                player.fetch("channel")
            )  # find "played (track)" message
            message = [m async for m in channel.history(limit=2)][-1]

            if (
                message.author == self.client.user
                and (em := message.embeds)  # message is from the bot
                and "Played" in (desc := em[0].description)  # message has an embed
                and desc.count("\n")  # embed is of a played track(s)
                < 15  # embed has less than 15 lines
            ):
                # add the playlist name if it's not there
                if "Played tracks from" not in desc:
                    desc = strip_pl_name(pl, desc).strip(f" • <@{requester}>")
                    desc = desc.replace(
                        "Played", f"<@{requester}> • Played tracks from **{pl}**:\n- "
                    )

                # add the track's information
                desc += f"\n- {strip_pl_name(pl, track_info)}"
                new_embed = message.embeds[0].copy()
                new_embed.description = desc

                # edit the message and delete the "now playing" message
                await message.edit(embed=new_embed)
                await orig_message.delete()
                return

        # edit the original "now playing" message with the embed
        await orig_message.edit(embed=played)

    @listener(QueueEndEvent)
    async def on_queue_end(self, event: QueueEndEvent):
        """event handler for when a queue ends"""
        player: DefaultPlayer = event.player
        guild = self.client.get_guild(player.guild_id)
        channel = guild.get_channel(player.channel_id)

        if channel.members == [guild.me]:
            await _dc(player, guild)  # leave if the bot is alone in vc

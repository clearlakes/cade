import discord
from discord.ext import commands, menus

from utils.tracks import (
    create_music_embed,
    find_tracks,
    get_queue
)
from utils.views import (
    TrackSelectView,
    NowPlayingView,
    PlaylistView
)
from utils.clients import LavalinkVoiceClient, Keys, get_spotify_client
from utils.useful import format_time, get_yt_thumbnail
from utils.base import BaseEmbed, BaseCog
from utils.main import Cade, CadeLavalink
from utils.data import err, colors, bot
from utils.events import TrackEvents
from utils.db import GuildDB

class Music(BaseCog):
    def __init__(self, client: Cade):
        super().__init__(client)

        if Keys.lavalink:
            self.client.lavalink = CadeLavalink(client.user.id)
            self.client.lavalink.add_node(*Keys.lavalink.ordered_keys, name = "default-node")
            self.client.lavalink.add_event_hooks(TrackEvents(client))

        if Keys.spotify:
            self.client.spotify_api = get_spotify_client()

        if not self.client.lavalink:
            self.client.log.warning("can't load music commands, missing lavalink info")

            for cmd in self.get_commands():
                cmd.enabled = False

        if not self.client.spotify_api:
            self.client.log.warning("can't play spotify tracks, missing spotify api keys")

    def cog_unload(self):
        self.client.lavalink._event_hooks.clear()

    async def cog_check(self, ctx: commands.Context):
        if ctx.command.name == "playlist":
            return True

        player = self.client.lavalink.get_player(ctx)

        if ctx.command.name == "disconnect" and not player:
            await ctx.send(err.BOT_NOT_IN_VC)
            return False

        # check if the bot is in vc
        if ctx.command.name in ["play", "disconnect"]:
            if not player or not player.is_connected:
                if ctx.command.name == "play" and ctx.author.voice:
                    player = self.client.lavalink.create_player(ctx)
                    await ctx.author.voice.channel.connect(cls = LavalinkVoiceClient)
                    return True
                else:
                    await ctx.send(err.BOT_NOT_IN_VC)
                    return False

        # check if the user is in vc
        if ctx.command.name not in ["loopcount", "queue", "nowplaying"]:
            if not ctx.author.voice or (ctx.command.name != "join" and player and ctx.author.voice.channel.id != player.channel_id):
                await ctx.send(err.USER_NOT_IN_VC)
                return False

        # check if the bot is playing music
        if ctx.command.name not in ["play", "join", "disconnect"]:
            if not player or not player.is_playing:
                await ctx.send(err.NO_MUSIC_PLAYING)
                return False

        return True

    @commands.command(aliases = ["p"], usage = "[url/query]")
    async def play(self, ctx: commands.Context, *, query: str = ""):
        """plays a track/playlist from youtube or spotify"""
        query = query.strip("<>")

        # check if the user wants to select a track
        if query.endswith("*"):
            query = query[:-1]
            track_selection = True
        else:
            track_selection = False

        # check if the query was empty
        if not query:
            raise commands.MissingRequiredArgument(ctx.command.params["query"])

        # get the player for this guild from cache
        player = self.client.lavalink.get_player(ctx)

        # get a list of tracks from the search results
        tracks, info, failed = await find_tracks(
            client = self.client,
            query = query,
            requester_id = ctx.author.id,
            return_all = track_selection
        )

        if not tracks:
            error = err.CANT_LOAD_MUSIC if failed else err.NO_MUSIC_RESULTS
            return await ctx.send(error)

        if track_selection:
            # creates a selection view using the search results
            view = TrackSelectView(ctx, tracks)

            await ctx.send(embed = view.track_embed, view = view)
            await view.wait()

            track, info = view.track, view.info

            if not track:
                return  # nothing was selected

            tracks = [track]

        for track in tracks:
            player.add(track, requester = ctx.author.id)

        if player.is_playing or len(tracks) > 1:
            # create an extra embed for playlists or queued tracks
            embed = create_music_embed(tracks, info, player, ctx.author)
            await ctx.send(embed = embed)

        await player.play(no_replace = True)

    @commands.command(aliases = ["j"])
    async def join(self, ctx: commands.Context):
        """makes the bot join a voice channel"""
        # create a player for the guild
        player = self.client.lavalink.create_player(ctx)

        # move to the user's vc if it is already connected to another
        if player.is_connected:
            if ctx.author.voice.channel.id != int(player.channel_id):
                await ctx.guild.voice_client.move_to(ctx.author.voice.channel)
                return await ctx.message.add_reaction(bot.OK)
            return await ctx.send(err.BOT_IN_VC)

        await ctx.author.voice.channel.connect(cls = LavalinkVoiceClient)
        await ctx.message.add_reaction(bot.OK)

    @commands.command(aliases = ["dc", "leave"])
    async def disconnect(self, ctx: commands.Context):
        """makes the bot leave a voice channel"""
        player = self.client.lavalink.get_player(ctx)

        # clear the queue
        player.queue.clear()

        # stop playing the current track
        await player.stop()

        # leave the vc
        await ctx.voice_client.disconnect(force = True)
        await ctx.message.add_reaction(bot.OK)

    @commands.command(aliases = ["s"], usage = "*[index]/all")
    async def skip(self, ctx: commands.Context, index: str = None):
        """skips the current track (or queued tracks)"""
        player = self.client.lavalink.get_player(ctx)

        # if nothing is given, skip the current track
        if index is None:
            track_id = f"{ctx.guild.id}:{player.current.identifier}"

            for view in self.client.persistent_views:
                if isinstance(view, NowPlayingView) and view.id == track_id:
                    await view.message.edit(view = view.disable("skipped"))

            player.set_loop(0)
            await player.skip()
            await ctx.message.add_reaction(bot.OK)
            return

        # clear the queue if "all" is given
        if index == "all":
            player.queue.clear()
            return await ctx.send(f"{bot.OK} cleared the queue")

        # if the given index is not numeric or larger than the number of tracks in the queue, send an error
        if not index.isnumeric() or int(index) > len(player.queue):
            return await ctx.send(err.NOT_IN_QUEUE)

        index = int(index)

        # "skipped track"
        title = player.queue[index - 1]["title"]
        player.queue.pop(index - 1)
        await ctx.send(f"{bot.OK} skipped **{title}**")

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        """shuffles the order of the queue"""
        player = self.client.lavalink.get_player(ctx)

        # check if the queue is empty
        if not player.queue:
            return await ctx.send("the queue is empty!")

        # sets the player's shuffle to it's opposite (true -> false, false -> true)
        player.shuffle = not player.shuffle

        # success message according to what it was set to
        if player.shuffle:
            await ctx.send(f"{bot.OK} picking a random song from now on")
        else:
            await ctx.send(f"{bot.OK} playing the queue in order from now on")

    @commands.command(aliases = ["l"])
    async def loop(self, ctx: commands.Context):
        """begins/stops looping the current track"""
        player = self.client.lavalink.get_player(ctx)

        # set the loop status to it's opposite (true -> false, false -> true)
        player.set_loop(int(not player.loop))

        # success message according to what it was set to
        if player.loop:
            await ctx.send(f"{bot.OK} looping **{player.current.title}**")
        else:
            # get and reset loopcount
            loopcount = player.fetch("loopcount")
            player.store("loopcount", 0)

            await ctx.send(f"{bot.OK} stopped loop at **{loopcount}** loop(s)")

    @commands.command(aliases = ["lc"])
    async def loopcount(self, ctx: commands.Context):
        """shows how many times the current track has been looped"""
        player = self.client.lavalink.get_player(ctx)

        # check if the current track is being looped
        if not player.loop:
            return await ctx.send(err.MUSIC_NOT_LOOPED)

        loopcount = player.fetch("loopcount")
        await ctx.send(f"`{player.current.title}` has been looped **{loopcount}** time(s)")

    @commands.command(aliases = ["pl"], usage = "*[playlist]")
    async def playlist(self, ctx: commands.Context, playlist: str = None):
        """lists every playlist and the controls for each"""
        db = GuildDB(ctx.guild)
        guild = await db.get()

        if not playlist:
            # create list of playlists
            embed = BaseEmbed(
                title = "Playlists:",
                from_list = (guild.playlists.keys(), "(none yet)")
            )

            embed.set_footer(text = "create, play, and edit playlists using .pl [playlist name]")

            return await ctx.send(embed = embed)

        # show playlist info if one is specified
        view = PlaylistView(self.client, ctx, playlist)
        await ctx.send(embed = await view.get_track_embed(), view = view.updated_view)

    @commands.command(aliases = ["pp"])
    async def pause(self, ctx: commands.Context):
        """pauses/unpauses the current track"""
        player = self.client.lavalink.get_player(ctx)

        # set the pause status to it's opposite value (paused -> unpaused, etc.)
        await player.set_pause(not player.paused)

        # success message depending on if the track is now paused or unpaused
        if player.paused:
            await ctx.send(f"{bot.OK} paused")
        else:
            await ctx.send(f"{bot.OK} unpaused")

    @commands.command(usage = "[time]")
    async def seek(self, ctx: commands.Context, time_input: str):
        """skips to a specific point in the current track"""
        player = self.client.lavalink.get_player(ctx)
        new_time = time_input

        # if the first character of the given time is not numeric (probably a + or -),
        # set new_time to whatever is after that character
        if not time_input[0].isnumeric():
            new_time = time_input[1:]

        try:
            if ":" in time_input and len(values := time_input.split(":")) <= 3:
                # if the time given is formatted as H:M:S, get it as seconds
                new_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(values)))

            # multiply by 1000 to get milliseconds
            new_time = int(new_time) * 1000
        except ValueError:
            return await ctx.send(err.INVALID_TIMESTAMP)

        # if + or - was in front of the given time
        if not time_input[0].isnumeric():
            if time_input[0] == "+":
                # fast forward by the amount of time given
                new_time = player.position + new_time

                # if the given time is further than the track's end time
                if new_time >= player.current.duration:
                    return await ctx.send(err.INVALID_SEEK)

                action = "skipped"
            elif time_input[0] == "-":
                # rewind by the amount of time given
                new_time = player.position - new_time

                # set the player's position to 0 if the track can't rewind any further
                if new_time < 0:
                    new_time = 0

                action = "rewinded"
        else:
            action = "set position"

        # format the given time
        formatted_time = format_time(ms = new_time)

        await player.seek(new_time)
        return await ctx.send(f"{bot.OK} {action} to `{formatted_time}`")

    @commands.command(aliases = ["q"])
    async def queue(self, ctx: commands.Context):
        """lists all of the tracks in the queue"""
        player = self.client.lavalink.get_player(ctx)

        if not player.queue:
            return await ctx.send("the queue is empty!")

        # create the paginator using the embeds from get_queue
        queue_pages = await get_queue(player)
        paginator =  menus.MenuPages(source = queue_pages, clear_reactions_after = True)

        await paginator.start(ctx)

    @commands.command(aliases = ["np"])
    async def nowplaying(self, ctx: commands.Context):
        """shows information about the current track"""
        player = self.client.lavalink.get_player(ctx)
        requester = await self.client.fetch_user(player.current.requester)

        # get current track information
        current_song_pos = player.position
        song_duration = player.current.duration

        # generate video progress bar
        ratio_of_times = (current_song_pos / song_duration) * 50
        ratio_of_times_in_range = ratio_of_times // 2.5

        line = "".join("-" if i != ratio_of_times_in_range else "⦿" for i in range(20))

        # formatted durations
        duration = format_time(ms = song_duration)
        time_at = format_time(ms = current_song_pos)
        time_left = format_time(ms = song_duration - current_song_pos)

        # create embed
        embed = discord.Embed(
            title = player.current.title,
            url = f"https://youtube.com/watch?v={player.current.identifier}",
            description = f"Sent by {requester.mention} | Duration: `{duration}`",
            color = colors.CURRENT_TRACK
        )

        embed.set_footer(text = f"{time_at} elapsed {line} {time_left} left")
        embed.set_author(name = "Currently Playing", icon_url = requester.display_avatar)
        embed.set_thumbnail(url = get_yt_thumbnail(player.current.identifier))

        # edit the embed to show if the current track is paused
        if player.paused:
            embed.description += " | **Paused**"

        # edit the footer if the current track is being looped
        if player.loop:
            embed.set_footer(text = f"{embed.footer.text} • looped")

        track_id = f"{ctx.guild.id}:{player.current.identifier}"

        for view in self.client.persistent_views:
            if isinstance(view, NowPlayingView) and view.id == track_id:
                await view.message.edit(view = view.clear_items())

        msg = await ctx.send(embed = embed)

        # add NowPlayingView buttons to message
        await msg.edit(embed = embed, view = NowPlayingView(ctx, player))

async def setup(bot: Cade):
    await bot.add_cog(Music(bot))
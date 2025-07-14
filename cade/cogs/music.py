from discord.ext import commands, menus

from utils.base import CadeElegy, BaseCog
from utils.tracks import create_music_embed, get_youtube, get_queue, get_np_lyrics
from utils.useful import format_time
from utils.vars import v
from utils.views import NowPlayingView, TrackSelectView


class Music(BaseCog):
    def cog_unload(self):
        self.client.lavalink._event_hooks.clear()

    async def cog_check(self, ctx: commands.Context):
        player = self.client.lavalink.get_player(ctx)
        connected_to_vc = (ctx.author.voice and player and ctx.author.voice.channel.id == player.channel_id)
        currently_playing = False if not player else player.is_playing

        if not connected_to_vc and ctx.command.name not in ["play", "join"]:
            await ctx.send(v.ERR__BOT_NOT_IN_VC)
            return False

        match ctx.command.name, currently_playing:
            case "play" | "join", False:
                if ctx.author.voice and not connected_to_vc:
                    player = self.client.lavalink.create_player(ctx)
                    await ctx.author.voice.channel.connect(
                        cls=self.client.lavalink.voice_client
                    )
                    return True
                elif not ctx.author.voice:
                    await ctx.send(v.ERR__USER_NOT_IN_VC)
                    return False
                else:
                    return True
            case "loopcount" | "queue" | "nowplaying" | "lyrics", True:
                if not ctx.author.voice or (player and ctx.author.voice.channel.id != player.channel_id):
                    await ctx.send(v.ERR__USER_NOT_IN_VC)
                    return False
                else:
                    return True
            case "loopcount" | "queue" | "nowplaying" | "lyrics", False:
                await ctx.send(v.ERR__NO_MUSIC_PLAYING)
                return False
            case _:
                return True

    @commands.command(aliases=["p"], usage="[url/query]")
    async def play(self, ctx: commands.Context, *, query: str = ""):
        """plays a track/playlist from youtube or spotify"""
        query = query.strip("<>")
        track_selection = False

        match list(query):
            case [*_, "*"]:  # if "*" is the last character, start track selection
                query = query[:-1]
                track_selection = True
            case []:  # if the query is empty, raise an error
                raise commands.MissingRequiredArgument(ctx.command.params["query"])

        # get the player for this guild from cache
        player = self.client.lavalink.get_player(ctx)

        # get a list of tracks from the search results
        tracks, info, failed = await get_youtube(self.client, query, track_selection)

        if not tracks:
            error = v.ERR__CANT_LOAD_MUSIC if failed else v.ERR__NO_MUSIC_RESULTS
            return await ctx.send(error)

        if track_selection:
            # creates a selection view using the search results
            view = TrackSelectView(ctx, tracks)

            track_list = await ctx.send(embed=await view.get_track_embed(), view=view)
            await view.wait()

            track, info = view.track, view.info

            if not track:
                return await track_list.delete()  # nothing was selected

            tracks = [track]

        for track in tracks:
            player.add(track, requester=ctx.author.id)

        if player.is_playing or len(tracks) > 1:
            # create an extra embed for playlists or queued tracks
            embed = create_music_embed(tracks, info, player, ctx.author)
            await ctx.send(embed=embed)

        await player.play(no_replace=True)

    @commands.command(aliases=["j"])
    async def join(self, ctx: commands.Context):
        """makes the bot join a voice channel"""
        # create a player for the guild
        player = self.client.lavalink.create_player(ctx)

        # move to the user's vc if it is already connected to another
        if player.is_connected:
            if ctx.author.voice.channel.id != int(player.channel_id):
                await ctx.guild.voice_client.move_to(ctx.author.voice.channel)
                return await ctx.message.add_reaction(v.EMJ__OK)
            return await ctx.send(v.ERR__BOT_IN_VC)

        await ctx.author.voice.channel.connect(cls=self.client.lavalink.voice_client)
        await ctx.message.add_reaction(v.EMJ__OK)

    @commands.command(aliases=["dc", "leave"])
    async def disconnect(self, ctx: commands.Context):
        """makes the bot leave a voice channel"""
        player = self.client.lavalink.get_player(ctx)

        # clear the queue
        player.queue.clear()

        # stop playing the current track
        await player.stop()

        # leave the vc
        await ctx.voice_client.disconnect(force=True)
        await ctx.message.add_reaction(v.EMJ__OK)

    @commands.command(aliases=["s"], usage="*[index]/all")
    async def skip(self, ctx: commands.Context, *, index: int | str | None):
        """skips the current track (or queued tracks)"""
        player = self.client.lavalink.get_player(ctx)
        skip_to = False
        removed = None

        async def _skip():
            track_id = f"{ctx.guild.id}:{player.current.identifier}"

            for view in self.client.persistent_views:
                if isinstance(view, NowPlayingView) and view.id == track_id:
                    await view.disable("skipped")

            player.set_loop(0)
            await player.skip()
            await ctx.message.add_reaction(v.EMJ__OK)

        if index is None:
            return await _skip()

        if index == "undo":
            if cache := player.fetch("queue_cache"):
                player.queue = cache  # revert back to saved version of queue
                player.store("queue_cache", None)
                return await ctx.message.add_reaction(v.EMJ__OK)
            else:
                return await ctx.message.add_reaction("❓")

        # save queue state in case they want to undo
        player.store("queue_cache", [*player.queue])

        while True:
            match index:
                case int():
                    if 0 < index <= len(player.queue):
                        if skip_to:  # skip to track and play it
                            player.queue = player.queue[index - 1 :]
                            return await _skip()

                        # remove track by index
                        removed = player.queue.pop(index - 1).title
                        break
                    else:
                        return await ctx.send(v.ERR__NOT_IN_QUEUE)
                case str():
                    match list(index):
                        case [*_, "^"]:
                            index = (
                                int(i) if (i := index[:-1]).isnumeric() else i
                            )  # remove "^"
                            skip_to = True  # restart match statement but skip to track instead
                        case _:
                            index = index.lower()

                            if index == "all":
                                player.queue.clear()
                                return await ctx.send(f"{v.EMJ__OK} cleared the queue")

                            # remove by playlist name
                            if pl_tracks := [
                                t
                                for t in player.queue
                                if (pl := t.extra["pl_name"]) and pl.lower() == index
                            ]:
                                if skip_to:  # skip to first track in playlist
                                    player.queue = player.queue[
                                        player.queue.index(pl_tracks[0]) :
                                    ]
                                    return await _skip()

                                player.queue = [
                                    track
                                    for track in player.queue
                                    if track not in pl_tracks
                                ]
                                removed = pl_tracks[0].extra["pl_name"]
                                break

                            # remove by track name
                            if any(
                                index in (track := t).title.lower()
                                for t in player.queue
                            ):
                                if (
                                    skip_to
                                ):  # skip to track and play it (but also find index)
                                    player.queue = player.queue[
                                        player.queue.index(track) :
                                    ]
                                    return await _skip()

                                player.queue.remove(track)
                                removed = track.title
                                break

                            return await ctx.send(v.ERR__NOT_IN_QUEUE)

        await ctx.send(f"{v.EMJ__OK} skipped **{removed}**")

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
            await ctx.send(f"{v.EMJ__OK} picking a random song from now on")
        else:
            await ctx.send(f"{v.EMJ__OK} playing the queue in order from now on")

    @commands.command(aliases=["l"])
    async def loop(self, ctx: commands.Context):
        """begins/stops looping the current track"""
        player = self.client.lavalink.get_player(ctx)

        # set the loop status to it's opposite (true -> false, false -> true)
        player.set_loop(int(not player.loop))

        # success message according to what it was set to
        if player.loop:
            await ctx.send(f"{v.EMJ__OK} looping **{player.current.title}**")
        else:
            # get and reset loopcount
            loopcount = player.fetch("loopcount")
            player.store("loopcount", 0)

            await ctx.send(f"{v.EMJ__OK} stopped loop at **{loopcount}** loop(s)")

    @commands.command(aliases=["lc"])
    async def loopcount(self, ctx: commands.Context):
        """shows how many times the current track has been looped"""
        player = self.client.lavalink.get_player(ctx)

        # check if the current track is being looped
        if not player.loop:
            return await ctx.send(v.ERR__MUSIC_NOT_LOOPED)

        loopcount = player.fetch("loopcount")
        await ctx.send(
            f"`{player.current.title}` has been looped **{loopcount}** time(s)"
        )

    @commands.command(aliases=["pp"])
    async def pause(self, ctx: commands.Context):
        """pauses/unpauses the current track"""
        player = self.client.lavalink.get_player(ctx)

        # set the pause status to it's opposite value (paused -> unpaused, etc.)
        await player.set_pause(not player.paused)

        # success message depending on if the track is now paused or unpaused
        if player.paused:
            await ctx.send(f"{v.EMJ__OK} paused")
        else:
            await ctx.send(f"{v.EMJ__OK} unpaused")

    @commands.command(usage="[time]")
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
                new_time = sum(int(x) * 60**i for i, x in enumerate(reversed(values)))

            # multiply by 1000 to get milliseconds
            new_time = int(new_time) * v.MATH__MS_MULTIPLIER
        except ValueError:
            return await ctx.send(v.ERR__INVALID_TIMESTAMP)

        # if + or - was in front of the given time
        if not time_input[0].isnumeric():
            if time_input[0] == "+":
                # fast forward by the amount of time given
                new_time = player.position + new_time

                # if the given time is further than the track's end time
                if new_time >= player.current.duration:
                    return await ctx.send(v.ERR__INVALID_SEEK)

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
        formatted_time = format_time(ms=new_time)

        await player.seek(new_time)
        return await ctx.send(f"{v.EMJ__OK} {action} to `{formatted_time}`")

    @commands.command(aliases=["q"])
    async def queue(self, ctx: commands.Context):
        """lists all of the tracks in the queue"""
        player = self.client.lavalink.get_player(ctx)

        if not player.queue:
            return await ctx.send("the queue is empty!")

        # create the paginator using the embeds from get_queue
        queue_pages = await get_queue(player)
        paginator = menus.MenuPages(source=queue_pages, clear_reactions_after=True)

        await paginator.start(ctx)

    @commands.command(aliases=["np"])
    async def nowplaying(self, ctx: commands.Context):
        """shows information about the current track"""
        player = self.client.lavalink.get_player(ctx)
        view = NowPlayingView(ctx, player)

        # clear existing "now playing" views
        for v in self.client.persistent_views:
            if isinstance(v, NowPlayingView) and v.id == view.id:
                await v.message.edit(view=v.clear_items())

        # create embed and add buttons to message
        view.message = await ctx.send(embed=await view.get_track_embed(), view=view)

    @commands.command()
    async def lyrics(self, ctx: commands.Context):
        """gets the lyrics for the current track"""
        player = self.client.lavalink.get_player(ctx)

        lyric_pages = await get_np_lyrics(player)

        if lyric_pages is None:
            return await ctx.send(v.ERR__NO_LYRICS)

        paginator = menus.MenuPages(source=lyric_pages, clear_reactions_after=True)

        await paginator.start(ctx)


async def setup(bot: CadeElegy):
    await bot.add_cog(Music(bot))

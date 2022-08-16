import discord
from discord.ext import commands, pages

from utils.music.tracks import (
    create_music_embed,
    select_tracks,
    find_tracks,
    get_queue
)
from utils.dataclasses import reg, err, colors, emoji
from utils.views import PlaylistView, NowPlayingView
from utils.music.voice import LavalinkVoiceClient
from utils.music.events import TrackEvents
from utils.functions import format_time
from utils.clients import Keys
from utils import database

from lavalink import Client as LavalinkClient, DefaultPlayer
from youtube_dl import YoutubeDL

class Music(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client

        # if not already connected, connect to the lavalink server using the credentials from lavalink_opts
        if not hasattr(client, 'lavalink'):
            self.client.lavalink = LavalinkClient(self.client.user.id)
            self.client.lavalink.add_node(*Keys.lavalink, name = "default-node")

        # get events to use for on_track_start/end, etc.
        self.client.lavalink.add_event_hooks(TrackEvents(self.client))

    @property
    def lavalink(self) -> LavalinkClient:
        return self.client.lavalink

    def cog_unload(self):
        self.lavalink._event_hooks.clear()

    def create_player(self, ctx: commands.Context):
        player: DefaultPlayer = self.lavalink.player_manager.create(ctx.guild.id, endpoint = str(ctx.author.voice.channel.rtc_region))
        player.store('channel', ctx.channel.id)
        return player

    def get_player(self, guild_id) -> DefaultPlayer:
        return self.lavalink.player_manager.get(guild_id)

    async def cog_check(self, ctx: commands.Context):
        if ctx.command.name == 'playlist':
            return True

        player = self.get_player(ctx.guild.id)

        if ctx.command.name == 'disconnect' and not player:
            await ctx.send(err.BOT_NOT_IN_VC)
            return False

        # check if the bot is in vc
        if ctx.command.name in ['play', 'disconnect']:
            if not player or not player.is_connected:
                if ctx.command.name == 'play' and ctx.author.voice:
                    player = self.create_player(ctx)
                    await ctx.author.voice.channel.connect(cls = LavalinkVoiceClient)
                    return True
                else:
                    await ctx.send(err.BOT_NOT_IN_VC)
                    return False

        # check if the user is in vc
        if ctx.command.name not in ['loopcount', 'queue', 'nowplaying']:
            if not ctx.author.voice or (ctx.command.name != 'join' and player and ctx.author.voice.channel.id != player.channel_id):
                await ctx.send(err.USER_NOT_IN_VC)
                return False

        # check if the bot is playing music
        if ctx.command.name not in ['play', 'join', 'disconnect']:
            if not player or not player.is_playing:
                await ctx.send(err.NO_MUSIC_PLAYING)
                return False

        return True

    @commands.command(aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str = ''):
        """Plays a track from a given url/query"""
        query = query.strip('<>')

        # check if the user wants to select a track
        if query.endswith("*"):
            query = query[:-1]
            track_selection = True
        else:
            track_selection = False
        
        # check if the query was empty
        if not query:
            raise commands.BadArgument()

        # get the player for this guild from cache
        player = self.get_player(ctx.guild.id)

        # get a list of tracks from the search results
        tracks, extra = await find_tracks(
            node = player.node, 
            query = query, 
            requester_id = ctx.author.id, 
            return_all = track_selection
        )
        
        if not tracks:
            return await ctx.send(err.NO_MUSIC_RESULTS)

        if track_selection:
            # creates a selection view using the search results
            track, extra = await select_tracks(ctx, tracks)

            if not track:
                return  # nothing was selected

            tracks = [track]

        for track in tracks:
            player.add(track, requester = ctx.author.id)

        if player.is_playing or len(tracks) > 1:
            # create an extra embed for playlists or queued tracks
            embed = create_music_embed(query, tracks, extra, player, ctx.author)
            await ctx.send(embed = embed)
        
        await player.play(no_replace = True)

    @commands.command(aliases=['j'])
    async def join(self, ctx: commands.Context):
        """Makes the bot join a VC"""
        # create a player for the guild
        player = self.create_player(ctx)

        # move to the user's vc if it is already connected to another
        if player.is_connected:
            if ctx.author.voice.channel.id != int(player.channel_id):
                await ctx.guild.voice_client.move_to(ctx.author.voice.channel)
                return await ctx.message.add_reaction(emoji.OK)
            return await ctx.send(err.BOT_IN_VC)

        await ctx.author.voice.channel.connect(cls = LavalinkVoiceClient)
        await ctx.message.add_reaction(emoji.OK)

    @commands.command(aliases=['dc', 'leave'])
    async def disconnect(self, ctx: commands.Context):
        """Disconnects the bot from the VC and clears the queue"""
        player = self.get_player(ctx.guild.id)

        # clear the queue
        player.queue.clear()

        # stop playing the current track
        await player.stop()

        # leave the vc
        await ctx.voice_client.disconnect(force = True)
        await ctx.message.add_reaction(emoji.OK)
    
    @commands.command(aliases=['s'])
    async def skip(self, ctx: commands.Context, index = None):
        """Skips either the current track, a track in the queue, or the entire queue"""
        player = self.get_player(ctx.guild.id)

        # if nothing is given, skip the current track
        if index is None:
            track_id = f"{ctx.guild.id}:{player.current.identifier}"
            
            for view in self.client.persistent_views:
                if isinstance(view, NowPlayingView) and view.id == track_id:
                    view = view.disable("skipped")
                    await view.msg.edit(view = view)

            player.set_loop(0)
            await player.skip()
            await ctx.message.add_reaction(emoji.OK)
            return
        
        # clear the queue if "all" is given
        if index == "all":
            player.queue.clear()
            return await ctx.send(f"{emoji.OK} Cleared the queue")
        
        # if the given index is not numeric or larger than the number of tracks in the queue, send an error
        if not index.isnumeric() or int(index) > len(player.queue):
            return await ctx.send(err.VALUE_NOT_IN_QUEUE)
        
        index = int(index)
        
        # "skipped track"
        title = player.queue[index - 1]['title']
        player.queue.pop(index - 1)
        await ctx.send(f"{emoji.OK} Skipped **{title}**")

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        """Shuffles the playing order of the queue"""
        player = self.get_player(ctx.guild.id)
        
        # check if the queue is empty
        if not player.queue:
            return await ctx.send("the queue is empty!")
        
        # sets the player's shuffle to it's opposite (true -> false, false -> true)
        player.shuffle = not player.shuffle

        # success message according to what it was set to
        if player.shuffle is False:
            await ctx.send(f"{emoji.OK} Playing the queue in order from now on")
        else:
            await ctx.send(f"{emoji.OK} Picking a random song from now on")
    
    @commands.command(aliases=['l'])
    async def loop(self, ctx: commands.Context):
        """Loops the current track"""
        player = self.get_player(ctx.guild.id)
        
        # set the loop status to it's opposite (true -> false, false -> true)
        player.set_loop(int(not player.loop))

        # success message according to what it was set to
        if player.loop:
            await ctx.send(f"{emoji.OK} Looping **{player.current.title}**")
        else:
            # get and reset loopcount
            loopcount = player.fetch("loopcount")
            player.store("loopcount", 0)

            await ctx.send(f"{emoji.OK} Stopped loop (ended at **{loopcount}** loop(s)) ")
    
    @commands.command(aliases=['lc'])
    async def loopcount(self, ctx: commands.Context):
        """Shows how many times the current track has been looped"""
        player = self.get_player(ctx.guild.id)
        
        # check if the current track is being looped
        if not player.loop:
            return await ctx.send(err.MUSIC_NOT_LOOPED)
        
        loopcount = player.fetch("loopcount")
        await ctx.send(f"`{player.current.title}` has been looped **{loopcount}** time(s)")

    @commands.command(aliases=['pl'])
    async def playlist(self, ctx: commands.Context, pl_name: str = None, opt: str = None, res: str = None):
        """Creates playlists and lets you add/remove tracks from them"""
        # options that the user can use
        add_opt = ["a", "add"]
        remove_opt = ["r", "remove", "delete", "d"]
        list_opt = ["l", "list"]

        # function for creating a list of tracks from a playlists
        async def get_track_embed():
            # check if there are tracks in the playlist
            if playlist_is_not_there or playlist_is_there_but_empty:
                embed = discord.Embed(
                    title = pl_name,
                    description = "(this playlist is empty)",
                    color = discord.Color.embed_background()
                )
            else:
                track_list = ''

                # get details about each track in the playlist, as well as who added them
                for i, track in enumerate(playlists[pl_name]):
                    title = track['title']
                    url = track['url']
                    user = f"<@{track['user']}>"
                    track_list += f"**{i + 1}.** [{title}]({url}) - {user}\n"
                    
                embed = discord.Embed(
                    title = f"{pl_name} - {len(playlists[pl_name])} track(s)",
                    description = track_list,
                    color = discord.Color.embed_background()
                )

            return embed
        
        db = database.Guild(ctx.guild)
        doc = db.get()

        # use an empty dict if the 'playlists' field is not listed in the guild database
        playlists = doc.playlists if doc.playlists else {}

        # variables that hold True or False according to:
        playlist_is_not_there = pl_name not in playlists.keys() # if the playlist is not listed in the database
        playlist_is_there_but_empty = not playlist_is_not_there and playlists != {} and len(playlists[pl_name]) == 0  # if the playlist is listed in the database, but is empty

        # if nothing is given
        if pl_name is None:
            list_of_playlists = "\n\ncommands:\n`.pl (name) [a]dd (url)` - add a track\n`.pl (name) [r]emove (index)|all` - remove a track / the entire playlist\n`.pl (name) [l]ist` - list tracks in a playlist"

            # if the 'playlists' field is not empty, add a list of the playlists
            if playlists != {}:
                list_of_playlists = '**' + '**, **'.join(playlists) + '**' + list_of_playlists

            embed = discord.Embed(
                title = "Playlists",
                description = list_of_playlists,
                color = discord.Color.embed_background()
            )

            return await ctx.send(embed = embed)

        pl_name = pl_name.lower()

        # if only a playlist name is given
        if opt is None:
            embed = await get_track_embed()

            # set message to have buttons from the PlaylistView class (add, play, remove)
            msg = await ctx.send(embed = embed)
            view = PlaylistView(self.lavalink, ctx, msg, pl_name)

            # disable the play/remove track buttons if the playlist is empty
            if playlist_is_not_there or playlist_is_there_but_empty:
                view.disable_all_items(exclusions = [view.children[0]])
            
            await msg.edit(embed = embed, view = view)
            return await view.wait()
        
        opt = opt.lower()
        
        # if the user is trying to add a track
        if opt in add_opt:
            # if nothing is given as a url 
            if res is None:
                return await ctx.send(err.MUSIC_URL_NOT_FOUND)

            # if the user input is not a youtube url
            if not reg.youtube.match(res):
                return await ctx.send(err.INVALID_MUSIC_URL)

            # get track information from the url
            with YoutubeDL() as ydl:
                video = ydl.extract_info(res, download = False)
                title = video['title']
            
            new_track = {"title": title, "url": res, "user": ctx.author.id}
            
            # update the playlist with the new track
            db.push(f'playlists.{pl_name}', new_track)
            
            if pl_name in playlists.keys():
                position = len(doc.playlists[pl_name])
                return await ctx.send(f"{emoji.OK} Added track **{title}** (`#{position}`)")
            else:        
                return await ctx.send(f"{emoji.OK} Created playlist **{pl_name}** and added track **{title}**")

        # if the user is trying to remove a track
        if opt in remove_opt:
            # if the playlist is empty
            if playlist_is_not_there:
                return await ctx.send(err.PLAYLIST_DOESNT_EXIST)

            # if the user does not give an index, or if the index is "all", remove the playlist entirely
            if res is None or res.lower() == "all":
                db.del_obj('playlists', pl_name)
                return await ctx.send(f"{emoji.OK} Removed **{pl_name}**")
            
            # check if the given index is numeric
            if res.isnumeric():
                if playlist_is_there_but_empty:
                    return await ctx.send(err.PLAYLIST_IS_EMPTY)

                if int(res) > len(playlists[pl_name]):
                    return await ctx.send(err.INVALID_INDEX)
                
                track_id = int(res) - 1
                title = playlists[pl_name][track_id]["title"]

                # remove the track from the playlist
                if len(playlists[pl_name]) > 1:
                    db.del_obj(f'playlists.{pl_name}', track_id)
                else:
                    # remove the playlist completely if the final track was deleted
                    db.del_obj('playlists', pl_name)

                return await ctx.send(f"{emoji.OK} Removed track **{title}**")
            else:
                return await ctx.send(err.INVALID_INDEX)

        # if the user only wants a list of tracks in the playlist
        if opt in list_opt:
            embed = await get_track_embed()
            return await ctx.send(embed = embed)

        raise commands.BadArgument()
    
    @commands.command(aliases=['pp', 'pause'])
    async def togglepause(self, ctx: commands.Context):
        """Pauses/unpauses the current track"""
        player = self.get_player(ctx.guild.id)

        # set the pause status to it's opposite value (paused -> unpaused, etc.)
        await player.set_pause(not player.paused)
        
        # success message depending on if the track is now paused or unpaused
        if player.paused is True:
            await ctx.send(f"{emoji.OK} paused")
        else:
            await ctx.send(f"{emoji.OK} unpaused")
    
    @commands.command()
    async def seek(self, ctx: commands.Context, time_input: str = None):
        """Seek to a given timestamp, or rewind/fast-forward the track"""
        player = self.get_player(ctx.guild.id)
        new_time = time_input

        # if nothing is given
        if time_input is None:
            raise commands.BadArgument()
        
        # if the first character of the given time is not numeric (probably a + or -),
        # set new_time to whatever is after that character
        if not time_input[0].isnumeric():
            new_time = time_input[1:]

        try:
            if ":" in time_input and len(values := time_input.split(':')) <= 3:
                # if the time given is formatted as H:M:S, get it as seconds
                new_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(values)))
            
            # multiply by 1000 to get milliseconds
            new_time = int(new_time) * 1000
        except ValueError:
            return await ctx.send(err.INVALID_TIMESTAMP)

        res = ''
        
        # if + or - was in front of the given time
        if not time_input[0].isnumeric():
            if time_input[0] == "+":
                # fast forward by the amount of time given
                new_time = player.position + new_time

                # if the given time is further than the track's end time
                if new_time >= player.current.duration:
                    return await ctx.send(err.INVALID_SEEK)

                res = 'skipped to `{}`'
            elif time_input[0] == "-":
                # rewind by the amount of time given
                new_time = player.position - new_time

                # set the player's position to 0 if the track can't rewind any further
                if new_time < 0:
                    new_time = 0

                res = 'rewinded to `{}`'
        else:
            res = 'set position to `{}`'

        # format the given time
        before_format = new_time // 1000
        formatted_time = format_time(before_format)
        res = res.format(formatted_time)
        
        await player.seek(new_time)
        return await ctx.send(f"{emoji.OK} {res}")

    @commands.command(aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """Displays the queue of the server"""
        player = self.get_player(ctx.guild.id)

        if not player.queue:
            return await ctx.send("the queue is empty!")

        # create the paginator using the embeds from get_queue
        queue_pages = await get_queue(player)
        paginator = pages.Paginator(pages = queue_pages, loop_pages = True)

        # if the queue is 1 page (10 items or less), send the embed without buttons
        if len(player.queue) <= 10:
            return await ctx.send(embed = queue_pages[0])

        await paginator.send(ctx)
    
    @commands.command(aliases=['np'])
    async def nowplaying(self, ctx: commands.Context):
        """Displays information about the current track"""
        player = self.get_player(ctx.guild.id)

        requester = await self.client.fetch_user(player.current.requester)
        
        # get current track information
        current_song_pos = player.position
        song_duration = player.current.duration
        
        # generate video progress bar
        ratio_of_times = (current_song_pos / song_duration) * 50
        ratio_of_times_in_range = ratio_of_times // 2.5

        line = ''.join("-" if i != ratio_of_times_in_range else "⦿" for i in range(20))

        current_song_pos = current_song_pos // 1000
        song_duration = song_duration // 1000

        # formatted durations
        duration = format_time(song_duration)
        time_at = format_time(current_song_pos)
        time_left = format_time(song_duration - current_song_pos)

        # create embed
        embed = discord.Embed(
            title = player.current.title,
            url = f"https://youtube.com/watch?v={player.current.identifier}",
            description = f"Sent by {requester.mention} | Duration: `{duration}`",
            color = colors.CURRENT_TRACK
        )

        embed.set_footer(text = f"{time_at} elapsed {line} {time_left} left")
        embed.set_author(name = f"Currently Playing", icon_url = requester.display_avatar)
        embed.set_thumbnail(url = f"https://img.youtube.com/vi/{player.current.identifier}/0.jpg")

        # edit the embed to show if the current track is paused
        if player.paused:
            embed.description += " | **Paused**"
        
        # edit the footer if the current track is being looped
        if player.loop:
            embed.set_footer(text = f"{embed.footer.text} • looped")

        track_id = f"{ctx.guild.id}:{player.current.identifier}"

        for view in self.client.persistent_views:
            if isinstance(view, NowPlayingView) and view.id == track_id:
                view.disable_all_items()
                await view.msg.edit(view = view)

        msg = await ctx.send(embed = embed)

        # add NowPlayingView buttons to message
        view = NowPlayingView(ctx, player, msg)
        await msg.edit(embed = embed, view = view)
        await view.wait()

def setup(bot):
    bot.add_cog(Music(bot))
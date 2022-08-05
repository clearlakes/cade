import discord
from discord.ext import commands, pages

from utils.views import QueueView, PlaylistView, TrackSelectView
from utils.dataclasses import reg, err, colors, emoji
from utils.voice import LavalinkVoiceClient
from utils.functions import format_time
from utils.clients import Clients, Keys
from utils import database

from lavalink import Client as LavalinkClient, DefaultPlayer, listener
from lavalink.events import TrackStartEvent, TrackEndEvent
from lavalink.models import AudioTrack

from dataclasses import dataclass
from youtube_dl import YoutubeDL
from functools import reduce
from textwrap import shorten

@dataclass
class CurrentTrack:
    requester_id = 0
    track: AudioTrack = None
    msg: discord.Message = None
    looped = False
    loop_count = 0

class Music(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client
        self.current_track = CurrentTrack()

        # if not already connected, connect to the lavalink server using the credentials from lavalink_opts
        if not hasattr(client, 'lavalink'):
            self.client.lavalink = LavalinkClient(self.client.user.id)
            self.client.lavalink.add_node(*Keys.lavalink, name = "default-node")

        # get events to use for on_track_start/end, etc.
        self.client.lavalink.add_event_hooks(self)

        # get spotify api client
        self.spotify_api = Clients().spotify()
        self.client.loop.create_task(self.spotify_api.get_auth_token_with_client_credentials())
        self.client.loop.create_task(self.spotify_api.create_new_client())

    def create_player(self, ctx: commands.Context) -> DefaultPlayer:
        player = self.lavalink.player_manager.create(ctx.guild.id, endpoint = str(ctx.author.voice.channel.rtc_region))
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

    @property
    def lavalink(self) -> LavalinkClient:
        return self.client.lavalink

    def cog_unload(self):
        self.lavalink._event_hooks.clear()

    @listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        """Event handler for when a track starts"""
        if self.current_track.looped:
            return

        # get the channel, requester, and track duration
        channel = await self.client.fetch_channel(event.player.fetch('channel'))
        requester = await self.client.fetch_user(event.track.requester)
        duration = format_time(event.track.duration // 1000)

        # create the embed
        playing = discord.Embed(
            title = event.track.title,
            url = event.track.uri,
            description = f"Duration: `{duration}` | Sent by {requester.mention}",
            color = colors.PLAYING_TRACK
        )

        # add footer and thumbnail
        playing.set_author(name="Now Playing", icon_url = requester.display_avatar)
        playing.set_thumbnail(url = f"https://img.youtube.com/vi/{event.track.identifier}/0.jpg")

        self.current_track.track = event.track
        self.current_track.requester_id = requester.id
        self.current_track.msg = await channel.send(embed = playing)
    
    @listener(TrackEndEvent)
    async def on_track_end(self, event: TrackEndEvent):
        """Event handler for when a track ends"""
        # check if the track is being looped
        if self.current_track.looped:
            player = self.get_player(event.player.guild_id)
            self.current_track.loop_count += 1

            # replay the track 
            player.add(track = self.current_track.track, requester = self.current_track.requester_id, index = 0)
        else:
            duration = format_time(event.track.duration // 1000)

            # create "played track" embed
            played = discord.Embed(
                title = event.track.title,
                url = event.track.uri,
                description = f"was played by <@{self.current_track.requester_id}> | Duration: `{duration}`",
                color = discord.Color.embed_background()
            )

            # edit the original "now playing" message with the embed
            await self.current_track.msg.edit(embed = played)

    @commands.command(aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str = ''):
        """Plays a track from a given url/query"""
        # this was also semi-taken from https://github.com/Devoxin/Lavalink.py/blob/master/examples/music.py
        track_selection = False

        # remove leading and trailing <> (<> may be used to suppress embedding links in Discord)
        query = query.strip('<>')

        # check if the user wants to select a track
        if query.endswith("*"):
            query = query[:-1]
            track_selection = True
        
        # check if the query was empty
        if not query:
            raise commands.BadArgument()

        def get_id(track_type: str):
            """Gets the track/playlist ID from a spotify url"""
            start = query.find(f'{track_type}/') + len(f'{track_type}/')
            url_id = query[start:query.find("?")]
            return url_id

        # get the player for this guild from cache
        player = self.get_player(ctx.guild.id)

        # find either the youtube url or query to use
        if not reg.url.match(query):
            query = f'ytsearch:{query}'
        else:
            query = reg.url.match(query).group(0)

            if "spotify" in query:
                if "track" in query:
                    # url is a track
                    track_id = get_id("track")
                    track = await self.spotify_api.track.get_one(track_id)
                    
                    # search youtube for a track with the same name
                    track_name = track["name"]
                    track_artist = track["artists"][0]["name"]
                    query = f'ytsearch:{track_artist} - {track_name}'

                elif "playlist" in query:
                    # url is a playlist
                    playlist_id = get_id("playlist")
                    playlist_info = await self.spotify_api.playlists.get_one(playlist_id)
                    tracks = playlist_info["tracks"]

                    # get playlist details
                    num_of_tracks = tracks["total"]
                    playlist_name = playlist_info["name"]
                    playlist_owner = playlist_info["owner"]["display_name"]
                    playlist_image = playlist_info["images"][0]["url"]

                    count = 0
                    total_duration = 0
                    tracks = tracks["items"]

                    msg = await ctx.send(f"{emoji.PROCESSING()} Adding spotify playlist (this may take a WHILE)")

                    # for each track in the playlist, get details about it
                    for item in tracks:
                        track = item['track'] if 'track' in item else item

                        # build search query
                        track_name = track["name"]
                        track_artist = track["artists"][0]["name"]
                        sp_query = f'ytsearch:{track_artist} - {track_name}'

                        # search for matching track
                        results = await player.node.get_tracks(sp_query)

                        # continue loop if no results were found that matched the track query
                        if not results or not results['tracks']:
                            continue
                        
                        # add track to queue
                        sp_track = results['tracks'][0]
                        sp_track = AudioTrack(sp_track, ctx.author.id)
                        player.add(requester = ctx.author.id, track = sp_track)
                        total_duration += track["duration_ms"]
                    
                    await msg.delete()

                    total_duration = total_duration // 1000
                    duration = format_time(total_duration)

                    # "the playlist was added"
                    embed = discord.Embed(
                        title = playlist_name,
                        description = f'**{playlist_owner}** - **{num_of_tracks}** tracks\nSent by {ctx.author.mention} | Duration: `{duration}`',
                        color = colors.ADDED_TRACK
                    )
                    embed.set_thumbnail(url = playlist_image)
                    embed.set_author(name = f"Added Spotify Playlist to Queue", icon_url = ctx.author.display_avatar)
                    embed.set_footer(text = f"Got results for {count} songs")

                    await ctx.send(embed = embed)
                    
                    await player.play(no_replace = True)
            else:
                # if it's not a youtube url, send an error
                if not reg.youtube.match(query):
                    return await ctx.send(err.INVALID_MUSIC_URL)
                
                # since youtube shorts urls are not recognized by lavalink yet, convert it into a regular url
                if 'shorts' in query:
                    query = f'https://youtube.com/watch?v={reg.youtube.match(query).group(1)}'

        # get the results from lavalink
        results = await player.node.get_tracks(query)

        # if nothing was found when searching for tracks
        if not results or not results['tracks']:
            return await ctx.send(err.NO_MUSIC_RESULTS)

        # check if the bot found either a playlist or a track
        if results['loadType'] == 'PLAYLIST_LOADED':
            # a playlist was found
            tracks = results['tracks']

            playlist_name = results["playlistInfo"]["name"]
            track_list = ''
            
            # for each track in the playlist, add it to the queue
            for i, track in enumerate(tracks):
                player.add(requester = ctx.author.id, track = track)

                # add track to list of added tracks
                if i <= 9:
                    shortened = shorten(track.title, 70, placeholder="...")
                    track_list += f'`{i + 1}.` [{shortened}]({track.uri})\n'
            
            # show how many tracks there are after the first 10
            if len(tracks) > 10:
                track_list += f'+`{len(tracks) - 10}` more'
            
            embed = discord.Embed(
                title = playlist_name,
                description = track_list,
                color = colors.ADDED_TRACK
            )
            embed.set_author(name=f"Queued Playlist ({len(tracks)} tracks)", icon_url = ctx.author.display_avatar)
            await ctx.send(embed = embed)
        else:
            # get a list of results if track selection is enabled
            if track_selection:
                tracks: list = results['tracks']
                track = tracks[0]

                msg = await ctx.send("Loading results...")
                view = TrackSelectView(ctx, msg, tracks)

                # disable 'next' button if there is only one result
                if len(results['tracks']) == 1:
                    view.children[2].disabled = True
                
                # disable 'back' button since it's starting at the first result
                view.children[1].disabled = True

                embed = discord.Embed(
                    title = track.title,
                    url = track.uri,
                    color = discord.Color.embed_background()
                )

                embed.set_author(name = f"Result {tracks.index(track) + 1} out of {len(tracks)}")
                embed.set_thumbnail(url = f"https://img.youtube.com/vi/{track.identifier}/0.jpg")

                embed.description = f"Author: **{track.author}** | Duration: `{format_time(track.duration // 1000)}`"

                await msg.edit(content = None, embed = embed, view = view)
                await view.wait()

                await msg.delete()

                if view.selection is None:
                    return await ctx.message.delete()
                
                track = view.selection
            else:
                track = results['tracks'][0]

            # if the player is currently playing a track, add to the queue
            if player.is_playing:
                duration = format_time(track.duration // 1000)

                # "added to queue"
                embed = discord.Embed(
                    title = track.title,
                    url = track.uri,
                    description = f"Added by {ctx.author.mention} | Duration: `{duration}`",
                    color = colors.ADDED_TRACK
                )
                
                # get time left before song is played
                time_left = player.current.duration - player.position
 
                for song in player.queue:
                    time_left += song.duration

                total_duration = format_time(time_left // 1000)
                queue_length = len(player.queue) + 1

                # set the footer, author, and thumbnail
                embed.set_footer(text = f"Playing in {total_duration}")
                embed.set_author(name = f"Queued Track - #{queue_length}", icon_url = ctx.author.display_avatar)
                embed.set_thumbnail(url = f"https://img.youtube.com/vi/{track.identifier}/0.jpg")

                await ctx.send(embed = embed)

            # add the track to the queue. if the player is not playing anything, this will make it play the requested track
            track = AudioTrack(track, ctx.author.id)
            player.add(requester = ctx.author.id, track = track)

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
        # disable loop
        self.current_track.looped = False

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
            self.current_track.looped = False
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
        self.current_track.looped = not self.current_track.looped

        # success message according to what it was set to
        if self.current_track.looped:
            await ctx.send(f"{emoji.OK} Looping **{player.current.title}**")
        else:
            await ctx.send(f"{emoji.OK} Stopped loop (ended at **{self.current_track.loop_count}** loop(s)) ")
            self.current_track.loop_count = 0
    
    @commands.command(aliases=['lc'])
    async def loopcount(self, ctx: commands.Context):
        """Shows how many times the current track has been looped"""
        player = self.get_player(ctx.guild.id)
        
        # check if the current track is being looped
        if not self.current_track.looped:
            return await ctx.send(err.MUSIC_NOT_LOOPED)
        
        await ctx.send(f"`{player.current.title}` has been looped **{self.current_track.loop_count}** time(s)")

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
            view = PlaylistView(self.client, ctx, msg, pl_name)

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
    async def seek(self, ctx: commands.Context, time_input = None):
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

        # if the time given is formatted as M:S 
        if ":" in time_input:
            # multiply by 60 for each value that is enclosed by colons (in order to get seconds), and then multiply by 1000 (for ms)
            new_time = reduce(lambda prev, next: prev * 60 + next, [float(x) for x in new_time.split(":")], 0) * 1000
            new_time = int(round(new_time))
        else:
            # most likely given seconds, so multiply by 1000
            try:
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
        queue_pages = await QueueView().get_queue(self.client, ctx)
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
        if self.current_track.looped:
            embed.set_footer(text = f"{embed.footer.text} • looped")

        msg = await ctx.send(embed = embed)

        # add NowPlayingView buttons to message
        view = NowPlayingView(self.current_track, ctx, player, msg)
        await msg.edit(embed = embed, view = view)
        await view.wait()

# this class should be in views.py but it uses self.current_track.looped so i can't
class NowPlayingView(discord.ui.View):
    def __init__(self, current_track, ctx, player, msg):
        super().__init__()
        self.current_track = current_track
        self.player = player
        self.ctx = ctx
        self.msg = msg

        # change pause emoji to play emoji, if paused
        if player.paused:
            self.children[1].emoji = "▶️"
        
        # change loop emoji to whatever 🔂 is, if looped
        if self.current_track.looped:
            self.children[2].emoji = "🔂"
    
    # link every button to the same callback

    @discord.ui.button(emoji = "⏩", custom_id = "skip")
    async def _skip(self, b, i): await self.callback(b, i)

    @discord.ui.button(emoji = "⏸️", custom_id = "pause")
    async def _pause(self, b, i): await self.callback(b, i)

    @discord.ui.button(emoji = "🔁", custom_id = "loop")
    async def _loop(self, b, i): await self.callback(b, i)

    async def callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        if not self.ctx.author.voice or (self.ctx.author.voice.channel.id != int(self.player.channel_id)):
            return await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral = True)

        await interaction.response.defer()

        embed = self.msg.embeds[0]

        if button.custom_id == "skip":
            # update original message view
            button.disabled = True
            button.label = "skipped"
            self.children = [button]
            self.current_track.looped = False
            
            await self.msg.edit(embed = embed, view = self)

            return await self.player.skip()

        # change pause button and embed description according to pause status
        elif button.custom_id == "pause":
            if not self.player.paused:
                await self.player.set_pause(True)
                self.children[1].emoji = "▶️"
                embed.description += " | **Paused**"
            else:
                await self.player.set_pause(False)
                self.children[1].emoji = "⏸️"
                embed.description = embed.description.replace(" | **Paused**", "")

        # do the same thing but for loop status
        elif button.custom_id == "loop":
            if not self.current_track.looped:
                self.current_track.looped = True
                embed.set_footer(text = f"{embed.footer.text} • looped")
                self.children[2].emoji = "🔂"
            else:
                self.current_track.looped = False
                embed.set_footer(text = embed.footer.text.replace(" • looped", ""))
                self.children[2].emoji = "🔁"

        return await self.msg.edit(embed = embed, view = self)

    # disable buttons on timeout
    async def on_timeout(self):
        self.disable_all_items()
        await self.msg.edit(embed = self.msg.embeds[0], view = self)

def setup(bot):
    bot.add_cog(Music(bot))
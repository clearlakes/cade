import discord
from discord.ext import commands, pages

from utils.views import QueueView, PlaylistView, TrackSelectView
from utils.lavalink_server import LavalinkVoiceClient
from utils.variables import Clients, Regex, Keys
from utils.functions import format_time
from utils import database

from lavalink.events import TrackStartEvent, TrackEndEvent
from lavalink.models import AudioTrack
from lavalink import Client, listener

from youtube_dl import YoutubeDL
from functools import reduce
from textwrap import shorten

re = Regex()

lavalink_opts = Keys().lavalink

playing_color = 0x4e42f5
added_color = 0x42f55a

repeat_single = False
current_track = None
loop_count = 0
np_msg = None

class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        global played_song
        played_song = False

        # if not already connected, connect to the lavalink server using the credentials from lavalink_opts
        if not hasattr(client, 'lavalink'):
            client.lavalink = Client(client.user.id)
            client.lavalink.add_node(*lavalink_opts, name = "default-node")

        # get events to use for on_track_start/end, etc.
        client.lavalink.add_event_hooks(self)

        # connect to spotify for use in the play command
        self.connect_spotify()

    def connect_spotify(self):
        """Connects to Spotify's API"""
        global api_client
        global sp_credentials

        api_client = Clients().spotify()
        sp_credentials = False

    def cog_unload(self):
        self.client.lavalink._event_hooks.clear()

    # create a player before every command invoke
    async def cog_before_invoke(self, ctx: commands.Context):
        guild_check = ctx.guild is not None

        if guild_check:
            self.client.lavalink.player_manager.create(ctx.guild.id, endpoint=str(ctx.guild.region))

        return guild_check

    @listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        """Event handler for when a track starts"""
        global current_track
        global repeat_single
        global np_msg
        
        if repeat_single is True:
            return
        
        current_track = [event.track, event.track.requester]

        # get the channel, requester, and duration
        channel = event.player.fetch('channel')
        channel = await self.client.fetch_channel(channel)
        requester = await self.client.fetch_user(event.track.requester)
        duration = event.track.duration // 1000
        duration = format_time(duration)

        # create the embed
        playing = discord.Embed(
            title = event.track.title,
            url = event.track.uri,
            description = f"Duration: `{duration}` | Sent by {requester.mention}",
            color = playing_color
        )

        # add footer and thumbnail
        playing.set_author(name="Now Playing", icon_url = requester.display_avatar)
        playing.set_thumbnail(url=f"https://img.youtube.com/vi/{event.track.identifier}/0.jpg")

        np_msg = await channel.send(embed = playing)
    
    @listener(TrackEndEvent)
    async def on_track_end(self, event: TrackEndEvent):
        """Event handler for when a track ends"""
        global np_msg
        global loop_count
        global repeat_single

        # check if the track is being looped
        if repeat_single:
            # replay the track
            guild_id = int(event.player.guild_id)
            player = self.client.lavalink.player_manager.get(guild_id)
            loop_count += 1
            player.add(track=current_track[0], requester=current_track[1], index=0)
        else:
            # get information about the track that ended
            title = event.track.title
            url = event.track.uri
            user = await self.client.fetch_user(current_track[1])
            duration = event.track.duration // 1000
            duration = format_time(duration)

            # create "played track" embed
            played = discord.Embed(
                title = title,
                url = url,
                description = f"was played by {user.mention} | Duration: `{duration}`",
                color = self.client.gray
            )

            # edit the original "now playing" message with the embed
            await np_msg.edit(embed = played)

    @commands.command(aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str = None):
        """Plays a track from a given url/query"""
        # this was also semi-taken from https://github.com/Devoxin/Lavalink.py/blob/master/examples/music.py
        global api_client
        global sp_credentials
        is_spotify = False
        track_selection = False

        if query is None:
            raise commands.BadArgument()

        def get_id(which: str, url):
            start = url.find(f'{which}/') + len(f'{which}/')
            end = url.find("?")
            url_id = url[start:end]
            return url_id

        # get the player for this guild from cache
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        # remove leading and trailing <> (<> may be used to suppress embedding links in Discord)
        query = query.strip('<>')

        # if the user wants to select a track
        if query.endswith("*"):
            # remove the asterisk from the query
            query = query[:-1]
            track_selection = True

            # just in case, check if the query is now nothing
            if query == '': raise commands.BadArgument()

        # if the user is not in a vc
        if not ctx.author.voice:
            return await ctx.send("**Error:** you're not in the same vc")

        # if the bot is not in a vc, connect to the user's vc
        # if the bot is in a vc (but not the user's vc), send an error
        if not player.is_connected:
            player.store('channel', ctx.channel.id)
            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        elif ctx.author.voice.channel.id != int(player.channel_id):
            return await ctx.send("**Error:** you're not in the same vc")

        # find either the youtube url or query to use
        if not re.url.match(query):
            query = f'ytsearch:{query}'
        else:
            # if the message contains a url, check if it's spotify
            query = re.url.match(query).group(0)

            if (query.find("spotify") != -1):
                if sp_credentials is False:
                    await api_client.get_auth_token_with_client_credentials()
                    await api_client.create_new_client()
                    sp_credentials = True
                is_spotify = True
            else:
                # if it's not spotify (but is a url), check if it's youtube
                # if it's not youtube, send an error
                if not re.youtube.match(query):
                    return await ctx.send("**Error:** only youtube/spotify links can be used")
                
                # since youtube shorts urls are not recognized by lavalink yet, convert it into a regular url
                if 'shorts' in query:
                    query = f'https://youtube.com/watch?v={re.youtube.match(query).group(1)}'

        # get the results from the lavalink server if it's not spotify
        if not is_spotify:
            results = await player.node.get_tracks(query)
        else:
            # check if the spotify link is for a track or a playlist
            if (query.find("track") != -1):
                # url is a track
                track_id = get_id("track", query)
                track = await api_client.track.get_one(track_id)
                
                # search youtube for a track with the same name
                track_name = track["name"]
                track_artist = track["artists"][0]["name"]
                sp_query = f'ytsearch:{track_artist} - {track_name}'

                results = await player.node.get_tracks(sp_query)
            elif (query.find("playlist") != -1):
                # url is a playlist
                playlist_id = get_id("playlist", query)
                playlist_info = await api_client.playlists.get_one(playlist_id)
                tracks = playlist_info["tracks"]

                # get playlist details
                num_of_tracks = tracks["total"]
                playlist_name = playlist_info["name"]
                playlist_owner = playlist_info["owner"]["display_name"]
                playlist_image = playlist_info["images"][0]["url"]

                count = 0
                total_duration = 0
                tracks = tracks["items"]

                msg = await ctx.send(f"{self.client.loading} Adding spotify playlist (this may take a WHILE)")

                # for each track in the playlist, get details about it
                for item in tracks:
                    if count == 50:
                        break

                    if 'track' in item:
                        track = item['track']
                    else:
                        track = item

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
                    player.add(requester=ctx.author.id, track=sp_track)
                    total_duration += track["duration_ms"]
                    count += 1
                
                await msg.delete()

                total_duration = total_duration // 1000
                duration = format_time(total_duration)

                # "the playlist was added"
                embed = discord.Embed(
                    title = playlist_name,
                    description = f'**{playlist_owner}** - **{num_of_tracks}** tracks\nSent by {ctx.author.mention} | Duration: `{duration}`',
                    color = added_color
                )
                embed.set_thumbnail(url=playlist_image)
                embed.set_author(name=f"Added Spotify Playlist to Queue", icon_url=ctx.author.display_avatar)
                embed.set_footer(text=f"Got results for {count} songs")

                await ctx.send(embed = embed)
                
                # start playing if it isn't
                if not player.is_playing:
                    await player.play()
                return
            else:
                return await ctx.send("**Error:** could not determine if url is a playlist or a track")

        # if nothing was found when searching for tracks
        if not results or not results['tracks']:
            return await ctx.send("**Error:** no results were found with that query")

        # check if the bot found either a playlist or a track
        if results['loadType'] == 'PLAYLIST_LOADED':
            # a playlist was found
            tracks = results['tracks']
            
            count = 0
            extended = False
            playlist_name = results["playlistInfo"]["name"]
            playlist_track_preview = ''
            
            # for each track in the playlist, add it to the queue
            for track in tracks:
                count += 1
                player.add(requester=ctx.author.id, track=track)

                if extended is True:
                    continue

                # add track to list of added tracks
                # if the amount of tracks is more than 10, keep counting from 1 without adding them to the list
                if count <= 10:
                    shortened = shorten(track.title, 70, placeholder="...")
                    url = track.uri
                    playlist_track_preview += f'`{count}.` [{shortened}]({url})\n'
                else:
                    count = 1
                    extended = True
            
            # show how many tracks there are after the first 10
            if extended is True:
                playlist_track_preview += f'(`+{count} more`)'
            
            embed = discord.Embed(
                title = playlist_name,
                description = playlist_track_preview,
                color = added_color
            )
            embed.set_author(name=f"Added Playlist to Queue ({len(tracks)} tracks)", icon_url=ctx.author.display_avatar)
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
                    url = track.uri
                )

                embed.set_author(name = f"Result {tracks.index(track) + 1} out of {len(tracks)}")
                embed.set_thumbnail(url = f"https://img.youtube.com/vi/{track.identifier}/0.jpg")

                embed.description = f"Author: **{track.author}** | Duration: `{format_time(track.duration // 1000)}`"

                await msg.edit(content = None, embed = embed, view = view)
                await view.wait()

                await msg.delete()

                if view.selection is None:
                    return await ctx.message.delete()
                else:
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
                    color = added_color
                )
                
                # get time left before song is played
                time_left = player.current.duration - player.position
 
                for song in player.queue:
                    time_left += song.duration

                total_duration = format_time(total_duration // 1000)
                queue_length = len(player.queue) + 1

                # set the footer, author, and thumbnail
                embed.set_footer(text = f"Playing in {total_duration}")
                embed.set_author(name = f"Queued - #{queue_length}", icon_url=ctx.author.display_avatar)
                embed.set_thumbnail(url = f"https://img.youtube.com/vi/{track.identifier}/0.jpg")

                await ctx.send(embed=embed)

            # add the track to the queue. if the player is not playing anything, this will make it play the requested track
            track = AudioTrack(track, ctx.author.id)
            player.add(requester=ctx.author.id, track=track)

        # play the track if it isn't doing anything
        if not player.is_playing:
            await player.play()

    @commands.command(aliases=['j'])
    async def join(self, ctx: commands.Context):
        """Makes the bot join a VC"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        # check if the user is in a vc
        if not ctx.author.voice:
            return await ctx.send("**Error:** you're not in a vc")

        # move to the user's vc if it is already connected to another
        if player.is_connected:
            if ctx.author.voice.channel.id != int(player.channel_id):
                await ctx.guild.voice_client.move_to(ctx.author.voice.channel)
                return await ctx.message.add_reaction(self.client.ok)
            return await ctx.send("**Error:** i'm already in the vc")

        # store the channel in the lavalink player
        player.store('channel', ctx.channel.id)

        await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        await ctx.message.add_reaction(self.client.ok)

    @commands.command(aliases=['dc', 'leave'])
    async def disconnect(self, ctx: commands.Context):
        """Disconnects the bot from the VC and clears the queue"""
        # disable loop
        global repeat_single
        repeat_single = False

        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")

        # clear the queue
        player.queue.clear()

        # stop playing the current track
        await player.stop()

        # leave the vc
        await ctx.voice_client.disconnect(force=True)
        await ctx.message.add_reaction(self.client.ok)
    
    @commands.command(aliases=['s'])
    async def skip(self, ctx: commands.Context, index = None):
        """Skips either the current track, a track in the queue, or the entire queue"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")

        # if the bot isn't playing anything, send an error
        if not player.is_playing:
            return await ctx.send("**Error:** not playing anything")

        # if nothing is given, skip the current track
        if index is None:
            await player.skip()
            await ctx.message.add_reaction(self.client.ok)
            return
        
        # clear the queue if "all" is given
        if index == "all":
            player.queue.clear()
            return await ctx.send(f"{self.client.ok} Cleared the queue")
        
        # if the given index is not numeric or larger than the number of tracks in the queue, send an error
        if not index.isnumeric() or int(index) > len(player.queue):
            return await ctx.send("**Error:** that is probably not in the queue")
        
        index = int(index)
        
        # "skipped track"
        title = player.queue[index-1]['title']
        player.queue.pop(index - 1)
        await ctx.send(f"{self.client.ok} Skipped **{title}**")

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        """Shuffles the playing order of the queue"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")
        
        # check if the queue is empty
        if not player.queue:
            return await ctx.send("the queue is empty!")
        
        # sets the player's shuffle to it's opposite (true -> false, false -> true)
        player.shuffle = not player.shuffle

        # success message according to what it was set to
        if player.shuffle is False:
            await ctx.send(f"{self.client.ok} Playing the queue in order from now on")
        else:
            await ctx.send(f"{self.client.ok} Picking a random song from now on")
    
    @commands.command(aliases=['l'])
    async def loop(self, ctx: commands.Context):
        """Loops the current track"""
        global repeat_single
        global loop_count

        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")
        
        if not player.is_playing:
            return await ctx.send("**Error:** nothing is playing right now")
        
        # set the loop status to it's opposite (true -> false, false -> true)
        repeat_single = not repeat_single

        # success message according to what it was set to
        if repeat_single is True:
            await ctx.send(f"{self.client.ok} Looping **{player.current.title}**")
        else:
            await ctx.send(f"{self.client.ok} Stopped loop (ended at **{loop_count}** loop(s)) ")
            loop_count = 0
    
    @commands.command(aliases=['lc'])
    async def loopcount(self, ctx: commands.Context):
        """Shows how many times the current track has been looped"""
        global repeat_single
        global loop_count

        player = self.client.lavalink.player_manager.get(ctx.guild.id)
        
        if not player.is_playing:
            return await ctx.send("**Error:** nothing is playing right now")
        
        # check if the current track is being looped
        if not repeat_single:
            return await ctx.send("**Error:** the current song is not being looped (use `.l` to do so)")
        
        await ctx.send(f"`{player.current.title}` has been looped **{loop_count}** time(s)")

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
                    color = self.client.gray
                )
            else:
                count = 0
                track_list = ''

                # get details about each track in the playlist, as well as who added them
                for track in playlists[pl_name]:
                    count += 1
                    title = track['title']
                    url = track['url']
                    user = f"<@{track['user']}>"
                    track_list += f"**{count}.** [{title}]({url}) - {user}\n"
                    
                embed = discord.Embed(
                    title = f"{pl_name} - {count} track(s)",
                    description = track_list,
                    color = self.client.gray
                )

            return embed
        
        db = database.Guild(ctx.guild)
        doc = db.get()

        # use an empty dict if the 'playlists' field is not listed in the guild database
        playlists = doc.playlists if doc.playlists else {}

        # variables that hold True or False according to:
        playlist_is_not_there = pl_name not in playlists.keys() # if the playlist is not listed in the database
        playlist_is_there_but_empty = not playlist_is_not_there and playlists != {} and len(playlists[pl_name]) == 0 # if the playlist is listed in the database, but is empty

        # if nothing is given
        if pl_name is None:
            list_of_playlists = "\n\ncommands:\n`.pl (name) [a]dd (url)` - add a track\n`.pl (name) [r]emove (index)|all` - remove a track / the entire playlist\n`.pl (name) [l]ist` - list tracks in a playlist"

            # if the 'playlists' field is not empty, add a list of the playlists
            if playlists != {}:
                list_of_playlists = '**' + '**, **'.join(playlists) + '**' + list_of_playlists

            embed = discord.Embed(
                title = "Playlists",
                description = list_of_playlists,
                color = self.client.gray
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
                view.children[1].disabled = True
                view.children[2].disabled = True
            
            await msg.edit(embed = embed, view = view)
            return await view.wait()
        
        opt = opt.lower()
        
        # if the user is trying to add a track
        if opt in add_opt:
            # if nothing is given as a url 
            if res is None:
                return await ctx.send("**Error:** missing track url")

            # if the user input is not a youtube url
            if not re.youtube.match(res):
                return await ctx.send("**Error:** not a valid url")

            # get track information from the url
            with YoutubeDL() as ydl:
                video = ydl.extract_info(res, download = False)
                title = video['title']
            
            new_track = {"title": title, "url": res, "user": ctx.author.id}
            
            # update the playlist with the new track
            db.push(f'playlists.{pl_name}', new_track)
            
            if pl_name in playlists.keys():
                position = len(doc.playlists[pl_name])
                return await ctx.send(f"{self.client.ok} Added track **{title}** (`#{position}`)")
            else:        
                return await ctx.send(f"{self.client.ok} Created playlist **{pl_name}** and added track **{title}**")

        # if the user is trying to remove a track
        if opt in remove_opt:
            # if the playlist is empty
            if playlist_is_not_there:
                return await ctx.send("**Error:** that playlist doesn't exist")

            # if the user does not give an index, or if the index is "all", remove the playlist entirely
            if res is None or res.lower() == "all":
                db.del_obj('playlists', pl_name)
                return await ctx.send(f"{self.client.ok} Removed **{pl_name}**")
            
            # check if the given index is numeric
            if res.isnumeric():
                if playlist_is_there_but_empty:
                    return await ctx.send("**Error:** that playlist is empty")

                if int(res) > len(playlists[pl_name]):
                    return await ctx.send("**Error:** invalid index (too high)")
                
                track_id = int(res) - 1
                title = playlists[pl_name][track_id]["title"]

                # remove the track from the playlist
                if len(playlists[pl_name]) > 1:
                    db.del_obj(f'playlists.{pl_name}', track_id)
                else:
                    # remove the playlist completely if the final track was deleted
                    db.del_obj('playlists', pl_name)

                return await ctx.send(f"{self.client.ok} Removed track **{title}**")
            else:
                return await ctx.send("**Error:** invalid index (must be a number)")

        # if the user only wants a list of tracks in the playlist
        if opt in list_opt:
            embed = await get_track_embed()
            return await ctx.send(embed = embed)

        await ctx.send("**Error:** usage is:\n`.pl (name) (a)dd (url)`\n`.pl (name) (r)emove (index)|all`\n`.pl (name) (l)ist`")
    
    @commands.command(aliases=['pp', 'pause'])
    async def togglepause(self, ctx: commands.Context):
        """Pauses/unpauses the current track"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")

        # set the pause status to it's opposite value (paused -> unpaused, etc.)
        await player.set_pause(not player.paused)
        
        # success message depending on if the track is now paused or unpaused
        if player.paused is True:
            await ctx.send(f"{self.client.ok} paused")
        else:
            await ctx.send(f"{self.client.ok} unpaused")
    
    @commands.command()
    async def seek(self, ctx: commands.Context, time_input = None):
        """Seek to a given timestamp, or rewind/fast-forward the track"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)
        new_time = time_input

        if not player.is_connected:
            return await ctx.send("**Error:** not connected to a vc")

        if not ctx.author.voice or (ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send("**Error:** you're not in the same vc")

        # if nothing is given
        if time_input is None:
            return await ctx.send("**Error:** specify the time you want to go to (ex. `1:00`, `10.5`), or use either `+` or `-` to skip/rewind")
        
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
            new_time = int(new_time) * 1000

        res = ''
        
        # if + or - was in front of the given time
        if not time_input[0].isnumeric():
            if time_input[0] == "+":
                # fast forward by the amount of time given
                new_time = player.position + new_time

                # if the given time is further than the track's end time
                if new_time >= player.current.duration:
                    return await ctx.send("**Error:** cannot skip that far into the track")

                res = '**Skipped** to `{}`'
            elif time_input[0] == "-":
                # rewind by the amount of time given
                new_time = player.position - new_time

                # set the player's position to 0 if the track can't rewind any further
                if new_time < 0:
                    new_time = 0

                res = '**Rewinded** to `{}`'
        else:
            res = '**Set position** to `{}`'

        # format the given time
        before_format = new_time // 1000
        formatted_time = format_time(before_format)
        res = res.format(formatted_time)
        
        await player.seek(new_time)
        return await ctx.send(f"{self.client.ok} {res}")

    @commands.command(aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """Displays the queue of the server"""
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.queue:
            return await ctx.send("the queue is empty!")

        # create the paginator using the embeds from get_queue
        queue_pages = await QueueView.get_queue(self.client, ctx)
        paginator = pages.Paginator(pages=queue_pages, loop_pages=True)

        # if the queue is 1 page (10 items or less), send the embed without buttons
        if len(player.queue) <= 10:
            return await ctx.send(embed = queue_pages[0])

        await paginator.send(ctx)
    
    @commands.command(aliases=['np'])
    async def nowplaying(self, ctx: commands.Context):
        """Displays information about the current track"""
        global loop_count
        global repeat_single
        player = self.client.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send("**Error:** not playing anything")

        requester = await self.client.fetch_user(player.current.requester)
        
        # get current track information
        current_song_pos = player.position
        song_duration = player.current.duration
        
        # generate video progress bar
        line = ""
        ratio_of_times = (current_song_pos / song_duration) * 50
        ratio_of_times_in_range = ratio_of_times // 2.5

        for i in range(20):
            if i == ratio_of_times_in_range:
                line += "⦿"
            else:
                line += "-"

        current_song_pos = current_song_pos // 1000
        song_duration = song_duration // 1000

        # formatted durations
        time_at = format_time(current_song_pos)
        time_left = format_time(song_duration - current_song_pos)
        duration = format_time(song_duration)

        # create embed
        embed = discord.Embed(
            title = player.current.title,
            url = f"https://youtube.com/watch?v={player.current.identifier}",
            description = f"Sent by {requester.mention} | Duration: `{duration}`",
            color = 0x4287f5
        )

        embed.set_footer(text=f"{time_at} elapsed {line} {time_left} left")
        embed.set_author(name=f"Currently Playing", icon_url=requester.display_avatar)
        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{player.current.identifier}/0.jpg")

        # edit the embed to show if the current track is paused
        if player.paused:
            embed.description += " | **Paused**"
        
        # edit the footer if the current track is being looped
        if repeat_single:
            embed.set_footer(text = f"{embed.footer.text} • looped")

        msg = await ctx.send(embed = embed)

        # add NowPlayingView buttons to message
        view = NowPlayingView(self.client, ctx, player, msg)
        await msg.edit(embed = embed, view = view)
        await view.wait()

# this class should be in views.py but it uses repeat_single so i can't
class NowPlayingView(discord.ui.View):
    def __init__(self, client, ctx, player, msg):
        super().__init__()
        
        global repeat_single
        self.player = player
        self.client = client
        self.ctx = ctx
        self.msg = msg

        # set the pause button to say play if the current track is paused
        if player.paused:
            self.children[2].label = "play"
            self.children[2].emoji = "▶️"
        
        # same thing for the loop button: 
        # if the current track is being looped, set it to say "stop loop"
        if repeat_single:
            self.children[3].label = "stop loop"
            self.children[3].emoji = "🔂"
    
    # link every button to the same callback.
    # i don't know if there is a better way to do this
    
    @discord.ui.button(label="10s", emoji="⏪", style=discord.ButtonStyle.secondary, custom_id="-10")
    async def first(self, b, i): await self.callback(b, i)

    @discord.ui.button(label="skip", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="skip")
    async def second(self, b, i): await self.callback(b, i)

    @discord.ui.button(label="pause", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="pause")
    async def third(self, b, i): await self.callback(b, i)

    @discord.ui.button(label="loop", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop")
    async def fourth(self, b, i): await self.callback(b, i)

    @discord.ui.button(label="10s", emoji="⏩", style=discord.ButtonStyle.secondary, custom_id="+10")
    async def fifth(self, b, i): await self.callback(b, i)
    
    async def callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        global repeat_single

        if interaction.user != self.ctx.author:
            return

        if not self.ctx.author.voice or (self.ctx.author.voice.channel.id != int(self.player.channel_id)):
            return await interaction.response.send_message("**Error:** you're not in the same vc", ephemeral=True)

        embed = self.msg.embeds[0]

        # seek forwards or backwards 10 seconds
        if button.custom_id == "-10": await self.player.seek(self.player.position - 10000)
        if button.custom_id == "+10": await self.player.seek(self.player.position + 10000)

        if button.custom_id == "skip":
            await interaction.response.defer()

            # update original message view
            button.disabled = True
            button.label = "skipped"
            self.children = [button]
            
            await self.msg.edit(embed = embed, view = self)

            return await self.player.skip()

        # change pause button and embed description according to pause status
        if button.custom_id == "pause":
            if not self.player.paused:
                await self.player.set_pause(True)
                self.children[2].label = "play"
                self.children[2].emoji = "▶️"
                embed.description += " | **Paused**"
            else:
                await self.player.set_pause(False)
                self.children[2].label = "pause"
                self.children[2].emoji = "⏸️"
                embed.description = embed.description.replace(" | **Paused**", "")
        
        # do the same thing but for loop status
        if button.custom_id == "loop":
            if not repeat_single:
                repeat_single = True
                embed.set_footer(text = f"{embed.footer.text} • looped")
                self.children[3].label = "stop loop"
                self.children[3].emoji = "🔂"
            else:
                repeat_single = False
                embed.set_footer(text = embed.footer.text.replace(" • looped", ""))
                self.children[3].label = "loop"
                self.children[3].emoji = "🔁"
        
        await self.msg.edit(embed = embed, view = self)

    # disable buttons on timeout
    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        
        await self.msg.edit(embed = self.msg.embeds[0], view = self)

def setup(bot):
    bot.add_cog(Music(bot))
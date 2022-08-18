import discord
from discord.ext import commands, menus

from utils.music.tracks import (
    create_music_embed,
    find_tracks,
    get_queue
)
from utils.views import PlaylistView, NowPlayingView, TrackSelectView
from utils.music.voice import LavalinkVoiceClient
from utils.dataclasses import err, colors, emoji
from utils.music.events import TrackEvents
from utils.functions import format_time
from utils.clients import Keys
from utils import database

from lavalink import Client as LavalinkClient, DefaultPlayer

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
            view = TrackSelectView(ctx, tracks)

            await ctx.send(embed = view.track_embed, view = view)
            await view.wait()

            track, extra = view.track, view.extra

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
    async def playlist(self, ctx: commands.Context, playlist: str = None):
        """Creates playlists and lets you add/remove tracks from them"""
        db = database.Guild(ctx.guild)
        guild = db.get()

        if not playlist:
            embed = discord.Embed(
                title = "Playlists",
                color = colors.EMBED_BG
            )

            # create list of playlists
            embed.description = "**" + "**, **".join(guild.playlists.keys()) + "**" if guild.playlists else "(none yet)"
            embed.set_footer(text = "create, play, and edit playlists using .pl [playlist name]")

            return await ctx.send(embed = embed)

        # show playlist info if one is specified
        view = PlaylistView(self.lavalink, ctx, playlist)
        await ctx.send(embed = view.track_embed, view = view.updated_view)
    
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
        paginator =  menus.MenuPages(source = queue_pages, clear_reactions_after = True)

        await paginator.start(ctx)
    
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
                for btn in view.children:
                    btn.disabled = True
                
                await view.msg.edit(view = view)

        msg = await ctx.send(embed = embed)

        # add NowPlayingView buttons to message
        view = NowPlayingView(ctx, player, msg)
        await msg.edit(embed = embed, view = view)
        await view.wait()

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
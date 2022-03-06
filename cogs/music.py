import math
import time
import pafy
import asyncio
import textwrap
import functools
import discord
from discord.ext import commands, pages
from async_spotify.authentification.authorization_flows import ClientCredentialsFlow
from async_spotify import SpotifyApiClient
from utils.bot_vars import db, g_id, url_rx, youtube_rx, spotify_keys, lavalink_opts, check, btn_check, CancelView
import lavalink

playing_color = 0x4e42f5
added_color = 0x42f55a

repeat_single = False
current_track = None
np_msg = None
loop_count = 0

class NowPlayingView(discord.ui.View):
    def __init__(self, client, ctx, player, msg):
        global repeat_single
        super().__init__()
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
        global np_msg

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
            
            # disable loop
            if repeat_single: 
                repeat_single = False

            # get current track information
            title = self.player.current.title
            url = f"https://youtube.com/watch?v={self.player.current.identifier}"
            user = await self.client.fetch_user(current_track[1])
            duration = self.player.current.duration // 1000
            duration = Music.format_time(duration)

            # update "now playing" message with new "track ended" embed
            played = discord.Embed(
                title = title,
                url = url,
                description = f"Sent by {user.mention} | Duration: `{duration}`",
                color = self.client.gray
            )
            played.set_author(name="Played Audio", icon_url=user.display_avatar)
            await np_msg.edit(embed = played)

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

class QueueView(commands.Cog):
    @classmethod
    async def get_queue(cls, client: discord.Client, ctx: commands.Context):
        player = client.lavalink.player_manager.get(ctx.guild.id)
        total_pages = math.ceil(len(player.queue) / 10)
        current_page = 1
        pages = []

        # generate queue pages
        while current_page <= total_pages:
            start = (current_page - 1) * 10
            end = start + 10

            queue_list = ''

            # get the information of each track in the queue starting from the current page
            for index, track in enumerate(player.queue[start:end], start=start):
                duration = Music.format_time(track.duration // 1000)
                requester = f"<@{track.requester}>"
                queue_list += f'**{index + 1}.** [**{track.title}**]({track.uri}) `{duration}` - {requester}\n'

            embed = discord.Embed(
                title = f"Queue ({len(player.queue)} total)",
                description = queue_list,
                color = client.gray
            )
            
            # add page counter to footer if there's more than one page
            if total_pages != 1:
                embed.set_footer(text=f'{ctx.guild.name} • page {current_page} out of {total_pages}', icon_url=ctx.guild.icon.url)
            else:
                embed.set_footer(text=f'{ctx.guild.name}', icon_url=ctx.guild.icon.url)

            pages.append(embed)
            current_page += 1
        
        return pages

class PlaylistView(discord.ui.View):
    def __init__(self, client, ctx, msg, playlist):
        super().__init__()
        pl_doc = db.find_one({"guild_id": ctx.guild.id, "playlists": {"$ne": None}})

        # use an empty dict if 'playlists' is not in the guild db
        if pl_doc is None:
            self.playlists = {}
        else:
            self.playlists = pl_doc['playlists']

        self.client = client
        self.pl = playlist
        self.msg = msg
        self.ctx = ctx

    @discord.ui.button(label="+", style=discord.ButtonStyle.success, custom_id="add")
    async def add(self, b, i): await self.callback(b, i) # use the same callback as the remove button

    @discord.ui.button(label="Play", style=discord.ButtonStyle.primary)
    async def play(self, button: discord.ui.Button, interaction: discord.Interaction):
        player = self.client.lavalink.player_manager.create(self.ctx.guild.id, endpoint=str(self.ctx.guild.region))

        # if the playlist is not listed
        if self.pl not in self.playlists.keys(): 
            return await interaction.response.send_message("**Error:** could not find playlist", ephemeral=True)
        
        # if the playlist is listed, but empty
        if len(self.playlists[self.pl]) == 0:
            return await interaction.response.send_message("**Error:** this playlist is empty", ephemeral=True)

        # if the user is not in a vc
        if not self.ctx.author.voice:
            return await interaction.response.send_message("**Error:** you're not in a vc", ephemeral=True)

        # if the player is not connected to a vc, join the user's vc.
        # else, if the user's vc does not match the player's vc, send an error
        if not player.is_connected:
            player.store('channel', self.ctx.channel.id)
            await self.ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)            
        elif self.ctx.author.voice.channel.id != int(player.channel_id):
            return await interaction.response.send_message("**Error:** you're not in the correct vc", ephemeral=True)

        count = 0
        track_list = ''
        extended = False

        # get the information of each track in the playlist
        for track in self.playlists[self.pl]:
            count += 1

            if extended:
                continue

            # if more than ten tracks are counted, skip them and continue updating the counter from 0
            if count == 10:
                count = 0
                extended = True
                continue

            title = track["title"]
            url = track["url"]

            # add the track
            results = await player.node.get_tracks(url)
            track = results['tracks'][0]
            track = lavalink.models.AudioTrack(track, self.ctx.author.id)
            player.add(requester=self.ctx.author.id, track=track)

            track_list += f'`{count}.` [{title}]({url})\n'
        
        # show the number of tracks that are not shown
        if extended is True:
            track_list += f'(`+{count} more`)'

        embed = discord.Embed(
            title = self.pl,
            description = track_list,
            color = added_color
        )
        embed.set_author(name=f"Added Playlist to Queue ({len(self.playlists[self.pl])} tracks)", icon_url=self.ctx.author.display_avatar)
        
        await self.ctx.send(embed = embed)

        # start playing if it's not
        if not player.is_playing:
            return await player.play()
        else:
            return

    @discord.ui.button(label="-", style=discord.ButtonStyle.danger, custom_id="remove")
    async def remove(self, b, i): await self.callback(b, i) # use the same callback as the add button

    async def callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        num = 0
        list_of_tracks = ''

        # function that updates the original embed, which will be used when the user adds or removes a track
        async def update_embed(button, interaction, title = None, url = None, position = None):
            # if adding a track
            if button.custom_id == "add":
                # fetch the original message embed again in case it changed (fixes visual glitch)
                fetched_msg = await self.msg.channel.fetch_message(self.msg.id)
                new_embed = fetched_msg.embeds[0]
                new_track = f"\n**{position}.** [{title}]({url}) - {interaction.user.mention}"

                # add the track to the embed
                new_embed.description = new_embed.description.replace("(this playlist is empty)", "") + new_track
                
                # enable the play/remove track buttons if they were disabled
                self.children[1].disabled = False
                self.children[2].disabled = False
                
                await self.msg.edit(embed = new_embed, view = self)
            
            # if removing a track
            if button.custom_id == "remove":
                # if the playlist is listed in the database and it has tracks
                if self.pl in self.playlists.keys() and len(self.playlists[self.pl]) > 0:
                    count = 0
                    track_list = ''

                    # build the track list again
                    for track in self.playlists[self.pl]:
                        count += 1
                        title = track['title']
                        url = track['url']
                        user = f"<@{track['user']}>"
                        track_list += f"**{count}.** [{title}]({url}) - {user}\n"
                        
                    embed = discord.Embed(
                        title = f"{self.pl} - {count} track(s)",
                        description = track_list,
                        color = self.client.gray
                    )
                else:
                    # if the playlist is now empty
                    embed = discord.Embed(
                        title = self.pl,
                        description = "(this playlist is empty)",
                        color = self.client.gray
                    )
                    
                    # disable the play/remove track buttons
                    self.children[1].disabled = True
                    self.children[2].disabled = True
                
                await self.msg.edit(embed = embed, view = self)

        embed = discord.Embed(
            title = f"{button.custom_id.capitalize()} Tracks",
            color = self.client.gray
        )

        # choose which words to use depending on button choice
        if button.custom_id == "add":
            words = ["youtube links", "add"]
        if button.custom_id == "remove":
            words = ["indexes", "remove"]

        description_text = "Send the {} of the tracks you want to {}.".format(*words)

        embed.description = description_text

        # create cancel view
        cancel_view = CancelView()

        await interaction.response.send_message(embed = embed, view = cancel_view, ephemeral = True)

        # continue recieving tracks/indexes as long as the user hasn't canceled it
        while not cancel_view.canceled:
            try:
                # wait for message or interaction
                done, _ = await asyncio.wait([
                    self.client.loop.create_task(self.client.wait_for('message', check=check(interaction), timeout=300)),
                    self.client.loop.create_task(self.client.wait_for('interaction', check=btn_check(interaction), timeout=300))
                ], return_when=asyncio.FIRST_COMPLETED)
                
                for future in done:
                    msg_or_interaction = future.result()

                # check if bot received interaction
                if isinstance(msg_or_interaction, discord.interactions.Interaction):
                    if cancel_view.canceled: break # if they canceled
                    else: continue # unexpected interaction

                # check if bot received message
                if isinstance(msg_or_interaction, discord.Message):
                    message = msg_or_interaction
                else:
                    # got something else unexpected
                    continue

                # make the bot ignore itself
                if message.author == self.client.user: continue
            except asyncio.TimeoutError:
                break
            
            # if adding a track
            if button.custom_id == "add":
                url = message.content

                # check if it's a youtube url
                if not youtube_rx.match(url):
                    await interaction.followup.send("**Error:** that is not a valid youtube link, try again", ephemeral=True)
                    continue
                else:
                    url = youtube_rx.match(url).group(0)
                
                await message.delete()

                processing = "\n_ _ - **Adding track...**"
                embed.description = description_text + processing

                await interaction.edit_original_message(embed = embed)

                # get track details
                title = pafy.new(url).title
                new_track = {"title": title, "url": url, "user": interaction.user.id}
                
                # update the playlist with the new track
                if self.pl in self.playlists.keys():
                    db.update_one(g_id(self.ctx), {'$push': {f'playlists.{self.pl}': new_track}})
                    position = len(db.find_one(g_id(self.ctx))['playlists'][self.pl])
                else:
                    # create the playlist if it doesn't exist
                    db.update_one(g_id(self.ctx), {'$set': {f'playlists.{self.pl}': [new_track]}}, upsert = True)
                    position = 1

                num += 1
                # update self.playlists to include the new playlist track
                self.playlists = db.find_one({"guild_id": self.ctx.guild.id, "playlists": {"$ne": None}})['playlists']

                list_of_tracks += f"\n_ _ - **{title}**"
                embed.description = description_text + f"\n_ _ - **Added `{title}`**"
                await interaction.edit_original_message(embed = embed)

                await update_embed(button, interaction, title, url, position)
                continue
            
            # if removing a track
            if button.custom_id == "remove":
                # check if the receieved message is a number
                if not message.content.isnumeric():
                    await interaction.followup.send("**Error:** invalid index, try again", ephemeral=True)
                    continue
                else:
                    message.content = int(message.content)

                # if the number given is larger than the number of tracks in the playlist, send an error
                if int(message.content) > len(self.playlists[self.pl]):
                    await interaction.followup.send("**Error:** index is too high, try again", ephemeral=True)
                    continue
                
                await message.delete()

                processing = "\n_ _ - **Removing track...**"
                embed.description = description_text + processing

                await interaction.edit_original_message(embed = embed)

                track_id = int(message.content) - 1

                # get the title of the track that will be deleted
                title = self.playlists[self.pl][track_id]["title"]

                # delete the track
                if len(self.playlists[self.pl]) > 1:
                    db.update_one(g_id(self.ctx), {'$unset': {f'playlists.{self.pl}.{track_id}': 1}})
                    db.update_one(g_id(self.ctx), {'$pull': {f'playlists.{self.pl}': None}})
                else:
                    # remove the playlist from the database if the track being deleted was the only track
                    db.update_one(g_id(self.ctx), {'$unset': {f'playlists.{self.pl}': ""}})

                num += 1
                # update self.playlists to include the updated playlist
                self.playlists = db.find_one({"guild_id": self.ctx.guild.id, "playlists": {"$ne": None}})['playlists']
                
                list_of_tracks += f"\n_ _ - **{title}**"
                embed.description = description_text + f"\n_ _ - **Removed `{title}`**"
                await interaction.edit_original_message(embed = embed)

                await update_embed(button, interaction)

                # if the playlist is now not in self.playlists, get out of the loop
                if self.pl not in self.playlists.keys() or len(self.playlists[self.pl]) == 0:
                    break
                else:
                    continue
        
        embed = discord.Embed()
        
        # update the embed to show the newly added/removed tracks
        if button.custom_id == "add":
            embed.title = f"Added {num} track(s)"
            embed.color = discord.Color.brand_green()
        elif button.custom_id == "remove":
            embed.title = f"Removed {num} track(s)"
            embed.color = discord.Color.red()
        
        embed.description = list_of_tracks

        await interaction.edit_original_message(embed = embed, view = None)
    
    # disable buttons on timeout
    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        
        await self.msg.edit(embed = self.msg.embeds[0], view = self)

class LavalinkVoiceClient(discord.VoiceClient):
    # class taken from https://github.com/Devoxin/Lavalink.py/blob/master/examples/music.py 

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel

        # ensure that a client already exists
        if hasattr(self.client, 'lavalink'):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(
                    'localhost',
                    3000,
                    'youshallnotpass',
                    'us',
                    'default-node')
            self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_SERVER_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_STATE_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        """ Connect the bot to the voice channel and create a player_manager if it doesn't exist yet """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel)

    async def disconnect(self, *, force: bool) -> None:
        """ Handles the disconnect. Cleans up running player and leaves the voice client """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that
        # would set channel_id to None doesn't get dispatched after the 
        # disconnect
        player.channel_id = None
        self.cleanup()

class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        global played_song
        played_song = False

        # if not already connected, connect to the lavalink server using the credentials from lavalink_opts
        if not hasattr(client, 'lavalink'):
            client.lavalink = lavalink.Client(client.user.id)
            client.lavalink.add_node(*lavalink_opts)

        # get events to use for on_track_start/end, etc.
        client.lavalink.add_event_hooks(self)

        # connect to spotify for use in the play command
        self.connect_spotify()

    def connect_spotify(self):
        """ Connects to Spotify's api """
        global api_client
        global sp_credentials

        # use credentials from spotify_keys
        auth_flow = ClientCredentialsFlow(
            application_id = spotify_keys[0],
            application_secret = spotify_keys[1]
        )

        auth_flow.load_from_env()
        api_client = SpotifyApiClient(auth_flow)
        sp_credentials = False
    
    def format_time(duration):
        """ Formats the given duration into either M:S or H:M:S """
        hour = int(time.strftime('%H', time.gmtime(int(duration))))

        # check if the duration is an hour or more
        if hour > 0:
            new_duration = time.strftime('%-H:%M:%S', time.gmtime(int(duration)))
        else:
            new_duration = time.strftime('%-M:%S', time.gmtime(int(duration)))

        return new_duration

    def cog_unload(self):
        self.client.lavalink._event_hooks.clear()

    # create a player before every command invoke
    async def cog_before_invoke(self, ctx: commands.Context):
        guild_check = ctx.guild is not None

        if guild_check:
            self.client.lavalink.player_manager.create(ctx.guild.id, endpoint=str(ctx.guild.region))

        return guild_check

    @lavalink.listener(lavalink.events.TrackStartEvent)
    async def on_track_start(self, event: lavalink.events.TrackStartEvent):
        """ Event handler for when a track starts """
        global current_track
        global np_msg
        
        if repeat_single is True:
            return
        
        current_track = [event.track, event.track.requester]

        # get the channel, requester, and duration
        channel = event.player.fetch('channel')
        channel = await self.client.fetch_channel(channel)
        requester = await self.client.fetch_user(event.track.requester)
        duration = event.track.duration // 1000
        duration = Music.format_time(duration)

        # create the embed
        playing = discord.Embed(
            title = event.track.title,
            url = event.track.uri,
            description = f"Duration: `{duration}` | Sent by {requester.mention}",
            color = playing_color
        )

        # add footer and thumbnail
        playing.set_author(name="Now Playing", icon_url = requester.display_avatar)
        playing.set_thumbnail(url=f"http://img.youtube.com/vi/{event.track.identifier}/0.jpg")

        np_msg = await channel.send(embed = playing)
    
    @lavalink.listener(lavalink.events.TrackEndEvent)
    async def on_track_end(self, event: lavalink.events.TrackEndEvent):
        """ Event handler for when a track ends """
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
            duration = Music.format_time(duration)

            # create "played track" embed
            played = discord.Embed(
                title = title,
                url = url,
                description = f"Sent by {user.mention} | Duration: `{duration}`",
                color = self.client.gray
            )
            played.set_author(name="Played Audio", icon_url=user.display_avatar)

            # edit the original "now playing" message with the embed
            await np_msg.edit(embed = played)
    
    # @lavalink.listener(lavalink.events.QueueEndEvent)
    # async def on_queue_end(self, event: lavalink.events.QueueEndEvent):
        # """ Event handler for when the queue ends """
        # guild_id = int(event.player.guild_id)
        # guild = await self.client.fetch_guild(guild_id)

        # automatically disconnect the bot if it isn't playing anything - unused
        #await asyncio.sleep(300)
        #if not event.player.is_playing and event.player.is_connected:
        #    await guild.voice_client.disconnect(force=False)

    @commands.command(aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str = None):
        """ Plays a track from a given url/query """
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
        if not url_rx.match(query):
            query = f'ytsearch:{query}'
        else:
            # if the message contains a url, check if it's spotify
            query = url_rx.match(query).group(0)

            if (query.find("spotify") != -1):
                if sp_credentials is False:
                    await api_client.get_auth_token_with_client_credentials()
                    await api_client.create_new_client()
                    sp_credentials = True
                is_spotify = True
            else:
                # if it's not spotify (but is a url), check if it's youtube
                # if it's not youtube, send an error
                if not youtube_rx.match(query):
                    return await ctx.send("**Error:** only youtube/spotify links can be used")

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
                    sp_track = lavalink.models.AudioTrack(sp_track, ctx.author.id)
                    player.add(requester=ctx.author.id, track=sp_track)
                    total_duration += track["duration_ms"]
                    count += 1
                
                await msg.delete()

                total_duration = total_duration // 1000
                duration = Music.format_time(total_duration)

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
                    shortened = textwrap.shorten(track.title, 70, placeholder="...")
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
                song_list = ''
                count = 0

                # list each track in the results
                for track in results['tracks']:
                    count += 1

                    # stop after five tracks
                    if count > 5:
                        break

                    track_name = track.title
                    track_url = track.uri
                    song_list += f'[**{count}**] [{track_name}]({track_url})\n'

                song_list += "type the number of the track you want (or `0` to cancel)"

                # create embed with the track list
                embed = discord.Embed(
                    description = song_list,
                    color = self.client.gray
                )
                embed.set_author(name=f"{ctx.author.name} -- choose a song", icon_url=ctx.author.display_avatar)

                bot_msg = await ctx.send(embed = embed)
                
                # wait for user input
                try:
                    user_msg = await self.client.wait_for('message', check=check(ctx), timeout=300)
                except asyncio.TimeoutError:
                    return await bot_msg.edit(content = "**Error:** timed out of song selection", embed = None)

                # if the received message is not a number
                if not user_msg.content.isnumeric():
                    return await bot_msg.edit(content = "**Error:** invalid index", embed = None)
                
                # if the user wants to cancel by sending 0
                if int(user_msg.content) == 0:
                    await user_msg.delete()
                    await bot_msg.delete()
                    return

                # select the track using the given index
                try:
                    track = results['tracks'][int(user_msg.content)-1]
                except IndexError:
                    return await bot_msg.edit(content = "**Error:** invalid index", embed = None)

                await user_msg.delete()
                await bot_msg.delete()
            else:
                track = results['tracks'][0]

            # if the player is currently playing a track, add to the queue
            if player.is_playing:
                track_id = track.identifier

                # get the track duration and forrmat it
                track_duration = track.duration
                duration = track_duration // 1000
                duration = Music.format_time(duration)

                # "added to queue"
                embed = discord.Embed(
                    title = track.title,
                    url = track.uri,
                    description = f"Added by {ctx.author.mention} | Duration: `{duration}`",
                    color = added_color
                )

                # getting the estimated time until it plays the track:
                
                # start with the time left of the current track
                total_duration = player.current.duration - player.position
 
                # add the durations of the other track
                for song in player.queue:
                    total_duration += song.duration
                total_duration = total_duration // 1000
                total_duration = Music.format_time(total_duration)

                queue_length = len(player.queue) + 1

                # set the footer, author, and thumbnail
                embed.set_footer(text=f"Will be played in {total_duration}")
                embed.set_author(name=f"Added to Queue - #{queue_length}", icon_url=ctx.author.display_avatar)
                embed.set_thumbnail(url=f"http://img.youtube.com/vi/{track_id}/0.jpg")

                await ctx.send(embed=embed)

            # add the track to the queue. if the player is not playing anything, this will make it play the requested track
            track = lavalink.models.AudioTrack(track, ctx.author.id)
            player.add(requester=ctx.author.id, track=track)

        # play the track if it isn't doing anything
        if not player.is_playing:
            await player.play()

    @commands.command(aliases=['j'])
    async def join(self, ctx: commands.Context):
        """ Makes the bot join a vc """
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
        """ Disconnects the bot from the vc and clears the queue """
        # disable loop
        global repeat_single; repeat_single = False

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
        """ Skips either the current track, a track in the queue, or the entire queue """
        global repeat_single
        global np_msg

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
            if repeat_single:
                repeat_single = False

            # get the information of the current track
            title = player.current.title
            url = f"https://youtube.com/watch?v={player.current.identifier}"
            user = await self.client.fetch_user(current_track[1])
            duration = player.current.duration // 1000
            duration = Music.format_time(duration)

            # "track ended" embed
            embed = discord.Embed(
                title = title,
                url = url,
                description = f"Sent by {user.mention} | Duration: `{duration}`",
                color = self.client.gray
            )
            embed.set_author(name="Played Audio", icon_url=user.display_avatar)
            await np_msg.edit(embed = embed)

            await ctx.message.add_reaction(self.client.ok)
            return await player.skip()
        
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
        """ Shuffles the playing order of the queue """
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
        """ Loops the current track """
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
        """ Shows how many times the current track has been looped """
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
        """ Creates playlists and lets you add/remove tracks from them """
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
        
        pl_doc = db.find_one({"guild_id": ctx.guild.id, "playlists": {"$ne": None}})

        # use an empty dict if the 'playlists' field is not listed in the guild database
        if pl_doc is None:
            playlists = {}
        else:
            playlists = pl_doc['playlists']

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
            if not youtube_rx.match(res):
                return await ctx.send("**Error:** not a valid url")

            # get track information from the url
            title = pafy.new(res).title
            new_track = {"title": title, "url": res, "user": ctx.author.id}
            
            # update the playlist with the new track
            if pl_name in playlists.keys():
                db.update_one(g_id(ctx), {'$push': {f'playlists.{pl_name}': new_track}})
                position = len(db.find_one(g_id(ctx))['playlists'][pl_name])
                return await ctx.send(f"{self.client.ok} Added track **{title}** (`#{position}`)")
            else:
                # create the playlist if it doesn't exist
                db.update_one(g_id(ctx), {'$set': {f'playlists.{pl_name}': [new_track]}}, upsert = True)
                return await ctx.send(f"{self.client.ok} Created playlist **{pl_name}** and added track **{title}**")

        # if the user is trying to remove a track
        if opt in remove_opt:
            # if the playlist is empty
            if playlist_is_not_there:
                return await ctx.send("**Error:** that playlist doesn't exist")

            # if the user does not give an index, or if the index is "all", remove the playlist entirely
            if res is None or res.lower() == "all":
                db.update_one(g_id(ctx), {'$unset': {f'playlists.{pl_name}': ""}})
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
                    db.update_one(g_id(ctx), {'$unset': {f'playlists.{pl_name}.{track_id}': 1}})
                    db.update_one(g_id(ctx), {'$pull': {f'playlists.{pl_name}': None}})
                else:
                    # remove the playlist completely if there was only one track left
                    db.update_one(g_id(ctx), {'$unset': {f'playlists.{pl_name}': ""}})

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
        """ Pauses/unpauses the current track """
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
        """ Seek to a given timestamp, or rewind/fast-forward the track """
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
            new_time = functools.reduce(lambda prev, next: prev * 60 + next, [float(x) for x in new_time.split(":")], 0) * 1000
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
        formatted_time = Music.format_time(before_format)
        res = res.format(formatted_time)
        
        await player.seek(new_time)
        return await ctx.send(f"{self.client.ok} {res}")

    @commands.command(aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """ Displays the queue of the server """
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
        """ Displays information about the current track """
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
        time_at = Music.format_time(current_song_pos)
        time_left = Music.format_time(song_duration - current_song_pos)
        duration = Music.format_time(song_duration)

        # create embed
        embed = discord.Embed(
            title = player.current.title,
            url = f"https://youtube.com/watch?v={player.current.identifier}",
            description = f"Sent by {requester.mention} | Duration: `{duration}`",
            color = 0x4287f5
        )

        embed.set_footer(text=f"{time_at} elapsed {line} {time_left} left")
        embed.set_author(name=f"Currently Playing", icon_url=requester.display_avatar)
        embed.set_thumbnail(url=f"http://img.youtube.com/vi/{player.current.identifier}/0.jpg")

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
                

def setup(bot):
    bot.add_cog(Music(bot))
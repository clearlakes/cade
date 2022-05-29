import discord
from discord.ext import commands

from utils.functions import btn_check, check, format_time, get_attachment, get_media_ids
from utils.variables import Clients, Regex, HANDLE
from utils.lavalink_server import LavalinkVoiceClient
from utils import database
import lavalink

import asyncio
import pafy
import math
import json

api = Clients.twitter()
handle = HANDLE

re = Regex()

class ChoiceView(discord.ui.View):
    # download choice for "get" command
    def __init__(self, ctx):
        super().__init__()
        self.choice = None
        self.ctx = ctx

    @discord.ui.button(label="audio", style=discord.ButtonStyle.secondary)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return
        
        # the user chose to download the audio
        self.choice = "audio"
        self.stop()

    @discord.ui.button(label="video", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        # the user chose to download the video
        self.choice = "video"
        self.stop()

class CancelView(discord.ui.View):
    def __init__(self):
        self.canceled = False
        super().__init__()
    
    # create a button with the label "Done" that sets self.canceled to True
    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.canceled = True
        self.stop()
    
    async def on_timeout(self) -> None:
        return await super().on_timeout()

class Dropdown(discord.ui.Select):
    def __init__(self, ctx):
        # dropdown options
        options = [
            discord.SelectOption(
                label="General",
                description="regular commands"
            ),
            discord.SelectOption(
                label="Music",
                description="so much groove"
            ),
            discord.SelectOption(
                label="Media",
                description="image and audio commands"
            )
        ]
        
        # add funny museum commands if guild matches the id
        if ctx.guild.id == 783166876784001075:
            options.extend([
                discord.SelectOption(
                    label="Funny Museum",
                    description="made for funny"
                )
            ])

        # placeholder and setup
        super().__init__(
            placeholder="select le category",
            min_values=1,
            max_values=1,
            options=options,
        )

    # callback runs whenever something is selected
    async def callback(self, interaction: discord.Interaction):
        # get information from category
        def get_help(cat):
            with open("commands.json", "r") as f:
                data = json.load(f)
            
            desc = ""
            for key in data[cat]:
                about = data[cat][key]["desc"]
                usage = data[cat][key]["usage"]
                
                # add backticks to each word in 'usage' if the usage isn't nothing
                if usage is not None: usage_str = ' `' + '` `'.join(usage.split()) + '`' if usage != '' else ''
                else: usage_str = ""

                # add the command to the description
                desc += f"**.{key}**{usage_str} - {about}\n"
            return desc
        
        selection = self.values[0]
        em = discord.Embed(color = 0x2f3136)
        em.title = f"Commands - {selection}"

        # edit embed when selection is made
        em.description = get_help(selection.lower())
        
        await interaction.response.edit_message(embed = em)

class DropdownView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()

        # build the dropdown list
        self.add_item(Dropdown(ctx))

class ReplyView(discord.ui.View):
    def __init__(self, client, msg, reply_id):
        self.msg = msg
        self.client = client
        self.reply_id = reply_id
        super().__init__(timeout = None)

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.primary, custom_id="replyview:reply")
    async def reply(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = CancelView()
        view.children[0].label = "Cancel"
        view.children[0].style = discord.ButtonStyle.secondary

        await interaction.response.send_message("Send a message to use as the reply.", view = view, ephemeral = True)
        
        # get user input
        try:
            # wait for either a message or button press
            done, _ = await asyncio.wait([
                self.client.loop.create_task(self.client.wait_for('message', check = check(interaction), timeout=300)),
                self.client.loop.create_task(self.client.wait_for('interaction', check = btn_check(interaction), timeout=300))
            ], return_when=asyncio.FIRST_COMPLETED)
            
            for future in done:
                msg_or_interaction = future.result()

            # if a button press was received
            if isinstance(msg_or_interaction, discord.interactions.Interaction):
                if view.canceled: 
                    return await interaction.edit_original_message(content = "(canceled)", view = None)
            
            # if a message was received instead
            if isinstance(msg_or_interaction, discord.Message):
                message = msg_or_interaction
            else:
                # got unexpected response
                return await interaction.edit_original_message(content = "**Error:** got a weird response for some reason, please try again (or don't if you wanted to cancel)", view = None)
        except asyncio.TimeoutError:
            await interaction.edit_original_message(content = "**Error:** timed out", view = None)

        await message.delete()
        
        ctx = await self.client.get_context(message)
        status = message.content
        
        # same procedure as a reply command
        content_given = await get_attachment(ctx, interaction)

        if content_given != False:
            media_ids = get_media_ids(content_given)
        else:
            media_ids = None
        
        # send the reply
        new_status = api.update_status(status=status, media_ids=media_ids, in_reply_to_status_id=self.reply_id, auto_populate_reply_metadata=True)

        await interaction.edit_original_message(content = "Replied!", view = None)

        # reply to the original message containing the tweet
        new_msg = await self.msg.reply(f"{interaction.user.mention} replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(self.client, new_msg, new_status.id)
        await new_msg.edit(view = view)

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
                duration = format_time(track.duration // 1000)
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
        self.db = database.Guild(ctx.guild)
        self.doc = self.db.get()

        # use an empty dict if 'playlists' is not in the guild db
        self.playlists = self.doc.playlists if self.doc.playlists else {}

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
            color = 0x42f55a
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
        list_of_tracks = ''
        num = 0

        # function that updates the original embed, which will be used when the user adds or removes a track
        async def update_embed(button: discord.ui.Button, interaction, title = None, url = None, position = None):
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
                if not re.youtube.match(url):
                    await interaction.followup.send("**Error:** that is not a valid youtube link, try again", ephemeral=True)
                    continue
                else:
                    url = re.youtube.match(url).group(0)
                
                await message.delete()

                processing = "\n_ _ - **Adding track...**"
                embed.description = description_text + processing

                await interaction.edit_original_message(embed = embed)

                # get track details
                title = pafy.new(url).title
                new_track = {"title": title, "url": url, "user": interaction.user.id}
                
                # update the playlist with the new track
                self.db.push(f'playlists.{self.pl}', new_track)
                position = len(self.doc.playlists[self.pl]) if self.pl in self.playlists.keys() else 1

                num += 1
                # update self.playlists to include the new playlist track
                self.playlists = self.db.get().playlists

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
                    self.db.del_obj(f'playlists.{self.pl}', track_id)
                else:
                    # remove the playlist from the database if the final track was deleted
                    self.db.del_obj('playlists', self.pl)

                num += 1
                # update self.playlists to include the updated playlist
                self.playlists = self.db.get().playlists
                
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

class TrackSelectView(discord.ui.View):
    def __init__(self, ctx, msg, tracks):
        super().__init__()
        
        self.msg: discord.Message = msg
        self.ctx: commands.Context = ctx
        self.tracks: list = tracks
        self.track = tracks[0]
        self.selection = None

    async def refresh_msg(self):
        embed = discord.Embed(
            title = self.track.title,
            url = self.track.uri
        )

        embed.set_author(name = f"Result {self.tracks.index(self.track) + 1} out of {len(self.tracks)}")
        embed.set_thumbnail(url = f"http://img.youtube.com/vi/{self.track.identifier}/0.jpg")

        embed.description = f"Author: **{self.track.author}** | Duration: `{format_time(self.track.duration // 1000)}`"

        # disable 'back' button if on the first track
        if self.tracks.index(self.track) == 0:
            self.children[1].disabled = True
        else:
            self.children[1].disabled = False

        # disable 'next' button if last track is reached
        if self.tracks.index(self.track) + 1 == len(self.tracks):
            self.children[2].disabled = True
        else:
            self.children[2].disabled = False

        await self.msg.edit(embed = embed, view = self)

    @discord.ui.button(label="nvm", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.selection = None
        self.stop()

    @discord.ui.button(label="back", style=discord.ButtonStyle.secondary)
    async def back(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.track = self.tracks[self.tracks.index(self.track) - 1]
        await self.refresh_msg()
    
    @discord.ui.button(label="next", style=discord.ButtonStyle.secondary)
    async def next(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.track = self.tracks[self.tracks.index(self.track) + 1]
        await self.refresh_msg()

    @discord.ui.button(label="this one", style=discord.ButtonStyle.primary)
    async def play(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.selection = self.track
        self.stop()
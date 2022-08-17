import discord
from discord.ext import commands

from utils.functions import (
    get_yt_thumbnail,
    get_attachment,
    get_media_ids,
    format_time,
    btn_check,
    check
)
from utils.music.voice import LavalinkVoiceClient
from utils.dataclasses import colors, err, reg
from utils.clients import Clients, handle
from utils import database

from lavalink import DefaultPlayer, AudioTrack, LoadResult, Client
from youtube_dl import YoutubeDL
import asyncio
import json

class ChoiceView(discord.ui.View):
    def __init__(self, ctx: commands.Context, choices: list):
        super().__init__(timeout = None)

        self.choice = None
        self.ctx = ctx

        async def callback(interaction: discord.Interaction): 
            if interaction.user != self.ctx.author:
                return

            self.choice = interaction.data['custom_id']
            self.stop()

        for choice in choices:
            button = discord.ui.Button(label = choice, custom_id = choice)
            button.callback = callback
            self.add_item(button)

class Dropdown(discord.ui.Select):
    def __init__(self, ctx: commands.Context):
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
            options=options,
        )

    # callback runs whenever something is selected
    async def callback(self, interaction: discord.Interaction):
        category = self.values[0].lower()

        with open("commands.json", "r") as f:
            data = json.load(f)
        
        desc = ""
        for cmd in data[category]:
            about: str = data[category][cmd]["desc"]
            usage: str = data[category][cmd]["usage"]
            
            # add backticks to each word in 'usage' if the usage isn't nothing
            usage_str = ' `' + '` `'.join(usage.split()) + '`' if usage else ''

            # add the command to the description
            desc += f"**.{cmd}**{usage_str} - {about}\n"

        embed = discord.Embed(
            title = f"Commands - {category}",
            description = desc,
            color = colors.EMBED_BG
        )
        
        await interaction.response.edit_message(embed = embed)

class DropdownView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout = None)

        # build the dropdown list
        self.add_item(Dropdown(ctx))

class ReplyView(discord.ui.View):
    def __init__(self, ctx: commands.Context, msg: discord.Message, reply_id):
        super().__init__(timeout = None)

        self.ctx = ctx
        self.msg = msg
        self.reply_id = reply_id

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.primary, custom_id="replyview:reply")
    async def reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChoiceView(self.ctx, ['cancel'])
        await interaction.response.send_message("send a message to use as the reply", view = view, ephemeral = True)

        client = interaction.client
        
        # get user input
        try:
            # wait for either a message or button press
            done, _ = await asyncio.wait([
                client.loop.create_task(client.wait_for('message', check = check(interaction))),
                client.loop.create_task(client.wait_for('interaction', check = btn_check(interaction)))
            ], return_when = 'FIRST_COMPLETED')
            
            for future in done:
                msg_or_interaction = future.result()

            # if a button press was received
            if isinstance(msg_or_interaction, discord.interactions.Interaction):
                if view.choice == 'cancel': 
                    return await interaction.edit_original_response(content = "(canceled)", view = None)
            
            # if a message was received instead
            if isinstance(msg_or_interaction, discord.Message):
                message = msg_or_interaction
            else:
                # got unexpected response
                return await interaction.edit_original_response(content = err.UNEXPECTED, view = None)
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content = err.TIMED_OUT, view = None)

        await message.delete()
        
        ctx = await interaction.client.get_context(message)
        status = message.content
        
        # same procedure as a reply command
        content_given = await get_attachment(ctx, interaction)
        media_ids = get_media_ids(content_given) if content_given else None
        
        # send the reply
        new_status = Clients().twitter().update_status(status=status, media_ids=media_ids, in_reply_to_status_id=self.reply_id, auto_populate_reply_metadata=True)

        await interaction.edit_original_response(content = "Replied!", view = None)

        # reply to the original message containing the tweet
        new_msg = await self.msg.reply(f"{interaction.user.mention} replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")
        view = ReplyView(interaction.client, new_msg, new_status.id)
        await new_msg.edit(view = view)

class PlaylistView(discord.ui.View):
    def __init__(self, lavalink: Client, ctx: commands.Context, msg: discord.Message, playlist: list):
        super().__init__()

        self.db = database.Guild(ctx.guild)
        self.doc = self.db.get()

        # use an empty dict if 'playlists' is not in the guild db
        self.playlists = self.doc.playlists if self.doc.playlists else {}

        self.lavalink = lavalink
        self.pl = playlist
        self.msg = msg
        self.ctx = ctx

    @discord.ui.button(label="+", style=discord.ButtonStyle.success, custom_id="add")
    async def add(self, i, b): await self.callback(i, b) # use the same callback as the remove button

    @discord.ui.button(label="Play", style=discord.ButtonStyle.primary)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        # if the playlist is not listed
        if self.pl not in self.playlists.keys(): 
            return await interaction.response.send_message(err.PLAYLIST_DOESNT_EXIST, ephemeral=True)
        
        # if the playlist is listed, but empty
        if len(self.playlists[self.pl]) == 0:
            return await interaction.response.send_message(err.PLAYLIST_IS_EMPTY, ephemeral=True)

        # if the user is not in a vc
        if not self.ctx.author.voice:
            return await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral=True)

        player: DefaultPlayer = self.lavalink.player_manager.create(self.ctx.guild.id, endpoint = str(self.ctx.author.voice.channel.rtc_region))

        # if the player is not connected to a vc, join the user's vc.
        # else, if the user's vc does not match the player's vc, send an error
        if not player.is_connected:
            player.store('channel', self.ctx.channel.id)
            await self.ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)            
        elif self.ctx.author.voice.channel.id != int(player.channel_id):
            return await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral=True)

        track_list = ''

        # get the information of each track in the playlist
        for i, track in enumerate(self.playlists[self.pl]):
            if i == 9:
                break  # only display the first ten tracks

            title = track["title"]
            url = track["url"]

            # add the track
            results: LoadResult = await player.node.get_tracks(url)
            track = results.tracks[0]

            player.add(track, self.ctx.author.id)

            track_list += f'`{i + 1}.` [{title}]({url})\n'
        
        # show the number of tracks that are not shown
        if (track_num := len(self.playlists[self.pl])) > 10:
            track_list += f'`+{track_num - 10} more`'

        embed = discord.Embed(title = self.pl, description = track_list, color = colors.ADDED_TRACK)
        embed.set_author(name=f"Added Playlist to Queue ({len(self.playlists[self.pl])} tracks)", icon_url=self.ctx.author.display_avatar)
        
        await self.ctx.send(embed = embed)

        # start playing if it's not
        await player.play(no_replace = True)

    @discord.ui.button(label="-", style=discord.ButtonStyle.danger, custom_id="remove")
    async def remove(self, i, b): await self.callback(i, b) # use the same callback as the add button

    async def callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        client = interaction.client
        list_of_tracks = ''
        num = 0

        # function that updates the original embed, which will be used when the user adds or removes a track
        async def update_embed(button: discord.ui.Button, interaction: discord.Interaction, title = None, url = None, position = None):
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
            elif button.custom_id == "remove":
                # if the playlist is listed in the database and it has tracks
                if self.pl in self.playlists.keys() and len(self.playlists[self.pl]) > 0:
                    track_list = ''

                    # build the track list again
                    for i, track in enumerate(self.playlists[self.pl]):
                        title = track['title']
                        url = track['url']
                        user = f"<@{track['user']}>"

                        track_list += f"**{i}.** [{title}]({url}) - {user}\n"
                        
                    embed = discord.Embed(
                        title = f"{self.pl} - {len(self.playlists[self.pl])} track(s)",
                        description = track_list,
                        color = colors.EMBED_BG
                    )
                else:
                    # if the playlist is now empty
                    embed = discord.Embed(
                        title = self.pl,
                        description = "(this playlist is empty)",
                        color = colors.EMBED_BG
                    )
                    
                    # disable the play/remove track buttons
                    self.children[1].disabled = True
                    self.children[2].disabled = True
                
                await self.msg.edit(embed = embed, view = self)

        embed = discord.Embed(
            title = f"{button.custom_id.capitalize()} Tracks",
            color = colors.EMBED_BG
        )

        # choose which words to use depending on button choice
        if button.custom_id == "add":
            action = "Added"
            words = ["youtube links", "add"]
        elif button.custom_id == "remove":
            action = "Removed"
            words = ["indexes", "remove"]

        description_text = "Send the {} of the tracks you want to {}.".format(*words)

        embed.description = description_text

        # create cancel view
        view = ChoiceView(self.ctx, ['cancel'])
        await interaction.response.send_message(embed = embed, view = view, ephemeral = True)

        # continue recieving tracks/indexes as long as the user hasn't canceled it
        while not view.choice == 'cancel':
            title = None
            url = None
            position = None

            try:
                # wait for message or interaction
                done, _ = await asyncio.wait([
                    client.loop.create_task(client.wait_for('message', check = check(interaction))),
                    client.loop.create_task(client.wait_for('interaction', check = btn_check(interaction)))
                ], return_when = 'FIRST_COMPLETED')
                
                for future in done:
                    msg_or_interaction = future.result()

                # check if bot received interaction
                if isinstance(msg_or_interaction, discord.interactions.Interaction):
                    if view.choice == 'cancel': 
                        break  # if they canceled

                # check if bot received message
                if isinstance(msg_or_interaction, discord.Message):
                    message = msg_or_interaction
                else:
                    continue  # got something else unexpected

                # make the bot ignore itself
                if message.author == client.user: 
                    continue
            except asyncio.TimeoutError:
                break

            res = message.content
            
            # if adding a track
            if button.custom_id == "add":
                # check if it's a youtube url
                if match := reg.youtube.match(res):
                    url = match.group(0)
                else:
                    await interaction.followup.send(err.INVALID_MUSIC_URL, ephemeral=True)
                    continue
                
                await message.delete()

                processing = "\n_ _ - **Adding track...**"
                embed.description = description_text + processing

                await interaction.edit_original_response(embed = embed)

                # get track details
                video = YoutubeDL().extract_info(url, download = False)
                new_track = {"title": video['title'], "url": url, "user": interaction.user.id}
                
                # update the playlist with the new track
                self.db.push(f'playlists.{self.pl}', new_track)
                position = len(self.doc.playlists[self.pl]) if self.pl in self.playlists.keys() else 1

                action = "Added"
            
            # if removing a track
            elif button.custom_id == "remove":
                # check if the receieved message is a number
                if not res.isnumeric():
                    await interaction.followup.send(err.INVALID_INDEX, ephemeral=True)
                    continue
                else:
                    res = int(res)

                # if the number given is larger than the number of tracks in the playlist, send an error
                if res > len(self.playlists[self.pl]):
                    await interaction.followup.send(err.INVALID_INDEX, ephemeral=True)
                    continue
                
                await message.delete()

                processing = "\n_ _ - **Removing track...**"
                embed.description = description_text + processing

                await interaction.edit_original_response(embed = embed)

                track_id = res - 1

                # get the title of the track that will be deleted
                title = self.playlists[self.pl][track_id]["title"]

                # delete the track
                if len(self.playlists[self.pl]) > 1:
                    self.db.del_obj(f'playlists.{self.pl}', track_id)
                else:
                    # remove the playlist from the database if the final track was deleted
                    self.db.del_obj('playlists', self.pl)

                action = "Removed"

            num += 1
            
            # update self.playlists to include the updated playlist
            self.playlists = self.db.get().playlists
            
            list_of_tracks += f"\n_ _ - **{title}**"
            embed.description = description_text + f"\n_ _ - **{action} `{title}`**"

            await interaction.edit_original_response(embed = embed)
            await update_embed(button, interaction, title, url, position)

            # if the playlist is now empty, stop removing tracks
            if len(self.playlists[self.pl]) == 0:
                break
            else:
                continue
        
        embed = discord.Embed()
        
        # update the embed to show the newly added/removed tracks
        embed.title = f"{action} {num} track(s)"
        embed.description = list_of_tracks

        await interaction.edit_original_response(embed = embed, view = None)
    
    # disable buttons on timeout
    async def on_timeout(self):
        for btn in self.children:
            btn.disabled = True
        
        await self.msg.edit(embed = self.msg.embeds[0], view = self)

class TrackSelectView(discord.ui.View):
    def __init__(self, ctx: commands.Context, tracks: list[AudioTrack]):
        super().__init__(timeout = None)
        
        self.ctx = ctx
        self.tracks = tracks
        self.track = tracks[0]

        self.set_buttons()

    @property
    def track_embed(self):
        embed = discord.Embed(
            title = self.track.title,
            url = self.track.uri,
            description = f"Author: **{self.track.author}** | Duration: `{format_time(self.track.duration // 1000)}`",
            color = colors.EMBED_BG
        )

        embed.set_author(name = f"Result {self.tracks.index(self.track) + 1} out of {len(self.tracks)}")
        embed.set_thumbnail(url = get_yt_thumbnail(self.track.identifier))

        return embed

    def set_buttons(self):
        # disable 'back' button if on the first track, and 'next' button if last track is reached
        self.children[1].disabled = (self.tracks[0] == self.track)
        self.children[2].disabled = (self.tracks[-1] == self.track)

    async def refresh_msg(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = self.track_embed

        self.set_buttons()
        await self.message.edit(embed = embed, view = self)

    @discord.ui.button(label="nvm", style=discord.ButtonStyle.secondary, custom_id="ts:cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return

        self.track = None
        self.stop()

    @discord.ui.button(label="back", style=discord.ButtonStyle.secondary, custom_id="ts:back")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return

        self.track = self.tracks[self.tracks.index(self.track) - 1]
        await self.refresh_msg(interaction)
    
    @discord.ui.button(label="next", style=discord.ButtonStyle.secondary, custom_id="ts:next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return

        self.track = self.tracks[self.tracks.index(self.track) + 1]
        await self.refresh_msg(interaction)

    @discord.ui.button(label="this one", style=discord.ButtonStyle.primary, custom_id="ts:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return

        # self.track is now the selected track
        self.stop()

class NowPlayingView(discord.ui.View):
    def __init__(self, ctx: commands.Context, player: DefaultPlayer, msg: discord.Message):
        super().__init__(timeout = None)
        
        self.id = f"{ctx.guild.id}:{player.current.identifier}"
        self.embed = msg.embeds[0]
        self.player = player
        self.ctx = ctx
        self.msg = msg

        # change pause emoji to play emoji, if paused
        if player.paused:
            self.children[1].emoji = "▶️"
        
        # change loop emoji to whatever 🔂 is, if looped
        if player.loop:
            self.children[2].emoji = "🔂"

    def disable(self, reason: str):
        skip_btn = self.children[0]
        skip_btn.disabled = True
        skip_btn.label = reason

        self.children = [skip_btn]
        self.stop()

        return self
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return False

        if not self.ctx.author.voice or (self.ctx.author.voice.channel.id != int(self.player.channel_id)):
            await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral = True)
            return False

        await interaction.response.defer()
        return True

    @discord.ui.button(emoji = "⏩", custom_id = f"np:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable("skipped")
        self.player.set_loop(0)
        
        await self.msg.edit(view = self)
        await self.player.skip()

    @discord.ui.button(emoji = "⏸️", custom_id = "np:pause")
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.paused:
            await self.player.set_pause(True)
            self.children[1].emoji = "▶️"
            self.embed.description += " | **Paused**"
        else:
            await self.player.set_pause(False)
            self.children[1].emoji = "⏸️"
            self.embed.description = self.embed.description.replace(" | **Paused**", "")

        await self.msg.edit(embed = self.embed, view = self)

    @discord.ui.button(emoji = "🔁", custom_id = "np:loop")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.loop:
            self.player.set_loop(1)
            self.embed.set_footer(text = f"{self.embed.footer.text} • looped")
            self.children[2].emoji = "🔂"
        else:
            self.player.set_loop(0)
            self.embed.set_footer(text = self.embed.footer.text.replace(" • looped", ""))
            self.children[2].emoji = "🔁"

        await self.msg.edit(embed = self.embed, view = self)
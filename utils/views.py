import discord
from discord.ext import commands

from utils.functions import (
    get_tweet_attachments,
    get_yt_thumbnail,
    get_media_ids,
    format_time,
    btn_check,
    check
)
from utils.music.tracks import create_music_embed, find_tracks
from utils.music.voice import LavalinkVoiceClient
from utils.dataclasses import colors, emoji, err
from utils.clients import Clients, handle
from utils import database

from lavalink import DefaultPlayer, AudioTrack, Client
import asyncio

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

class HelpView(discord.ui.View):
    def __init__(self, client: commands.Bot, ctx: commands.Context):
        super().__init__(timeout = None)
        self.client = client
        self.ctx = ctx

        for cog in client.cogs.keys():
            # don't show funny museum commands if not funny museum
            if cog == "Funny" and ctx.guild.id != 783166876784001075:
                continue
            
            button = discord.ui.Button(label = cog, custom_id = f"h:{cog}")
            button.callback = self.callback
            self.add_item(button)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return
        
        await interaction.response.defer()

        # get cog name from button id
        interaction_id = interaction.data["custom_id"]
        cog = interaction_id.split(":")[1]

        commands = [c for c in self.client.get_cog(cog).get_commands() if not c.hidden]
        command_list = ""

        longest = max([cmd.name for cmd in commands], key = len)

        for command in commands:
            # pad command name to match the longest one
            padding = len(longest) - len(command.name)
            cmd_name = f"`.{command.name}" + (" " * padding) + "`"

            command_list += f"{cmd_name} - {command.help}\n"
        
        for btn in self.children:
            # highlight the selected button
            if btn.custom_id == interaction_id:
                btn.style = discord.ButtonStyle.primary
            else:
                btn.style = discord.ButtonStyle.secondary

        embed = discord.Embed(
            title = f"{cog} Commands",
            description = command_list,
            color = colors.EMBED_BG
        )

        await interaction.message.edit(embed = embed, view = self)

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

        try:
            # get user input
            finished, message = await wait_until_button(interaction, view)
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content = err.TIMED_OUT, view = None)

        if finished:
            # if cancel button was pressed, exit
            return await interaction.edit_original_response(content = "(canceled)", view = None)

        await message.delete()
        status = message.content
        
        # same procedure as a reply command
        media = await get_tweet_attachments(interaction)
        media_ids = get_media_ids(*media)
        
        # send the reply
        new_status = Clients().twitter().update_status(status=status, media_ids=media_ids, in_reply_to_status_id=self.reply_id, auto_populate_reply_metadata=True)

        await interaction.edit_original_response(content = "Replied!", view = None)

        # reply to the original message containing the tweet
        new_msg = await self.msg.reply(f"{interaction.user.mention} replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")
        view = ReplyView(interaction.client, new_msg, new_status.id)
        await new_msg.edit(view = view)

class PlaylistView(discord.ui.View):
    def __init__(self, lavalink: Client, ctx: commands.Context, playlist: str):
        super().__init__(timeout = None)

        self.lavalink = lavalink
        self.playlist = playlist
        self.ctx = ctx

        self.db = database.Guild(ctx.guild)

    @property
    def playlist_exists(self):
        """Checks if the playlist exists and isn't empty"""
        return (
            self.playlist in self.guild_playlists and 
            bool(self.guild_playlists[self.playlist])
        )

    async def get_track_embed(self):
        """Generates the track list for the playlist"""
        self.guild_playlists = (await self.db.get()).playlists

        embed = discord.Embed(
            title = self.playlist,
            description = "",
            color = colors.EMBED_BG
        )

        if not self.playlist_exists:
            embed.description = "(this playlist is empty)"
        else:
            # generate list of tracks
            for i, track_entry in enumerate(self.guild_playlists[self.playlist]):
                track, user_id = track_entry
                track_title = track['info']['title']
                track_url = track['info']['uri']

                embed.description += f"**{i + 1}. [{track_title}]({track_url})** - <@{user_id}>\n"

        return embed

    @property
    def updated_view(self):
        if not self.playlist_exists:
            # disable play and remove buttons if playlist is empty
            for btn in self.children[1:]:
                btn.disabled = True
        else:
            # otherwise enable all buttons
            for btn in self.children:
                btn.disabled = False

        return self
    
    @discord.ui.button(label = "+", style = discord.ButtonStyle.success, custom_id = "pv:add")
    async def add_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChoiceView(self.ctx, ['done'])

        prompt = "send a youtube/spotify link or query for the track you want to add"
        await interaction.response.send_message(prompt, view = view, ephemeral = True)

        tracks_added = 0

        while True:
            finished, message = await wait_until_button(interaction, view)

            if finished:
                break

            # search for track (thumbnail/title is not needed)
            tracks, _ = await find_tracks(self.lavalink, message.content, interaction.user.id)

            if not tracks:
                await interaction.edit_original_response(content = f"{prompt}\n- {err.NO_MUSIC_RESULTS}")
                continue
            
            # fail if it's a playlist (more than 1 track)
            if len(tracks) > 1:
                await interaction.edit_original_response(content = f"{prompt}\n- {err.SINGLE_TRACK_ONLY}")
                continue

            await message.delete()

            # add track information and the user who added it
            await self.db.push(f"playlists.{self.playlist}", [tracks[0]._raw, interaction.user.id])
            tracks_added += 1

            await interaction.edit_original_response(content = f"{prompt}\n - Added **{tracks[0].title}**")
            await interaction.message.edit(embed = await self.get_track_embed(), view = self.updated_view)
        
        await interaction.edit_original_response(content = f"{emoji.OK} added {tracks_added} track(s)", view = None)

    @discord.ui.button(label = "Play", style = discord.ButtonStyle.primary, custom_id = "pv:play")
    async def play_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: DefaultPlayer = self.lavalink.player_manager.get(interaction.guild.id)
        
        # if bot not in vc, but:
        if not player or not player.is_connected:
            if vc := interaction.user.voice:
                # user in vc -> create player and join
                player: DefaultPlayer = self.lavalink.player_manager.create(
                    guild_id = interaction.guild.id, 
                    endpoint = str(interaction.user.voice.channel.rtc_region)
                )
                player.store('channel', interaction.channel.id)
                await vc.channel.connect(cls = LavalinkVoiceClient)
            else:
                # user not in vc -> error
                return await interaction.response.send_message(err.BOT_NOT_IN_VC, ephemeral = True)
        else:
            # if user not in vc -> error
            if interaction.user.voice.channel.id != player.channel_id:
                return await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral = True)

        tracks = []

        # underscore to ignore the user id stored with the track
        for (track, _) in self.guild_playlists[self.playlist]:
            # create an AudioTrack to pass into the player
            track = AudioTrack(track, interaction.user.id)
            player.add(track, interaction.user.id)

            tracks.append(track)    
        
        embed = create_music_embed("", tracks, (None, self.playlist), player, interaction.user)

        await interaction.response.send_message(embed = embed)
        await player.play(no_replace = True)

    @discord.ui.button(label = "-", style = discord.ButtonStyle.danger, custom_id = "pv:del")
    async def del_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChoiceView(self.ctx, ['done'])

        prompt = "send the number of the track you want to remove"
        await interaction.response.send_message(prompt, view = view, ephemeral = True)

        tracks_removed = 0

        while True:
            finished, message = await wait_until_button(interaction, view)
            
            if finished:
                break

            try:
                # get the real index and find the track entry with it
                index = int(message.content) - 1
                track_entry = self.guild_playlists[self.playlist][index]
            except (ValueError, IndexError):
                # error if the index wasn't in the playlist
                await interaction.edit_original_response(content = f"{prompt}\n- {err.INVALID_INDEX}")
                continue

            await message.delete()

            # remove track from playlist
            await self.db.pull(f"playlists.{self.playlist}", track_entry)
            tracks_removed += 1

            if not self.playlist_exists:
                # stop and delete playlist entirely if it's now empty 
                await self.db.del_obj("playlists", self.playlist)
                break

            track_title = track_entry[0]['info']['title']

            await interaction.edit_original_response(content = f"{prompt}\n - Removed **{track_title}**")
            await interaction.message.edit(embed = await self.get_track_embed(), view = self.updated_view)

        await interaction.edit_original_response(content = f"{emoji.OK} removed {tracks_removed} track(s)", view = None)

class TrackSelectView(discord.ui.View):
    def __init__(self, ctx: commands.Context, tracks: list[AudioTrack]):
        super().__init__(timeout = None)
        
        self.ctx = ctx
        self.tracks = tracks

        self.track = tracks[0]
        self.extra = None

        self.set_buttons()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user == self.ctx.author

    @property
    def track_embed(self):
        thumbnail = get_yt_thumbnail(self.track.identifier)
        title = self.track.title
        
        self.extra = (thumbnail, title)

        embed = discord.Embed(
            title = title,
            url = self.track.uri,
            description = f"Author: **{self.track.author}** | Duration: `{format_time(self.track.duration // 1000)}`",
            color = colors.EMBED_BG
        )

        embed.set_author(name = f"Result {self.tracks.index(self.track) + 1} out of {len(self.tracks)}")
        embed.set_thumbnail(url = thumbnail)

        return embed

    def set_buttons(self):
        # disable 'back' button if on the first track, and 'next' button if last track is reached
        self.children[1].disabled = (self.tracks[0] == self.track)
        self.children[2].disabled = (self.tracks[-1] == self.track)

    async def refresh_msg(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = self.track_embed

        self.set_buttons()
        await interaction.message.edit(embed = embed, view = self)

    @discord.ui.button(label="nvm", style=discord.ButtonStyle.secondary, custom_id="ts:cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = None
        self.stop()

    @discord.ui.button(label="back", style=discord.ButtonStyle.secondary, custom_id="ts:back")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = self.tracks[self.tracks.index(self.track) - 1]
        await self.refresh_msg(interaction)
    
    @discord.ui.button(label="next", style=discord.ButtonStyle.secondary, custom_id="ts:next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = self.tracks[self.tracks.index(self.track) + 1]
        await self.refresh_msg(interaction)

    @discord.ui.button(label="this one", style=discord.ButtonStyle.primary, custom_id="ts:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

        # self.track/self.extra is now the selected track
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

        # remove every button except for the skip button
        for btn in self.children:
            if btn != skip_btn:
                self.remove_item(btn)

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

async def wait_until_button(interaction: discord.Interaction, choice_view: ChoiceView):
    done, _ = await asyncio.wait([
        interaction.client.loop.create_task(interaction.client.wait_for('message', check = check(interaction))),
        interaction.client.loop.create_task(interaction.client.wait_for('interaction', check = btn_check(interaction)))
    ], return_when = 'FIRST_COMPLETED')
    
    response = [future.result() for future in done][-1]

    # if a button press was received
    if type(response) is discord.interactions.Interaction and type(choice_view.choice) is str:
        return True, response.data['custom_id']
    
    # if a message was received instead
    if type(response) is discord.Message:
        return False, response
import discord
from discord.ext import commands

from utils.useful import (
    get_tweet_attachments,
    get_yt_thumbnail,
    get_media_ids,
    get_twt_url,
    format_time,
    btn_check,
    check
)
from utils.tracks import QueryInfo, create_music_embed, find_tracks
from utils.clients import LavalinkVoiceClient
from utils.base import BaseEmbed
from utils.data import bot, err
from utils.db import GuildDB
from utils.main import Cade

from lavalink import DefaultPlayer, AudioTrack
from typing import Union
import asyncio
import tweepy

class ChoiceView(discord.ui.View):
    def __init__(self, orig_user: Union[discord.Member, discord.User], choices: list):
        super().__init__(timeout = None)

        self.choice = None

        async def callback(interaction: discord.Interaction):
            if interaction.user != orig_user:
                return

            self.choice = interaction.data["custom_id"]
            self.stop()

        for choice in choices:
            button = discord.ui.Button(label = choice, custom_id = choice)
            button.callback = callback
            self.add_item(button)

class HelpView(discord.ui.View):
    def __init__(self, client: Cade, ctx: commands.Context):
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

        embed = BaseEmbed(
            title = f"{cog} Commands",
            description = command_list
        )

        await interaction.message.edit(embed = embed, view = self)

class ReplyView(discord.ui.View):
    def __init__(self, api: tweepy.API, reply_id: int):
        super().__init__(timeout = None)
        self.reply_id = reply_id
        self.api = api

    @discord.ui.button(label = "Reply", style = discord.ButtonStyle.primary, custom_id = "rv:reply")
    async def reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChoiceView(interaction.user, ["cancel"])
        await interaction.response.send_message("send a message to use as the reply", view = view, ephemeral = True)

        # get user input
        finished, message = await wait_until_button(interaction, view)

        if finished:
            # if cancel button was pressed, exit
            return await interaction.edit_original_response(content = "(canceled)", view = None)

        if not message:
            # error if no message or button press (just in case)
            return await interaction.edit_original_response(content = err.UNEXPECTED, view = None)

        await message.delete()
        status = message.content

        # same procedure as a reply command
        media = await get_tweet_attachments(interaction)
        media_ids = get_media_ids(self.api, *media)

        # send the reply
        new_status = self.api.update_status(
            status = status,
            media_ids = media_ids,
            in_reply_to_status_id = self.reply_id,
            auto_populate_reply_metadata = True
        )

        await interaction.edit_original_response(content = f"{bot.OK} replied", view = None)

        # reply to the original message containing the tweet
        await interaction.message.reply(
            f"{interaction.user.mention} replied with {get_twt_url(self.api.me().screen_name, new_status.id)}",
            view = ReplyView(self.api, new_status.id)
        )

class PlaylistView(discord.ui.View):
    def __init__(self, client: Cade, ctx: commands.Context, playlist: str):
        super().__init__(timeout = None)

        self.client = client
        self.playlist = playlist
        self.db = GuildDB(ctx.guild)

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

        embed = BaseEmbed(title = self.playlist)

        if not self.playlist_exists:
            embed.description = "(this playlist is empty)"
        else:
            # generate list of tracks
            tracks = []

            for i, track_entry in enumerate(self.guild_playlists[self.playlist]):
                track, user_id = track_entry
                track_title = track["info"]["title"]
                track_url = track["info"]["uri"]

                tracks.append(f"**{i + 1}. [{track_title}]({track_url})** - <@{user_id}>")

            embed.description = "\n".join(tracks)

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
        view = ChoiceView(interaction.user, ["done"])

        prompt = "send a youtube/spotify link or query for the track you want to add"
        await interaction.response.send_message(prompt, view = view, ephemeral = True)

        tracks_added = 0

        while True:
            finished, message = await wait_until_button(interaction, view)

            if finished:
                break

            if not message:
                # error if no message or button press (just in case)
                return await interaction.edit_original_response(content = err.UNEXPECTED, view = None)

            # search for track (thumbnail/title is not needed)
            tracks, *_ = await find_tracks(self.client, message.content, interaction.user.id)

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

        await interaction.edit_original_response(content = f"{bot.OK} added {tracks_added} track(s)", view = None)

    @discord.ui.button(label = "Play", style = discord.ButtonStyle.primary, custom_id = "pv:play")
    async def play_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.client.lavalink.create_player(interaction)

        # if bot not in vc, but:
        if not player.is_connected:
            if vc := interaction.user.voice:
                # user in vc -> join vc
                await vc.channel.connect(cls = LavalinkVoiceClient)
            else:
                # user not in vc -> error
                return await interaction.response.send_message(err.BOT_NOT_IN_VC, ephemeral = True)
        else:
            # if user not in bot vc -> error
            if interaction.user.voice.channel.id != player.channel_id:
                return await interaction.response.send_message(err.USER_NOT_IN_VC, ephemeral = True)

        tracks: list[AudioTrack] = []

        # underscore to ignore the user id stored with the track
        for (track, _) in self.guild_playlists[self.playlist]:
            # create an AudioTrack to pass into the player
            track = AudioTrack(track, interaction.user.id)
            player.add(track, interaction.user.id)

            tracks.append(track)

        info = QueryInfo(title = self.playlist)

        if len(tracks) > 1:
            info.thumbnail = None
            info.url = None
        else:
            info.thumbnail = get_yt_thumbnail(tracks[0].identifier)
            info.url = tracks[0].uri

        embed = create_music_embed(tracks, info, player, interaction.user)

        await interaction.response.send_message(embed = embed)
        await player.play(no_replace = True)

    @discord.ui.button(label = "-", style = discord.ButtonStyle.danger, custom_id = "pv:del")
    async def del_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChoiceView(interaction.user, ["done"])

        prompt = "send the number of the track you want to remove"
        await interaction.response.send_message(prompt, view = view, ephemeral = True)

        tracks_removed = 0

        while True:
            finished, message = await wait_until_button(interaction, view)

            if finished:
                break

            if not message:
                # error if no message or button press (just in case)
                return await interaction.edit_original_response(content = err.UNEXPECTED, view = None)

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

            self.guild_playlists = (await self.db.get()).playlists

            if not self.playlist_exists:
                # remove playlist if it's empty
                await self.db.del_obj("playlists", self.playlist)

            track_title = track_entry[0]["info"]["title"]

            await interaction.edit_original_response(content = f"{prompt}\n - Removed **{track_title}**")
            await interaction.message.edit(embed = await self.get_track_embed(), view = self.updated_view)

        await interaction.edit_original_response(
            content = f"{bot.OK} removed {tracks_removed} track(s)",
            view = None
        )

class TrackSelectView(discord.ui.View):
    def __init__(self, ctx: commands.Context, tracks: list[AudioTrack]):
        super().__init__(timeout = None)

        self.ctx = ctx
        self.tracks = tracks

        self.track = tracks[0]
        self.info = QueryInfo(
            get_yt_thumbnail(self.track.identifier),
            self.track.title,
            self.track.uri
        )

        self.set_buttons()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user == self.ctx.author

    @property
    def track_embed(self):
        embed = BaseEmbed(
            title = self.info.title,
            url = self.info.url,
            description = f"Author: **{self.track.author}** | Duration: `{format_time(ms = self.track.duration)}`"
        )

        embed.set_author(name = f"Result {self.tracks.index(self.track) + 1} out of {len(self.tracks)}")
        embed.set_thumbnail(url = self.info.thumbnail)

        return embed

    def set_buttons(self):
        # disable "back" button if on the first track, and "back" button if last track is reached
        self.children[1].disabled = (self.tracks[0] == self.track)
        self.children[2].disabled = (self.tracks[-1] == self.track)

        return self

    async def refresh_msg(self, interaction: discord.Interaction):
        self.info.thumbnail = get_yt_thumbnail(self.track.identifier)
        self.info.title = self.track.title
        self.info.url = self.track.uri

        await interaction.response.defer()
        await interaction.message.edit(embed = self.track_embed, view = self.set_buttons())

    @discord.ui.button(label = "nvm", style = discord.ButtonStyle.secondary, custom_id = "ts:cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = None
        self.stop()

    @discord.ui.button(label = "back", style = discord.ButtonStyle.secondary, custom_id = "ts:back")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = self.tracks[self.tracks.index(self.track) - 1]
        await self.refresh_msg(interaction)

    @discord.ui.button(label = "next", style = discord.ButtonStyle.secondary, custom_id = "ts:next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.track = self.tracks[self.tracks.index(self.track) + 1]
        await self.refresh_msg(interaction)

    @discord.ui.button(label = "this one", style = discord.ButtonStyle.primary, custom_id = "ts:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

        # self.track/self.extra is now the selected track
        self.stop()

class NowPlayingView(discord.ui.View):
    def __init__(self, ctx: commands.Context, player: DefaultPlayer):
        super().__init__(timeout = None)

        self.id = f"{ctx.guild.id}:{player.current.identifier}"
        self.player = player
        self.ctx = ctx

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

        self.message = interaction.message
        self.embed = self.message.embeds[0]

        return True

    @discord.ui.button(emoji = "⏩", custom_id = "np:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        # disable loop if looped
        self.player.set_loop(0)

        await self.message.edit(view = self.disable("skipped"))
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

        await self.message.edit(embed = self.embed, view = self)

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

        await self.message.edit(embed = self.embed, view = self)

async def wait_until_button(
    interaction: discord.Interaction,
    choice_view: ChoiceView
) -> tuple[bool, Union[str, discord.Message, None]]:
    button_id = choice_view.children[0].custom_id

    done, _ = await asyncio.wait([
        interaction.client.loop.create_task(
            interaction.client.wait_for("message", check = check(interaction))
        ),
        interaction.client.loop.create_task(
            interaction.client.wait_for("interaction", check = btn_check(interaction, button_id))
        )
    ], return_when = "FIRST_COMPLETED")

    response = [future.result() for future in done][-1]

    if type(response) is discord.interactions.Interaction and type(choice_view.choice) is str:
        return True, response.data["custom_id"]  # if a button press was received
    elif type(response) is discord.Message:
        return False, response  # if a message was received instead
    else:
        return False, None
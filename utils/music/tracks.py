import discord
from discord.ext import commands

from lavalink import (
    DeferredAudioTrack,
    DefaultPlayer,
    LoadResult,
    AudioTrack,
    LoadError,
    LoadType,
    Client,
    Node
)

from utils.functions import format_time, get_yt_thumbnail
from utils.dataclasses import colors, reg
from utils.clients import SpotifyClient
from utils.views import TrackSelectView

from async_spotify.spotify_errors import SpotifyAPIError
from typing import Union

class DeferredSpotifyTrack(DeferredAudioTrack):
    """Saves information about a spotify track and searches for it when loaded"""
    async def load(self, lavalink: Client):
        result: LoadResult = await lavalink.get_tracks(f"ytsearch:{self.author} - {self.title}")

        if result.load_type != LoadType.SEARCH or not result.tracks:
            raise LoadError

        track = result.tracks[0]

        # set displayed track as the one from youtube
        self.identifier = track.identifier
        self.title = track.title

        self.track = track.track
        return self.track

def _build_spotify_track(track: dict, requester_id: int) -> DeferredSpotifyTrack:
    """Creates a DefferedSpotifyTrack with information from the spotify api"""
    return DeferredSpotifyTrack(
        data = {
            'identifier': track['id'],
            'isSeekable': True,
            'author': track['artists'][0]['name'],
            'length': track['duration_ms'],
            'isStream': False,
            'title': track['name'],
            'uri': (
                track['external_urls']['spotify'] if 'spotify' in track['external_urls'] else
                f"https://open.spotify.com/track/{track['id']}"
            )
        },
        requester = requester_id
    )

async def find_tracks(node: Node, query: str, requester_id: int, return_all: bool = False):
    """Gets tracks and playlist info from either youtube or spotify"""
    if match := reg.spotify.search(query):
        tracks, extra = await get_spotify(node, *match.groups(), requester_id)
    else:
        tracks, extra = await get_youtube(node, query, return_all)

    return tracks, extra

async def select_tracks(ctx: commands.Context, tracks: list[AudioTrack, DeferredAudioTrack]):
    """Creates a view where someone can select a track from youtube results"""
    view = TrackSelectView(ctx, tracks)

    selection = await ctx.send(embed = view.track_embed, view = view)
    await view.wait()

    thumbnail = None
    title = None

    track: AudioTrack = view.track
    # track will still be None if nothing was selected

    if track:
        thumbnail = get_yt_thumbnail(track.identifier)
        title = track.title

    await selection.delete()
    
    return track, (thumbnail, title)

def create_music_embed(query: str, tracks: list[AudioTrack], extra: tuple, player: DefaultPlayer, requester: discord.Member): 
    """Creates the embed for queued tracks or playlists"""
    thumbnail, title = extra
    embed = discord.Embed(color = colors.ADDED_TRACK)

    embed.title = title
    embed.set_thumbnail(url = thumbnail)

    if len(tracks) > 1:
        # infer that it is a playlist if there is more than one track
        embed.set_author(name = f"Queued Playlist - {len(tracks)} track(s)", icon_url = requester.display_avatar)

        embed.url = reg.url.search(query).group(0)
        duration = sum([track.duration for track in tracks])
    else:
        # infer that the track is being queued
        track = tracks[0]

        embed.set_author(name = f"Queued Track - #{len(player.queue)}", icon_url = requester.display_avatar)

        embed.url = track.uri
        duration = track.duration

    embed.description = f"Added by {requester.mention} | Duration: `{format_time(duration // 1000)}`"

    return embed

async def get_youtube(node: Node, query: str, return_all: bool = False):
    """Gets tracks from youtube"""
    query = query if reg.youtube.match(query) else f"ytsearch:{query}"

    result: LoadResult = await node.get_tracks(query)

    tracks: list[AudioTrack] = result.tracks
    thumbnail = None
    title = None
    
    # load track(s) if it got any results, else leave everything as None
    if result.load_type not in (LoadType.NO_MATCHES, LoadType.LOAD_FAILED):
        if result.load_type is LoadType.PLAYLIST:
            title = result.playlist_info.name
        else:
            title = tracks[0].title

            if not return_all:
                tracks = [tracks[0]]
    
        thumbnail = get_yt_thumbnail(tracks[0].identifier)

    return tracks, (thumbnail, title)

async def get_spotify(node: Node, type: str, id: str, requester_id: int):
    """Gets tracks from spotify"""
    tracks: list[Union[DeferredSpotifyTrack, AudioTrack]] = []
    thumbnail: str = None
    title: str = None

    if type in ("album", "playlist"):
        # albums and playlists have different methods
        try:
            async with SpotifyClient() as spotify_api:
                spotify_info = (
                    await spotify_api.albums.get_one(id) if type == "album" else
                    await spotify_api.playlists.get_one(id)
                )
        except SpotifyAPIError:
            # same as returning nothing
            return tracks, (thumbnail, title)

        items = spotify_info['tracks']['items']

        tracks = [
            _build_spotify_track(
                item['track'] if 'track' in item else item, requester_id
            ) for item in items
        ]

        thumbnail = spotify_info["images"][0]["url"]
        title = spotify_info["name"]
    else:
        # same logic as playlists/albums but searches youtube instead of deferring 
        try:
            async with SpotifyClient() as spotify_api:
                spotify_info = await spotify_api.track.get_one(id)
        except SpotifyAPIError:
            return tracks, (thumbnail, title)

        title = spotify_info["name"]
        author = spotify_info["artists"][0]["name"]

        result: LoadResult = await node.get_tracks(f"ytsearch:{author} - {title}")

        if result.load_type not in (LoadType.NO_MATCHES, LoadType.LOAD_FAILED):
            tracks = [result.tracks[0]]

            thumbnail = get_yt_thumbnail(tracks[0].identifier)
            title = tracks[0].title
    
    return tracks, (thumbnail, title)

async def get_queue(player: DefaultPlayer):
    """Generates the queue list"""
    total_items = len(player.queue)
    total_pages = int(total_items / 10) + (total_items % 10 > 0)

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
            color = discord.Color.embed_background()
        )
        
        # add page counter to footer if there's more than one page
        page_count = f"page {current_page} out of {total_pages}" if total_pages > 1 else ''

        embed.set_footer(text = page_count)
        pages.append(embed)

        current_page += 1
    
    return pages
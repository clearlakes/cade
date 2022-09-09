import discord
from discord.ext import menus

from lavalink import (
    DeferredAudioTrack,
    DefaultPlayer,
    LoadResult,
    AudioTrack,
    LoadError,
    LoadType,
    Client,
)
from utils.useful import format_time, get_yt_thumbnail
from utils.data import colors, reg
from utils.base import BaseEmbed
from utils.main import Cade

from async_spotify.spotify_errors import SpotifyAPIError
from dataclasses import dataclass
from typing import Union

@dataclass
class QueryInfo:
    thumbnail: str = None
    title: str = None
    url: str = None

    def __iter__(self):
        return iter((self.thumbnail, self.title, self.url))

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
            "identifier": track["id"],
            "isSeekable": True,
            "author": track["artists"][0]["name"],
            "length": track["duration_ms"],
            "isStream": False,
            "title": track["name"],
            "uri": (
                track["external_urls"]["spotify"] if "spotify" in track["external_urls"] else
                f"https://open.spotify.com/track/{track['id']}"
            )
        },
        requester = requester_id
    )

async def find_tracks(
    client: Cade,
    query: str,
    requester_id: int,
    return_all: bool = False
) -> tuple[
    list[Union[AudioTrack, DeferredSpotifyTrack]],
    QueryInfo,
    bool
]:
    """Gets tracks and playlist info from either youtube or spotify"""
    if (match := reg.spotify.match(query)) and client.spotify_api:
        tracks, info, failed = await get_spotify(client, *match.groups(), requester_id)
    else:
        tracks, info, failed = await get_youtube(client, query, return_all)

    return tracks, info, failed

async def get_youtube(client: Cade, query: str, return_all: bool = False):
    """Gets tracks from youtube"""
    if match := reg.youtube.match(query):
        if match.group(1) != "playlist":
            # strip extra stuff in link just in case
            query = f"https://youtube.com/watch?v={match.group(2)}"
    elif not reg.url.match(query):
        query = f"ytsearch:{query}"

    result: LoadResult = await client.lavalink.get_tracks(query)

    tracks: list[AudioTrack] = result.tracks
    info = QueryInfo()

    # load track(s) if it got any results, else leave everything as None
    if result.load_type not in (LoadType.NO_MATCHES, LoadType.LOAD_FAILED):
        if result.load_type is LoadType.PLAYLIST:
            info.title = result.playlist_info.name
            info.url = query
        else:
            info.title = tracks[0].title
            info.url = tracks[0].uri

            if not return_all:
                tracks = [tracks[0]]

        info.thumbnail = get_yt_thumbnail(tracks[0].identifier)

    failed = result.load_type is LoadType.LOAD_FAILED

    return tracks, info, failed

async def get_spotify(client: Cade, url_type: str, url_id: str, requester_id: int):
    """Gets tracks from spotify"""
    tracks: list[Union[DeferredSpotifyTrack, AudioTrack]] = []
    info = QueryInfo()

    failed = False

    if url_type in ("album", "playlist"):
        # albums and playlists have different methods
        try:
            spotify_info = (
                await client.spotify_api.albums.get_one(url_id) if url_type == "album" else
                await client.spotify_api.playlists.get_one(url_id)
            )
        except SpotifyAPIError:
            # same as returning nothing
            return tracks, info, failed

        items = spotify_info["tracks"]["items"]

        tracks = [
            _build_spotify_track(
                item["track"] if "track" in item else item, requester_id
            ) for item in items
        ]

        info.thumbnail = spotify_info["images"][0]["url"]
        info.title = spotify_info["name"]
        info.url = spotify_info["external_urls"]["spotify"]
    else:
        # same logic as playlists/albums but searches youtube instead of deferring
        try:
            spotify_info = await client.spotify_api.track.get_one(url_id)
        except SpotifyAPIError:
            return tracks, info, failed

        title = spotify_info["name"]
        author = spotify_info["artists"][0]["name"]

        result: LoadResult = await client.lavalink.get_tracks(f"ytsearch:{author} - {title}")

        if result.load_type not in (LoadType.NO_MATCHES, LoadType.LOAD_FAILED):
            tracks = [result.tracks[0]]

            info.thumbnail = get_yt_thumbnail(tracks[0].identifier)
            info.title = tracks[0].title
            info.url = tracks[0].uri

        failed = result.load_type is LoadType.LOAD_FAILED

    return tracks, info, failed

def create_music_embed(tracks: list[AudioTrack], info: QueryInfo, player: DefaultPlayer, requester: discord.Member):
    """Creates the embed for queued tracks or playlists"""
    embed = discord.Embed(color = colors.ADDED_TRACK)
    thumbnail, title, url = info

    embed.set_thumbnail(url = thumbnail)
    embed.title = title
    embed.url = url

    if len(tracks) > 1:
        # infer that it is a playlist if there is more than one track
        embed.set_author(name = f"Queued Playlist - {len(tracks)} track(s)", icon_url = requester.display_avatar)
        duration = sum([track.duration for track in tracks])
    else:
        # infer that the track is being queued
        embed.set_author(name = f"Queued Track - #{len(player.queue)}", icon_url = requester.display_avatar)
        duration = tracks[0].duration

    embed.description = f"Added by {requester.mention} | Duration: `{format_time(ms = duration)}`"

    return embed

class QueuePages(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page = 1)

    async def format_page(self, _, entries):
        return entries

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

        queue_list = ""

        # get the information of each track in the queue starting from the current page
        for index, track in enumerate(player.queue[start:end], start = start):
            duration = format_time(ms = track.duration)
            requester = f"<@{track.requester}>"
            queue_list += f'**{index + 1}.** [**{track.title}**]({track.uri}) `{duration}` - {requester}\n'

        embed = BaseEmbed(
            title = f"Queue ({len(player.queue)} total)",
            description = queue_list
        )

        # add page counter to footer if there's more than one page
        page_count = f"page {current_page} out of {total_pages}" if total_pages > 1 else ""

        embed.set_footer(text = page_count)
        pages.append(embed)

        current_page += 1

    return QueuePages(pages)
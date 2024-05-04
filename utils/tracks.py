from dataclasses import dataclass

import discord
from async_spotify.spotify_errors import SpotifyAPIError
from discord.ext import commands, menus
from lavalink import (
    AudioTrack,
    Client,
    DefaultPlayer,
    DeferredAudioTrack,
    LoadError,
    LoadResult,
    LoadType,
)

from .base import BaseEmbed
from .useful import format_time, get_yt_thumbnail, strip_pl_name
from .vars import colors, reg


@dataclass
class QueryInfo:
    thumbnail: str = None
    title: str = None
    url: str = None

    def __iter__(self):
        return iter((self.thumbnail, self.title, self.url))


class DeferredSpotifyTrack(DeferredAudioTrack):
    """saves information about a spotify track and searches for it when loaded"""

    async def load(self, lavalink: Client):
        result: LoadResult = await lavalink.get_tracks(
            f"ytsearch:{self.author} - {self.title}"
        )

        if result.load_type != LoadType.SEARCH or not result.tracks:
            raise LoadError

        track = result.tracks[0]

        # set displayed track as the one from youtube
        self.identifier = track.identifier
        self.title = track.title

        self.track = track.track
        return self.track


def _build_spotify_track(track: dict, requester_id: int) -> DeferredSpotifyTrack:
    """creates a DefferedSpotifyTrack with information from the spotify api"""
    return DeferredSpotifyTrack(
        data={
            "identifier": track["id"],
            "isSeekable": True,
            "author": track["artists"][0]["name"],
            "length": track["duration_ms"],
            "isStream": False,
            "title": track["name"],
            "uri": (
                track["external_urls"]["spotify"]
                if "spotify" in track["external_urls"]
                else f"https://open.spotify.com/track/{track['id']}"
            ),
        },
        requester=requester_id,
    )


async def find_tracks(
    client: commands.Bot, query: str, requester_id: int, return_all: bool = False
) -> tuple[list[AudioTrack | DeferredSpotifyTrack], QueryInfo, bool]:
    """gets tracks and playlist info from either youtube or spotify"""
    if (match := reg.SPOTIFY.match(query)) and client.spotify_api:
        tracks, info, failed = await get_spotify(client, *match.groups(), requester_id)
    else:
        tracks, info, failed = await get_youtube(client, query, return_all)

    return tracks, info, failed


async def get_youtube(client: commands.Bot, query: str, return_all: bool = False):
    """gets tracks from youtube"""
    playlist_name = None

    if (match := reg.YOUTUBE.match(query)) and match.group(1) != "playlist":
        query = f"https://youtube.com/watch?v={match.group(2)}"
    elif not reg.URL.match(query):
        query = f"ytsearch:{query}"

    result: LoadResult = await client.lavalink.get_tracks(query)

    tracks: list[AudioTrack] = result.tracks
    info = QueryInfo()

    # load track(s) if it got any results, else leave everything as None
    if result.load_type not in (LoadType.EMPTY, LoadType.ERROR):
        if result.load_type is LoadType.PLAYLIST:
            info.title = playlist_name = result.playlist_info.name
            info.url = query
        else:
            info.title = tracks[0].title
            info.url = tracks[0].uri

            if not return_all:
                tracks = [tracks[0]]

        info.thumbnail = get_yt_thumbnail(tracks[0].identifier)

    failed = result.load_type is LoadType.ERROR

    for track in tracks:
        track.extra["pl_name"] = playlist_name

    return tracks, info, failed


async def get_spotify(
    client: commands.Bot, url_type: str, url_id: str, requester_id: int
):
    """gets tracks from spotify"""
    tracks: list[DeferredSpotifyTrack | AudioTrack] = []
    info = QueryInfo()

    playlist_name = None
    failed = False

    if url_type in ("album", "playlist"):
        # albums and playlists have different methods
        try:
            spotify_info = (
                await client.spotify_api.albums.get_one(url_id)
                if url_type == "album"
                else await client.spotify_api.playlists.get_one(url_id)
            )
        except SpotifyAPIError:
            # same as returning nothing
            return tracks, info, failed

        items = spotify_info["tracks"]["items"]

        tracks = [
            _build_spotify_track(
                item["track"] if "track" in item else item, requester_id
            )
            for item in items
        ]

        info.thumbnail = spotify_info["images"][0]["url"]
        info.title = playlist_name = spotify_info["name"]
        info.url = spotify_info["external_urls"]["spotify"]
    else:
        # same logic as playlists/albums but searches youtube instead of deferring
        try:
            spotify_info = await client.spotify_api.track.get_one(url_id)
        except SpotifyAPIError:
            return tracks, info, failed

        title = spotify_info["name"]
        author = spotify_info["artists"][0]["name"]

        result: LoadResult = await client.lavalink.get_tracks(
            f"ytsearch:{author} - {title}"
        )

        if result.load_type not in (LoadType.NO_MATCHES, LoadType.LOAD_FAILED):
            tracks = [result.tracks[0]]

            info.thumbnail = get_yt_thumbnail(tracks[0].identifier)
            info.title = tracks[0].title
            info.url = tracks[0].uri

        failed = result.load_type is LoadType.LOAD_FAILED

    for track in tracks:
        track.extra["pl_name"] = playlist_name

    return tracks, info, failed


def create_music_embed(
    tracks: list[AudioTrack],
    info: QueryInfo,
    player: DefaultPlayer,
    requester: discord.Member,
):
    """creates the embed for queued tracks or playlists"""
    duration = format_time(ms=sum([track.duration for track in tracks]))
    thumbnail, title, url = info

    embed = discord.Embed(
        description=f"**[{title}]({url})**", color=colors.QUEUED_TRACK
    )

    if len(tracks) > 1:  # more than 1 track means playlist
        embed.set_author(name="Queued Playlist", icon_url=requester.display_avatar)
        embed.description += (
            f" - `{len(tracks)} tracks`\n`{duration}` • {requester.mention} | "
        )
        embed.description += f"**#{len(player.queue) - len(tracks) + 1} to #{len(player.queue)}** in queue"
    else:
        embed.set_author(name="Queued Track", icon_url=requester.display_avatar)
        embed.description += (
            f"\n`{duration}` • {requester.mention} | **#{len(player.queue)}** in queue"
        )

    embed.set_thumbnail(url=thumbnail)

    return embed


class QueuePages(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, _, entries):
        return entries


async def get_queue(player: DefaultPlayer):
    """generates the queue list"""
    total_items = len(player.queue)
    total_pages = int(total_items / 10) + (total_items % 10 > 0)
    pages = []

    # generate queue pages
    while (current_page := (len(pages) + 1)) <= total_pages:
        start = (current_page - 1) * 10
        end = start + 10

        queue_list = ""
        current_playlist = None

        # get the information of each track in the queue starting from the current page
        for index, track in enumerate(player.queue[start:end], start=start):
            if pl := track.extra["pl_name"]:
                if pl == current_playlist:  # already a part of the playlist
                    queue_list += "`|` "
                else:  # start of a new playlist
                    queue_list += f"**`{pl}`** • <@{track.requester}>\n`|` "
                    current_playlist = pl

                title = strip_pl_name(pl, track.title)
            else:
                if current_playlist:  # add separator if there was a playlist
                    queue_list += "`" + ("─" * len(current_playlist)) + "`\n"

                current_playlist = None
                title = track.title

            duration = format_time(ms=track.duration)
            queue_list += f"**{index + 1}. [{title}]({track.uri})** `{duration}`"

            if not current_playlist:
                queue_list += f" • <@{track.requester}>"

            queue_list += "\n"

        if (
            current_page < total_pages
            and player.queue[current_page * 10].extra["pl_name"] == current_playlist
        ):
            queue_list += (
                "`...`"  # show that there are more tracks from the same playlist
            )
        elif current_playlist:
            queue_list += (
                "`" + ("─" * len(current_playlist)) + "`\n"
            )  # add separator on last page

        embed = BaseEmbed(title="Queue", description=queue_list.strip())
        embed.set_footer(
            text=f"{len(player.queue)} tracks • page {current_page}/{total_pages}"
        )

        pages.append(embed)

    return QueuePages(pages)

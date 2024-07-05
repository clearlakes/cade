from dataclasses import dataclass
from aiohttp import ClientSession

import discord
from lavalink import (
    AudioTrack,
    DefaultPlayer,
    LoadResult,
    LoadType,
)

from .base import BaseEmbed, CadeElegy
from .useful import (
    format_time,
    strip_pl_name,
    Pages,
    get_average_color,
    read_from_url,
    get_artwork_url,
)
from .vars import colors, reg
from .keys import LavalinkKeys

import math


@dataclass
class QueryInfo:
    thumbnail: str = None
    title: str = None
    url: str = None

    def __iter__(self):
        return iter((self.thumbnail, self.title, self.url))


async def get_youtube(client: CadeElegy, query: str, return_all: bool = False):
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

        info.thumbnail = tracks[0].artwork_url

    failed = result.load_type is LoadType.ERROR

    for track in tracks:
        track.extra["pl_name"] = playlist_name

    return tracks, info, failed


async def _get_lyrics(track: AudioTrack):
    ll_keys = LavalinkKeys()

    async with ClientSession(headers={"Authorization": ll_keys.secret}) as session:
        async with session.get(
            f"http://localhost:{ll_keys.port}/v4/lyrics?track={track.raw['encoded']}"
        ) as resp:
            status = resp.status
            resp = await resp.json()

    return status, resp


async def get_np_lyrics(player: DefaultPlayer):
    track = player.current
    status, resp = await _get_lyrics(track)

    if status != 200:
        return

    lyrics = [unit["line"] for unit in resp["lines"]]
    embeds: list[BaseEmbed] = []

    total_pages = int(math.ceil(len(lyrics) / 25))

    for i, line in enumerate(lyrics):
        if i % 24 == 0:
            yt_image_bytes = (await read_from_url(get_artwork_url(track)))[1]
            average_color = get_average_color(yt_image_bytes)

            new_embed = BaseEmbed(
                title=track.title,
                description="",
                color=discord.Color.from_rgb(*average_color),
            )
            new_embed.set_footer(
                text=f"({math.ceil((i + 1) / 24)} / {total_pages}) • from {resp['sourceName']}"
            )
            embeds.append(new_embed)

        embeds[-1].description += f"{line}\n"

    return Pages(embeds)


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

    return Pages(pages)

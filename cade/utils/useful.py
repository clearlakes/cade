import asyncio
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from os.path import splitext
from shlex import split
from subprocess import PIPE, Popen
from time import gmtime, strftime
import sys

import aiohttp
import discord
import numpy as np
from discord.ext import commands, menus
from PIL import Image

from .base import CadeElegy
from .db import GuildDB
from .ext import serve_very_big_file
from .keys import Keys
from .vars import v

from lavalink import AudioTrack


@dataclass
class AttObj:
    filebyte: BytesIO
    filename: str
    filetype: str


class Pages(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, _, entries):
        return entries


def get_media_kind(mime: str):
    match mime.split("/"):
        case ["image", "gif" | "apng"]:
            return "gif"
        case ["image", _]:
            return "image"
        case ["video", _]:
            return "video"


async def read_from_url(url: str):
    r_bytes: bytes = None
    r_json: dict = {}

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            if get_media_kind(r.content_type) in ["image", "gif", "video"]:
                r_bytes = await r.read()
            else:
                try:
                    r_json = await r.json()
                except aiohttp.ContentTypeError:
                    r_json = {"text": await r.text()}

            return r, r_bytes, r_json


async def _link_bytes(
    link: str, media_types: list[str]
) -> tuple[AttObj | None, str | None]:
    """reads media from the url as bytes"""
    if res := v.RE__TENOR.search(link):
        if not Keys.tenor:
            return None, v.ERR__UNSUPPORTED_URL

        # get direct gif link through tenor's api
        try:
            link = (
                await read_from_url(
                    f"https://tenor.googleapis.com/v2/posts?key={Keys.tenor}&client_key=cade&ids={res.group(1)}"
                )
            )[2]["results"][0]["media_formats"]["gif"]["url"]
        except IndexError:
            return None, v.ERR__INVALID_URL
    elif res := v.RE__GYAZO.search(link):
        if not Keys.gyazo:
            return None, v.ERR__UNSUPPORTED_URL

        # get direct gif link through gyazo's api
        try:
            link = (
                await read_from_url(
                    f"https://api.gyazo.com/api/images/{res.group(1)}?access_token={Keys.gyazo}"
                )
            )[2]["url"]
        except IndexError:
            return None, v.ERR__INVALID_URL
    elif res := v.RE__DISCORD.match(link) and Keys.image.cdn:
        link = f"{Keys.image.cdn}/{link}"

    # try reading bytes from the link
    r, r_bytes, r_json = await read_from_url(link)

    if r_json and r_json["text"] == "This content is no longer available.":
        return None, v.ERR__CDN_EXPIRED

    if get_media_kind(r.content_type) in media_types:
        return AttObj(BytesIO(r_bytes), "url", r.content_type), None
    else:
        return None, v.ERR__WRONG_ATT_TYPE


async def get_media(
    ctx: commands.Context, media_types: list[str]
) -> tuple[AttObj | None, str | None]:
    """main function for getting attachments from either messages, replies, or previous messages"""
    att_obj = None
    error = None

    match bool(ctx.message.attachments), bool(ctx.message.reference):
        case True, False:
            msg = ctx.message  # use first message if it has an attachment
        case False, True:
            msg = ctx.message.reference.resolved  # use reference if there is one
        case _:
            # index 0: bot msg -> 1: invoke msg -> 2: msg with link or image
            msg = [message async for message in ctx.channel.history(limit=3)][
                2
            ]  # use previous message

    if msg.attachments:  # if attachment was found
        att = msg.attachments[0]

        if get_media_kind(att.content_type) in media_types:
            att_obj = AttObj(
                BytesIO(await att.read()), splitext(att.filename)[0], att.content_type
            )
        else:
            error = v.ERR__WRONG_ATT_TYPE
    elif match := v.RE__URL.search(msg.content):  # if link was found
        link = match.group(0)

        if link.startswith((Keys.image.domain, *v.BOT__SUPPORTED_SITES)):
            att_obj, error = await _link_bytes(link, media_types)
        else:
            error = v.ERR__UNSUPPORTED_URL
    else:  # if nothing was found
        error = v.ERR__NO_ATT_OR_URL_FOUND

        if "//imgur.com" in msg.content:
            error += ' (imgur links need to start with "i.")'

    return att_obj, error


def check(ctx: commands.Context | discord.Interaction):
    """checks if a message is sent by the command sender"""

    def check_inner(message: discord.Message):
        # get author from either interaction or context
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user

        # check if the message if from the original author and channel
        return message.author == author and message.channel == ctx.channel

    return check_inner


def btn_check(ctx: discord.Interaction, button_id: str):
    """checks if a button is pressed by the command sender"""

    def btn_check_inner(interaction: discord.Interaction):
        return (  # check if:
            interaction.type == discord.InteractionType.component
            and interaction.data["custom_id"] == button_id  # a button was pressed
            and interaction.user == ctx.user  # its custom id matches button_id
            and interaction.channel  # it was from the original person
            == ctx.channel  # it was in the original channel
        )

    return btn_check_inner


def format_time(sec: int = 0, ms: int = 0):
    """formats the given duration (in seconds/milliseconds) into either M:S or H:M:S"""
    # convert milliseconds to seconds
    sec = ms // v.MATH__MS_MULTIPLIER if ms else sec

    # check if the duration is an hour or more (and switch formats)
    hours = sec // 3600
    format = "%-H:%M:%S" if hours else "%-M:%S"

    return strftime(format, gmtime(sec))


def get_average_color(image: bytes):
    """gets the average color of an image (from bytes)"""
    pil_img = Image.open(BytesIO(image))
    np_img = np.array(pil_img)

    average_color = [round(x) for x in np_img.mean(axis=0).mean(axis=0)]
    return average_color


def strip_pl_name(playlist_name: str, text: str):
    """strips the playlist name from track titles"""
    track_name = t.group(0) if (t := v.RE__TRACKNAME.search(text)) else text
    playlist_name = playlist_name.lower()

    if any(
        (short_title := x).lower().strip(" ost") not in playlist_name
        for x in v.RE__PLAYLIST.split(track_name, 1)
    ):
        return text.replace(track_name, short_title.strip())

    return text


def get_attachment_obj(ctx: commands.Context):
    """gets the attachment object from a message"""
    # switch to the message being replied to if it's there
    msg = (
        ctx.message.reference.resolved
        if ctx.message.reference and not ctx.message.attachments
        else ctx.message
    )

    if not msg.attachments:
        return

    return msg.attachments[0]


def get_artwork_url(track: AudioTrack):
    """gets a link to the thumbnail of the track"""
    return track.raw["albumArtUrl"] if not track.artwork_url else track.artwork_url


def run_async(func):
    async def wrapper(*args, **kwargs):
        """runs blocking functions in async"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    return wrapper


@run_async
def run_cmd(
    cmd: str, b1: bytes = None, decode: bool = False
) -> tuple[str | bytes, int]:
    """executes ffmpeg/git commands and returns the output"""
    p = Popen(split(cmd), stdin=PIPE, stdout=PIPE)
    result: bytes = p.communicate(input=b1)[0]

    if decode:
        result = result.decode("utf-8").strip("\n")

    return result, p.returncode


async def send_media(
    ctx: commands.Context, orig_msg: discord.Message, media: tuple[BytesIO, str, str]
):
    """sends the given media to discord or the image server depending on its size"""
    await orig_msg.edit(content=f"-# {v.EMJ__WAITING} sending...")

    if not media[0]:  # if the edited file is missing (could not be made)
        await orig_msg.edit(content=v.ERR__MEDIA_EDIT_ERROR)
        return
    elif (sys.getsizeof(media[0]) / v.DISCORD__MAX_FILESIZE_BYTES) >= v.DISCORD__MAX_FILESIZE_MB:
        if Keys.image.domain:
            url = await serve_very_big_file(ctx.guild.id, media)
            await ctx.reply(f"-# uploaded to {Keys.image.domain.replace('https://', '')} (larger than 10 mb), deletes in 24 hrs!!\n{url}")
        else:
            await orig_msg.edit(content=v.ERR__FILE_TOO_BIG)
            return

    try:
        await ctx.reply(file=discord.File(*media[:2]), mention_author=False)
    except discord.HTTPException:
        await orig_msg.edit(content=v.ERR__CANT_SEND_FILE)
        return

    await orig_msg.delete()


async def get_prefix(client: CadeElegy, message: discord.Message):
    # use custom prefix if there is one
    prefix = (await GuildDB(message.guild).get()).prefix
    return commands.when_mentioned_or(prefix)(client, message)

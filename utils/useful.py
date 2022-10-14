import discord
from discord.ext import commands

from utils.ext import serve_very_big_file
from utils.data import bot, reg, err, ff
from utils.base import BaseEmbed
from utils.clients import Keys

from tempfile import TemporaryDirectory, NamedTemporaryFile as create_temp
from subprocess import Popen, PIPE
from dataclasses import dataclass
from time import strftime, gmtime
from functools import partial
from os.path import splitext
from shlex import split
from io import BytesIO
from PIL import Image
import asyncio
import aiohttp
import tweepy

@dataclass
class AttObj:
    filebyte: BytesIO
    filename: str
    filetype: str

def get_media_kind(mime: str):
    match mime.split("/"):
        case ["image", "gif" | "apng"]:
            return "gif"
        case ["image", _]:
            return "image"
        case ["video", _]:
            return "video"

async def read_from_url(url: str, read_bytes: bool = False, read_json: bool = False):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            r_bytes: bytes = await r.read() if read_bytes else None
            r_json: dict = await r.json() if read_json else None

            return r, r_bytes, r_json

async def _link_bytes(link: str, media_types: list[str]) -> tuple[AttObj | None, str | None]:
    """Reads media from the url as bytes"""
    if res := reg.tenor.search(link):
        if not Keys.tenor:
            return None, err.UNSUPPORTED_URL

        # get direct gif link through tenor's api
        *_, res = await read_from_url(f"https://g.tenor.com/v1/gifs?ids={res.group(1)}&key={Keys.tenor}", read_json = True)

        try:
            link = res["results"][0]["media"][0]["gif"]["url"]
        except IndexError:
            return None, err.INVALID_URL

    elif res := reg.gyazo.search(link):
        if not Keys.gyazo:
            return None, err.UNSUPPORTED_URL

        # get direct gif link through gyazo's api
        *_, res = await read_from_url(f"https://api.gyazo.com/api/images/{res.group(1)}?access_token={Keys.gyazo}", read_json = True)

        try:
            link = res["url"]
        except IndexError:
            return None, err.INVALID_URL

    # try reading bytes from the link
    r, r_bytes, _ = await read_from_url(link, read_bytes = True)

    if get_media_kind(r.content_type) in media_types:
        return AttObj(BytesIO(r_bytes), "url", r.content_type), None
    else:
        return None, err.WRONG_ATT_TYPE

async def get_media(ctx: commands.Context, media_types: list[str]) -> tuple[AttObj | None, str | None]:
    """Main function for getting attachments from either messages, replies, or previous messages"""
    att_obj = None
    error = None

    match bool(ctx.message.attachments), bool(ctx.message.reference):
        case True, False:
            msg = ctx.message  # use first message if it has an attachment
        case False, True:
            msg = ctx.message.reference.resolved  # use reference if there is one
        case _:
            # index 0: bot msg -> 1: invoke msg -> 2: msg with link or image
            msg = [message async for message in ctx.channel.history(limit = 3)][2]  # use previous message

    if msg.attachments:  # if attachment was found
        att = msg.attachments[0]

        if get_media_kind(att.content_type) in media_types:
            att_obj = AttObj(BytesIO(await att.read()), splitext(att.filename)[0], att.content_type)
        else:
            error = err.WRONG_ATT_TYPE
    elif match := reg.url.search(msg.content):  # if link was found
        link = match.group(0)

        if link.startswith((Keys.image.domain, *bot.SUPPORTED_SITES)):
            att_obj, error = await _link_bytes(link, media_types)
        else:
            error = err.UNSUPPORTED_URL
    else:  # if nothing was found
        error = err.NO_ATT_OR_URL_FOUND

        if "//imgur.com" in msg.content:
            error += " (imgur links need to start with \"i.\")"

    return att_obj, error

def check(ctx: commands.Context | discord.Interaction):
    """Checks if a message is sent by the command sender"""
    def check_inner(message: discord.Message):
        # get author from either interaction or context
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user

        # check if the message if from the original author and channel
        return (message.author == author and message.channel == ctx.channel)

    return check_inner

def btn_check(ctx: discord.Interaction, button_id: str):
    """Checks if a button is pressed by the command sender"""
    def btn_check_inner(interaction: discord.Interaction):
        return (  # check if:
            interaction.type == discord.InteractionType.component and  # a button was pressed
            interaction.data["custom_id"] == button_id and  # its custom id matches button_id
            interaction.user == ctx.user and  # it was from the original person
            interaction.channel == ctx.channel  # it was in the original channel
        )

    return btn_check_inner

def format_time(sec: int = 0, ms: int = 0):
    """Formats the given duration (in seconds/milliseconds) into either M:S or H:M:S"""
    # convert milliseconds to seconds
    sec = ms // 1000 if ms else sec

    # check if the duration is an hour or more (and switch formats)
    hours = sec // 3600
    format = "%-H:%M:%S" if hours else "%-M:%S"

    return strftime(format, gmtime(sec))

async def get_tweet_attachments(ctx: commands.Context | discord.Interaction):
    """Gets the attachments to use for tweets"""
    # switch to the original message if it's a reply
    msg = ctx.message.reference.resolved if ctx.message.reference and not ctx.message.attachments else ctx.message

    media_type = None
    attachments = []

    for _, att in zip(range(4), msg.attachments):
        att_bytes = BytesIO(await att.read())

        if "image" in att.content_type:
            # if the content is animated, only one can be posted
            if att.content_type.split("/")[1] in ("gif", "apng"):
                media_type = "gif"
                attachments = [att_bytes]
                break

            media_type = "image"
            attachments.append(att_bytes)
            continue
        else:
            if att.filename.lower().endswith("mov"):
                att_bytes = await mov_to_mp4(att_bytes)

            if not att_bytes:
                media_type = None
                attachments.clear()

                if isinstance(ctx, commands.Context):
                    await ctx.send(err.MOV_TO_MP4_ERROR)
                else:
                    await ctx.edit_original_response(content = err.MOV_TO_MP4_ERROR)
            else:
                media_type = "video"
                attachments = [att_bytes]

            break

    return media_type, attachments

def get_attachment_obj(ctx: commands.Context):
    """Gets the attachment object from a message"""
    # switch to the message being replied to if it's there
    msg = ctx.message.reference.resolved if ctx.message.reference and not ctx.message.attachments else ctx.message

    if not msg.attachments:
        return

    return msg.attachments[0]

def get_media_ids(api: tweepy.API, media_type: str, attachments: list[BytesIO]):
    """Gets the media ids for content in tweets"""
    if not attachments:
        return  # in case get_attachment returns None

    media_ids = []

    # chooses between either uploading multiple images or just one video/gif
    if media_type == "image":
        for image in attachments:
            # create temporary file to store image data in
            with create_temp(suffix='.png') as temp:
                # convert image into png in case of filetype conflicts
                im = Image.open(image)
                im.convert("RGBA")
                im.save(temp.name, format='PNG')

                res = api.media_upload(temp.name)
                media_ids.append(res.media_id)
    else:
        # store media data in a temporary file
        with create_temp() as temp:
            temp.write(attachments[0].getvalue())
            res = api.chunked_upload(temp.name, media_category = f"tweet_{media_type}")
            media_ids.append(res.media_id)

    return media_ids

async def mov_to_mp4(file: BytesIO):
    """Converts mov files to mp4"""
    with TemporaryDirectory() as temp:
        with open(f"{temp}/input.mov", "wb") as input:
            input.write(file.getvalue())

        _, returncode = await run_cmd(ff.MOV_TO_MP4(temp))

        if returncode != 0:
            return

        with open(f"{temp}/output.mp4", "rb") as output:
            result = BytesIO(output.read())

        return result

def get_yt_thumbnail(identifier: str):
    """Gets a link to the thumbnail of the youtube video"""
    return f"https://img.youtube.com/vi/{identifier}/0.jpg"

def get_twt_url(handle: str, tweet_id: str = None):
    return f"https://twitter.com/{handle}" + (f"/status/{tweet_id}" if tweet_id else "")

def run_async(func):
    async def wrapper(*args, **kwargs):
        """Runs blocking functions in async"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))
    return wrapper

@run_async
def run_cmd(cmd: str, b1: bytes = None, decode: bool = False) -> tuple[str | bytes, int]:
    """Executes ffmpeg/git commands and returns the output"""
    p = Popen(split(cmd), stdin = PIPE, stdout = PIPE)
    result: bytes = p.communicate(input = b1)[0]

    if decode:
        result = result.decode("utf-8").strip("\n")

    return result, p.returncode

async def send_media(ctx: commands.Context, orig_msg: discord.Message, media: tuple[BytesIO, str, str]):
    """Sends the given media to discord or the image server depending on its size"""
    if not media[0]:  # if the edited file is missing (could not be made)
        await orig_msg.edit(content = err.MEDIA_EDIT_ERROR)
        return

    try:
        await ctx.reply(file = discord.File(*media[:2]), mention_author = False)
    except discord.HTTPException:
        if Keys.image and "video" not in media[2]:
            url = await serve_very_big_file(media[0], media[2])

            if not url:
                # send error if uploading failed
                await orig_msg.edit(content = err.IMAGE_SERVER_ERROR)
                return

            embed = BaseEmbed()
            embed.set_image(url = url)
            embed.set_footer(text = f"uploaded to {Keys.image.domain.replace('https://', '')} (larger than 8 mb), deletes in 24h!!")

            await ctx.reply(embed = embed)
        else:
            await orig_msg.edit(content = err.CANT_SEND_FILE)
            return

    await orig_msg.delete()
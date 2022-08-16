import discord
from discord.ext import commands

from utils.dataclasses import reg, err, ff
from utils.clients import Clients, Keys

from tempfile import NamedTemporaryFile as create_temp, TemporaryDirectory
from subprocess import Popen, PIPE
from time import strftime, gmtime
from os.path import splitext
from typing import Union
from shlex import split
from io import BytesIO
from PIL import Image
import aiohttp

class AttObj:
    def __init__(self, bytes, filename, filetype):
        self.obj = BytesIO(bytes)
        self.name = filename
        self.type = filetype

def _get_link(text: str):
    # links that can be read directly
    valid_urls = (
        "https://tenor",
        "https://cdn.discordapp",
        "https://media.discordapp",
        "https://i.imgur",
        "https://c.tenor",
        Keys.imoog_domain   # allow content from the image server
    )

    if match := reg.url.search(text):
        link = match.group(0)

        return link if link.startswith(valid_urls) else None

async def _link_bytes(link: str, allow_gifs: bool, media_types: list[str]):
    if res := reg.tenor.search(link):
        # get direct gif link through tenor's api
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://g.tenor.com/v1/gifs?ids={res.group(1)}&key={Keys.tenor}') as r:
                res = await r.json()

        link = res['results'][0]['media'][0]['gif']['url']

    # read bytes from the link
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as r:
            r_type = r.content_type

            if any(x in r_type for x in ("gif", "apng")) and not allow_gifs:
                return None

            return (await r.read(), "url", r_type) if any(types in r_type for types in media_types) else None

async def get_media(ctx: commands.Context, media_types: list[str], allow_gifs: bool = False, allow_urls: bool = False):
    """Main function for getting attachments from either messages, replies, or previous messages"""
    if ctx.message.attachments:
        msg = ctx.message
    else:
        if ctx.message.reference:
            msg = ctx.message.reference.resolved
        else:
            # 0: bot msg --> 1: initial msg --> 2: [msg with link or image] 
            msg = (await ctx.message.channel.history(limit=3).flatten())[2]

    if msg.attachments:
        att = msg.attachments[0]

        # don't use animated gifs/pngs if allow_gifs is false
        if any(x in att.content_type for x in ("gif", "apng")) and not allow_gifs:
            return (None, err.WRONG_ATT_TYPE)

        return (AttObj(await att.read(), splitext(att.filename)[0], att.content_type), None) if any(types in att.content_type for types in media_types) else (None, err.WRONG_ATT_TYPE)
    else:
        # if allow_urls is true, read the image/gif from the link
        if not allow_urls:
            return (None, err.NO_ATTACHMENT_FOUND)
        else:
            link = _get_link(msg.content)

            if link:
                link_bytes = await _link_bytes(link, allow_gifs, media_types)
                return (AttObj(*link_bytes), None) if link_bytes else (None, err.WRONG_ATT_TYPE)
            else:
                error = err.NO_ATT_OR_URL_FOUND
                
                if "//imgur.com" in msg.content:
                    error += " (cant use imgur link it doesn't start with \"i.\")"

                return (None, error)

def check(ctx: Union[commands.Context, discord.Interaction]):
    """Checks if a message is sent by the command sender"""
    def check_inner(message: discord.Message):
        # get author from either interaction or context
        if isinstance(ctx, discord.Interaction):
            author = ctx.user
        else: 
            author = ctx.author
        
        # check if the message author is the same as the original user
        # and that the message channel is the same as the original channel
        return (message.author == author
            and message.channel == ctx.channel)

    return check_inner

def btn_check(ctx: Union[commands.Context, discord.Interaction]):
    """Checks if a button is pressed by the command sender"""
    if isinstance(ctx, discord.Interaction):
        author = ctx.user
    else: 
        author = ctx.author

    # check if: 
    #  - the interaction is from a component (ex. button)
    #  - the user who send the interaction is the same as the original user
    #  - the channel that the interaction was sent in is the same as the original channel

    def btn_check_inner(interaction: discord.Interaction):
        return (interaction.type == discord.InteractionType.component 
            and interaction.user == author
            and interaction.channel == ctx.channel)

    return btn_check_inner

def format_time(duration: int):
    """Formats the given duration (in seconds) into either M:S or H:M:S"""
    # check if the duration is an hour or more (and switch formats)
    hours = duration // 3600
    format = '%-H:%M:%S' if hours else '%-M:%S'

    return strftime(format, gmtime(duration))

async def get_attachment(ctx: commands.Context, interaction: discord.Interaction = None):
    """Gets the attachment to use for the tweet"""
    # switch to the original message if it's a reply
    msg = ctx.message.reference.resolved if ctx.message.reference and not ctx.message.attachments else ctx.message

    if not msg.attachments:
        return

    attachments = []

    for i, att in enumerate(msg.attachments):
        if i == 4:
            break

        att_bytes = BytesIO(await att.read())

        if "image" in att.content_type:
            # if the content is animated, only one can be posted
            if any(att.content_type == x for x in ["image/gif", "image/apng"]):
                return ["gif", att_bytes]

            attachments.append(att_bytes)
            continue
        
        if att.filename.lower().endswith("mov"):
            att_bytes = mov_to_mp4(att_bytes)

            if not att_bytes:
                if interaction:
                    await interaction.edit_original_message(content = err.MOV_TO_MP4_ERROR)
                else:
                    await ctx.send(err.MOV_TO_MP4_ERROR)

                return

        return ["video", att_bytes]

    return ["image", attachments]

def get_attachment_obj(ctx: commands.Context):
    """Gets the attachment object from a message"""
    # switch to the replied message if it's there
    msg = ctx.message.reference.resolved if ctx.message.reference and not ctx.message.attachments else ctx.message
    
    if not msg.attachments:
        return
    
    return msg.attachments[0]
    
def get_media_ids(content):
    """Gets the media ids for content in tweets"""
    api = Clients().twitter()

    result = content[0]  # either "image", "video", or "gif"
    media = content[1]  # BytesIO (or list if "image")
    media_ids = []

    # chooses between either uploading multiple images or just one video/gif
    if result == "image":
        for image in media:
            # create temporary file to store image data in
            with create_temp(suffix='.png') as temp:
                # convert image into png in case of filetype conflicts
                im = Image.open(image)
                im.convert('RGBA')
                im.save(temp.name, format='PNG')

                res = api.media_upload(temp.name)
                media_ids.append(res.media_id)
    else:
        # store media data in a temporary file
        with create_temp() as temp:
            temp.write(media.getvalue())
            res = api.chunked_upload(temp.name, media_category=f"tweet_{result}")
            media_ids.append(res.media_id)

    return media_ids

async def _upload_to_server(b: BytesIO, mime: str):
    """Uploads media to the image server (imoog)"""
    form = aiohttp.FormData()
    form.add_field("file", b.getvalue(), content_type = mime)

    async with aiohttp.ClientSession() as session:
        async with session.post(f'http://localhost:{Keys.imoog_port}/upload', data = form, headers = {"Authorization": Keys.imoog_secret}) as resp:
            resp = await resp.json()

    id: str = resp['file_id']
    ext: str = resp['file_ext']
    domain = Keys.imoog_domain

    return f"{domain}/image/{id.upper()}.{ext}"

def mov_to_mp4(file: BytesIO):
    """Converts mov files to mp4"""
    with TemporaryDirectory() as temp:
        with open(f'{temp}/input.mov', 'wb') as input:
            input.write(file.getvalue())
        
        _, returncode = run(ff.MOV_TO_MP4(temp))

        if returncode != 0:
            return None

        with open(f'{temp}/output.mp4') as output:
            result = BytesIO(output.read())
        
        return result

def get_yt_thumbnail(identifier: str):
    return f"https://img.youtube.com/vi/{identifier}/0.jpg"

def run(cmd: str, b1: bytes = None, decode: bool = False):
    p = Popen(split(cmd), stdin = PIPE, stdout = PIPE)
    result: bytes = p.communicate(input = b1)[0]

    return (result.decode('utf-8').strip('\n') if decode else result), p.returncode

async def send_media(ctx: commands.Context, msg: discord.Message, content: BytesIO, filetype: str, filename: str):
    """Sends the given media to discord or the image server depending on its size"""
    try:
        await ctx.reply(file = discord.File(content, filename), mention_author = False)
    except:
        if (Keys.imoog_port and Keys.imoog_domain and Keys.imoog_secret) and "video" not in filetype:
            url = await _upload_to_server(content, filetype)

            embed = discord.Embed(color = discord.Color.embed_background())
            embed.set_image(url = url)
            embed.set_footer(text = f"uploaded to {Keys.imoog_domain.replace('https://', '')} | expires in 24h")

            await ctx.reply(embed = embed)
        else:
            return await msg.edit(content = err.CANT_SEND_FILE)
    
    await msg.delete()
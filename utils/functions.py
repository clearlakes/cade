import discord
from discord.ext import commands

from utils.variables import Clients, Regex, Keys, FFMPEG

from tempfile import NamedTemporaryFile as create_temp
from time import strftime, gmtime
from subprocess import Popen
from os.path import splitext
from typing import Union
from shlex import split
from io import BytesIO
from PIL import Image
import aiohttp

re = Regex()
keys = Keys()
api = Clients().twitter()

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
        "https://c.tenor"
    )

    if match := re.url.search(text):
        link = match.group(0)

        return link if link.startswith(valid_urls) else None

async def _link_bytes(link: str, allow_gifs: bool, media_types: list[str]):
    if res := re.tenor.search(link):
        # get direct gif link through tenor's api
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://g.tenor.com/v1/gifs?ids={res.group(1)}&key={keys.tenor}') as r:
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
            return (None, "wrong attachment type")

        return (AttObj(await att.read(), splitext(att.filename)[0], att.content_type), None) if any(types in att.content_type for types in media_types) else (None, "wrong attachment type")
    else:
        # if allow_urls is true, read the image/gif from the link
        if not allow_urls:
            return (None, "no attachments were found")
        else:
            link = _get_link(msg.content)

            if link:
                link_bytes = await _link_bytes(link, allow_gifs, media_types)
                return (AttObj(*link_bytes), None) if link_bytes else (None, "invalid media type")
            else:
                return (None, "unknown link")

def clean_error(text: Exception):
    """Removes color codes and newlines from errors"""
    return re.ansi.sub('', str(text)).replace("\n", " - ")

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

def format_time(duration):
    """Formats the given duration into either M:S or H:M:S"""
    hour = int(strftime('%H', gmtime(int(duration))))

    # check if the duration is an hour or more
    if hour > 0:
        new_duration = strftime('%-H:%M:%S', gmtime(int(duration)))
    else:
        new_duration = strftime('%-M:%S', gmtime(int(duration)))

    return new_duration

async def get_attachment(ctx: commands.Context, interaction: discord.Interaction = None):
    """Gets the attachment to use for the tweet"""
    client = ctx.bot

    # switch to the replied message if it's there
    if ctx.message.attachments:
        msg = ctx.message
    elif ctx.message.reference:
        msg = ctx.message.reference.resolved
    else:
        return False
    
    count = 0
    att_bytes = []

    if not msg.attachments:
        return False
    else:
        for att in msg.attachments:
            if count == 4:
                break

            if "image" in att.content_type:
                # if the content is animated, only one can be posted
                if any(att.content_type == x for x in ["image/gif", "image/apng"]):
                    return ["gif", BytesIO(await att.read())]

                att_bytes.append(BytesIO(await att.read()))
                count += 1
                continue
            
            if att.filename.lower().endswith("mov"):
                # convert mov to mp4
                with create_temp(suffix=".mov") as temp_mov, create_temp(suffix=".mp4") as temp_mp4:
                    if not interaction:
                        processing = await ctx.send(f"{client.loading} Processing...")
                    else:
                        processing = await interaction.edit_original_message(content = f"{client.loading} Processing...", view = None)

                    temp_mov.write(await att.read())
                    command = split(f'{FFMPEG} -i {temp_mov.name} -qscale 0 {temp_mp4.name}')
                    
                    p = Popen(command)
                    p.wait()

                    # if there was an error running the ffmpeg command
                    if p.returncode != 0:
                        if not interaction:
                            await processing.edit("**Error:** there was an issue converting from mov to mp4")
                        else:
                            processing = await interaction.edit_original_message(content = "**Error:** there was an issue converting from mov to mp4")

                        return False
                    else:
                        return ["video", BytesIO(temp_mp4.read())]

            return ["video", BytesIO(await att.read())]

        return ["image", att_bytes]

async def get_attachment_obj(ctx: commands.Context):
    """Gets the attachment object from a message"""
    # switch to the replied message if it's there
    if ctx.message.attachments:
        msg = ctx.message
    elif ctx.message.reference:
        msg = ctx.message.reference.resolved
    else:
        return False
    
    if not msg.attachments:
        return False
    else:
        return msg.attachments[0]
    
def get_media_ids(content):
    """Gets the media ids for content in tweets"""
    media_ids = []
    result = content[0]
    media = content[1]

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
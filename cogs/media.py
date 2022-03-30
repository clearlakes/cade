import discord
import aiohttp
from discord.ext import commands
from tempfile import NamedTemporaryFile as create_temp
from utils.bot_vars import url_rx, tenor_rx, youtube_rx, tenor_key, escape_ansii, FFMPEG
from mutagen.mp3 import MP3
from utils import img_edit
import subprocess
import mimetypes
import datetime
import asyncio
import random
import string
import shlex
import pafy
import time
import io
import os

class ChoiceView(discord.ui.View):
    # download choice for "get" command
    def __init__(self, ctx):
        super().__init__()
        self.choice = None
        self.ctx = ctx

    @discord.ui.button(label="audio", style=discord.ButtonStyle.secondary)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return
        
        # the user chose to download the audio
        self.choice = "audio"
        self.stop()

    @discord.ui.button(label="video", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        # the user chose to download the video
        self.choice = "video"
        self.stop()

class media(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    async def get_media(self, ctx: commands.Context, media_type: list, allow_gifs: bool = False, allow_tenor: bool = False):
        """ Gets an attachment from either the message itself, the message it's replying to, or the message above it """
        # function that gets data from a url
        async def get_bytes(url, filename = None):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    b = await r.read()
                    att_bytes = io.BytesIO(b)
                    
                    # the filename will be none if the url is not of an attachment 
                    if filename is None:
                        filename = ''.join(random.choice(string.ascii_letters) for _ in range(7))
                        filename += mimetypes.guess_extension(r.content_type)

            no_ext = os.path.splitext(filename)[0]
            return [att_bytes, filename, no_ext]
                
        msg = ctx.message

        # if the given message is a reply, use the message being replied to
        if ctx.message.reference:
            msg = ctx.message.reference.resolved
        
        # i don't know what happened in this next part

        # if no attachments were found
        if not msg.attachments:
            # if the command running the function accepts tenor links
            if allow_tenor is True:
                # if the message's content does not have a url in it, switch to the message above it
                if not url_rx.match(msg.content):
                    messages = await ctx.channel.history(limit=3).flatten()
                    msg = messages[2]

                    # if that message contains attachments, use those
                    if msg.attachments:
                        att = msg.attachments[0]
                        if att.size < 8388608 and any(x in att.content_type for x in media_type):
                            return await get_bytes(att.url, att.filename), True
                        else:
                            types = "/".join(x for x in media_type)
                            return await ctx.send(f"**Error:** wrong attachment type (looking for {types})"), False
                    
                    # if not even that message contains a url, send an error
                    if not url_rx.match(msg.content):
                        return await ctx.send("**Error:** could not find the attachment"), False

                content_url = url_rx.match(msg.content).group(0)

                # if the given url is from tenor
                if tenor_rx.match(content_url):
                    # get the gif id from the url
                    url_id = tenor_rx.match(content_url).group(1)

                    # get the gif's information using the gif id and tenor api key
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f'https://g.tenor.com/v1/gifs?ids={url_id}&key={tenor_key}') as r:
                            res = await r.json()

                    # get the actual gif url
                    content_url = res['results'][0]['media'][0]['gif']['url']
                    
                return await get_bytes(content_url), True
            
            # ok now back to if allow_tenor isn't set to true
            # if no attachments were found, switch to the message above it
            messages = await ctx.channel.history(limit=3).flatten()
            msg = messages[2]

            # if that message doesn't have any attachments, send an error
            if not msg.attachments:
                return await ctx.send("**Error:** missing attachment"), False

        # get the first attachment
        att = msg.attachments[0]

        # check if the attachment is or is larger than 8 mb
        if att.size >= 8388608:
            return await ctx.send("**Error:** attachment is too large"), False

        att_type = att.content_type

        # if the attachment is animated and allow_gifs is set to false, send an error
        if att_type in ("image/gif", "image/apng") and allow_gifs is False:
            types = "/".join(x for x in media_type)
            return await ctx.send(f"**Error:** wrong attachment type (looking for {types})"), False

        # check if the attachment matches the required media type
        if any(x in att_type for x in media_type):
            return await get_bytes(att.url, att.filename), True
        else:
            # if it doesn't match, list what is needed 
            if "image" in media_type and allow_gifs is True:
                media_type.append("gif")

            types = "/".join(x for x in media_type)
            return await ctx.send(f"**Error:** wrong attachment type (looking for {types})"), False

    @commands.command()
    async def jpeg(self, ctx: commands.Context):
        """ Decreases the quality of a given image """
        processing = await ctx.send(f"{self.client.loading} Processing...")

        # get an image from the user's message
        attachment, res = await self.get_media(ctx, ["image"])
        if res is False: return await processing.delete()

        result = await self.client.loop.run_in_executor(None, lambda: img_edit.jpeg(attachment[0]))

        filename = f"{attachment[2]}.jpg"

        # send the created image
        try:
            await ctx.send(file=discord.File(result, filename))
            await processing.delete()
        except:
            return await processing.edit("**Error:** could not send the image for some reason")
    
    @commands.command(aliases=["img"])
    async def imgaudio(self, ctx: commands.Context, length: int = None):
        """ Creates a video of a set length with a given image and audio source """
        global audio; global audio_type

        def check_audio(author):
            def check_inner(message):
                global audio; global audio_type

                mp3_types = ["mpeg", "mp3"]

                # check if the bot needs to get information from a reply
                if message.reference:
                    msg = message.reference.resolved
                else:
                    msg = message

                # if the message contains an mp3 file
                if msg.attachments and any(x in msg.attachments[0].content_type for x in mp3_types):
                    audio_type = "file"
                    audio = msg.attachments[0]

                # if the message contains a youtube url
                elif youtube_rx.match(msg.content):
                    url = youtube_rx.match(msg.content).group(0)
                    audio_type = "url"
                    audio = url

                else:
                    # failed to get anything
                    audio_type = None
                    audio = None

                return message.author == author
            return check_inner
        
        # if a length is given, check if it's a number
        if length:
            try:
                length = int(length)
            except ValueError:
                return await ctx.send("**Error:** length must be in seconds")
        
        # embed that will show the progress
        embed = discord.Embed(
            title = f"{self.client.loading} Processing...",
            color = self.client.gray
        )

        wait_msg = await ctx.send(embed = embed)

        # get the image attachment
        img_file, res = await self.get_media(ctx, ["image"])
        if res is False: return await wait_msg.delete()

        img_file[0] = await self.client.loop.run_in_executor(None, lambda: img_edit.size_check(img_file[0]))

        # edit the embed to ask for audio
        embed.title = f"{self.client.wait} Send either a youtube url or an mp3 file to use as the audio."
        embed.set_footer(text="(you may also reply to a message that contains it)")
        await wait_msg.edit(embed = embed)

        # wait for a youtube url or mp3 file using the check_audio function
        try:
            response = await self.client.wait_for('message', check = check_audio(ctx.author), timeout=300)
        except asyncio.TimeoutError:
            return await wait_msg.edit(content="**Error:** timed out", embed=None)

        await response.delete()

        # if nothing was found
        if audio is None:
            await wait_msg.delete()
            return await ctx.send("**Error:** could not find audio file or url")

        # edit the embed to show that it's in step 1
        embed.title = f"{self.client.loading} Getting {audio_type} information..."
        embed.set_footer()
        await wait_msg.edit(embed = embed)

        # if a video link was given
        if audio_type == "url":
            # get video information
            try:
                video = pafy.new(audio)
                stream_url = video.getbestaudio().url
            except Exception as e:
                await wait_msg.delete()
                return await ctx.send(f"**Error:** could not get video information\n(full error: ||{escape_ansii(e)}||)")

            video_title = video.title
            duration = video.length
            duration_text = str(datetime.timedelta(seconds = duration))
            audio_source = video_title
        
        # if an mp3 file was given
        if audio_type == "file":
            # download the video as a temporary file and get its duration
            with create_temp(suffix="mp3") as temp:
                await audio.save(temp.name)
                audio_bytes = temp.read()
                duration = round(MP3(temp.name).info.length, 1)

            audio_source = audio.filename
            duration_text = f"{duration} seconds"

        # if a length was not given, use the audio source's length
        if length is None:
            # if the audio source's length is longer than 30 minutes, send an error
            if duration >= 1800:
                await wait_msg.delete()
                return await ctx.send("**Error:** audio length is too long (max: 30 minutes)")
            else:
                length = duration

        audio_str = f"[{audio_source}]({audio})" if audio_type == "url" else audio_source

        # edit the embed to show that it's in step 2
        embed.title = f"{self.client.loading} Generating video..."
        embed.description = f"- Audio: **{audio_str}** `{duration_text}`\n- Length: `{length} seconds`"
        await wait_msg.edit(embed = embed)
        
        # create two temporary files to use later on, with one being a video and the other being an image
        with create_temp(suffix='.mp4') as temp, create_temp(suffix='.png') as image:
            async def command_error(cmd):
                # if the ffmpeg command fails using the stream url, it might be because it's age restricted
                extra = ", make sure that the youtube video is not age restricted just in case" if cmd == "p" else ''

                await wait_msg.delete()
                await ctx.send(f"**Error:** failed to create the video{extra} (more details: ||command `{cmd}` failed with audio type `{audio_type}`||)")

            # write the given image into the temporary image file
            image.write(img_file[0].getvalue())

            # if the audio source is a url, only a single command needs to run
            if audio_type == "url":
                # streches the image out into a video and uses audio from the given url
                # the final video is written into the temporary video file
                command = shlex.split(f'{FFMPEG} -loop 1 -i {image.name} -i {stream_url} -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p -shortest {temp.name}')
                p = subprocess.Popen(command)
                p.wait()

                # if there was an error
                if p.returncode != 0: return await command_error("p")

            if audio_type == "file":
                # create another temporary file as input for the second command
                with create_temp(suffix='.mp4') as second_input:
                    # the first command streches the image into a video, and saves it into the temporary file that was just created
                    first_command = shlex.split(f'{FFMPEG} -loop 1 -i {image.name} -c:v libx264 -t {length} -pix_fmt yuv420p {second_input.name}')
                    # the second command adds audio from the mp3 file using its bytes, and the final video is saved into the original temporary video file
                    second_command = shlex.split(f'{FFMPEG} -i {second_input.name} -f mp3 -i pipe: -map 0:v -map 1:a -c:v copy -shortest {temp.name}')

                    # run the first command
                    p1 = subprocess.Popen(first_command)
                    p1.wait()

                    # check for errors
                    if p1.returncode != 0: return await command_error("p1")

                    # run the second command and send the mp3 file as bytes
                    p2 = subprocess.Popen(second_command, stdin=subprocess.PIPE)
                    p2.communicate(input=audio_bytes)
                    p2.wait()

                    if p2.returncode != 0: return await command_error("p2")

            video_file = io.BytesIO(temp.read())

            embed.title = f"{self.client.loading} Sending video..."
            await wait_msg.edit(embed = embed)

            # send the completed video
            try:
                await ctx.send(ctx.author.mention, file = discord.File(video_file, f"{img_file[2]}.mp4"))
                
                embed.title = f"{self.client.ok} Completed"
                embed.color = discord.Color.brand_green()
                await wait_msg.edit(embed = embed)
            except:
                await wait_msg.edit(content = "**Error:** could not send video (probably too large)", embed = None)
    
    @commands.command()
    async def resize(self, ctx: commands.Context, width = "auto", height = "auto"):
        """ Resizes the given attachment """
        auto = False

        # if nothing is given (if both values are still "auto")
        if width == "auto" and height == "auto":
            raise commands.BadArgument()

        if width == "auto" or height == "auto":
            auto = True

        # if a given size is over 2000 pixels, send an error
        if (width.isnumeric() and int(width) > 2000) or (height.isnumeric() and int(height) > 2000):
            return await ctx.send("**Error:** value too large (max: 2000)")

        processing = await ctx.send(f"{self.client.loading} Processing...")

        # get either an image, gif, or video attachment
        attachment, res = await self.get_media(ctx, ["image", "video"], allow_gifs=True)
        if res is False: return await processing.delete()

        # if the attachment is a video
        if attachment[1].lower().endswith("mp4"):
            await processing.edit(content=f"{self.client.loading} Resizing video...")

            # create a temporary file to use with the ffmpeg command
            with create_temp() as temp:
                temp.write(attachment[0].getvalue())

                # resize the video using the given size (and replace "auto" with -2, which means the same thing for ffmpeg)
                command = shlex.split(f'{FFMPEG} -i {temp.name} -f mp4 -movflags frag_keyframe+empty_moov -vf scale={width}:{height} pipe:'.replace("auto", "-2"))
                
                p = subprocess.Popen(command, stdout=subprocess.PIPE)
                out = p.communicate()[0]
                p.wait()

                # get the result in bytes
                result = io.BytesIO(out)

                # if there was an error running the command
                if p.returncode != 0:
                    await processing.delete()
                    return await ctx.send("**Error:** an issue occurred while resizing the video")
            
            filename = f"{attachment[2]}.mp4"
            
            await processing.delete()
            return await ctx.send(file = discord.File(result, filename))

        orig_width, orig_height = await self.client.loop.run_in_executor(None, lambda: img_edit.get_size(attachment[0]))

        await processing.edit(content=f"{self.client.loading} Processing... ({orig_width}x{orig_height} **-->** {width}x{height})".replace("auto", "`auto`"))

        if auto is True:
            if width != "auto":
                # calculate the height
                wpercent = (int(width) / float(orig_width))
                height = int((float(orig_height) * float(wpercent)))
            else:
                # calculate the width
                hpercent = (int(height) / float(orig_height))
                width = int((float(orig_width) * float(hpercent)))

        new_size = (int(width), int(height))

        # if the attachment is a gif, resize it using the edit_gif function
        if attachment[1].lower().endswith("gif"):
            result = await self.client.loop.run_in_executor(None, lambda: img_edit.gif(attachment[0], edit_type=1, size=new_size))
            filename = f"{attachment[2]}.gif"
        else:
            # resize it using PIL if it's an image
            result = await self.client.loop.run_in_executor(None, lambda: img_edit.resize(attachment[0], size=new_size))
            filename = f"{attachment[2]}.png"

        # send the resized attachment
        try:
            await ctx.send(file = discord.File(result, filename))
        except:
            await ctx.send("**Error:** could not send resized file")
        
        await processing.delete()

    @commands.command()
    async def caption(self, ctx: commands.Context, *, text: str = None):
        """ Captions the given image/gif """
        # if nothing is given
        if text is None:
            raise commands.BadArgument()

        # remove emojis from the given caption
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        # check if the caption is empty again in case it was only made up of emojis for some reason
        if text == '':
            return await ctx.send("**Error:** can't do emojis sorry")

        processing = await ctx.send(f"{self.client.loading} Processing...")

        # get either an image, gif, or tenor url
        attachment, res = await self.get_media(ctx, ["image"], allow_gifs=True, allow_tenor=True)
        if res is False: return await processing.delete()

        width, height = await self.client.loop.run_in_executor(None, lambda: img_edit.get_size(attachment[0]))

        # this command freezes for some reason if the file is too small
        # checking if the file size is less than 50 pixels is just a guess at what the issue is
        if width <= 50 or height <= 50:
            await processing.delete()
            return await ctx.send("**Error:** file too small")

        # now we start generating the caption image
        caption = await self.client.loop.run_in_executor(None, lambda: img_edit.create_caption(text, width))

        # if the attachment is a gif, use the edit_gif function to caption each frame
        if attachment[1].lower().endswith("gif"):
            result = await self.client.loop.run_in_executor(None, lambda: img_edit.gif(attachment[0], edit_type=2, caption=caption))
            filename = f"{attachment[2]}.gif"
        else:
            # if it's an image, add the caption image to the top of it
            result = await self.client.loop.run_in_executor(None, lambda: img_edit.add_caption(attachment[0], caption=caption))
            filename = f"{attachment[2]}.png"

        # send the completed caption
        try:
            await ctx.send(file = discord.File(result, filename))
        except:
            await ctx.send("**Error:** the completed gif was too large to send")

        await processing.delete()

    @commands.command()
    async def get(self, ctx: commands.Context, url: str = None, start = None, end = None):
        """ Downloads either the audio or video of a given youtube video """
        if url is None:
            raise commands.BadArgument()

        # if the given url is not a link (probably sent as ".get 1:00 2:00"), try to get the url from the message being replied to
        if not youtube_rx.match(url):
            # check if there is a reply and that the message being replied to contains a yt link
            if ctx.message.reference and youtube_rx.match(ctx.message.reference.resolved.content):
                # check if an end time (which would be "start" in this case) was not given
                if start is None:
                    return await ctx.send("**Error**: missing end timestamp")

                end = start
                start = url
                url = youtube_rx.match(ctx.message.reference.resolved.content).group(0)
            else:
                return await ctx.send("**Error:** invalid url")

        # if a start time is given but not an end time
        if start is not None and end is None:
            return await ctx.send("**Error:** missing end timestamp")
        
        # if a start/end time is given, see if they are formatted correctly
        if start is not None:        
            s_colons = start.count(":")
            time_format = "%H:%M:%S" if s_colons == 2 else "%M:%S"
        
            try:
                a = time.strptime(start, time_format)
                b = time.strptime(end, time_format)
            except ValueError:
                return await ctx.send(f"**Error:** invalid timestamps (must be M:S or H:M:S)")

            if time.strftime(time_format, a) <= time.strftime(time_format, b):
                return await ctx.send(f"**Error:** the start time must come before the end time")
        
        # send a message with the "video"/"audio" buttons from ChoiceView
        view = ChoiceView(ctx)
        msg = await ctx.send("what should be downloaded?", view = view)
        await view.wait()

        # disable the buttons
        for btn in view.children:
            btn.disabled = True

        await msg.edit(f"{self.client.loading} Getting {view.choice}...", view = view)
        
        pafy_obj = pafy.new(url)

        # get the stream url according to the user's choice
        if view.choice == "video":
            video_res = pafy_obj.getbest(preftype="mp4")
        else:
            video_res = pafy_obj.getbestaudio()

        stream_url = video_res.url
        video_title = video_res.title
        
        suffix = '.mp3' if view.choice == 'audio' else '.mp4'

        # create a temporary file to save the audio/video to
        with create_temp(suffix=suffix) as temp:
            # change the command to include a start/end time if they are given
            if start is not None:
                command = shlex.split(f"{FFMPEG} -ss {start} -to {end} -i {stream_url} {temp.name}")
            else:
                command = shlex.split(f"{FFMPEG} -i {stream_url} {temp.name}")
            
            p = subprocess.Popen(command)
            p.wait()

            # if the command failed
            if p.returncode != 0:
                await msg.delete()
                return await ctx.send("**Error:** could not download video (most likely age restricted)")
            
            # send the downloaded file
            try:
                await ctx.send(ctx.author.mention, file = discord.File(temp.name, f"{video_title}{suffix}"))
            except:
                await ctx.send("**Error:** could not send file (most likely too large)")
                
            await msg.delete()

def setup(bot):
    bot.add_cog(media(bot))

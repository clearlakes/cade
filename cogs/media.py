import discord
from discord.ext import commands

from utils.functions import clean_error, get_media, format_time, upload_to_server
from utils.variables import Keys, Regex, FFMPEG
from utils.views import ChoiceView
from utils import image

from tempfile import NamedTemporaryFile as create_temp
from time import strftime, strptime
from subprocess import Popen, PIPE
from youtube_dl import YoutubeDL
from asyncio import TimeoutError
from functools import partial
from mutagen.mp3 import MP3
from shlex import split
from io import BytesIO

re = Regex()
keys = Keys()

class Media(commands.Cog):
    def __init__(self, client):
        self.client: discord.Bot = client

    @commands.command()
    async def jpeg(self, ctx: commands.Context):
        """Decreases the quality of a given image"""
        processing = await ctx.send(f"{self.client.loading} Processing...")

        # get an image from the user's message
        res, err = await get_media(ctx, ["image"])
        if err: return await processing.edit(content = f"**Error:** {err}")

        result = await self.client.loop.run_in_executor(None, partial(image.jpeg, res.obj))

        # send the created image
        try:
            await ctx.send(file=discord.File(result, f"{res.name}.jpg"))
            await processing.delete()
        except:
            return await processing.edit(content = "**Error:** could not send the image for some reason")
    
    @commands.command(aliases=["img"])
    async def imgaudio(self, ctx: commands.Context, length: int = None):
        """Creates a video of a set length with a given image and audio source"""
        global audio; global audio_type

        def check_audio(author):
            def check_inner(message: discord.Message):
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
                elif re.youtube.match(msg.content):
                    url = re.youtube.match(msg.content).group(0)
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

        processing = await ctx.send(embed = embed)

        # get the image attachment
        res, err = await get_media(ctx, ["image"])
        if err: return await processing.edit(content = f"**Error:** {err}", embed = None)

        result = await self.client.loop.run_in_executor(None, partial(image.size_check, res.obj))

        # edit the embed to ask for audio
        embed.title = f"{self.client.wait} Send a youtube url or an mp3 file to use as the audio"
        embed.set_footer(text="or reply to any message that contains one")
        await processing.edit(embed = embed)

        # wait for a youtube url or mp3 file using the check_audio function
        try:
            response = await self.client.wait_for('message', check = check_audio(ctx.author), timeout=300)
        except TimeoutError:
            return await processing.edit(content="**Error:** timed out", embed=None)

        await response.delete()

        # if nothing was found
        if audio is None:
            await processing.delete()
            return await ctx.send("**Error:** could not find audio file or url")

        # edit the embed to show that it's in step 1
        embed.title = f"{self.client.loading} Getting {audio_type} information..."
        embed.set_footer()
        await processing.edit(embed = embed)

        # if a video link was given
        if audio_type == "url":
            # get video information
            try:
                with YoutubeDL({'format': 'bestaudio'}) as ydl:
                    video = ydl.extract_info(audio, download = False)
            except Exception as e:
                await processing.delete()
                return await ctx.send(f"**Error:** could not get video information\n(full error: ||{clean_error(e)}||)")

            stream_url = video['url']
            duration = video['duration']
            video_title = video['title']

            duration_text = format_time(video['duration'])
            audio_source = video_title
        
        # if an mp3 file was given
        if audio_type == "file":
            # download the video as a temporary file and get its duration
            with create_temp(suffix="mp3") as temp:
                await audio.save(temp.name)
                audio_bytes = temp.read()
                duration = MP3(temp.name).info.length

            duration_text = format_time(round(duration, 1))
            audio_source = audio.filename

        # if a length was not given, use the audio source's length
        if length is None:
            # if the audio source's length is longer than 30 minutes, send an error
            if duration >= 1800:
                await processing.delete()
                return await ctx.send("**Error:** audio length is too long (max: 30 minutes)")
            else:
                length = duration

        audio_str = f"[{audio_source}]({audio})" if audio_type == "url" else audio_source

        # edit the embed to show that it's in step 2
        embed.title = f"{self.client.loading} Generating video..."
        embed.description = f"- Audio: **{audio_str}** `{duration_text}`\n- Length: `{length} seconds`"
        await processing.edit(embed = embed)
        
        # create two temporary files to use later on, with one being a video and the other being an image
        with create_temp(suffix='.mp4') as temp, create_temp(suffix='.png') as img:
            async def command_error(cmd):
                # if the ffmpeg command fails using the stream url, it might be because it's age restricted
                extra = ", make sure that the youtube video is not age restricted just in case" if cmd == "p" else ""

                await processing.delete()
                await ctx.send(f"**Error:** failed to create the video{extra} (more details: ||command `{cmd}` failed with audio type `{audio_type}`||)")

            # write the given image into the temporary image file
            img.write(result.getvalue())
            img.seek(0)

            # if the audio source is a url, only a single command needs to run
            if audio_type == "url":
                # streches the image out into a video and uses audio from the given url
                # the final video is written into the temporary video file
                command = split(f'{FFMPEG} -loop 1 -i {img.name} -i {stream_url} -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p -shortest {temp.name}')
                p = Popen(command)
                p.wait()

                # if there was an error
                if p.returncode != 0: return await command_error("p")

            if audio_type == "file":
                # create another temporary file as input for the second command
                with create_temp(suffix='.mp4') as second_input:
                    # the first command streches the image into a video, and saves it into the temporary file that was just created
                    first_command = split(f'{FFMPEG} -loop 1 -i {img.name} -c:v libx264 -t {length} -pix_fmt yuv420p {second_input.name}')
                    # the second command adds audio from the mp3 file using its bytes, and the final video is saved into the original temporary video file
                    second_command = split(f'{FFMPEG} -i {second_input.name} -f mp3 -i pipe: -map 0:v -map 1:a -c:v copy -shortest {temp.name}')

                    # run the first command
                    p1 = Popen(first_command)
                    p1.wait()

                    # check for errors
                    if p1.returncode != 0: return await command_error("p1")

                    # run the second command and send the mp3 file as bytes
                    p2 = Popen(second_command, stdin = PIPE)
                    p2.communicate(input=audio_bytes)
                    p2.wait()

                    if p2.returncode != 0: return await command_error("p2")

            video_file = BytesIO(temp.read())

            embed.title = f"{self.client.loading} Sending video..."
            await processing.edit(embed = embed)

            # send the completed video
            try:
                await ctx.send(ctx.author.mention, file = discord.File(video_file, f"{res.name}.mp4"))
                
                embed.title = f"{self.client.ok} Completed"
                embed.color = discord.Color.brand_green()
                await processing.edit(embed = embed)
            except:
                await processing.edit(content = "**Error:** could not send video (probably too large)", embed = None)
    
    @commands.command()
    async def resize(self, ctx: commands.Context, width = "auto", height = "auto"):
        """Resizes the given attachment"""
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
        res, err = await get_media(ctx, ["image", "video"], allow_gifs = True, allow_urls = True)
        if err: return await processing.edit(content = f"**Error:** {err}")

        # if the attachment is a video
        if "video" in res.type:
            await processing.edit(content=f"{self.client.loading} Resizing video...")

            # create a temporary file to use with the ffmpeg command
            with create_temp() as temp:
                temp.write(res.obj.getvalue())

                # resize the video using the given size (and replace "auto" with -2, which means the same thing for ffmpeg)
                command = split(f'{FFMPEG} -i {temp.name} -f mp4 -movflags frag_keyframe+empty_moov -vf scale={width}:{height} pipe:'.replace("auto", "-2"))
                
                p = Popen(command, stdout = PIPE)
                out = p.communicate()[0]
                p.wait()

                # get the result in bytes
                result = BytesIO(out)

                # if there was an error running the command
                if p.returncode != 0:
                    await processing.delete()
                    return await ctx.send("**Error:** an issue occurred while resizing the video")
            
            await processing.delete()
            return await ctx.send(file = discord.File(result, f"{res.name}.mp4"))

        orig_width, orig_height = await self.client.loop.run_in_executor(None, partial(image.get_size, res.obj))

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

        # resize the attachment depending on file type
        if "gif" in res.type:
            result = await self.client.loop.run_in_executor(None, partial(image.gif, res.obj, edit_type = 1, size = new_size))
            filename = f"{res.name}.gif"
        else:
            result = await self.client.loop.run_in_executor(None, partial(image.resize, res.obj, size = new_size))
            filename = f"{res.name}.png"

        # send the resized attachment
        try:
            await ctx.send(file = discord.File(result, filename))
        except:
            await ctx.send("**Error:** could not send resized file")
        
        await processing.delete()

    @commands.command()
    async def caption(self, ctx: commands.Context, *, text: str = None):
        """Captions the given image/gif"""
        if text is None:
            raise commands.BadArgument()

        processing = await ctx.send(f"{self.client.loading} Processing...")

        # get either an image, gif, or tenor url
        res, err = await get_media(ctx, ["image"], allow_gifs = True, allow_urls = True)
        if err: return await processing.edit(content = f"**Error:** {err}")

        width, height = await self.client.loop.run_in_executor(None, partial(image.get_size, res.obj))

        if width <= 10 or height <= 10:
            await processing.delete()
            return await ctx.send("**Error:** file too small")

        # now we start generating the caption image
        caption = await self.client.loop.run_in_executor(None, partial(image.create_caption, text, width))

        # if the attachment is a gif, use the edit_gif function to caption each frame
        if "gif" in res.type:
            result = await self.client.loop.run_in_executor(None, partial(image.gif, res.obj, edit_type = 2, caption = caption))
            filename = f"{res.name}.gif"
        else:
            # if it's an image, add the caption image to the top of it
            result = await self.client.loop.run_in_executor(None, partial(image.add_caption, res.obj, caption = caption))
            filename = f"{res.name}.png"

        # send the completed caption
        try:
            await ctx.reply(file = discord.File(result, filename), mention_author = False)
        except:
            if keys.imoog_port and keys.imoog_domain and keys.imoog_secret:
                await processing.edit(content = f"{self.client.loading} File too large, uploading instead...")

                url = await upload_to_server(result, "gif")

                embed = discord.Embed(color = self.client.gray)
                embed.set_image(url = url)
                embed.set_footer(text = f"Uploaded to {keys.imoog_domain.replace('https://', '')} | Expires in 24h")

                await ctx.reply(embed = embed)
            else:
                return await processing.edit(content = f"**Error:** the final result was too large to send")

        await processing.delete()

    @commands.command()
    async def get(self, ctx: commands.Context, url: str = None, start = None, end = None):
        """Downloads either the audio or video from a given youtube url"""
        if url is None:
            raise commands.BadArgument()

        # if the given url is not a link (probably sent as ".get 1:00 2:00"), try to get the url from the message being replied to
        if not re.youtube.match(url):
            # check if there is a reply and that the message being replied to contains a yt link
            if ctx.message.reference and re.youtube.match(ctx.message.reference.resolved.content):
                # check if an end time (which would be "start" in this case) was not given
                if start is None:
                    return await ctx.send("**Error**: missing end timestamp")

                end = start
                start = url
                url = re.youtube.match(ctx.message.reference.resolved.content).group(0)
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
                a = strptime(start, time_format)
                b = strptime(end, time_format)
            except ValueError:
                return await ctx.send(f"**Error:** invalid timestamps (must be M:S or H:M:S)")

            if strftime(time_format, a) <= strftime(time_format, b):
                return await ctx.send(f"**Error:** the start time must come before the end time")
        
        # send a message with the "video"/"audio" buttons from ChoiceView
        view = ChoiceView(ctx)
        msg = await ctx.send("what should be downloaded?", view = view)
        await view.wait()

        # disable the buttons
        for btn in view.children:
            btn.disabled = True

        await msg.edit(f"{self.client.loading} Getting {view.choice}...", view = view)

        # get the stream url according to the user's choice            
        if view.choice == "video":
            with YoutubeDL({'format': 'best'}) as ydl:
                video = ydl.extract_info(url, download = False)
                stream_url = video['url']
        else:
            with YoutubeDL({'format': 'bestaudio'}) as ydl:
                video = ydl.extract_info(url, download = False)
                stream_url = video['formats'][0]['url']

        video_title = video['title']
        suffix = '.mp3' if view.choice == 'audio' else '.mp4'

        # create a temporary file to save the audio/video to
        with create_temp(suffix=suffix) as temp:
            # change the command to include a start/end time if they are given
            if start is not None:
                command = split(f"{FFMPEG} -ss {start} -to {end} -i {stream_url} {temp.name}")
            else:
                command = split(f"{FFMPEG} -i {stream_url} {temp.name}")
            
            p = Popen(command)
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
    bot.add_cog(Media(bot))

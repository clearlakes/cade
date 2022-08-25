import discord
from discord.ext import commands

from utils.image import EditImage, EditGif, create_caption_text, get_size
from utils.functions import format_time, send_media, get_media, run
from utils.video import EditVideo, get_size as get_video_size
from utils.dataclasses import reg, err, ff, emoji, colors
from utils.views import ChoiceView

from tempfile import NamedTemporaryFile as create_temp, TemporaryDirectory
from youtube_dl import YoutubeDL
from asyncio import TimeoutError
from functools import partial
from io import BytesIO

class Media(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client

    async def run_async(self, func, *args) -> BytesIO:
        return await self.client.loop.run_in_executor(None, partial(func, *args))

    @commands.command(usage = "(image)")
    async def jpeg(self, ctx: commands.Context):
        """lowers the quality of the given image"""
        processing = await ctx.send(f"{emoji.PROCESSING()} Processing...")

        # get an image from the user's message
        res, error = await get_media(ctx, ["image"])
        if error: return await processing.edit(content = error)

        result = await self.run_async(EditImage(res.obj).jpeg)

        # send the created image
        try:
            await ctx.send(file=discord.File(result, f"{res.name}.jpg"))
            await processing.delete()
        except:
            return await processing.edit(content = err.CANT_SEND_FILE)
    
    @commands.command(aliases = ["img"], usage = "*[seconds] (image)")
    async def imgaudio(self, ctx: commands.Context, length: int = None):
        """converts an image into a video with audio"""
        global audio; global audio_type

        def check_audio(ctx: commands.Context):
            def check_inner(message: discord.Message):
                global audio; global audio_type

                mp3_types = ["audio/mpeg", "audio/mp3"]

                # check if the bot needs to get information from a reply
                msg = message.reference.resolved if message.reference and not message.attachments else message

                audio_type = None
                audio = None

                # if the message contains an mp3 file
                if any((att := attachment).content_type in mp3_types for attachment in msg.attachments):
                    audio_type = "file"
                    audio = att

                # if the message contains a youtube url
                elif match := reg.youtube.search(msg.content):
                    url = match.group(0)
                    audio_type = "url"
                    audio = url

                return message.author == ctx.author and message.channel == ctx.channel
            return check_inner
        
        # if a length is given, check if it's a number
        length = int(length) if str(length).isnumeric() else None
        
        # embed that will show the progress
        embed = discord.Embed(
            title = f"{emoji.PROCESSING()} Processing...",
            color = colors.EMBED_BG
        )

        processing = await ctx.send(embed = embed)

        # get the image attachment
        res, error = await get_media(ctx, ["image"])
        if error: return await processing.edit(content = error, embed = None)

        result = await self.run_async(EditImage(res.obj).resize_even)

        # edit the embed to ask for audio
        embed.title = f"{emoji.WAITING} Send a youtube url or an mp3 file to use as the audio"
        embed.set_footer(text="or reply to any message that contains one")
        await processing.edit(embed = embed)

        # wait for a youtube url or mp3 file using the check_audio function
        try:
            response = await self.client.wait_for('message', check = check_audio(ctx), timeout=300)
        except TimeoutError:
            return await processing.edit(content = err.TIMED_OUT, embed = None)

        await response.delete()

        # if nothing was found
        if audio is None:
            await processing.delete()
            return await ctx.send(err.NO_AUDIO_FOUND)

        # edit the embed to show that it's in step 1
        embed.title = f"{emoji.PROCESSING()} Getting {audio_type} information..."
        embed.set_footer()
        await processing.edit(embed = embed)

        # if a video link was given
        if audio_type == "url":
            audio_bytes = None

            # get video information
            try:
                with YoutubeDL({'format': 'bestaudio'}) as ydl:
                    video = ydl.extract_info(audio, download = False)
            except Exception:
                await processing.delete()
                return await ctx.send(err.YOUTUBE_ERROR)

            stream_url = video['url']
            duration = video['duration']
            video_title = video['title']

            audio_source = video_title
        
        # if an mp3 file was given
        elif audio_type == "file":
            # download the video as a temporary file and get its duration
            with create_temp(suffix=".mp3") as temp:
                await audio.save(temp.name)
                audio_bytes = await audio.read()

                # get mp3 duration
                duration, returncode = run(ff.GET_DURATION(temp.name))

                if returncode != 0:
                    return await ctx.send(err.FFMPEG_ERROR)

                duration = int(float(duration.decode('utf-8')))

            audio_source = audio.filename
        
        duration_text = format_time(duration)

        # if a length was not given, use the audio source's length
        if length is None:
            # if the audio source's length is longer than 30 minutes, send an error
            if duration >= 1800:
                await processing.delete()
                return await ctx.send(err.AUDIO_MAX_LENGTH)
            else:
                length = duration

        audio_str = f"[{audio_source}]({audio})" if audio_type == "url" else audio_source

        # edit the embed to show that it's in step 2
        embed.title = f"{emoji.PROCESSING()} Generating video..."
        embed.description = f"- Audio: **{audio_str}** `{duration_text}`\n- Length: `{length} seconds`"
        await processing.edit(embed = embed)
        
        # create two temporary files to use later on, with one being a video and the other being an image
        with TemporaryDirectory() as temp:
            with open(f'{temp}/input.png', 'wb') as f_img:
                f_img.write(result.getvalue())

            source = '-' if audio_type == "file" else stream_url

            _, returncode = run(ff.IMGAUDIO(temp, source, length), audio_bytes)

            if returncode != 0:
                await processing.delete()
                return await ctx.send(err.FFMPEG_ERROR)

            embed.title = f"{emoji.PROCESSING()} Sending video..."
            await processing.edit(embed = embed)

            # send the completed video
            try:
                await ctx.send(ctx.author.mention, file = discord.File(f"{temp}/output.mp4", f"{res.name}.mp4"))
                
                embed.title = f"{emoji.OK} finish"
                embed.color = discord.Color.brand_green()
                await processing.edit(embed = embed)
            except:
                await processing.edit(content = err.CANT_SEND_FILE, embed = None)
    
    @commands.command(usage = "[width]/auto *[height]/auto (gif/image/video)")
    async def resize(self, ctx: commands.Context, width = 'auto', height = 'auto'):
        """resizes the given attachment"""
        # if nothing is given
        if width == 'auto' and height == 'auto':
            raise commands.MissingRequiredArgument(ctx.command.params["width"])

        # if a given size is over 2000 pixels, send an error
        if any(x.isnumeric() and int(x) > 2000 for x in (width, height)):
            return await ctx.send(err.FILE_MAX_SIZE)

        processing = await ctx.send(f"{emoji.PROCESSING()} Processing...")

        # get either an image, gif, or video attachment
        res, error = await get_media(ctx, ["image", "video"], allow_gifs = True, allow_urls = True)
        if error: return await processing.edit(content = error)

        # if the attachment is a video
        if "video" in res.type:
            result = await self.run_async(EditVideo(res.obj).resize, (width, height))

            if not result:
                return await processing.edit(content = err.FFMPEG_ERROR)

            await ctx.send(file = discord.File(result, f"{res.name}.mp4"))
            return await processing.delete()

        orig_width, orig_height = await self.run_async(get_size, res.obj)
        
        # calculate 'auto' sizes
        if height == 'auto':
            wpercent = (int(width) / float(orig_width))
            height = int((float(orig_height) * float(wpercent)))
        elif width == 'auto':
            hpercent = (int(height) / float(orig_height))
            width = int((float(orig_width) * float(hpercent)))
        
        new_size = (int(width), int(height))

        # resize the attachment depending on file type
        if "gif" in res.type:
            result = await self.run_async(EditGif(res.obj).resize, new_size)
            filename = f"{res.name}.gif"
        else:
            result = await self.run_async(EditImage(res.obj).resize, new_size)
            filename = f"{res.name}.png"

        # send the resized attachment
        try:
            await ctx.send(file = discord.File(result, filename))
        except:
            await ctx.send(err.CANT_SEND_FILE)
        
        await processing.delete()

    @commands.command(usage = "[text] (gif/image/video)")
    async def caption(self, ctx: commands.Context, *, text: str):
        """captions the specified gif or image in the style of iFunny's captions"""
        processing = await ctx.send(f"{emoji.PROCESSING()} Processing...")

        # get either an image, gif, or tenor url
        res, error = await get_media(ctx, ["image", "video"], allow_gifs = True, allow_urls = True)
        if error: return await processing.edit(content = error)

        get_size_func = get_size if "image" in res.type else get_video_size
        size = await self.run_async(get_size_func, res.obj)

        if not size:
            return await ctx.send(err.FFMPEG_ERROR)

        # now we start generating the caption image
        caption = await self.run_async(create_caption_text, text, size[0])

        # run respective functions for captioning gifs/images/videos

        if "gif" in res.type:
            result = await self.run_async(EditGif(res.obj).caption, caption)
            filename = f"{res.name}.gif"

        elif "image" in res.type:
            result = await self.run_async(EditImage(res.obj).caption, caption)
            filename = f"{res.name}.png"

        else:
            result = await self.run_async(EditVideo(res.obj).caption, caption)

            if not result:
                return await ctx.send(err.FFMPEG_ERROR)
            
            filename = f"{res.name}.mp4"

        await send_media(ctx, processing, result, res.type, filename)

    @commands.command(usage = "(gif/image/video)")
    async def uncaption(self, ctx: commands.Context):
        """removes the caption from the given attachment"""
        processing = await ctx.send(f"{emoji.PROCESSING()} Processing...")

        # get either an image, gif, or tenor url
        res, error = await get_media(ctx, ["image", "video"], allow_gifs = True, allow_urls = True)
        if error: return await processing.edit(content = error)

        if "gif" in res.type:
            result = await self.run_async(EditGif(res.obj).uncaption)
            filename = f"{res.name}.gif"

        elif "image" in res.type:
            result = await self.run_async(EditImage(res.obj).uncaption)
            filename = f"{res.name}.png"

        else:
            result = await self.run_async(EditVideo(res.obj).uncaption)

            if not result:
                return await ctx.send(err.FFMPEG_ERROR)

            filename = f"{res.name}.mp4"

        await send_media(ctx, processing, result, res.type, filename)

    @commands.command(usage = "[youtube-url] *[start-time] *[end-time]")
    async def get(self, ctx: commands.Context, url: str, start: str = None, end: str = None):
        """downloads a youtube video (or a part of it)"""
        # if the given url is not a link (probably sent as ".get 1:00 2:00"), try to get the url from the message being replied to
        if not reg.youtube.match(url):
            # check if there is a reply and that the message being replied to contains a yt link
            if (ref := ctx.message.reference) and (match := reg.youtube.search(ref.resolved.content)):
                # check if an end time (which would be "start" in this case) was not given
                if start is None:
                    raise commands.BadArgument()

                end = start
                start = url
                url = match.group(0)
            else:
                return await ctx.send(err.INVALID_URL)
        
        # if a start/end time is given, see if they are formatted correctly
        if start and end:        
            try:
                s_seconds = 0
                e_seconds = 0

                for x in start.split(':'):
                    s_seconds = s_seconds * 60 + int(x)
                
                for y in end.split(':'):
                    e_seconds = e_seconds * 60 + int(y)

            except ValueError:
                return await ctx.send(err.INVALID_TIMESTAMP)

            if (s_seconds - e_seconds) > 0:
                return await ctx.send(err.WEIRD_TIMESTAMPS)
        
        # send a message with ChoiceView buttons
        view = ChoiceView(ctx, ['video', 'audio', 'nvm'])
        msg = await ctx.send("what should be downloaded?", view = view)
        await view.wait()

        # if canceled
        if view.choice == 'nvm':
            await msg.delete()
            await ctx.message.delete()
            return

        await msg.edit(content = f"{emoji.PROCESSING()} downloading {view.choice}...", view = None)

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
        with create_temp(suffix = suffix) as temp:
            # change the command to include a start/end time if they are given
            if start is not None:
                cmd = ff.GET_CUT_STREAM(stream_url, start, end, temp.name)
            else:
                cmd = ff.GET_FULL_STREAM(stream_url, temp.name)
            
            _, returncode = run(cmd)

            # if the command failed
            if returncode != 0:
                await msg.delete()
                return await ctx.send(err.YOUTUBE_ERROR)
            
            # send the downloaded file
            try:
                await ctx.send(ctx.author.mention, file = discord.File(temp.name, f"{video_title}{suffix}"))
            except:
                await ctx.send(err.CANT_SEND_FILE)
                
            await msg.delete()

async def setup(bot: commands.Bot):
    await bot.add_cog(Media(bot))
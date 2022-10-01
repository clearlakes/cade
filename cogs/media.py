import discord
from discord.ext import commands

from utils.useful import (
    format_time,
    send_media,
    get_media,
    run_async,
    run_cmd,
    check
)
from utils.image import (
    create_caption_text,
    get_image_size,
    EditImage,
    EditGif
)
from utils.video import EditVideo, get_video_size
from utils.base import BaseEmbed, BaseCog
from utils.data import reg, err, ff, bot
from utils.views import ChoiceView
from utils.clients import Keys
from utils.main import Cade

from yt_dlp import YoutubeDL, DownloadError
from tempfile import TemporaryDirectory
from asyncio import TimeoutError
import random

class Media(BaseCog):
    def __init__(self, client: Cade):
        super().__init__(client)

        if not Keys.tenor:
            self.client.log.warning("can't use tenor links, missing tenor api key")

        if not Keys.image:
            self.client.log.warning("can't upload larger files, missing image server info")

    @run_async
    def yt_extract(self, url: str, audio_only: bool = True):
        yt_format = "bestaudio" if audio_only else "best"

        try:
            with YoutubeDL({"format": yt_format, "quiet": True, "noplaylist": True}) as ydl:
                return ydl.extract_info(url, download = False)
        except DownloadError as e:
            # clean error and include it in the message
            return "(from youtube) " + f"\"{reg.color.sub('', e.msg).split(':')[2].strip()}\""

    @commands.command(usage = "(image)")
    async def jpeg(self, ctx: commands.Context):
        """lowers the quality of the given image"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        # get an image from the user's message
        res, error = await get_media(ctx, ["image"])
        if error: return await processing.edit(content = error)

        result = await EditImage(res).jpeg()

        # send the created image
        await send_media(ctx, processing, result, res.filetype)

    @commands.command(aliases = ["img"], usage = "*[seconds] (image)")
    async def imgaudio(self, ctx: commands.Context, length: str = None):
        """converts an image into a video with audio"""
        # if a length is given, check if it's a number
        length = int(length) if length and length.isnumeric() else None

        # embed that will show the progress
        embed = BaseEmbed(title = f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        processing = await ctx.send(embed = embed)

        # get the image attachment
        res, error = await get_media(ctx, ["image"])
        if error: return await processing.edit(content = error, embed = None)

        result, _ = await EditImage(res).resize_even()

        # edit the embed to ask for audio
        embed.title = f"{bot.WAITING} send a youtube url or an mp3 file to use as the audio"
        embed.set_footer(text = "or reply to any message that contains one")
        await processing.edit(embed = embed)

        # wait for a youtube url or mp3 file using the check_audio function
        try:
            response: discord.Message = await self.client.wait_for("message", check = check(ctx), timeout = 600)
        except TimeoutError:
            return await processing.edit(content = err.TIMED_OUT, embed = None)

        msg = response.reference.resolved if response.reference and not response.attachments else response
        await response.delete()

        mp3_types = ["audio/mpeg", "audio/mp3"]
        audio_type = None
        audio = None

        # see if the message contains an mp3 file or youtube url
        if any((att := attachment).content_type in mp3_types for attachment in msg.attachments):
            audio_type = "file"
            audio = att
        elif match := reg.youtube.search(msg.content):
            url = match.group(0)
            audio_type = "url"
            audio = url
        else:
            # cancel if nothing was found
            return await processing.edit(content = err.NO_AUDIO_FOUND, embed = None)

        # edit the embed to show that it's in step 1
        embed.title = f"{bot.PROCESSING()} getting {audio_type} information..."
        embed.set_footer()

        await processing.edit(embed = embed)

        # if a video link was given
        if audio_type == "url":
            audio_bytes = None

            # get video information
            video = await self.yt_extract(audio)

            if type(video) is str:
                error_msg = video
                return await ctx.send(err.YT_ERROR(error_msg))

            stream_url = video["url"]
            duration = video["duration"]
            video_title = video["title"]

            audio_source = video_title

        # if an mp3 file was given
        elif audio_type == "file":
            # download the video as a temporary file and get its duration
            audio_bytes = await audio.read()

            # get mp3 duration
            duration, returncode = await run_cmd(ff.GET_DURATION, audio_bytes, decode = True)

            if returncode != 0:
                return await ctx.send(err.FFMPEG_ERROR)

            duration = int(float(duration))
            audio_source = audio.filename

        duration_text = format_time(sec = duration)

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
        embed.title = f"{bot.PROCESSING()} making video..."
        embed.description = f"- Audio: **{audio_str}** `{duration_text}`\n- Length: `{length} seconds`"
        await processing.edit(embed = embed)

        # create two temporary files to use later on, with one being a video and the other being an image
        with TemporaryDirectory() as temp:
            with open(f"{temp}/input.png", "wb") as f_img:
                f_img.write(result.getvalue())

            source = "-" if audio_type == "file" else stream_url

            _, returncode = await run_cmd(ff.IMGAUDIO(temp, source, length), audio_bytes)

            if returncode != 0:
                await processing.delete()
                return await ctx.send(err.FFMPEG_ERROR)

            embed.title = f"{bot.PROCESSING()} sending video..."
            await processing.edit(embed = embed)

            # send the completed video
            try:
                await ctx.send(ctx.author.mention, file = discord.File(f"{temp}/output.mp4", f"{res.filename}.mp4"))

                embed.title = f"{bot.OK} finish"
                embed.color = discord.Color.brand_green()
                await processing.edit(embed = embed)
            except discord.HTTPException:
                await processing.edit(content = err.CANT_SEND_FILE, embed = None)

    @commands.command(usage = "[width]/auto *[height]/auto (gif/image/video)")
    async def resize(self, ctx: commands.Context, width = "auto", height = "auto"):
        """resizes the given attachment"""
        # if nothing is given
        if width == "auto" and height == "auto":
            raise commands.MissingRequiredArgument(ctx.command.params["width"])

        # if a given size is over 2000 pixels, send an error
        if any(x.isnumeric() and int(x) > 2000 for x in (width, height)):
            return await ctx.send(err.FILE_MAX_SIZE)

        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        # get either an image, gif, or video attachment
        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error: return await processing.edit(content = error)

        # if the attachment is a video
        if "video" in res.filetype:
            result = await EditVideo(res).resize((width, height))

            if not result:
                return await processing.edit(content = err.FFMPEG_ERROR)
        else:
            orig_size = await get_image_size(res.filebyte)

            if not orig_size:
                return await ctx.send(err.PIL_ERROR)

            orig_width, orig_height = orig_size

            # calculate "auto" sizes
            if height == "auto":
                wpercent = (int(width) / float(orig_width))
                height = int((float(orig_height) * float(wpercent)))
            elif width == "auto":
                hpercent = (int(height) / float(orig_height))
                width = int((float(orig_width) * float(hpercent)))

            new_size = (int(width), int(height))

            # resize the attachment depending on file type
            if "gif" in res.filetype:
                result = await EditGif(res).resize(new_size)
            else:
                result = await EditImage(res).resize(new_size)

        # send the resized attachment
        await send_media(ctx, processing, result, res.filetype)

    @commands.command(usage = "[text] (gif/image/video)")
    async def caption(self, ctx: commands.Context, *, text: str):
        """captions the specified gif or image in the style of iFunny's captions"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        # get either an image, gif, or tenor url
        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error: return await processing.edit(content = error)

        if "image" in res.filetype:
            size = await get_image_size(res.filebyte)
            size_error = err.PIL_ERROR
        else:
            size = await get_video_size(res.filebyte)
            size_error = err.FFMPEG_ERROR

        if not size:
            return await ctx.send(size_error)

        # now we start generating the caption image
        caption = await create_caption_text(text, size[0])

        # run respective functions for captioning gifs/images/videos

        if "gif" in res.filetype:
            result = await EditGif(res).caption(caption)
        elif "image" in res.filetype:
            result = await EditImage(res).caption(caption)
        else:
            result = await EditVideo(res).caption(caption)

            if not result:
                return await ctx.send(err.FFMPEG_ERROR)

        await send_media(ctx, processing, result, res.filetype)

    @commands.command(usage = "(gif/image/video)")
    async def uncaption(self, ctx: commands.Context):
        """removes the caption from the given attachment"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        # get either an image, gif, or tenor url
        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error: return await processing.edit(content = error)

        if "gif" in res.filetype:
            result = await EditGif(res).uncaption()
        elif "image" in res.filetype:
            result = await EditImage(res).uncaption()
        else:
            result = await EditVideo(res).uncaption()

            if not result:
                return await ctx.send(err.FFMPEG_ERROR)

        await send_media(ctx, processing, result, res.filetype)

    @commands.command(usage = "*[multiplier] (gif/video)")
    async def speed(self, ctx: commands.Context, amount: str = "1.25"):
        """speeds up a gif/video by a given amount (1.25x by default)"""
        try:
            # get valid multiplier
            amount = float(amount.strip("x"))
        except ValueError:
            error = err.INVALID_MULTIPLIER

            if bool(random.getrandbits(1)):
                error = error.replace("mult", "mark")

            return await ctx.send(error)

        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        res, error = await get_media(ctx, ["video", "gif"])
        if error: return await processing.edit(content = error)

        if "gif" in res.filetype:
            result = await EditGif(res).speed(amount)
        else:
            result = await EditVideo(res).speed(amount)

        await send_media(ctx, processing, result, res.filetype)

    @commands.command(usage = "[youtube-url] *[start-time] *[end-time]")
    async def get(self, ctx: commands.Context, url: str = None, start: str = None, end: str = None):
        """downloads a youtube video (or a part of it)"""
        # if the url is missing but the message is a reply, get it from the referenced message
        if (not url or not reg.youtube.match(url)) and (ref := ctx.message.reference):
            if (match := reg.youtube.search(ref.resolved.content)):
                # shift variables one place back
                end = start
                start = url
                url = match.group(0)
            else:
                return await ctx.send(err.INVALID_URL)

        if start and not end:
            # send error if an end time is not given
            raise commands.BadArgument()
        elif start and end:
            # see if timestamps are formatted correctly
            try:
                s_seconds = 0
                e_seconds = 0

                for x in start.split(":"):
                    s_seconds = s_seconds * 60 + int(x)

                for y in end.split(":"):
                    e_seconds = e_seconds * 60 + int(y)

            except ValueError:
                return await ctx.send(err.INVALID_TIMESTAMP)

            if (s_seconds - e_seconds) > 0:
                return await ctx.send(err.WEIRD_TIMESTAMPS)

        # send a message with ChoiceView buttons
        view = ChoiceView(ctx.author, ["video", "audio", "nvm"])
        msg = await ctx.send("what should be downloaded?", view = view)
        await view.wait()

        # if canceled
        if view.choice == "nvm":
            await msg.delete()
            await ctx.message.delete()
            return

        await msg.edit(content = f"{bot.PROCESSING()} downloading {view.choice}...", view = None)

        # get the stream url according to the user's choice
        video = await self.yt_extract(url, view.choice == "audio")

        if type(video) is str:
            error_msg = video
            return await msg.edit(content = err.YT_ERROR(error_msg))

        stream_url = video["url"]
        video_title = video["title"]
        ext = "mp3" if view.choice == "audio" else "mp4"

        with TemporaryDirectory() as temp:
            _, returncode = await run_cmd(ff.GET_STREAM(temp, stream_url, ext, start, end))

            # if the command failed
            if returncode != 0:
                await msg.delete()
                return await ctx.send(err.YT_ERROR("can get info just can't download"))

            # send the downloaded file
            try:
                await ctx.send(ctx.author.mention, file = discord.File(f"{temp}/output.{ext}", f"{video_title}.{ext}"))
            except discord.HTTPException:
                await ctx.send(err.CANT_SEND_FILE)

            await msg.delete()

async def setup(bot: Cade):
    await bot.add_cog(Media(bot))
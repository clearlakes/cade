import random
import asyncio
from asyncio import TimeoutError
from tempfile import TemporaryDirectory

import discord
from discord.ext import commands
from yt_dlp import DownloadError, YoutubeDL

from utils.base import CadeElegy, BaseCog, BaseEmbed
from utils.edit import edit
from utils.useful import check, format_time, get_media, run_async, run_cmd, send_media
from utils.vars import v
from utils.views import ChoiceView

from io import BytesIO
from os import listdir
from os.path import isfile, join
import mimetypes

from datetime import datetime, timezone

class Media(BaseCog):
    @run_async
    def video_download(self, loop, msg, url: str, start, end, video_format: str = "audio",   ):
        def _create_yt_hook(progress_msg, loop):
            class _Hook:
                def __init__(self):
                    self.last_edit = datetime.now(timezone.utc)
                
                async def _edit_progress(self, percent: str, msg: discord.Message):
                    await msg.edit(content=f"-# {v.EMJ__WAITING} downloading... {percent} complete")

                def yt_hook(self, info: dict[str, str]):
                    if info["status"] == "downloading":
                        new_status = info['_percent_str'].split(".")[0] + "%"
                        dt_now = datetime.now(timezone.utc)

                        if (dt_now - self.last_edit).total_seconds() > 1:
                            self.last_edit = dt_now
                            asyncio.run_coroutine_threadsafe(
                                coro=self._edit_progress(new_status, progress_msg), 
                                loop=loop
                            )
        
            return _Hook().yt_hook
        
        hook = _create_yt_hook(msg, loop)

        with TemporaryDirectory() as tmpdir:
            dl_opts = {
                "format": "best",
                "quiet": True,
                "noplaylist": True,
                "listformats": ("bsky" in url),
                "progress_hooks": [hook],
                "outtmpl": f"{tmpdir}/%(title)s.%(ext)s"
            }

            if video_format == "audio":
                dl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                }]
            
            if start and end:
                dl_opts["external_downloader"] = "ffmpeg"
                dl_opts["external_downloader_args"] = ["-c:v", "libx264", "-c:a", "aac", "-copyts", "-ss", start, "-to", end]

            try:
                with YoutubeDL(dl_opts) as ydl:
                    ydl.download(url)
            except DownloadError as e:
                # clean error and include it in the message
                dl_error = f"```{v.RE__COLOR.sub('', e.msg)}```"

                if "requested format is not available" in dl_error.lower():
                    return f"couldn't find a(n) {video_format} format"

                return f"\n{dl_error}"
            
            result_filename = [f for f in listdir(tmpdir) if isfile(join(tmpdir, f))][0]
            result_bytes = BytesIO()

            with open(f"{tmpdir}/{result_filename}", "rb") as f:
                result_bytes.write(f.read())

            result_bytes.seek(0)
            mime = mimetypes.guess_type(f"{tmpdir}/{result_filename}")[0]

            return (result_bytes, result_filename, mime)
        

    @commands.command(usage="(image)")
    async def jpeg(self, ctx: commands.Context):
        """lowers the quality of the given image"""
        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        # get an image from the user's message
        res, error = await get_media(ctx, ["image"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).jpeg()

        # send the created image
        await send_media(ctx, processing, result)

    @commands.command(aliases=["img"], usage="*[audio-url] *[seconds] (image)")
    async def imgaudio(
        self, ctx: commands.Context, url: str | None, length_given: str | None
    ):
        """converts an image into a video with audio"""
        mp3_types = ["audio/mpeg", "audio/mp3"]
        audio_type = None
        audio = None

        # switch length_given and url if getting the audio later on
        if url and url.isnumeric():
            length_given = url
            url = None
        elif url:
            audio_type = "url"
            audio = url

        # if a length is given, check if it's a number
        length_given = (
            int(length_given) if (length_given and length_given.isnumeric()) else None
        )

        # embed that will show the progress
        embed = BaseEmbed(title=v.BOT__PROCESSING_MSG())

        processing = await ctx.send(embed=embed)

        # get the image attachment
        res, error = await get_media(ctx, ["image"])
        if error:
            return await processing.edit(content=error, embed=None)

        if not url:
            # edit the embed to ask for audio
            embed.title = (
                f"{v.EMJ__WAITING} send a video url or an mp3 file to use as the audio"
            )
            embed.set_footer(text="or reply to any message that contains one")
            await processing.edit(embed=embed)

            # wait for a video url or mp3 file using the check_audio function
            try:
                response: discord.Message = await self.client.wait_for(
                    "message", check=check(ctx), timeout=600
                )
            except TimeoutError:
                return await processing.edit(content=v.ERR__TIMED_OUT, embed=None)

            msg = (
                response.reference.resolved
                if response.reference and not response.attachments
                else response
            )
            await response.delete()

            # see if the message contains an mp3 file or youtube url
            if any(
                (att := attachment).content_type in mp3_types
                for attachment in msg.attachments
            ):
                audio_type = "file"
                audio = att
            elif match := v.RE__URL.match(msg.content):
                url = match.group(0)
                audio_type = "url"
                audio = url
            else:
                # cancel if nothing was found
                return await processing.edit(content=v.ERR__NO_AUDIO_FOUND, embed=None)

        # edit the embed to show that it's in step 1
        embed.title = f"{v.EMJ__PROCESSING()} getting {audio_type} information..."
        embed.set_footer()

        await processing.edit(embed=embed)

        # if a video link was given
        if audio_type == "url":
            audio_bytes = None

            # get video information
            video = await self.video_download(audio)

            if type(video) is str:
                return await ctx.send(v.ERR__VID_DL_ERROR(video))

            stream_url, video_title, duration = video
            audio_source = video_title

        # if an mp3 file was given
        if audio_type == "file":
            # download the video as a temporary file and get its duration
            audio_bytes = await audio.read()

            # get mp3 duration
            duration, returncode = await run_cmd(
                v.FF__GET_DURATION, audio_bytes, decode=True
            )

            if returncode != 0:
                return await ctx.send(v.ERR__FFMPEG_ERROR)

            duration = int(float(duration))
            audio_source = audio.filename

        if type(duration) is int:
            # if a length was not given, use the audio source's length
            if length_given is None:
                # if the audio source's length is longer than 30 minutes, send an error
                if duration >= 1800:
                    return await processing.edit(
                        embed=None, content=v.ERR__AUDIO_MAX_LENGTH
                    )
                else:
                    length_given = duration

            duration = format_time(sec=duration)
        elif length_given is None:
            return await processing.edit(embed=None, content=v.ERR__NO_DURATION)

        audio_str = (
            f"[{audio_source}]({audio})" if audio_type == "url" else audio_source
        )

        # edit the embed to show that it's in step 2
        embed.title = f"{v.EMJ__PROCESSING()} making video..."
        embed.description = (
            f"- Audio: **{audio_str}** `{duration}`\n- Length: `{length_given} seconds`"
        )
        await processing.edit(embed=embed)

        # create two temporary files to use later on, with one being a video and the other being an image
        with TemporaryDirectory() as temp:
            with open(f"{temp}/input.png", "wb") as f_img:
                f_img.write(res.filebyte.getvalue())

            source = "-" if audio_type == "file" else stream_url

            _, returncode = await run_cmd(
                v.FF__IMGAUDIO(temp, source, length_given), audio_bytes
            )

            if returncode != 0:
                return await processing.edit(embed=None, content=v.ERR__FFMPEG_ERROR)

            embed.title = f"{v.BOT__PROCESSING_MSG} sending video..."
            await processing.edit(embed=embed)

            # send the completed video
            try:
                await ctx.send(
                    ctx.author.mention,
                    file=discord.File(f"{temp}/output.mp4", f"{res.filename}.mp4"),
                )

                embed.title = f"{v.EMJ__OK} finish"
                embed.color = discord.Color.brand_green()
                await processing.edit(embed=embed)
            except discord.HTTPException:
                await processing.edit(content=v.ERR__CANT_SEND_FILE, embed=None)

    @commands.command(usage="[width]/auto *[height]/auto (gif/image/video)")
    async def resize(self, ctx: commands.Context, width: str, height: str = v.RESIZE__AUTO_SIZE):
        """resizes the given attachment"""
        # send error if width/height is over max size in pixels
        if any(x.isnumeric() and int(x) > 2000 for x in (width, height)):
            return await ctx.send(v.ERR__FILE_MAX_SIZE)

        # set variables to -2 (auto) if a number isn't given
        if not width.isnumeric() or width == "0":
            width = v.RESIZE__AUTO_SIZE
        elif not height.isnumeric() or height == "0":
            height = v.RESIZE__AUTO_SIZE

        if width == v.RESIZE__AUTO_SIZE and height == "0":
            return await ctx.send(v.ERR__FILE_INVALID_SIZE)

        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        # get either an image, gif, or video attachment
        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error:
            return await processing.edit(content=error)

        # calculate "auto" sizes
        if orig_size := edit(res).file.size:
            match (width, height):
                case (v.RESIZE__AUTO_SIZE, v.RESIZE__AUTO_SIZE):  # raise error if both are auto
                    raise commands.MissingRequiredArgument(ctx.command.params["width"])
                case (v.RESIZE__AUTO_SIZE, _):  # needs width
                    new_height = int(height)
                    hpercent = new_height / orig_size[1]
                    new_width = round(orig_size[0] * hpercent)
                case (_, v.RESIZE__AUTO_SIZE):  # needs height
                    new_width = int(width)
                    wpercent = new_width / orig_size[0]
                    new_height = round(orig_size[1] * wpercent)
                case (_, _):
                    new_width = int(width)
                    new_height = int(height)

        result = await edit(res).resize((new_width, new_height))

        # send the resized attachment
        await send_media(ctx, processing, result)

    @commands.command(usage="[text] (gif/image/video)")
    async def caption(self, ctx: commands.Context, *, text: str):
        """captions the specified gif or image in the style of iFunny's captions"""
        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).caption(text)

        await send_media(ctx, processing, result)

    @commands.command(usage="(gif/image/video)")
    async def uncaption(self, ctx: commands.Context):
        """removes the caption from the given attachment"""
        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).uncaption()

        await send_media(ctx, processing, result)

    @commands.command(usage="*[multiplier] (gif/video)")
    async def speed(self, ctx: commands.Context, amount: str = "1.25"):
        """speeds up a gif/video by a given amount (1.25x by default)"""
        try:
            # get valid multiplier
            amount = float(amount.strip("x"))
        except ValueError:
            error = v.ERR__INVALID_MULTIPLIER

            if bool(random.getrandbits(1)):
                error = error.replace("mult", "mark")

            return await ctx.send(error)

        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        res, error = await get_media(ctx, ["video", "gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).speed(amount)

        await send_media(ctx, processing, result)

    @commands.command(usage="[media-url] *[start-time] *[end-time]")
    async def get(
        self, ctx: commands.Context, url: str, start: str | None, end: str | None
    ):
        """downloads a video (or part of it) from supported urls: `.get supported`"""
        # if the url is missing but the message is a reply, get it from the referenced message

        if url == "supported":
            return await ctx.send(
                "`.get` [list of supported sites](<https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md>) (via yt-dlp)"
            )

        if not v.RE__URL.match(url):
            return await ctx.send(v.ERR__INVALID_URL)

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
                return await ctx.send(v.ERR__INVALID_TIMESTAMP)

            if (s_seconds - e_seconds) > 0:
                return await ctx.send(v.ERR__WEIRD_TIMESTAMPS)

        # send a message with ChoiceView buttons
        view = ChoiceView(ctx.author, ["video", "audio", "nvm"])
        msg = await ctx.send("what should be downloaded?", view=view)
        await view.wait()

        # if canceled
        if view.choice == "nvm":
            await msg.delete()
            return

        await msg.edit(
            content=f"-# {v.EMJ__WAITING} downloading...", view=None
        )

        loop = asyncio.get_running_loop()
        result = await self.video_download(loop, msg, url, start, end, view.choice)

        if type(result) is str:
            return await msg.edit(content=v.ERR__VID_DL_ERROR(result))
        
        await send_media(ctx, msg, result)        

    @commands.command(usage="(gif)")
    async def reverse(self, ctx: commands.Context):
        """reverses a gif"""
        processing = await ctx.send(v.BOT__PROCESSING_MSG())

        res, error = await get_media(ctx, ["gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).reverse()

        await send_media(ctx, processing, result)


async def setup(bot: CadeElegy):
    await bot.add_cog(Media(bot))

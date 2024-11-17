import random
from asyncio import TimeoutError
from tempfile import TemporaryDirectory

import discord
from discord.ext import commands
from yt_dlp import DownloadError, YoutubeDL

from utils.base import CadeElegy, BaseCog, BaseEmbed
from utils.edit import edit
from utils.useful import check, format_time, get_media, run_async, run_cmd, send_media
from utils.vars import bot, err, ff, reg
from utils.views import ChoiceView


class Media(BaseCog):
    @run_async
    def video_extract(self, url: str, video_format: str = "audio"):
        dl_opts = {
            "format": f"best{video_format}",
            "quiet": True,
            "noplaylist": True,
            "listformats": ("bsky" in url),
        }

        try:
            with YoutubeDL(dl_opts) as ydl:
                results = ydl.extract_info(url, download=False)

                if dl_opts["listformats"]:
                    return results["formats"][0]["url"], results["title"], "??:??"
                else:
                    return results["url"], results["title"], results["duration"]
        except DownloadError as e:
            # clean error and include it in the message
            dl_error = f"```{reg.COLOR.sub('', e.msg).split(':')[2].strip()}```"

            if "requested format is not available" in dl_error.lower():
                return f"couldn't find a {video_format} format"

            return f"idk but read this:\n{dl_error}"

    @commands.command(usage="(image)")
    async def jpeg(self, ctx: commands.Context):
        """lowers the quality of the given image"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

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
        embed = BaseEmbed(title=f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        processing = await ctx.send(embed=embed)

        # get the image attachment
        res, error = await get_media(ctx, ["image"])
        if error:
            return await processing.edit(content=error, embed=None)

        if not url:
            # edit the embed to ask for audio
            embed.title = (
                f"{bot.WAITING} send a video url or an mp3 file to use as the audio"
            )
            embed.set_footer(text="or reply to any message that contains one")
            await processing.edit(embed=embed)

            # wait for a video url or mp3 file using the check_audio function
            try:
                response: discord.Message = await self.client.wait_for(
                    "message", check=check(ctx), timeout=600
                )
            except TimeoutError:
                return await processing.edit(content=err.TIMED_OUT, embed=None)

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
            elif match := reg.URL.match(msg.content):
                url = match.group(0)
                audio_type = "url"
                audio = url
            else:
                # cancel if nothing was found
                return await processing.edit(content=err.NO_AUDIO_FOUND, embed=None)

        # edit the embed to show that it's in step 1
        embed.title = f"{bot.PROCESSING()} getting {audio_type} information..."
        embed.set_footer()

        await processing.edit(embed=embed)

        # if a video link was given
        if audio_type == "url":
            audio_bytes = None

            # get video information
            video = await self.video_extract(audio)

            if type(video) is str:
                return await ctx.send(err.VID_DL_ERROR(video))

            stream_url, video_title, duration = video
            audio_source = video_title

        # if an mp3 file was given
        if audio_type == "file":
            # download the video as a temporary file and get its duration
            audio_bytes = await audio.read()

            # get mp3 duration
            duration, returncode = await run_cmd(
                ff.GET_DURATION, audio_bytes, decode=True
            )

            if returncode != 0:
                return await ctx.send(err.FFMPEG_ERROR)

            duration = int(float(duration))
            audio_source = audio.filename

        if type(duration) is int:
            # if a length was not given, use the audio source's length
            if length_given is None:
                # if the audio source's length is longer than 30 minutes, send an error
                if duration >= 1800:
                    return await processing.edit(
                        embed=None, content=err.AUDIO_MAX_LENGTH
                    )
                else:
                    length_given = duration

            duration = format_time(sec=duration)
        elif length_given is None:
            return await processing.edit(embed=None, content=err.NO_DURATION)

        audio_str = (
            f"[{audio_source}]({audio})" if audio_type == "url" else audio_source
        )

        # edit the embed to show that it's in step 2
        embed.title = f"{bot.PROCESSING()} making video..."
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
                ff.IMGAUDIO(temp, source, length_given), audio_bytes
            )

            if returncode != 0:
                return await processing.edit(embed=None, content=err.FFMPEG_ERROR)

            embed.title = f"{bot.PROCESSING()} sending video..."
            await processing.edit(embed=embed)

            # send the completed video
            try:
                await ctx.send(
                    ctx.author.mention,
                    file=discord.File(f"{temp}/output.mp4", f"{res.filename}.mp4"),
                )

                embed.title = f"{bot.OK} finish"
                embed.color = discord.Color.brand_green()
                await processing.edit(embed=embed)
            except discord.HTTPException:
                await processing.edit(content=err.CANT_SEND_FILE, embed=None)

    @commands.command(usage="[width]/auto *[height]/auto (gif/image/video)")
    async def resize(self, ctx: commands.Context, width: str, height: str = "-2"):
        """resizes the given attachment"""
        # send error if width/height is over max size in pixels
        if any(x.isnumeric() and int(x) > 2000 for x in (width, height)):
            return await ctx.send(err.FILE_MAX_SIZE)

        # set variables to -2 (auto) if a number isn't given
        if not width.isnumeric() or width == "0":
            width = "-2"
        elif not height.isnumeric() or height == "0":
            height = "-2"

        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        # get either an image, gif, or video attachment
        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error:
            return await processing.edit(content=error)

        # calculate "auto" sizes
        if orig_size := edit(res).dimensions:
            match (width, height):
                case ("-2", "-2"):  # raise error if both are auto
                    raise commands.MissingRequiredArgument(ctx.command.params["width"])
                case ("-2", _):  # needs width
                    new_height = int(height)
                    hpercent = new_height / orig_size[1]
                    new_width = round(orig_size[0] * hpercent)
                case (_, "-2"):  # needs height
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
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        res, error = await get_media(ctx, ["image", "video", "gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).caption(text)

        await send_media(ctx, processing, result)

    @commands.command(usage="(gif/image/video)")
    async def uncaption(self, ctx: commands.Context):
        """removes the caption from the given attachment"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

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
            error = err.INVALID_MULTIPLIER

            if bool(random.getrandbits(1)):
                error = error.replace("mult", "mark")

            return await ctx.send(error)

        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

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

        if not reg.URL.match(url):
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
        msg = await ctx.send("what should be downloaded?", view=view)
        await view.wait()

        # if canceled
        if view.choice == "nvm":
            await msg.delete()
            return

        await msg.edit(
            content=f"{bot.PROCESSING()} downloading {view.choice}...", view=None
        )

        # get the stream url according to the user's choice
        video = await self.video_extract(url, view.choice)

        if type(video) is str:
            return await msg.edit(content=err.VID_DL_ERROR(video))

        stream_url, video_title, _ = video
        ext = "mp3" if view.choice == "audio" else "mp4"

        with TemporaryDirectory() as temp:
            _, returncode = await run_cmd(
                ff.GET_STREAM(temp, stream_url, ext, start, end)
            )

            # if the command failed
            if returncode != 0:
                await msg.delete()
                return await ctx.send(err.VID_DL_ERROR("maybe not supported?"))

            # send the downloaded file
            try:
                await ctx.send(
                    ctx.author.mention,
                    file=discord.File(f"{temp}/output.{ext}", f"{video_title}.{ext}"),
                )
            except discord.HTTPException:
                await ctx.send(err.CANT_SEND_FILE)

            await msg.delete()

    @commands.command(usage="(gif)")
    async def reverse(self, ctx: commands.Context):
        """reverses a gif"""
        processing = await ctx.send(f"{bot.PROCESSING()} {bot.PROCESSING_MSG()}")

        res, error = await get_media(ctx, ["gif"])
        if error:
            return await processing.edit(content=error)

        result = await edit(res).reverse()

        await send_media(ctx, processing, result)


async def setup(bot: CadeElegy):
    await bot.add_cog(Media(bot))

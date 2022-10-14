from discord.ext import commands

from utils.useful import (
    get_tweet_attachments,
    get_attachment_obj,
    get_media_ids,
    get_twt_url
)
from utils.clients import Keys, get_twitter_client
from utils.data import err, bot, reg
from utils.views import ReplyView
from utils.base import BaseCog
from utils.main import Cade

from tempfile import NamedTemporaryFile as create_temp
from tweepy import TweepyException, NotFound
from io import BytesIO
from PIL import Image

class Funny(BaseCog):
    def __init__(self, client: Cade):
        super().__init__(client)

        if Keys.twitter:
            self.client.twitter_api = get_twitter_client()
            self.handle: str = self.client.twitter_api.verify_credentials().screen_name

        if not self.client.twitter_api:
            self.client.log.warning("can't use twitter commands, missing twitter api keys")

            for cmd in self.get_commands():
                cmd.enabled = False

    async def cog_check(self, ctx: commands.Context):
        # check if command is sent from funny museum
        if ctx.guild.id != 783166876784001075:
            await ctx.send(err.FUNNY_ONLY)
            return False
        else:
            return True

    async def get_tweet_content(self, ctx: commands.Context, status: str | None):
        media_type, attachments = await get_tweet_attachments(ctx)

        if not status and not attachments:
            # send error with the last parameter of the command (usually "content")
            raise commands.MissingRequiredArgument(list(ctx.command.params.values())[-1])

        return status, get_media_ids(self.client.twitter_api, media_type, attachments)

    @commands.command(usage = "[message]")
    async def tweet(self, ctx: commands.Context, *, content: str | None):
        """tweets out a message"""
        status, media_ids = await self.get_tweet_content(ctx, content)

        # sends the tweet
        try:
            new_status = self.client.twitter_api.update_status(status = status, media_ids = media_ids)
        except TweepyException:
            return await ctx.send(err.TWEET_ERROR)

        # tweet sent! so cool
        await ctx.send(
            f"{bot.OK} {get_twt_url(self.handle, new_status.id)}",
            view = ReplyView(self.client.twitter_api, new_status.id)
        )

    @commands.command(usage = "[tweet-id]/latest [message]")
    async def reply(self, ctx: commands.Context, reply_to: str | int, *, content: str | None):
        """replies to a given tweet by its url/id (or the latest tweet)"""
        status, media_ids = await self.get_tweet_content(ctx, content)
        is_chain = False

        # checks if the user wants to reply to a tweet that is in a different message
        if ctx.message.reference and not reg.twitter.match(reply_to):
            # .reply hello there
            #          ^ this is not intended to be used as the reply id, so add it to the existing status
            status = f"{reply_to} {status}" if status else reply_to
            reply_to = ctx.message.reference.resolved.content
            is_chain = True

        # if reply_to is not numeric, treat it as a url
        if not reply_to.isnumeric():
            # except if it's "latest", then use the latest tweet
            if reply_to == "latest":
                reply_id = self.client.twitter_api.user_timeline(screen_name = self.handle, count = 1)[0].id
            else:
                url = reg.twitter.search(reply_to)

                if url is None:
                    return await ctx.send(err.TWEET_URL_NOT_FOUND)

                reply_id = int(url.group(2))
        else:
            # if an id is given
            reply_id = int(reply_to)

        # send the reply
        try:
            new_status = self.client.twitter_api.update_status(
                status = status,
                media_ids = media_ids,
                in_reply_to_status_id = reply_id,
                auto_populate_reply_metadata = True
            )
        except NotFound:
            return await ctx.send(err.TWEET_NOT_FOUND)
        except TweepyException:
            return await ctx.send(err.TWEET_ERROR)

        view = ReplyView(self.client.twitter_api, new_status.id)

        if not is_chain:
            await ctx.send(
                f"{bot.OK} replied with {get_twt_url(self.handle, new_status.id)}",
                view = view
            )
        else:
            await ctx.message.delete()
            await ctx.message.reference.resolved.reply(
                f"{ctx.author.mention} replied with {get_twt_url(self.handle, new_status.id)}",
                view = view
            )

    @commands.command(aliases = ["pf"], usage = "profile/banner (image)")
    async def profile(self, ctx: commands.Context, kind: str):
        """replaces the profile/banner of the twita account"""
        att = get_attachment_obj(ctx)

        if not att:
            return await ctx.send(err.NO_ATTACHMENT_FOUND)

        if "image" in att.content_type and att.content_type.split("/")[1] not in ("gif", "apng"):
            processing = await ctx.send(f"{bot.PROCESSING()} resizing image...")

            img = Image.open(BytesIO(await att.read()))

            try:
                with create_temp(suffix = ".png") as temp:
                    # resize into a square for pfp
                    if kind in ("p", "picture"):
                        kind = "picture"

                        img = img.convert("RGBA").resize((512, 512))

                        img.save(temp.name, format = "PNG")
                        self.client.twitter_api.update_profile_image(filename = temp.name)

                    # resize into a rectangle for banner
                    elif kind in ("b", "banner"):
                        kind = "banner"

                        img = img.convert("RGBA").resize((1500, 500))

                        img.save(temp.name, format = "PNG")
                        self.client.twitter_api.update_profile_banner(filename = temp.name)

                    else:
                        await processing.delete()
                        raise commands.BadArgument()
            except TweepyException:
                await processing.delete()
                return await ctx.send(err.TWITTER_PROFILE_ERROR)

            await processing.delete()

            # it worked
            await ctx.send(f"{bot.OK} set profile {kind}:\n{get_twt_url(self.handle)}")
        else:
            return await ctx.send(err.WRONG_ATT_TYPE)

async def setup(bot: Cade):
    await bot.add_cog(Funny(bot))
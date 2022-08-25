import discord
from discord.ext import commands

from utils.functions import get_attachment_obj, get_tweet_attachments, get_media_ids
from utils.dataclasses import err, emoji, reg
from utils.clients import Clients, handle
from utils.views import ReplyView

from tempfile import NamedTemporaryFile as create_temp
from tweepy import NotFound
from typing import Union
from io import BytesIO
from PIL import Image

class TweetContent(commands.Converter):
    async def convert(self, ctx: commands.Context, arg: str = None):
        media_type, attachments = await get_tweet_attachments(ctx)

        if not arg and not attachments:
            # send error with the last parameter of the command (usually 'content')
            raise commands.MissingRequiredArgument(list(ctx.command.params.values())[-1])

        return arg, get_media_ids(media_type, attachments)

class Funny(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client
        self.api = Clients().twitter()

        self.react_roles = {
            "1️⃣": 820126482684313620,  # he/him
            "2️⃣": 820126584442322984,  # she/her
            "3️⃣": 820126629945933874,  # they/them
        }

    async def cog_check(self, ctx: commands.Context):
        # check if command is sent from funny museum
        if ctx.guild.id != 783166876784001075:
            await ctx.send(err.FUNNY_ONLY)
            return False
        else:
            return True

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.react_roles[event.emoji.name])

            # add the corresponding role from the reaction
            await event.member.add_roles(role)
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild = self.client.get_guild(event.guild_id)
            role = guild.get_role(self.react_roles[event.emoji.name])

            # remove the corresponding role
            member = guild.get_member(event.user_id)
            await member.remove_roles(role)

    @commands.command(usage = "[message]")
    async def tweet(self, ctx: commands.Context, *, content: TweetContent):
        """tweets out a message"""
        status, media_ids = content
        
        # sends the tweet
        try:
            new_status = self.api.update_status(status=status, media_ids=media_ids)
        except Exception:
            return await ctx.send(err.TWEET_ERROR)
        
        # tweet sent! so cool
        msg = await ctx.send(f"{emoji.OK} **Tweet sent:**\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(ctx, msg, new_status.id)
        await msg.edit(view = view)

    @commands.command(usage = "[tweet-id]/latest [message]")
    async def reply(self, ctx: commands.Context, reply_to: Union[str, int], *, content: TweetContent):
        """replies to a given tweet by its url/id (or the latest tweet)"""
        status, media_ids = content
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
                reply_id = self.api.user_timeline(screen_name = handle, count = 1)[0].id
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
            new_status = self.api.update_status(status=status, media_ids=media_ids, in_reply_to_status_id=reply_id, auto_populate_reply_metadata=True)
        except NotFound:
            return await ctx.send(err.TWEET_URL_NOT_FOUND)
        except Exception:
            return await ctx.send(err.TWEET_ERROR)
        
        if not is_chain:
            replied_to = self.api.get_status(reply_id)
            msg = await ctx.send(f"{emoji.OK} **Reply sent:**\nhttps://twitter.com/{replied_to.user.screen_name}/status/{replied_to.id}\nhttps://twitter.com/{handle}/status/{new_status.id}")
        else:
            await ctx.message.delete()
            msg = await ctx.message.reference.resolved.reply(f"{ctx.author.mention} replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(ctx, msg, new_status.id)
        await msg.edit(view = view)
        
    @commands.command(aliases = ["pf"], usage = "profile/banner (image)")
    async def profile(self, ctx: commands.Context, kind: str):
        """replaces the profile/banner of the twita account"""
        att = get_attachment_obj(ctx)

        if not att:
            return await ctx.send(err.NO_ATTACHMENT_FOUND)

        if "image" in att.content_type and att.content_type.split("/")[1] not in ("gif", "apng"):
            processing = await ctx.send(f"{emoji.PROCESSING()} Resizing image...")

            img = Image.open(BytesIO(await att.read()))

            try:
                with create_temp(suffix=".png") as temp:
                    # resize into a square for pfp
                    if kind in ("p", "picture"):
                        kind = "picture"

                        img = img.convert('RGBA').resize((512, 512))

                        img.save(temp.name, format="PNG")
                        self.api.update_profile_image(filename=temp.name)

                    # resize into a rectangle for banner
                    elif kind in ("b", "banner"):
                        kind = "banner"

                        img = img.convert('RGBA').resize((1500, 500))

                        img.save(temp.name, format="PNG")
                        self.api.update_profile_banner(filename=temp.name)

                    else:
                        await processing.delete()
                        raise commands.BadArgument()
            except Exception:
                await processing.delete()
                return await ctx.send(err.TWITTER_PROFILE_ERROR)

            await processing.delete()
            
            # it worked
            await ctx.send(f"{emoji.OK} **The profile {kind} has been set:**\nhttps://twitter.com/{handle}")
        else:
            return await ctx.send(err.WRONG_ATT_TYPE)

async def setup(bot: commands.Bot):
    await bot.add_cog(Funny(bot))
import discord
from discord.ext import commands

from utils.functions import (
    clean_error, 
    get_attachment, 
    get_attachment_obj, 
    get_media_ids
)
from utils.variables import Clients, Regex as re, handle
from utils.views import ReplyView

from tempfile import NamedTemporaryFile as create_temp
from tweepy import NotFound
from typing import Union
from io import BytesIO
from PIL import Image

class Funny(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.api = Clients().twitter()
    
    async def cog_check(self, ctx):
        # check if command is sent from funny museum
        if ctx.guild.id != 783166876784001075:
            await ctx.send("**Error:** that command only works in funny museum")
            return False
        else:
            return True

    def get_reaction_role(self, emoji: discord.PartialEmoji, guild: discord.Guild):
        if emoji.name == "1️⃣":
            # selected "he/him"
            role = guild.get_role(820126482684313620)
        elif emoji.name == "2️⃣":
            # selected "she/her"
            role = guild.get_role(820126584442322984)
        elif emoji.name == "3️⃣":
            # selected "they/them"
            role = guild.get_role(820126629945933874)

        return role

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild: discord.Guild = self.client.get_guild(event.guild_id)

            # get the corresponding role from the reaction
            role = self.get_reaction_role(event.emoji, guild)
            await event.member.add_roles(role)
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, event: discord.RawReactionActionEvent):
        # check if the message being reacted to is the one from funny museum
        if event.message_id == 820147742382751785:
            guild: discord.Guild = self.client.get_guild(event.guild_id)
            
            # get the corresponding role from the reaction
            role = self.get_reaction_role(event.emoji, guild)

            member = guild.get_member(event.user_id)
            await member.remove_roles(role)

    @commands.command()
    async def tweet(self, ctx: commands.Context, *, status: str = None):
        """Tweets any message from discord"""
        content_given = await get_attachment(ctx)

        # gets the media ids to use if an attachment is found
        if content_given != False:
            media_ids = get_media_ids(content_given)
        else:
            if status is None:
                raise commands.BadArgument()

            media_ids = None
        
        # sends the tweet
        try:
            new_status = self.api.update_status(status=status, media_ids=media_ids)
        except Exception as e:
            return await ctx.send(f"**Error:** could not send tweet (full error: ||{clean_error(e)}||)")
        
        # tweet sent! so cool
        msg = await ctx.send(f"{self.client.ok} **Tweet sent:**\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(ctx, msg, new_status.id)
        await msg.edit(view = view)

    @commands.command()
    async def reply(self, ctx: commands.Context, reply_to: Union[str, int] = None, *, status: str = None):
        """Replies to a given tweet"""
        is_chain = False

        # checks if the user wants to reply to a tweet that is in a different message
        if ctx.message.reference and not re.twitter.match(reply_to):
            # .reply hello there
            #          ^ this is not intended to be used as the reply id, so add it to the existing status
            status = f"{reply_to} {status}" if status else reply_to
            reply_to = ctx.message.reference.resolved.content
            is_chain = True
        
        # if nothing is given at all
        if reply_to is None:
            raise commands.BadArgument()
        
        # if reply_to is not numeric, treat it as a url
        if not reply_to.isnumeric():
            # except if it's "latest", then use the latest tweet
            if reply_to == "latest":
                reply_id = self.api.user_timeline(screen_name = handle, count = 1)[0].id
            else:
                url = re.twitter.search(reply_to)
                
                if url is None:
                    return await ctx.send("**Error:** could not find tweet url/id")
                
                reply_id = int(url.group(2))
        else:
            # if an id is given
            reply_id = int(reply_to)

        content_given = await get_attachment(ctx)

        # check for attachments and create media ids
        if content_given != False:
            media_ids = get_media_ids(content_given)
        else:
            if status is None:
                return commands.BadArgument()

            media_ids = None
        
        # send the reply
        try:
            new_status = self.api.update_status(status=status, media_ids=media_ids, in_reply_to_status_id=reply_id, auto_populate_reply_metadata=True)
        except NotFound:
            return await ctx.send("**Error:** could not find tweet from the given url/id")
        except Exception as e:
            return await ctx.send(f"**Error:** could not send tweet (full error: ||{clean_error(e)}||)")
        
        if not is_chain:
            replied_to = self.api.get_status(reply_id)
            msg = await ctx.send(f"{self.client.ok} **Reply sent:**\nhttps://twitter.com/{replied_to.user.screen_name}/status/{replied_to.id}\nhttps://twitter.com/{handle}/status/{new_status.id}")
        else:
            await ctx.message.delete()
            msg = await ctx.message.reference.resolved.reply(f"{ctx.author.mention} replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(ctx, msg, new_status.id)
        await msg.edit(view = view)
        
    @commands.command(aliases=['pf'])
    async def profile(self, ctx: commands.Context, kind: str = None):
        """Changes the twitter account's profile picture/banner"""
        if kind is None:
            raise commands.BadArgument()

        att = await get_attachment_obj(ctx)

        if not att:
            return await ctx.send("no image attachment was found")

        # if an image is given
        if "image" in att.content_type and any(att.content_type != x for x in ["image/gif", "image/apng"]):
            processing = await ctx.send(f"{self.client.loading} Resizing image...")

            img = Image.open(BytesIO(await att.read()))

            try:
                with create_temp(suffix=".png") as temp:
                    # resize into a square for pfp
                    if any(kind == x for x in ["p", "picture"]):
                        kind = "picture"

                        img = img.convert('RGBA').resize((512, 512))

                        img.save(temp.name, format="PNG")
                        self.api.update_profile_image(filename=temp.name)

                    # resize into a rectangle for banner
                    elif any(kind == x for x in ["b", "banner"]):
                        kind = "banner"

                        img = img.convert('RGBA').resize((1500, 500))

                        img.save(temp.name, format="PNG")
                        self.api.update_profile_banner(filename=temp.name)

                    else:
                        await processing.delete()
                        raise commands.BadArgument()
            except Exception as e:
                await processing.delete()
                return await ctx.send(f"**Error:** could not set profile {kind} (full error: ||{clean_error(e)}||)")

            await processing.delete()
            
            # it worked
            await ctx.send(f"{self.client.ok} **The profile {kind} has been set:**\nhttps://twitter.com/{handle}")
        else:
            return await ctx.send("**Error:** attachment is not an image")

def setup(bot):
    bot.add_cog(Funny(bot))
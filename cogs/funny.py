import discord
from typing import Union
from discord.ext import commands
from tempfile import NamedTemporaryFile as create_temp
from bot_vars import CancelView, twitter_rx, twitter_keys, handle, check, btn_check, escape_ansii, FFMPEG
from PIL import Image
import subprocess
import asyncio
import tweepy
import shlex
import io

# connect using the twitter keys in config
auth = tweepy.OAuthHandler(twitter_keys[0], twitter_keys[1])
auth.set_access_token(twitter_keys[2], twitter_keys[3])
api = tweepy.API(auth)

class ReplyView(discord.ui.View):
    def __init__(self, client, msg, reply_id):
        self.msg = msg
        self.client = client
        self.reply_id = reply_id
        super().__init__()

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.primary)
    async def reply(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = CancelView()
        view.children[0].label = "Cancel"

        await interaction.response.send_message("Send a message to use as the reply.", view = view, ephemeral = True)
        
        # get user input
        try:
            # wait for either a message or button press
            done, _ = await asyncio.wait([
                self.client.loop.create_task(self.client.wait_for('message', check=check(interaction), timeout=300)),
                self.client.loop.create_task(self.client.wait_for('interaction', check=btn_check(interaction), timeout=300))
            ], return_when=asyncio.FIRST_COMPLETED)
            
            for future in done:
                msg_or_interaction = future.result()

            # if there was a button press
            if isinstance(msg_or_interaction, discord.interactions.Interaction):
                if view.canceled: 
                    return await interaction.edit_original_message(content = "(canceled)", view = None)

            message = msg_or_interaction
        except asyncio.TimeoutError:
            await interaction.edit_original_message(content = "**Error:** timed out", view = None)

        await message.delete()
        
        ctx = await self.client.get_context(message)
        status = message.content
        
        # same procedure as a reply command
        content_given = await funny(self.client).get_attachment(ctx, interaction)

        if content_given != False:
            media_ids = funny(self.client).get_media_ids(content_given)
        else:
            media_ids = None
        
        # send the reply
        new_status = api.update_status(status=status, media_ids=media_ids, in_reply_to_status_id=self.reply_id, auto_populate_reply_metadata=True)

        await interaction.edit_original_message(content = "Replied!")

        # reply to the original message containing the tweet
        new_msg = await self.msg.reply(f"<@{interaction.user.mention}> replied:\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(self.client, new_msg, new_status.id)
        await new_msg.edit(view = view)

    # disable reply button on timeout
    async def on_timeout(self):
        self.children[0].style = discord.ButtonStyle.secondary
        self.children[0].disabled = True
        await self.msg.edit(view = self)

class funny(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    async def cog_check(self, ctx):
        # check if command is sent from funny museum
        if ctx.guild.id != 783166876784001075:
            await ctx.send("**Error:** that command only works in funny museum")
        else:
            return True
    
    async def get_attachment(self, ctx: commands.Context, interaction: discord.Interaction = None):
        """ Get the attachment to use for the tweet """
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
                        return ["gif", io.BytesIO(await att.read())]

                    att_bytes.append(io.BytesIO(await att.read()))
                    count += 1
                    continue
                
                if att.filename.lower().endswith("mov"):
                    # convert mov to mp4
                    with create_temp(suffix=".mov") as temp_mov, create_temp(suffix=".mp4") as temp_mp4:
                        if not interaction:
                            processing = await ctx.send(f"{self.client.loading} Processing...")
                        else:
                            processing = await interaction.edit_original_message(content = f"{self.client.loading} Processing...", view = None)

                        temp_mov.write(await att.read())
                        command = shlex.split(f'{FFMPEG} -i {temp_mov.name} -qscale 0 {temp_mp4.name}')
                        
                        p = subprocess.Popen(command)
                        p.wait()

                        # if there was an error running the ffmpeg command
                        if p.returncode != 0:
                            if not interaction:
                                await processing.edit("**Error:** there was an issue converting from mov to mp4")
                            else:
                                processing = await interaction.edit_original_message(content = "**Error:** there was an issue converting from mov to mp4")

                            return False
                        else:
                            return ["video", io.BytesIO(temp_mp4.read())]

                return ["video", io.BytesIO(await att.read())]

            return ["image", att_bytes]
    
    async def get_attachment_obj(self, ctx: commands.Context):
        """ For just getting the attachment only """
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
        
    def get_media_ids(self, content):
        """ Uploads the given content to twitter and gets the returned media id """
        media_ids = []
        result = content[0]
        media = content[1]

        # chooses between either uploading multiple images or just one video/gif
        if result == "image":
            for image in media:
                res = api.media_upload(image)
                media_ids.append(res.media_id)
        else:
            res = api.chunked_upload(media, media_category=f"tweet_{result}")
            media_ids.append(res.media_id)

        return media_ids

    @commands.command()
    async def tweet(self, ctx: commands.Context, *, status: str = None):
        """ Tweets any message from discord """
        content_given = await self.get_attachment(ctx)

        # gets the media ids to use if an attachment is found
        if content_given != False:
            media_ids = self.get_media_ids(content_given)
        else:
            if status is None:
                return await ctx.send("**Error:** usage: `.tweet [message]`")

            media_ids = None
        
        # sends the tweet
        try:
            new_status = api.update_status(status=status, media_ids=media_ids)
        except Exception as e:
            return await ctx.send(f"**Error:** could not send tweet (full error: ||{escape_ansii(e)}||)")
        
        # tweet sent! so cool
        msg = await ctx.send(f"{self.client.ok} **Tweet sent:**\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(self.client, msg, new_status.id)
        await msg.edit(view = view)

    @commands.command()
    async def reply(self, ctx: commands.Context, reply_to: Union[str, int] = None, *, status: str = None):
        """ Replies to a given tweet """
        # if the message is a reply, get the twitter link from the message it's replying to
        # i know this checks if reply_to is none but that is because the status will start from there if the twitter link is coming from the reply. it's weird
        if ctx.message.reference and reply_to is not None:
            status = str(reply_to) + status
            reply_to = ctx.message.reference.resolved
        else:
            # if nothing is given, and the message isn't a reply
            if reply_to is None:
                return await ctx.send("**Error:** usage: `.reply [tweet-id/url]/latest [message]`")
        
        # if reply_to is not numeric, treat it as a url
        if not reply_to.isnumeric():
            # except if it's "latest", then use the latest tweet
            if reply_to == "latest":
                reply_id = api.user_timeline(screen_name = handle, count = 1)[0].id
            else:
                url = twitter_rx.match(reply_to)
                
                if url is None:
                    return await ctx.send("**Error:** could not find tweet url/id")
                
                reply_id = int(url.group(2))
        else:
            # if an id is given
            reply_id = int(reply_to)

        content_given = await self.get_attachment(ctx)

        # check for attachments and create media ids
        if content_given != False:
            media_ids = self.get_media_ids(content_given)
        else:
            if status is None:
                return await ctx.send("**Error:** usage: `.reply [tweet-id/url]/latest [message]`")

            media_ids = None
        
        # send the reply
        try:
            new_status = api.update_status(status=status, media_ids=media_ids, in_reply_to_status_id=reply_id, auto_populate_reply_metadata=True)
        except tweepy.NotFound:
            return await ctx.send("**Error:** could not find tweet from the given url/id")
        except Exception as e:
            return await ctx.send(f"**Error:** could not send tweet (full error: ||{escape_ansii(e)}||)")
            
        replied_to = api.get_status(reply_id)

        msg = await ctx.send(f"{self.client.ok} **Reply sent:**\nhttps://twitter.com/{replied_to.user.screen_name}/status/{replied_to.id}\nhttps://twitter.com/{handle}/status/{new_status.id}")

        view = ReplyView(self.client, msg, new_status.id)
        await msg.edit(view = view)
        
    @commands.command(aliases=['pf'])
    async def profile(self, ctx: commands.Context, kind: str = None):
        """ Changes the twitter account's profile picture/banner """
        if kind is None:
            return await ctx.send("**Error:** usage: `.profile p/b (image)`")

        att = await self.get_attachment_obj(ctx)

        if att is False:
            embed = self.error_create("no image attachment was found")
            return await ctx.send(embed = embed)

        # if an image is given
        if "image" in att.content_type and any(att.content_type != x for x in ["image/gif", "image/apng"]):
            processing = await ctx.send(f"{self.client.loading} Resizing image...")

            img = Image.open(io.BytesIO(await att.read()))

            try:
                with create_temp(suffix=".png") as temp:
                    # resize into a square for pfp
                    if any(kind == x for x in ["p", "picture"]):
                        kind = "picture"

                        img = img.convert('RGBA').resize((512, 512))

                        img.save(temp.name, format="PNG")
                        api.update_profile_image(filename=att.filename, file=temp.name)

                    # resize into a rectangle for banner
                    elif any(kind == x for x in ["b", "banner"]):
                        kind = "banner"

                        img = img.convert('RGBA').resize((1500, 500))

                        img.save(temp.name, format="PNG")
                        api.update_profile_banner(filename=att.filename, file=temp.name)

                    else:
                        await processing.delete()
                        return await ctx.send("**Error:** usage: `.profile p/b (image)`")
            except Exception as e:
                return await ctx.send(f"**Error:** could not set profile {kind} (full error: ||{escape_ansii(e)}||)")

            await processing.delete()
            
            # it worked
            await ctx.send(f"{self.client.ok} **The profile {kind} has been set:**\nhttps://twitter.com/{handle}")
        else:
            return await ctx.send("**Error:** attachment is not an image")

def setup(bot):
    bot.add_cog(funny(bot))
import discord
from utils.bot_vars import db, g_id, url_rx
from discord.ext import commands
from datetime import timedelta
import subprocess
import traceback
import random
import shlex
import time
import json

class Dropdown(discord.ui.Select):
    def __init__(self, ctx):
        # dropdown options
        options = [
            discord.SelectOption(
                label="General",
                description="regular commands"
            ),
            discord.SelectOption(
                label="Music",
                description="so much groove"
            ),
            discord.SelectOption(
                label="Media",
                description="image and audio commands"
            )
        ]
        
        # add funny museum commands if guild matches the id
        if ctx.guild == 783166876784001075:
            options.extend([
                discord.SelectOption(
                    label="Funny Museum",
                    description="made for funny"
                )
            ])

        # placeholder and setup
        super().__init__(
            placeholder="select le category",
            min_values=1,
            max_values=1,
            options=options,
        )

    # callback runs whenever something is selected
    async def callback(self, interaction: discord.Interaction):
        # get information from category
        def get_help(cat):
            with open("commands.json", "r") as f:
                data = json.load(f)
            
            desc = ""
            for key in data[cat]:
                about = data[cat][key]["desc"]
                usage = data[cat][key]["usage"]
                
                # add backticks to each word in 'usage' if the usage isn't nothing
                if usage is not None: usage_str = ' `' + '` `'.join(usage.split()) + '`' if usage != '' else ''
                else: usage_str = ""

                # add the command to the description
                desc += f"**.{key}**{usage_str} - {about}\n"
            return desc
        
        selection = self.values[0]
        em = discord.Embed(color = 0x2f3136)
        em.title = f"Commands - {selection}"

        # edit embed when selection is made
        em.description = get_help(selection.lower())
        
        await interaction.response.edit_message(embed = em)

class DropdownView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()

        # build the dropdown list
        self.add_item(Dropdown(ctx))

class general(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # add guild to database on join
        db.insert_one({
            'guild_id': guild.id,
            'tags': {},
            'playlists': {},
            'welcome': {[None, None]}
        })
        print(f"added new guild to database ({guild.id}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        # remove guild from database on leave
        db.delete_one(g_id(guild.id))
        print(f"removed guild from database ({guild.id})")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        welcome_doc = db.find_one({"guild_id": member.guild.id, "welcome": {"$exists": True}})

        # if the 'welcome' field wasn't found
        if welcome_doc is None:
            return
            
        welcome_msg, channel_id = welcome_doc['welcome']

        # if the welcome message was disabled
        if welcome_msg is None:
            return

        # get channel from id stored in 'welcome'
        channel = await self.client.fetch_channel(channel_id)

        # insert mentions into message
        welcome_msg: str = welcome_msg.replace(r"{user}", member.mention)
        
        await channel.send(welcome_msg)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # if the error was from an invalid argument
        if isinstance(error, commands.BadArgument):
            with open("commands.json", "r") as f:
                data = json.load(f)
            
            cmd = ctx.command.name

            # get category and command information (from help command)
            cat, cmd = next(((cat, x) for cat, x in data.items() 
                for x in data[cat] if cmd == x or data[cat][x]["alt"] is not None 
                and any(cmd == alt for alt in data[cat][x]["alt"])))
                
            usage = data[cat][cmd]["usage"]

            # add space if usage is not empty
            if usage is not None: usage = f" {usage}"
            else: usage = ""

            return await ctx.send(f"**Error:** usage: `.{cmd}{usage}`")
        else:
            # print the error
            traceback.print_exception(type(error), error, error.__traceback__)
    
    @commands.command(aliases=["re"])
    @commands.is_owner()
    async def reload(self, ctx, cog_to_reload: str = None):
        processing = await ctx.send(f"{self.client.loading}")

        try:
            # reload all cogs if nothing is specified
            if cog_to_reload is None:
                for cog in ["funny", "general", "media", "music"]:
                    self.client.reload_extension(f"cogs.{cog}")
            else:
                # reload the specified extension
                self.client.reload_extension(f"cogs.{cog_to_reload.lower()}")
        except:
            return await ctx.send(f"**Error:** could not reload")
        
        await processing.delete()
        await ctx.message.add_reaction(self.client.ok)

    @commands.command(aliases=["u"])
    @commands.is_owner()
    async def update(self, ctx):
        processing = await ctx.send(f"{self.client.loading} looking for update...")

        # get the last update's information
        previous = subprocess.Popen(shlex.split(r"git rev-parse --short HEAD"), stdout=subprocess.PIPE).communicate()[0].decode('UTF_8')

        # get the latest update from the github repo
        update = subprocess.Popen(["git", "pull"], stdout=subprocess.PIPE).communicate()[0].decode('UTF-8')

        if "Already up to date." in update:
            return await processing.edit("**Already up to date!**")

        # reload cogs after update
        for cog in ["funny", "general", "media", "music"]:
            self.client.reload_extension(f"cogs.{cog}")

        # get information about new update
        get_commit_data = shlex.split(r"git log -1 --pretty=format:%h%x09%s")
        commit_data = subprocess.Popen(get_commit_data, stdout=subprocess.PIPE).communicate()[0].decode('UTF_8').split('\t')
        
        url = "https://github.com/source64/cade/commit/{}"

        embed = discord.Embed(
            description = f"{self.client.ok} **Updated bot: [`{previous}`]({url.format(previous)}) -> [`{commit_data[0]}`]({url.format(commit_data[0])})\n```fix\n{update}```"
        )

        await processing.edit(embed = embed)

    @commands.command()
    async def info(self, ctx: commands.Context):
        """ Gets information about the bot """
        wait = await ctx.send(f"{self.client.loading} Loading information..")

        # make embed
        embed = discord.Embed(
            description = f"made in the funny museum\nuse `.help` or `.help [command]` for help.\ncreated <t:1596846209:R>!",
            color = 0xd9ba93
        )

        # link to github
        embed.set_author(name="cade bot", url="https://github.com/source64/cade")

        # get the uptime by subtracting the current time by the time that was stored in client.initial
        current_time = time.time()
        difference = int(round(current_time - self.client.initial))
        uptime_str = str(timedelta(seconds=difference))

        # get the ping, which is client.latency times 1000 (for ms)
        ping = round(self.client.latency * 1000, 3)

        # get random picture from the client.cats list
        cat = random.choice(self.client.cats)
        embed.set_thumbnail(url=cat)

        # get the number of commands
        num_of_commands = len(self.client.commands)
        
        # add fields to embed
        embed.add_field(name="Uptime", value=f"`{uptime_str}`")
        embed.add_field(name="Ping (ms)", value=f"`{ping}`")
        embed.add_field(name="Commands", value=f"`{num_of_commands}`")
        
        # the commands below are used to get information about the latest (local) commit:
        # commit_num - get the total number of commits so far
        # commit_data - get the commit hash, timestamp, and message
        # commit_diff - get the number of commits that the bot hasn't pulled yet from the remote repo

        # split commands for use in subprocess
        get_commit_data = shlex.split(r"git log -1 --pretty=format:%h%x09%at%x09%s")
        get_commit_diff = shlex.split(r"git rev-list --left-right --count origin/main...main")
        get_commit_num = shlex.split(r"git rev-list --all --count")

        # get latest metadata
        subprocess.Popen(["git", "fetch"])

        # get subprocess result, turn it into a regular string, and split the string every time '\t' (tab character) is found
        commit_num = subprocess.Popen(get_commit_num, stdout=subprocess.PIPE).communicate()[0].decode('UTF_8').replace('\n', '')
        commit_data = subprocess.Popen(get_commit_data, stdout=subprocess.PIPE).communicate()[0].decode('UTF_8').split('\t')
        commit_diff = int(subprocess.Popen(get_commit_diff, stdout=subprocess.PIPE).communicate()[0].decode('UTF_8').split('\t')[0])
        
        # url that links to the commit
        commit_url = f"https://github.com/source64/cade/commit/{commit_data[0]}"

        # check if the bot is behind on updates
        if commit_diff > 0:
            extra = f"({commit_diff} update behind)" if commit_diff == 1 else f"({commit_diff} updates behind)"
        else:
            extra = '(up to date)'

        embed.add_field(name="Latest update (from github):", value=f"<t:{commit_data[1]}:R> [`#{commit_num}`]({commit_url}) - {commit_data[2]}", inline=False)
        
        embed.set_footer(text=f"version 3 • by steve859\n{extra}")

        await wait.delete()
        await ctx.send(embed = embed)

    @commands.command()
    async def help(self, ctx: commands.Context, cmd: str = None):
        """ Gets information about commands """
        embed = discord.Embed(color = self.client.gray)

        if cmd is None:
            # default embed to use
            embed.title = "Commands"
            embed.description = "Use the dropdown menu to select a command category.\n(command options that have an asterisk in front of them are optional)"

            # send message with dropdown
            view = DropdownView(ctx)
            return await ctx.send(embed = embed, view = view)

        cmd = cmd.lower()

        with open("commands.json", "r") as f:
            data = json.load(f)
        
        try:
            # for every category and item in that category, if the item itself is equal to the command given, or if one of
            # the item's "alt" values is equal to it, return both the name of the category and the item
            cat, cmd = next(((cat, x) for cat, x in data.items() for x in data[cat] if cmd == x or data[cat][x]["alt"] is not None and any(cmd == alt for alt in data[cat][x]["alt"])))
        except StopIteration:
            # if neither the item nor any of the "alt" values matched the command 
            return await ctx.send("**Error:** command not found")

        usage = data[cat][cmd]["usage"]

        # if the usage isn't nothing, format it
        if usage is not None: usage_str = '`' + '` `'.join(usage.split()) + '`' if usage != '' else ''
        else: usage_str = ""

        description = data[cat][cmd]["desc"]
        alt = data[cat][cmd]["alt"]

        embed.description = f"**.{cmd}** - {description}\n\nUsage: **.{cmd}** {usage_str}"
        embed.set_footer(text = f"category: {cat}")
        
        # format alts if there are any
        if alt is not None:
            alt = ", .".join(x for x in alt)
            embed.description += f"\nAliases: `.{alt}`"
        
        await ctx.send(embed = embed)

    @commands.command()
    async def echo(self, ctx: commands.Context, channel: discord.TextChannel, *, msg = None):
        """ Sends a given message as itself """
        # if nothing is given
        if msg is None and not ctx.message.attachments:
            return await ctx.send("**Error:** uhhh no message found")

        # if the user can't send messages in the given channel
        if channel.permissions_for(ctx.author).send_messages == False:
            return await ctx.send("**Error:** you're missing permissions")
        
        # repeat the message in the given channel
        try:
            file_array = [await x.to_file() for x in ctx.message.attachments]
            await channel.send(msg, files=file_array)
        except discord.Forbidden:
            return await ctx.send("**Error:** i can't do that, missing permissions")
        
        # react with ok
        await ctx.message.add_reaction(self.client.ok)

    @commands.command(aliases=['t'])
    async def tag(self, ctx: commands.Context, tag_name: str = None, *, tag_content: str = None):
        """ Creates/sends a tag """
        def get_attachment(ctx):
            # use the replied message if it's there
            if ctx.message.attachments:
                msg = ctx.message
            elif ctx.message.reference:
                msg = ctx.message.reference.resolved
            else:
                return False
            
            # find a url if there are no attachments
            if not msg.attachments:
                if url_rx.match(msg.content):
                    return url_rx.match(msg.content).group(0)
                else:
                    return False
            else:
                return msg.attachments[0].url
        
        # if nothing is given
        if tag_name is None:
            return await ctx.send("**Error:** usage: `.t [existing tag]` or `.t [new tag] [tag content]`")
        
        tag_doc = db.find_one({"guild_id": ctx.guild.id, "tags": {"$ne": None}})

        # if 'tags' is not in guild database, use an empty dict
        if tag_doc is None:
            data = {}
        else:
            data = tag_doc['tags']        
        
        # if only the name of a tag is given
        if tag_content is None:
            att_url = get_attachment(ctx)
            
            # if an attachment is given
            if att_url != False:
                if tag_name not in data.keys():
                    db.update_one(g_id(ctx), {'$set': {f'tags.{tag_name}': att_url}}, upsert = True)
                    return await ctx.send(f"{self.client.ok} Added tag `{tag_name}`")

            # post the tag if it exists, or if the tag was found from the last if statement
            if tag_name in data.keys():
                result = data[tag_name]
                new_res = str(result).replace("media.discordapp.net", "cdn.discordapp.com")
                return await ctx.send(new_res)
            else:
                return await ctx.send(f"**Error:** the tag `{tag_name}` has not been created yet")
        else:
            # if content is given
            if tag_name not in data.keys():
                att_url = get_attachment(ctx)

                if att_url is False:
                    new_tag = tag_content
                else:
                    new_tag = f"{att_url} {tag_content}"

                db.update_one(g_id(ctx), {'$set': {f'tags.{tag_name}': new_tag}}, upsert = True)
                return await ctx.send(f"{self.client.ok} Added tag `{tag_name}`")
            else:
                return await ctx.send(f"**Error:** the tag `{tag_name}` already exists")

    @commands.command(aliases=['tagdel', 'tdel'])
    async def tagdelete(self, ctx: commands.Context, tag: str = None):
        """ Deletes a given tag """
        if tag is None:
            return await ctx.send("**Error:** missing tag name")

        tag = str(tag).lower()

        tag_doc = db.find_one({"guild_id": ctx.guild.id, "tags": {"$ne": None}})

        # if 'tags' is not in guild database, use an empty dict
        if tag_doc is None:
            tags = {}
        else:
            tags = tag_doc['tags']

        # if the tag is not listed
        if tag not in tags:
            return await ctx.send("**Error:** tag not found")
        
        # remove the tag
        db.update_one(g_id(ctx), {'$unset': {f'tags.{tag}': 1}})
        db.update_one(g_id(ctx), {'$pull': {f'tags.{tag}': None}})

        await ctx.send(f"{self.client.ok} Removed tag `{tag}`")
    
    @commands.command(aliases=['tlist', 'tags'])
    async def taglist(self, ctx: commands.Context):
        """ Lists every tag """
        tag_doc = db.find_one({"guild_id": ctx.guild.id, "tags": {"$ne": None}})

        # if 'tags' is not in the guild database
        if tag_doc is None:
            return await ctx.send("**Error:** no tags were found")

        tags = tag_doc['tags']

        # if 'tags' is there, but empty
        if tags == {}:
            return await ctx.send("**Error:** no tags were found")

        # create list
        list = '**' + '**, **'.join(tags) + '**'

        embed = discord.Embed(
            title = "Tags:",
            description = list,
            color = self.client.gray
        )

        await ctx.send(embed = embed)
    
    @commands.command()
    @commands.has_permissions(administrator = True)
    async def welcome(self, ctx: commands.Context, channel: discord.TextChannel = None, *, msg: str = None):
        """ Sets the welcome message of the server """
        if channel is None:
            raise commands.BadArgument()

        # if nothing is given, disable the welcome message by setting it as None
        if not msg and not ctx.message.attachments:
            db.update_one(g_id(ctx), {'$set': {'welcome': [None, None]}}, upsert = True)
            return await ctx.send(f"{self.client.ok} disabled welcome message")

        # get attachment url if there is one
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            msg = msg + '\n' + att.url if msg else att.url

        # update 'welcome' with the given message and channel id
        db.update_one(g_id(ctx), {'$set': {'welcome': [msg, channel.id]}}, upsert = True)
        
        await ctx.send(f"{self.client.ok} set the welcome message and channel")

def setup(bot):
    bot.add_cog(general(bot))
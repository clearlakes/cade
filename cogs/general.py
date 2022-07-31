import discord
from discord.ext import commands

from utils.variables import Colors, Regex as re
from utils.views import DropdownView
from utils.functions import run
from utils.enums import err
from utils import database

from subprocess import Popen, PIPE
from datetime import timedelta
from random import choice
from shlex import split
from time import time
from json import load

class General(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # add guild to database on join
        database.Guild(guild).add()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        # remove guild from database on leave
        database.Guild(guild).remove()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        doc = database.Guild(member.guild).get()

        # if the welcome field wasn't found
        if doc.welcome is None:
            return
            
        welcome_msg, channel_id = doc.welcome

        # if the welcome message was disabled
        if welcome_msg is None:
            return

        # get channel from id stored in 'welcome'
        channel = await self.client.fetch_channel(channel_id)

        # insert mentions into message
        welcome_msg: str = welcome_msg.replace(r"{user}", member.mention)
        
        await channel.send(welcome_msg)
    
    @commands.command(aliases=["re"])
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog_to_reload: str = None):
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
            return await ctx.send(err.COG_RELOAD_ERROR.value)
        
        await processing.delete()
        await ctx.message.add_reaction(self.client.ok)

    @commands.command(aliases=["u"])
    @commands.is_owner()
    async def update(self, ctx: commands.Context):
        processing = await ctx.send(f"{self.client.loading} looking for update...")

        def get_info_from(cmd: str):
            return run(split(cmd))[0].decode('utf-8').strip('\n').replace("=", "-")

        # get the last update's information
        # .decode('UTF-8') - convert byte string to regular text
        # .replace('\n', '') - replace newlines with an empty space
        previous = get_info_from("git rev-parse --short HEAD")

        # check if on the latest commit
        if (utd := "already up to date") in get_info_from("git pull"):
            return await processing.edit(f"**{utd}**")

        # reload cogs after update
        for cog in ["funny", "general", "media", "music"]:
            self.client.reload_extension(f"cogs.{cog}")

        # get information about new update
        commit_data = get_info_from("git log -1 --pretty=format:%h%x09%s").split('\t')
        
        url = lambda commit: f"https://github.com/source64/cade/commit/{commit}"

        await processing.delete()

        embed = discord.Embed(
            description = f"{self.client.ok} **updated from [`{previous}`]({url(previous)}) to [`{commit_data[0]}`]({url(commit_data[0])})**"
        )

        await ctx.send(embed = embed)

    @commands.command()
    async def info(self, ctx: commands.Context):
        """Gets information about the bot"""
        wait = await ctx.send(f"{self.client.loading} Loading information..")

        # make embed
        embed = discord.Embed(
            description = f"made in the funny museum\nuse `.help` or `.help [command]` for help.\ncreated <t:1596846209:R>!",
            color = Colors.info
        )

        # link to github
        embed.set_author(name="cade bot", url="https://github.com/source64/cade")

        # get the uptime by subtracting the current time by the time that was stored in client.initial
        current_time = time()
        difference = int(round(current_time - self.client.initial))
        uptime_str = str(timedelta(seconds=difference))

        # get the ping, which is client.latency times 1000 (for ms)
        ping = round(self.client.latency * 1000, 3)

        # get random picture from the client.cats list
        cat = choice(self.client.cats)
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
        get_commit_data = split(r"git log -1 --pretty=format:%h%x09%at%x09%s")
        get_commit_diff = split(r"git rev-list --left-right --count origin/main...main")
        get_commit_num = split(r"git rev-list --all --count")

        # get latest metadata
        Popen(["git", "fetch"])

        # get subprocess result, turn it into a regular string, and split the string every time '\t' (tab character) is found
        commit_num = Popen(get_commit_num, stdout = PIPE).communicate()[0].decode('UTF_8').replace('\n', '')
        commit_data = Popen(get_commit_data, stdout = PIPE).communicate()[0].decode('UTF_8').split('\t')
        commit_diff = int(Popen(get_commit_diff, stdout = PIPE).communicate()[0].decode('UTF_8').split('\t')[0])
        
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
        """Gets information about commands"""
        embed = discord.Embed(color = Colors.gray)

        if cmd is None:
            # default embed to use
            embed.title = "Commands"
            embed.description = "Use the dropdown menu to select a command category.\n(command options that have an asterisk in front of them are optional)"

            # send message with dropdown
            view = DropdownView(ctx)
            return await ctx.send(embed = embed, view = view)

        cmd = cmd.lower()

        with open("commands.json", "r") as f:
            data = load(f)
        
        try:
            # for every category and item in that category, if the item itself is equal to the command given, or if one of
            # the item's "alt" values is equal to it, return both the name of the category and the item
            cat, cmd = next(((cat, x) for cat, x in data.items() for x in data[cat] if cmd == x or data[cat][x]["alt"] is not None and any(cmd == alt for alt in data[cat][x]["alt"])))
        except StopIteration:
            # if neither the item nor any of the "alt" values matched the command 
            return await ctx.send(err.HELP_NOT_FOUND.value)

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
        """Sends a given message as itself"""
        # if nothing is given, throw an error
        if msg is None and not ctx.message.attachments:
            raise commands.BadArgument()

        # if the user can't send messages in the given channel
        if channel.permissions_for(ctx.author).send_messages == False:
            return await ctx.send(err.NO_PERMISSIONS_USER.value)
        
        # repeat the message in the given channel
        try:
            file_array = [await x.to_file() for x in ctx.message.attachments]
            await channel.send(msg, files=file_array)
        except discord.Forbidden:
            return await ctx.send(err.NO_PERMISSIONS_BOT.value)
        
        # react with ok
        await ctx.message.add_reaction(self.client.ok)

    @commands.command(aliases=['t'])
    async def tag(self, ctx: commands.Context, tag_name: str = None, *, tag_content: str = None):
        """Creates/sends a tag"""
        def get_attachment(ctx: commands.Context):
            # use the replied message if it's there
            msg = ctx.message.reference.resolved if ctx.message.reference and not ctx.message.attachments else ctx.message
            
            # find a url if there are no attachments
            if not msg.attachments:
                if match := re.url.match(msg.content):
                    return match.group(0)
                else:
                    return False
            else:
                return msg.attachments[0].url
        
        # if nothing is given
        if tag_name is None:
            raise commands.BadArgument()
        
        db = database.Guild(ctx.guild)
        doc = db.get()

        # if 'tags' is not in guild database, use an empty dict
        data = doc.tags if doc.tags else {}  
        
        # if only the name of a tag is given
        if tag_content is None:
            att_url = get_attachment(ctx)
            
            # if an attachment is given
            if att_url != False:
                if tag_name not in data.keys():
                    db.add_obj('tags', tag_name, att_url)
                    return await ctx.send(f"{self.client.ok} Added tag `{tag_name}`")

            # post the tag if it exists, or if the tag was found from the last if statement
            if tag_name in data.keys():
                result = data[tag_name]
                new_res = str(result).replace("media.discordapp.net", "cdn.discordapp.com")
                return await ctx.send(new_res)
            else:
                return await ctx.send(err.TAG_DOESNT_EXIST.value)
        else:
            # if content is given
            if tag_name not in data.keys():
                att_url = get_attachment(ctx)

                if att_url is False:
                    new_tag = tag_content
                else:
                    new_tag = f"{att_url} {tag_content}"

                db.add_obj('tags', tag_name, new_tag)
                return await ctx.send(f"{self.client.ok} Added tag `{tag_name}`")
            else:
                return await ctx.send(err.TAG_EXISTS.value)

    @commands.command(aliases=['tagdel', 'tdel'])
    async def tagdelete(self, ctx: commands.Context, tag: str = None):
        """Deletes a given tag"""
        if tag is None:
            raise commands.BadArgument()

        tag = str(tag).lower()

        db = database.Guild(ctx.guild)
        doc = db.get()

        # if 'tags' is not in guild database, use an empty dict
        tags = doc.tags if doc.tags else {}

        # if the tag is not listed
        if tag not in tags:
            return await ctx.send(err.TAG_DOESNT_EXIST.value)
        
        # remove the tag
        db.del_obj('tags', tag)

        await ctx.send(f"{self.client.ok} Removed tag `{tag}`")
    
    @commands.command(aliases=['tlist', 'tags'])
    async def taglist(self, ctx: commands.Context):
        """Lists every tag in the guild"""
        db = database.Guild(ctx.guild)
        doc = db.get()

        # if 'tags' is empty or not in the guild database
        if not doc.tags:
            return await ctx.send(err.NO_TAGS_AT_ALL.value)

        tags = doc.tags

        # create list
        list = '**' + '**, **'.join(tags) + '**'

        embed = discord.Embed(
            title = "Tags:",
            description = list,
            color = Colors.gray
        )

        await ctx.send(embed = embed)
    
    @commands.command()
    @commands.has_permissions(administrator = True)
    async def welcome(self, ctx: commands.Context, channel: discord.TextChannel = None, *, msg: str = None):
        """Sets the welcome message of the server"""
        if channel is None:
            raise commands.BadArgument()

        db = database.Guild(ctx.guild)

        # if nothing is given, disable the welcome message by setting it as None
        if not msg and not ctx.message.attachments:
            db.set('welcome', [None, None])
            return await ctx.send(f"{self.client.ok} disabled welcome message")

        # get attachment url if there is one
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            msg = msg + '\n' + att.url if msg else att.url

        # update 'welcome' with the given message and channel id
        db.set('welcome', [msg, channel.id])
        
        await ctx.send(f"{self.client.ok} set the welcome message and channel")

def setup(bot):
    bot.add_cog(General(bot))
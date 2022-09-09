import discord
from discord.ext import commands

from utils.useful import get_attachment_obj, run_cmd
from utils.base import BaseCog, BaseEmbed
from utils.events import add_bot_events
from utils.data import err, colors, bot
from utils.ext import generate_cmd_list
from utils.views import HelpView
from utils.db import GuildDB
from utils.main import Cade

from datetime import datetime

class General(BaseCog):
    def __init__(self, client: Cade):
        super().__init__(client)

        add_bot_events(self.client)

    @commands.command(aliases = ["gen"], hidden = True)
    @commands.is_owner()
    async def generate(self, ctx: commands.Context = None):
        processing = await ctx.send(bot.PROCESSING())

        generate_cmd_list(self.client.cogs)

        await processing.edit(content = f"{bot.OK} created commands.md")

    @commands.command(aliases = ["re"], hidden = True)
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog_to_reload: str = None):
        processing = await ctx.send(bot.PROCESSING())

        try:
            if cog_to_reload is None:
                # reload all cogs if nothing is specified
                for cog in ["funny", "general", "media", "music"]:
                    await self.client.reload_extension(f"cogs.{cog}")
            else:
                # reload the specified extension
                await self.client.reload_extension(f"cogs.{cog_to_reload.lower()}")
        except commands.ExtensionError as e:
            return await ctx.send(err.COG_RELOAD_ERROR(e.name))

        await processing.delete()
        await ctx.message.add_reaction(bot.OK)

    @commands.command(aliases = ["u"], hidden = True)
    @commands.is_owner()
    async def update(self, ctx: commands.Context):
        processing = await ctx.send(f"{bot.PROCESSING()} looking for update...")

        # get the last update's information
        previous = (await run_cmd("git rev-parse --short HEAD", decode = True))[0]

        # check if on the latest commit
        if (utd := "Already up to date.") in (await run_cmd("git pull", decode = True))[0]:
            return await processing.edit(content = f"**{utd.lower().strip('.')}**")

        # reload cogs after update
        for cog in ["funny", "general", "media", "music"]:
            await self.client.reload_extension(f"cogs.{cog}")

        # get information about new update
        new_commit = (await run_cmd("git log -1 --pretty=format:%h%x09%s", decode = True))[0].split("\t")

        link_to = lambda commit: f"[`{commit}`](https://github.com/source64/cade/commit/{commit})"

        await processing.delete()

        embed = BaseEmbed(
            description = f"{bot.OK} **updated from {link_to(previous)} to {link_to(new_commit)}**"
        )
        await ctx.send(embed = embed)

    @commands.command()
    async def info(self, ctx: commands.Context):
        """get information about the bot"""
        wait = await ctx.send(f"{bot.PROCESSING()} loading...")

        # make embed
        embed = discord.Embed(
            description = "made in the funny museum\nuse `.help` or `.help [command]` for help.\ncreated <t:1596846209:R>!",
            color = colors.CADE
        )

        # link to github
        embed.set_author(name = "cade bot", url = "https://github.com/source64/cade")

        # get the uptime by subtracting the current time by the init time
        uptime = str(datetime.now() - self.client.init_time).split(".")[0]

        # get the ping, which is client.latency times 1000 (for ms)
        ping = round(self.client.latency * 1000, 3)

        # get random picture of cat
        embed.set_thumbnail(url = bot.CAT())

        # get the number of commands
        num_of_commands = len([x for x in self.client.commands if not x.hidden])

        # add fields to embed
        embed.add_field(name = "Uptime", value = f"`{uptime}`")
        embed.add_field(name = "Ping (ms)", value = f"`{ping}`")
        embed.add_field(name = "Commands", value = f"`{num_of_commands}`")

        # get latest metadata
        await run_cmd("git fetch")

        # get the total number of commits so far
        commit_num = (await run_cmd("git rev-list --all --count", decode = True))[0]

        # get the commit hash, timestamp, and message
        commit_data = (await run_cmd("git log -1 --pretty=format:%h%x09%at%x09%s", decode = True))[0].split("\t")

        # url that links to the commit
        commit_url = f"https://github.com/source64/cade/commit/{commit_data[0]}"

        latest_update = f"<t:{commit_data[1]}:R> [`#{commit_num}`]({commit_url}) - {commit_data[2]}"

        embed.add_field(name = "Latest update (from github):", value = latest_update, inline = False)
        embed.set_footer(text = "version 3 • by steve859")

        await wait.delete()
        await ctx.send(embed = embed)

    @commands.command(usage = "*[command]")
    async def help(self, ctx: commands.Context, cmd: str = None):
        """see a list of commands"""
        embed = BaseEmbed()

        if cmd is None:
            # default embed to use
            embed.title = "Commands"
            embed.description = "choose a category below to see the commands for it"

            # send message with buttons
            return await ctx.send(embed = embed, view = HelpView(self.client, ctx))

        command = self.client.get_command(cmd)

        if not command or command.hidden:
            return await ctx.send(err.HELP_NOT_FOUND)

        embed = BaseEmbed(description = f"**.{command.name}** - {command.help}")

        if usage := command.usage:
            if "*" in usage:
                embed.set_footer(text = "* - optional")

            if "(" in usage:
                att_index = usage.index("(")
                att_types = usage[att_index:].strip("()")
                usage = usage[:att_index]

                embed.add_field(name = "takes:", value = att_types)

            embed.insert_field_at(index = 0, name = "how to use:", value = f"`.{command.name} {usage}`".strip())

        if command.aliases:
            embed.add_field(name = "other names:", value = " ".join(f"`.{a}`" for a in command.aliases))

        await ctx.send(embed = embed)

    @commands.command(aliases = ["t"], usage = "[tag-name] *[message]")
    async def tag(self, ctx: commands.Context, tag_name: str, *, tag_content: str = ""):
        """sends/creates a tag containing a given message"""
        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        # add attachment url to tag_content if one is given
        if att := get_attachment_obj(ctx):
            tag_content += f" {att.url}"

        if not tag_content:
            # send tag if it exists
            if tag_name not in tags.keys():
                return await ctx.send(err.TAG_DOESNT_EXIST)

            return await ctx.send(tags[tag_name])
        else:
            # create tag if it doesn't exist
            if tag_name in tags.keys():
                return await ctx.send(err.TAG_ALREADY_EXISTS)

            await db.add_obj("tags", tag_name, tag_content.strip())
            return await ctx.send(f"{bot.OK} added tag `{tag_name}`")

    @commands.command(aliases = ["tagdel", "tdel"], usage = "[tag-name]")
    async def tagdelete(self, ctx: commands.Context, tag: str):
        """deletes the specified tag if it exists"""
        tag = str(tag).lower()

        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        # if the tag is not listed
        if tag not in tags:
            return await ctx.send(err.TAG_DOESNT_EXIST)

        # remove the tag
        await db.del_obj("tags", tag)

        await ctx.send(f"{bot.OK} removed tag `{tag}`")

    @commands.command(aliases = ["tlist", "tags"])
    async def taglist(self, ctx: commands.Context):
        """lists every tag in the server"""
        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        # if "tags" is empty or not in the guild database
        if not tags:
            return await ctx.send(err.NO_TAGS_AT_ALL)

        embed = BaseEmbed(
            title = "Tags:",
            from_list = (tags, None)
        )

        await ctx.send(embed = embed)

    @commands.command(usage = "[channel] *[message]")
    @commands.has_permissions(administrator = True)
    async def welcome(self, ctx: commands.Context, channel: discord.TextChannel, *, msg: str = None):
        """sets the welcome message for the server (admin)"""
        db = GuildDB(ctx.guild)

        # if nothing is given, disable the welcome message by setting it as None
        if not msg and not ctx.message.attachments:
            await db.set("welcome", [])
            return await ctx.send(f"{bot.OK} disabled welcome message")

        # get attachment url if there is one
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            msg = msg + "\n" + att.url if msg else att.url

        # update "welcome" with the given message and channel id
        await db.set("welcome", [msg, channel.id])

        await ctx.send(f"{bot.OK} set the welcome message and channel")

async def setup(bot: Cade):
    await bot.add_cog(General(bot))
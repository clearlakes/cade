import textwrap
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO

import discord
from discord.ext import commands

from utils.base import CadeElegy, BaseCog, BaseEmbed
from utils.db import GuildDB, Internal
from utils.useful import get_attachment_obj, run_cmd
from utils.vars import bot, colors, err
from utils.views import HelpView

from . import COGS


class Misc(BaseCog):
    @commands.command(aliases=["re"], hidden=True)
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog_to_reload: str | None):
        processing = await ctx.send(bot.PROCESSING())
        cogs = [cog_to_reload.lower()] if cog_to_reload else COGS

        try:
            for cog in cogs:
                await self.client.reload_extension(cog)
        except commands.ExtensionError as e:
            return await ctx.send(err.COG_RELOAD_ERROR(e.name))

        await processing.delete()
        await ctx.message.add_reaction(bot.OK)

    @commands.command(aliases=["u"], hidden=True)
    @commands.is_owner()
    async def update(self, ctx: commands.Context):
        processing = await ctx.send(f"{bot.PROCESSING()} looking for update...")
        embed = BaseEmbed()

        link_to = (
            lambda c_hash, c_num: f"[`#{c_num}`](https://github.com/clearlakes/cade/commit/{c_hash})"
        )

        # get the previous update's information
        prev_num = (await run_cmd("git rev-list --count HEAD", decode=True))[0]
        prev_hash = (await run_cmd("git rev-parse --short HEAD", decode=True))[0]

        # check if on the latest update already
        if (utd := "Already up to date.") in (await run_cmd("git pull", decode=True))[
            0
        ]:
            embed.description = f"{bot.OK} **{utd.lower().strip('.')}** ({link_to(prev_hash, prev_num)})"
        else:
            # reload cogs after update
            for cog in COGS:
                await self.client.reload_extension(cog)

            # get the new update's information
            new_num = (await run_cmd("git rev-list --count HEAD", decode=True))[0]
            new_hash = (await run_cmd("git rev-parse --short HEAD", decode=True))[0]

            embed.description = f"{bot.OK} **updated from {link_to(prev_hash, prev_num)} to {link_to(new_hash, new_num)}**"

        await processing.edit(content=None, embed=embed)

    @commands.command(aliases=["e"], hidden=True)
    @commands.is_owner()
    async def eval(self, ctx: commands.Context, *, code: str | None):
        # mostly taken from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py#L216-L261
        if code is None:
            if (ref := ctx.message.reference) and (content := ref.resolved.content):
                code = content
            elif (
                message := [msg async for msg in ctx.channel.history(limit=2)][1]
            ).author == ctx.author:
                code = message.content
            else:
                return await ctx.send("huh")

        stdout = StringIO()
        code = code.removeprefix("```py").removesuffix("```")
        function = f"async def func():\n{textwrap.indent(code.strip('`'), '  ')}"

        if "last_eval" not in dir(self):
            self.last_eval = None

        env = {
            "client": self.client,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "_": self.last_eval,
        }

        env.update(globals())

        try:
            exec(function, env)
            func = env["func"]
        except Exception as e:
            return await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")

        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
        else:
            value = stdout.getvalue()
            await ctx.message.add_reaction(bot.OK)

            if ret is None:
                if value:
                    await ctx.send(f"```py\n{value}\n```")
            else:
                self._last_result = ret
                await ctx.send(f"```py\n{value}{ret}\n```")

    @commands.command(usage="*[command]")
    async def info(self, ctx: commands.Context, cmd: str | None):
        """get information about the bot or a command"""
        if cmd:
            if command := self.client.get_command(cmd):
                count = await Internal().get_invoke_count(command.name)
                return await ctx.send(
                    f"**{command.name}** has been run `{count}` time(s)"
                )
            else:
                return await ctx.send(err.CMD_NOT_FOUND)

        pre = (await GuildDB(ctx.guild).get()).prefix
        gh = "https://github.com/clearlakes/cade"

        # get the uptime by subtracting the current time by the init time
        uptime = str(datetime.now() - self.client.init_time).split(".")[0]

        # get the ping, which is client.latency times 1000 (for ms)
        ping = round(self.client.latency * 1000, 3)

        # get the latest github commit
        number = (await run_cmd("git rev-list --count HEAD", decode=True))[0]
        commit_hash, timestamp, message = (
            await run_cmd("git log -1 --pretty=format:%h%n%at%n%s", decode=True)
        )[0].split("\n")
        latest_update = (
            f"<t:{timestamp}:R> [`#{number}`]({gh}/commit/{commit_hash}) - {message}"
        )

        # get the total number of commands that have been run (and date when counting began)
        invoke_count = await Internal().total_invoke_count
        began_counting = int((await Internal()._db)["_id"].generation_time.timestamp())

        embed = discord.Embed(title=f"{bot.CADE} cade {bot.CADE}", color=colors.CADE)

        embed.description = f"""cool insane bot made by clearlakes
        **[source]({gh})** • **[commands]({gh}/blob/main/commands.md)** • **[found bug]({gh}/issues/new)**
        use `{pre}help` for help. created <t:1596846209:R>!
        """

        embed.add_field(name="uptime", value=f"`{uptime}`")
        embed.add_field(name="ping", value=f"`{ping} ms`")
        embed.add_field(
            name="commands run",
            value=f"`{invoke_count}` (since <t:{began_counting}:d>)",
        )
        embed.add_field(name="latest update", value=latest_update, inline=False)

        embed.set_thumbnail(url=bot.CAT())

        guilds = len(self.client.guilds)  # get number of guilds
        users = len(
            [u for u in self.client.users if not u.bot]
        )  # get number of users that aren't bots

        embed.set_footer(
            text=f"in {guilds} servers with {users} people • made in funny museum"
        )

        await ctx.send(embed=embed)

    @commands.command(usage="*[command]")
    async def help(self, ctx: commands.Context, cmd: str | None):
        """see a list of commands"""
        pre = (await GuildDB(ctx.guild).get()).prefix
        embed = BaseEmbed()

        if cmd is None:
            # show list of commands
            view = HelpView(self.client, ctx, pre)
            return await ctx.send(embed=view.main_embed, view=view)

        # start getting command information
        command = self.client.get_command(cmd)

        if not command or command.hidden:
            return await ctx.send(err.CMD_NOT_FOUND)

        embed = BaseEmbed(description=f"**{pre}{command.name}** - {command.help}")

        if command.name == "help":
            embed.description = "are you serious"

        if usage := command.usage:
            if "*" in usage:
                embed.set_footer(text="* - optional")

            if "(" in usage:
                att_index = usage.index("(")
                att_types = usage[att_index:].strip("()")
                usage = usage[:att_index]

                embed.add_field(name="takes:", value=att_types)

            embed.insert_field_at(
                index=0,
                name="how to use:",
                value=f"`{pre}{command.name} {usage}`".strip(),
            )

        if command.aliases:
            embed.add_field(
                name="other names:",
                value=" ".join(f"`{pre}{a}`" for a in command.aliases),
            )

        await ctx.send(embed=embed)

    @commands.command(aliases=["t"], usage="[tag-name] *[message]")
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

    @commands.command(aliases=["tagdel", "tdel"], usage="[tag-name]")
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

    @commands.command(aliases=["tlist", "tags"])
    async def taglist(self, ctx: commands.Context):
        """lists every tag in the server"""
        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        if not tags:
            return await ctx.send(err.NO_TAGS_AT_ALL)

        tag_list = ""
        for tag in tags[:-1]:
            tag_list += f"**{tag}**, "  # create tag list

        tag_list += f"**{tag[-1]}**"  # add last item without comma

        embed = BaseEmbed(title="Tags:", description=tag_list)
        await ctx.send(embed=embed)

    @commands.command(usage="[channel] *[message]")
    @commands.has_permissions(administrator=True)
    async def welcome(
        self, ctx: commands.Context, channel: discord.TextChannel, *, msg: str | None
    ):
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

    @commands.command(aliases=["prefix"], usage="[prefix]")
    @commands.has_permissions(administrator=True)
    async def setprefix(self, ctx: commands.Context, new_prefix: str | None):
        """sets the bot prefix for the server (admin)"""
        db = GuildDB(ctx.guild)

        if new_prefix is None:  # display current prefix
            pre = (await db.get()).prefix
            return await ctx.send(f"the current prefix is `{pre}` (default is `.`)")

        if len(new_prefix) > 3:  # prevent long prefixes
            return await ctx.send(err.INVALID_PREFIX)

        await db.set("prefix", new_prefix)  # set new prefix
        await ctx.send(f"{bot.OK} set prefix to `{new_prefix}`")


async def setup(bot: CadeElegy):
    await bot.add_cog(Misc(bot))

from datetime import datetime

import discord
from discord.ext import commands

from utils.base import CadeElegy, BaseCog, BaseEmbed
from utils.db import GuildDB, Internal
from utils.useful import get_attachment_obj, run_cmd
from utils.vars import v
from utils.views import HelpView


class Misc(BaseCog):
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
                return await ctx.send(v.ERR__CMD_NOT_FOUND)

        pre = (await GuildDB(ctx.guild).get()).prefix
        gh = "https://github.com/clearlakes/cade"

        # get the uptime by subtracting the current time by the init time
        uptime = str(datetime.now() - self.client.init_time).split(".")[0]

        # get the ping, which is client.latency times 1000 (for ms)
        ping = round(self.client.latency * v.MATH__MS_MULTIPLIER, v.DISCORD__LATENCY_DEC_PLACES)

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
        began_counting = int((await Internal()._db_doc)["_id"].generation_time.timestamp())

        embed = discord.Embed(title=f"{v.EMJ__CADE} cade {v.EMJ__CADE}", color=v.BOT__CADE_THEME)

        embed.description = f"""cool insane bot made by me lakes
        **[source]({gh})** • **[commands]({gh}/blob/main/commands.md)** • **[found bug]({gh}/issues)**
        use `{pre}help` for help. created <t:1596846209:R>!
        **[discord](https://discord.gg/yRMsr9Td5c)**
        """

        embed.add_field(name="uptime", value=f"`{uptime}`")
        embed.add_field(name="ping", value=f"`{ping} ms`")
        embed.add_field(
            name="commands run",
            value=f"`{invoke_count}` (since <t:{began_counting}:d>)",
        )
        embed.add_field(name="latest update", value=latest_update, inline=False)

        embed.set_thumbnail(url=v.BOT__CAT_PIC())

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
            return await ctx.send(v.ERR__CMD_NOT_FOUND)

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
                return await ctx.send(v.ERR__TAG_DOESNT_EXIST)

            return await ctx.send(tags[tag_name])
        else:
            # create tag if it doesn't exist
            if tag_name in tags.keys():
                return await ctx.send(v.ERR__TAG_ALREADY_EXISTS)

            await db.add_obj("tags", tag_name, tag_content.strip())
            return await ctx.send(f"{v.EMJ__OK} added tag `{tag_name}`")

    @commands.command(aliases=["tagdel", "tdel"], usage="[tag-name]")
    async def tagdelete(self, ctx: commands.Context, tag: str):
        """deletes the specified tag if it exists"""
        tag = str(tag).lower()

        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        # if the tag is not listed
        if tag not in tags:
            return await ctx.send(v.ERR__TAG_DOESNT_EXIST)

        # remove the tag
        await db.del_obj("tags", tag)

        await ctx.send(f"{v.EMJ__OK} removed tag `{tag}`")

    @commands.command(aliases=["tlist", "tags"])
    async def taglist(self, ctx: commands.Context):
        """lists every tag in the server"""
        db = GuildDB(ctx.guild)
        tags = (await db.get()).tags

        if not tags:
            return await ctx.send(v.ERR__NO_TAGS_AT_ALL)

        # create tag list
        tag_list = ", ".join([f"**{t}**" for t in list(tags.keys())])

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
            return await ctx.send(f"{v.EMJ__OK} disabled welcome message")

        # get attachment url if there is one
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            msg = msg + "\n" + att.url if msg else att.url

        # update "welcome" with the given message and channel id
        await db.set("welcome", [msg, channel.id])

        await ctx.send(f"{v.EMJ__OK} set the welcome message and channel")

    @commands.command(aliases=["prefix"], usage="[prefix]")
    @commands.has_permissions(administrator=True)
    async def setprefix(self, ctx: commands.Context, new_prefix: str | None):
        """sets the bot prefix for the server (admin)"""
        db = GuildDB(ctx.guild)

        if new_prefix is None:  # display current prefix
            pre = (await db.get()).prefix
            return await ctx.send(f"the current prefix is `{pre}` (default is `.`)")

        if len(new_prefix) > 3:  # prevent long prefixes
            return await ctx.send(v.ERR__INVALID_PREFIX)

        await db.set("prefix", new_prefix)  # set new prefix
        await ctx.send(f"{v.EMJ__OK} set prefix to `{new_prefix}`")


async def setup(bot: CadeElegy):
    await bot.add_cog(Misc(bot))

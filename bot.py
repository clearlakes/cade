import discord
from discord.ext import commands, tasks

from utils.functions import run_cmd, generate_cmd_list
from utils.dataclasses import err, STATUS

import configparser
import aiohttp
import logging
import time

class Cade(commands.Bot):
    def __init__(self):
        super().__init__(
            help_command = None,
            command_prefix = commands.when_mentioned_or('.'),
            intents = discord.Intents.all()
        )

        self.init_time = time.time()

        # read config to get token
        config = configparser.ConfigParser()
        config.read("config.ini")

        self.token = str(config.get("server", "token"))
        self.cog_files = ["funny", "general", "media", "music"]
    
    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop = self.loop)

        for cog in self.cog_files:
            await self.load_extension(f"cogs.{cog}")

        self.random_activity.start()

    async def on_ready(self):
        self.log = logging.getLogger('discord')
        self.log.name = ""

        self.log.warning("cade ready to rumble")

    @tasks.loop(minutes = 10)
    async def random_activity(self):
        # change activity every 10 minutes
        type, name = STATUS()
        await self.change_presence(activity = discord.Activity(type = type, name = name))

    @random_activity.before_loop
    async def _before(self):
        await self.wait_until_ready()

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await ctx.send(err.USAGE(ctx.command))
        elif isinstance(error, commands.CheckFailure):
            return  # ignore check failures

        raise error
    
    async def close(self):
        for cog in self.cog_files:
            # generate command list again if any changes were made
            if (await run_cmd(f"git diff --quiet cogs/{cog}.py"))[1]:
                self.log.info("generating commands.md")
                generate_cmd_list(self.cogs)
                break

        await self.session.close()

    def run(self):
        super().run(self.token, reconnect = True)

if __name__ == '__main__':
    cade = Cade()
    cade.run()
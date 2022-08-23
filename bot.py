import discord
from discord.ext import commands

from utils.dataclasses import err

from json import load
import configparser
import aiohttp
import logging
import time

class Cade(commands.Bot):
    def __init__(self):
        super().__init__(
            help_command = None,
            command_prefix = commands.when_mentioned_or('.'),
            intents = discord.Intents.all(),
            activity = discord.Activity(
                type = discord.ActivityType.watching, 
                name = "food battle 2014"
            )
        )

        self.init_time = time.time()

        # read config to get token
        config = configparser.ConfigParser()
        config.read("config.ini")

        self.token = str(config.get("server", "token"))
    
    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop = self.loop)

        for cog in ["funny", "general", "media", "music"]:
            await self.load_extension(f"cogs.{cog}")

    async def on_ready(self):
        self.log = logging.getLogger('discord')
        self.log.name = ""

        self.log.warning("cade ready to rumble")

    async def on_command_error(self, ctx: commands.Context, error):
        # if the error was from an invalid argument
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            with open("commands.json", "r") as f:
                data = load(f)
            
            cmd = ctx.command.name

            # get category and command information (from help command)
            cat, cmd = next(((cat, x) for cat, x in data.items() 
                for x in data[cat] if cmd == x or data[cat][x]["alt"] is not None 
                and any(cmd == alt for alt in data[cat][x]["alt"])))
                
            usage = data[cat][cmd]["usage"]

            return await ctx.send(err.USAGE(cmd, usage))
        elif isinstance(error, commands.CheckFailure):
            # ignore check failures
            pass
        else:
            raise error
    
    async def close(self):
        await self.session.close()

    def run(self):
        super().run(self.token, reconnect = True)

if __name__ == '__main__':
    cade = Cade()
    cade.run()
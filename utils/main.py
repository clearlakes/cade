import discord
from discord.ext import commands, tasks

from utils.data import err, bot
from utils.db import GuildDB

from async_spotify import SpotifyApiClient
from lavalink import Client, DefaultPlayer
from datetime import datetime
import configparser
import aiohttp
import logging
import tweepy

class Cade(commands.Bot):
    def __init__(self):
        super().__init__(
            help_command = None,
            command_prefix = get_prefix,
            intents = discord.Intents.all()
        )

        self.init_time = datetime.now()

        self.log = logging.getLogger("discord")
        self.log.name = ""

        # read config to get token
        config = configparser.ConfigParser()
        config.read("config.ini")

        self.token = str(config.get("bot", "token"))
        self.cog_files = ["funny", "general", "media", "music"]

        self.lavalink: CadeLavalink = None
        self.twitter_api: tweepy.API = None
        self.spotify_api: SpotifyApiClient = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop = self.loop)

        for cog in self.cog_files:
            await self.load_extension(f"cogs.{cog}")

        self.random_activity.start()

    async def on_ready(self):
        self.log.warning("cade ready to rumble")

    @tasks.loop(minutes = 10)
    async def random_activity(self):
        # change activity every 10 minutes
        act_type, name = bot.STATUS()
        await self.change_presence(activity = discord.Activity(type = act_type, name = name))

    @random_activity.before_loop
    async def _before(self):
        await self.wait_until_ready()

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            prefix = (await GuildDB(ctx.guild).get()).prefix
            await ctx.send(err.CMD_USAGE(prefix, ctx.command))  # send command usage
            return
        elif isinstance(error, (commands.CheckFailure, commands.DisabledCommand, commands.CommandNotFound)):
            return  # ignore errors that aren't important

        raise error

    async def close(self):
        if self.spotify_api:
            await self.spotify_api.close_client()

        await self.session.close()

    def run(self):
        super().run(self.token, reconnect = True)

class CadeLavalink(Client):
    def create_player(self, ctx: commands.Context | discord.Interaction) -> DefaultPlayer:
        user = ctx.author if isinstance(ctx, commands.Context) else ctx.user

        player: DefaultPlayer = self.player_manager.create(ctx.guild.id, endpoint = str(user.voice.channel.rtc_region))
        player.store("channel", ctx.channel.id)

        return player

    def get_player(self, ctx: commands.Context | discord.Interaction | discord.Member) -> DefaultPlayer:
        return self.player_manager.get(ctx.guild.id)

async def get_prefix(client: Cade, message: discord.Message):
    # use custom prefix if there is one
    prefix = (await GuildDB(message.guild).get()).prefix
    return commands.when_mentioned_or(prefix)(client, message)
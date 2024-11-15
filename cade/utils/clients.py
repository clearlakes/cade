import configparser
import logging
from datetime import datetime, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks
from lavalink import Client, DefaultPlayer
import os

from cogs import COGS

from .db import Internal
from .events import BotEvents, TrackEvents
from .keys import Keys
from .useful import get_prefix
from .vars import bot
from .ext import generate_cmd_list


class Cade(commands.Bot):
    def __init__(self):
        super().__init__(
            help_command=None, command_prefix=get_prefix, intents=discord.Intents.all()
        )

        self.client = self

        self.init_time = datetime.now()

        self.log = logging.getLogger("discord")
        self.log.name = ""

        # read config to get token
        config = configparser.ConfigParser()
        config.read("config.ini")

        self.token = str(config.get("bot", "token"))
        self.cog_files = ["funny", "general", "media", "music"]

        self.before_invoke(self._start_timer)
        self.after_invoke(self._log_and_increment)

    async def _start_timer(self, ctx: commands.Context):
        ctx.command.extras["t"] = datetime.now()

    async def _log_and_increment(self, ctx: commands.Context):
        delta: timedelta = datetime.now() - ctx.command.extras["t"]
        self.log.info(
            f"ran .{ctx.command.name} (took {round(delta.total_seconds(), 2)}s)"
        )

        if not ctx.command.hidden:
            await Internal().inc_invoke_count(ctx.command.name)

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop=self.loop)

        for cog in COGS:
            await self.load_extension(cog)

        self.random_activity.start()
        BotEvents(self).add()

        self.lavalink = CadeLavalink(self.user.id)
        self.lavalink.add_node(*Keys.lavalink.ordered_keys, name="default-node")
        self.lavalink.add_event_hooks(TrackEvents(self))
        self.log.info("connected to lavalink")

        if os.environ["GENERATE"].lower() == "true":
            self.log.info("generating commands.md...")
            generate_cmd_list(self.cogs)

    async def on_ready(self):
        self.log.warning("cade ready to rumble")

    @tasks.loop(minutes=10)
    async def random_activity(self):
        # change activity every 10 minutes
        act_type, name = bot.STATUS()
        await self.change_presence(activity=discord.Activity(type=act_type, name=name))

    @random_activity.before_loop
    async def _before(self):
        await self.wait_until_ready()

    async def close(self):
        await self.session.close()

    def run(self):
        super().run(self.token, reconnect=True)


class CadeLavalink(Client):
    def __init__(self, user_id: int | str = None):
        self.voice_client = LavalinkVoiceClient
        super().__init__(user_id)

    def create_player(
        self, ctx: commands.Context | discord.Interaction
    ) -> DefaultPlayer:
        user = ctx.author if isinstance(ctx, commands.Context) else ctx.user

        player: DefaultPlayer = self.player_manager.create(
            ctx.guild.id, endpoint=str(user.voice.channel.rtc_region)
        )
        player.store("channel", ctx.channel.id)

        return player

    def get_player(
        self, ctx: commands.Context | discord.Interaction | discord.Member
    ) -> DefaultPlayer:
        return self.player_manager.get(ctx.guild.id)


class LavalinkVoiceClient(discord.VoiceClient):
    """discord <-> lavalink connection (from lavalink.py)"""

    def __init__(self, client: Cade, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.log = client.log
        self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        lavalink_data = {"t": "VOICE_SERVER_UPDATE", "d": data}
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        lavalink_data = {"t": "VOICE_STATE_UPDATE", "d": data}
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(
        self,
        *,
        timeout: float,
        reconnect: bool,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)

        await self.channel.guild.change_voice_state(
            channel=self.channel, self_mute=self_mute, self_deaf=self_deaf
        )

        self.log.info(f"added player in {self.channel.guild.id}")

    async def disconnect(self, *, force: bool) -> None:
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        if not force and not player:
            return

        await self.channel.guild.change_voice_state(channel=None)

        player.channel_id = None
        self.cleanup()

        self.lavalink.player_manager.remove(self.channel.guild.id)
        self.log.info(f"removed player in {self.channel.guild.id}")

import importlib
import sys
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands

from logging import Logger
from configparser import ConfigParser
from lavalink import Client as LavaClient, DefaultPlayer

from .vars import colors


class CadeElegy(commands.Bot):
    """copy of Cade class from clients.py (to avoid circular imports)"""

    def __init__(self):
        self._config: ConfigParser = None
        self.init_time: datetime = None
        self.log: Logger = None
        self.token: str = None
        self.cog_files: list[str] = [None]
        self.lavalink: CadeLavalinkElegy = None


class CadeLavalinkElegy(LavaClient):
    """copy of CadeLavalink class from clients.py (to avoid circular imports)"""

    def __init__(self):
        self.voice_client: discord.VoiceClient = None

    def create_player(
        self, ctx: commands.Context | discord.Interaction
    ) -> DefaultPlayer: ...
    def get_player(
        self, ctx: commands.Context | discord.Interaction | discord.Member
    ) -> DefaultPlayer: ...


class BaseCog(commands.Cog):
    """like a regular cog but adds self.client (more stuff could be added later if needed)"""

    def __init__(self, client: CadeElegy):
        for module in [m[1] for m in sys.modules.items() if m[0].startswith("utils")]:
            importlib.reload(module)  # reloads all imports, useful when updating

        client.log.info(f"loaded {self.__cog_name__}")
        self.client = client


class BaseEmbed(discord.Embed):
    """like a regular embed but with gray as the default color"""

    def __init__(
        self,
        *,
        color: int | discord.Colour | None = colors.EMBED_BG,
        title: Any | None = None,
        url: Any | None = None,
        description: Any | None = None,
        timestamp: datetime | None = None,
    ):
        super().__init__(
            color=color,
            title=title,
            url=url,
            description=description,
            timestamp=timestamp,
        )

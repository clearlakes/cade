import discord
from discord.ext import commands

from utils.data import colors
from utils.main import Cade

from datetime import datetime
from typing import Any
import importlib
import sys

class BaseCog(commands.Cog):
    """like a regular cog but adds self.client (more stuff could be added later if needed)"""
    def __init__(self, client):
        self.client: Cade = client

        for module in [m[1] for m in sys.modules.items() if m[0].startswith("utils")]:
            importlib.reload(module)  # reloads all imports, useful when updating

        self.client.log.info(f"loaded {self.__cog_name__}")

class BaseEmbed(discord.Embed):
    """like a regular embed but with gray as the default color (also able to create lists)"""
    def __init__(self, *,
        color: int | discord.Colour | None = colors.EMBED_BG,
        title: Any | None = None,
        url: Any | None = None,
        description: Any | None = None,
        timestamp: datetime | None = None,
        from_list: tuple[list, str] = None
    ):
        if from_list:
            item_list, placeholder = from_list
            description = "**" + "**, **".join(item_list) + "**" if item_list else placeholder

        super().__init__(
            color = color,
            title = title,
            url = url,
            description = description,
            timestamp = timestamp
        )
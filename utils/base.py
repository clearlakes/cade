import discord
from discord.ext import commands

from utils.data import colors
from utils.main import Cade

from typing import Optional, Union, Any
from datetime import datetime

class BaseCog(commands.Cog):
    """like a regular cog but adds self.client (more stuff could be added later if needed)"""
    def __init__(self, client):
        self.client: Cade = client

class BaseEmbed(discord.Embed):
    """like a regular embed but with gray as the default color (also able to create lists)"""
    def __init__(self, *,
        color: Optional[Union[int, discord.Colour]] = colors.EMBED_BG,
        title: Optional[Any] = None,
        url: Optional[Any] = None,
        description: Optional[Any] = None,
        timestamp: Optional[datetime] = None,
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
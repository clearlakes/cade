import discord
from discord.ext import commands
from typing import Callable, Union
import configparser
import pymongo
import re

# ffmpeg options that hide everything except errors
FFMPEG = "ffmpeg -y -hide_banner -loglevel error"

# load config file
config = configparser.ConfigParser()
config.read("config.ini")

# load database from the config
mongo_url = str(config.get("server", "mongodb"))
mongo_client = pymongo.MongoClient(mongo_url)
db = mongo_client.cade.main

# get api keys
tenor_key = str(config.get("tenor", "key"))
twitter_keys = [str(config.get("twitter", x)) for x in config.options("twitter") if x != "handle"]
spotify_keys = [str(config.get("spotify", x)) for x in config.options("spotify")]

# twitter handle to use
handle = str(config.get("twitter", "handle"))

# host, port, password, etc. for connecting to lavalink
# this will get everything as a string, except for the port (which will be a number)
lavalink_opts = [str(config.get("lavalink", x)) if x != "port" else int(config.get("lavalink", x)) for x in config.options("lavalink")]

# lambda function for creating a database filter
# this will be used for finding things in the db relating to a server
g_id: Callable[[Union[commands.Context, discord.Member]], dict[str, int]] = lambda x: {'guild_id': x.guild.id}

# standard function for checking user when waiting for message
def check(ctx: Union[commands.Context, discord.Interaction]):
    """ wait_for function that checks the context matches what's required """

    def check_inner(message: discord.Message):
        # get author from either interaction or context
        if isinstance(ctx, discord.Interaction):
            author = ctx.user
        else: 
            author = ctx.author
        
        # check if the message author is the same as the original user
        # and that the message channel is the same as the original channel
        return (message.author == author
            and message.channel == ctx.channel)

    return check_inner

def btn_check(ctx: Union[commands.Context, discord.Interaction]):
    """ wait_for function that checks if the interaction matches what's required """

    if isinstance(ctx, discord.Interaction):
        author = ctx.user
    else: 
        author = ctx.author

    # check if: 
    #   the interaction is from a component (ex. button)
    #   the user who send the interaction is the same as the original user
    #   the channel that the interaction was sent in is the same as the original channel

    def btn_check_inner(interaction: discord.Interaction):
        return (interaction.type == discord.InteractionType.component 
            and interaction.user == author
            and interaction.channel == ctx.channel)

    return btn_check_inner

def escape_ansii(text):
    """ Removes color codes and newlines from errors """
    text = str(text)
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')

    # substitute the codes with an empty string and newlines with a dash
    return ansi_escape.sub('', text).replace("\n", " - ")

# cancel button for messages
class CancelView(discord.ui.View):
    def __init__(self):
        self.canceled = False
        super().__init__()
    
    # create a button with the label "Done" that sets self.canceled to True
    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.canceled = True
        self.stop()
    
    async def on_timeout(self) -> None:
        return await super().on_timeout()

# universal url regex
url_rx = re.compile(r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)')

# regex for different urls
youtube_rx = re.compile(r'(?:https?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]+)')
twitter_rx = re.compile(r'https?:\/\/twitter\.com\/(?:#!\/)?(\w+)\/status(?:es)?\/(\d+)') # group 1: handle, group 2: status id
tenor_rx = re.compile(r'https?:\/\/tenor.com\/view\/(?:[a-zA-Z]+(?:-[a-zA-Z]+)+)-([0-9]+)') # group 1: tenor id
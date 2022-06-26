import discord
from discord.utils import get
from discord.ext import commands

from json import load
import configparser
import time

# save the current time
initial = time.time()

# read config to get token
config = configparser.ConfigParser()
config.read("config.ini")

token = str(config.get("server", "token"))
intents = discord.Intents.all()

# set activity status
activity = discord.Activity(type=discord.ActivityType.watching, name="food battle 2014")

# set the bot's prefix and intents
client = commands.Bot(command_prefix=commands.when_mentioned_or("."), intents=intents, activity=activity)
client.remove_command('help')

@client.event
async def on_ready():
    # list of cats for info command
    client.cats = [
        "https://i.imgur.com/1WCgVB5.jpg", 
        "https://i.imgur.com/o2Mv3id.gif",
        "https://i.imgur.com/jBdFw84.jpg",
        "https://i.imgur.com/q5MlyL1.jpg",
        "https://i.imgur.com/7lt16yi.jpg",
        "https://i.imgur.com/mXKsgNU.jpg",
        "https://i.imgur.com/UmmYVhK.jpg"
    ]

    client.initial = initial

    # small function that returns emojis from a server
    get_emoji = lambda x: get(client.emojis, name = x, guild_id = 680201586579996678)

    # get emojis that the bot uses
    client.loading = get_emoji("cadeload")
    client.wait = get_emoji("cadewait")
    client.ok = get_emoji("cadeok")

    # load cogs
    for cog in ["funny", "general", "media", "music"]:
        client.load_extension(f"cogs.{cog}")

    print("cade ready to rumble")

@client.event
async def on_command_error(ctx: commands.Context, error):
    # if the error was from an invalid argument
    if isinstance(error, commands.BadArgument):
        with open("commands.json", "r") as f:
            data = load(f)
        
        cmd = ctx.command.name

        # get category and command information (from help command)
        cat, cmd = next(((cat, x) for cat, x in data.items() 
            for x in data[cat] if cmd == x or data[cat][x]["alt"] is not None 
            and any(cmd == alt for alt in data[cat][x]["alt"])))
            
        usage = data[cat][cmd]["usage"]

        # add space if usage is not empty
        if usage is not None: usage = f" {usage}"
        else: usage = ""

        return await ctx.send(f"**Error:** usage: `.{cmd}{usage}`")
    elif isinstance(error, commands.CheckFailure):
        # ignore check failures
        pass
    else:
        raise error

client.run(token)
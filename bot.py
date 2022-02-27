import discord
from discord.utils import get
from discord.ext import commands
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
    client.gray = 0x2f3136

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

@client.command(aliases=["re"])
@commands.is_owner()
async def reload(ctx, cog_to_reload: str = None):
    processing = await ctx.send(f"{client.loading}")

    try:
        # reload all cogs if nothing is specified
        if cog_to_reload is None:
            for cog in ["funny", "general", "media", "music"]:
                client.reload_extension(f"cogs.{cog}")
        else:
            # reload the specified extension
            client.reload_extension(f"cogs.{cog_to_reload.lower()}")
    except:
        return await ctx.send(f"**Error:** could not reload")
    
    await processing.delete()
    await ctx.message.add_reaction(client.ok)

client.run(token)
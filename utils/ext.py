from discord.ext import commands
from utils.clients import Keys

from typing import Mapping
from io import BytesIO
import aiohttp

async def serve_very_big_file(b: BytesIO, mime: str):
    """Uploads media to the image server"""
    form = aiohttp.FormData()
    form.add_field("file", b.getvalue(), content_type = mime)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f'{Keys.image.domain}/upload', data = form, headers = {"Authorization": Keys.image.secret}) as post:
                res: dict[str, str] = await post.json()

        filename = f"{res['file_id'].upper()}.{res['file_ext']}"
        file_url = f"{Keys.image.domain}/image/{filename}"
    except (aiohttp.ClientConnectionError, aiohttp.ContentTypeError):
        file_url = None

    return file_url

def generate_cmd_list(bot_cogs: Mapping[str, commands.Cog]):
    """Generates the command list (commands.md)"""
    cogs = list(reversed(bot_cogs.values()))
    cool_fire = "<img src='https://i.imgur.com/yxm0XNL.gif' width='20'>"

    markdown = "\n".join([
        f"# {cool_fire} cade commands {cool_fire}",
        "-  arguments starting with `*` are optional<br>",
        "-  command prefix might be different depending on the server<br>",
        "-  each command is linked to where their code is"
    ]) + "\n\n"

    # add links to command sections
    cog_names = [c.qualified_name for c in cogs]
    markdown += " • ".join(f"[**{name}**](#{name.lower()})" for name in cog_names) + "\n\n"

    for cog, cog_name in zip(cogs, cog_names):
        markdown += f"\n## {cog_name}\n"

        if cog_name == "Funny":
            markdown += "> note: these commands are specific to funny museum\n"

        cog_commands = [c for c in cog.get_commands() if not c.hidden]
        cog_filename = f"cogs/{cog_name.lower()}.py"

        for cmd in cog_commands:
            # get line number of command function
            with open(cog_filename, "r") as f:
                content = f.readlines()
                line_num = [x for x in range(len(content)) if f"def {cmd.name}(" in content[x]][0]

            line = f"https://github.com/source64/cade/blob/main/{cog_filename}#L{line_num}"

            markdown += f"-  [**`.{cmd.name}`**]({line}) - {cmd.help}\n"

            if cmd.usage:
                markdown += f"   -  how to use: `.{cmd.name} {cmd.usage}`\n"

            markdown += "\n"

    with open("commands.md", "w") as f:
        f.write(markdown.strip())
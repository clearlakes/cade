from io import BytesIO
from typing import Mapping
from pathlib import Path
from datetime import datetime
import random
import string

from discord.ext import commands

from .keys import Keys
from .db import Internal


async def serve_very_big_file(guild_id: int, media: tuple[BytesIO, str, str]):
    """uploads media to the image server"""
    file_dir = f"./largefiles/{guild_id}"

    Path(file_dir).mkdir(parents=True, exist_ok=True)

    rand_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    filename = rand_code + "_" + media[1]

    db = Internal().internal_db
    await db.push("largefiles", [guild_id, filename, datetime.now()])

    with open(f"{file_dir}/{filename}", "wb") as f:
        f.write(media[0].read())
        f.seek(0)

    return f"{Keys.image.domain}/{guild_id}/{filename}"


def generate_cmd_list(bot_cogs: Mapping[str, commands.Cog]):
    """generates the command list (commands.md)"""
    cogs = list(reversed(bot_cogs.values()))
    cool_fire = "<img src='https://i.imgur.com/yxm0XNL.gif' width='20'>"

    markdown = (
        "\n".join(
            [
                f"# {cool_fire} cade commands {cool_fire}",
                "-  arguments starting with `*` are optional<br>",
                "-  command prefix might be different depending on the server<br>",
                "-  each command is linked to where their code is",
            ]
        )
        + "\n\n"
    )

    # add links to command sections
    cog_names = [c.qualified_name for c in cogs]
    markdown += (
        " • ".join(f"[**{name}**](#{name.lower()})" for name in cog_names) + "\n\n"
    )

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
                line_num = [
                    x for x in range(len(content)) if f"def {cmd.name}(" in content[x]
                ][0]

            line = f"https://github.com/clearlakes/cade/blob/main/{cog_filename}#L{line_num}"

            markdown += f"-  [**`.{cmd.name}`**]({line}) - {cmd.help}\n"

            if cmd.usage:
                markdown += f"   -  how to use: `.{cmd.name} {cmd.usage}`\n"

            markdown += "\n"

    with open("commands.md", "w") as f:
        f.write(markdown.strip())

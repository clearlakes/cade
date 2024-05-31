from argparse import ArgumentParser

from utils.clients import Cade
from utils.ext import generate_cmd_list

p = ArgumentParser()
p.add_argument("-g", "--generate", action="store_true")
cade_args = vars(p.parse_args())

if __name__ == "__main__":
    cade = Cade()

    if not cade_args["generate"]:
        cade.run()
    else:
        cade.run()
        cade.log.info("generating commands.md...")
        generate_cmd_list(cade.cogs)
        cade.log.info("done")

#   /\__/\     z Z
#  / _  _ \ . z
#  \  ^   /

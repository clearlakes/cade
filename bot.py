from utils.main import Cade
from utils.ext import generate_cmd_list

if __name__ == '__main__':
    cade = Cade()
    cade.run()

    #   /\  /\     z Z
    #  / _ _  \ . z
    #  \  ^   /

    cade.log.info("generating commands.md")
    generate_cmd_list(cade.cogs)
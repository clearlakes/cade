import random
import re
from dataclasses import dataclass

from discord import ActivityType as act

@dataclass
class v:
    """
    a list of variables for the bot

    prefix descriptions:

    - `__*` = internal use
    - `PIL__` = Pillow variables
    - `BOT__` = general bot variables
    - `EMJ__` = emojis
    - `RE__` = regex
    - `FF__` = ffmpeg commands
    - `ERR__` = errors
    """

    __FFMPEG = "ffmpeg -y -hide_banner -loglevel error"
    __FFPROBE = "ffprobe -v error"

    # pad videos to make their sizes even (required to make mp4)
    __FF__PAD_EVEN = '-vf pad="width=ceil(iw/2)*2:height=ceil(ih/2)*2"'

    # error prefix
    E = "<a:fire:1004208282585530408>"

    RESIZE__AUTO_SIZE = "-2"

    CAPTION__SPACING_RATIO = 40
    CAPTION__FONTSIZE_RATIO = 10
    CAPTION__EMOJI_SCALE = 1.2
    CAPTION__EMOJI_SCALE_LRG = 1.5
    CAPTION__EMJ_OFFSET_X = 12
    CAPTION__EMJ_OFFSET_Y = CAPTION__EMJ_OFFSET_X // 2

    HTML__OK_STATUS = 200

    MUSIC__LYRIC_MAX_LINES = 24
    MUSIC__QUEUE_MAX_LINES = 10

    DISCORD__MAX_FILESIZE_BYTES = 10**6
    DISCORD__MAX_FILESIZE_MB = 10
    DISCORD__LATENCY_DEC_PLACES = 3

    MATH__MS_MULTIPLIER = 1000

    PIL__FONT_PATH = "fonts/futura.ttf"
    PIL__WHITE = (255, 255, 255)
    PIL__BLACK = (0, 0, 0)

    BOT__CADE_THEME = 0xEAC597
    BOT__PLAYING_TRACK_THEME = 0x4287F5
    BOT__QUEUED_TRACK_THEME = 0x40C752
    BOT__EMBED_BG = 0x2F3136

    BOT__STATUS_MSG = lambda: random.choice(
        [
            [act.listening, "relaxing white noise 10 hours"],
            [act.listening, "cheezer"],
            [act.watching, "food battle 2014"],
            [act.playing, "let me out!!!! get me out of here"],
            [act.playing, "coming back from applebees"],
            [act.playing, "stole 418852014401 bobux"],
            [act.playing, "legalize nuclear bombs"],
            [act.playing, "aint that nathaniel b"],
            [act.playing, "going to applebees"],
            [act.playing, "i miss my wife"],
            [act.playing, "i need money"],
            [act.playing, "mario"],
        ]
    )

    BOT__CAT_PIC = lambda: random.choice(
        [
            "https://i.imgur.com/1WCgVB5.jpg",
            "https://i.imgur.com/o2Mv3id.gif",
            "https://i.imgur.com/jBdFw84.jpg",
            "https://i.imgur.com/q5MlyL1.jpg",
            "https://i.imgur.com/7lt16yi.jpg",
            "https://i.imgur.com/mXKsgNU.jpg",
            "https://i.imgur.com/UmmYVhK.jpg",
        ]
    )

    BOT__SUPPORTED_SITES = (
        "https://tenor",
        "https://gyazo",
        "https://cdn.discordapp",
        "https://media.discordapp",
        "https://i.imgur",
        "https://c.tenor",
    )

    EMJ__PROCESSING = lambda: "-# " + random.choice(
        ["<a:bandy:1004177770554859603>", "<a:cadeload:934934660495048716>"]
    )
    EMJ__WAITING = "<a:cadewait:945424680351850506>"
    EMJ__OK = "<:cadeok:934934539124502598>"
    EMJ__CADE = "<:cade:1245901352715026463>"
    EMJ__CADEMAD = "<:cademad:1245901173232242698>"
    EMJ__CADEHAPPY = "<:cadehappy:1245899329038712943>"
    EMJ__CADEMOLDY = "<:cademoldy:1388257976917295215>"
    EMJ__CONNECTION = "<:connected2:1125295361859272774>"

    BOT__PROCESSING_MSG = lambda P=EMJ__PROCESSING(): random.choice(
        [
            f"{P} processing...",
            f"{P} loading...",
            f"{P} doing something...",
            f"{P} hi",
            f"{P} i hate my stupid chud life",
            f"{P} HELP ME",
            f"{P} one secs...",
            f"{P} ...!!!",
            f"{P} (cade now loading)",
        ]
    )
    
    RE__YOUTUBE = re.compile(
        r"https?:\/\/(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(watch|v|embed|shorts|playlist)?(?:\.php)?(?:\?(?:v=|list=)|\/))([a-zA-Z0-9\_-]+)"
    )  # group 1: type, group 2: id
    RE__URL = re.compile(
        r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)"
    )
    RE__TENOR = re.compile(r"https?:\/\/tenor.com\/view\/.*-(\d+)")  # group 1: tenor id
    RE__GYAZO = re.compile(r"https?:\/\/gyazo.com\/(.*)")  # group 1: gyazo id
    RE__COLOR = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    RE__DISCORD = re.compile(r"https:\/\/(cdn|media)\.discordapp\.(com|net)\/.*")
    RE__TRACKNAME = re.compile(r"(?<=\[).*(?=\])")
    RE__PLAYLIST = re.compile(r"(?:\: )|(?: - )")
    RE__DISCORD_EMOJI = re.compile(r"<\:\w*\:\w*>")
    RE__DE_PLACEHOLDER = re.compile(r"\[#[0-9]#\]")
    
    FF__GET_DIMENSIONS = f"{__FFPROBE} -select_streams v -show_entries stream=width,height -of csv=p=0:s=x -"
    FF__GET_DURATION = f"{__FFPROBE} -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -"
    FF__GET_STREAM = lambda path, url, ext, start, end, FF=__FFMPEG: (
        FF + (f"-ss {start} -to {end} " if start else "") + f"-i {url} {path}/output.{ext}"
    )
    FF__CREATE_MP4 = lambda path, fps, FF=__FFMPEG, PD=__FF__PAD_EVEN: (
        f"{FF} -framerate {fps} -i '{path}/%d.png' -vn -i {path}/input.mp4 -c:v libx264 -pix_fmt yuv420p {PD} {path}/output.mp4"
    )
    FF__RESIZE = lambda path, width, height, FF=__FFMPEG: (
        f"{FF} -i {path}/input.mp4 -vf scale={width}:{height} {path}/output.mp4"
    )
    FF__IMGAUDIO = lambda path, audio, length, FF=__FFMPEG, PD=__FF__PAD_EVEN: (
        f"{FF} -loop 1 -i {path}/input.png -i {audio} -map 0 -map 1:a -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p {PD} -shortest {path}/output.mp4"
    )
    FF__SPEED_UP = lambda path, amount, FF=__FFMPEG: (
        f"{FF} -i {path}/input.mp4 -vf 'setpts={1 / amount}*PTS' -af 'atempo={amount}' {path}/output.mp4"
    )

    ERR__TIMED_OUT = f"{E} timed out"
    ERR__COG_RELOAD_ERROR = lambda c, E=E: f"{E} could not reload {c}"
    ERR__INVALID_PREFIX = f"{E} prefix is too long (needs to be less than 4 letters)"
    ERR__FUNNY_ONLY = f"{E} that only works in funny museum"
    ERR__NO_ATTACHMENT_FOUND = f"{E} no attachment was found"
    ERR__NO_ATT_OR_URL_FOUND = f"{E} no attachment or url was found"
    ERR__NO_AUDIO_FOUND = f"{E} could not find audio file or url"
    ERR__WRONG_ATT_TYPE = f"{E} wrong attachment type"
    ERR__UNSUPPORTED_URL = f"{E} unsupported url (lmk if you think it should be)"
    ERR__CMD_NOT_FOUND = f"{E} command not found"
    ERR__NO_PERMISSIONS_USER = f"{E} you're missing permissions"
    ERR__NO_PERMISSIONS_BOT = f"{E} i'm missing permissions"
    ERR__TAG_DOESNT_EXIST = f"{E} that tag has not been created yet"
    ERR__TAG_ALREADY_EXISTS = f"{E} that tag already exists"
    ERR__NO_TAGS_AT_ALL = f"{E} no tags have been made yet"
    ERR__CANT_SEND_FILE = f"{E} could not send the file?? (maybe try again)"
    ERR__FILE_TOO_BIG = f"{E} the file was too big (over 10 mb)"
    ERR__IMAGE_SERVER_ERROR = (
        f"{E} can't find image server (not your fault i need to fix this)"
    )
    ERR__VID_DL_ERROR = lambda e, E=E: f"{E} could not get video: {e}"
    ERR__NO_DURATION = f"{E} the video's duration could not be found (specify)"
    ERR__NO_LYRICS = f"{E} couldn't find lyrics"
    ERR__AUDIO_MAX_LENGTH = f"{E} audio length is too long (max: 30 minutes)"
    ERR__FILE_MAX_SIZE = f"{E} size too large (max: 2000px)"
    ERR__FILE_INVALID_SIZE = f"{E} invalid size"
    ERR__FFMPEG_ERROR = (
        f"{E} processing the command failed for some reason (maybe not your fault)"
    )
    ERR__MEDIA_EDIT_ERROR = (
        f"{E} processing the file failed for some reason (wrong file type?)"
    )
    ERR__INVALID_URL = f"{E} invalid url"
    ERR__INVALID_TIMESTAMP = f"{E} invalid timestamp (must be min:sec, hr:min:sec, or sec)"
    ERR__INVALID_MULTIPLIER = (
        f"{E} invalid multiplier (should be something like 2x, 1.5, etc.)"
    )
    ERR__WEIRD_TIMESTAMPS = f"{E} the starting position must come before the end position"
    ERR__BOT_NOT_IN_VC = f"{E} i'm not in a vc"
    ERR__USER_NOT_IN_VC = f"{E} you're not in the vc"
    ERR__NO_MUSIC_PLAYING = f"{E} nothing is playing right now"
    ERR__SINGLE_TRACK_ONLY = f"{E} only one track can be added at a time"
    ERR__NO_MUSIC_RESULTS = f"{E} no results were found with that query"
    ERR__CANT_LOAD_MUSIC = (
        f"{E} can't play music (could be private/age-restricted/copyrighted)"
    )
    ERR__BOT_IN_VC = f"{E} i'm already in the vc"
    ERR__NOT_IN_QUEUE = f"{E} that isn't in the queue"
    ERR__MUSIC_NOT_LOOPED = f"{E} the current song is not being looped (use `.l` to do so)"
    ERR__INVALID_INDEX = f"{E} invalid index"
    ERR__INVALID_SEEK = f"{E} cannot skip that far into the track"
    ERR__UNEXPECTED = f"{E} weird response, try again"
    ERR__CDN_EXPIRED = f"{E} that discord cdn(?) link is expired, to refresh it open it in a new tab and copy and paste the link at the top"
    ERR__CMD_USAGE = lambda pre, c, E=E: (
        f"{E} it's `{pre}{c.name}" + f" {c.usage}`" if c.usage else "`"
    )
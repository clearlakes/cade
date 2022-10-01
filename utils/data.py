from discord import ActivityType as act
from dataclasses import dataclass
import random
import re

# use options to hide the walls of text
FFMPEG = "ffmpeg -y -hide_banner -loglevel error"
FFPROBE = "ffprobe -v error"

# pad videos to make their sizes even (required to make mp4)
PAD_EVEN = "-vf pad=\"width=ceil(iw/2)*2:height=ceil(ih/2)*2\""

# error prefix
E = "<a:fire:1004208282585530408> **error:**"

@dataclass
class colors:
    """colors used in embeds"""
    CADE =          0xeac597  # used in .info
    PLAYING_TRACK = 0x4287f5  # used when a track starts playing
    ADDED_TRACK =   0x42f55a  # used when a track is added
    CURRENT_TRACK = 0x4e42f5  # used in .nowplaying
    EMBED_BG =      0x2F3136  # same color as embed background

@dataclass
class bot:
    """main stuff used in commands / for the bot"""
    STATUS = lambda: random.choice([
        [act.listening, "relaxing white noise 10 hours"],
        [act.listening, "cheezer"],
        [act.watching, "food battle 2014"],
        [act.playing, "there's the hat, ohhh he went too far! is this guy a rookie"],
        [act.playing, "let me out!!!! get me out of here"],
        [act.playing, "coming back from applebees"],
        [act.playing, "stole 418852014401 bobux"],
        [act.playing, "aint that nathaniel b"],
        [act.playing, "going to applebees"],
        [act.playing, "i miss my wife"],
        [act.playing, "i need money"],
        [act.playing, "mario"]
    ])

    CAT = lambda: random.choice([
        "https://i.imgur.com/1WCgVB5.jpg",
        "https://i.imgur.com/o2Mv3id.gif",
        "https://i.imgur.com/jBdFw84.jpg",
        "https://i.imgur.com/q5MlyL1.jpg",
        "https://i.imgur.com/7lt16yi.jpg",
        "https://i.imgur.com/mXKsgNU.jpg",
        "https://i.imgur.com/UmmYVhK.jpg"
    ])

    PROCESSING = lambda: random.choice([
        "<a:bandy:1004177770554859603>",
        "<a:cadeload:934934660495048716>"
    ])

    PROCESSING_MSG = lambda: random.choice([
        "processing...",
        "loading...",
        "doing something...",
        "ummmmmm...",
        ".............",
        "un momento..."
    ])

    WAITING = "<a:cadewait:945424680351850506>"
    OK = "<:cadeok:934934539124502598>"

@dataclass
class reg:
    """regex stuff most likely copied from somewhere"""
    youtube =   re.compile(r"https?:\/\/(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(watch|v|embed|shorts|playlist)?(?:\.php)?(?:\?(?:v=|list=)|\/))([a-zA-Z0-9\_-]+)") # group 1: type, group 2: id
    url =       re.compile(r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)")  # gets any url
    spotify =   re.compile(r"https?:\/\/open\.spotify\.com\/(track|playlist|album)\/([a-zA-Z0-9\_-]+)")  # group 1: type, group 2: id
    twitter =   re.compile(r"https?:\/\/twitter\.com\/(?:#!\/)?(\w+)\/status(?:es)?\/(\d+)")  # group 1: handle, group 2: status id
    tenor =     re.compile(r"https?:\/\/tenor.com\/view\/.*-(\d+)")  # group 1: tenor id
    gyazo =     re.compile(r"https?:\/\/gyazo.com\/(.*)") # group 1: gyazo id
    color =     re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

@dataclass
class ff:
    """ffmpeg commands used throughout the bot"""
    GET_DIMENSIONS = (
        f"{FFPROBE} -select_streams v -show_entries stream=width,height -of csv=p=0:s=x -"
    )
    GET_DURATION = (
        f"{FFPROBE} -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -"
    )
    GET_STREAM = lambda path, url, ext, start, end: (
        f"{FFMPEG} " + (f"-ss {start} -to {end} " if start else "") + f"-i {url} {path}/output.{ext}"
    )
    MOV_TO_MP4 = lambda path: (
        f"{FFMPEG} -i {path}/input.mov -qscale 0 {path}/output.mp4"
    )
    CREATE_MP4 = lambda path, fps: (
        f"{FFMPEG} -framerate {fps} -i '{path}/%d.png' -vn -i {path}/input.mp4 -c:v libx264 -pix_fmt yuv420p {PAD_EVEN} {path}/output.mp4"
    )
    RESIZE = lambda path, width, height: (
        f"{FFMPEG} -i {path}/input.mp4 -vf scale={width}:{height} {path}/output.mp4".replace("auto", "-2")
    )
    IMGAUDIO = lambda path, audio, length: (
        f"{FFMPEG} -loop 1 -i {path}/input.png -i {audio} -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p -shortest {path}/output.mp4"
    )
    SPEED_UP = lambda path, amount: (
        f"{FFMPEG} -i {path}/input.mp4 -vf 'setpts={1 / amount}*PTS' -af 'atempo={amount}' {path}/output.mp4"
    )

@dataclass
class err:
    """errors used throughout the bot"""
    TIMED_OUT =                  f"{E} timed out"
    COG_RELOAD_ERROR = lambda c: f"{E} could not reload {c}"
    FUNNY_ONLY =                 f"{E} that only works in funny museum"
    TWEET_ERROR =                f"{E} could not send tweet"
    TWITTER_PROFILE_ERROR =      f"{E} could not change profile information"
    TWEET_URL_NOT_FOUND =        f"{E} could not find tweet url/id"
    TWEET_NOT_FOUND =            f"{E} could not find tweet from the given url/id"
    NO_ATTACHMENT_FOUND =        f"{E} no attachment was found"
    NO_ATT_OR_URL_FOUND =        f"{E} no attachment or url was found"
    NO_AUDIO_FOUND =             f"{E} could not find audio file or url"
    WRONG_ATT_TYPE =             f"{E} wrong attachment type"
    HELP_NOT_FOUND =             f"{E} command not found"
    NO_PERMISSIONS_USER =        f"{E} you're missing permissions"
    NO_PERMISSIONS_BOT =         f"{E} i'm missing permissions"
    TAG_DOESNT_EXIST =           f"{E} that tag has not been created yet"
    TAG_ALREADY_EXISTS =         f"{E} that tag already exists"
    NO_TAGS_AT_ALL =             f"{E} no tags were found"
    CANT_SEND_FILE =             f"{E} could not send the file (too large maybe)"
    IMAGE_SERVER_ERROR =         f"{E} can't find image server (not your fault i need to fix this)"
    YT_ERROR = lambda e:         f"{E} could not get video: {e}"
    AUDIO_MAX_LENGTH =           f"{E} audio length is too long (max: 30 minutes)"
    FILE_MAX_SIZE =              f"{E} size too large (max: 2000px)"
    FFMPEG_ERROR =               f"{E} processing the command failed for some reason (maybe not your fault)"
    PIL_ERROR =                  f"{E} processing the file failed for some reason (wrong file type?)"
    INVALID_URL =                f"{E} invalid url"
    INVALID_TIMESTAMP =          f"{E} invalid timestamp (must be min:sec, hr:min:sec, or sec)"
    INVALID_MULTIPLIER =         f"{E} invalid multiplier (should be something like 2x, 1.5, etc.)"
    WEIRD_TIMESTAMPS =           f"{E} the start time must come before the end time"
    BOT_NOT_IN_VC =              f"{E} i'm not in a vc"
    USER_NOT_IN_VC =             f"{E} you're not in the vc"
    NO_MUSIC_PLAYING =           f"{E} nothing is playing right now"
    SINGLE_TRACK_ONLY =          f"{E} only one track can be added at a time"
    NO_MUSIC_RESULTS =           f"{E} no results were found with that query"
    CANT_LOAD_MUSIC =            f"{E} can't play music (could be private/age-restricted/copyrighted)"
    BOT_IN_VC =                  f"{E} i'm already in the vc"
    NOT_IN_QUEUE =               f"{E} that is probably not in the queue"
    MUSIC_NOT_LOOPED =           f"{E} the current song is not being looped (use `.l` to do so)"
    NO_SPOTIFY_ON_YT = lambda t: f"{E} couldn't find `{t}` on youtube sorry (skipping)"
    INVALID_INDEX =              f"{E} invalid index"
    INVALID_SEEK =               f"{E} cannot skip that far into the track"
    MOV_TO_MP4_ERROR =           f"{E} there was an issue converting from mov to mp4"
    UNEXPECTED =                 f"{E} weird response, try again"
    CMD_USAGE = lambda c:        f"{E} usage: `.{c.name}" + f" {c.usage}`" if c.usage else "`"
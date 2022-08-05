from dataclasses import dataclass
import random
import re

# use options to hide the walls of text
FFMPEG = "ffmpeg -y -hide_banner -loglevel error"
FFPROBE = "ffprobe -v error"

# pad videos to make their sizes even (required for mp4)
PAD_EVEN = "-vf pad=\"width=ceil(iw/2)*2:height=ceil(ih/2)*2\""

# error prefix
E = "<a:fire:1004208282585530408> **error:**"

CAT = lambda : random.choice([
    "https://i.imgur.com/1WCgVB5.jpg", 
    "https://i.imgur.com/o2Mv3id.gif",
    "https://i.imgur.com/jBdFw84.jpg",
    "https://i.imgur.com/q5MlyL1.jpg",
    "https://i.imgur.com/7lt16yi.jpg",
    "https://i.imgur.com/mXKsgNU.jpg",
    "https://i.imgur.com/UmmYVhK.jpg"
])

@dataclass
class colors:
    """colors used in embeds"""
    CADE =          0xd9ba93  # used in .info
    PLAYING_TRACK = 0x4287f5  # used when a track starts playing
    ADDED_TRACK =   0x42f55a  # used when a track is added
    CURRENT_TRACK = 0x4e42f5  # used in .nowplaying

@dataclass
class emoji:
    PROCESSING = lambda : random.choice([
        "<a:bandy:1004177770554859603>",
        "<a:cadeload:934934660495048716>"
    ])
    OK = (
        "<:cadeok:934934539124502598>"
    )

@dataclass
class reg:
    url = re.compile(r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)')  # gets any url
    youtube = re.compile(r'(?:https?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed|shorts)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]+)')
    twitter = re.compile(r'https?:\/\/twitter\.com\/(?:#!\/)?(\w+)\/status(?:es)?\/(\d+)')  # group 1: handle, group 2: status id
    tenor = re.compile(r'https?:\/\/tenor.com\/view\/.*-(\d+)')  # group 1: tenor id

@dataclass
class ff:
    """ffmpeg commands used throughout the bot"""
    GET_FULL_STREAM = lambda url, filename: (
        f"{FFMPEG} -i {url} {filename}"
    )
    GET_CUT_STREAM = lambda url, start, end, filename: (
        f"{FFMPEG} -ss {start} -to {end} -i {url} {filename}"
    )
    GET_DIMENSIONS = lambda filename: (
        f"{FFPROBE} -select_streams v -show_entries stream=width,height -of csv=p=0:s=x {filename}"
    )
    GET_DURATION = lambda filename: (
        f"{FFPROBE} -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {filename}"
    )
    MOV_TO_MP4 = lambda dir: (
        f"{FFMPEG} -i {dir}/input.mov -qscale 0 {dir}/output.mp4"
    )
    CREATE_MP4 = lambda dir, fps, audio_source: (
        f"{FFMPEG} -framerate {fps} -i '{dir}/%d.png' -vn -i {dir}/{audio_source} -c:v libx264 -pix_fmt yuv420p {PAD_EVEN} {dir}/output.mp4"
    )
    RESIZE = lambda filename, size: (
        f"{FFMPEG} -i {filename} -f mp4 -movflags frag_keyframe+empty_moov -vf scale={size[0]}:{size[1]} pipe:".replace("auto", "-2")
    )
    IMGAUDIO = lambda dir, audio, length: (
        f"{FFMPEG} -loop 1 -i {dir}/input.png -i {audio} -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p -shortest {dir}/output.mp4"
    )

@dataclass
class err:
    """errors used throughout the bot"""
    TIMED_OUT =             f"{E} timed out"
    COG_RELOAD_ERROR =      f"{E} could not reload"
    FUNNY_ONLY =            f"{E} that only works in funny museum"
    TWEET_ERROR =           f"{E} could not send tweet"
    TWITTER_PROFILE_ERROR = f"{E} could not change profile information"
    TWEET_URL_NOT_FOUND =   f"{E} could not find tweet url/id"
    TWEET_NOT_FOUND =       f"{E} could not find tweet from the given url/id"
    NO_ATTACHMENT_FOUND =   f"{E} no attachment was found"
    NO_ATT_OR_URL_FOUND =   f"{E} no attachment or url was found"
    NO_AUDIO_FOUND =        f"{E} could not find audio file or url"
    WRONG_ATT_TYPE =        f"{E} wrong attachment type"
    HELP_NOT_FOUND =        f"{E} command not found"
    NO_PERMISSIONS_USER =   f"{E} you're missing permissions"
    NO_PERMISSIONS_BOT =    f"{E} i'm missing permissions"
    TAG_DOESNT_EXIST =      f"{E} that tag has not been created yet"
    TAG_EXISTS =            f"{E} that tag already exists"
    NO_TAGS_AT_ALL =        f"{E} no tags were found"
    CANT_SEND_FILE =        f"{E} could not send the file for some reason"
    YOUTUBE_ERROR =         f"{E} could not get video information for some reason"
    AUDIO_MAX_LENGTH =      f"{E} audio length is too long (max: 30 minutes)"
    FILE_MAX_SIZE =         f"{E} size too large (max: 2000px)"
    FFMPEG_ERROR =          f"{E} processing the command failed for some reason"
    INVALID_URL =           f"{E} invalid url"
    INVALID_TIMESTAMP =     f"{E} invalid timestamp (must be min:sec, hr:min:sec, or sec)"
    WEIRD_TIMESTAMPS =      f"{E} the start time must come before the end time"
    BOT_NOT_IN_VC =         f"{E} i'm not in a vc"
    USER_NOT_IN_VC =        f"{E} you're not in the vc"
    NO_MUSIC_PLAYING =      f"{E} nothing is playing right now"
    INVALID_MUSIC_URL =     f"{E} only youtube/spotify links can be used"
    NO_MUSIC_RESULTS =      f"{E} no results were found with that query"
    BOT_IN_VC =             f"{E} i'm already in the vc"
    VALUE_NOT_IN_QUEUE =    f"{E} that is probably not in the queue"
    MUSIC_NOT_LOOPED =      f"{E} the current song is not being looped (use `.l` to do so)"
    MUSIC_URL_NOT_FOUND =   f"{E} missing track url"
    PLAYLIST_DOESNT_EXIST = f"{E} that playlist doesn't exist"
    PLAYLIST_IS_EMPTY =     f"{E} that playlist is empty"
    INVALID_INDEX =         f"{E} invalid index"
    INVALID_SEEK =          f"{E} cannot skip that far into the track"
    MOV_TO_MP4_ERROR =      f"{E} there was an issue converting from mov to mp4"
    UNEXPECTED =            f"{E} unexpected response uhh try again?"
    USAGE = lambda c, u:    f"{E} usage: `.{c}" + f" {u}`" if u else "`" 
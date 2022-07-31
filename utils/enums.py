from enum import Enum
from shlex import split
from functools import partial

# use options to hide the walls of text
FFMPEG = "ffmpeg -y -hide_banner -loglevel error"
FFPROBE = "ffprobe -v error"

# pad videos to make their sizes even (required for mp4)
PAD_EVEN = "-vf pad=\"width=ceil(iw/2)*2:height=ceil(ih/2)*2\""

class ff(Enum):
    """ffmpeg commands used throughout the bot"""
    GET_FULL_STREAM = partial(lambda url, filename: split(f"{FFMPEG} -i {url} {filename}"))
    GET_CUT_STREAM =  partial(lambda url, start, end, filename: split(f"{FFMPEG} -ss {start} -to {end} -i {url} {filename}"))
    GET_DIMENSIONS =  partial(lambda filename: split(f"{FFPROBE} -select_streams v -show_entries stream=width,height -of csv=p=0:s=x {filename}"))
    GET_DURATION =    partial(lambda filename: split(f"{FFPROBE} -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {filename}"))
    MOV_TO_MP4 =      partial(lambda dir: split(f"{FFMPEG} -i {dir}/input.mov -qscale 0 {dir}/output.mp4"))
    CREATE_MP4 =      partial(lambda dir, fps, audio_source: split(f"{FFMPEG} -framerate {fps} -i '{dir}/%d.png' -vn -i {dir}/{audio_source} -c:v libx264 -pix_fmt yuv420p {PAD_EVEN} {dir}/output.mp4"))
    RESIZE =          partial(lambda filename, size: split(f"{FFMPEG} -i {filename} -f mp4 -movflags frag_keyframe+empty_moov -vf scale={size[0]}:{size[1]} pipe:".replace("auto", "-2")))
    IMGAUDIO =        partial(lambda dir, audio, length: split(f"{FFMPEG} -loop 1 -i {dir}/input.png -i {audio} -ss 0 -t {length} -c:v libx264 -tune stillimage -c:a aac -pix_fmt yuv420p -shortest {dir}/output.mp4"))

class err(Enum):
    """errors used throughout the bot"""
    TIMED_OUT =             "**Error:** timed out"
    COG_RELOAD_ERROR =      "**Error:** could not reload"
    FUNNY_ONLY =            "**Error:** that only works in funny museum"
    TWEET_ERROR =           "**Error:** could not send tweet"
    TWITTER_PROFILE_ERROR = "**Error:** could not change profile information"
    TWEET_URL_NOT_FOUND =   "**Error:** could not find tweet url/id"
    TWEET_NOT_FOUND =       "**Error:** could not find tweet from the given url/id"
    NO_ATTACHMENT_FOUND =   "**Error:** no attachment was found"
    NO_ATT_OR_URL_FOUND =   "**Error:** no attachment or url was found"
    NO_AUDIO_FOUND =        "**Error:** could not find audio file or url"
    WRONG_ATT_TYPE =        "**Error:** wrong attachment type"
    HELP_NOT_FOUND =        "**Error:** command not found"
    NO_PERMISSIONS_USER =   "**Error:** you're missing permissions"
    NO_PERMISSIONS_BOT =    "**Error:** i'm missing permissions"
    TAG_DOESNT_EXIST =      "**Error:** that tag has not been created yet"
    TAG_EXISTS =            "**Error:** that tag already exists"
    NO_TAGS_AT_ALL =        "**Error:** no tags were found"
    CANT_SEND_FILE =        "**Error:** could not send the file for some reason"
    YOUTUBE_ERROR =         "**Error:** could not get video information for some reason"
    AUDIO_MAX_LENGTH =      "**Error:** audio length is too long (max: 30 minutes)"
    FILE_MAX_SIZE =         "**Error:** size too large (max: 2000px)"
    FFMPEG_ERROR =          "**Error:** processing the command failed for some reason"
    INVALID_URL =           "**Error:** invalid url"
    INVALID_TIMESTAMP =     "**Error:** invalid timestamp (must be min:sec, hr:min:sec, or sec)"
    WEIRD_TIMESTAMPS =      "**Error:** the start time must come before the end time"
    BOT_NOT_IN_VC =         "**Error:** i'm not in a vc"
    USER_NOT_IN_VC =        "**Error:** you're not in the vc"
    NO_MUSIC_PLAYING =      "**Error:** nothing is playing right now"
    INVALID_MUSIC_URL =     "**Error:** only youtube/spotify links can be used"
    NO_MUSIC_RESULTS =      "**Error:** no results were found with that query"
    BOT_IN_VC =             "**Error:** i'm already in the vc"
    VALUE_NOT_IN_QUEUE =    "**Error:** that is probably not in the queue"
    MUSIC_NOT_LOOPED =      "**Error:** the current song is not being looped (use `.l` to do so)"
    MUSIC_URL_NOT_FOUND =   "**Error:** missing track url"
    PLAYLIST_DOESNT_EXIST = "**Error:** that playlist doesn't exist"
    PLAYLIST_IS_EMPTY =     "**Error:** that playlist is empty"
    INVALID_INDEX =         "**Error:** invalid index"
    INVALID_SEEK =          "**Error:** cannot skip that far into the track"
    MOV_TO_MP4_ERROR =      "**Error:** there was an issue converting from mov to mp4"
    UNEXPECTED =            "**Error:** unexpected response uhh try again?"
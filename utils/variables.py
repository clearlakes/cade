from async_spotify.authentification.authorization_flows import ClientCredentialsFlow
from async_spotify import SpotifyApiClient
import tweepy

from dataclasses import dataclass
import configparser
import re

# load config file
config = configparser.ConfigParser()
config.read("config.ini")

# twitter handle
handle = str(config.get("twitter", "handle"))

@dataclass
class Colors:
    info = 0xd9ba93
    gray = 0x2f3136
    now_playing = 0x4287f5
    added_track = 0x42f55a
    playing_track = 0x4e42f5

@dataclass
class Regex:
    # universal url regex
    url = re.compile(r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)')

    youtube = re.compile(r'(?:https?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed|shorts)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]+)')
    twitter = re.compile(r'https?:\/\/twitter\.com\/(?:#!\/)?(\w+)\/status(?:es)?\/(\d+)') # group 1: handle, group 2: status id
    tenor = re.compile(r'https?:\/\/tenor.com\/view\/.*-(\d+)') # group 1: tenor id
    emoji = re.compile(r':(?P<name>[a-zA-Z0-9_]{2,32}):')
    ansi = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')

@dataclass
class Keys:
    get_list = lambda section: [str(config.get(section, x)) for x in config.options(section) if x != "handle"] # ignore twitter handle
    get = lambda section, option: str(config.get(section, option))
    
    lavalink = get_list('lavalink')
    twitter = get_list('twitter')
    spotify = get_list('spotify')

    tenor = get("tenor", "key")
    imoog_port = get("imoog", "port")
    imoog_domain = get("imoog", "domain")
    imoog_secret = get("imoog", "key")
    
class Clients:
    def twitter(self):
        twitter_keys = Keys.twitter
        auth = tweepy.OAuthHandler(twitter_keys[0], twitter_keys[1])
        auth.set_access_token(twitter_keys[2], twitter_keys[3])

        return tweepy.API(auth)

    def spotify(self):
        spotify_keys = Keys.spotify

        # use credentials from spotify_keys
        auth_flow = ClientCredentialsFlow(
            application_id = spotify_keys[0],
            application_secret = spotify_keys[1]
        )

        auth_flow.load_from_env()
        return SpotifyApiClient(auth_flow)
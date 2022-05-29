from async_spotify.authentification.authorization_flows import ClientCredentialsFlow
from async_spotify import SpotifyApiClient
import tweepy

import configparser
import re

# shortcut to use options that hide the wall of text
FFMPEG = "ffmpeg -y -hide_banner -loglevel error"

# load config file
config = configparser.ConfigParser()
config.read("config.ini")

HANDLE = str(config.get("twitter", "handle"))

class Regex:
    def __init__(self):
        # universal url regex
        self.url = re.compile(r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*)')

        self.youtube = re.compile(r'(?:https?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed|shorts)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]+)')
        self.twitter = re.compile(r'https?:\/\/twitter\.com\/(?:#!\/)?(\w+)\/status(?:es)?\/(\d+)') # group 1: handle, group 2: status id
        self.tenor = re.compile(r'https?:\/\/tenor.com\/view\/.*-(\d+)') # group 1: tenor id
        self.emoji = re.compile(r':(?P<name>[a-zA-Z0-9_]{2,32}):')
        self.ansi = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')

class Keys:
    def __init__(self):
        self.tenor = str(config.get("tenor", "key"))
        self.twitter = [str(config.get("twitter", x)) for x in config.options("twitter") if x != "handle"]
        self.lavalink = [config.get("lavalink", x) for x in config.options("lavalink")]
        self.spotify = [str(config.get("spotify", x)) for x in config.options("spotify")]
    
class Clients:
    @classmethod
    def twitter(self):
        twitter_keys = [str(config.get("twitter", x)) for x in config.options("twitter") if x != "handle"]
        auth = tweepy.OAuthHandler(twitter_keys[0], twitter_keys[1])
        auth.set_access_token(twitter_keys[2], twitter_keys[3])

        return tweepy.API(auth)

    @classmethod
    def spotify(self):
        spotify_keys = [str(config.get("spotify", x)) for x in config.options("spotify")]

        # use credentials from spotify_keys
        auth_flow = ClientCredentialsFlow(
            application_id = spotify_keys[0],
            application_secret = spotify_keys[1]
        )

        auth_flow.load_from_env()
        return SpotifyApiClient(auth_flow)
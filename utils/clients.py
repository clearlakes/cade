from async_spotify.authentification.authorization_flows import ClientCredentialsFlow
from async_spotify import SpotifyApiClient
import tweepy

from dataclasses import dataclass
import configparser

# load config file
config = configparser.ConfigParser()
config.read("config.ini")

# twitter handle
handle = str(config.get("twitter", "handle"))

@dataclass
class Keys:
    get_list = lambda section: [str(config.get(section, x)) for x in config.options(section) if x != "handle"]  # ignore twitter handle
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
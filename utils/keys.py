import configparser
from dataclasses import dataclass


class BaseKey:
    def __init__(self, section: str):
        # load config file
        self._config = configparser.ConfigParser(interpolation=None)
        self._config.read("config.ini")

        self._section = section

    def get(self, key):
        return self._config.get(self._section, key, fallback=None)

    @property
    def all(self):
        return dict(self._config.items(self._section)) if self else {}

    def __bool__(self):
        return self._config.has_section(self._section)


class LavalinkKeys(BaseKey):
    def __init__(self):
        super().__init__("lavalink")
        self.host = self.get("host")
        self.port = self.get("port")
        self.secret = self.get("secret")
        self.region = self.get("region")

        self.ordered_keys = (self.host, self.port, self.secret, self.region)


class ImageServerKeys(BaseKey):
    def __init__(self):
        super().__init__("image-server")
        self.domain = self.get("domain")
        self.secret = self.get("secret")


class OtherKeys(BaseKey):
    def __init__(self):
        super().__init__("other")
        self.tenor = self.get("tenor")
        self.gyazo = self.get("gyazo")


@dataclass
class Keys:
    lavalink = LavalinkKeys()
    image = ImageServerKeys()
    tenor = OtherKeys().tenor
    gyazo = OtherKeys().gyazo

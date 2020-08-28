import random
from enum import Enum, auto
import time
import urllib3
from threading import Thread, Lock
import json
from credentials.api_credentials import client_id, secret
from utility import file_loader as f

TOGGLEABLE = 3


class MessageType(Enum):
    FUNCTIONAL = auto()
    CHAT = auto()
    COMMAND = auto()
    SPAM = auto()
    HELPFUL = auto()
    SPECIAL = auto()
    SUBSCRIBER = auto()
    BLACKLISTED = auto()

    def __str__(self):
        return self.name


class ToggleType(Enum):
    ON = auto()
    OFF = auto()
    COMMAND = auto()
    SPAM = auto()
    HELPFUL = auto()
    SPECIAL = auto()
    SUBSCRIBER = auto()
    BLACKLISTED = auto()

    @staticmethod
    def can_toggle(self, tipe):
        return tipe.value >= TOGGLEABLE


class Message:
    def __init__(self, msg: str, msg_type: MessageType, channel=None):
        self.content = msg
        self.type = msg_type
        self.channel = channel

    def __str__(self):
        if self.channel is None:
            return "(" + self.content.rstrip() + ", " + str(self.type) + ")"
        return "(" + self.content.rstrip() + ", " + str(self.type) + "," + self.channel + ")"


class Validation:
    def __init__(self, boolean: bool, correct_ans: str):
        self.boolean = boolean
        self.correct = correct_ans


class RandomLinePicker:
    def __init__(self, fp):
        self.lines_said = []
        self.lines = []
        lines = open(fp)
        for line in lines:
            self.lines.append(line.rstrip())

    def get_line(self):
        if len(self.lines) == 0:
            self.lines = self.lines_said
            self.lines_said = []
        line = random.choice(self.lines)
        self.lines.remove(line)
        self.lines_said.append(line)
        return line


class IDCache:
    def __init__(self):
        self.state = f.load("texts/streamer_ids.txt", {})
        self.lock = Lock()

    def __contains__(self, item):
        return item in self.state

    def get_id(self, channel):
        return self.state.get(channel, None)

    def add_id(self, channel, channel_id):
        self.state[channel] = channel_id
        self.lock.acquire()
        f.save(self.state, "texts/streamer_ids.txt")
        self.lock.release()


class MessageLimiter:
    def __init__(self):
        self.dct = dict()

    def can_send(self, channel: str, command: str, tp: int, renew=False):
        if channel not in self.dct:
            self.dct[channel] = dict()
        ts = self.dct.get(channel).get(command, None)
        current_ts = time.time()
        if ts is not None:
            delta = current_ts - ts
            if delta > tp:
                self.dct[channel][command] = current_ts
                return True
            if renew:
                self.dct[channel][command] = current_ts
            return False
        else:
            self.dct[channel][command] = current_ts
            return True

    def seconds_since_limit(self, channel: str, command: str):
        current_ts = time.time()
        previous_ts = self.dct.get(channel, dict()).get(command, current_ts)
        return round(current_ts - previous_ts)


class TwitchStatus:
    def __init__(self, user: str, channels: list, id_cache: IDCache):
        self._client = client_id
        self._secret = secret
        self.state = {}
        self._user = user
        self._channels = []
        for chan in channels:
            self.add_channel(chan)
        self._manager = urllib3.PoolManager()
        self._bearer = self._get_bearer()
        user_token = f.load("credentials/user_token.txt")
        self._user_token = user_token.get("access_token")
        self._refresh_token = user_token.get("refresh_token")
        self._cache = id_cache
        self._id = self.get_id(self._user)
        self._count = 0

        self.alive = True
        self.update_thread = Thread(target=self._update_channels)
        self.update_thread.daemon = True
        self.update_thread.start()

    def stop(self):
        self.alive = False
        self.update_thread.join()

    def _get_bearer(self):
        base = "https://id.twitch.tv/oauth2/token"
        parameters = {
            "client_id": self._client,
            "client_secret": self._secret,
            "grant_type": "client_credentials",
        }
        response = self._manager.request("POST", base, fields=parameters)
        if response.status != 200:
            raise Exception("TwitchStatus couldn't get a bearer token from twitch API")
        js = json.loads(response.data.decode("UTF-8"))
        return js.get("access_token")

    def _refresh_access_token(self):
        base = "https://id.twitch.tv/oauth2/token"
        parameters = {
            "client_id": self._client,
            "client_secret": self._secret,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token
        }
        response = self._manager.request("POST", base, fields=parameters)
        if response.status != 200:
            raise Exception("TwitchStatus couldn't get a bearer token from twitch API")
        js = json.loads(response.data.decode("UTF-8"))
        self._user_token = js.get("access_token")
        self._refresh_token = js.get("refresh_token")
        f.save({"access_token": self._user_token, "refresh_token": self._refresh_token}, "credentials/user_token.txt")

    def get_id(self, channel):
        if channel in self._cache:
            return self._cache.get_id(channel)
        else:
            headers = {
                "Client-id": self._client,
                "Accept": "application/vnd.twitchtv.v5+json"
            }
            fields = {
                "login": channel
            }
            base = "https://api.twitch.tv/kraken/users"
            response = self._manager.request("GET", base, headers=headers, fields=fields).data.decode("UTF-8")
            data = json.loads(response)
            channel_id = data.get("users")[0].get("_id")
            self._cache.add_id(channel, channel_id)
            return channel_id

    def _update_channel(self, channel):
        base = "https://api.twitch.tv/helix/streams"
        parameters = {"user_login": channel}
        headers = {
            "Client-ID": self._client,
            "Authorization": f"Bearer {self._bearer}"
        }
        response = self._manager.request("GET", base, fields=parameters, headers=headers)
        if response.status == 401:
            # Bearer has expired
            self._bearer = self._get_bearer()
            self._update_channel(channel)
        elif response.status != 200:
            # Something weird happened so we do nothing
            return
        else:
            # 200 ok
            dct = json.loads(response.data.decode("UTF-8"))
            data = dct.get("data")
            if len(data) == 0:
                # not live
                self.state[channel]["live"] = False
                self.state[channel]["activity"] = "Prechat"
                return
            # live
            self.state[channel]["live"] = True
            # get game
            game_id = data[0].get("game_id")
            base = "https://api.twitch.tv/helix/games"
            parameters = {
                "id": game_id
            }
            response = self._manager.request("GET", base, fields=parameters, headers=headers)
            dct = json.loads(response.data.decode("UTF-8"))
            data = dct.get("data")
            if len(data) == 0:
                # something weird happened
                self.state[channel]["activity"] = "Prechat"
                return
            self.state[channel]["activity"] = data[0].get("name")

    def _is_user_subscribed(self, channel):
        request_url = "https://api.twitch.tv/kraken/users/" + self._id + "/subscriptions/" + self.get_id(channel)
        headers = {
            "Accept": "application/vnd.twitchtv.v5+json",
            "Client-ID": self._client,
            "Authorization": f"OAuth {self._user_token}"
        }
        response = self._manager.request("GET", request_url, headers=headers)
        if response.status == 401:
            # user token has expired and needs to be refreshed
            self._user_token = self._refresh_access_token()
            return self._is_user_subscribed(channel)
        elif response.status == 404:
            return False
        elif response.status == 200:
            return True
        else:
            raise Exception("Unknown status code received when trying to check if user is subscribed to channel")

    def get_status(self, channel):
        return self.state.get(channel, {"live": False, "activity": "Prechat"})

    def is_subscribed_to(self, channel):
        return self.state[channel]["subscribed"]

    def add_channel(self, channel):
        self._channels.append(channel)
        self.state[channel] = self.state.get(channel, {"live": False, "activity": "Prechat"})

    def delete_channel(self, channel):
        if self._channels.__contains__(channel):
            self._channels.remove(channel)

    def _update_channels(self):
        while self.alive:
            check = self._count == 0
            for channel in self._channels:
                time.sleep(1)
                if check:
                    self.state[channel]["subscribed"] = self._is_user_subscribed(channel)
                self._update_channel(channel)
            self._count += 1
            if self._count == 200:
                self._count = 0
            time.sleep(15)


class TimedTask:
    def __init__(self, func, loop_time, manager=None):
        self.func = func
        self.loop_time = loop_time
        self.manager = manager
        self.state = {}
        self.alive = False
        self.thread = Thread(target=self.run)
        self.thread.daemon = True

    def start(self):
        self.alive = True
        self.thread.start()

    def join(self):
        self.thread.join()

    def stop(self):
        self.alive = False

    def restart(self):
        if not self.alive:
            self.alive = True
            self.thread = Thread(target=self.run)
            self.thread.daemon = True
            self.thread.start()

    def setup(self, func):
        if self.manager is None:
            func(self.state)
        else:
            func(self.state, self.manager)

    def run(self):
        while self.alive:
            if self.manager is None:
                self.func(self.state)
            else:
                self.func(self.state, self.manager)
            time.sleep(self.loop_time)


class CircularArray:
    def __init__(self, positionable_iterable):
        self.array = positionable_iterable
        self.len = len(positionable_iterable)
        self.pos = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.pos == self.len:
            self.pos = 0
        item = self.array[self.pos]
        self.pos += 1
        return item


class LockedData:
    def __init__(self, obj):
        self.data = obj
        self.lock = Lock()
        self.buffer_dict = dict()

    def access(self, func, **kwargs):
        self.lock.acquire()
        val = func(self.data, kwargs)
        self.lock.release()
        return val

    def buffered_write(self, func, **kwargs):
        locked = self.lock.acquire(False)
        self.buffer_dict[func.__name__] = self.buffer_dict.get(func.__name__, [])
        if locked:
            if len(self.buffer_dict.get(func.__name__)) != 0:
                for kwarg in self.buffer_dict.get(func.__name__):
                    func(self.data, kwarg)
                self.buffer_dict[func.__name__] = []
            func(self.data, kwargs)
            self.lock.release()
        else:
            self.buffer_dict.get(func.__name__).append(kwargs)

import random
from enum import Enum, auto
import time
import urllib3
from urllib.parse import urlencode
from threading import Thread, Lock
import json
from credentials.api_credentials import client_id, secret
from utility import file_loader as f
from utility import functions

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
    def __init__(self, msg: str, msg_type: MessageType, channel):
        self.content = msg
        self.type = msg_type
        self.channel = channel

    def __str__(self):
        return "(" + self.content.rstrip() + ", " + str(self.type) + "," + self.channel + ")"


class Validation:
    def __init__(self, boolean: bool, correct_ans: str):
        self.boolean = boolean
        self.correct = correct_ans


class RandomLinePicker:
    def __init__(self, fp):
        self.file_pointer = fp
        self.lines_said = []
        self.lines = f.load(fp)

    def get_line(self):
        if len(self.lines) == 0:
            self.lines = self.lines_said
            self.lines_said = []
        line = random.choice(self.lines)
        self.lines.remove(line)
        self.lines_said.append(line)
        return line

    def add_line(self, line: str):
        if line not in self.lines:
            self.lines.append(line)
            f.save(self.lines.extend(self.lines_said), self.file_pointer)

    def remove_line(self, line: str):
        if line in self.lines:
            self.lines.remove(line)
            f.save(self.lines.extend(self.lines_said), self.file_pointer)


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
        subscribed = f.load("texts/subscribed.txt", {})
        for chan in channels:
            self.add_channel(chan)
            self.state[chan]["subscribed"] = subscribed.get(chan, "False")
        self._manager = urllib3.PoolManager()
        self._bearer = self._get_bearer()
        self._cache = id_cache

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

    def get_status(self, channel):
        return self.state.get(channel, {"live": False, "activity": "Prechat"})

    def is_subscribed_to(self, channel):
        return functions.convert(self.state[channel]["subscribed"])

    def add_subscription(self, channel):
        self.state[channel]["subscribed"] = "True"
        self.save_subscriptions()

    def remove_subscription(self, channel):
        self.state[channel]["subscribed"] = "False"
        self.save_subscriptions()

    def save_subscriptions(self):
        dct = {}
        for channel in self._channels:
            dct[channel] = self.state[channel]["subscribed"]
        f.save(dct, "texts/subscribed.txt")

    def add_channel(self, channel):
        self._channels.append(channel)
        self.state[channel] = self.state.get(channel, {"live": False, "activity": "Prechat"})

    def delete_channel(self, channel):
        if self._channels.__contains__(channel):
            self._channels.remove(channel)

    def _update_channels(self):
        while self.alive:
            for channel in self._channels:
                time.sleep(1)
                self._update_channel(channel)
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

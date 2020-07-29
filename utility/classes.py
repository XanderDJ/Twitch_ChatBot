import random
from enum import Enum
import time
import urllib3
from threading import Thread
import json


class MessageType(Enum):
    FUNCTIONAL = 1
    COMMAND = 2
    SPAM = 3
    HELPFUL = 4
    SPECIAL = 5
    SUBSCRIBER = 6
    CHAT = 7
    BLACKLISTED = 8

    def __str__(self):
        return self.name


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
    def __init__(self, client_id: str, secret: str, channels: list):
        self._client = client_id
        self._secret = secret
        self._channels = channels
        self._manager = urllib3.PoolManager()
        self._bearer = self._get_bearer()
        self.state = {}
        self.update_thread = Thread(target=self._update_channels)
        self.update_thread.daemon = True
        self.update_thread.start()
        self.alive = True

    def stop(self):
        self.alive = False
        self.update_thread.join()

    def _get_bearer(self):
        base = "https://id.twitch.tv/oauth2/token"
        parameters = {
            "client_id": self._client,
            "client_secret": self._secret,
            "grant_type": "client_credentials"
        }
        response = self._manager.request("POST", base, fields=parameters)
        if response.status != 200:
            raise Exception("TwitchStatus couldn't get a bearer token from twitch API")
        js = json.loads(response.data.decode("UTF-8"))
        return js.get("access_token")

    def _is_live(self, channel):
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
            return self._is_live(channel)
        else:
            dct = json.loads(response.data.decode("UTF-8"))
            data = dct.get("data")
            if len(data) == 0:
                return False
            return True

    def get_status(self, channel):
        return self.state.get(channel, True)

    def add_channel(self, channel):
        self._channels.append(channel)

    def delete_channel(self, channel):
        if self._channels.__contains__(channel):
            self._channels.remove(channel)

    def _update_channels(self):
        while self.alive:
            time.sleep(15)
            for channel in self._channels:
                time.sleep(1)
                status = self._is_live(channel)
                self.state[channel] = status

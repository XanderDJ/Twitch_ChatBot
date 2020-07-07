import random
from enum import Enum
import time


class MessageType(Enum):
    FUNCTIONAL = 1
    COMMAND = 2
    SPAM = 3
    HELPFUL = 4
    SPECIAL = 5
    SUBSCRIBER = 6
    CHAT = 7
    BLACKLISTED = 8


class Message:
    def __init__(self, msg: str, msg_type: MessageType):
        self.content = msg
        self.type = msg_type

    def __str__(self):
        return "(" + self.content.rstrip() + ", " + str(self.type) + ")"


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

import asynchat
import asyncore
import json
import logging
import re
import socket
import sys
import time
import random
import enchant
from datetime import datetime, timedelta
from threading import Thread
import urllib3
from enum import Enum
from text_to_dictionary import *

PY3 = sys.version_info[0] == 3
if PY3:
    from urllib.request import urlopen, Request
    from queue import Queue

logger = logging.getLogger(name="tmi")

http = urllib3.PoolManager()


def define(word):
    html = http.request("GET", "http://dictionary.reference.com/browse/" + word + "?s=t").data.decode("UTF-8")
    items = re.findall('<meta name=\"description\" content=\"(.*) See more.\">', html, re.S)
    defs = [re.sub('<.*?>', '', x).strip() for x in items]
    return defs[0]


def contains_word(msg, words):
    for word in words:
        if word in " " + msg + " ":
            return True
    return False


def contains_all(msg, words):
    for word in words:
        if word not in " " + msg + " ":
            return False
    return True


def is_word(msg, words):
    for word in words:
        if msg == word:
            return True
    return False


def convert(string: str) -> bool:
    if string == "True":
        return True
    return False


def load_emotes():
    fh = open("emotes.txt", "r")
    emotes = dict()
    emotes["all_emotes"] = []
    for emote in fh:
        emote = emote.rstrip()
        emotes["all_emotes"] += [emote]
        emotes[emote.lower()] = emote
    fh.close()
    return emotes


def hammington(str1, str2):
    str1 = str1.lower()
    str2 = str2.lower()
    len1 = len(str1)
    len2 = len(str2)
    smallest = min(len1, len2)
    starting_dist = abs(len1 - len2)
    if str1[0] != str2[0] or str1[0:smallest] == str2[0:smallest]:
        starting_dist += 3
    for i in range(smallest):
        if str1[i] != str2[i]:
            starting_dist += 1
    return starting_dist


def validate_emote(emote, emotes):
    for correct_emote in emotes:
        dist = hammington(emote, correct_emote)
        if dist == 1:
            return False
    return True


def subscriber_type(months):
    if months == "1":
        return "bronze"
    elif months == "3":
        return "silver"
    elif months == "6":
        return "gold"
    elif months == "12":
        return "pink"
    elif months == "24":
        return "jump king"
    elif months == "32":
        return "snail"
    else:
        return months + " months"


def count_os(string):
    count = 0
    max_count = 0
    prev_char = ""
    for char in string:
        if prev_char == "y" and char.lower() == "o":
            count += 1
        elif char.lower() == "o" and prev_char == "o" and count > 0:
            count += 1
        else:
            if count > max_count:
                max_count = count
            count = 0
        prev_char = char.lower()

    if count > max_count:
        max_count = count
    return max_count


class MessageType(Enum):
    FUNCTIONAL = 1
    COMMAND = 2
    SPAM = 3
    HELPFUL = 4
    SPECIAL = 5


class Message:
    def __init__(self, msg: str, msg_type: MessageType):
        self.content = msg
        self.type = msg_type

    def __str__(self):
        return "(" + self.content.rstrip() + ", " + str(self.type) + ")"


class RandomGreeting:
    def __init__(self):
        self.greetings_said = set()
        self.greetings = set()
        greetings = open("hello.txt")
        for greeting in greetings:
            self.greetings.add(greeting.rstrip())

    def get_greeting(self):
        if len(self.greetings) == 0:
            self.greetings = self.greetings_said
            self.greetings_said = set()
        greeting = self.greetings.pop()
        self.greetings_said.add(greeting)
        return greeting


class EightBall:
    def __init__(self):
        self.prophecies_said = set()
        self.prophecies = set()
        prophecies = open("8ball.txt")
        for prophecy in prophecies:
            self.prophecies.add(prophecy.rstrip())

    def get_prophecy(self):
        if len(self.prophecies) == 0:
            self.prophecies = self.prophecies_said
            self.prophecies_said = set()
        prophecy = self.prophecies.pop()
        self.prophecies_said.add(prophecy)
        return prophecy


class RandomLinePicker:
    def __init__(self, fp):
        self.lines_said = set()
        self.lines = set()
        lines = open(fp)
        for line in lines:
            self.lines.add(line.rstrip())

    def get_line(self):
        if len(self.lines) == 0:
            self.lines = self.lines_said
            self.lines_said = set()
        line = self.lines.pop()
        self.lines_said.add(line)
        return line


class MessageLimiter:
    def __init__(self):
        self.dct = dict()

    def can_send(self, msg, tp, renew=False):
        ts = self.dct.get(msg, None)
        current_ts = time.time()
        if ts is not None:
            delta = current_ts - ts
            if delta > tp:
                self.dct[msg] = current_ts
                return True
            if renew:
                self.dct[msg] = current_ts
            return False
        else:
            self.dct[msg] = current_ts
            return True


class TwitchChat(object):

    def __init__(self, user, oauth, channels):
        self.logger = logging.getLogger(name="twitch_chat")
        self.channels = channels
        self.user = user
        self.oauth = oauth
        self.channel_servers = {'irc.chat.twitch.tv:6667': {'channel_set': channels}}
        self.irc_handlers = []
        self.greeting_gen = RandomGreeting()
        self.eightball = EightBall()
        self.facts = RandomLinePicker("facts.txt")
        self.friends = RandomLinePicker("friend.txt")
        self.byes = RandomLinePicker("goodbyes.txt")
        self.jokes = RandomLinePicker("jokes.txt")
        self.pickups = RandomLinePicker("pickuplines.txt")
        self.limiter = MessageLimiter()
        self.emotes = load_emotes()
        self.state = self.load_state()
        self.english = enchant.Dict("en_US")
        self.load_words()
        self.active = True
        self.command_thread = Thread(target=self.handle_commandline_input)
        self.command_thread.daemon = True
        self.command_thread.start()
        for server in self.channel_servers:
            handler = IrcClient(server, self.handle_message, self.handle_connect, self.can_send_type)
            self.channel_servers[server]['client'] = handler
            self.irc_handlers.append(handler)

    def can_send_type(self, msg_type: MessageType):
        return convert(self.state.get(msg_type.name, "True"))

    def save_state(self):
        loadToText(self.state, "global_state.txt")

    @staticmethod
    def load_state():
        return loadToDictionary("global_state.txt")

    def load_words(self):
        self.english.add("pov")
        self.english.add("ludwig,")

    def start(self):
        for handler in self.irc_handlers:
            handler.start()

    def join(self):
        for handler in self.irc_handlers:
            handler.asynloop_thread.join()

    def stop_all(self):
        for handler in self.irc_handlers:
            handler.stop()

    def check_error(self, irc_message):
        """Check for a login error notification and terminate if found"""
        if re.search(r":tmi.twitch.tv NOTICE \* :Error logging i.*", irc_message):
            self.logger.critical(
                "Error logging in to twitch irc, check your oauth and username are set correctly in config.txt!")
            self.stop_all()
            return True

    def check_join(self, irc_message):
        """Watch for successful channel join messages"""
        match = re.search(r':{0}!{0}@{0}\.tmi\.twitch\.tv JOIN #(.*)'.format(self.user), irc_message)
        if match:
            if match.group(1) in self.channels:
                self.logger.info("Joined channel {0} successfully".format(match.group(1)))
                return True

    def check_part(self, irc_message):
        """Watch for successful channel join messages"""
        match = re.search(r':{0}!{0}@{0}\.tmi\.twitch\.tv PART #(.*)'.format(self.user), irc_message)
        if match:
            self.logger.info("Left channel {0} successfully".format(match.group(1)))
            return True

    def check_usernotice(self, irc_message):
        """Parse out new twitch subscriber messages and then call... python subscribers"""
        if irc_message[0] == '@':
            arg_regx = r"([^=;]*)=([^ ;]*)"
            arg_regx = re.compile(arg_regx, re.UNICODE)
            args = dict(re.findall(arg_regx, irc_message[1:]))
            regex = (
                r'^@[^ ]* :tmi.twitch.tv'
                r' USERNOTICE #(?P<channel>[^ ]*)'  # channel
                r'((?: :)?(?P<message>.*))?')  # message
            regex = re.compile(regex, re.UNICODE)
            match = re.search(regex, irc_message)
            if match:
                args['channel'] = match.group(1)
                args['message'] = match.group(2)
                self.send_pog(args)
                return True

    def send_pog(self, args):
        username = args["login"]
        tipe = args["msg-id"]
        if is_word(tipe, ["sub", "resub"]):
            amount_of_months = args["msg-param-cumulative-months"]
            type_sub = subscriber_type(amount_of_months)
            message = Message("@" + username + " POGGIES " + type_sub + "!", MessageType.SPECIAL)
            self.send_message(args["channel"], message)
        elif tipe == "subgift":
            amount_of_gifts = args["msg-param-sender-count"]
            if not amount_of_gifts == "0":
                message = Message("@" + username + " POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                                  MessageType.SPECIAL)
                self.send_message(args["channel"], message)
        elif tipe == "submysterygift":
            amount_of_gifts = args["msg-param-sender-count"]
            message = Message("@" + username + " POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SPECIAL)
            self.send_message(args["channel"], message)
        elif tipe == "anonsubgift":
            message = Message("POGGIES", MessageType.SPECIAL)
            self.send_message(args["channel"], message)
        else:
            return

    def check_ping(self, irc_message, client):
        """Respond to ping messages or twitch boots us off"""
        if re.search(r"PING :tmi\.twitch\.tv", irc_message):
            self.logger.info("Responding to a ping from twitch... pong!")
            client.send_message("PING :pong\r\n")
            return True

    def check_message(self, irc_message):
        """Watch for chat messages and notifiy subsribers"""
        if irc_message[0] == "@":
            arg_regx = r"([^=;]*)=([^ ;]*)"
            arg_regx = re.compile(arg_regx, re.UNICODE)
            args = dict(re.findall(arg_regx, irc_message[1:]))
            regex = (r'^@[^ ]* :([^!]*)![^!]*@[^.]*.tmi.twitch.tv'  # username
                     r' PRIVMSG #([^ ]*)'  # channel
                     r' :(.*)')  # message
            regex = re.compile(regex, re.UNICODE)
            match = re.search(regex, irc_message)
            if match:
                args['username'] = match.group(1)
                args['channel'] = match.group(2)
                args['message'] = match.group(3)
                self.logger.debug(args["message"])
                if args['username'] == "lonewulfx3":
                    if self.time_out(args):
                        return True
                if args['username'] != "lonewulfx6":
                    self.validate_emotes(args)
                    self.bye(args)
                    self.give_fact(args)
                    self.eight_ball(args)
                    self.ping_if_asked(args)
                    self.reply_if_yo(args)
                    self.gn(args)
                    self.schleem(args)
                    self.spam(args)
                    self.suicune(args)
                    self.weird_jokes(args)
                    self.dict(args)
                    self.joke(args)
                    self.pickup(args)
                    self.aniki(args)
                    self.lacking(args)
                    self.respond(args)
                    self.iamhere(args)
                return True

    def iamhere(self, args):
        msg = args["message"].lower()
        if contains_all(msg, ["who", "is", "here"]):
            message = Message("I am here peepoPog", MessageType.SPECIAL)
            self.send_message(args["channel"], message)

    def respond(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["@lonewulfx6", "lonewulfx6"]):
            message = Message("@" + args["username"] +
                              ", the fact that you've pinged me probably means you've been caught lacking. "
                              "This bot was made to alert you when you've made"
                              " a mistake in emotes spelling/capitalisation. "
                              "Try to be better next time FeelsOkayMan ."
                              , MessageType.SPAM)
            self.send_message(args["channel"], message)

    def lacking(self, args):
        msg = args["message"].lower()
        if msg == "!lacking":
            amount = self.state.get("lacking", "0")
            message = Message("@" + args["username"] + ", " + amount + " people have been caught lacking PepeLaugh",
                              MessageType.SPECIAL)
            self.send_message(args["channel"], message)

    def aniki(self, args):
        msg = args["message"].lower()
        if msg == "!aniki":
            message = Message("Sleep tight PepeHands", MessageType.COMMAND)
            self.send_message(args["channel"], message)

    def pickup(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["!pickup", "!pickupline", "!pickups", "!pickuplines"]):
            message = Message("@" + args["username"] + ", " + self.pickups.get_line(), MessageType.COMMAND)
            self.send_message(args["channel"], message)

    def joke(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["!joke", "!jokes", "give me a joke"]):
            message = Message("@" + args["username"] + ", " + self.jokes.get_line(), MessageType.COMMAND)
            self.send_message(args["channel"], message)

    def dict(self, args):
        msg = args["message"].lower() + " "
        match = re.match(r"!dict\b(.*) ", msg)
        if match:
            word = match.group(1)
            if self.english.check(word):
                try:
                    definition = define(word)
                    message = Message("@" + args["username"] + ", " + definition, MessageType.COMMAND)
                    self.send_message(args["channel"], message)
                except Exception:
                    message = Message("@" + args["username"] + " couldn't look up the definition of " + word,
                                      MessageType.COMMAND)
                    self.send_message(args["channel"], message)
            else:
                message = Message("@" + args["username"] + ", " + word + " is not an english word.",
                                  MessageType.COMMAND)
                self.send_message(args["channel"], message)

    def weird_jokes(self, args):
        msg = args["message"].lower()
        if contains_all(msg, ["slime", "piss"]) \
                or contains_all(msg, ["slime", "pee"]) \
                or contains_all(msg, ["bus", "lud"]) \
                or contains_all(msg, ["bus", "hit"]):
            message = Message("@" + args["username"] + ", FeelsWeirdMan", MessageType.SPAM)
            self.send_message(args["channel"], message)

    def suicune(self, args):
        msg = args["message"].lower()
        if "!suicune" == msg:
            if self.limiter.can_send("suicune", 5, True):
                message = Message("bitch", MessageType.COMMAND)
                self.send_message(args["channel"], message)

    def spam(self, args):
        msg = args["message"].lower()
        if "!spam" == msg:
            if self.limiter.can_send("spam", 5, True):
                message = Message("not cool peepoWTF", MessageType.COMMAND)
                self.send_message(args["channel"], message)

    def validate_emotes(self, args):
        msg = args["message"]
        words = msg.split()
        emotes = self.emotes["all_emotes"]
        wrong_emotes = []
        for word in words:
            lowered_word = word.lower()
            if lowered_word in self.emotes:
                correct_emote = self.emotes.get(lowered_word)
                if word != correct_emote:
                    wrong_emotes.append(word)
            else:
                if not validate_emote(word, emotes):
                    if not self.english.check(word):
                        wrong_emotes.append(word)
        if len(wrong_emotes) != 0:
            amount = self.state.get("lacking", "0")
            self.state["lacking"] = str(int(amount) + 1)
            txt = " ".join(wrong_emotes)
            message = Message("@" + args["username"] + ", " + txt + " PepeLaugh", MessageType.SPAM)
            self.send_message(args["channel"], message)

    def schleem(self, args):
        msg = args["message"].lower()
        if "!schleem" == msg:
            if self.limiter.can_send("schleem", 10):
                message = Message("Get outta town", MessageType.COMMAND)
                self.send_message(args["channel"], message)

    def time_out(self, args):
        msg = args["message"].lower()
        if "time out" in msg:
            message = Message("Gift me PepeLaugh", MessageType.SPECIAL)
            self.send_message(args["channel"], message)

    def bye(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["cya", "goodbye", "bye", "pppoof"]):
            if self.limiter.can_send("bye", 60, True):
                message = Message("@" + args["username"]
                                  + ", " + self.byes.get_line()
                                  + " " + self.friends.get_line() + " peepoHug"
                                  , MessageType.HELPFUL)
                self.send_message(args["channel"], message)

    def gn(self, args):
        msg = args["message"].lower()
        if contains_word(msg, [" gn ", "good night", "goodnight", "to sleep", "bedtime", "to bed"]):
            if self.limiter.can_send("bye", 60, True):
                message = Message("@" + args["username"] + ", " + "gn ppPoof , sleep tight!", MessageType.HELPFUL)
                self.send_message(args["channel"], message)

    def ping_if_asked(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["ping me", "give me attention"]):
            message = Message("@" + args["username"] + " " + self.greeting_gen.get_greeting(), MessageType.SPECIAL)
            self.send_message(args["channel"], message)

    def give_fact(self, args):
        msg = args["message"].lower()
        if contains_word(msg, ["!fact", "!facts", "give me a fact"]):
            message = Message("@" + args["username"] + ", did you know that " + self.facts.get_line() + "?",
                              MessageType.COMMAND)
            self.send_message(args["channel"], message)

    def reply_if_yo(self, args):
        msg = args["message"].lower()
        if len(msg) > 2 and "yo" in msg and count_os(msg) > 2:
            self.logger.info("Message contained yo, sending Ping")
            message = Message("@" + args["username"] + ", " + self.greeting_gen.get_greeting() + " peepoHappy",
                              MessageType.SPECIAL)
            self.send_message(args["channel"], message)
            return True
        return False

    def eight_ball(self, args):
        msg = args["message"].lower()
        if "!8ball" in msg or "!eightball" in msg:
            message = Message("@" + args["username"] + " " + self.eightball.get_prophecy(), MessageType.COMMAND)
            self.send_message(args["channel"], message)
            return True

    def handle_connect(self, client):
        self.logger.info('Connected..authenticating as {0}'.format(self.user))
        client.send_message(Message('Pass ' + self.oauth + '\r\n', MessageType.FUNCTIONAL))
        client.send_message(Message('NICK ' + self.user + '\r\n'.lower(), MessageType.FUNCTIONAL))
        client.send_message(Message('CAP REQ :twitch.tv/tags\r\n', MessageType.FUNCTIONAL))
        client.send_message(Message('CAP REQ :twitch.tv/membership\r\n', MessageType.FUNCTIONAL))
        client.send_message(Message('CAP REQ :twitch.tv/commands\r\n', MessageType.FUNCTIONAL))

        for server in self.channel_servers:
            if server == client.serverstring:
                self.logger.info('Joining channels {0}'.format(self.channel_servers[server]))
                for chan in self.channel_servers[server]['channel_set']:
                    client.send_message(Message('JOIN ' + '#' + chan.lower() + '\r\n', MessageType.FUNCTIONAL))

    def join_twitch_channel(self, channel: str):
        self.logger.info('Joining channel {0}'.format(channel))
        channels = self.channel_servers.get('irc.chat.twitch.tv:6667').get("channel_set")
        channels.append(channel)
        self.channel_servers['irc.chat.twitch.tv:6667']['channel_set'] = channels
        self.channels = channels
        client = self.channel_servers["irc.chat.twitch.tv:6667"]["client"]
        client.send_message(Message("JOIN #" + channel.lower() + "\r\n", MessageType.FUNCTIONAL))

    def leave_twitch_channel(self, channel: str):
        self.logger.info('Leaving channel {0}'.format(channel))
        client = self.channel_servers["irc.chat.twitch.tv:6667"]["client"]
        client.send_message(Message("PART #" + channel.lower() + "\r\n", MessageType.FUNCTIONAL))
        channels = self.channel_servers.get('irc.chat.twitch.tv:6667').get("channel_set")
        updated_channels = [chan for chan in channels if chan != channel]
        self.channel_servers['irc.chat.twitch.tv:6667']['channel_set'] = updated_channels
        self.channels = updated_channels

    def handle_message(self, irc_message, client):
        """Handle incoming IRC messages"""
        self.logger.debug(irc_message)
        if self.check_message(irc_message):
            return
        elif self.check_join(irc_message):
            return
        elif self.check_part(irc_message):
            return
        elif self.check_usernotice(irc_message):
            return
        elif self.check_ping(irc_message, client):
            return
        elif self.check_error(irc_message):
            return

    def send_message(self, channel: str, message: Message):
        for server in self.channel_servers:
            if channel in self.channel_servers[server]['channel_set']:
                client = self.channel_servers[server]['client']
                client.send_message(Message(u'PRIVMSG #{0} :{1}\n'.format(channel, message.content), message.type))
                break

    def handle_commandline_input(self):
        while self.active:
            ans = input().lower()
            if ans == "save":
                self.save_state()
            elif ans == "stop":
                self.active = False
                self.save_state()
                self.stop_all()
            elif ans == "join":
                print("Which channel?")
                channel = input()
                self.join_twitch_channel(channel)
            elif ans == "leave":
                print("Which channel?")
                channel = input()
                if channel not in self.channels:
                    print("Not following {0}".format(channel))
                else:
                    self.leave_twitch_channel(channel)
            elif ans == "toggle":
                client = self.channel_servers.get("irc.chat.twitch.tv:6667").get("client")
                sendable = not client.allowed
                client.allowed = sendable
            elif ans == "toggle spam":
                self.state[MessageType.SPAM.name] = str(not convert(self.state.get(MessageType.SPAM.name, "True")))
            elif ans == "toggle command":
                self.state[MessageType.COMMAND.name] = str(
                    not convert(self.state.get(MessageType.COMMAND.name, "True")))
            elif ans == "toggle helpful":
                self.state[MessageType.HELPFUL.name] = str(
                    not convert(self.state.get(MessageType.HELPFUL.name, "True")))
            elif ans == "toggle special":
                self.state[MessageType.SPECIAL.name] = str(
                    not convert(self.state.get(MessageType.SPECIAL.name, "True")))
            else:
                print("save\nstop\ntoggle\ntoggle (type)")


MAX_SEND_RATE = 20
SEND_RATE_WITHIN_SECONDS = 30


class IrcClient(asynchat.async_chat, object):

    def __init__(self, server, message_callback, connect_callback, allowed_callback):
        self.logger = logging.getLogger(name="tmi_client[{0}]".format(server))
        self.logger.info('TMI initializing')
        self.map = {}
        asynchat.async_chat.__init__(self, map=self.map)
        self.received_data = bytearray()
        servernport = server.split(":")
        self.serverstring = server
        self.server = servernport[0]
        self.port = int(servernport[1])
        self.set_terminator(b'\n')
        self.asynloop_thread = Thread(target=self.run)
        self.running = False
        self.allowed = False
        self.message_callback = message_callback
        self.connect_callback = connect_callback
        self.allowed_callback = allowed_callback
        self.message_queue = Queue()
        self.messages_sent = []
        self.logger.info('TMI initialized')
        return

    def send_message(self, msg: Message):
        self.message_queue.put(msg)

    def handle_connect(self):
        """Socket connected successfully"""
        self.connect_callback(self)

    def handle_error(self):
        if self.socket:
            self.close()
        raise

    def collect_incoming_data(self, data):
        """Dump recieved data into a buffer"""
        self.received_data += data

    def found_terminator(self):
        """Processes each line of text received from the IRC server."""
        txt = self.received_data.rstrip(b'\r')  # accept RFC-compliant and non-RFC-compliant lines.
        del self.received_data[:]
        self.message_callback(txt.decode("utf-8"), self)

    def start(self):
        """Connect start message watching thread"""
        if not self.asynloop_thread.is_alive():
            self.running = True
            self.allowed = True
            self.asynloop_thread = Thread(target=self.run)
            self.asynloop_thread.daemon = True
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connect((self.server, self.port))
            self.asynloop_thread.start()

            self.send_thread = Thread(target=self.send_loop)
            self.send_thread.daemon = True
            self.send_thread.start()

        else:
            self.logger.critical("Already running can't run twice")

    def stop(self):
        """Terminate the message watching thread by killing the socket"""
        self.running = False
        if self.asynloop_thread.is_alive():
            if self.socket:
                self.close()
            try:
                self.asynloop_thread.join()
                self.send_thread.join()
            except RuntimeError as e:
                if str(e) == "cannot join current thread":
                    # this is thrown when joining the current thread and is ok.. for now"
                    pass
                else:
                    raise e

    def send_loop(self):
        while self.running:
            time.sleep(random.randint(1, 2))
            if len(self.messages_sent) < MAX_SEND_RATE:
                if not self.message_queue.empty():
                    to_send = self.message_queue.get()
                    self.logger.info("Sending")
                    self.logger.info(str(to_send))
                    if self.allowed and self.allowed_callback(to_send.type):
                        self.push(to_send.content.encode("UTF-8"))
                    self.messages_sent.append(datetime.now())
            else:
                time_cutoff = datetime.now() - timedelta(seconds=SEND_RATE_WITHIN_SECONDS)
                self.messages_sent = [dt for dt in self.messages_sent if dt < time_cutoff]

    def run(self):
        """Loop!"""
        try:
            asyncore.loop(map=self.map)
        finally:
            self.running = False

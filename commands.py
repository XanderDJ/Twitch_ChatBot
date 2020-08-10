"""
    Commands in this file will be automatically used by chatbot for commands. Any time a message appears it will run through all the commands available

    @command = this will add the method to the commands that are called when a PRIVMSG appears
    @admin = This will call the command only when the admin of the bot (bot defined in ChatBot.py or credentials.py) types the command in chat
    @returns = This is for commands where other commands shouldn't run
    @save = called in save method every 10 minutes.
    @notice = This will call the command when an USERNOTICE is send in chat.


    LINES = contains all RandomLinePickers used in commands. These are stored in twitchchat.chat.TwitchChat.line_pickers.
"""
import os

from utility import *
import functools
import re
import urllib3
import enchant
import time
import datetime
import pymongo
import json
from threading import Lock

# THIS IS TO AVOID CYCLICAL IMPORTS BUT STILL ALLOWS TYPE CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitchchat.chat import TwitchChat

# Imports of stuff I don't want on github directly
from pings import pings

# LOADING STUFF

ADMIN = {}
COMMAND = {}
NOTICE = {}
RETURNS = {}
SAVE = {}
REPEAT = {}
REPEAT_SETUP = {}
line_pickers = {
    "greetings": RandomLinePicker("texts/hello.txt"),
    "8ball": RandomLinePicker("texts/8ball.txt"),
    "facts": RandomLinePicker("texts/facts.txt"),
    "friends": RandomLinePicker("texts/friend.txt"),
    "byes": RandomLinePicker("texts/goodbyes.txt"),
    "jokes": RandomLinePicker("texts/jokes.txt"),
    "pickups": RandomLinePicker("texts/pickuplines.txt"),
    "quotes": RandomLinePicker("texts/quotes.txt"),
    "lilb": RandomLinePicker("texts/lilb.txt")
}

lurkers = dict()
previous_lurker_ts = time.time() - 600
ignore_list = LockedData(f.load("texts/ignore.txt", set()))
alts = LockedData(f.load("texts/alts.txt", dict()))
colors = LockedData(f.load("texts/colors_users.txt", dict()))


def load_emotes():
    fh = open("texts/emotes.txt", "r")
    emotes = dict()
    emotes["all_emotes"] = []
    for emote in fh:
        emote = emote.rstrip()
        emotes["all_emotes"] += [emote]
        emotes[emote.lower()] = emote
    fh.close()
    return emotes


db = LockedData({"emotes": dict(), "mentions": []})
emote_dict = load_emotes()
blacklisted = f.load("texts/blacklisted.txt", [])


def reload():
    global emote_dict, blacklisted
    emote_dict = load_emotes()
    blacklisted = f.load("texts/blacklisted.txt", [])


# DECORATORS
def admin(func):
    ADMIN[func.__name__] = func
    return func


def command(func):
    COMMAND[func.__name__] = func
    return func


def notice(func):
    NOTICE[func.__name__] = func
    return func


def returns(func):
    RETURNS[func.__name__] = func
    return func


def save(func):
    SAVE[func.__name__] = func
    return func


def repeat(seconds):
    def repeat_inner(func):
        REPEAT[func.__name__] = (func, seconds)
        return func

    return repeat_inner


def repeat_setup(func_name):
    if func_name not in REPEAT:
        return

    def setup_inner(func):
        REPEAT_SETUP[func_name] = func
        return func

    return setup_inner


def unwrap_command_args(func):
    """
        Decorator for commands that automatically unwraps some args by calling them on the dictionary provided
    :param func: the function wrapped, takes 5 arguments
    :return: wrapped function that takes two inputs, args (dict) and bot (TwitchChat class)
    """

    @functools.wraps(func)
    def wrapper(bot, args: dict, send=True) -> bool:
        msg = args.get("message")
        username = args.get("username")
        channel = args.get("channel")
        return func(bot, args, msg, username, channel, send)

    return wrapper


# SAVES

client = pymongo.MongoClient("mongodb://localhost:27017/")


@save
def save_emotes():
    global db, client

    def save_emotes_inner(temp_db, kwargs):
        for channel, collections in temp_db.get("emotes").items():
            db = client[channel]
            global_coll = db["global"]
            global_coll.insert_one({"count": collections.get("count"), "timestamp": datetime.datetime.utcnow()})
            for emote, wrong_emotes in collections.items():
                col = db[emote]
                wrong_emotes_to_insert = []
                if emote != "count":
                    for (misspell, activity), count in wrong_emotes.items():
                        item = {"count": count, "spelling": misspell, "activity": activity,
                                "timestamp": datetime.datetime.utcnow()}
                        wrong_emotes_to_insert.append(item)
                    col.insert_many(wrong_emotes_to_insert)
        temp_db["emotes"] = dict()

    db.access(save_emotes_inner)
    # clear buffer for any emotes caught during saving
    db.buffered_write(update_emotes)


@save
def save_mentions():
    global db, client

    def save_mentions_inner(mongo_db, kwargs):
        if "client" in kwargs:
            client = kwargs.get("client")
            db = client["twitch"]
            col = db["twitch"]
            if len(mongo_db["mentions"]) != 0:
                col.insert_many(mongo_db.get("mentions"))
            mongo_db["mentions"] = []

    db.access(save_mentions_inner, client=client)
    # clear buffer that might have build up during save
    db.buffered_write(append_to_list_in_dict)


@save
def save_ignore_list():
    global ignore_list
    ignore_list.access(lambda lst, kwargs: f.save(lst, "texts/ignore.txt"))
    # clear buffer
    ignore_list.buffered_write(add_to_container)
    ignore_list.buffered_write(delete_from_list)


@save
def save_alts():
    global alts
    alts.access(lambda alts_set, kwargs: f.save(alts_set, "texts/alts.txt"))
    # clear buffer
    alts.buffered_write(write_to_dict)


@save
def save_colors():
    global colors
    colors.access(lambda colors_dict, kwargs: f.save(colors_dict, "texts/colors_users.txt"))
    # clear buffer
    colors.buffered_write(write_to_dict)


# ADMIN

@admin
@unwrap_command_args
def toggle(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r"!toggle (\w+)", msg)
    if match:
        ans = match.group(1)
        if ans == "on":
            bot.toggle_channel(channel, ToggleType.ON)
            message = Message("Hey guys PrideLion !", MessageType.CHAT, channel)
            bot.send_message(message)
        elif ans == "off":
            bot.toggle_channel(channel, ToggleType.OFF)
            message = Message("Bye guys PrideLion !", MessageType.CHAT, channel)
            bot.send_message(message)
        elif ans == "spam":
            bot.toggle_channel(channel, ToggleType.SPAM)
        elif ans == "command":
            bot.toggle_channel(channel, ToggleType.COMMAND)
        elif ans == "bld":
            bot.toggle_channel(channel, ToggleType.BLACKLISTED)
        elif ans == "helpful":
            bot.toggle_channel(channel, ToggleType.HELPFUL)
        elif ans == "special":
            bot.toggle_channel(channel, ToggleType.SPECIAL)
        elif ans == "sub":
            bot.toggle_channel(channel, ToggleType.SUBSCRIBER)
        else:
            return


@admin
@unwrap_command_args
def join(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r"!join (\w+)", msg)
    if match:
        channel_to_join = match.group(1)
        bot.join_twitch_channel(channel_to_join)


@admin
@unwrap_command_args
def part(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r"!leave (\w+)", msg)
    if match:
        channel_to_leave = match.group(1)
        if channel_to_leave != "all":
            bot.leave_twitch_channel(channel_to_leave)
        else:
            for chan in bot.channels:
                if chan != channel:
                    bot.leave_twitch_channel(chan)


@admin
@unwrap_command_args
def ping(bot: 'TwitchChat', args, msg, username, channel, send):
    if msg == "!ping":
        message = Message("Pong, I'm alive!", MessageType.FUNCTIONAL, channel)
        bot.send_message(message)


@admin
@unwrap_command_args
def add_alt(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    global alts
    match = re.match(r'!(addalt|namechange)\s(\w+)\s(\w+)', msg.lower())
    if match:
        alt = match.group(2)
        main = match.group(3)
        alts.buffered_write(write_to_dict, key=alt, val=main)
        message = Message(
            "@" + username + ", " + alt + " is " + main + " PepoG",
            MessageType.CHAT,
            channel
        )
        bot.send_message(message)


@admin
@unwrap_command_args
def delete_alt(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    global alts
    match = re.match(r'!delalt\s(\w+)', msg.lower())
    if match:
        alt = match.group(1)
        if alts.access(contains, elem=alt):
            alts.access(delete_from_dict, key=alt)
            message = Message(
                "@" + username + ", pffft " + alt + " never heard of them PepeLaugh",
                MessageType.CHAT,
                channel
            )
            bot.send_message(message)


# COMMANDS

@command
@unwrap_command_args
def update_mentions(bot: 'TwitchChat', args, msg, username, channel, send):
    global db
    if contains_word(msg.lower(), pings):
        doc = {
            "user": username,
            "message": msg,
            "channel": channel,
            "timestamp": datetime.datetime.utcnow()
        }
        db.buffered_write(append_to_list_in_dict, key="mentions", val=doc)


http = urllib3.PoolManager()


def english_dictionary():
    english_dict = enchant.Dict("en_US")
    english_dict.add("pov")
    english_dict.add("POV")
    english_dict.add("pogo")
    english_dict.add("poro")
    english_dict.add("png")
    english_dict.add("PNG")
    english_dict.add("ppl")
    english_dict.add("nvm")
    return english_dict


dictionary = english_dictionary()


@command
@unwrap_command_args
def dct(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower() + " "
    match = re.match(r"!dict\b(.*) ", msg)
    if match:
        word = match.group(1)
        if dictionary.check(word):
            try:
                definition = define(word)
                message = Message("@" + username + ", " + definition, MessageType.COMMAND, channel)

                bot.send_message(message)
            except Exception:
                message = Message("@" + username + " couldn't look up the definition of " + word,
                                  MessageType.COMMAND, channel)

                bot.send_message(message)
        else:
            message = Message("@" + username + ", " + word + " is not an english word.",
                              MessageType.COMMAND, channel)

            bot.send_message(message)


def define(word):
    html = http.request("GET", "http://dictionary.reference.com/browse/" + word + "?s=t").data.decode("UTF-8")
    items = re.findall('<meta name=\"description\" content=\"(.*) See more.\">', html, re.S)
    defs = [re.sub('<.*?>', '', x).strip() for x in items]
    return defs[0]


def change_if_blacklisted(username, msg, channel):
    if username.lower() in blacklisted:
        return Message("@" + username + " ludwigSpectrum " * random.randint(1, 3), MessageType.BLACKLISTED, channel)
    return msg


@command
@unwrap_command_args
def time_out(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    username = username
    if "time out" in msg and username == bot.admin:
        message = Message("Gift me PepeLaugh", MessageType.SPECIAL, channel)
        bot.send_message(message)
    elif "time out" in msg:
        message = Message("@" + username + " What's the password", MessageType.SPAM, channel)

        bot.send_message(message)


@command
@unwrap_command_args
def dance(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg
    if contains_word(msg, [" ludwigGun "]) and bot.limiter.can_send(channel, "dance", 25, True):
        message = Message("pepeD " * random.randint(1, 9), MessageType.SPAM, channel)

        bot.send_message(message)


@command
@unwrap_command_args
def iamhere(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, [" who ", " is ", " here "]):
        message = Message("I am here peepoPog", MessageType.SPECIAL, channel)

        bot.send_message(message)


@command
@unwrap_command_args
def respond(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["@" + bot.user, bot.user]):
        message = Message("@" + username +
                          ", Beep Boop MrDestructoid"
                          , MessageType.SPAM, channel)

        bot.send_message(message)


@command
@unwrap_command_args
def weird_jokes(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, [" slime ", " piss "]) \
            or contains_all(msg, [" slime ", " pee "]):
        message = Message("@" + username + ", FeelsWeirdMan", MessageType.SPAM, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def validate_emotes(bot: 'TwitchChat', args, msg, username, channel, send):
    if username == bot.user:
        return
    global emote_dict, db
    channel = channel
    words = msg.split()
    emotes = emote_dict["all_emotes"]
    wrong_emotes = []
    status = bot.twitch_status.get_status(channel)
    for word in words:
        if len(word) > 2 and word[0] == "\"" and word[-1] == "\"":
            continue
        word = cleanup(word)
        lowered_word = word.lower()
        if lowered_word in emote_dict:
            correct_emote = emote_dict.get(lowered_word)
            if word != correct_emote and not dictionary.check(word):
                db.buffered_write(update_emotes, chan=channel, we=word, ce=correct_emote, ac=status.get("activity"))
                wrong_emotes.append(word)
        else:
            val = validate_emote(word, emotes)
            if not val.boolean:
                if not dictionary.check(word):
                    db.buffered_write(update_emotes, chan=channel, we=word, ce=val.correct, ac=status.get("activity"))
                    wrong_emotes.append(word)
    if len(wrong_emotes) != 0:
        amount = bot.state.get(channel).get("lacking", "0")
        bot.state[channel]["lacking"] = str(int(amount) + len(wrong_emotes))
        if send:
            txt = " ".join(wrong_emotes)
            message = Message("@" + username + ", " + txt + " PepeLaugh", MessageType.SPAM, channel)
            bot.send_message(message)


def validate_emote(emote, emotes):
    for correct_emote in emotes:
        dist = hammington(emote, correct_emote)
        if dist == 1 or is_anagram(correct_emote, emote):
            return Validation(False, correct_emote)
    return Validation(True, emote)


def update_emotes(db, kwargs) -> None:
    if "chan" in kwargs and "we" in kwargs and "ce" in kwargs and "ac" in kwargs:
        channel, wrong_emote, correct_emote, activity = kwargs.get("chan"), kwargs.get("we"), \
                                                        kwargs.get("ce"), kwargs.get("ac")
        db["emotes"][channel] = db.get("emotes").get(channel, dict())
        channel_dict = db.get("emotes").get(channel)
        channel_dict[correct_emote] = channel_dict.get(correct_emote, dict())
        emote_dict = channel_dict.get(correct_emote)
        count = emote_dict.get((wrong_emote, activity), 0)
        emote_dict[(wrong_emote, activity)] = count + 1
        channel_dict["count"] = channel_dict.get("count", 0) + 1


@command
@unwrap_command_args
def card_pogoff(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    msg = cleanup(msg)
    if (username.lower() in
        [
            "cardinal256",
            "lil_schleem"
        ]
    ) and \
            (
                    contains_all(msg.rstrip().lower(), ["ptidelio", "pepelaugh"])
                    or contains_all(msg.rstrip().lower(), ["ptideiio", "pepelaugh"])
                    or contains_all(msg.rstrip().lower(), ["ptideii", "omegalul"])
                    or contains_all(msg.rstrip().lower(), ["ptideli", "omegalul"])
                    or contains_all(msg.lower().rstrip(), ["wulf", "pogo"])
            ):
        message = Message("@" + username + ", PogOff you're not funny " + "PogOff " * random.randint(1, 6),
                          MessageType.SPAM, channel)
        bot.send_message(message)


# NOTICE

@notice
def send_pog(bot: 'TwitchChat', args):
    username = args["login"]
    tipe = args["msg-id"]
    channel = args["channel"]
    if username is None:
        return
    elif is_word(tipe, ["sub", "resub"]):
        amount_of_months = args.get("msg-param-cumulative-months", None)
        type_sub = subscriber_type(amount_of_months)
        message = Message("POGGIES " + type_sub + "!", MessageType.SUBSCRIBER, channel)
        bot.send_message(message)
    elif tipe == "subgift":
        amount_of_gifts = args.get("msg-param-sender-count")
        if amount_of_gifts != "0" and amount_of_gifts is not None:
            message = Message("POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SUBSCRIBER, channel)
            bot.send_message(message)
    elif tipe == "submysterygift":
        amount_of_gifts = args.get("msg-param-sender-count", "0")
        if amount_of_gifts != "0" and amount_of_gifts is not None:
            message = Message("POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SUBSCRIBER, channel)
            bot.send_message(message)
    elif tipe == "anonsubgift":
        message = Message("POGGIES", MessageType.SUBSCRIBER, channel)
        bot.send_message(message)
    else:
        return


def subscriber_type(months):
    if months is None:
        return ""
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


# RETURNS

@returns
@unwrap_command_args
def scrape_color(bot: 'TwitchChat', args, msg, username, channel, send):
    color = args['color']
    color = color if len(color) != 0 else "#808080"
    if not colors.access(contains, key=username):
        colors.buffered_write(write_to_dict, key=username, val=color)
    return False


@returns
@unwrap_command_args
def add_to_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    msg = msg.lower()
    if msg == "!ignore me":
        if not ignore_list.access(contains, elem=username):
            ignore_list.buffered_write(add_to_container, elem=username)
            message = Message("@" + username + ", from now on you will be ignored PrideLion", MessageType.COMMAND,
                              channel)
            bot.send_message(message)
        else:
            message = Message("@" + username + ", You're already ignored 4Head", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True
    return False


@returns
@unwrap_command_args
def remove_from_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    msg = msg.lower()
    if msg == "!unignore me":
        ignore_list.buffered_write(delete_from_set, elem=username)
        message = Message("@" + username + ", welcome back PrideLion !", MessageType.COMMAND, channel)
        bot.send_message(message)
        return True
    return False


@returns
@unwrap_command_args
def ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    if ignore_list.access(contains, elem=username):
        validate_emotes(bot, args, False)
        return True
    return False


@returns
@unwrap_command_args
def tj(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!tj":
        if bot.limiter.can_send(channel, "tj", 20):
            message = Message("fuck texas ludwigSpectrum (uni)", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def whois(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    global alts
    match = re.match(r'!whois\s(\w+)', msg.lower())
    if match:
        alt = match.group(1)
        while alts.access(contains, elem=alt):
            alt = alts.access(get_val, key=alt)
        if alt == match.group(1):
            message = Message(
                "@" + username + ", " + alt + " is " + alt + " PrideLion",
                MessageType.COMMAND,
                channel
            )
            bot.send_message(message)
        else:
            message = Message(
                "@" + username + ", " + match.group(1) + " is " + alt + " PrideLion",
                MessageType.COMMAND,
                channel
            )
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def correct(bot: 'TwitchChat', args, msg, username, channel, send):
    global emote_dict
    match = re.match(r"!correct (\w+)", msg)
    if match:
        emote = match.group(1)
        correct_emote = emote_dict.get(emote.lower(), None)
        if correct_emote != "WeirdChamp":
            if correct_emote is None:
                message = Message(
                    "@" + username + ", that emote wasn't in my emote database. "
                                     "So I can't tell you the correct way to spell it.", MessageType.COMMAND, channel)
                bot.send_message(message)
                return True
            if emote == correct_emote:
                message = Message("@" + username + ", you wrote " + emote + " correctly! Good job FeelsWowMan",
                                  MessageType.COMMAND, channel)
                bot.send_message(message)
                return True
            else:
                message = Message(
                    "@" + username + ", you wrote " + emote + " incorrectly FeelsBadMan . "
                                                              "The correct way of spelling it is " + correct_emote,
                    MessageType.COMMAND, channel)
                bot.send_message(message)
                return True
        else:
            message = Message("@" + username + " can't fool me PepeLaugh", MessageType.COMMAND, channel)
            bot.send_message(message)
            return True
    return False


@returns
@unwrap_command_args
def tyke(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if msg == "!tyke":
        if bot.limiter.can_send(channel, "tyke", 300, True):
            for i in range(3):
                parity = i % 2
                txt = "blobDance RareChar blobDance RareChar blobDance " \
                    if parity == 0 else "RareChar blobDance RareChar blobDance RareChar "
                message = Message(txt, MessageType.SPAM, channel)
                bot.send_message(message)
                time.sleep(2)
        return True


@returns
@unwrap_command_args
def lurk(bot: 'TwitchChat', args, msg, username, channel, send):
    global lurkers
    global previous_lurker_ts
    msg = msg.lower()
    if "!lurker" in msg:
        if len(lurkers.get(channel, [])) == 0 or time.time() - previous_lurker_ts > 600:
            js = http.request("GET", "https://tmi.twitch.tv/group/user/" + channel + "/chatters").data.decode("UTF-8")
            chatters = json.loads(js)
            lurkers[channel] = chatters.get("chatters").get("viewers")
            lurkers[channel] = [None] if len(lurkers.get(channel)) == 0 else lurkers.get(channel)
            previous_lurker_ts = time.time()
        if bot.limiter.can_send(channel, "lurker", 1200, True):
            lurker = random.choice(lurkers.get(channel, [None]))
            txt = lurker + " is lurking in chat right now monkaW ." \
                if lurker is not None else "No lurkers in chat FeelsBadMan "
            message = Message(txt, MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def aaron(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!ap"]):
        if bot.limiter.can_send(channel, "aaron", 60, False):
            message = Message("Wizard Toad wishes you a good day =)", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def replay(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!replay"]):
        if bot.limiter.can_send(channel, "replay", 60, True):
            message = Message("Green FeelsOkayMan", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def limit(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r'!(limit|cooldown) (\w+)', msg)
    if match:
        cmd = match.group(2)
        s = bot.limiter.seconds_since_limit(channel, cmd)
        txt = "@" + username + ", " + str(s) + " seconds since command !" + cmd + " was used." \
            if s != 0 else "@" + username + ", that command wasn't used yet"
        message = Message(txt, MessageType.COMMAND, channel)
        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def seal(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!seal":
        if bot.limiter.can_send(channel, "seal", 20):
            message = Message("Such a brave bird PrideLion", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True
    return False


@returns
@unwrap_command_args
def thor(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!thor":
        if bot.limiter.can_send(channel, "thor", 20):
            message = Message("Just beat it 4Head", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def psy(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!psy":
        if bot.limiter.can_send(channel, "psy", 20):
            message = Message("@psygs daily ping or however many times people access this command PrideLion",
                              MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def lilb(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!lilb":
        if bot.limiter.can_send(channel, "lilb", 20):
            message = Message(line_pickers.get("lilb").get_line(), MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def nuggles(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!nuggles":
        if bot.limiter.can_send(channel, "nuggles", 40, True):
            message = Message(
                "Hey I’m Brett from LA and if you wanna see some sick montage parodies "
                "this is the channel to subscribe to. You got memes! You got the illuminati!"
                " Mountain Dew! Doritos! Basically everything that’s cool on the internet. "
                "So click the fuckin subscribe button and join the party, you’ll be glad you did! FeelsOkayMan ",
                MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def xray(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!xray":
        if bot.limiter.can_send(channel, "xray", 20):
            message = Message("* peepoHug intensifies *", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def deane(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!deane":
        if bot.limiter.can_send(channel, "deane", 120):
            message = Message("peepoArrive", MessageType.COMMAND, channel)
            bot.send_message(message)
            time.sleep(2)
            message = Message("hi", MessageType.COMMAND, channel)
            bot.send_message(message)
            time.sleep(2)
            message = Message("ppPoof", MessageType.COMMAND, channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def auto(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!auto":
        if bot.limiter.can_send(channel, "auto", 20):
            message = Message("peepoPog person with a cool command response", MessageType.COMMAND,
                              channel)
            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def suicune(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!suicune" == msg:
        if bot.limiter.can_send(channel, "suicune", 5, True):
            message = Message("bitch", MessageType.COMMAND, channel)

            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def spam(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!spam" == msg:
        if bot.limiter.can_send(channel, "spam", 5, True):
            message = Message("not cool peepoWTF", MessageType.COMMAND, channel)

            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def schleem(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!schleem" == msg:
        if bot.limiter.can_send(channel, "schleem", 10):
            message = Message("Get outta town", MessageType.COMMAND, channel)

            bot.send_message(message)
        return True


@returns
@unwrap_command_args
def give_fact(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!fact", "!facts", "give me a fact"]):
        message = Message("@" + username + ", did you know that " + line_pickers.get("facts").get_line(),
                          MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def eight_ball(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!8ball" in msg or "!eightball" in msg:
        message = Message("@" + username + " " + line_pickers.get("8ball").get_line(), MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def quote(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg
    username = username
    if is_word(msg, ["!inspire"]):
        message = Message("@" + username + ", " + line_pickers.get("quotes").get_line(), MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def lacking(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    channel = channel
    if msg == "!lacking":
        amount = bot.state.get(channel, {}).get("lacking", "0")
        message = Message("@" + username + ", " + amount + " people have been caught lacking PepeLaugh",
                          MessageType.SPECIAL, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def aniki(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if msg == "!aniki":
        message = Message("Sleep tight PepeHands", MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def pickup(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!pickup", "!pickupline", "!pickups", "!pickuplines"]):
        message = Message("@" + username + ", " + line_pickers.get("pickups").get_line(), MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def joke(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!joke", "!jokes", " give me a joke "]):
        message = Message("@" + username + ", " + line_pickers.get("jokes").get_line(), MessageType.COMMAND, channel)

        bot.send_message(message)
        return True


@returns
@unwrap_command_args
def pyramid(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!pyramid\s(-*\w+)?\s(.+)', msg)
    if match:
        layers = match.group(1)
        try:
            layers = int(layers)
        except ValueError:
            message = Message(
                "@" + username + ", is " + layers + " a natural number huh?! is it?! I didn't think so peepoWTF",
                MessageType.COMMAND, channel)
            bot.send_message(message)
            return True
        if layers > 3 and username != bot.admin:
            message = Message("@" + username + ", you're a greedy one ain'tcha peepoWTF", MessageType.COMMAND, channel)
            bot.send_message(message)
            return True
        elif layers <= 0:
            message = Message("@" + username + ", wtf am I supposed to do with a non positive number peepoWTF",
                              MessageType.COMMAND, channel)
            bot.send_message(message)
            return True
        else:
            pyramid_emotes = match.group(2).split()
            correct_emotes = emote_dict["all_emotes"]
            for emote in pyramid_emotes:
                if emote not in correct_emotes:
                    return False
                if emote == "WeirdChamp":
                    message = Message("@" + username + " can't fool me PepeLaugh", MessageType.COMMAND, channel)
                    bot.send_message(message)
                    return True
            if bot.limiter.can_send(channel, "pyramid", 300):
                pyramid = word_pyramid(layers, pyramid_emotes)
                for pyramid_msg in pyramid:
                    message = Message(pyramid_msg, MessageType.SPAM, channel)
                    bot.send_message(message)
                    time.sleep(1.5)
                return True
            return True
    return False


@returns
@unwrap_command_args
def color(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r'!(hex|color)\s(\w+)', msg)
    if match:
        user = match.group(2)
        if colors.access(contains, elem=user):
            color = colors.access(get_val, key=user)
            color_name = get_color_name(color, http)
            clarification = " which is " + color_name if len(color_name) != 0 else ""
            message = Message("@" + username + ", the last hex/color of " + user + " seen is " + color + clarification,
                              MessageType.COMMAND, channel)
            bot.send_message(message)
        else:
            message = Message("@" + username + ", I have never seen this person type in the chat O.o",
                              MessageType.COMMAND, channel)
            bot.send_message(message)
        return True
    return False


def get_color_name(hex_code: str, pm: urllib3.PoolManager):
    color_code = hex_code[1:]
    base = "https://www.color-hex.com/color/" + color_code.lower()
    response = pm.request("GET", base).data.decode("UTF-8")
    iteration = re.finditer(r'<title>' + hex_code.lower() + r' Color Hex (.+)</title>', response)
    try:
        first = next(iteration)
        return first.group(1)
    except StopIteration:
        return ""


# REPEATS and REPEATS_SETUP

@repeat(5)
def handle_pull_event(state: dict, bot: 'TwitchChat'):
    cm_time = os.stat("commands.py").st_mtime
    state["clm"] = state.get("clm", cm_time)
    clm_time = state.get("clm")
    if cm_time > clm_time:
        bot.logger.info("COMMANDS FILE UPDATED")
        state["clm"] = cm_time
        # Commands.py has been modified due to a git pull
        # Check if twitchchat.chat.py has been modified, if so then bot should stop and restart manually
        chm_time = os.stat("twitchchat/chat.py").st_mtime
        state["chlm"] = state.get("chlm", chm_time)
        chlm_time = state.get("chlm")
        if chm_time > chlm_time:
            # chat.py was modified so program has to shutdown
            bot.logger.info("STOPPING")
            bot.save()
            bot.stop_all()
        else:
            # chat.py wasn't modified so it's safe to reload commands.py
            bot.logger.info("RELOADING")
            bot.reload()


@repeat(30)
def check_for_title_change(state: dict, bot: 'TwitchChat'):
    channels = bot.channels
    for channel in channels:
        old_title = state.get(channel, "")
        if channel not in state["ids"]:
            user_id = get_id(http, channel)
            state["ids"][channel] = user_id
            f.save(state["ids"], "texts/streamer_ids.txt", True)
        else:
            user_id = state["ids"][channel]
        current_title = get_title(http, channel, user_id)
        if old_title != current_title:
            state[channel] = current_title
            message = Message(
                "PrideLion TITLE CHANGE PrideLion",
                MessageType.CHAT,
                channel
            )
            if old_title != "":
                bot.send_message(message)


@repeat_setup(check_for_title_change.__name__)
def check_for_title_change_setup(state: dict, bot: 'TwitchChat'):
    state["ids"] = f.load("texts/streamer_ids.txt", {})


def get_id(pool_manager, name):
    headers = {
        "Client-id": client_id,
        "Accept": "application/vnd.twitchtv.v5+json"
    }
    fields = {
        "login": name
    }
    base = "https://api.twitch.tv/kraken/users"
    response = pool_manager.request("GET", base, headers=headers, fields=fields).data.decode("UTF-8")
    data = json.loads(response)
    return data.get("users")[0].get("_id")


def get_title(pool_manager, channel, user_id):
    headers = {
        "Client-id": client_id,
        "Accept": "application/vnd.twitchtv.v5+json"
    }
    fields = {
        "stream_type": "all"
    }
    base = "https://api.twitch.tv/kraken/channels/" + user_id
    response = pool_manager.request("GET", base, headers=headers, fields=fields).data.decode("UTF-8")
    return json.loads(response).get("status")


@repeat(5)
def toggle_if_live(state, bot: 'TwitchChat'):
    for channel in bot.channels:
        live = bot.twitch_status.get_status(channel)["live"]
        state[channel] = live
        if live and live != state[channel]:
            bot.logger.info(channel + " went live toggling bot off")
            bot.toggle_channel(channel, ToggleType.OFF)


@repeat_setup(toggle_if_live.__name__)
def toggle_if_live(state, bot: 'TwitchChat'):
    for channel in bot.channels:
        state[channel] = bot.twitch_status.get_status(channel)["live"]

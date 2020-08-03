"""
    Commands in this file will be automatically used by chatbot for commands. Any time a message appears it will run through all the commands available

    @command = this will add the method to the commands that are called when a PRIVMSG appears
    @admin = This will call the command only when the admin of the bot (bot defined in ChatBot.py or credentials.py) types the command in chat
    @returns = This is for commands where other commands shouldn't run
    @save = called in save method every 10 minutes.
    @notice = This will call the command when an USERNOTICE is send in chat.


    LINES = contains all RandomLinePickers used in commands. These are stored in twitchchat.chat.TwitchChat.line_pickers.
"""
from utility import *
import functools
import re
import urllib3
import enchant
import time
import datetime
import pymongo
import json

# THIS IS TO AVOID CYCLICAL IMPORTS BUT STILL ALLOWS TYPE CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitchchat.chat import TwitchChat

# Imports of stuff I don't want on github directly
from pings import pings

# DICTS

ADMIN = {}
COMMAND = {}
NOTICE = {}
RETURNS = {}
SAVE = {}
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
previous_lurker_get = time.time() - 600
ignore_list = f.load("texts/ignore.txt", set())


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


# COMMANDS AND HELPER FUNCTIONS

client = pymongo.MongoClient("mongodb://localhost:27017/")
temp_db = {"emotes": dict(), "mentions": []}


@save
def save_emotes():
    global temp_db, client
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


@save
def save_mentions():
    global temp_db, client
    db = client["twitch"]
    col = db["twitch"]
    if len(temp_db["mentions"]) != 0:
        col.insert_many(temp_db.get("mentions"))
    temp_db["mentions"] = []


@save
def save_ignore_list():
    global ignore_list
    f.save(ignore_list, "texts/ignore.txt")


@command
@unwrap_command_args
def update_mentions(bot: 'TwitchChat', args, msg, username, channel, send):
    global temp_db
    if contains_word(msg.lower(), pings):
        doc = {
            "user": username,
            "message": msg,
            "channel": channel,
            "timestamp": datetime.datetime.utcnow()
        }
        mentions = temp_db["mentions"]
        mentions.append(doc)


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
                message = change_if_blacklisted(username, message, channel)
                bot.send_message(message)
            except Exception:
                message = Message("@" + username + " couldn't look up the definition of " + word,
                                  MessageType.COMMAND, channel)
                message = change_if_blacklisted(username, message, channel)
                bot.send_message(message)
        else:
            message = Message("@" + username + ", " + word + " is not an english word.",
                              MessageType.COMMAND, channel)
            message = change_if_blacklisted(username, message, channel)
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


@command
@unwrap_command_args
def schleem(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!schleem" == msg:
        if bot.limiter.can_send(channel, "schleem", 10):
            message = Message("Get outta town", MessageType.COMMAND, channel)
            message = change_if_blacklisted(username, message, channel)
            bot.send_message(message)


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
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def give_fact(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!fact", "!facts", "give me a fact"]):
        message = Message("@" + username + ", did you know that " + line_pickers.get("facts").get_line(),
                          MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def eight_ball(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!8ball" in msg or "!eightball" in msg:
        message = Message("@" + username + " " + line_pickers.get("8ball").get_line(), MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)
        return True


@command
@unwrap_command_args
def dance(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg
    if contains_word(msg, [" ludwigGun "]) and bot.limiter.can_send(channel, "dance", 25, True):
        message = Message("pepeD " * random.randint(1, 9), MessageType.SPAM, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def quote(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg
    username = username
    if is_word(msg, ["!inspire"]):
        message = Message("@" + username + ", " + line_pickers.get("quotes").get_line(), MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def iamhere(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, ["who", "is", "here"]):
        message = Message("I am here peepoPog", MessageType.SPECIAL, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def respond(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["@" + bot.user, bot.user]):
        message = Message("@" + username +
                          ", Beep Boop MrDestructoid"
                          , MessageType.SPAM, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def lacking(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    channel = channel
    if msg == "!lacking":
        amount = bot.state.get(channel, {}).get("lacking", "0")
        message = Message("@" + username + ", " + amount + " people have been caught lacking PepeLaugh",
                          MessageType.SPECIAL, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def aniki(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if msg == "!aniki":
        message = Message("Sleep tight PepeHands", MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def pickup(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!pickup", "!pickupline", "!pickups", "!pickuplines"]):
        message = Message("@" + username + ", " + line_pickers.get("pickups").get_line(), MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def joke(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!joke", "!jokes", " give me a joke "]):
        message = Message("@" + username + ", " + line_pickers.get("jokes").get_line(), MessageType.COMMAND, channel)
        message = change_if_blacklisted(username, message, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def weird_jokes(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, ["slime", "piss"]) \
            or contains_all(msg, ["slime", "pee"]) \
            or contains_all(msg, ["bus", "lud"]) \
            or contains_all(msg, ["bus", "hit"]):
        message = Message("@" + username + ", FeelsWeirdMan", MessageType.SPAM, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def suicune(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!suicune" == msg:
        if bot.limiter.can_send(channel, "suicune", 5, True):
            message = Message("bitch", MessageType.COMMAND, channel)
            message = change_if_blacklisted(username, message, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def spam(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if "!spam" == msg:
        if bot.limiter.can_send(channel, "spam", 5, True):
            message = Message("not cool peepoWTF", MessageType.COMMAND, channel)
            message = change_if_blacklisted(username, message, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def validate_emotes(bot: 'TwitchChat', args, msg, username, channel, send):
    global emote_dict
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
                update_emotes(channel, word, correct_emote, status.get("activity"))
                wrong_emotes.append(word)
        else:
            val = validate_emote(word, emotes)
            if not val.boolean:
                if not dictionary.check(word):
                    update_emotes(channel, word, val.correct, status.get("activity"))
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


def update_emotes(channel: str, wrong_emote: str, correct_emote: str, activity: str) -> None:
    global temp_db
    temp_db["emotes"][channel] = temp_db.get("emotes").get(channel, dict())
    channel_dict = temp_db.get("emotes").get(channel)
    channel_dict[correct_emote] = channel_dict.get(correct_emote, dict())
    emote_dict = channel_dict.get(correct_emote)
    count = emote_dict.get((wrong_emote, activity), 0)
    emote_dict[(wrong_emote, activity)] = count + 1
    channel_dict["count"] = channel_dict.get("count", 0) + 1


@command
@unwrap_command_args
def tyke(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if msg == "!tyke":
        if bot.limiter.can_send(channel, "tyke", 300, True):
            for i in range(3):
                parity = i % 2
                txt = "blobDance RareChar blobDance RareChar blobDance " if parity == 0 else "RareChar blobDance RareChar blobDance RareChar "
                message = Message(txt, MessageType.SPAM, channel)
                bot.send_message(message)


@admin
@unwrap_command_args
def toggle(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r"!toggle (\w+)", msg)
    if match:
        ans = match.group(1)
        if ans == "on":
            for tipe in MessageType:
                if tipe != MessageType.FUNCTIONAL and tipe != MessageType.CHAT:
                    bot.state[channel][tipe.name] = str(True)
            message = Message("@" + username + " bot is now toggled on.", MessageType.CHAT, channel)
            bot.send_message(message)
        elif ans == "off":
            for tipe in MessageType:
                if tipe != MessageType.FUNCTIONAL and tipe != MessageType.CHAT:
                    bot.state[channel][tipe.name] = str(False)
            message = Message("@" + username + " bot is now toggled off.", MessageType.CHAT, channel)
            bot.send_message(message)
        elif ans == "spam":
            bot.state[channel][MessageType.SPAM.name] = str(
                not convert(bot.state.get(channel).get(MessageType.SPAM.name, "True")))
        elif ans == "command":
            bot.state[channel][MessageType.COMMAND.name] = str(
                not convert(bot.state.get(channel).get(MessageType.COMMAND.name, "True")))
        elif ans == "bld":
            bot.state[channel][MessageType.BLACKLISTED.name] = str(
                not convert(bot.state.get(channel).get(MessageType.BLACKLISTED.name, "True")))
        elif ans == "helpful":
            bot.state[channel][MessageType.HELPFUL.name] = str(
                not convert(bot.state.get(channel).get(MessageType.HELPFUL.name, "True")))
        elif ans == "special":
            bot.state[channel][MessageType.SPECIAL.name] = str(
                not convert(bot.state.get(channel).get(MessageType.SPECIAL.name, "True")))
        elif ans == "sub":
            bot.state[channel][MessageType.SUBSCRIBER.name] = str(
                not convert(bot.state.get(channel).get(MessageType.SUBSCRIBER.name, "True")))
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


@command
@unwrap_command_args
def lurk(bot: 'TwitchChat', args, msg, username, channel, send):
    global lurkers
    global previous_lurker_get
    msg = msg.lower()
    if "!lurker" in msg:
        if len(lurkers.get(channel, [])) == 0 or time.time() - previous_lurker_get > 600:
            js = http.request("GET", "https://tmi.twitch.tv/group/user/" + channel + "/chatters").data.decode("UTF-8")
            chatters = json.loads(js)
            lurkers[channel] = chatters.get("chatters").get("viewers")
            lurkers[channel] = [None] if len(lurkers.get(channel)) == 0 else lurkers.get(channel)
            previous_lurker_get = time.time()
        if bot.limiter.can_send(channel, "lurker", 1200, True):
            lurker = random.choice(lurkers.get(channel, [None]))
            txt = lurker + " is lurking in chat right now monkaW ." if lurker is not None else "No lurkers in chat FeelsBadMan "
            message = Message(txt, MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def aaron(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!ap"]):
        if bot.limiter.can_send(channel, "aaron", 60, False):
            message = Message("Wizard Toad wishes you a good day =)", MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def replay(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["!replay"]):
        if bot.limiter.can_send(channel, "replay", 60, True):
            message = Message("Green FeelsOkayMan", MessageType.COMMAND, channel)
            bot.send_message(message)


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


@admin
@unwrap_command_args
def limit(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r'!limit (\w+)', msg)
    if match:
        cmd = match.group(1)
        s = bot.limiter.seconds_since_limit(channel, cmd)
        txt = "@" + username + ", " + str(s) + " seconds since command !" + cmd + " was used." \
            if s != 0 else "@" + username + ", that command wasn't used yet"
        message = Message(txt, MessageType.COMMAND, channel)
        bot.send_message(message)


@admin
@unwrap_command_args
def ping(bot: 'TwitchChat', args, msg, username, channel, send):
    if msg == "!ping":
        message = Message("Pong, I'm alive!", MessageType.FUNCTIONAL, channel)
        bot.send_message(message)


@returns
@unwrap_command_args
def remove_from_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    msg = msg.lower()
    if msg == "!unignore me":
        ignore_list.remove(username)
        message = Message("@" + username + ", welcome back PrideLion !", MessageType.COMMAND, channel)
        bot.send_message(message)
        return True
    return False


@returns
@unwrap_command_args
def ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    if username in ignore_list:
        validate_emotes(bot, args, False)
        return True
    return False


@command
@unwrap_command_args
def add_to_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    msg = msg.lower()
    if msg == "!ignore me":
        ignore_list.add(username)
        message = Message("@" + username + ", from now on you will be ignored PrideLion", MessageType.COMMAND, channel)
        bot.send_message(message)


@command
@unwrap_command_args
def seal(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!seal":
        if bot.limiter.can_send(channel, "seal", 20):
            message = Message("Such a brave bird PrideLion", MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def thor(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!thor":
        if bot.limiter.can_send(channel, "thor", 20):
            message = Message("Just beat it 4Head", MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def psy(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!psy":
        if bot.limiter.can_send(channel, "psy", 20):
            message = Message("@psygs daily ping or however many times people use this command PrideLion",
                              MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def lilb(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!lilb":
        if bot.limiter.can_send(channel, "lilb", 20):
            message = Message(line_pickers.get("lilb").get_line(), MessageType.COMMAND, channel)
            bot.send_message(message)


@command
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


@command
@unwrap_command_args
def xray(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!xray":
        if bot.limiter.can_send(channel, "xray", 20):
            message = Message("* peepoHug intensifies *", MessageType.COMMAND, channel)
            bot.send_message(message)


@command
@unwrap_command_args
def deane(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!deane":
        if bot.limiter.can_send(channel, "deane", 120):
            message = Message("peepoArrive", MessageType.COMMAND, channel)
            bot.send_message(message)
            time.sleep(0.5)
            message = Message("hi", MessageType.COMMAND, channel)
            bot.send_message(message)
            time.sleep(0.5)
            message = Message("ppPoof", MessageType.COMMAND, channel)
            bot.send_message(message)



@command
@unwrap_command_args
def auto(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if msg.lower() == "!auto":
        if bot.limiter.can_send(channel, "auto", 20):
            message = Message("YELLOW GANG ALL MY HOMIES LOVE YELLOW GANG", MessageType.COMMAND, channel)
            bot.send_message(message)
"""
    Commands in this file will be automatically used by chatbot for commands.
    Any time a message appears it will run through all the commands available

    @command = this will add the method to the commands that are called when a PRIVMSG appears
    @admin = This will call the command only when the admin of the bot (bot defined in ChatBot.py or credentials.py)
             types the command in chat
    @returns = This is for commands where other commands shouldn't run
    @save = called in save method every 10 minutes.
    @notice = This will call the command when an USERNOTICE is send in chat.


    LINES = contains all RandomLinePickers used in commands.
            These are stored in twitchchat.chat.TwitchChat.line_pickers.
"""
import os

from utility import *
from utility import rbac
import functools
import re
import urllib3
import enchant
import time
import datetime
import pymongo
import json
from credentials import mongo_credentials
from credentials import credentials
from google.oauth2 import service_account
import googleapiclient.discovery
import googleapiclient.errors
# THIS IS TO AVOID CYCLICAL IMPORTS BUT STILL ALLOWS TYPE CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitchchat.chat import TwitchChat
# LOADING STUFF

ADMIN = {}
COMMAND = {}
CLEARCHAT = {}
NOTICE = {}
COMMANDS = {}
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
    "lilb": RandomLinePicker("texts/lilb.txt"),
    "halloween": RandomLinePicker("texts/halloween.txt")
}

lurkers = dict()
previous_lurker_ts = time.time() - 600
ignore_list = LockedData(f.load("texts/ignore.txt", set()))
alts = LockedData(f.load("texts/alts.txt", dict()))
bad_words = f.load("texts/bad_words.txt", [])
streaks = LockedData(f.load("texts/streaks.txt", {}))
origins = f.load("texts/emote_origins.txt")
dictionary_words = LockedData(f.load("texts/dictionary.txt", []))
commands = LockedData(f.load("texts/commands.txt", {}))
rps_scores = LockedData(f.load("texts/rps.txt", {}))


def get_youtube_api():
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "0"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "credentials/youtube_credentials.json"

    # Get credentials and create an API client
    credentials = service_account.Credentials.from_service_account_file(client_secrets_file, scopes=scopes)
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)
    return youtube


def load_emotes():
    emote_dict = {}
    all_emotes = f.load("texts/emotes.txt", [])
    emote_dict["all_emotes"] = all_emotes
    for emote in all_emotes:
        if emote.lower() not in emote_dict:
            emote_dict[emote.lower()] = []
        emote_dict[emote.lower()].append(emote)
    return emote_dict


youtube = get_youtube_api()
db = LockedData({"emotes": dict(), "mentions": []})
emote_dict = LockedData(load_emotes())
blacklisted = f.load("texts/blacklisted.txt", [])
afk = dict()
ID_cache = IDCache()


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


def clearchat(func):
    CLEARCHAT[func.__name__] = func
    return func


def notice(func):
    NOTICE[func.__name__] = func
    return func


def alias(*aliases):
    def inner_func(func):
        for alias in aliases:
            COMMANDS[alias] = func
        return func

    return inner_func


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

client = pymongo.MongoClient("mongodb://{}:{}@127.0.0.1:27017/".format(mongo_credentials.user, mongo_credentials.pwd))


@save
def save_emotes():
    global db, client

    def save_emotes_inner(temp_db, kwargs):
        ts = datetime.datetime.utcnow()
        for channel, collections in temp_db.get("emotes").items():
            db = client[channel]
            global_coll = db["global"]
            global_coll.insert_one({"count": collections.get("count"), "timestamp": ts})
            for emote, wrong_emotes in collections.items():
                col = db[emote]
                wrong_emotes_to_insert = []
                if emote != "count":
                    for (misspell, activity), count in wrong_emotes.items():
                        item = {"count": count, "spelling": misspell, "activity": activity,
                                "timestamp": ts}
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
def save_streaks():
    global streaks
    streaks.access(lambda streaks, kwargs: f.save(streaks, "texts/streaks.txt"))
    # clear buffer
    streaks.buffered_write(update_streak_inner)


@save
def save_emotes_txt():
    global emote_dict

    def save_emotes_inner(data, kwargs):
        f.save(data["all_emotes"], "texts/emotes.txt")

    emote_dict.access(save_emotes_inner)
    # clear buffer
    emote_dict.access(append_to_list_in_dict)
    emote_dict.access(write_to_dict)


@save
def save_user_roles():
    rbac.users.access(lambda db, kwargs: f.save(db, "texts/user_roles.txt"))


@save
def save_blacklist():
    f.save(blacklisted, "texts/blacklisted.txt")


@save
def save_dictionary_words():
    def save_dictionary_inner(data, kwargs):
        f.save(data, "texts/dictionary.txt")

    dictionary_words.access(save_dictionary_inner)


@save
def save_commands():
    def save_commands_inner(data, kwargs):
        f.save(data, "texts/commands.txt")

    commands.access(save_commands_inner)


@save
def save_rps_scores():
    def save_rps_inner(data, kwargs):
        f.save(data, "texts/rps.txt")

    rps_scores.access(save_rps_inner)


# ADMIN
@rbac.addRole("toggler")
@admin
@unwrap_command_args
def toggle(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r"!toggle\s(\w+)", msg)
    if match:
        ans = match.group(1)
        if ans == "on":
            bot.toggle_channel(channel, ToggleType.ON)
            message = Message("Hey guys PrideLion !", MessageType.CHAT, channel, username)
            bot.send_message(message)
        elif ans == "off":
            bot.toggle_channel(channel, ToggleType.OFF)
            message = Message("Bye guys PrideLion !", MessageType.CHAT, channel, username)
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
            pass
        return True
    return False


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


@rbac.addRole("pinger")
@admin
@unwrap_command_args
def ping(bot: 'TwitchChat', args, msg, username, channel, send):
    if msg == "!ping":
        message = Message("Pong, I'm alive!", MessageType.FUNCTIONAL, channel, username)
        bot.send_message(message)
        return True
    return False


@rbac.addRole("snitch")
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
            channel,
            username
        )
        bot.send_message(message)
        return True
    return False


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
                channel,
                username
            )
            bot.send_message(message)


@admin
@unwrap_command_args
def add_line(bot: 'TwitchChat', args, msg, username, channel, send):
    global line_pickers
    match = re.match(r'!addline\s([^\s]+)\s(.+)', msg)
    if match:
        file = match.group(1)
        line = match.group(2)
        if file in line_pickers:
            line_pickers.get(file).add_line(line)
            message = Message(line + " has been added to " + file + ".", MessageType.CHAT, channel, username)
        else:
            message = Message("I don't recognize " + file + " you may have typed it wrong.",
                              MessageType.CHAT, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def remove_line(bot: 'TwitchChat', args, msg, username, channel, send):
    global line_pickers
    match = re.match(r'!removeline\s([^\s]+)\s(.+)', msg)
    if match:
        file = match.group(1)
        line = match.group(2)
        if file in line_pickers:
            line_pickers.get(file).remove_line(line)
            message = Message(line + " has been removed from " + file + " if it was in it.", MessageType.CHAT, channel,
                              username)
        else:
            message = Message("I don't recognize " + file + " you may have typed it wrong.", MessageType.CHAT, channel,
                              username)
        bot.send_message(message)


@admin
@unwrap_command_args
def add_emote(bot: 'TwitchChat', args, msg, username, channel, send):
    global emote_dict
    match = re.match(r'!addemote\s(\w+)', msg)
    if match:
        emote = match.group(1)
        contains_check = emote_dict.access(contains, elem=emote.lower())
        if contains_check and emote in emote_dict.access(get_val, key=emote.lower()):
            message = Message("Already know that emote (albeit in a lowered form) 4Weird", MessageType.COMMAND, channel,
                              username)
            bot.send_message(message)
        elif contains_check:
            emote_dict.buffered_write(append_to_list_in_dict, key="all_emotes", val=emote)
            emote_dict.buffered_write(append_to_list_in_dict, key=emote.lower(), val=emote)
            message = Message("I know " + emote + " now OkayChamp", MessageType.COMMAND, channel, username)
            bot.send_message(message)
        else:
            emote_dict.buffered_write(append_to_list_in_dict, key="all_emotes", val=emote)
            emote_dict.buffered_write(write_to_dict, key=emote.lower(), val=[emote])
            message = Message("I know " + emote + " now OkayChamp", MessageType.COMMAND, channel, username)
            bot.send_message(message)


@admin
@unwrap_command_args
def add_role(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!addrole\s(\w+)\s(\w+)', msg.lower())
    if match:
        role = match.group(1)
        user = match.group(2)
        rbac.add_role(user, role, channel)
        message = Message(user + " now has role " + role + " PrideLion", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def remove_role(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!removerole\s(\w+)\s(\w+)', msg.lower())
    if match:
        role = match.group(1)
        user = match.group(2)
        rbac.remove_role(user, role, channel)
        message = Message(user + " no longer has role " + role + " PrideLion . Did they abuse it 4WeirdW ?",
                          MessageType.COMMAND, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def delete_counter(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!deletecounter\s([^\s]+)\s([^\s]+)', msg)
    if match:
        user = match.group(1)
        word = match.group(2)
        if user in bot.state and "counters" in bot.state.get(user) and word in bot.state.get(user).get("counters"):
            bot.state.get(user).get("counters").pop(word)
            if word == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                message = Message("Can't say the word but it will no longer be tracked for " + user,
                                  MessageType.COMMAND, channel, username)
            else:
                message = Message("I will no longer track " + word + " for " + user, MessageType.COMMAND, channel,
                                  username)
            bot.send_message(message)
        else:
            if word == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                message = Message("Can't say the word but I wasn't tracking it for " + user + " 4Head",
                                  MessageType.COMMAND, channel, username)
            else:
                message = Message("I wasn't tracking " + user + " for " + word + " 4Head", MessageType.COMMAND, channel,
                                  username)
            bot.send_message(message)


@admin
@unwrap_command_args
def add_subscription(bot: 'TwitchChat', args, msg, username, channel, send):
    if msg == "!sub":
        bot.twitch_status.add_subscription(channel)


@admin
@unwrap_command_args
def remove_subscription(bot: 'TwitchChat', args, msg, username, channel, send):
    if msg == "!unsub":
        bot.twitch_status.remove_subscription(channel)


@admin
@unwrap_command_args
def ignore_user(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!ignore\s(\w+)', msg)
    if match:
        user = match.group(1)
        ignore_list.access(add_to_container, elem=user)
        message = Message("Ignoring " + user + " from now on PrideLion", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def blacklist_user(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!blacklist\s(\w+)', msg.lower())
    if match:
        user = match.group(1)
        if user not in blacklisted:
            blacklisted.append(user)
        message = Message(user + " is now blacklisted", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def unblacklist_user(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!unblacklist\s(\w+)', msg.lower())
    if match:
        user = match.group(1)
        if user in blacklisted:
            blacklisted.remove(user)
        message = Message(user + " is now unblacklisted", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@admin
@unwrap_command_args
def reset_streak(bot: 'TwitchChat', args, msg, username, channel, send):
    global streaks
    match = re.match(r'!reset\s([^\s]+)', msg)
    if match:
        emote = match.group(1)
        streaks.access(reset_streak_inner, emote=emote, channel=channel)
        return True
    return False


@admin
@unwrap_command_args
def add_word(bot: 'TwitchChat', args, msg, username, channel, send):
    global dictionary, dictionary_words
    match = re.match(r'!addword\s([^\s]+)', msg)
    if match:
        new_word = match.group(1)
        dictionary.add(new_word)
        dictionary_words.access(add_to_container, elem=new_word)
        return True
    return False


@admin
@unwrap_command_args
def add_command(bot: 'TwitchChat', args, msg, username, channel, send):
    global commands
    match = re.match(r'!addcommand\s([a-zA-Z0-9_]*)\s(.*)', msg)
    if match:
        command_name = match.group(1)
        if commands.access(contains, elem=command_name):
            bot.send_message(Message(
                "This command is already in use, if you want to overwrite this command use !addcommandf PrideLion",
                MessageType.FUNCTIONAL, channel, username))
        else:
            commands.access(write_to_dict, key=command_name, val=match.group(2))
            bot.send_message(
                Message(f"Command {command_name} added PrideLion", MessageType.FUNCTIONAL, channel, username))


@admin
@unwrap_command_args
def add_commandf(bot: 'TwitchChat', args, msg, username, channel, send):
    global commands
    match = re.match(r'!addcommandf\s([a-zA-Z0-9_]*)\s(.*)', msg)
    if match:
        command_name = match.group(1)
        commands.access(write_to_dict, key=command_name, val=match.group(2))
        bot.send_message(Message(f"Command {command_name} added PrideLion", MessageType.FUNCTIONAL, channel, username))


# COMMANDS


@command
@unwrap_command_args
def ping_me(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, [" ping ", " me "]):
        message = Message("@" + username + ", ping!", MessageType.HELPFUL, channel, username)
        bot.send_message(message)


@command
@unwrap_command_args
def loop_over_words(bot: 'TwitchChat', args, msg, username, channel, send):
    words = msg.split()
    username = username.lower()
    # static data
    counters = bot.state.get(username, {}).get("counters", {})
    emotes = emote_dict.access(get_val, key="all_emotes")
    unique_emotes = set()
    wrong_emotes = []
    status = bot.twitch_status.get_status(channel)
    # static flags
    counters_check = username in bot.state and len(counters) != 0
    not_bot = not username == bot.user
    for word in words:
        if word.lower() == "poooound" and bot.limiter.can_send(channel, "pound", 30, True):
            message = Message("Poooound", MessageType.SPAM, channel, username)
            bot.send_message(message)
        if counters_check and word in counters:
            counters[word] = str(int(counters.get(word)) + 1)
        if not_bot:
            # Using De morgan laws to turn not (a and b) to not a or not b turns this into harder to understand boolean
            if len(word) > 2 and not (word[0] == "\"" and word[-1] == "\""):
                wrong_emote = validate_emotes(channel, status, word, emotes)
                if wrong_emote is not None:
                    wrong_emotes.append(wrong_emote)
        if word in emotes and word not in unique_emotes and word != "WeirdChamp":
            unique_emotes.add(word)
        match = re.match(r".*watch\?v=([a-zA-Z0-9\-_]+).*", word)
        if match:
            check_for_troll(bot, channel, username, match.group(1))
    update_streaks(unique_emotes, channel, username)
    # Use data gathered
    if len(wrong_emotes) != 0:
        amount = bot.state.get(channel).get("lacking", "0")
        bot.state[channel]["lacking"] = str(int(amount) + len(wrong_emotes))
        if send:
            txt = " ".join(wrong_emotes)
            message = Message("@" + username + ", pepePoint " + txt, MessageType.SPAM, channel, username)
            bot.send_message(message)


def check_for_troll(bot: 'TwitchChat', channel: str, username: str, video_id: str):
    global youtube
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()
    try:
        title = response.get("items")[0].get("snippet").get("title")
        if contains_all(title.lower(), ["rick", "roll"]) or contains_all(title.lower(),
                                                                         ["gonna", "give", "you", "up", "rick",
                                                                          "astley"]):
            message = Message("Don't search that youtube video, " + username + " is trying to rick roll you!",
                              MessageType.HELPFUL, channel, username)
        elif contains_all(title.lower(), ["stick", "bug"]):
            message = Message("Don't search that youtube video, " + username + " is trying to stick bug you!",
                              MessageType.HELPFUL, channel, username)
        elif contains_all(title.lower(), ["jebaited"]):
            message = Message("Don't search that youtube video, " + username + " is trying to Jebaited you!",
                              MessageType.HELPFUL, channel, username)
        elif contains_word(title.lower(), ["corrolad", "corolla'd", "corollad"]):
            message = Message("Don't search that youtube video, " + username + " is trying to toyota corolla you!",
                              MessageType.HELPFUL, channel, username)
        else:
            return
        bot.send_message(message)
    except IndexError as e:
        return


def update_streaks(unique_emotes, channel, username):
    global streaks
    streaks.buffered_write(update_streak_inner, emotes=unique_emotes, channel=channel)


def validate_emotes(channel, status, word, emotes):
    global emote_dict, db
    word = cleanup(word)
    lowered_word = word.lower()
    if emote_dict.access(contains, elem=lowered_word):
        correct_emotes = emote_dict.access(get_val, key=lowered_word)
        if word not in correct_emotes and not dictionary.check(word):
            db.buffered_write(update_emotes, chan=channel, we=word, ce=correct_emotes[0], ac=status.get("activity"))
            return word
    else:
        val = validate_emote(word, emotes)
        if not val.boolean:
            if not dictionary.check(word):
                db.buffered_write(update_emotes, chan=channel, we=word, ce=val.correct, ac=status.get("activity"))
                return word


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
def time_out(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    username = username
    if "time out" in msg and username == bot.admin:
        message = Message(
            "This is a very long text so that eventually I will get timed out with a relatively small time. This is done so that my messages will get \"cleared\" and is appropriate when you said some shit that you regret or find repulsive. Hopefully this text is long enough cause I don't know the character limit. I'm dog like that. How many more sentences should I write to get that sweet sweet timeout , is this long enough? God I hope it is? Imagine if it wasn't I would look foolish and goolish. pepePray ",
            MessageType.SPECIAL, channel, username)
        bot.send_message(message)
    elif "time out" in msg:
        message = Message("@" + username + " What's the password", MessageType.SPAM, channel, username)

        bot.send_message(message)


@command
@unwrap_command_args
def dance(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg
    if contains_word(msg, [" ludwigGun ", " flyannGun "]) and bot.limiter.can_send(channel, "dance", 25, True):
        message = Message("pepeD " * random.randint(1, 9), MessageType.SPAM, channel, username)

        bot.send_message(message)


@command
@unwrap_command_args
def respond(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_word(msg, ["@" + bot.user, bot.user]):
        message = Message("@" + username +
                          ", Beep Boop MrDestructoid",
                          MessageType.SPAM, channel, username)
        bot.send_message(message)


@command
@unwrap_command_args
def weird_jokes(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    if contains_all(msg, [" slime ", " piss "]) \
            or contains_all(msg, [" slime ", " pee "]):
        message = Message("@" + username + ", FeelsWeirdMan", MessageType.SPAM, channel, username)
        bot.send_message(message)


@command
@unwrap_command_args
def card_pogoff(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    msg = cleanup(msg)
    if \
            (
                    username.lower() in
                    [
                        "cardinal256",
                        "lil_schleem"
                    ]
            ) and (
                    contains_all(msg.rstrip().lower(), ["ptidelio", "pepelaugh"])
                    or contains_all(msg.rstrip().lower(), ["ptideiio", "pepelaugh"])
                    or contains_all(msg.rstrip().lower(), ["ptideii", "omegalul"])
                    or contains_all(msg.rstrip().lower(), ["ptideli", "omegalul"])
                    or contains_all(msg.lower().rstrip(), ["wulf", "pogo"])
                    or contains_all(msg.lower().rstrip(), ["nuggle1laugh", "ptidelio"])
            ):
        message = Message("@" + username + ", PogOff you're not funny " + "PogOff " * random.randint(1, 6),
                          MessageType.SPAM, channel, username)
        bot.send_message(message)


@command
@unwrap_command_args
def check_if_afk(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if username in afk:
        afk.pop(username)
        message = Message("@" + username + ", " + line_pickers.get("greetings").get_line() + " " +
                          line_pickers.get("friends").get_line() + " PrideLion ",
                          MessageType.HELPFUL, channel, username)
        bot.send_message(message)


@command
@unwrap_command_args
def notify_afk(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    for word in msg.lower().split():
        if word in afk:
            message = Message("that user is afk for: " + afk.get(word), MessageType.SPAM, channel, credentials.username)
            bot.send_message(message)


"""
@command
@unwrap_command_args
def scrape_color(bot: 'TwitchChat', args, msg, username, channel, send):
    color = args['color']
    color = color if len(color) != 0 else "#808080"
    try:
        doc = client.colors.users.find({"username": username.lower()})[0]
        if doc["hex"] != color:
            client.colors.users.replace_one(doc, {"username": username.lower(), "hex": color})
    except IndexError:
        client.colors.users.insert_one({"username": username.lower(), "hex": color})
"""


# CLEARCHAT

@clearchat
def send_kapow(bot: 'TwitchChat', args):
    channel = args["channel"]
    message = Message("KAPOW", MessageType.SPAM, channel, credentials.username)
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
        message = Message("POGGIES " + type_sub + "!", MessageType.SUBSCRIBER, channel, username)
        bot.send_message(message)
        bot.state["lonewulfx6"]["counters"]["POGGIES"] = str(
            int(bot.state.get("lonewulfx6").get("counters").get("POGGIES")) + 1)
    elif tipe == "subgift":
        amount_of_gifts = args.get("msg-param-sender-count")
        if amount_of_gifts != "0" and amount_of_gifts is not None:
            message = Message("POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SUBSCRIBER, channel, username)
            bot.send_message(message)
            bot.state["lonewulfx6"]["counters"]["POGGIES"] = str(
                int(bot.state.get("lonewulfx6").get("counters").get("POGGIES")) + 1)
    elif tipe == "submysterygift":
        amount_of_gifts = args.get("msg-param-sender-count", "0")
        if amount_of_gifts != "0" and amount_of_gifts is not None:
            message = Message("POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SUBSCRIBER, channel, username)
            bot.send_message(message)
            bot.state["lonewulfx6"]["counters"]["POGGIES"] = str(
                int(bot.state.get("lonewulfx6").get("counters").get("POGGIES")) + 1)
    elif tipe == "anonsubgift":
        message = Message("POGGIES", MessageType.SUBSCRIBER, channel, username)
        bot.send_message(message)
        bot.state["lonewulfx6"]["counters"]["POGGIES"] = str(
            int(bot.state.get("lonewulfx6").get("counters").get("POGGIES")) + 1)
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


@alias("ignore")
@unwrap_command_args
def add_to_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    if not ignore_list.access(contains, elem=username):
        ignore_list.buffered_write(add_to_container, elem=username)
        message = Message("@" + username + ", from now on you will be ignored PrideLion", MessageType.COMMAND,
                          channel, username)
        bot.send_message(message)
    else:
        message = Message("@" + username + ", You're already ignored 4Head", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("unignore")
@unwrap_command_args
def remove_from_ignore(bot: 'TwitchChat', args, msg, username, channel, send):
    global ignore_list
    if ignore_list.access(contains, elem=username):
        ignore_list.buffered_write(delete_from_set, elem=username)
        message = Message("@" + username + ", welcome back PrideLion !", MessageType.COMMAND, channel, username)
        bot.send_message(message)
    else:
        message = Message("@" + username + ", you're not ignored 4Head", MessageType.COMMAND, channel, username)
        bot.send_message(message)


http = urllib3.PoolManager()


def english_dictionary():
    global dictionary_words
    english_dict = enchant.Dict("en_US")
    current_words = dictionary_words.access(get_data)
    for word in current_words:
        english_dict.add(word)
    return english_dict


dictionary = english_dictionary()


@alias("dict", "dictionary")
@unwrap_command_args
def dct(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower() + " "
    match = re.match(r"!dict\s([^\s]+)", msg)
    if match:
        word = match.group(1)
        try:
            definition = define(word)
            if word == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                message = Message("@" + username + ", Can't fool me PepeLaugh", MessageType.COMMAND, channel, username)
            else:
                message = Message("@" + username + ", " + definition, MessageType.COMMAND, channel, username)
        except Exception:
            if word == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                message = Message("@" + username + ", Can't fool me PepeLaugh", MessageType.COMMAND, channel, username)
            else:
                message = Message("@" + username + " couldn't look up the definition of " + word,
                                  MessageType.COMMAND, channel, username)
        bot.send_message(message)


def define(word):
    html = http.request("GET", "http://dictionary.reference.com/browse/" + word + "?s=t").data.decode("UTF-8")
    items = re.findall('<meta name=\"description\" content=\"(.*) See more.\">', html, re.S)
    defs = [re.sub('<.*?>', '', x).strip() for x in items]
    return defs[0]


@alias("addcounter", "addcount")
@unwrap_command_args
def addcounter(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!addcounte*r*\s([^\s]+)\s*([^\s]*)', msg)
    if match:
        val_or_user = match.group(1)
        val = match.group(2)
        username = username.lower()
        if len(val) == 0:
            if val_or_user.lower() in bad_words:
                message = Message("@" + username + ", not fucking cool man.", MessageType.COMMAND, channel, username)
                bot.send_message(message)
                return True
            # Add the counter for the user that used this command
            bot.state[username] = bot.state.get(username, dict())
            bot.state[username]["counters"] = bot.state.get(username).get("counters", {})
            counters = bot.state.get(username).get("counters")
            if len(counters) < 5:
                if val_or_user not in counters:
                    counters[val_or_user] = counters.get(val_or_user, "0")
                    if val_or_user == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                        message = Message("@" + username + ", I'm currently not subscribed so I can't say the word. "
                                                           "But it will be tracked for you PrideLion !",
                                          MessageType.COMMAND, channel, username)
                    else:
                        message = Message(
                            "@" + username + ", I will now count how many times you say " + val_or_user + " PrideLion",
                            MessageType.COMMAND, channel, username)
                    bot.send_message(message)
                else:
                    message = Message("@" + username + ", already tracking " + val_or_user + " 4Head",
                                      MessageType.COMMAND,
                                      channel,
                                      username
                                      )
                    bot.send_message(message)
            else:
                message = Message(
                    "@" + username + ", you already have 5 counters, you can't have more. "
                                     "Ask " + bot.admin + " nicely to implement a delete counter command",
                    MessageType.COMMAND,
                    channel,
                    username
                )
                bot.send_message(message)
        else:
            if val.lower() in bad_words:
                message = Message("@" + username + ", not fucking cool man.", MessageType.COMMAND, channel, username)
                bot.send_message(message)
                return True
            val_or_user = val_or_user.lower()
            if username.lower() == val_or_user.lower() or username == bot.admin:
                # add the counter for the username mentione with
                bot.state[val_or_user] = bot.state.get(val_or_user, dict())
                bot.state[val_or_user]["counters"] = bot.state.get(val_or_user).get("counters", {})
                counters = bot.state.get(val_or_user).get("counters")
                if len(counters) < 5:
                    if val not in counters:
                        counters[val] = counters.get(val, "0")
                        if val == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                            message = Message(
                                "@" + username + ", I'm currently not subscribed so I can't say the word. "
                                                 "But it will be tracked for you PrideLion !",
                                MessageType.COMMAND, channel, username)
                        else:
                            message = Message(
                                "@" + username + ", I will now count how many times "
                                + val_or_user + " says " + val + " PrideLion",
                                MessageType.COMMAND, channel, username)
                        bot.send_message(message)
                    else:
                        message = Message("@" + username + ", already tracking " + val_or_user + " 4Head",
                                          MessageType.COMMAND,
                                          channel,
                                          username
                                          )
                        bot.send_message(message)
                else:
                    message = Message(
                        "@" + username + ", you already have 5 counters, you can't have more. "
                                         "Ask " + bot.admin + " nicely to implement a delete counter command",
                        MessageType.COMMAND,
                        channel,
                        username
                    )
                    bot.send_message(message)
            else:
                # Let user know who can do this command
                message = Message(
                    "@" + username + ", only " + val_or_user + " and " + bot.admin + " can use this command",
                    MessageType.COMMAND,
                    channel,
                    username
                )
                bot.send_message(message)


@alias("count")
@unwrap_command_args
def get_count(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!count\s(\w+)\s*([^\s]*)', msg)
    if match:
        user = match.group(1).lower() if len(match.group(2)) != 0 else username.lower()
        val = match.group(2) if len(match.group(2)) != 0 else match.group(1)
        if val.lower() in bad_words:
            message = Message("@" + username + ", not fucking cool man.", MessageType.COMMAND, channel, username)
            bot.send_message(message)
            return
        if user in bot.state:
            if len(bot.state.get(user).get("counters", dict())) != 0:
                counters = bot.state.get(user).get("counters")
                if val in counters:
                    if val == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                        message = Message(
                            "@" + username + ", I'm currently not subscribed so I can't say that word sorry!",
                            MessageType.COMMAND, channel, username)
                        bot.send_message(message)
                        return
                    if bot.limiter.can_send(channel, user, 5):
                        message = Message(
                            "@" + username + ", " + user + " has said " + val + " " + counters.get(val) + " times",
                            MessageType.COMMAND,
                            channel,
                            username
                        )
                        bot.send_message(message)
                else:
                    message = Message("@" + username + ", " + user + " isn't being tracked for " + val,
                                      MessageType.COMMAND, channel, username)
                    bot.send_message(message)
            else:
                message = Message("@" + username + ", " + user + " doesn't have any counts", MessageType.COMMAND,
                                  channel, username)
                bot.send_message(message)
        else:
            message = Message("@" + username + ", " + user + " doesn't have any counts", MessageType.COMMAND, channel,
                              username)
            bot.send_message(message)


@alias("whois")
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
                channel,
                username
            )
            bot.send_message(message)
        else:
            message = Message(
                "@" + username + ", " + match.group(1) + " is " + alt + " PrideLion",
                MessageType.COMMAND,
                channel,
                username
            )
            bot.send_message(message)


@alias("correct")
@unwrap_command_args
def correct(bot: 'TwitchChat', args, msg, username, channel, send):
    global emote_dict
    match = re.match(r"!correct (\w+)", msg)
    if match:
        emote = match.group(1)
        correct_emotes = emote_dict.access(get_val, key=emote.lower())
        if correct_emotes is not None:
            if "WeirdChamp" in correct_emotes and not bot.twitch_status.is_subscribed_to(channel):
                message = Message("@" + username + " can't fool me PepeLaugh", MessageType.COMMAND, channel, username)
                bot.send_message(message)
                return
            if emote in correct_emotes:
                message = Message("@" + username + ", you wrote " + emote + " correctly! Good job FeelsWowMan",
                                  MessageType.COMMAND, channel, username)
                bot.send_message(message)
                return
            else:
                message = Message(
                    "@" + username + ", you wrote " + emote + " incorrectly FeelsBadMan . "
                                                              "The correct way(s) of spelling it is "
                    + " , ".join(correct_emotes),
                    MessageType.COMMAND, channel, username)
                bot.send_message(message)
                return
        else:
            message = Message(
                "@" + username + ", that emote wasn't in my emote database. "
                                 "So I can't tell you the correct way to spell it.", MessageType.COMMAND, channel,
                username)
            bot.send_message(message)


@alias("tyke")
@unwrap_command_args
def tyke(bot: 'TwitchChat', args, msg, username, channel, send):
    if bot.limiter.can_send(channel, "tyke", 300, True):
        for i in range(3):
            parity = i % 2
            txt = "blobDance RareChar blobDance RareChar blobDance " \
                if parity == 0 else "RareChar blobDance RareChar blobDance RareChar "
            message = Message(txt, MessageType.SPAM, channel, username)
            bot.send_message(message)


@alias("lurker", "lurking")
@unwrap_command_args
def lurk(bot: 'TwitchChat', args, msg, username, channel, send):
    global lurkers
    global previous_lurker_ts
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
        message = Message(txt, MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("limit", "cooldown")
@unwrap_command_args
def limit(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r'!(limit|cooldown) (\w+)', msg)
    if match:
        cmd = match.group(2)
        s = bot.limiter.seconds_since_limit(channel, cmd)
        txt = "@" + username + ", " + str(s) + " seconds since command !" + cmd + " was used." \
            if s != 0 else "@" + username + ", that command wasn't used yet"
        message = Message(txt, MessageType.COMMAND, channel, username)
        bot.send_message(message)
        return True


@alias("lilb")
@unwrap_command_args
def lilb(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if bot.limiter.can_send(channel, "lilb", 20):
        message = Message(line_pickers.get("lilb").get_line(), MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("deane")
@unwrap_command_args
def deane(bot: 'TwitchChat', args, msg, username, channel, send: bool):
    if bot.limiter.can_send(channel, "deane", 120):
        message = Message("peepoArrive", MessageType.COMMAND, channel, username)
        bot.send_message(message)
        message = Message("hi", MessageType.COMMAND, channel, username)
        bot.send_message(message)
        message = Message("ppPoof", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("fact")
@unwrap_command_args
def give_fact(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + ", did you know that " + line_pickers.get("facts").get_line(),
                      MessageType.COMMAND, channel, username)
    bot.send_message(message)


@alias("8ball", "eightball")
@unwrap_command_args
def eight_ball(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + " " + line_pickers.get("8ball").get_line(), MessageType.COMMAND, channel,
                      username)
    bot.send_message(message)


@alias("inspire")
@unwrap_command_args
def quote(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + ", " + line_pickers.get("quotes").get_line(), MessageType.COMMAND, channel,
                      username)
    bot.send_message(message)


@alias("lackers", "lacking")
@unwrap_command_args
def lacking(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    amount = bot.state.get(channel, {}).get("lacking", "0")
    message = Message("@" + username + ", " + amount + " people have been caught lacking PepeLaugh",
                      MessageType.SPECIAL, channel, username)
    bot.send_message(message)


@alias("pickup", "pickupline")
@unwrap_command_args
def pickup(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + ", " + line_pickers.get("pickups").get_line(), MessageType.COMMAND, channel,
                      username)
    bot.send_message(message)


@alias("joke", "jokes")
@unwrap_command_args
def joke(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + ", " + line_pickers.get("jokes").get_line(), MessageType.COMMAND, channel,
                      username)
    bot.send_message(message)


@alias("pyramid")
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
                MessageType.COMMAND, channel, username)
            bot.send_message(message)
            return True
        if layers > 3 and username != bot.admin:
            message = Message("@" + username + ", you're a greedy one ain'tcha peepoWTF", MessageType.COMMAND, channel,
                              username)
            bot.send_message(message)
            return True
        elif layers <= 0:
            message = Message("@" + username + ", wtf am I supposed to do with a non positive number peepoWTF",
                              MessageType.COMMAND, channel, username)
            bot.send_message(message)
            return True
        else:
            pyramid_emotes = match.group(2).split()
            correct_emotes = emote_dict.access(get_val, key="all_emotes")
            for emote in pyramid_emotes:
                if emote not in correct_emotes:
                    return True
                if emote == "WeirdChamp" and not bot.twitch_status.is_subscribed_to(channel):
                    message = Message("@" + username + " can't fool me PepeLaugh", MessageType.COMMAND, channel,
                                      username)
                    bot.send_message(message)
                    return True
            if bot.limiter.can_send(channel, "pyramid", 300):
                pyramid = word_pyramid(layers, pyramid_emotes)
                for pyramid_msg in pyramid:
                    message = Message(pyramid_msg, MessageType.SPAM, channel, username)
                    bot.send_message(message)
                return True


@alias("hex", "color", "colour")
@unwrap_command_args
def color(bot: 'TwitchChat', args, msg, username, channel, send):
    msg = msg.lower()
    match = re.match(r'!(hex|color|colour)\s(\w+)', msg)
    if match:
        user = match.group(2)
        color = get_color(user.lower())
        if color is not None:
            color_name = get_color_name(color, http)
            clarification = " which is " + color_name if len(color_name) != 0 else ""
            message = Message("@" + username + ", the last hex/color of " + user + " seen is " + color + clarification,
                              MessageType.COMMAND, channel, username)
            bot.send_message(message)
        else:
            message = Message("@" + username + ", I have never seen this person type in the chat O.o",
                              MessageType.COMMAND, channel, username)
            bot.send_message(message)


def get_color_name(hex_code: str, pm: urllib3.PoolManager):
    try:
        color_name = client.colors.names.find({"hex": hex_code})[0]
        return color_name.get("name")
    except IndexError:
        color_code = hex_code[1:]
        base = "https://www.color-hex.com/color/" + color_code.lower()
        response = pm.request("GET", base).data.decode("UTF-8")
        iteration = re.finditer(r'<title>' + hex_code.lower() + r' Color Hex (.+)</title>', response)
        try:
            first = next(iteration)
            client.colors.names.insert_one({"hex": hex_code, "name": first.group(1)})
            return first.group(1)
        except StopIteration:
            client.colors.names.insert_one({"hex": hex_code, "name": ""})
            return ""


def get_color(username):
    try:
        doc = client.colors.users.find({"username": username})[0]
        return doc.get("hex")
    except IndexError:
        return None


@alias("request")
@unwrap_command_args
def request(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message(
        ".w " + username + " https://docs.google.com/forms/d/1NLkm2W281fN_vzv-F-zzc3Npbq3IBf62w-i1Ye-z9oo/",
        MessageType.COMMAND, channel, username)
    bot.send_message(message)


@alias("unique")
@unwrap_command_args
def unique(bot: 'TwitchChat', args, msg, username, channel, send):
    if bot.limiter.can_send(channel, "unique", 20):
        users = client["colors"]["users"]
        unique_users = users.count()
        message = Message("The number of unique users x6 has seen is " + str(unique_users),
                          MessageType.COMMAND,
                          channel,
                          username
                          )
        bot.send_message(message)


@alias("jouch")
@unwrap_command_args
def jouch(bot: 'TwitchChat', args, msg, username, channel, send):
    if bot.limiter.can_send(channel, "jouch", 20):
        emote = random.choice(emote_dict.access(get_val, key="all_emotes"))
        if emote == "WeirdChamp":
            if bot.twitch_status.is_subscribed_to(channel):
                message = Message(emote + " on da Jouch ", MessageType.COMMAND, channel, username)
            else:
                message = Message("Tried to say wc when I wasn't subscribed", MessageType.COMMAND, channel, username)
        else:
            message = Message(emote + " on da Jouch ", MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("generate")
@unwrap_command_args
def generate(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!generate\s(\w+)', msg)
    if match:
        emote = match.group(1)
        if emote in emote_dict.access(get_val, key="all_emotes") and bot.limiter.can_send(channel, "generate", 30):
            emote += " "
            emote *= random.randint(1, 8)
            message = Message(emote, MessageType.SPAM, channel, username)
            bot.send_message(message)


@alias("streak")
@unwrap_command_args
def streak(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!streak\s(\w+)', msg)
    if match:
        def get_streak(dct, kwargs):
            if "emote" in kwargs and "channel" in kwargs:
                emote = kwargs.get("emote")
                channel = kwargs.get("channel")
                if emote in dct.get(channel, {}):
                    return dct.get(channel).get(emote)

        emote = match.group(1)
        streak = streaks.access(get_streak, emote=emote, channel=channel)
        if streak is None:
            message = Message("This emote wasn't in the database or hasn't been used yet, sorry PrideLion !",
                              MessageType.COMMAND,
                              channel, username)
            bot.send_message(message)
        else:
            current = streak["current"]
            max_streak = streak["max"]
            message = Message("@" + username + ", streak data " + emote + " : current =" + current
                              + " max =" + max_streak,
                              MessageType.COMMAND,
                              channel, username)
            bot.send_message(message)


@alias("topstreaks")
@unwrap_command_args
def top_streaks(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!topstreaks\s*(\d*)', msg.lower())
    if match:
        amount = int(match.group(1)) if len(match.group(1)) != 0 else 5
        if not username == bot.admin and (amount > 10 or amount < 1):
            message = Message("greedy greedy greedy peepoWTF", MessageType.COMMAND, channel, username)
            bot.send_message(message)
            return True

        def get_top_10_streaks(dct, kwargs):
            if "channel" in kwargs and "amount" in kwargs:
                channel = kwargs.get("channel")
                amount = kwargs.get("amount")
                streaks = []
                dct[channel] = dct.get(channel, {})
                for emote, streak in dct[channel].items():
                    streaks.append((emote, streak["max"]))
                streaks.sort(key=lambda tup: int(tup[1]), reverse=True)
                return streaks[:amount]

        top = streaks.access(get_top_10_streaks, channel=channel, amount=amount)
        if len(top) != 0:
            txt = ""
            for pos, (emote, streak) in enumerate(top, 1):
                txt += "<{}> {} with {} ".format(pos, emote, streak)
            message = Message(txt, MessageType.COMMAND, channel, username)
            bot.send_message(message)
        else:
            message = Message("No streaks yet PrideLion", MessageType.COMMAND, channel, username)
            bot.send_message(message)


@alias("info", "youtube")
@unwrap_command_args
def check_youtube(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!info\s/*watch\?v=([a-zA-Z0-9_\-]+)', msg)
    if match:
        video_id = match.group(1)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        try:
            title, channel_name = response.get("items")[0].get("snippet").get("title"), response.get("items")[0].get(
                "snippet").get("channelTitle")
            if contains_word(title.lower(), bad_words):
                message = Message("@" + username + ", fuck off for trying that 4Weird", MessageType.COMMAND, channel,
                                  username)
            else:
                msg = title + " - " + channel_name + " - LINK: https://www.youtube.com/watch?v=" + video_id if "linker" in rbac.get_roles(
                    username, channel) else title + " - " + channel_name
                message = Message(msg, MessageType.COMMAND, channel,
                                  username)
        except IndexError as e:
            message = Message("@" + username + ", that youtube video doesn't exist", MessageType.COMMAND, channel,
                              username)
        bot.send_message(message)


@alias("afk")
@unwrap_command_args
def going_afk(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r'!afk\s*(.*)', msg)
    if match:
        reason = match.group(1) if len(match.group(1)) != 0 else "No reason given"
        if contains_all(reason, ["gift", "me"]) or contains_word(reason, bad_words):
            message = Message("Can't fool me PepeLaugh", MessageType.COMMAND, channel, username)
            bot.send_message(message)
            return True
        afk[username] = reason
        message = Message("@" + username + ", " + line_pickers.get("byes").get_line() + " " +
                          line_pickers.get("friends").get_line() + " PrideLion",
                          MessageType.HELPFUL, channel, username)
        bot.send_message(message)


@alias("doomsday")
@unwrap_command_args
def doomsday(bot: 'TwitchChat', args, msg, username, channel, send):
    try:
        min_msgs = get_min_chat_count(channel)
        current_message_count = int(bot.state.get(channel).get("messages", "0"))
        if current_message_count < min_msgs:
            messages_away = min_msgs - current_message_count
            message = Message("@" + username + f", I'm currently {messages_away - 1} messages away from doomsday",
                              MessageType.COMMAND, channel, username)
        else:
            message = Message(
                "@" + username + ", either " + bot.admin + " didn't really care "
                                                           "or they're lazy because doomsday has passed",
                MessageType.COMMAND, channel, username
            )
        bot.send_message(message)
    except Exception:
        message = Message("Couldn't verify doomsday monkaW", MessageType.COMMAND, channel, username)
        bot.send_message(message)


def get_min_chat_count(channel: str):
    base = "https://api.streamelements.com/kappa/v2/chatstats/" + channel + "/stats"
    headers = {"accept": "application/json"}
    response = http.request("GET", base, headers=headers).data
    stats = json.loads(response)
    return stats.get("chatters")[-1].get("amount")


@alias("counts", "counters")
@unwrap_command_args
def counts(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r"!(counts|counters)\s*(\w*)", msg.lower())
    if match:
        username = username if len(match.group(2)) == 0 else match.group(2)
        if username in bot.state and "counters" in bot.state.get(username):
            counts = bot.state.get(username).get("counters").keys()
            counts = " ".join(counts)
            message = Message("@" + username + ", your counters are : " + counts, MessageType.COMMAND, channel,
                              username)
            bot.send_message(message)
        else:
            message = Message("@" + username + ", You don't have any counters 4Head .", MessageType.COMMAND, channel,
                              username)
            bot.send_message(message)


@alias("origin")
@unwrap_command_args
def origin(bot: 'TwitchChat', args, msg, username, channel, send):
    global origins
    match = re.match(r"!origin\s([^\s]+)", msg)
    if match:
        word = match.group(1)
        if word in origins:
            message = Message(f"@{username}, the origin of that emote is : {origins.get(word)}", MessageType.COMMAND,
                              channel, username)
        else:
            message = Message(f"@{username}, don't know the origin of that emote FeelsBadMan", MessageType.COMMAND,
                              channel, username)
        bot.send_message(message)


@alias("halloween", "costume_idea")
@unwrap_command_args
def costume_idea(bot: 'TwitchChat', args, msg, username, channel, send):
    message = Message("@" + username + ", You could try this: " + line_pickers.get("halloween").get_line(),
                      MessageType.COMMAND, channel, username)
    bot.send_message(message)


@alias("countdown")
@unwrap_command_args
def countdown(bot: 'TwitchChat', args, msg, username, channel, send):
    for i in range(3, 0, -1):
        message = Message(str(i), MessageType.COMMAND, channel, username)
        bot.send_message(message)
        time.sleep(1.3)
    message = Message("GO", MessageType.COMMAND, channel, username)
    bot.send_message(message)


@alias("roles")
@unwrap_command_args
def roles(bot: 'TwitchChat', args, msg, username, channel, send):
    roles = rbac.get_roles(username, channel)
    if len(roles) == 0:
        message = Message("@" + username + ", you don't have any roles 4Weird", MessageType.COMMAND, channel,
                          username)
        bot.send_message(message)
    else:
        string = "@" + username + ", your roles are : " + ", ".join(roles)
        message = Message(string, MessageType.COMMAND, channel, username)
        bot.send_message(message)


@alias("title")
@unwrap_command_args
def title(bot: 'TwitchChat', args, msg, username, channel, send):
    global ID_cache
    if bot.limiter.can_send(channel, "title", 30):
        if channel in ID_cache:
            title = get_title(http, channel, ID_cache.get_id(channel))
            message = Message("@" + username + ", Current title: " + title + " PrideLion ", MessageType.COMMAND,
                              channel, username)
            bot.send_message(message)
        else:
            message = Message("@" + username + ", Don't have the id for this channel yet somehow PrideLion ",
                              MessageType.COMMAND, channel, username)
            bot.send_message(message)


@alias("whoami")
@unwrap_command_args
def whoami(bot: 'TwitchChat', args, msg, username, channel, send):
    global alts
    alt = username
    while alts.access(contains, elem=alt):
        alt = alts.access(get_val, key=alt)
    message = Message("@" + username + ", you're " + alt + " PrideLion", MessageType.COMMAND, channel, username)
    bot.send_message(message)


@alias("rps_score")
@unwrap_command_args
def rps_score(bot: 'TwitchChat', args, msg, username, channel, send):
    global rps_scores
    if rps_scores.access(contains, elem=username):
        (wins, losses, ties) = rps_scores.access(get_val, key=username)
        message = Message(
            f"@{username}, your rock paper scissors scores is {int(wins) - int(losses)} with {wins} wins, {losses} losses, and {ties} ties PrideLion",
            MessageType.SPAM, channel, username)
        bot.send_message(message)
    else:
        message = Message(f"@{username}, you haven't played any rps games yet 4Head", MessageType.SPAM, channel,
                          username)
        bot.send_message(message)


# GAMES WOOOOO

@alias("rps")
@unwrap_command_args
def rps(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r"!rps\s*(rock|r|paper|p|scissors|s)*", msg.lower())
    if match and bot.limiter.can_send(channel, "rps", 5):
        matched = match.group(1)
        if matched is None:
            message = Message(
                f"@{username}, to play rock paper scissors, use !rps (rock or paper or scissors) PrideLion",
                MessageType.SPAM, channel, username)
            bot.send_message(message)
        else:
            rps_object = get_RPS_object(matched)
            if rps_object is None:
                message = Message(f"@{username} couldn't parse given symbol {matched}", MessageType.SPAM, channel,
                                  username)
                bot.send_message(message)
            else:
                (outcome, bot_symbol) = play_rps(rps_object)
                if outcome == Outcome.WON:
                    message = Message(f"@{username}, You won PrideLion ! I chose {str(bot_symbol)}",
                                      MessageType.SPAM, channel, username)
                    rps_scores.access(add_win, user=username)
                elif outcome == Outcome.LOST:
                    message = Message(f"@{username}, You lost PrideLion ! I chose {str(bot_symbol)}",
                                      MessageType.SPAM, channel, username)
                    rps_scores.access(add_loss, user=username)
                else:
                    message = Message(f"@{username}, We tied PrideLion ! I chose {str(bot_symbol)}",
                                      MessageType.SPAM, channel, username)
                    rps_scores.access(add_tie, user=username)
                bot.send_message(message)


ttt = TicTacToe()


@alias("tictactoe", "ttt")
@unwrap_command_args
def tictactoe(bot: 'TwitchChat', args, msg, username, channel, send):
    match = re.match(r"!(tictactoe|ttt)\s([^\s]+)", msg.lower())
    bot.logger.info("Trying to start ttt game")
    if match and bot.limiter.can_send(channel, "ttt", 600):
        if not ttt.active:
            ttt.p1 = username.lower()
            ttt.waiting_for = match.group(2).lower()
            message = Message(f"Waiting for @{match.group(2)} to accept the challenge with !accept PrideLion",
                              MessageType.SPAM, channel, username)
            bot.send_message(message)


@alias("swap")
@unwrap_command_args
def swap(bot: 'TwitchChat', args, msg, username, channel, send):
    if username.lower() == ttt.p1 and not ttt.active:
        match = re.match(r"!swap\s([^\s]*)", msg.lower())
        if match:
            previous_wait = ttt.waiting_for
            ttt.waiting_for = match.group(1)
            message = Message(f"@{username}, swapped challenge from {previous_wait} to {match.group(1)} PrideLion",
                              MessageType.SPAM, channel, username)
            bot.send_message(message)
    else:
        message = Message(
            f"@{username} either you're not the one who sent the challenge or the game is already running 4Head",
            MessageType.SPAM, channel, username)


@alias("accept")
@unwrap_command_args
def accept(bot: 'TwitchChat', args, msg, username, channel, send):
    if username.lower() == ttt.waiting_for:
        ttt.active = True
        if randint(0, 1) == 0:
            ttt.p2 = ttt.waiting_for
        else:
            ttt.p2 = ttt.p1
            ttt.p1 = ttt.waiting_for
        ttt.waiting_for = ""
        message = Message(f"TIC TAC TOE GAME STARTED. Player 1 = {ttt.p1}, Player 2 = {ttt.p2} PrideLion",
                          MessageType.SPAM, channel, username)
        bot.send_message(message)
        board = ttt.get_board()
        for row in board:
            message = Message(row, MessageType.SPAM, channel, username)
            bot.send_message(message)
        message = Message(
            f"Pick the row and column to place your symbol by using !pick row col. row and col need to be between 1 and 3 PrideLion",
            MessageType.SPAM, channel, username)
        bot.send_message(message)
    else:
        message = Message(f"Waiting for {ttt.waiting_for} not for you {username} 4WeirdW", MessageType.SPAM, channel,
                          username)
        bot.send_message(message)


@alias("pick")
@unwrap_command_args
def pick(bot: 'TwitchChat', args, msg, username, channel, send):
    user = username.lower()
    if ttt.active and (user == ttt.p1 or user == ttt.p2):
        match = re.match(r"!pick\s(\d)\s(\d)", msg.lower())
        if match:
            row = int(match.group(1))
            col = int(match.group(2))
            if ttt.pick(user, row, col):
                board = ttt.get_board()
                for row in board:
                    message = Message(row, MessageType.SPAM, channel, username)
                    bot.send_message(message)
                (won, player) = ttt.won()
                if won:
                    message = Message(f"@{player} won PrideLion !!", MessageType.SPAM, channel, username)
                    bot.send_message(message)
                    ttt.reset()
                    return
                tie = ttt.tie()
                if tie:
                    message = Message(f"No one won the tic tac toe game PrideLion !", MessageType.SPAM, channel,
                                      username)
                    bot.send_message(message)
                    ttt.reset()
                    return
            else:
                message = Message(f"@{username}, either it's not your turn or you tried to do an invalid turn",
                                  MessageType.SPAM, channel, username)
                bot.send_message(message)
    else:
        message = Message(f"@{username}, you're not participating 4WeirdW", MessageType.SPAM, channel, username)


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
            for channel in bot.channels:
                message = Message("I've received a critical update so I'm turning off, bye guys PrideLion !",
                                  MessageType.HELPFUL, channel, credentials.username)
                bot.send_message(message)
            time.sleep(len(bot.channels) * 2)
            bot.logger.info("STOPPING")
            bot.save()
            bot.stop_all()
        else:
            # chat.py wasn't modified so it's safe to reload commands.py
            for channel in bot.channels:
                message = Message("I've been upgraded or updated, I don't care, it's cool PrideLion !",
                                  MessageType.HELPFUL, channel, credentials.username)
                bot.send_message(message)
            bot.logger.info("RELOADING")
            bot.reload()


@repeat(30)
def check_for_title_change(state: dict, bot: 'TwitchChat'):
    channels = bot.channels
    for channel in channels:
        old_title = state.get(channel, "")
        if channel not in state["cache"]:
            user_id = get_id(http, channel)
            state["cache"].add_id(channel, user_id)
        else:
            user_id = state["cache"].get_id(channel)
        current_title = get_title(http, channel, user_id)
        if old_title != current_title:
            state[channel] = current_title
            message = Message(
                "PrideLion TITLE CHANGE PrideLion",
                MessageType.FUNCTIONAL,
                channel,
                credentials.username
            )
            if old_title != "" and not bot.twitch_status.get_status(channel)["live"]:
                bot.send_message(message)


@repeat_setup(check_for_title_change.__name__)
def check_for_title_change_setup(state: dict, bot: 'TwitchChat'):
    global ID_cache
    state["cache"] = ID_cache


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
        if live and live != state[channel]:
            state[channel] = live
            bot.logger.info(channel + " went live toggling bot off")
            bot.toggle_channel(channel, ToggleType.OFF)


@repeat_setup(toggle_if_live.__name__)
def toggle_if_live(state, bot: 'TwitchChat'):
    for channel in bot.channels:
        state[channel] = bot.twitch_status.get_status(channel)["live"]


# FILTERING

def filter_message(message: Message, bot: 'TwitchChat'):
    if message.user in blacklisted:
        message = Message("@" + message.user + ", " + "PogOff " * random.randint(1, 7),
                          message.type, message.channel, message.user)
    if contains_word(message.content, ["WeirdChamp"]) and not bot.twitch_status.is_subscribed_to(message.channel):
        message = Message("Can't fool me PepeLaugh", message.type, message.channel, message.user)
    return message

"""
    Commands in this file will be automatically used by chatbot for commands. Any time a message appears it will run through all the commands available

    @command = this will add the method to the commands that are called when a PRIVMSG appears
    @admin = This will call the command only when the admin of the bot (bot defined in ChatBot.py or credentials.py) types the command in chat
    @notice = This will call the command when an USERNOTICE is send in chat.

    LINES = contains all RandomLinePickers used in commands. These are stored in twitchchat.chat.TwitchChat.line_pickers.
"""
from utility.classes import *
from utility.functions import *
import functools
import re
import urllib3
import enchant

# DICTS

ADMIN = {}
COMMAND = {}
NOTICE = {}
line_pickers = {
    "greetings": RandomLinePicker("texts/hello.txt"),
    "8ball": RandomLinePicker("texts/8ball.txt"),
    "facts": RandomLinePicker("texts/facts.txt"),
    "friends": RandomLinePicker("texts/friend.txt"),
    "byes": RandomLinePicker("texts/goodbyes.txt"),
    "jokes": RandomLinePicker("texts/jokes.txt"),
    "pickups": RandomLinePicker("texts/pickuplines.txt"),
    "quotes": RandomLinePicker("texts/quotes.txt")
}


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


def unwrap_command_args(func):
    """
        Decorator for commands that automatically unwraps some args by calling them on the dictionary provided
    :param func: the function wrapped, takes 5 arguments
    :return: wrapped function that takes two inputs, args (dict) and bot (TwitchChat class)
    """
    @functools.wraps(func)
    def wrapper(bot, args: dict) -> bool:
        msg = args.get("message")
        username = args.get("username")
        channel = args.get("channel")
        return func(bot, args, msg, username, channel)

    return wrapper


# COMMANDS AND HELPER FUNCTIONS


http = urllib3.PoolManager()


def english_dictionary():
    english_dict = enchant.Dict("en_US")
    english_dict.add("pov")
    english_dict.add("POV")
    english_dict.add("pogo")
    english_dict.add("poro")
    return english_dict


dictionary = english_dictionary()


@command
@unwrap_command_args
def dct(bot, args, msg, username, channel):
    msg = msg.lower() + " "
    match = re.match(r"!dict\b(.*) ", msg)
    if match:
        word = match.group(1)
        if dictionary.check(word):
            try:
                definition = define(word)
                message = Message("@" + username + ", " + definition, MessageType.COMMAND)
                message = change_if_blacklisted(bot, username, message)
                bot.send_message(channel, message)
            except Exception:
                message = Message("@" + username + " couldn't look up the definition of " + word,
                                  MessageType.COMMAND)
                message = change_if_blacklisted(bot, username, message)
                bot.send_message(channel, message)
        else:
            message = Message("@" + username + ", " + word + " is not an english word.",
                              MessageType.COMMAND)
            message = change_if_blacklisted(bot, username, message)
            bot.send_message(channel, message)


def define(word):
    html = http.request("GET", "http://dictionary.reference.com/browse/" + word + "?s=t").data.decode("UTF-8")
    items = re.findall('<meta name=\"description\" content=\"(.*) See more.\">', html, re.S)
    defs = [re.sub('<.*?>', '', x).strip() for x in items]
    return defs[0]


def validate_emote(emote, emotes):
    for correct_emote in emotes:
        dist = hammington(emote, correct_emote)
        if dist == 1 or is_anagram(correct_emote, emote):
            return Validation(False, correct_emote)
    return Validation(True, emote)


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


def count_os(msg):
    count = 0
    max_count = 0
    prev_char = ""
    for char in msg:
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


def change_if_blacklisted(bot, username, msg):
    if username.lower() in bot.blacklisted:
        return Message("@" + username + " ludwigSpectrum " * random.randint(1, 3), MessageType.BLACKLISTED)
    return msg


@notice
def send_pog(bot, args):
    username = args["login"]
    tipe = args["msg-id"]
    channel = args["channel"]
    if is_word(tipe, ["sub", "resub"]):
        amount_of_months = args.get("msg-param-cumulative-months", None)
        type_sub = subscriber_type(amount_of_months)
        message = Message("@" + username + " POGGIES " + type_sub + "!", MessageType.SUBSCRIBER)
        bot.send_message(channel, message)
    elif tipe == "subgift":
        amount_of_gifts = args.get("msg-param-sender-count")
        if not amount_of_gifts == "0":
            message = Message("@" + username + " POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                              MessageType.SUBSCRIBER)
            bot.send_message(channel, message)
    elif tipe == "submysterygift":
        amount_of_gifts = args["msg-param-sender-count"]
        message = Message("@" + username + " POGGIES " + amount_of_gifts + " gifts! Bitch you crazy!",
                          MessageType.SUBSCRIBER)
        bot.send_message(channel, message)
    elif tipe == "anonsubgift":
        message = Message("POGGIES", MessageType.SUBSCRIBER)
        bot.send_message(channel, message)
    else:
        return


@command
@unwrap_command_args
def schleem(bot, args, msg, username, channel):
    msg = msg.lower()
    if "!schleem" == msg:
        if bot.limiter.can_send("schleem", 10):
            message = Message("Get outta town", MessageType.COMMAND)
            message = change_if_blacklisted(bot, username, message)
            bot.send_message(channel, message)


@command
@unwrap_command_args
def time_out(bot, args, msg, username, channel):
    msg = msg.lower()
    username = username
    if "time out" in msg and username == bot.admin:
        message = Message("Gift me PepeLaugh", MessageType.SPECIAL)
        bot.send_message(channel, message)
    elif "time out" in msg:
        message = Message("@" + username + " What's the password", MessageType.SPAM)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(args['channel'], message)


@command
@unwrap_command_args
def bye(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, ["cya", "goodbye", "bye", "pppoof"]):
        if bot.limiter.can_send("bye", 60, True):
            message = Message("@" + username
                              + ", " + line_pickers.get("byes").get_line()
                              + " " + line_pickers.get("friends").get_line() + " peepoHug"
                              , MessageType.HELPFUL)
            bot.send_message(channel, message)


@command
@unwrap_command_args
def gn(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, [" gn ", "good night", "goodnight", "to sleep", "bedtime", "to bed"]):
        if bot.limiter.can_send("bye", 60, True):
            message = Message("@" + username + ", " + "gn ppPoof , sleep tight!", MessageType.HELPFUL)
            bot.send_message(channel, message)


@command
@unwrap_command_args
def ping_if_asked(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, [" ping me ", " give me attention"]):
        message = Message("@" + username + " " + line_pickers.get("greetings").get_line(), MessageType.SPECIAL)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def give_fact(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, ["!fact", "!facts", "give me a fact"]):
        message = Message("@" + username + ", did you know that " + line_pickers.get("facts").get_line(),
                          MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def reply_if_yo(bot, args, msg, username, channel):
    msg = msg.lower()
    if len(msg) > 2 and "yo" in msg and count_os(msg) > 2:
        message = Message("@" + username + ", " + line_pickers.get("greetings").get_line() + " peepoHappy",
                          MessageType.SPECIAL)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)
        return True
    return False


@command
@unwrap_command_args
def eight_ball(bot, args, msg, username, channel):
    msg = msg.lower()
    if "!8ball" in msg or "!eightball" in msg:
        message = Message("@" + username + " " + line_pickers.get("8ball").get_line(), MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)
        return True


@command
@unwrap_command_args
def dance(bot, args, msg, username, channel):
    msg = msg
    if contains_word(msg, [" ludwigGun "]) and bot.limiter.can_send("dance", 25, True):
        message = Message("pepeD " * random.randint(1, 9), MessageType.SPAM)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def quote(bot, args, msg, username, channel):
    msg = msg
    username = username
    if is_word(msg, ["!inspire"]):
        message = Message("@" + username + ", " + line_pickers.get("quotes").get_line(), MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def iamhere(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_all(msg, ["who", "is", "here"]):
        message = Message("I am here peepoPog", MessageType.SPECIAL)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def respond(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, ["@lonewulfx6", "lonewulfx6"]):
        message = Message("@" + username +
                          ", Beep Boop MrDestructoid"
                          , MessageType.SPAM)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def lacking(bot, args, msg, username, channel):
    msg = msg.lower()
    channel = channel
    if msg == "!lacking":
        amount = bot.state.get(channel + "lacking", "0")
        message = Message("@" + username + ", " + amount + " people have been caught lacking PepeLaugh",
                          MessageType.SPECIAL)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def aniki(bot, args, msg, username, channel):
    msg = msg.lower()
    if msg == "!aniki":
        message = Message("Sleep tight PepeHands", MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def pickup(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, ["!pickup", "!pickupline", "!pickups", "!pickuplines"]):
        message = Message("@" + username + ", " + line_pickers.get("pickups").get_line(), MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def joke(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_word(msg, ["!joke", "!jokes", " give me a joke "]):
        message = Message("@" + username + ", " + line_pickers.get("jokes").get_line(), MessageType.COMMAND)
        message = change_if_blacklisted(bot, username, message)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def weird_jokes(bot, args, msg, username, channel):
    msg = msg.lower()
    if contains_all(msg, ["slime", "piss"]) \
            or contains_all(msg, ["slime", "pee"]) \
            or contains_all(msg, ["bus", "lud"]) \
            or contains_all(msg, ["bus", "hit"]):
        message = Message("@" + username + ", FeelsWeirdMan", MessageType.SPAM)
        bot.send_message(channel, message)


@command
@unwrap_command_args
def suicune(bot, args, msg, username, channel):
    msg = msg.lower()
    if "!suicune" == msg:
        if bot.limiter.can_send("suicune", 5, True):
            message = Message("bitch", MessageType.COMMAND)
            message = change_if_blacklisted(bot, username, message)
            bot.send_message(channel, message)


@command
@unwrap_command_args
def spam(bot, args, msg, username, channel):
    msg = msg.lower()
    if "!spam" == msg:
        if bot.limiter.can_send("spam", 5, True):
            message = Message("not cool peepoWTF", MessageType.COMMAND)
            message = change_if_blacklisted(bot, username, message)
            bot.send_message(channel, message)


@command
@unwrap_command_args
def validate_emotes(bot, args, msg, username, channel):
    msg = cleanup(msg)
    channel = channel
    words = msg.split()
    emotes = bot.emotes["all_emotes"]
    wrong_emotes = []
    for word in words:
        lowered_word = word.lower()
        if lowered_word in bot.emotes:
            correct_emote = bot.emotes.get(lowered_word)
            if word != correct_emote and not dictionary.check(word):
                bot.update_db(channel, word, correct_emote)
                wrong_emotes.append(word)
        else:
            val = validate_emote(word, emotes)
            if not val.boolean:
                if not dictionary.check(word):
                    bot.update_db(channel, word, val.correct)
                    wrong_emotes.append(word)
    if len(wrong_emotes) != 0:
        amount = bot.state.get(channel + "lacking", "0")
        bot.state[channel + "lacking"] = str(int(amount) + len(wrong_emotes))
        txt = " ".join(wrong_emotes)
        message = Message("@" + username + ", " + txt + " PepeLaugh", MessageType.SPAM)
        bot.send_message(channel, message)

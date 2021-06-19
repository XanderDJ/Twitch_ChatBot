from twitchchat import TwitchChat
from credentials.credentials import *
import sys
import logging

args = sys.argv
if len(args) < 2:
    print("you need to add a streamer or multiple streamers in the commandline")
else:
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    twitch_irc = TwitchChat(username, admin, oauth, [streamer for streamer in args[1:]])
    twitch_irc.start()
    twitch_irc.join()

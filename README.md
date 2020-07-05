# Synopsis

A twitch chat bot with multiple features based on Shughes-uk initial structure.
When run it joins twitch channels given in the commandline.
Commandline driven. (save, stop, join, leave, reload, toggle (type), send, state, db)
Allows toggling of specific command types.
Types defined:
* Functional (Can't be toggled)
* Command (Regular commands)
* Helpful ( Actions that the bot take that aren't specifically commands but are reactionary to incoming messages. I.e. Saying bye to people saying bye in chat, or saying good night to people in chat)
* Spam (All actions that can spam the chat. Specifically correcting twitch chat users that misspell/miscapitalise an emote)
* Special (Functions you find more important than the other types)
* Blacklisted (Users trying to use command get ludwigSpectrum as a response)
* Chat (used for sending messages with bot through commandline)

Bot uses a state to keep certain data. Whatever you toggled will be remembered if bot closed normally before.

# Tracking
Bot now tracks all misspelled emotes and stores them every 10 minutes in a mongodb.
This functionality is implemented in commands.py and can be removed if there is no desire to track these stats.

# Usage
```python
from twitchchat import TwitchChat
from credentials import * #You need to create credentials.py and define username, oauth and admin in it
import logging



logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
tirc = TwitchChat(username, admin,  oauth, ['geekandsundry', 'riotgames'])
tirc.start()
tirc.join()
```

# Commands
Adding commands is done in commands.py. With usage of decorators it's now very easy to add a new command. The signature of the command needs to have five arguments (bot, args, msg, username, channel).
Alongside the decorators.

## Decorators
- notice : Used for USERNOTICE messages. (don't use unwrap decorator)
- admin : used for commands that can only be run by the defined admin in credentials.py
- command : Used for commands that everybody can use. 
- unwrap_command_args : this decorator takes bot and args and gets the msg, username and channel out of args. 
Convenience decorator so you can use msg, username, channel immediately without needing to get it out of the dictionary.
Needed for both admin and command decorator (put this decorator beneath the two mentioned).

## Example:
```python
@command
@unwrap_command_args
def new_command(bot, args, msg, username, channel):
    pass
```

# Utility
The utility package contains some utility functions and classes used by both commands.py and twitchchat.py.

# State and db
The bot uses a state to determine which type of messages it can send and how many people have been caught misspelling emotes.
It stores this state in a txt file calle global_state.txt . It loads this text file when it boots up and creates it if it hasn't been made yet.
Everything is used with default parameters so on first bootup when nothings has been toggled yet all types automatically can get send and the amount of lackers will be defaulted to 0
. 

The temp_db field of TwitchChat stores all misspelled emotes. Every 10 minutes this db gets stored in a mongodb and then cleared. This prevents memory consumption.
The db looks like this:
```
{ (channel_name) : {
    (correct_emote_name) : {
        "spelling" : (misspelled_emote),
        "count" : (count),
        "timestamp" : (time.time())
        }
    }
}
```

# Texts
The texts directory contains texts files that the bot uses as responses to commands. 
Commands can use this by loading a RandomLinePicker with the associated text file 
and then calling get_line() on the linepicker. For convenience all linepickers are stored in line_pickers in commands.py
this way any command can access them and they all use the same memory (no multiple objects using the same text file)


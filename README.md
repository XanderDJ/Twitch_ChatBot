# Synopsis

A twitch chat bot with multiple features based on Shughes-uk initial structure.
When run it joins twitch channels given in the commandline.
Commandline driven. (save, stop, join, leave, toggle, toggle (type))
Allows toggling of specific command types.
Types defined:
* Functional (Can't be toggled)
* Command (Regular commands)
* Helpful ( Actions that the bot take that aren't specifically commands but are reactionary to incoming messages. I.e. Saying bye to people saying bye in chat, or saying good night to people in chat)
* Spam (All actions that can spam the chat. Specifically correcting twitch chat users that misspell/miscapitalise an emote)
* Special (Functions you find more important than the other types)

If toggle is entered then no message will ever be sent (THis breaks the bot as it doesn't respond to ping anymore) 

Bot uses a state to keep certain data. Whatever you toggled will be remembered if bot closed normally before.

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

#Future
- Whatever functionality I desire to add. 
- Organise adding new commands in a more clean way.

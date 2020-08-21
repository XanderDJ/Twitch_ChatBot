# This folder needs to contain two python files

## credentials.py
This file needs to hold three variables.
* oauth = (oauth token)
* username = (bot name)
* admin = (admin name)

## api_credentials.py
This is used to interact with the twitch api to get channels status and game they're playing. If you don't feel
comfortable storing your client secret wherever you host this 
then you should remove self.twitch_status from twitchchat.chat.TwitchChat.__init__()

This file needs to hold two parameters.
* client_id = (your twitch client id)
* secret = (your twitch client secret)

## mongo_credentials.py
This is used to connect to the mongo database, connections need to be authenticated so you can use the mongodb outside of the vps

* user = (user)
* pwd = (pwd)
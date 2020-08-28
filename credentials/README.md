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

## user_token.txt

Because of a rule in a channel my bot uses I need to check if the bot is subscribed or not. To be able to check this with the API you need a user access token and not an app bearer token.
This means that you need to manually authorize a user token with the API. I stored this token in this txt file. 
It is possible to set up this token to automatically refresh when it expires without having to go to the browser.
This allows us to do it once post it in the file and be done with it, If you don't need to know if the bot is subscribed or not then you don't need this
 txt file and you can delete functions in utility.classes.TwitchStatus
 
 user_token.txt contents:
{access_token:(access_token),refresh_token:(refresh_token)}
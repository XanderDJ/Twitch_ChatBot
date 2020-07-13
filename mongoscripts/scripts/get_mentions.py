from mongoscripts import client

twitch_db = client["twitch"]
mentions = twitch_db["mentions"]
for doc in mentions.find({}):
    username = doc["username"]
    message = doc["message"]
    timestamp = doc["timestamp"]
    print(timestamp)

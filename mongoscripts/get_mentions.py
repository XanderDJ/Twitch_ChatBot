import pymongo
import datetime
client = pymongo.MongoClient("mongodb://localhost:27017/")
twitch_db = client["twitch"]
mentions = twitch_db["twitch"]
for doc in mentions.find({}):
    username = doc["user"]
    message = doc["message"]
    timestamp = doc["timestamp"]
    print(username + ": " + message + " at " + timestamp)

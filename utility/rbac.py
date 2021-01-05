from utility import file_loader as f
from utility.classes import LockedData
from credentials import mongo_credentials
from datetime import datetime
import pymongo

ROLES = {}
users = LockedData(f.load("texts/user_roles.txt", {}))


def addRole(role):
    global ROLES

    def add_role_inner(func):
        if role not in ROLES:
            ROLES[role] = []
        ROLES[role].append(func)
        return func

    return add_role_inner


def get_roles(user, channel):
    global users

    def get_roles_inner(db, kwargs):
        if "user" in kwargs and "channel" in kwargs:
            if user in db:
                return db.get(kwargs.get("user")).get(kwargs.get("channel"), [])
            else:
                return []

    return users.access(get_roles_inner, user=user, channel=channel)


def has_roles(user, channel):
    global users

    def has_roles_inner(db, kwargs):
        if "user" in kwargs and "channel" in kwargs:
            user = kwargs.get("user")
            channel = kwargs.get("channel")
            if user in db:
                if channel in db.get(user) and len(db.get(user).get(channel)) != 0:
                    return True
            return False

    return users.access(has_roles_inner, user=user, channel=channel)


def get_allowed_functions(user, channel):
    roles = get_roles(user, channel)
    funcs = []
    for role in roles:
        if role in ROLES:
            funcs.extend(ROLES.get(role))
    return funcs


def add_role(user, role, channel):
    global users

    def add_role_inner(data, kwargs):
        if "user" in kwargs and "channel" in kwargs and "role" in kwargs:
            user = kwargs.get("user")
            channel = kwargs.get("channel")
            role = kwargs.get("role")
            if user not in data:
                data[user] = {}
            if channel not in data.get(user):
                data[user][channel] = []
            if role not in data.get(user).get(channel):
                data[user][channel].append(role)

    users.access(add_role_inner, user=user, channel=channel, role=role)


def remove_role(user, role, channel):
    global users

    def remove_role_inner(data, kwargs):
        if "user" in kwargs and "channel" in kwargs and "role" in kwargs:
            user = kwargs.get("user")
            channel = kwargs.get("channel")
            role = kwargs.get("role")
            if user in data:
                if channel in data.get(user, {}):
                    if role in data.get(user).get(channel, []):
                        data[user][channel].remove(role)

    users.access(remove_role_inner, user=user, channel=channel, role=role)


client = pymongo.MongoClient("mongodb://{}:{}@127.0.0.1:27017/".format(mongo_credentials.user, mongo_credentials.pwd))


def log_access(args, channel):
    args["timestamp"] = datetime.utcnow()
    twitch = client["twitch"]
    col = twitch[channel]
    try:
        col.insert_one(args)
    except Exception:
        pass

from utility import file_loader as f
from utility.classes import LockedData

ROLES = {}
users = LockedData(f.load("texts/user_roles.txt"), {})


def addRole(role):
    def add_role_inner(func):
        if role not in ROLES:
            ROLES[role] = []
        ROLES[role].append(func)
        return func

    return add_role_inner()


def get_roles(user, channel):
    def get_roles_inner(db, kwargs):
        if "user" in kwargs and "channel" in kwargs:
            return db.get(kwargs.get("user")).get(kwargs.get("channel"))

    return users.access(get_roles_inner, user=user, channel=channel)


def has_roles(user, channel):
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
    pass


def remove_role(user, role, channel):
    pass

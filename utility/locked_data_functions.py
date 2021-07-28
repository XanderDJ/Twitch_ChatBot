def write_to_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct[kwargs.get("key")] = kwargs.get("val")


def get_val(dct, kwargs):
    if "key" in kwargs:
        return dct.get(kwargs.get("key"))


def delete_from_dict(dct, kwargs):
    if "key" in kwargs and kwargs.get("key") in dct:
        return dct.pop(kwargs.get("key"))


def delete_from_set(st, kwargs):
    if "elem" in kwargs:
        elem = kwargs.get("elem")
        if elem in st:
            st.remove(elem)


def delete_from_list(lst, kwargs):
    if "elem" in kwargs:
        if kwargs.get("elem") in lst:
            lst.remove(kwargs.get("elem"))


def add_to_container(container, kwargs):
    if "elem" in kwargs:
        elem = kwargs.get("elem")
        if isinstance(container, list):
            container.append(elem)
        elif isinstance(container, set):
            container.add(elem)
        else:
            pass


def contains(container, kwargs):
    if "elem" in kwargs:
        return kwargs.get("elem") in container
    return False


def append_to_list_in_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct[kwargs.get("key")] = dct.get(kwargs.get("key"), [])
        dct.get(kwargs.get("key")).append(kwargs.get("val"))


def delete_from_list_in_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        key = kwargs.get("key")
        val = kwargs.get("val")
        dct[key] = dct.get(key, [])
        dct.get(key).remove(val)


def list_in_dict_contains(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        key = kwargs.get("key")
        val = kwargs.get("val")
        return val in dct.get(key)
    return False

def update_streak_inner(dct, kwargs):
    if "emotes" in kwargs and "channel" in kwargs:
        channel = kwargs.get("channel")
        emotes = kwargs.get("emotes")
        dct[channel] = dct.get(channel, {})
        for emote in emotes:
            if emote not in dct[channel]:
                dct[channel][emote] = {"current": "0", "max": "0"}
        for emote, streak in dct[channel].items():
            if emote in emotes:
                streak["current"] = str(int(streak.get("current")) + 1)
            elif int(streak["current"]) > int(streak["max"]):
                streak["max"] = streak["current"]
                streak["current"] = "0"
            else:
                streak["current"] = "0"


def reset_streak_inner(dct, kwargs):
    if "emote" in kwargs and "channel" in kwargs:
        emote = kwargs.get("emote")
        channel = kwargs.get("channel")
        print(emote)
        if emote in dct[channel]:
            print("trying to reset")
            dct[channel][emote]["max"] = "0"


def get_data(data, kwargs):
    return data


def add_loss(data, kwargs):
    if "user" in kwargs:
        user = kwargs.get("user")
        (wins, losses, ties) = data.get(user, ("0", "0", "0"))
        data[user] = (wins, str(int(losses) + 1), ties)


def add_win(data, kwargs):
    if "user" in kwargs:
        user = kwargs.get("user")
        (wins, losses, ties) = data.get(user, ("0", "0", "0"))
        data[user] = (str(int(wins) + 1), losses, ties)


def add_tie(data, kwargs):
    if "user" in kwargs:
        user = kwargs.get("user")
        (wins, losses, ties) = data.get(user, ("0", "0", "0"))
        data[user] = (wins, losses, str(int(ties) + 1))

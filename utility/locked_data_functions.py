def write_to_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct[kwargs.get("key")] = kwargs.get("val")


def get_val(dct, kwargs):
    if "key" in kwargs:
        return dct.get(kwargs.get("key"))


def delete_from_dict(dct, kwargs):
    if "key" in kwargs:
        return dct.pop(kwargs.get("key"))


def delete_from_set(st, kwargs):
    if "elem" in kwargs:
        elem = kwargs.get("elem")
        st.remove(elem)


def delete_from_list(lst, kwargs):
    if "elem" in kwargs:
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


def append_to_list_in_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct.get(kwargs.get("key")).append(kwargs.get("val"))


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
            elif streak["current"] > streak["max"]:
                streak["max"] = streak["current"]
                streak["current"] = "0"
            else:
                streak["current"] = "0"

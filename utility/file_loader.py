def save(obj, fp: str, pretty=True):
    try:
        for item in obj:
            break
    except TypeError as e:
        print(e)
    else:
        txt = to_pretty_txt(obj) if pretty else to_txt(obj)
        fh = open(fp, "w+")
        fh.write(txt)
        fh.flush()
        fh.close()


def load(fp: str, default=None):
    try:
        fh = open(fp, "r")
    except FileNotFoundError:
        fh = open(fp, "w+")
        fh.close()
        fh = open(fp, "r")
    txt = clean_txt("".join(fh.readlines()))
    fh.close()
    obj = from_text(txt)
    if obj is None and default is not None:
        return default
    return obj


def to_txt(obj):
    txt = ""
    if isinstance(obj, list):
        items = iterable_to_strings(obj)
        txt += "["
        txt += ",".join(items)
        txt += "]"
        return txt
    elif isinstance(obj, tuple):
        items = iterable_to_strings(obj)
        txt += "("
        txt += ",".join(items)
        txt += ")"
        return txt
    elif isinstance(obj, set):
        items = iterable_to_strings(obj)
        txt += "{["
        txt += ",".join(items)
        txt += "]}"
        return txt
    elif isinstance(obj, dict):
        items = []
        for key, val in obj.items():
            items.append(str(key) + ":" + to_txt(val))
        txt += "{"
        txt += ",".join(items)
        txt += "}"
        return txt
    else:
        return str(obj)


def to_pretty_txt(obj):
    txt = ""
    if isinstance(obj, list):
        items = iterable_to_strings(obj, True)
        txt += "[\n"
        txt += ",\n".join(items)
        txt += "\n]"
        return txt
    elif isinstance(obj, tuple):
        items = iterable_to_strings(obj, True)
        txt += "(\n"
        txt += ",\n".join(items)
        txt += "\n)"
        return txt
    elif isinstance(obj, set):
        items = iterable_to_strings(obj, True)
        txt += "{[\n"
        txt += ",\b".join(items)
        txt += "\n]}"
        return txt
    elif isinstance(obj, dict):
        items = []
        for key, val in obj.items():
            items.append(" " * 4 + str(key) + ":" + to_txt(val))
        txt += "{\n"
        txt += ",\n".join(items)
        txt += "\n}"
        return txt
    else:
        return str(obj)


def iterable_to_strings(iterable, pretty=False):
    items = []
    for item in iterable:
        txt = to_txt(item) if not pretty else " " * 4 + to_txt(item)
        items.append(txt)
    return items


def clean_txt(txt):
    return "".join(char for char in txt if char not in [" ", "\n", "\t"])


def from_text(txt):
    if len(txt) == 0:
        return
    bracket = txt[0]
    content = txt[1:-1]
    if bracket == "[":
        # list
        lst = []
        list_items = all_items(content)
        for item in list_items:
            lst.append(from_text(item))
        return lst
    elif bracket == "(":
        # tuple
        lst = []
        list_items = all_items(content)
        for item in list_items:
            lst.append(from_text(item))
        return tuple(lst)
    elif bracket == "{":
        # set or dict
        if len(content) != 0 and content[0] == "[":
            # set
            content = content[1:-1]
            st = set()
            for item in all_items(content):
                st.add(from_text(item))
            return st
        else:
            # dict
            dct = {}
            for item in all_items(content):
                # Items should be in shape of (key):(possible iterable or txt)
                key, value = item.split(":", maxsplit=1)
                dct[key] = from_text(value)
            return dct
    else:
        # not an iterable
        return txt


def all_items(txt):
    brackets_open = 0
    items = []
    item = ""
    for char in txt:
        if brackets_open == 0:
            if char not in ["{", "[", "("]:
                if char == ",":
                    items.append(item)
                    item = ""
                else:
                    item += char
            else:
                item += char
                brackets_open += 1
        else:
            if char in ["}", ")", "]"]:
                brackets_open -= 1
            if char in ["{", "[", "("]:
                brackets_open += 1
            item += char
    if len(item) != 0:
        items.append(item)
    return items

def write_to_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct[kwargs.get("key")] = kwargs.get("val")


def get_val(dct, kwargs):
    if "key" in kwargs:
        return dct.get(kwargs.get("key"))


def delete_from_dict(dct, kwargs):
    if "key" in kwargs:
        return dct.pop(kwargs.get("key"))


def delete_from_list(lst, kwargs):
    if "elem" in kwargs:
        lst.remove(kwargs.get("elem"))


def append_to_list(lst, kwargs):
    if "elem" in kwargs:
        lst.append(kwargs.get("elem"))


def contains(container, kwargs):
    if "elem" in kwargs:
        return kwargs.get("elem") in container


def append_to_list_in_dict(dct, kwargs):
    if "key" in kwargs and "val" in kwargs:
        dct.get(kwargs.get("key")).append(kwargs.get("val"))

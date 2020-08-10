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

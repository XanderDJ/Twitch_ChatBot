import re


def loadToDictionary(path):
    try:
        file = open(path, 'r')
    except Exception as e:
        file = open(path, 'w+')
    file.close()
    match = re.compile("^(.*) : (.*)$")
    dictionary = {}
    f = open(path, "r")
    for line in f:
        regex = match.match(line.rstrip())
        dictionary[regex.group(1)] = regex.group(2)
    f.close()
    return dictionary


def loadToText(dct, path):
    txt = open(path, "w+")
    for key, value in dct.items():
        value = str(value)
        txt.write(key + " : " + value + "\n")
    txt.close()


def set_to_txt(s, path):
    txt = open(path, "w+")
    for item in s:
        value = str(item)
        txt.write(value + "\n")
    txt.close()


def txt_to_set(path):
    try:
        file = open(path, 'r')
    except Exception as e:
        file = open(path, 'w+')
    file.close()
    txt = open(path, "r")
    s = set()
    for line in txt:
        s.add(line.rstrip())
    txt.close()
    return s
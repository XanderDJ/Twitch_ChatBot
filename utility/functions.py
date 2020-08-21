import string
import utility.classes as c


def contains_word(msg, words):
    for word in words:
        if word in " " + msg + " ":
            return True
    return False


def contains_all(msg, words):
    for word in words:
        if word not in " " + msg + " ":
            return False
    return True


def is_word(msg, words):
    for word in words:
        if msg == word:
            return True
    return False


def convert(boolean: str) -> bool:
    if boolean == "True":
        return True
    return False


def hammington(str1, str2):
    len1 = len(str1)
    len2 = len(str2)
    if len1 == 0 or len2 == 0:
        return max(len1, len2) + 1
    str1 = str1.lower()
    str2 = str2.lower()
    smallest = min(len1, len2)
    starting_dist = abs(len1 - len2)
    if str1[0] != str2[0] or str1[0:smallest] == str2[0:smallest]:
        starting_dist += 3
    for i in range(smallest):
        if str1[i] != str2[i]:
            starting_dist += 1
    return starting_dist


def is_anagram(w1: str, w2: str):
    if len(w1) != len(w2):
        return False
    w1 = sorted(w1.lower())
    w2 = sorted(w2.lower())
    if w1 == w2:
        return True
    return False


punctuation = string.punctuation.replace("'", "") + "”"


def cleanup(word: str):
    return word.translate(str.maketrans('', '', punctuation))


def word_pyramid(count, emote_list):
    iterable = iter(c.CircularArray(emote_list))
    pyramid = []
    text = ""
    for i in range(count):
        text = next(iterable) + " " + text
        pyramid.append(text)
    for i in range(len(pyramid) - 2, -1, -1):
        pyramid.append(pyramid[i])
    return pyramid


def count_capitals(text: str):
    count = 0
    for char in text:
        if char.isupper():
            count += 1
    return count

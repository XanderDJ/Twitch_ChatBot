from enum import Enum
from random import randint


class RPS(Enum):
    ROCK = 1
    SCISSORS = 2
    PAPER = 3

    def beats(self):
        if self == RPS.ROCK:
            return RPS.SCISSORS
        elif self == RPS.PAPER:
            return RPS.ROCK
        else:
            return RPS.PAPER

    def __str__(self):
        if self == RPS.ROCK:
            return "ROCK"
        elif self == RPS.SCISSORS:
            return "SCISSORS"
        else:
            return "PAPER"


class Outcome(Enum):
    LOST = 1
    TIE = 2
    WON = 3


def get_RPS_object(value):
    if value == "r" or value == "rock":
        return RPS.ROCK
    elif value == "p" or value == "paper":
        return RPS.PAPER
    elif value == "s" or value == "scissors":
        return RPS.SCISSORS


def play_rps(symbol: RPS) -> (Outcome, RPS):
    random_symbol = randint(1, 3)
    bot_symbol = RPS(random_symbol)
    if bot_symbol.beats() == symbol:
        return Outcome.LOST, bot_symbol
    elif symbol.beats() == bot_symbol:
        return Outcome.WON, bot_symbol
    else:
        return Outcome.TIE, bot_symbol

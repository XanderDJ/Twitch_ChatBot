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


class TicTacToe:
    def __init__(self):
        self.p1 = ""
        self.p2 = ""
        self.active = False
        self.x = "x"
        self.o = "o"
        self.board = [["_" for i in range(3)] for i in range(3)]
        self.current = 0
        self.waiting_for = ""

    def get_board(self):
        return [" ".join(row) for row in self.board]

    def pick(self, user, row, col):
        row -= 1
        col -= 1
        if not self.is_valid_pick(row, col):
            return False
        if self.current % 2 == 0:
            if user == self.p1:
                self.board[row][col] = self.x
                self.current += 1
                return True
            return False
        else:
            if user == self.p2:
                self.board[row][col] = self.o
                self.current += 1
                return True
            return False

    def is_valid_pick(self, row, col):
        if 0 <= row < 3 and 0 <= col < 3 and self.board[row][col] == "_":
            return True
        return False

    def won(self):
        # Check row
        for row in self.board:
            if "x" in row and "o" not in row and "_" not in row:
                return True, self.p1
            elif "o" in row and "x" not in row and "_" not in row:
                return True, self.p2
        # check column
        for i in range(len(self.board)):
            col = [self.board[i][col] for col in range(3)]
            if "x" in col and "o" not in col and "_" not in col:
                return True, self.p1
            elif "o" in col and "x" not in col and "_" not in col:
                return True, self.p2

        # check diagonal
        diagonal1 = [self.board[i][i] for i in range(3)]
        diagonal2 = [self.board[i][2 - i] for i in range(3)]
        if "x" in diagonal1 and "o" not in diagonal1 and "_" not in diagonal1:
            return True, self.p1
        elif "o" in diagonal1 and "x" not in diagonal1 and "_" not in diagonal1:
            return True, self.p2

        if "x" in diagonal2 and "o" not in diagonal2 and "_" not in diagonal2:
            return True, self.p1
        elif "o" in diagonal2 and "x" not in diagonal2 and "_" not in diagonal2:
            return True, self.p2

        return False, ""

    def tie(self):
        (won, player) = self.won()
        if self.current > 8 and not won:
            return True
        return False

    def reset(self):
        self.p1 = ""
        self.p2 = ""
        self.active = False
        self.current = 0
        self.waiting_for = ""
        self.board = [["_" for i in range(3)] for i in range(3)]
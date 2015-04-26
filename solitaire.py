import functools
import logging
import os
import random
import sys

from argparse import ArgumentParser
from collections import namedtuple
from copy import deepcopy

log = logging.getLogger(__name__)

VALUES = ['A',2,3,4,5,6,7,8,9,10,'J','Q','K']
SUITS = {'red' : ('H', 'D'), 'black': ('C', 'S') }

TURN_MESSAGE = [ "",
    "[D]raw from the draw pile",
    "[P]lay from the draw pile",
    "[M]ove from the stacks", 
    "[S]ave the board",
    "Res[T]ore previous state", "",
]

class InvalidCard(Exception):
    pass

class InvalidInput(Exception):
    pass

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def clear_screen():
    os.system('clear')

def refresh_view(func):
    def inner(self, *args, **kwargs):
        clear_screen()
        if not self.board.draw_pile.revealed_set.cards and self.board.draw_pile.discards:
            self.board.draw_iterator.next()
        print(self.board)
        result = func(self, *args, **kwargs)
        clear_screen()
        print(self.board)
        return result
    return inner

class Test(object):
    def __init__(self, func, err_message):
        self.func = func
        self.err = err_message

    def __call__(self, x):
        if not self.func(x):
            return True
        result = self.func(x)
        if not result:
            raise InvalidInput(self.err)
        return result


class Message(object):
    def __init__(self, message, join="\n"):
        self.message = message
        self.join = join

    def __str__(self):
        if not isinstance(self.message, basestring):
            return self.join.join(self.message)
        return str(self.message)

def enumerate_deck(deck):
    enums = []
    index = 1
    for card in deck.cards:
        if not card.face_up:
            enums.append('  ')
        else:
            string_len = len(card.name)
            enums.append("%{}s".format(string_len) % index)
            index += 1
    return ", ".join(enums)

class PlayerChoice(object):
    def __init__(self, message, board, type=str, test=lambda x: True):
        self.message = message
        self.board = board
        self.type = type
        self.test = test

    def __enter__(self):
        option = self.get_option()
        log.debug("Got player input: {}".format(option))
        while not self.validated(option):
            option = self.get_option()
        if option is None:
            return
        return self.transform(option)

    def __exit__(self, type, value, traceback):
        pass

    @refresh_view
    def get_option(self):
        value = raw_input(str(self.message))
        log.debug("Player chose: '%s'", value)
        if value == "":
            log.debug("Player did not enter a choice.")
            return None
        return self.type(value)

    def validated(self, option):
        if option is None:
            log.debug("Cannot validate 'None'.")
            return True 
        try:
            log.debug("Validating input {} against {}".format(option, self.test))
            result = self.test(option)
            log.debug("Test result: {}".format(result))
            return self.test(option)
        except InvalidInput as e:
            log.error(e.message)
            return False

    @refresh_view
    def transform(self, option):
        return option



is_valid_stack = lambda x: 0 <= x <= 6
is_valid_victory = lambda x: 0 <= x <= 2
def is_valid_selection(x, y=1):
    return 0 <= x <= y

ValidateStack = Test(is_valid_stack, "Must be an integer in [0-6]! ")
ValidateVictory = Test(is_valid_victory, "Must be an interger in [0-3]")
InvalidPile = Test(lambda x: False, "Pile must be 'S' or 'V'")

PileDefinition = namedtuple('PileDefinition', ['test', 'pile'])

def get_enumerated_index(deck, enum_choice):
    transform = len(deck.face_up_cards) - enum_choice
    transform += 1
    return -transform

class PileChoice(PlayerChoice):
    def __init__(self, board, signifier="", active_cards=None):
        self.pile = None
        message = Message([
            "Active Cards: {}".format(active_cards),
            "Choose a {} stack, including 's', or 'v': ".format(signifier),
        ])
        super(PileChoice, self).__init__(message, board)
        self.pile_definitions = {
            'S' : PileDefinition(ValidateStack, self.board.stacking_decks),
            'V' : PileDefinition(ValidateVictory, self.board.victory_decks),
        }

    def transform(self, option):
        if option is None:
            return
        return self.pile.cards[-option]

    def define_from_pile_type(self, pile_type):
        definition = self.pile_definitions[pile_type]
        self.test = definition.test
        self.pile = definition.pile

    def get_option(self):
        option = super(PileChoice, self).get_option()
        if option is None:
            return

        pile_type = option[0].upper()

        try:
            self.define_from_pile_type(pile_type)
        except IndexError:
            self.test = InvalidPile
        try:
            return int(option[1:])
        except ValueError:
            return None

    def transform(self, option):
        return self.pile[option]


class CardChoice(PlayerChoice):
    def __init__(self, deck, board, signifier=""):
        self.deck = deck
        self.max_choice = len(deck.face_up_cards)-1
        message = Message([
            str(deck),
            enumerate_deck(deck),
            "Select card {} from [0-{}]".format(signifier, self.max_choice)
        ])

        test = Test(functools.partial(is_valid_selection,y=self.max_choice),
                    "Must be an integer in [0-{}]!".format(self.max_choice))

        super(CardChoice, self).__init__(message=message, board=board, type=int, test=test)

    def get_option(self):
        if not self.max_choice:
            log.debug("Only one option available. Choosing it.")
            return 1
        try:
            return super(CardChoice, self).get_option()            
        except ValueError:
            raise InvalidInput

    def transform(self, option):
        if option is None:
            return
        i = get_enumerated_index(self.deck, option)
        return self.deck.cards[i]


def create_standard_deck():
    deck = Deck()
    for suits in SUITS.values():
        for suit in suits:
            for value in VALUES:
                deck.add(Card(suit, value))
    return deck


class Card(object):
    def __init__(self, suit, value, face_up=False):
        self.suit = suit
        self.value = value
        self.value_index = VALUES.index(self.value)
        self.face_up = face_up

    @property
    def name(self):
        return "{}{}".format(self.value, self.suit)

    def __cmp__(self, other):
        if self.value_index < other.value_index:
            return -1
        elif self.value_index > other.value_index:
            return 1
        return 0

    def __eq__(self, other):
        return self.value == other.value and self.suit == other.suit

    @property
    def color(self):
        if self.suit in SUITS['black']:
            return bcolors.OKBLUE
        return bcolors.FAIL

    def __str__(self):
        if self.face_up:
            return "{}{}{}".format(self.color, self.name, bcolors.ENDC)
        return "??"

    def __add__(self, number):
        return Card(self.suit, VALUES[self.value_index+1])

    def __sub__(self, number):
        next_value_index = self.value_index-1
        next_value = VALUES[next_value_index]
        log.debug("My value is %s [index %d]. Sub-1 value = %s [index %d]",self.value,
                                                                            self.value_index,
                                                                            next_value_index,
                                                                            next_value)
        return Card(self.suit, next_value)


class Deck(object):
    def __init__(self, cards=None):
        self.cards = cards or []
        self.name = "Deck"

    def __nonzero__(self):
        return bool(self.cards)

    def __str__(self):
        return ", ".join([str(c) for c in self.cards])

    def __eq__(self, other):
        if not isinstance(other, Deck):
            return False
        return self.cards == other.cards

    def __len__(self):
        return len(self.cards)

    @property
    def face_up_cards(self):
        return filter(lambda c: c.face_up, self.cards)

    def flip(self):
        for card in self.cards:
            card.face_up = not card.face_up

    def add(self, card):
        if isinstance(card, Deck):
            self.cards.extend(card.cards)
        else:
            self.cards.append(card)

    def draw(self):
        return self.cards.pop(-1)

    def must_have(self, card):
        if card not in self.cards:
            raise InvalidCard('{} is not in deck {}!"'.format(card, self))

    def shuffle(self):
        random.shuffle(self.cards)

    def split_after(self, card, include=True):
        """Returns a new deck from [n..x], where 'n' is:
                - {card} if 'include' is True
                - {card + 1} otherwise
            and 'x' is the end of the deck.
        """
        self.must_have(card)
        index = self.cards.index(card)
        if not include:
            index += 1
        new = self.__class__(cards=self.cards[index:])
        self.cards = self.cards[:index]
        return new

    def split_before(self, card, include=True):
        """Returns a new deck from [0..n], where 'n' is:
                - {card} if 'include' is True
                - {card - 1} otherwise
        """
        self.must_have(card)

        index = self.cards.index(card)
        if not include:
            index -= 1

        new = self.__class__(self.cards[:index+1])
        self.cards = self.cards[index+1:]
        return new


class VictoryDeck(Deck):
    def add(self, card):
        if isinstance(card, Deck):
            card = card.cards[0]
        if not self.cards: 
            if card.value == 'A':
                self.cards.append(card)
            else:
                raise InvalidCard("{} cannot start a victory deck! Only aces can do that!".format(card))

        elif self.cards[0].suit == card.suit and card.value == (self.cards[-1]+1).value:
            self.cards.append(card)
        else:
            raise InvalidCard("{} cannot be placed on top of {} in a victory deck!".format(card, self.cards[-1]))


class StackingDeck(Deck):
    def suit_can_stack(self, card):
        if self.cards[-1].suit in SUITS['red']:
            return card.suit in SUITS['black']
        return card.suit in SUITS['red']

    def value_can_stack(self, card):
        ideal_value = (self.cards[-1]-1).value
        log.debug("Looking for value: {}".format(ideal_value))
        return self.cards[-1].value != 'A' and card.value == ideal_value

    def can_stack(self, card):
        if not self.cards:
            return card.value == 'K'
        suit = self.suit_can_stack(card)
        value = self.value_can_stack(card)
        log.debug("Can suit stack? {}; Can value stack? {}".format(suit, value))
        return suit and value

    def add(self, card):
        if self.cards and not filter(lambda x: x.face_up, self.cards):
            self.cards.append(card)
            return
        if isinstance(card, Deck):
            log.debug("Attempting to add deck %s to %s", card, self)
            if self.can_stack(card.cards[0]):
                log.debug("Deck %s may be added to %s", card, self)
                self.cards.extend(card.cards)
            else:
                raise(InvalidCard("{} cannot be placed on top of {} in stacking decks!".format(card, self.cards[-1])))
        elif self.can_stack(card):
            log.debug("Card %s may be added to %s", card, self)
            self.cards.append(card)
        else:
            log.error("Cannot add!")
            raise InvalidCard('{} cannot be placed on top of {} in stacking decks!'.format(card, self.cards[-1]))
        log.debug("Added. Deck is now: %s", self)


class DrawPile(Deck):
    def __init__(self, max_loops=None, draw_pile_size=3, cards=None):
        super(DrawPile, self).__init__(cards)
        self.draw_pile_size = draw_pile_size
        if max_loops is None:
            max_loops = sys.maxint
        self.max_loops = max_loops

        self.discards = Deck()
        self.revealed_set = Deck()
        self.loops = 0

    @property
    def split_index(self):
        if not self.cards:
            log.debug("No cards left in main deck. Putting discards back in!")
            self.cards = self.discards.cards
        return min(self.draw_pile_size, len(self.cards))

    def reverse_revealed_set(self):
        for card in self.revealed_set.cards:
            card.face_up = not card.face_up
        self.revealed_set.cards.reverse()

    def __deepcopy__(self, memo):
        new = DrawPile(self.max_loops, self.draw_pile_size)
        new.cards = deepcopy(self.cards)
        new.discards = deepcopy(self.discards)
        new.revealed_set = deepcopy(self.revealed_set)
        new.loops = self.loops
        return new

    def __iter__(self):
        while self.cards or self.discards and self.loops < self.max_loops:
            log.debug("Adding {} to discards".format(self.revealed_set))
            if not self.revealed_set.cards and self.discards.cards:
                self.revealed_set = self.discards.split_after(self.discards.cards[-1], include=True)
            else:
                self.discards.add(self.revealed_set)
                if not self.cards:
                    self.discards.cards.reverse()
                    self.add(self.discards)
                    self.discards = Deck()
                    for card in self.cards:
                        card.face_up = False
                    self.loops += 1
                self.revealed_set = self.split_after(self.cards[-self.split_index], include=True)
                self.reverse_revealed_set()
            yield self.revealed_set


class Board(object):
    def __init__(self, max_loops, draw_pile_size):
        self.draw_pile = DrawPile(max_loops, draw_pile_size)
        self.draw_pile.add(create_standard_deck())
        self.draw_iterator = None
        self.draw_pile.shuffle()

        self.victory_decks = [VictoryDeck() for _ in range(4)]
        self.stacking_decks = []
        for i in range(7):
            deck_size = i + 1
            cards = [self.draw_pile.draw() for _ in range(deck_size)]
            self.stacking_decks.append(StackingDeck(cards))
        for deck in self.stacking_decks:
            if deck.cards:
                deck.cards[-1].face_up = True

    def __deepcopy__(self, memo):
        new = Board(self.draw_pile.max_loops, self.draw_pile.draw_pile_size)
        new.draw_pile = deepcopy(self.draw_pile)
        new.draw_iterator = iter(new.draw_pile)
        new.victory_decks = deepcopy(self.victory_decks)
        new.stacking_decks = deepcopy(self.stacking_decks)
        return new

    def __str__(self):
        output = []
        output.append(">>>>>> VICTORY DECKS:")
        for i, v in enumerate(self.victory_decks):
            output.append("V{}: {}".format(i, v))
        output.append("<<<<<< PLAY DECKS:")
        for i, s in enumerate(self.stacking_decks):
            output.append("S{}: {}".format(i, s))
        output.append("Current Draw Deck: {}".format(self.draw_pile.revealed_set))
        return "\n".join(output)

class Game(object):
    def __init__(self, max_loops, draw_pile_size):
        self.board = Board(max_loops, draw_pile_size)
        self.turns = 0
        self.moves = {
            'D' : self.draw_from_draw_pile, 
            'M' : self.move_from_stacks,
            'P' : self.play_from_draw_pile,
            'S' : self.save_board,
            'T' : self.restore_board,
        }

        self.board.draw_iterator = iter(self.board.draw_pile)

    @refresh_view
    def draw_from_draw_pile(self):
        self.board.draw_iterator.next()

    @refresh_view
    def move_from_stacks(self):
        with PileChoice(self.board, signifier="source") as source_stack:
            if source_stack is None:
                return
            with CardChoice(source_stack, self.board, "to move") as split_index:
                if split_index is None:
                    return
                temp_deck = source_stack.split_after(split_index, include=True)
                temp_deck = self.select_destination(temp_deck)
            if temp_deck:
                source_stack.add(temp_deck)

    @refresh_view
    def play_from_draw_pile(self):
        if not self.board.draw_pile.revealed_set.cards:
            self.draw_from_draw_pile()
        pile = self.board.draw_pile.revealed_set
        with PlayerChoice("Play {}? [y/n]: ".format(pile.cards[-1]), self.board, test=lambda x: bool(x) and x in ('yYnN')) as yes:
            if yes.upper() == 'Y':
                card = pile.split_after(pile.cards[-1], include=True)
                self.select_destination(card)

    def select_destination(self, active_cards):
        while True:
            with PileChoice(self.board, signifier="destination", active_cards=active_cards) as destination:
                if destination is None:
                    continue
                try:
                    log.debug("Adding %s to %s", active_cards, destination)
                    destination.add(active_cards)
                    break
                except InvalidCard as e:
                    print(e.message)
                except KeyError:
                    return active_cards

    @refresh_view
    def restore_board(self):
        self.board = self.backup

    @refresh_view
    def save_board(self):
        self.backup = deepcopy(self.board)

    @refresh_view
    def turn(self):
        print(self.board)
        with PlayerChoice(Message(TURN_MESSAGE), board=self.board) as choice:
            if not choice:
                return
            choice = choice[0].upper()
            try:
                self.moves[choice]()
            except KeyError:
                print("{} is not a valid choice!".format(choice))
            except InvalidInput:
                print("{} is not a valid choice!".format(choice))

    def play(self):
        self.save_board()
        while True: 
            self.turn()
            for deck in self.board.stacking_decks:
                if deck.cards:
                    deck.cards[-1].face_up = True
            victory = all([len(deck) == 13 for deck in self.board.victory_decks])
            if victory:
                print("YOU WIN!")
                break

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--debug", "-g", action="store_true", default=False)
    parser.add_argument("--draw-pile-size", type=int, default=3, action="store",
                        help="Choose your draw pile size.")
    parser.add_argument("--max-loops", type=int, default=None, action="store",
                        help="Maximum number of times to loop through the draw deck (default is infinite)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARN)
    game = Game(max_loops=args.max_loops, draw_pile_size=args.draw_pile_size)
    game.play()
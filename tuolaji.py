"""
拖拉机 Tuo La Ji (Sheng Ji / Tractor) — Complete Game Engine + GUI
=================================================================
2 decks, 4 players (2v2), trump suit + trump rank system.

FILE LAYOUT
───────────
  Card, Deck          — card model & shuffling
  TrumpSystem         — hierarchy, card classification
  CardCombo           — single / pair / tractor / multi detection & validation
  Trick               — one trick (4 plays), winner resolution
  GameState           — full round/game state machine
  BotPlayer           — 70/80% heuristic, 20/30% random AI
  YahtzeeApp → TuoLaJiApp  — tkinter GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import random
from collections import Counter
from itertools import groupby
from typing import List, Optional, Tuple, Dict

# ═══════════════════════════════════════════════════════════════
# 1.  CARD MODEL
# ═══════════════════════════════════════════════════════════════

SUITS   = ["♣", "♦", "♥", "♠"]          # clubs, diamonds, hearts, spades
RANKS   = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
RANK_VAL= {r: i for i, r in enumerate(RANKS)}   # "2"→0 … "A"→12

SMALL_JOKER = "SJ"
BIG_JOKER   = "BJ"

POINT_VALUES = {"5": 5, "10": 10, "K": 10}


class Card:
    """Immutable playing card.  deck_id distinguishes identical cards."""
    __slots__ = ("suit", "rank", "deck_id", "_str")

    def __init__(self, suit: str, rank: str, deck_id: int = 0):
        self.suit    = suit
        self.rank    = rank
        self.deck_id = deck_id
        if suit in (SMALL_JOKER, BIG_JOKER):
            self._str = suit
        else:
            self._str = f"{suit}{rank}"

    def is_joker(self)   -> bool: return self.suit in (SMALL_JOKER, BIG_JOKER)
    def is_big_joker(self)-> bool: return self.suit == BIG_JOKER
    def is_small_joker(self)->bool: return self.suit == SMALL_JOKER
    def point_value(self)-> int:   return POINT_VALUES.get(self.rank, 0)

    def __repr__(self): return f"{self._str}({self.deck_id})"
    def __str__ (self): return self._str
    def __eq__(self, other): return (self.suit == other.suit and
                                     self.rank == other.rank and
                                     self.deck_id == other.deck_id)
    def __hash__(self): return hash((self.suit, self.rank, self.deck_id))


def make_deck() -> List[Card]:
    """One standard deck: 52 cards + small joker + big joker = 54 cards."""
    cards = []
    for suit in SUITS:
        for rank in RANKS:
            cards.append(Card(suit, rank))
    cards.append(Card(SMALL_JOKER, SMALL_JOKER))
    cards.append(Card(BIG_JOKER,   BIG_JOKER))
    return cards


def make_double_deck() -> List[Card]:
    """Two decks, deck_id distinguishes duplicates. 108 cards total."""
    d = []
    for deck_id in range(2):
        for suit in SUITS:
            for rank in RANKS:
                d.append(Card(suit, rank, deck_id))
        d.append(Card(SMALL_JOKER, SMALL_JOKER, deck_id))
        d.append(Card(BIG_JOKER,   BIG_JOKER,   deck_id))
    random.shuffle(d)
    return d


# ═══════════════════════════════════════════════════════════════
# 2.  TRUMP SYSTEM  — the heart of the game
# ═══════════════════════════════════════════════════════════════

class TrumpSystem:
    """
    Card classification and ordering.

    Non-trump suit cards are ordered normally by rank.
    Trump cards form one merged suit with this order (lowest → highest):

        non-trump-suit cards of trump_rank
        (ordered: ♣ ♦ ♥ ♠ — whichever isn't trump suit, left to right)
        trump-suit cards of normal rank (2..A, skipping trump_rank)
        trump-suit card of trump_rank
        small joker
        big joker
    """

    def __init__(self, trump_suit: str, trump_rank: str):
        self.trump_suit = trump_suit    # e.g. "♠"
        self.trump_rank = trump_rank    # e.g. "2"

    # ── classification ──────────────────────────────────────

    def is_trump(self, card: Card) -> bool:
        if card.is_joker():                        return True
        if card.rank == self.trump_rank:           return True
        if card.suit == self.trump_suit:           return True
        return False

    def effective_suit(self, card: Card) -> str:
        """Returns "TRUMP" or the card's actual suit."""
        return "TRUMP" if self.is_trump(card) else card.suit

    # ── ordering value (higher = stronger) ──────────────────

    def trump_order(self, card: Card) -> int:
        """Ordering within the trump suit (only call for trump cards)."""
        if card.is_big_joker():   return 1000
        if card.is_small_joker(): return 999

        # trump_rank of trump_suit
        if card.suit == self.trump_suit and card.rank == self.trump_rank:
            return 998

        # trump_rank of non-trump suit (ordered by suit index)
        if card.rank == self.trump_rank:
            non_trump = [s for s in SUITS if s != self.trump_suit]
            return 500 + non_trump.index(card.suit)   # 500, 501, 502

        # trump-suit normal cards
        if card.suit == self.trump_suit:
            return RANK_VAL[card.rank]   # 0-12

        raise ValueError(f"{card} is not trump")

    def card_order(self, card: Card) -> int:
        """Universal ordering (for sorting a hand etc.)."""
        if self.is_trump(card):
            return 2000 + self.trump_order(card)
        return SUITS.index(card.suit) * 100 + RANK_VAL[card.rank]

    def beats(self, challenger: Card, incumbent: Card, led_suit: str) -> bool:
        """
        Does challenger beat incumbent?
        Rules:
          • Trump beats non-trump of led suit
          • Within same effective suit, higher order wins
          • A card of a different non-trump suit never beats anything
        """
        c_trump = self.is_trump(challenger)
        i_trump = self.is_trump(incumbent)
        c_suit  = self.effective_suit(challenger)
        i_suit  = self.effective_suit(incumbent)

        if c_suit == i_suit:
            return self.trump_order(challenger) > self.trump_order(incumbent) \
                   if (c_trump and i_trump) \
                   else RANK_VAL[challenger.rank] > RANK_VAL[incumbent.rank]

        # challenger is trump, incumbent is not → beats
        if c_trump and not i_trump:
            return True

        # challenger is led-suit, incumbent is something else → beats
        if c_suit == led_suit and i_suit not in (led_suit, "TRUMP"):
            return True

        return False

    def sort_hand(self, hand: List[Card]) -> List[Card]:
        """Sort a hand: non-trump suits grouped, then trump, all high→low."""
        return sorted(hand, key=self.card_order, reverse=True)


# ═══════════════════════════════════════════════════════════════
# 3.  CARD COMBINATION MODEL
# ═══════════════════════════════════════════════════════════════

class ComboType:
    SINGLE  = "single"
    PAIR    = "pair"
    TRACTOR = "tractor"   # consecutive pairs (拖拉机)
    MULTI   = "multi"     # mixed lead of single/pair/tractor


class CardCombo:
    """
    Represents a valid play (one or more cards forming a legal combination).
    """

    def __init__(self, cards: List[Card], trump: TrumpSystem):
        self.cards = cards
        self.trump = trump
        self.type, self.components = self._detect()

    # ── detection ───────────────────────────────────────────

    def _detect(self):
        cards = self.cards
        n = len(cards)
        trump = self.trump

        if n == 1:
            return ComboType.SINGLE, [cards]

        # All must be same effective suit for non-multi combos
        suits = set(trump.effective_suit(c) for c in cards)

        if len(suits) == 1:
            # Group by rank within effective suit
            if n == 2:
                if cards[0].rank == cards[1].rank or \
                   (trump.is_trump(cards[0]) and trump.is_trump(cards[1]) and
                    trump.trump_order(cards[0]) == trump.trump_order(cards[1])):
                    return ComboType.PAIR, [cards]
                # Two different singles is invalid as pair; treat as multi
            # Check tractor: consecutive pairs
            tractor = self._try_tractor(cards)
            if tractor:
                return ComboType.TRACTOR, [cards]

        # Multi: decompose into components
        components = self._decompose(cards)
        if len(components) == 1 and len(components[0]) == n:
            # Single component — classify properly
            if n == 2:
                return ComboType.PAIR, components
            return ComboType.TRACTOR, components
        return ComboType.MULTI, components

    def _group_by_order(self, cards: List[Card]):
        """Return dict: order_value → list of cards."""
        groups: Dict[int, List[Card]] = {}
        for c in cards:
            o = (self.trump.trump_order(c) if self.trump.is_trump(c)
                 else RANK_VAL[c.rank])
            groups.setdefault(o, []).append(c)
        return groups

    def _try_tractor(self, cards: List[Card]) -> bool:
        """Check if cards form a tractor (≥2 consecutive pairs, same suit)."""
        if len(cards) < 4 or len(cards) % 2 != 0:
            return False
        groups = self._group_by_order(cards)
        if any(len(v) != 2 for v in groups.values()):
            return False
        orders = sorted(groups.keys())
        # Consecutive in trump ordering? We need consecutive trump orders
        # For trump: we must skip the gaps created by trump_rank insertion
        for i in range(len(orders)-1):
            if orders[i+1] - orders[i] != 1:
                return False
        return True

    def _decompose(self, cards: List[Card]) -> List[List[Card]]:
        """Break cards into tractors, then pairs, then singles."""
        remaining = list(cards)
        components = []
        trump = self.trump

        # Group by (effective_suit, order)
        def order_of(c):
            return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

        groups: Dict[Tuple, List[Card]] = {}
        for c in remaining:
            key = (trump.effective_suit(c), order_of(c))
            groups.setdefault(key, []).append(c)

        # Find tractors (greedy, longest first)
        pairs_by_suit: Dict[str, List] = {}
        for (suit, order), cs in groups.items():
            if len(cs) >= 2:
                pairs_by_suit.setdefault(suit, []).append((order, cs[:2]))

        used = set()
        for suit, pair_list in pairs_by_suit.items():
            pair_list.sort()
            # Find consecutive runs
            i = 0
            while i < len(pair_list):
                j = i + 1
                while j < len(pair_list) and pair_list[j][0] - pair_list[j-1][0] == 1:
                    j += 1
                if j - i >= 2:
                    tractor_cards = []
                    for k in range(i, j):
                        tractor_cards.extend(pair_list[k][1])
                        used.add(id(pair_list[k][1][0]))
                        used.add(id(pair_list[k][1][1]))
                    components.append(tractor_cards)
                i = j

        # Remaining pairs
        for (suit, order), cs in groups.items():
            if len(cs) >= 2:
                pair = [c for c in cs[:2] if id(c) not in used]
                if len(pair) == 2:
                    components.append(pair)
                    used.update(id(c) for c in pair)

        # Singles
        for (suit, order), cs in groups.items():
            for c in cs:
                if id(c) not in used:
                    components.append([c])
                    used.add(id(c))

        return components if components else [cards]

    # ── strength ─────────────────────────────────────────────

    def top_card(self) -> Card:
        """Highest card in the combo."""
        trump = self.trump
        def key(c):
            return trump.card_order(c)
        return max(self.cards, key=key)

    def effective_suit(self) -> str:
        """
        The effective suit of this combo.
        For a valid single-suit lead this is well-defined.
        For a multi-suit follow, returns the suit of the first card
        (used only for trick-winner resolution, which handles mixed plays correctly).
        """
        return self.trump.effective_suit(self.cards[0])

    def suits_present(self) -> set:
        """Set of effective suits present in these cards."""
        return set(self.trump.effective_suit(c) for c in self.cards)

    # ── lead validation ───────────────────────────────────────

    @staticmethod
    def is_valid_lead(cards: List[Card], trump: TrumpSystem) -> Tuple[bool, str]:
        """
        Check whether `cards` constitute a legal lead.

        Rules for leading:
          • All cards must be from the same effective suit.
          • Within that suit, the cards must form a valid combo:
              - single, pair, tractor, or a multi-combo (multiple
                singles/pairs/tractors all from the same suit — e.g.
                leading AA + KK + J from hearts is fine as a multi-lead
                as long as every component is hearts).
          • You cannot lead cards from more than one effective suit.
        """
        if not cards:
            return False, "No cards selected."
        suits = set(trump.effective_suit(c) for c in cards)
        if len(suits) > 1:
            suit_list = ", ".join(sorted(suits))
            return False, (f"A lead must be all one suit. "
                           f"You selected cards from: {suit_list}.")
        return True, ""

    # ── follow validation ─────────────────────────────────────

    @staticmethod
    def required_follow_structure(led: "CardCombo", hand: List[Card],
                                  trump: TrumpSystem) -> Dict[str, int]:
        """
        Given what was led and what cards a player holds, compute the minimum
        *structural* obligation they must fulfil from their led-suit cards.

        Returns a dict:
          "tractors"  → number of tractor-cards (groups of ≥4) that must be played
          "pair_cards" → number of pair-cards (groups of 2) that must be played
                         (after tractors are satisfied)
          "singles"   → number of single led-suit cards that must fill remaining slots
          "total"     → total led-suit cards that must be played

        Algorithm:
          Work through each component in the lead (largest first: tractors, then
          pairs, then singles).  For each component type, check how many matching
          combos the follower can supply from their led-suit hand cards, and
          require as many as available (capped by the lead's demand).

          Any shortfall in a component type falls down to the next type, then
          finally to plain singles, and finally to off-suit cards.
        """
        led_suit     = led.effective_suit()
        n_lead       = len(led.cards)
        hand_in_suit = [c for c in hand if trump.effective_suit(c) == led_suit]
        n_in_suit    = len(hand_in_suit)

        # If void in suit, nothing is required from the suit.
        if n_in_suit == 0:
            return {"tractors": 0, "pair_cards": 0, "singles": 0, "total": 0}

        # Count what the follower holds in the led suit, by structure.
        # Build (effective_suit, order) → list of cards
        def order_of(c):
            return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

        suit_groups: Dict[int, List[Card]] = {}
        for c in hand_in_suit:
            o = order_of(c)
            suit_groups.setdefault(o, []).append(c)

        # Find pairs available in the follower's hand (in the led suit)
        pair_orders = sorted(
            [o for o, cs in suit_groups.items() if len(cs) >= 2]
        )

        # Find tractors (consecutive pair orders)
        tractor_pair_count = 0   # number of pairs consumed by tractors
        used_in_tractor: set = set()
        i = 0
        while i < len(pair_orders):
            j = i + 1
            while j < len(pair_orders) and pair_orders[j] - pair_orders[j-1] == 1:
                j += 1
            run_length = j - i   # number of consecutive pairs in this run
            if run_length >= 2:
                tractor_pair_count += run_length
                for k in range(i, j):
                    used_in_tractor.add(pair_orders[k])
            i = j

        # Pairs not used in tractors
        free_pair_count = sum(
            1 for o in pair_orders if o not in used_in_tractor
        )

        # How many tractor-cards, pair-cards, singles does the lead demand?
        # Walk through lead components sorted largest-first.
        lead_components = sorted(led.components, key=lambda c: -len(c))

        demand_tractor_pairs = 0   # pairs demanded by tractor slots
        demand_pairs         = 0   # pairs demanded by pair slots (non-tractor)
        demand_singles       = 0   # singles demanded

        for comp in lead_components:
            size = len(comp)
            if size >= 4:
                demand_tractor_pairs += size // 2
            elif size == 2:
                demand_pairs += 1
            else:
                demand_singles += 1

        # How many tractor-pairs can we actually supply?
        supplied_tractor_pairs = min(tractor_pair_count, demand_tractor_pairs)
        remaining_tractor_demand = demand_tractor_pairs - supplied_tractor_pairs
        # Shortfall in tractors falls to pairs
        demand_pairs += remaining_tractor_demand

        # Remaining free pairs after supplying tractors
        remaining_free_pairs = free_pair_count
        supplied_pairs = min(remaining_free_pairs, demand_pairs)
        remaining_pair_demand = demand_pairs - supplied_pairs
        # Shortfall in pairs falls to singles
        demand_singles += remaining_pair_demand * 2   # each missing pair → 2 singles

        # Cards committed so far
        committed = supplied_tractor_pairs * 2 + supplied_pairs * 2
        # Remaining singles needed (from led-suit hand cards)
        remaining_suit_cards = n_in_suit - committed
        supplied_singles = min(remaining_suit_cards, demand_singles)

        total = min(committed + supplied_singles, n_in_suit, n_lead)

        return {
            "tractors":   supplied_tractor_pairs * 2,
            "pair_cards": supplied_pairs * 2,
            "singles":    supplied_singles,
            "total":      total,
            # raw counts for validation
            "_avail_tractor_pairs": tractor_pair_count,
            "_avail_free_pairs":    free_pair_count,
            "_hand_in_suit":        hand_in_suit,
        }

    @staticmethod
    def is_valid_follow(cards: List[Card], led: "CardCombo",
                        hand: List[Card], trump: TrumpSystem) -> Tuple[bool, str]:
        """
        Check whether `cards` is a legal follow to `led`.

        Full Sheng Ji structure-following rules:
          1. Must play exactly as many cards as the lead.
          2. Must play as many led-suit cards as possible (up to n_lead).
          3. Within those led-suit cards, must match the lead structure greedily:
               a. Contribute tractors first (as many tractor-pairs as you hold,
                  up to the number demanded by the lead's tractor components).
               b. Then contribute pairs (as many free pairs as remain, up to demand).
               c. Then fill remaining slots with singles from the led suit.
          4. Any slots still unfilled after exhausting the led suit may be any card.
        """
        n_needed = len(led.cards)
        if len(cards) != n_needed:
            return False, f"Must play exactly {n_needed} card(s)."

        led_suit     = led.effective_suit()
        hand_in_suit = [c for c in hand if trump.effective_suit(c) == led_suit]
        play_in_suit = [c for c in cards if trump.effective_suit(c) == led_suit]

        req = CardCombo.required_follow_structure(led, hand, trump)

        # Rule 2: must play the required total number of led-suit cards
        if len(play_in_suit) < req["total"]:
            return False, (
                f"You must play {req['total']} card(s) of the led suit "
                f"({led_suit}) — you played {len(play_in_suit)}."
            )

        # Rules 3a–3b: check tractor and pair obligations within the played in-suit cards
        # Only applies when the player actually has enough in-suit cards to matter.
        if len(play_in_suit) >= req["total"] and req["total"] > 0:
            # Build structure of what the player actually played from the led suit
            def order_of(c):
                return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

            play_suit_groups: Dict[int, List[Card]] = {}
            for c in play_in_suit:
                o = order_of(c)
                play_suit_groups.setdefault(o, []).append(c)

            played_pair_orders = sorted(
                [o for o, cs in play_suit_groups.items() if len(cs) >= 2]
            )

            # Count tractor pairs in what was played
            played_tractor_pairs = 0
            played_used_in_tractor: set = set()
            i = 0
            while i < len(played_pair_orders):
                j = i + 1
                while (j < len(played_pair_orders) and
                       played_pair_orders[j] - played_pair_orders[j-1] == 1):
                    j += 1
                run = j - i
                if run >= 2:
                    played_tractor_pairs += run
                    for k in range(i, j):
                        played_used_in_tractor.add(played_pair_orders[k])
                i = j

            played_free_pairs = sum(
                1 for o in played_pair_orders if o not in played_used_in_tractor
            )
            played_singles_in_suit = sum(
                1 for o, cs in play_suit_groups.items() if len(cs) == 1
            )

            avail_tp = req["_avail_tractor_pairs"]
            avail_fp = req["_avail_free_pairs"]

            # 3a: must play min(avail_tractor_pairs, demanded_tractor_pairs) tractor pairs
            required_tp = req["tractors"] // 2
            if played_tractor_pairs < required_tp:
                return False, (
                    f"You must play {required_tp} tractor pair(s) from "
                    f"{led_suit} — you have them but didn't play them."
                )

            # 3b: after tractors, must play as many free pairs as demanded
            required_fp = req["pair_cards"] // 2
            if played_free_pairs < required_fp:
                return False, (
                    f"You must play {required_fp} pair(s) from {led_suit} "
                    f"— you have them but played a non-pair instead."
                )

        return True, ""

    @staticmethod
    def build_valid_follow(led: "CardCombo", hand: List[Card],
                           trump: TrumpSystem) -> List[Card]:
        """
        Construct a valid (but not necessarily optimal) follow for a bot or
        corrective fallback.  Greedily fills:
          1. Tractors from led suit (up to demand)
          2. Pairs from led suit (up to demand)
          3. Singles from led suit (up to demand)
          4. Off-suit cards for any remaining slots
        """
        n_needed     = len(led.cards)
        led_suit     = led.effective_suit()
        hand_in_suit = [c for c in hand if trump.effective_suit(c) == led_suit]
        req          = CardCombo.required_follow_structure(led, hand, trump)

        def order_of(c):
            return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

        chosen: List[Card] = []
        remaining = list(hand_in_suit)

        def take_cards(card_list):
            for c in card_list:
                chosen.append(c)
                remaining.remove(c)

        # Group remaining by order
        def group(pool):
            g: Dict[int, List[Card]] = {}
            for c in pool:
                g.setdefault(order_of(c), []).append(c)
            return g

        # Step 1: tractors
        need_tractor_pairs = req["tractors"] // 2
        if need_tractor_pairs > 0:
            g = group(remaining)
            pair_orders = sorted([o for o, cs in g.items() if len(cs) >= 2])
            # find consecutive runs and take them
            i = 0
            taken = 0
            while i < len(pair_orders) and taken < need_tractor_pairs:
                j = i + 1
                while (j < len(pair_orders) and
                       pair_orders[j] - pair_orders[j-1] == 1):
                    j += 1
                run = j - i
                if run >= 2:
                    pairs_to_take = min(run, need_tractor_pairs - taken)
                    for k in range(i, i + pairs_to_take):
                        take_cards(g[pair_orders[k]][:2])
                    taken += pairs_to_take
                i = j

        # Step 2: free pairs
        need_free_pairs = req["pair_cards"] // 2
        if need_free_pairs > 0:
            g = group(remaining)
            pair_orders = sorted(
                [o for o, cs in g.items() if len(cs) >= 2], reverse=True
            )
            for o in pair_orders[:need_free_pairs]:
                take_cards(g[o][:2])

        # Step 3: singles from led suit
        need_singles = req["singles"]
        if need_singles > 0:
            # Take lowest-value singles to waste as little as possible
            singles = sorted(remaining, key=lambda c: order_of(c))
            take_cards(singles[:need_singles])

        # Step 4: fill rest with off-suit cards (lowest value first)
        still_need = n_needed - len(chosen)
        if still_need > 0:
            off_suit = [c for c in hand if c not in chosen and c not in hand_in_suit]
            off_suit_sorted = sorted(off_suit, key=lambda c: trump.card_order(c))
            chosen.extend(off_suit_sorted[:still_need])

        return chosen[:n_needed]

    # ── legacy helper kept for trick resolution ───────────────

    @staticmethod
    def valid_responses(hand: List[Card], led: "CardCombo",
                        trump: TrumpSystem) -> List[List[Card]]:
        """Kept for compatibility — returns pool of cards that must be used."""
        led_suit     = led.effective_suit()
        hand_in_suit = [c for c in hand if trump.effective_suit(c) == led_suit]
        return [hand_in_suit] if hand_in_suit else [hand]

    def __repr__(self):
        return f"CardCombo({self.type}, {self.cards})"


# ═══════════════════════════════════════════════════════════════
# 4.  TRICK
# ═══════════════════════════════════════════════════════════════

class Trick:
    """Tracks one trick: up to 4 plays, resolves winner."""

    def __init__(self, trump: TrumpSystem, leader: int):
        self.trump   = trump
        self.leader  = leader            # player index who leads
        self.plays: List[Tuple[int, List[Card]]] = []   # (player_idx, cards)
        self.led_combo: Optional[CardCombo] = None

    def play(self, player_idx: int, cards: List[Card]):
        combo = CardCombo(cards, self.trump)
        if not self.plays:
            self.led_combo = combo
        self.plays.append((player_idx, cards))

    def is_complete(self) -> bool:
        return len(self.plays) == 4

    def winner(self) -> int:
        """Return player index of trick winner."""
        assert self.is_complete()
        led_suit   = self.led_combo.effective_suit()
        led_comps  = self.led_combo.components   # list of component card-lists

        best_player = self.plays[0][0]
        best_cards  = self.plays[0][1]

        for player_idx, cards in self.plays[1:]:
            if self._play_beats(cards, best_cards, led_comps, led_suit):
                best_cards  = cards
                best_player = player_idx

        return best_player

    def _play_beats(self, challenger_cards: List[Card],
                    incumbent_cards: List[Card],
                    led_components: List[List[Card]],
                    led_suit: str) -> bool:
        """
        Does challenger beat incumbent?

        Rules (Sheng Ji / Tractor):
        ─────────────────────────────────────────────────────────────
        The lead defines a *structure* — an ordered list of components
        sorted largest-first: e.g. [tractor(6 cards), pair(2), single(1)].

        A play beats the current best IFF, for EVERY component position i:
          • challenger's component[i] beats incumbent's component[i]
            in the same position.

        Component matching uses the *led* component sizes as the template.
        The follower's cards are decomposed to match that template, then
        compared position by position.

        Exception: if a play is entirely off-suit AND off-trump, it can
        never win — return False immediately.
        """
        trump = self.trump

        # Quick discard: challenger must have at least one card in the
        # led suit or trump to be able to win
        c_suits = set(trump.effective_suit(c) for c in challenger_cards)
        if led_suit not in c_suits and "TRUMP" not in c_suits:
            return False

        i_suits = set(trump.effective_suit(c) for c in incumbent_cards)

        # Decompose each play into components matching the led template
        c_comps = self._match_components(challenger_cards, led_components)
        i_comps = self._match_components(incumbent_cards,  led_components)

        # Challenger must beat incumbent on EVERY component
        for c_comp, i_comp, led_comp in zip(c_comps, i_comps, led_components):
            if not self._component_beats(c_comp, i_comp, led_comp, led_suit):
                return False
        return True

    def _match_components(self, cards: List[Card],
                          template: List[List[Card]]) -> List[List[Card]]:
        """
        Split `cards` into len(template) groups whose sizes match the
        template sizes.  We greedily assign cards by matching combo type
        (tractor > pair > single) and strength within each slot.
        """
        trump    = self.trump
        sizes    = [len(t) for t in template]
        remaining = list(cards)
        result   = []

        for size in sizes:
            # Take `size` cards from remaining that best match the slot
            # For simplicity: take the `size` highest-order cards available
            def order_key(c):
                return trump.card_order(c)
            chunk = sorted(remaining, key=order_key, reverse=True)[:size]
            for c in chunk:
                remaining.remove(c)
            result.append(chunk)

        return result

    def _component_beats(self, challenger: List[Card],
                         incumbent: List[Card],
                         led: List[Card],
                         led_suit: str) -> bool:
        """
        Does the challenger component beat the incumbent component,
        given the led component as the structural template?

        Rules by component size:
          size 1 (single):  higher card wins; trump beats led-suit; off-suit loses
          size 2 (pair):    must be a pair to beat a pair; higher pair wins
          size ≥4 (tractor): must be a tractor to beat a tractor; higher wins
        """
        trump = self.trump
        n = len(led)

        # Determine what the incumbent is (pair/tractor/single)
        inc_combo  = CardCombo(incumbent, trump)
        chal_combo = CardCombo(challenger, trump)

        inc_suit  = trump.effective_suit(incumbent[0])  if incumbent  else None
        chal_suit = trump.effective_suit(challenger[0]) if challenger else None

        # Off-suit, off-trump challenger can never beat anything
        if chal_suit not in (led_suit, "TRUMP"):
            return False

        # Challenger must match the *structural type* of the led component
        # to beat the incumbent's matching component.
        if n == 1:
            # Singles: just compare card strength
            return trump.beats(challenger[0], incumbent[0], led_suit)

        if n == 2:
            # Pair slot: challenger must also be a pair to win
            if chal_combo.type != ComboType.PAIR:
                return False
            if inc_combo.type != ComboType.PAIR:
                # Incumbent wasn't a pair — challenger pair beats it
                # (incumbent couldn't match the structure)
                return True
            # Both pairs — compare the pair's card value
            return trump.beats(chal_combo.top_card(), inc_combo.top_card(), led_suit)

        # n >= 4: tractor slot
        if chal_combo.type != ComboType.TRACTOR:
            return False
        if inc_combo.type != ComboType.TRACTOR:
            return True
        return trump.beats(chal_combo.top_card(), inc_combo.top_card(), led_suit)

    def points(self) -> int:
        return sum(c.point_value() for _, cards in self.plays for c in cards)

    def __repr__(self):
        return f"Trick(leader={self.leader}, plays={self.plays})"


# ═══════════════════════════════════════════════════════════════
# 5.  GAME STATE
# ═══════════════════════════════════════════════════════════════

class GamePhase:
    DEALING   = "dealing"    # cards dealt one-by-one; players may declare trump
    KITTY     = "kitty"      # winning declarer buries 8 cards
    PLAYING   = "playing"    # trick-taking
    SCORING   = "scoring"    # round over


# Declaration bid strengths — higher overrides lower
# single trump-rank card = 1, pair of trump-rank = 2,
# single small joker = 3, pair of small jokers = 4,
# single big joker = 5, pair of big jokers = 6
def _bid_strength(cards: List["Card"], trump_rank: str) -> int:
    """Return the bid strength of a proposed declaration (0 = invalid)."""
    if not cards:
        return 0
    if len(cards) == 1:
        c = cards[0]
        if c.is_big_joker():   return 5
        if c.is_small_joker(): return 3
        if c.rank == trump_rank: return 1
        return 0
    if len(cards) == 2:
        c0, c1 = cards
        if c0.is_big_joker()   and c1.is_big_joker():   return 6
        if c0.is_small_joker() and c1.is_small_joker(): return 4
        if (c0.rank == trump_rank and c1.rank == trump_rank
                and c0.suit == c1.suit):                return 2
    return 0


class GameState:
    """
    Full game state for one round of Tuo La Ji.

    Teams: 0&2 vs 1&3.
    Declarers (team that wins the bid) try to prevent defenders from
    getting enough points.  Defenders need ≥80 points to hold.

    Trump declaration during dealing
    ─────────────────────────────────
    Cards are dealt one at a time (deal_next_card()).  At any point a
    player may call declare_trump(player, cards) to bid for the trump
    suit.  A bid is valid only if its strength > current declaration
    strength, OR it is the first bid.  Joker bids do not set a suit
    (suit stays as the previous declaration's suit or defaults to ♠).
    Once all non-kitty cards are dealt the phase advances to KITTY and
    the winning declarer picks up + buries the kitty.
    """

    KITTY_SIZE = 8

    def __init__(self, num_players=4, trump_rank="2", declaring_team=0):
        self.num_players    = num_players
        self.trump_rank     = trump_rank

        # Declaration state — resolved at end of dealing
        self.declaration: Optional[Tuple[int, List[Card]]] = None  # (player, cards)
        self.declaration_strength: int = 0
        self.declaring_player: int = declaring_team * 2   # player 0 or player 1 initially
        self.declaring_team:   int = declaring_team

        # Trump is initially unknown; default used for sorting only
        self.trump_suit = "♠"
        self.trump      = TrumpSystem(self.trump_suit, self.trump_rank)

        self.team_levels = ["2", "2"]

        self.hands: List[List[Card]] = [[] for _ in range(num_players)]
        self.kitty: List[Card] = []

        self.phase          = GamePhase.DEALING
        self.current_player = 0
        self.tricks: List[Trick] = []
        self.current_trick: Optional[Trick] = None
        self.scores         = [0, 0]
        self.trick_winner_log: List[Tuple[int,int]] = []

        # Internal deal queue
        self._deck: List[Card] = []
        self._deal_idx: int = 0
        self._cards_per_player: int = 0
        self._prepare_deck()

    def _prepare_deck(self):
        deck = make_double_deck()
        random.shuffle(deck)
        self._cards_per_player = (len(deck) - self.KITTY_SIZE) // self.num_players
        self._deck = deck
        self._deal_idx = 0
        # Reserve last KITTY_SIZE cards as kitty
        self._kitty_start = self._cards_per_player * self.num_players

    def deal_next_card(self) -> Optional[Tuple[int, Card]]:
        """
        Deal one card to the next player in rotation.
        Returns (player_idx, card) or None if dealing is complete.
        When dealing finishes, advances phase to KITTY automatically
        and sets the kitty cards.
        """
        if self._deal_idx >= self._kitty_start:
            return None  # all player cards dealt

        player_idx = self._deal_idx % self.num_players
        card = self._deck[self._deal_idx]
        self.hands[player_idx].append(card)
        self._deal_idx += 1

        if self._deal_idx >= self._kitty_start:
            # Dealing complete — set kitty and advance phase
            self.kitty = self._deck[self._kitty_start:]
            self._finalize_declaration()
            self.phase = GamePhase.KITTY

        return (player_idx, card)

    def _finalize_declaration(self):
        """Lock in trump suit/player after dealing is done."""
        if self.declaration is None:
            # Nobody declared — default: player 0 declares ♠
            self.declaring_player = 0
            self.declaring_team   = 0
            self.trump_suit       = "♠"
        else:
            player, cards = self.declaration
            self.declaring_player = player
            self.declaring_team   = player % 2
            # Joker-only bids don't reveal a suit — keep last suit or default ♠
            non_joker = [c for c in cards if not c.is_joker()]
            if non_joker:
                self.trump_suit = non_joker[0].suit
        self.trump = TrumpSystem(self.trump_suit, self.trump_rank)
        # Re-sort all hands with resolved trump
        for i in range(self.num_players):
            self.hands[i] = self.trump.sort_hand(self.hands[i])

    def declare_trump(self, player_idx: int,
                      cards: List[Card]) -> Tuple[bool, str]:
        """
        Attempt a trump declaration.
        Returns (success, message).
        Rules:
          • Cards must all be in player's hand
          • Must be valid bid cards (trump-rank suit cards or jokers)
          • Bid strength must exceed current strength
          • Joker pairs are the strongest bid and cannot be overridden
        """
        if self.phase != GamePhase.DEALING:
            return False, "Can only declare during the dealing phase."

        for c in cards:
            if c not in self.hands[player_idx]:
                return False, "You don't have those cards."

        strength = _bid_strength(cards, self.trump_rank)
        if strength == 0:
            return False, ("Declaration must be trump-rank cards of one suit, "
                           "a joker, or a pair of the same.")
        if strength <= self.declaration_strength:
            return False, (f"Your bid (strength {strength}) doesn't beat "
                           f"the current declaration (strength "
                           f"{self.declaration_strength}).")

        self.declaration          = (player_idx, cards)
        self.declaration_strength = strength

        # Immediately update trump so hand sorting reflects the bid
        non_joker = [c for c in cards if not c.is_joker()]
        if non_joker:
            self.trump_suit = non_joker[0].suit
            self.trump      = TrumpSystem(self.trump_suit, self.trump_rank)

        return True, "Declaration accepted!"

    def is_dealing_done(self) -> bool:
        return self._deal_idx >= self._kitty_start

    def bury_kitty(self, cards_to_bury: List[Card]):
        """Declaring player picks up kitty and buries 8 cards."""
        player_idx = self.declaring_player
        assert len(cards_to_bury) == self.KITTY_SIZE
        self.hands[player_idx].extend(self.kitty)
        for c in cards_to_bury:
            self.hands[player_idx].remove(c)
        self.kitty = cards_to_bury
        self.phase          = GamePhase.PLAYING
        self.current_trick  = Trick(self.trump, player_idx)
        self.current_player = player_idx

    def play_cards(self, player_idx: int, cards: List[Card]) -> Optional[int]:
        """
        Play cards into the current trick.
        Returns winner player_idx if trick is complete, else None.
        """
        assert player_idx == self.current_player
        assert self.phase == GamePhase.PLAYING

        # Remove from hand
        for c in cards:
            self.hands[player_idx].remove(c)

        self.current_trick.play(player_idx, cards)

        if self.current_trick.is_complete():
            winner = self.current_trick.winner()
            pts    = self.current_trick.points()
            winning_team = winner % 2
            self.scores[winning_team] += pts
            self.tricks.append(self.current_trick)
            self.trick_winner_log.append((len(self.tricks)-1, winner))

            # Kitty points go to defending team if they win the last trick,
            # or to declarers if declarers win the last trick
            if self._all_cards_played():
                kitty_pts = sum(c.point_value() for c in self.kitty)
                # Last trick winner gets kitty
                self.scores[winning_team] += kitty_pts
                self.phase = GamePhase.SCORING
                return winner

            self.current_trick  = Trick(self.trump, winner)
            self.current_player = winner
            return winner
        else:
            self.current_player = (player_idx + 1) % self.num_players
            return None

    def _all_cards_played(self) -> bool:
        return all(len(h) == 0 for h in self.hands)

    def defending_team(self) -> int:
        return 1 - self.declaring_team

    def attacker_points(self) -> int:
        """Points scored by the attacking (defending) team this round."""
        return self.scores[self.defending_team()]

    def compute_round_outcome(self) -> dict:
        """
        Return a dict describing the full round outcome for Sheng Ji level logic.

        Sheng Ji attacker-point thresholds:
          0–39:   Attackers lose, defenders level up +2
          40–79:  Attackers lose, defenders level up +1
          80–119: Attackers win, no level change
          120–159:Attackers win, attackers level up +1
          160–199:Attackers win, attackers level up +2
          200+:   Attackers win, attackers level up +3

        'Attackers' = the team that is NOT the current defenders
                    = the team that is NOT burying the kitty
        'Defenders' = declaring_team (the kitty-burying team)
        """
        pts        = self.attacker_points()
        def_team   = self.declaring_team          # current defenders (kitty team)
        atk_team   = 1 - def_team                 # current attackers

        if pts < 40:
            attackers_win = False
            level_delta   = 2    # defenders level up
            winner_team   = def_team
        elif pts < 80:
            attackers_win = False
            level_delta   = 1
            winner_team   = def_team
        elif pts < 120:
            attackers_win = True
            level_delta   = 0
            winner_team   = atk_team
        elif pts < 160:
            attackers_win = True
            level_delta   = 1
            winner_team   = atk_team
        elif pts < 200:
            attackers_win = True
            level_delta   = 2
            winner_team   = atk_team
        else:
            attackers_win = True
            level_delta   = 3
            winner_team   = atk_team

        leveling_team = def_team if not attackers_win else atk_team

        return {
            "attacker_pts":   pts,
            "attackers_win":  attackers_win,
            "winner_team":    winner_team,       # 0 or 1
            "leveling_team":  leveling_team,     # team that levels up
            "level_delta":    level_delta,
            "def_team":       def_team,
            "atk_team":       atk_team,
        }

    def round_result(self) -> str:
        """Human-readable one-line round result (legacy)."""
        pts = self.attacker_points()
        if pts >= 80:
            return f"Attackers win! ({pts} points)"
        return f"Defenders win! (Attackers only got {pts} points)"

    def team_of(self, player_idx: int) -> int:
        return player_idx % 2

    def is_declarer(self, player_idx: int) -> bool:
        return self.team_of(player_idx) == self.declaring_team


# ═══════════════════════════════════════════════════════════════
# 6.  BOT PLAYER  (70–80% heuristic, 20–30% random)
# ═══════════════════════════════════════════════════════════════

class BotPlayer:
    """
    Educated bot.  random_rate controls how often it ignores strategy.
    """

    def __init__(self, player_idx: int, random_rate: float = 0.22):
        self.player_idx  = player_idx
        self.random_rate = random_rate

    def choose_play(self, hand: List[Card], trick: Trick,
                    game: GameState) -> List[Card]:
        """Choose which cards to play."""
        if random.random() < self.random_rate:
            return self._random_play(hand, trick, game)
        return self._heuristic_play(hand, trick, game)

    # ── random fallback ──────────────────────────────────────

    def _random_play(self, hand: List[Card], trick: Trick,
                     game: GameState) -> List[Card]:
        if not trick.plays:
            return self._random_lead(hand, game)
        return self._random_follow(hand, trick, game)

    def _random_lead(self, hand: List[Card], game: GameState) -> List[Card]:
        return [random.choice(hand)]

    def _random_follow(self, hand: List[Card], trick: Trick,
                       game: GameState) -> List[Card]:
        led_suit  = trick.led_combo.effective_suit()
        trump     = game.trump
        in_suit   = [c for c in hand if trump.effective_suit(c) == led_suit]
        n_needed  = len(trick.led_combo.cards)
        pool      = in_suit if in_suit else hand
        n         = min(n_needed, len(pool))
        return random.sample(pool, n)

    # ── heuristic strategy ───────────────────────────────────

    def _heuristic_play(self, hand: List[Card], trick: Trick,
                        game: GameState) -> List[Card]:
        if not trick.plays:
            return self._heuristic_lead(hand, game)
        return self._heuristic_follow(hand, trick, game)

    def _heuristic_lead(self, hand: List[Card], game: GameState) -> List[Card]:
        trump = game.trump
        sorted_hand = trump.sort_hand(hand)

        # Priority 1: Lead a tractor if we have one
        tractor = self._find_tractor(hand, trump)
        if tractor:
            # _find_tractor guarantees same effective suit
            return tractor

        # Priority 2: Lead a pair (same effective suit by construction)
        pair = self._find_pair(hand, trump)
        if pair:
            return pair

        # Priority 3: Lead highest non-trump single
        non_trump = [c for c in sorted_hand if not trump.is_trump(c)]
        if non_trump:
            return [non_trump[0]]

        # Priority 4: Lead lowest trump
        trumps = [c for c in sorted_hand if trump.is_trump(c)]
        if trumps:
            return [trumps[-1]]

        # Fallback: single card (always single-suit by definition)
        return [sorted_hand[0]]

    def _heuristic_follow(self, hand: List[Card], trick: Trick,
                          game: GameState) -> List[Card]:
        trump    = game.trump
        led_suit = trick.led_combo.effective_suit()
        n_needed = len(trick.led_combo.cards)
        in_suit  = [c for c in hand if trump.effective_suit(c) == led_suit]

        partner_winning = self._is_partner_winning(trick, game)

        if in_suit:
            if partner_winning:
                # Dump high-point cards on partner's winning trick
                sorted_pts = sorted(in_suit, key=lambda c: c.point_value(),
                                    reverse=True)
                return sorted_pts[:n_needed]
            else:
                # Try to beat current winner
                winning_card = self._current_winner_card(trick)
                beaters = [c for c in in_suit
                           if trump.beats(c, winning_card, led_suit)]
                if beaters:
                    # Play lowest beater
                    return sorted(beaters, key=trump.card_order)[:n_needed]
                # Can't beat — play lowest
                return sorted(in_suit, key=trump.card_order)[:n_needed]
        else:
            # Off-suit: dump points on partner, dump trash on opponents
            if partner_winning:
                sorted_pts = sorted(hand, key=lambda c: c.point_value(),
                                    reverse=True)
                return sorted_pts[:n_needed]
            else:
                # Dump lowest non-point cards
                non_point = [c for c in hand if c.point_value() == 0]
                pool = non_point if non_point else hand
                return sorted(pool, key=trump.card_order)[:n_needed]

    def _is_partner_winning(self, trick: Trick, game: GameState) -> bool:
        if not trick.plays:
            return False
        current_winner = trick.winner() if trick.is_complete() else \
            self._provisional_winner(trick, game)
        partner = (self.player_idx + 2) % 4
        return current_winner == partner

    def _provisional_winner(self, trick: Trick, game: GameState) -> int:
        """Winner so far (trick not complete)."""
        if not trick.plays:
            return -1
        led_suit   = trick.led_combo.effective_suit()
        best_p, best_c = trick.plays[0]
        best_combo = CardCombo(best_c, game.trump)
        for pid, cards in trick.plays[1:]:
            combo = CardCombo(cards, game.trump)
            if trick._component_beats(cards, best_c, best_c, led_suit):
                best_combo = combo
                best_p     = pid
        return best_p

    def _current_winner_card(self, trick: Trick) -> Card:
        """Top card of current winning play."""
        trump = trick.trump
        led_suit = trick.led_combo.effective_suit()
        best_cards = trick.plays[0][1]
        best_top   = CardCombo(best_cards, trump).top_card()
        for _, cards in trick.plays[1:]:
            top = CardCombo(cards, trump).top_card()
            if trump.beats(top, best_top, led_suit):
                best_top = top
        return best_top

    def _find_tractor(self, hand: List[Card],
                      trump: TrumpSystem) -> Optional[List[Card]]:
        """Find the first tractor in hand."""
        # Group by (effective_suit, order)
        def order_of(c):
            return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

        suit_groups: Dict[str, List] = {}
        for c in hand:
            s = trump.effective_suit(c)
            suit_groups.setdefault(s, []).append(c)

        for suit, cards in suit_groups.items():
            # Find pairs
            order_map: Dict[int, List[Card]] = {}
            for c in cards:
                o = order_of(c)
                order_map.setdefault(o, []).append(c)
            pairs = {o: cs for o, cs in order_map.items() if len(cs) >= 2}
            if len(pairs) < 2:
                continue
            orders = sorted(pairs.keys())
            for i in range(len(orders)-1):
                if orders[i+1] - orders[i] == 1:
                    return pairs[orders[i]][:2] + pairs[orders[i+1]][:2]
        return None

    def _find_pair(self, hand: List[Card],
                   trump: TrumpSystem) -> Optional[List[Card]]:
        """Find the highest pair in hand (must share the same effective suit)."""
        def order_of(c):
            return trump.trump_order(c) if trump.is_trump(c) else RANK_VAL[c.rank]

        # Group by (effective_suit, order) so pairs must be same suit AND same rank
        suit_order_map: Dict[Tuple, List[Card]] = {}
        for c in hand:
            key = (trump.effective_suit(c), order_of(c))
            suit_order_map.setdefault(key, []).append(c)

        pairs = [(key, cs) for key, cs in suit_order_map.items() if len(cs) >= 2]
        if not pairs:
            return None

        # Prefer non-trump pairs to preserve trump; within each preference sort by order
        non_trump_pairs = [(key, cs) for key, cs in pairs if key[0] != "TRUMP"]
        pool = non_trump_pairs if non_trump_pairs else pairs
        best_key, best_cs = max(pool, key=lambda x: x[0][1])   # highest order
        return best_cs[:2]

    def bury_kitty(self, hand: List[Card],
                   game: GameState) -> List[Card]:
        trump = game.trump
        # Bury: prefer non-trump low cards, then high-value non-trump
        non_trump = [c for c in hand if not trump.is_trump(c)]
        # Sort: lowest rank, but prefer point cards if we have too many
        non_trump_sorted = sorted(non_trump, key=lambda c: RANK_VAL[c.rank])

        to_bury = []
        # First bury low non-point non-trump cards
        low_non_pt = [c for c in non_trump_sorted if c.point_value() == 0]
        to_bury.extend(low_non_pt[:8])

        if len(to_bury) < 8:
            # Then point non-trump cards (we can score them later via kitty)
            pt_cards = [c for c in non_trump if c.point_value() > 0]
            pt_sorted = sorted(pt_cards, key=lambda c: c.point_value())
            to_bury.extend(pt_sorted[:8-len(to_bury)])

        if len(to_bury) < 8:
            # Reluctantly bury trump (lowest first)
            trumps = sorted([c for c in hand if trump.is_trump(c)],
                            key=trump.card_order)
            to_bury.extend(trumps[:8-len(to_bury)])

        return to_bury[:8]


# ═══════════════════════════════════════════════════════════════
# 7.  COLORS & CONSTANTS
# ═══════════════════════════════════════════════════════════════

C = {
    "bg":      "#1a1a2e",
    "panel":   "#16213e",
    "accent":  "#0f3460",
    "red":     "#e94560",
    "text":    "#eaeaea",
    "muted":   "#8892a4",
    "white":   "#ffffff",
    "yellow":  "#ffd166",
    "green":   "#06d6a0",
    "dark":    "#0d1b2a",
    "card_bg": "#f5f0e8",
    "card_red":"#c0392b",
    "trump_bg":"#fff3cd",
}

SUIT_COLORS = {"♠": "#1a1a2e", "♣": "#1a1a2e",
               "♥": C["card_red"], "♦": C["card_red"],
               SMALL_JOKER: "#7b2d8b", BIG_JOKER: "#7b2d8b"}

PLAYER_POSITIONS = ["bottom", "right", "top", "left"]   # relative to player 0


# ═══════════════════════════════════════════════════════════════
# 8.  CARD WIDGET
# ═══════════════════════════════════════════════════════════════

class CardWidget(tk.Frame):
    W, H = 52, 76

    def __init__(self, parent, card: Card, face_up=True,
                 selected=False, on_click=None, trump: TrumpSystem = None):
        super().__init__(parent, bg=C["bg"],
                         cursor="hand2" if on_click else "arrow")
        self.card      = card
        self.face_up   = face_up
        self.selected  = selected
        self.on_click  = on_click
        self.trump     = trump
        self._canvas   = tk.Canvas(self, width=self.W, height=self.H,
                                   highlightthickness=0)
        self._canvas.pack()
        if on_click:
            self._canvas.bind("<Button-1>", lambda e: on_click(card))
            self.bind("<Button-1>", lambda e: on_click(card))
        self._draw()

    def set_selected(self, v: bool):
        self.selected = v
        self._draw()

    def _draw(self):
        self._canvas.delete("all")
        W, H, r = self.W, self.H, 5
        if not self.face_up:
            self._canvas.create_rectangle(2,2,W-2,H-2, fill="#1e3a5f",
                                          outline=C["accent"], width=1)
            self._canvas.create_text(W//2, H//2, text="🂠",
                                     font=("Arial", 20), fill="#4a7fa5")
            return

        c = self.card
        is_trump_card = self.trump and self.trump.is_trump(c)
        fill = C["trump_bg"] if is_trump_card else C["card_bg"]
        if self.selected:
            fill = "#d4edda"

        self._rounded_rect(2, 2, W-2, H-2, r,
                           fill=fill,
                           outline=C["red"] if self.selected else "#aaa",
                           width=2 if self.selected else 1)

        if c.is_joker():
            label = "BIG\nJOKER" if c.is_big_joker() else "SMALL\nJOKER"
            col   = "#8B008B" if c.is_big_joker() else "#9400D3"
            self._canvas.create_text(W//2, H//2, text=label,
                                     font=("Arial", 7, "bold"),
                                     fill=col, justify="center")
        else:
            col = SUIT_COLORS.get(c.suit, "black")
            self._canvas.create_text(5, 9, text=c.suit,
                                     font=("Arial", 9), fill=col, anchor="w")
            self._canvas.create_text(5, 18, text=c.rank,
                                     font=("Arial", 8, "bold"), fill=col, anchor="w")
            self._canvas.create_text(W//2, H//2, text=c.suit,
                                     font=("Arial", 18), fill=col)
            # Point marker
            if c.point_value():
                self._canvas.create_text(W-3, H-6,
                                         text=f"+{c.point_value()}",
                                         font=("Arial", 6, "bold"),
                                         fill="#e74c3c", anchor="e")

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        c = self._canvas
        for args in [
            (x1,y1,x1+2*r,y1+2*r,90,90),(x2-2*r,y1,x2,y1+2*r,0,90),
            (x1,y2-2*r,x1+2*r,y2,180,90),(x2-2*r,y2-2*r,x2,y2,270,90)]:
            c.create_arc(*args[:4], start=args[4], extent=args[5],
                         style="pieslice", **kw)
        c.create_rectangle(x1+r,y1,x2-r,y2,**kw)
        c.create_rectangle(x1,y1+r,x2,y2-r,**kw)


# ═══════════════════════════════════════════════════════════════
# 9.  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════

class TuoLaJiApp(tk.Tk):

    RANKS = RANKS   # "2"…"A"

    def __init__(self):
        super().__init__()
        self.title("拖拉机 Tuo La Ji")
        self.configure(bg=C["bg"])
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.geometry("1200x800")
        self.minsize(900, 650)
        self._fullscreen = False
        self.bind("<F11>", self._toggle_fs)
        self.bind("<Escape>", self._exit_fs)

        # ── Persistent cross-round state ──────────────────────
        # team_levels[i] = current rank string for team i ("2"…"A")
        self.team_levels     = ["2", "2"]
        # Which team is currently defending (burying the kitty)
        self.defending_team  = 0           # team 0 = players 0 & 2
        # Which player buries kitty this round (within the defending team)
        self.kitty_player    = 2           # Bot T starts as kitty burier
        # Round counter
        self.round_num       = 0

        self._show_start()

    def _toggle_fs(self, e=None):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def _exit_fs(self, e=None):
        if self._fullscreen:
            self._fullscreen = False
            self.attributes("-fullscreen", False)

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _show_start(self):
        self._clear()
        outer = tk.Frame(self, bg=C["bg"])
        outer.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(outer, text="拖拉机", font=("Arial", 48, "bold"),
                 bg=C["bg"], fg=C["red"]).pack()
        tk.Label(outer, text="Tuo La Ji  ·  Sheng Ji  ·  Tractor",
                 font=("Arial", 14), bg=C["bg"], fg=C["muted"]).pack(pady=(0,16))

        # Show current game state if not first round
        if self.round_num > 0:
            PNAMES = ["You", "Bot R", "Bot T", "Bot L"]
            def_name = "Team A (You & Bot T)" if self.defending_team == 0 else "Team B (Bot R & Bot L)"
            kit_name = PNAMES[self.kitty_player]
            state_info = (
                f"Round {self.round_num + 1}\n\n"
                f"Team A level: {self.team_levels[0]}  |  Team B level: {self.team_levels[1]}\n"
                f"Defenders this round: {def_name}\n"
                f"Trump rank: {self.team_levels[self.defending_team]}\n"
                f"Kitty burier: {kit_name}"
            )
            tk.Label(outer, text=state_info, font=("Arial", 12),
                     bg=C["bg"], fg=C["green"], justify="center").pack(pady=(0,16))
        else:
            info = (
                "2v2 trick-taking card game  ·  2 decks  ·  108 cards\n"
                "You (Player 0) + Bot T  vs  Bot R & Bot L\n\n"
                "During the deal, declare trump suit by showing a trump-rank card or joker.\n"
                "A pair beats a single. Jokers beat trump-rank cards.\n"
                "Defenders need ≥ 80 attacker points to hold.\n"
                "F11 = fullscreen"
            )
            tk.Label(outer, text=info, font=("Arial", 11),
                     bg=C["bg"], fg=C["muted"], justify="center").pack(pady=(0,16))

        if self.round_num == 0:
            # Only ask for starting trump rank on first round
            tk.Label(outer, text="Starting Trump Rank (both teams begin at):",
                     font=("Arial", 12), bg=C["bg"], fg=C["text"]).pack()
            self.rank_var = tk.StringVar(value="2")
            rf = tk.Frame(outer, bg=C["bg"])
            rf.pack(pady=6)
            for r in RANKS:
                tk.Radiobutton(rf, text=r, variable=self.rank_var, value=r,
                               font=("Arial", 10), bg=C["bg"], fg=C["text"],
                               selectcolor=C["accent"],
                               activebackground=C["bg"]).pack(side="left", padx=2)

        lbl = "▶  Deal Cards" if self.round_num == 0 else "▶  Next Round"
        btn = tk.Button(outer, text=lbl,
                        font=("Arial", 15, "bold"),
                        bg=C["red"], fg=C["white"], relief="flat",
                        padx=24, pady=12, cursor="hand2",
                        command=self._start_game)
        btn.pack(pady=20)

        if self.round_num == 0:
            tk.Button(outer, text="Reset Game", font=("Arial", 10),
                      bg=C["accent"], fg=C["muted"], relief="flat",
                      cursor="hand2", command=self._reset_game).pack()

    def _reset_game(self):
        self.team_levels    = ["2", "2"]
        self.defending_team = 0
        self.kitty_player   = 2
        self.round_num      = 0
        self._show_start()

    def _start_game(self):
        if self.round_num == 0:
            start_rank = self.rank_var.get()
            self.team_levels = [start_rank, start_rank]
        self._clear()
        trump_rank = self.team_levels[self.defending_team]
        gs = GameScreen(self, trump_rank,
                        defending_team=self.defending_team,
                        kitty_player=self.kitty_player)
        gs.pack(fill="both", expand=True)

    def advance_round(self, outcome: dict):
        """
        Called by GameScreen when a round ends.
        Updates team levels, defending team, kitty player.
        """
        self.round_num += 1
        leveling_team = outcome["leveling_team"]
        delta         = outcome["level_delta"]
        attackers_win = outcome["attackers_win"]
        old_kitty     = self.kitty_player

        # Level up the leveling team
        if delta > 0:
            cur_idx = RANKS.index(self.team_levels[leveling_team])
            new_idx = min(cur_idx + delta, len(RANKS) - 1)
            self.team_levels[leveling_team] = RANKS[new_idx]

        if not attackers_win:
            # Defenders successfully defended — keep defending, alternate kitty burier
            # Kitty burier rotates within the defending team (0↔2 or 1↔3)
            self.kitty_player = self.kitty_player ^ 2   # toggles: 0↔2, 1↔3
        else:
            # Attackers won — they become new defenders
            self.defending_team = outcome["atk_team"]
            # New kitty burier = player to the right of old kitty burier
            self.kitty_player = (old_kitty + 1) % 4


# ═══════════════════════════════════════════════════════════════
# 10. GAME SCREEN
# ═══════════════════════════════════════════════════════════════

class GameScreen(tk.Frame):
    PLAYER_NAMES = ["You", "Bot R", "Bot T", "Bot L"]
    TEAMS = {0: "Team A (You & Bot T)", 1: "Team B (Bot R & Bot L)"}
    DEAL_SPEED_MS = 110   # ms between dealt cards

    def __init__(self, master, trump_rank, defending_team=0, kitty_player=2):
        super().__init__(master, bg=C["bg"])
        self.master  = master
        self.game    = GameState(trump_rank=trump_rank,
                                 declaring_team=defending_team)
        # Override the default kitty burier to the one passed in
        self.game.declaring_player = kitty_player
        self.bots    = {i: BotPlayer(i) for i in range(1, 4)}
        self.bots[2] = BotPlayer(2)

        self.selected_cards: List[Card] = []
        self.card_widgets:   Dict[int, List[CardWidget]] = {}
        self.message = tk.StringVar(value="")

        self._declare_selected: List[Card] = []

        self._build_ui()
        self._start_dealing()

    # ══════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=C["accent"], pady=4)
        top.pack(fill="x")
        tk.Button(top, text="☰ Menu", font=("Arial",10),
                  bg=C["accent"], fg=C["text"], relief="flat",
                  cursor="hand2", command=self._go_menu).pack(side="left", padx=8)
        self.status_lbl = tk.Label(top, textvariable=self.message,
                                   font=("Arial",12,"bold"),
                                   bg=C["accent"], fg=C["yellow"])
        self.status_lbl.pack(side="left", padx=16)
        tk.Button(top, text="⛶ F11", font=("Arial",10),
                  bg=C["accent"], fg=C["muted"], relief="flat",
                  cursor="hand2",
                  command=self.master._toggle_fs).pack(side="right", padx=8)

        # Info bar
        info_bar = tk.Frame(self, bg=C["dark"], pady=3)
        info_bar.pack(fill="x")
        self.score_lbl = tk.Label(info_bar, text="",
                                  font=("Arial",11), bg=C["dark"], fg=C["green"])
        self.score_lbl.pack(side="left", padx=12)
        self.trump_lbl = tk.Label(info_bar, text="",
                                  font=("Arial",11,"bold"),
                                  bg=C["dark"], fg=C["yellow"])
        self.trump_lbl.pack(side="right", padx=12)

        # Main play area
        self.play_area = tk.Frame(self, bg=C["bg"])
        self.play_area.pack(fill="both", expand=True)
        self.play_area.rowconfigure(1, weight=1)
        self.play_area.columnconfigure(1, weight=1)

        # Player hand zones
        self.zones: Dict[int,tk.Frame] = {}
        for i, pos in enumerate(PLAYER_POSITIONS):
            z = tk.Frame(self.play_area, bg=C["panel"], pady=4)
            if pos == "bottom":
                z.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
            elif pos == "top":
                z.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
            elif pos == "left":
                z.grid(row=1, column=0, sticky="ns", padx=4, pady=4)
            else:
                z.grid(row=1, column=2, sticky="ns", padx=4, pady=4)
            self.zones[i] = z

        # Center area — reused for trick display and dealing info
        self.center_area = tk.Frame(self.play_area, bg=C["accent"],
                                    width=320, height=220)
        self.center_area.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")
        self.center_area.grid_propagate(False)

        # Bottom action bar — declaration panel + play button share this space
        self.action_bar = tk.Frame(self, bg=C["bg"])
        self.action_bar.pack(fill="x", padx=8, pady=4)

        # Declaration panel (shown during dealing)
        self.declare_panel = tk.Frame(self.action_bar, bg=C["bg"])
        self.declare_panel.pack(side="left", fill="x", expand=True)

        self.declare_info = tk.Label(self.declare_panel,
                                     text="Dealing… select a trump-rank card or joker to declare",
                                     font=("Arial",10), bg=C["bg"], fg=C["muted"])
        self.declare_info.pack(side="left", padx=6)

        self.declare_btn = tk.Button(self.declare_panel,
                                     text="🏳  Declare Trump",
                                     font=("Arial",11,"bold"),
                                     bg=C["accent"], fg=C["white"], relief="flat",
                                     padx=14, pady=6, cursor="hand2",
                                     command=self._human_declare,
                                     state="disabled")
        self.declare_btn.pack(side="left", padx=6)

        # Play button (hidden during dealing)
        self.action_btn = tk.Button(self.action_bar,
                                    text="▶  Play Selected Cards",
                                    font=("Arial",13,"bold"),
                                    bg=C["red"], fg=C["white"], relief="flat",
                                    padx=20, pady=8, cursor="hand2",
                                    command=self._human_play,
                                    state="disabled")
        self.action_btn.pack(side="right", padx=6)
        self.action_btn.pack_forget()   # hidden until play phase

        # Log
        log_frame = tk.Frame(self, bg=C["dark"])
        log_frame.pack(fill="x", padx=8, pady=(0,6))
        self.log_text = tk.Text(log_frame, height=3, bg=C["dark"],
                                fg=C["muted"], font=("Arial",9),
                                relief="flat", state="disabled")
        self.log_text.pack(fill="x")

    # ══════════════════════════════════════════════════════
    # DEALING PHASE
    # ══════════════════════════════════════════════════════

    def _start_dealing(self):
        self.message.set(f"Dealing… trump rank is {self.game.trump_rank}")
        self._update_labels()
        self._render_center_dealing()
        self._deal_one()

    def _deal_one(self):
        """Deal a single card, then schedule the next one."""
        result = self.game.deal_next_card()
        if result is None:
            # Dealing complete
            self._dealing_done = True
            self._on_dealing_done()
            return

        player_idx, card = result

        # Re-render the recipient's hand
        self._render_hand(player_idx)

        # Bots may declare after receiving each of their cards
        if player_idx != 0:
            self._bot_maybe_declare(player_idx)

        # Update declare button state
        self._update_declare_btn()
        self._update_labels()

        self.after(self.DEAL_SPEED_MS, self._deal_one)

    def _render_center_dealing(self):
        """Show dealing progress in the center area."""
        for w in self.center_area.winfo_children():
            w.destroy()

        g = self.game
        tk.Label(self.center_area, text="⚙ Dealing",
                 font=("Arial",12,"bold"), bg=C["accent"],
                 fg=C["text"]).pack(pady=(10,4))

        info = (
            f"Trump rank: {g.trump_rank}\n\n"
            "Declare trump by selecting\n"
            "a trump-rank card or joker\n"
            "from your hand, then clicking\n"
            "🏳  Declare Trump below.\n\n"
            "Pairs beat singles.\n"
            "Jokers beat trump-rank cards."
        )
        tk.Label(self.center_area, text=info,
                 font=("Arial",10), bg=C["accent"],
                 fg=C["muted"], justify="center").pack(padx=8)

        self.decl_status_lbl = tk.Label(self.center_area, text="No declaration yet",
                                         font=("Arial",10,"bold"),
                                         bg=C["accent"], fg=C["yellow"])
        self.decl_status_lbl.pack(pady=(8,4))

    def _update_declare_btn(self):
        """Enable declare button only when player 0 has valid declarable cards selected."""
        g = self.game
        if g.phase != GamePhase.DEALING:
            self.declare_btn.config(state="disabled")
            return

        # Check if currently selected cards are a valid bid that beats current
        strength = _bid_strength(self.selected_cards, g.trump_rank)
        if strength > g.declaration_strength:
            self.declare_btn.config(state="normal", bg=C["red"])
        else:
            self.declare_btn.config(state="disabled", bg=C["accent"])

    def _human_declare(self):
        """Player 0 clicks Declare Trump."""
        g = self.game
        cards = self.selected_cards[:]
        ok, msg = g.declare_trump(0, cards)
        if ok:
            suit_name = cards[0].suit if not cards[0].is_joker() else "joker"
            self._log(f"You declared trump: {' '.join(str(c) for c in cards)}"
                      f"  →  Trump suit: {g.trump_suit}")
            self.selected_cards.clear()
            self._update_decl_status()
            self._render_hand(0)
        else:
            self.message.set(f"Invalid declaration: {msg}")
        self._update_declare_btn()

    def _bot_maybe_declare(self, player_idx: int):
        """Let a bot consider declaring after receiving a card."""
        g = self.game
        hand = g.hands[player_idx]
        trump_rank = g.trump_rank

        # Collect trump-rank cards and jokers in hand
        declarable = [c for c in hand
                      if c.rank == trump_rank or c.is_joker()]
        if not declarable:
            return

        # Find best possible bid
        best_cards = None
        best_strength = g.declaration_strength  # must beat this

        # Try pair of same trump-rank suit
        suit_groups: Dict[str, List[Card]] = {}
        for c in declarable:
            suit_groups.setdefault(c.suit, []).append(c)

        for suit, cards in suit_groups.items():
            if len(cards) >= 2:
                strength = _bid_strength(cards[:2], trump_rank)
                if strength > best_strength:
                    best_strength = strength
                    best_cards = cards[:2]

        # Try single if no better pair found
        if best_cards is None:
            for c in declarable:
                strength = _bid_strength([c], trump_rank)
                if strength > g.declaration_strength:
                    # Bots only declare singles early in the deal (first 12 cards)
                    # to simulate realistic caution — don't snap on every card
                    cards_dealt = g._deal_idx
                    if cards_dealt < 12 and random.random() < 0.4:
                        continue
                    if strength > best_strength:
                        best_strength = strength
                        best_cards = [c]

        if best_cards is None:
            return

        # Small chance bot holds back (simulate strategic timing)
        if random.random() < 0.25:
            return

        ok, _ = g.declare_trump(player_idx, best_cards)
        if ok:
            self._log(f"{self.PLAYER_NAMES[player_idx]} declared trump: "
                      f"{' '.join(str(c) for c in best_cards)}"
                      f"  →  Trump suit: {g.trump_suit}")
            self._update_decl_status()

    def _update_decl_status(self):
        """Update the declaration status label in the center area."""
        if not hasattr(self, "decl_status_lbl"):
            return
        g = self.game
        if g.declaration is None:
            self.decl_status_lbl.config(text="No declaration yet",
                                         fg=C["yellow"])
        else:
            pid, cards = g.declaration
            name = self.PLAYER_NAMES[pid]
            card_str = " ".join(str(c) for c in cards)
            strength_names = {1:"single", 2:"pair", 3:"small joker",
                              4:"joker pair", 5:"big joker", 6:"joker pair"}
            s_name = strength_names.get(g.declaration_strength, "")
            self.decl_status_lbl.config(
                text=f"{name}: {card_str} ({s_name})\nTrump → {g.trump_suit}",
                fg=C["green"])

    def _on_dealing_done(self):
        """Called when all cards have been dealt. Transition to kitty phase."""
        g = self.game
        declarer_name = self.PLAYER_NAMES[g.declaring_player]
        self._log(f"Dealing complete. Declarer: {declarer_name} "
                  f"(Team {'A' if g.declaring_team==0 else 'B'}), "
                  f"Trump: {g.trump_suit} {g.trump_rank}")
        self.message.set(f"Dealing done! {declarer_name} declares {g.trump_suit}")

        # Hide declare panel, show play button
        self.declare_panel.pack_forget()
        self.action_btn.pack(side="right", padx=6)

        # Re-render all hands with correct trump sorting
        self._render_all()
        self._update_labels()

        # Kitty burial
        self.after(600, self._do_kitty)

    def _do_kitty(self):
        g = self.game
        dp = g.declaring_player

        if dp == 0:
            # Human player buries kitty
            self._human_bury_kitty()
        else:
            # Bot buries kitty
            to_bury = self.bots[dp].bury_kitty(g.hands[dp], g)
            g.bury_kitty(to_bury)
            self._log(f"{self.PLAYER_NAMES[dp]} buried the kitty.")
            self._render_all()
            self._update_labels()
            self.after(400, self._start_playing)

    def _human_bury_kitty(self):
        """Show kitty to human player, let them pick 8 cards to bury."""
        g = self.game
        # Give human the kitty first
        g.hands[0].extend(g.kitty)
        g.hands[0] = g.trump.sort_hand(g.hands[0])
        g.kitty = []

        self.selected_cards.clear()
        self._render_hand(0)
        self._render_center_kitty()

        self.action_btn.config(
            text=f"🪦  Bury 8 Cards  ({len(self.selected_cards)}/8 selected)",
            state="disabled",
            command=self._human_bury_confirm)
        self.message.set("You won the bid! Select 8 cards to bury into the kitty.")

    def _render_center_kitty(self):
        for w in self.center_area.winfo_children():
            w.destroy()
        tk.Label(self.center_area,
                 text="Select 8 cards to bury\n(they score for last trick winner)",
                 font=("Arial",11), bg=C["accent"], fg=C["text"],
                 justify="center").pack(pady=16, padx=8)
        self.bury_count_lbl = tk.Label(self.center_area,
                                        text="0 / 8 selected",
                                        font=("Arial",14,"bold"),
                                        bg=C["accent"], fg=C["yellow"])
        self.bury_count_lbl.pack()

    def _human_bury_confirm(self):
        if len(self.selected_cards) != 8:
            self.message.set("You must select exactly 8 cards to bury!")
            return
        g = self.game
        g.kitty = self.selected_cards[:]
        for c in self.selected_cards:
            g.hands[0].remove(c)
        g.hands[0] = g.trump.sort_hand(g.hands[0])
        g.phase = GamePhase.PLAYING
        g.current_trick  = Trick(g.trump, 0)
        g.current_player = 0
        self.selected_cards.clear()
        self._log("You buried 8 cards into the kitty.")
        self._render_all()
        self._update_labels()
        self.after(300, self._start_playing)

    # ══════════════════════════════════════════════════════
    # PLAYING PHASE
    # ══════════════════════════════════════════════════════

    def _start_playing(self):
        self.action_btn.config(text="▶  Play Selected Cards",
                               command=self._human_play)
        self._render_center_trick()
        self._next_action()

    def _next_action(self):
        g = self.game
        if g.phase == GamePhase.SCORING:
            self.after(800, self._show_result)
            return

        cp = g.current_player
        self._update_labels()
        self.message.set("Your turn — select cards and click Play"
                         if cp == 0 else
                         f"{self.PLAYER_NAMES[cp]} thinking…")

        if cp == 0:
            self.selected_cards.clear()
            self._render_hand(0)
            self.action_btn.config(state="normal")
        else:
            self.action_btn.config(state="disabled")
            self.after(900, lambda: self._bot_play(cp))

    def _human_play(self):
        g = self.game
        trick = g.current_trick

        if not self.selected_cards:
            self.message.set("Select at least one card first!")
            return

        if not trick.plays:
            # ── LEADING ──────────────────────────────────────
            ok, err = CardCombo.is_valid_lead(self.selected_cards, g.trump)
            if not ok:
                self.message.set(err)
                return
        else:
            # ── FOLLOWING ────────────────────────────────────
            ok, err = CardCombo.is_valid_follow(
                self.selected_cards, trick.led_combo,
                g.hands[0], g.trump)
            if not ok:
                self.message.set(err)
                return

        self._do_play(0, self.selected_cards[:])

    def _bot_play(self, player_idx: int):
        g    = self.game
        bot  = self.bots[player_idx]
        hand = g.hands[player_idx]
        trick = g.current_trick
        cards = bot.choose_play(hand, trick, g)

        if not trick.plays:
            # ── BOT LEADING: must be single-suit ─────────────
            ok, _ = CardCombo.is_valid_lead(cards, g.trump)
            if not ok:
                cards = [g.trump.sort_hand(hand)[0]]
        else:
            # ── BOT FOLLOWING: structure-aware enforcement ────
            ok, _ = CardCombo.is_valid_follow(cards, trick.led_combo, hand, g.trump)
            if not ok:
                cards = CardCombo.build_valid_follow(trick.led_combo, hand, g.trump)

        self._do_play(player_idx, cards)

    def _do_play(self, player_idx: int, cards: List[Card]):
        g = self.game
        self._log(f"{self.PLAYER_NAMES[player_idx]} plays: "
                  f"{' '.join(str(c) for c in cards)}")
        winner = g.play_cards(player_idx, cards)
        self.selected_cards.clear()
        self._render_all()
        self._update_labels()

        if winner is not None:
            pts = g.tricks[-1].points()
            self._log(f"  → {self.PLAYER_NAMES[winner]} wins trick "
                      f"(+{pts} pts)  |  A={g.scores[0]}  B={g.scores[1]}")
            self.after(1200, self._next_action)
        else:
            self.after(400, self._next_action)

    # ══════════════════════════════════════════════════════
    # RENDERING
    # ══════════════════════════════════════════════════════

    def _render_all(self):
        for i in range(4):
            self._render_hand(i)
        if self.game.phase == GamePhase.PLAYING:
            self._render_center_trick()

    def _render_hand(self, player_idx: int):
        zone = self.zones[player_idx]
        for w in zone.winfo_children():
            w.destroy()

        hand    = self.game.hands[player_idx]
        trump   = self.game.trump
        face_up = (player_idx == 0)
        pos     = PLAYER_POSITIONS[player_idx]
        phase   = self.game.phase

        team_tag = "A" if player_idx % 2 == 0 else "B"
        name     = f"{self.PLAYER_NAMES[player_idx]}  [Team {team_tag}]"
        name_col = C["green"] if player_idx % 2 == 0 else C["yellow"]
        tk.Label(zone, text=name, font=("Arial",9,"bold"),
                 bg=C["panel"], fg=name_col).pack()

        hand_frame = tk.Frame(zone, bg=C["panel"])
        hand_frame.pack()

        if pos in ("left", "right"):
            tk.Label(hand_frame,
                     text=f"{'🂠 '*min(len(hand),8)}\n{len(hand)} cards",
                     font=("Arial",10), bg=C["panel"],
                     fg=C["muted"]).pack(padx=4, pady=4)
            return

        if not hand:
            tk.Label(hand_frame, text="(no cards)", font=("Arial",9),
                     bg=C["panel"], fg=C["muted"]).pack()
            return

        overlap  = max(18, min(52, 480 // max(len(hand),1)))
        canvas_w = overlap * (len(hand)-1) + CardWidget.W + 4
        canvas_h = CardWidget.H + 22

        cv = tk.Canvas(hand_frame, width=canvas_w, height=canvas_h,
                       bg=C["panel"], highlightthickness=0)
        cv.pack()

        sorted_hand = trump.sort_hand(hand) if face_up else hand

        # During kitty burial, track selected for bury count display
        is_bury_phase = (phase == GamePhase.KITTY and
                         self.game.declaring_player == 0 and
                         player_idx == 0)

        for idx, card in enumerate(sorted_hand):
            x = idx * overlap
            selected = face_up and card in self.selected_cards

            def make_click(c=card):
                def _click(e):
                    if c in self.selected_cards:
                        self.selected_cards.remove(c)
                    else:
                        self.selected_cards.append(c)
                    # During dealing, update declare button
                    if self.game.phase == GamePhase.DEALING:
                        self._update_declare_btn()
                    # During kitty burial, update bury count
                    if is_bury_phase:
                        n = len(self.selected_cards)
                        if hasattr(self, "bury_count_lbl"):
                            self.bury_count_lbl.config(text=f"{n} / 8 selected")
                        self.action_btn.config(
                            text=f"🪦  Bury 8 Cards  ({n}/8 selected)",
                            state="normal" if n == 8 else "disabled")
                    self._render_hand(0)
                return _click

            cw = CardWidget(hand_frame, card, face_up=face_up,
                            selected=selected, trump=trump, on_click=None)
            y_off = -10 if selected else 0
            wid = cv.create_window(x, 10 + y_off, anchor="nw", window=cw)
            if face_up:
                cv.tag_bind(wid, "<Button-1>", make_click(card))
                cw._canvas.bind("<Button-1>", make_click(card))

    def _render_center_trick(self):
        for w in self.center_area.winfo_children():
            w.destroy()

        trick = self.game.current_trick
        if not trick:
            return

        tk.Label(self.center_area, text="Current Trick",
                 font=("Arial",10,"bold"), bg=C["accent"],
                 fg=C["text"]).pack(pady=(6,4))

        grid  = tk.Frame(self.center_area, bg=C["accent"])
        grid.pack(expand=True)

        positions = {0:(1,1), 1:(1,2), 2:(0,1), 3:(1,0)}
        trump = self.game.trump

        for pid, cards in trick.plays:
            row, col = positions[pid]
            cell = tk.Frame(grid, bg=C["accent"])
            cell.grid(row=row, column=col, padx=8, pady=4)
            tk.Label(cell, text=self.PLAYER_NAMES[pid],
                     font=("Arial",8), bg=C["accent"], fg=C["muted"]).pack()
            cf = tk.Frame(cell, bg=C["accent"])
            cf.pack()
            for c in cards:
                CardWidget(cf, c, face_up=True, trump=trump).pack(side="left", padx=1)

    # ══════════════════════════════════════════════════════
    # LABELS & LOG
    # ══════════════════════════════════════════════════════

    def _update_labels(self):
        g = self.game
        phase_tag = {"dealing":"DEALING","kitty":"KITTY",
                     "playing":"PLAYING","scoring":"DONE"}.get(g.phase,"")
        self.score_lbl.config(
            text=f"[{phase_tag}]  "
                 f"Team A (You & Bot T): {g.scores[0]} pts  |  "
                 f"Team B (Bot R & Bot L): {g.scores[1]} pts  |  "
                 f"Defenders need 80 pts")
        declared = f"{g.trump_suit} {g.trump_rank}" if g.declaration else f"? {g.trump_rank}"
        self.trump_lbl.config(text=f"Trump: {declared}")

    def _log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ══════════════════════════════════════════════════════
    # END OF ROUND
    # ══════════════════════════════════════════════════════

    def _show_result(self):
        g       = self.game
        outcome = g.compute_round_outcome()
        pts     = outcome["attacker_pts"]
        a_win   = outcome["attackers_win"]
        delta   = outcome["level_delta"]
        lteam   = outcome["leveling_team"]
        def_t   = outcome["def_team"]
        atk_t   = outcome["atk_team"]

        PNAMES = self.PLAYER_NAMES
        team_names = {0: "Team A (You & Bot T)", 1: "Team B (Bot R & Bot L)"}
        def_name = team_names[def_t]
        atk_name = team_names[atk_t]
        lev_name = team_names[lteam]

        # Outcome headline
        if not a_win:
            if delta == 2:
                outcome_line = f"Defenders hold!  {def_name} level up by +2"
            else:
                outcome_line = f"Defenders hold!  {def_name} level up by +1"
        else:
            if delta == 0:
                outcome_line = f"Attackers win!  Roles switch, no level change"
            else:
                outcome_line = f"Attackers win!  {atk_name} level up by +{delta}"

        # Build point threshold explanation
        if pts < 40:
            thresh = "0–39 pts → Defenders +2 levels"
        elif pts < 80:
            thresh = "40–79 pts → Defenders +1 level"
        elif pts < 120:
            thresh = "80–119 pts → Attackers win, no bonus"
        elif pts < 160:
            thresh = "120–159 pts → Attackers win +1 level"
        elif pts < 200:
            thresh = "160–199 pts → Attackers win +2 levels"
        else:
            thresh = "200+ pts → Attackers win +3 levels"

        # Preview what happens next round
        app = self.master
        # Simulate advance to preview
        new_levels = list(app.team_levels)
        if delta > 0:
            cur_idx = RANKS.index(new_levels[lteam])
            new_idx = min(cur_idx + delta, len(RANKS) - 1)
            new_levels[lteam] = RANKS[new_idx]
        if not a_win:
            next_def   = def_t
            next_kitty = app.kitty_player ^ 2
        else:
            next_def   = atk_t
            next_kitty = (app.kitty_player + 1) % 4
        next_trump = new_levels[next_def]
        next_def_name = team_names[next_def]
        next_kitty_name = PNAMES[next_kitty]

        detail = (
            f"Attacker points this round: {pts}\n"
            f"({thresh})\n\n"
            f"─────────────────────────────\n"
            f"{outcome_line}\n"
            f"─────────────────────────────\n\n"
            f"Team A score: {g.scores[0]} pts\n"
            f"Team B score: {g.scores[1]} pts\n\n"
            f"Tricks won — A: {sum(1 for _,w in g.trick_winner_log if w%2==0)}  "
            f"B: {sum(1 for _,w in g.trick_winner_log if w%2==1)}\n\n"
            f"═════════════ NEXT ROUND ════════════\n"
            f"Team A level: {new_levels[0]}  |  Team B level: {new_levels[1]}\n"
            f"Defenders: {next_def_name}\n"
            f"Trump rank: {next_trump}\n"
            f"Kitty burier: {next_kitty_name}"
        )

        resp = messagebox.askyesno("Round Over", detail + "\n\nPlay next round?")
        app.advance_round(outcome)
        if resp:
            app._show_start()
        else:
            app.quit()

    def _go_menu(self):
        if messagebox.askyesno("Menu", "Return to main menu?"):
            self.master._show_start()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = TuoLaJiApp()
    app.mainloop()
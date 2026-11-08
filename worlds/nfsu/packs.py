"""Event packs: career events as Archipelago items.

  * #1-#5 are open from the start; #111 keeps its own items ("Finale: #111", "Samantha's Big Tease").
  * Every other event (#6-#110) is in exactly one "Event Pack N". The pack sizes are the game's own event sets
    (sets 2-63; sets without checks - time trials, #110 - count with the set before them), but the seed decides
    which events are in which pack, across all tiers (e.g. one pack = #8, #19, #43, #44, #56).
  * If the item pool has no room for all packs, neighbouring packs are merged (fewer, bigger packs).
  * Tournaments still need their reputation stars in game (record +24, events.py reputation_required).
  * The race map shows at most 12 open events (fixed 12-slot list, 0x00315DD8); the client picks which.
"""
import random
from typing import Dict, List, Sequence, Tuple

from .data.events import CAREER_EVENTS, GOAL_EVENT

START_EVENTS: Tuple[int, ...] = (1, 2, 3, 4, 5)
#: Same as locations.CHOICE_EVENTS (no import: locations -> items -> packs); a test checks they agree.
CHOICE_EVENTS = frozenset(e.number for e in CAREER_EVENTS
                          if any("(Choice)" in u.split(":")[0] for u in e.vanilla_unlocks) or e.number == 15)
#: Events that go into packs: every career event except the start events and the finale.
PACK_EVENTS: Tuple[int, ...] = tuple(e.number for e in CAREER_EVENTS
                                     if e.number not in START_EVENTS and e.number != GOAL_EVENT)


def _vanilla_pack_sizes() -> List[int]:
    sets: Dict[int, List[int]] = {}
    for e in CAREER_EVENTS:
        if e.number in PACK_EVENTS:
            sets.setdefault(e.set, []).append(e.number)
    sizes: List[int] = []
    for key in sorted(sets):
        if sizes and all(n in CHOICE_EVENTS for n in sets[key]):
            sizes[-1] += len(sets[key])       # a set without checks rides with the set before it
        else:
            sizes.append(len(sets[key]))
    return sizes


VANILLA_PACK_SIZES: Tuple[int, ...] = tuple(_vanilla_pack_sizes())
MAX_PACKS = len(VANILLA_PACK_SIZES)
assert sum(VANILLA_PACK_SIZES) == len(PACK_EVENTS)


def pack_item_name(index: int) -> str:
    """1-based."""
    return f"Event Pack {index}"


PACK_ITEM_NAMES: Tuple[str, ...] = tuple(pack_item_name(i) for i in range(1, MAX_PACKS + 1))


def pack_sizes(count: int) -> List[int]:
    """Sizes for `count` packs: the vanilla set sizes, with neighbours merged (smallest pairs first) if fewer."""
    sizes = list(VANILLA_PACK_SIZES)
    count = max(1, min(count, len(sizes)))
    while len(sizes) > count:
        i = min(range(len(sizes) - 1), key=lambda k: (sizes[k] + sizes[k + 1], k))
        sizes[i:i + 2] = [sizes[i] + sizes[i + 1]]
    return sizes


def make_packs(rng: random.Random, count: int) -> List[List[int]]:
    """Shuffles all pack events into `count` packs (sorted event numbers per pack)."""
    sizes = pack_sizes(count)
    rng.shuffle(sizes)
    events = list(PACK_EVENTS)
    rng.shuffle(events)
    packs, pos = [], 0
    for size in sizes:
        packs.append(sorted(events[pos:pos + size]))
        pos += size
    return packs


def pack_of(packs: Sequence[Sequence[int]]) -> Dict[int, str]:
    """event number -> pack item name."""
    return {n: pack_item_name(i + 1) for i, pack in enumerate(packs) for n in pack}

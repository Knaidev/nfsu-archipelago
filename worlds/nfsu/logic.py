"""Logic helpers: performance level per category and reputation (stars) from visual items.

Star model: the stars come from the RECEIVED visual items,
not from what is installed in game (the game does not store a reputation value – it computes it on demand).
  * Every visual category is progressive; reputation = sum over categories of the star value of the highest
    level received (NFS Wiki values). Level 1 parts bought in game don't count.
  * Unique time-trial parts are vanilla rewards (choice events carry no checks) and do not count.
  * Paint, Decals and Vinyls count 0 (no values known).
  * Star gates count full stars only (rounded down).
"""
import math
from typing import TYPE_CHECKING, Callable, Dict, Sequence, Tuple

from BaseClasses import CollectionState

from .data.parts import PERFORMANCE, VISUAL
from .items import VISUAL_ITEM_LEVELS, progressive_name

if TYPE_CHECKING:
    from .world import NFSUWorld

PERFORMANCE_CATEGORIES: Tuple[str, ...] = tuple(c.name for c in PERFORMANCE)

#: Relevant performance categories per race type (design doc 3.3).
RELEVANT_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Drag": ("Engine/Exhaust", "ECU & Fuel", "Turbo", "Nitrous", "Drivetrain", "Tires"),
    "Drift": ("Suspension", "Tires", "Weight Reduction"),
}


def relevant_categories(race_type: str) -> Tuple[str, ...]:
    return RELEVANT_CATEGORIES.get(race_type, PERFORMANCE_CATEGORIES)


# ------------------------------------------------------------------ requirements per tier
# (level, fraction of relevant categories) per tier index 1..5 (5 = finale), per strictness.
TIER_PART_REQUIREMENTS = {
    0: {1: (0, 0.0), 2: (1, 0.5), 3: (2, 0.5), 4: (3, 1 / 3), 5: (3, 2 / 3)},   # loose
    1: {1: (0, 0.0), 2: (1, 1.0), 3: (2, 1.0), 4: (3, 2 / 3), 5: (3, 1.0)},     # normal
    2: {1: (0, 0.0), 2: (1, 1.0), 3: (2, 1.0), 4: (3, 1.0), 5: (3, 1.0)},       # strict
}

#: Based on the original reputation requirements (#30 x2, #66 x3, #91 x3, #101 x4, data/events.py), one step
#: higher from Tier 4 on so every tier needs more stars than the one before. All visual items give 7.6.
BASE_STAR_GATES = {1: 0, 2: 2, 3: 3, 4: 4, 5: 5}


def part_requirement(world: "NFSUWorld", tier: int, race_type: str) -> Tuple[int, int, Tuple[str, ...]]:
    """Returns (level, number of categories, relevant categories)."""
    tier = min(tier, 5)
    level, fraction = TIER_PART_REQUIREMENTS[world.options.logic_strictness.value][tier]
    cats = relevant_categories(race_type)
    return level, math.ceil(fraction * len(cats)), cats


def star_gate(world: "NFSUWorld", tier: int) -> int:
    """Stars needed to enter a tier. The finale (5) is always gated; Tiers 2-4 only with star_gates."""
    if tier < 5 and not world.options.star_gates:
        return 0
    return BASE_STAR_GATES[tier] * world.options.star_gate_scale.value // 100


# ------------------------------------------------------------------ state helpers
def part_level(state: CollectionState, player: int, category: str) -> int:
    # Always progressive: in game Level 3 can only be installed on top of Level 2, and 2 on top of 1.
    return min(3, state.count(progressive_name(category), player))


def has_parts(state: CollectionState, player: int, level: int, count: int, categories: Sequence[str]) -> bool:
    if level <= 0 or count <= 0:
        return True
    have = 0
    for cat in categories:
        if part_level(state, player, cat) >= level:
            have += 1
            if have >= count:
                return True
    return False


_VISUAL = {c.name: c for c in VISUAL}


def reputation_from(count: Callable[[str], int]) -> float:
    """Stars from received items. `count(item_name)` -> how many of that item were received.
    Shared by the generator logic and the client, so both always agree."""
    reps: Dict[str, float] = {}
    for cat, levels in VISUAL_ITEM_LEVELS.items():
        got = min(count(progressive_name(cat)), len(levels))
        reps[cat] = (_VISUAL[cat].rep[levels[got - 1] - 1] or 0.0) if got else 0.0
    # Unique parts from time trials are vanilla rewards (no items) and do not count for the star gates.
    return round(sum(reps.values()), 2)


def full_stars(reputation_value: float) -> int:
    """Star gates count full stars only (rounded down)."""
    return int(math.floor(reputation_value + 1e-9))


def reputation(state: CollectionState, player: int) -> float:
    return reputation_from(lambda name: state.count(name, player))


def has_stars(state: CollectionState, player: int, stars: int) -> bool:
    return stars <= 0 or full_stars(reputation(state, player)) >= stars


def max_reputation() -> float:
    """Reputation with every visual item collected (used by tests)."""
    return reputation_from(lambda name: 3)


def starting_reputation() -> float:
    """Reputation before any visual item arrived (Level 1 parts you buy yourself do not count)."""
    return reputation_from(lambda name: 0)

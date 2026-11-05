"""Performance and visual part data for Need for Speed: Underground (PS2).

Sources (NFS Wiki, retrieved 2026-11-04):
  Performance: https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Customisation/Performance and sub-pages
  Visual:      https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Customisation/Visual and sub-pages
  Unlock events: the "Unlocks" sections of the individual event pages (see events.py).

"rep" is the reputation (star) value the wiki lists for one installed part of that level
("Rep: +0.5 ★"). Values are fractional, so partial stars exist. Reputation appears to be
per car (it is shown on the car), see TODO below.
"""
from typing import Dict, NamedTuple, Optional, Tuple


class PerformanceCategory(NamedTuple):
    name: str
    cost: Tuple[int, int, int]           # Bank for Level 1 (Street), 2 (Pro), 3 (Extreme)
    unlock_event: Tuple[int, int, int]   # vanilla event that unlocks Level 1/2/3
    affects: Tuple[str, ...]             # rating(s) the wiki says the part improves


PERFORMANCE: Tuple[PerformanceCategory, ...] = (
    PerformanceCategory("Engine/Exhaust", (500, 1000, 2000), (6, 30, 66), ("acceleration",)),
    PerformanceCategory("Drivetrain", (500, 1000, 2000), (6, 30, 66), ("top speed",)),
    PerformanceCategory("Tires", (500, 1000, 2000), (6, 30, 66), ("handling",)),
    PerformanceCategory("ECU & Fuel", (1000, 2000, 4000), (9, 38, 80), ("acceleration", "top speed")),
    PerformanceCategory("Turbo", (1000, 2000, 4000), (9, 38, 80), ("acceleration",)),
    PerformanceCategory("Brakes", (1000, 2000, 4000), (9, 38, 80), ("handling",)),
    PerformanceCategory("Weight Reduction", (750, 1500, 3000), (14, 48, 91), ("acceleration", "handling")),
    PerformanceCategory("Suspension", (750, 1500, 3000), (14, 48, 91), ("handling",)),
    PerformanceCategory("Nitrous", (750, 1500, 3000), (14, 48, 91), ("top speed", "acceleration")),
)

#: Bank needed to buy Level 1-3 in every category once (one car): 47,250.
PERFORMANCE_TOTAL_COST = sum(sum(c.cost) for c in PERFORMANCE)


class VisualCategory(NamedTuple):
    name: str
    cost: Tuple[Optional[int], Optional[int], Optional[int]]   # per part, Level 1/2/3 (None = level does not exist)
    rep: Tuple[Optional[float], Optional[float], Optional[float]]
    unlock_event: Tuple[Optional[int], Optional[int], Optional[int]]  # 0 = available from the start


VISUAL: Tuple[VisualCategory, ...] = (
    VisualCategory("Front Bumper", (500, 1000, 1500), (0.4, 0.7, 1.1), (0, 44, 90)),
    VisualCategory("Rear Bumper", (500, 1000, 1500), (0.4, 0.7, 1.1), (0, 49, 100)),
    VisualCategory("Side Skirts", (400, 800, 1200), (0.4, 0.6, 0.9), (0, 39, 84)),
    VisualCategory("Spoiler", (300, 600, 900), (0.3, 0.5, 0.8), (0, 45, 93)),
    VisualCategory("Hood", (300, 600, 900), (0.3, 0.5, 0.8), (0, 43, 89)),
    VisualCategory("Roof Scoop", (None, 400, 600), (None, 0.4, 0.6), (None, 31, 70)),
    VisualCategory("Rims", (400, 800, 1200), (0.3, 0.5, 0.8), (0, 34, 81)),
    VisualCategory("Neon", (200, 400, 600), (0.1, 0.3, 0.4), (0, 18, 62)),
    VisualCategory("Muffler Tip", (None, 200, 300), (None, 0.1, 0.2), (None, 28, 54)),
    VisualCategory("Window Tint", (100, 200, 300), (0.1, 0.1, 0.1), (0, 29, 56)),
    # Headlights/Taillights: the wiki lists one tier (4 parts, 600 Bank, +0.4) without a level heading.
    # Event pages #60 / #61 say they unlock "Level 3". TODO: confirm there is no Level 1/2.
    VisualCategory("Headlights", (None, None, 600), (None, None, 0.4), (None, None, 60)),
    VisualCategory("Taillights", (None, None, 600), (None, None, 0.4), (None, None, 61)),
    # Paint and Decals: unlock events known, but the wiki gives no cost / reputation values.
    # TODO: measure in game (reputation before/after applying).
    VisualCategory("Paint", (None, None, None), (None, None, None), (0, 23, 65)),
    VisualCategory("Decals", (None, None, None), (None, None, None), (0, 12, 51)),
)


class UniqueReward(NamedTuple):
    event: int
    item_name: str
    kind: str                   # "performance" or "visual"
    choices: Tuple[str, ...]    # vanilla lets the player pick ONE of these
    rep: Optional[float]        # reputation value of the visual part (performance: None)


UNIQUE_REWARDS: Tuple[UniqueReward, ...] = (
    UniqueReward(7, "TJ's Time Trial", "performance", ("Engine/Exhaust", "Drivetrain", "Tires"), None),
    UniqueReward(15, "Jail Break", "visual", ("Hood: Formula-Style CF", "Hood: G-Force", "Hood: Speed CF"), 1.3),
    UniqueReward(26, "Keep Them Coming", "performance",
                 ("Brakes", "Drivetrain", "Engine/Exhaust", "ECU & Fuel", "Turbo", "Tires"), None),
    UniqueReward(47, "Blue Light Special", "visual",
                 ('Rims: Enkei Arashi', 'Rims: Enkei Silverstar', 'Rims: NFSU Livia', 'Rims: Momo Vantage',
                  'Rims: O.Z. Superleggera'), 1.3),
    # Vinyl reputation value not listed on the wiki. TODO: measure.
    UniqueReward(68, "Dead of Night", "visual", tuple(f"Vinyl: Samantha Custom {i}" for i in range(1, 11)), None),
    UniqueReward(77, "Samantha's Big Tease", "visual", ("Spoiler: Dual GT", "Spoiler: Duotek", "Spoiler: Katana"), 1.3),
    UniqueReward(96, "Mods to the Max", "performance",
                 ("Brakes", "Drivetrain", "Nitrous", "Suspension", "Turbo", "Tires", "Weight Reduction"), None),
    # Not a time trial, but an optional event with a unique visual reward (not in the original design doc).
    UniqueReward(110, "Good Samaritan", "visual", ("Wide Body Kit: Mantis", "Wide Body Kit: Vapor"), 4.0),
)

#: Option values for `mods_to_the_max_choice` (vanilla choices at event #96).
MODS_TO_THE_MAX_CHOICES = UNIQUE_REWARDS[6].choices

#: Highest reputation from regular (non-unique) visual parts on one car, Level 3 everywhere,
#: excluding Paint/Decals/Vinyl (unknown): 7.6.
MAX_REP_LEVEL3_KNOWN = round(sum(c.rep[2] or 0 for c in VISUAL), 1)

# TODO (in game): Is reputation per car? Is the multiplier the rounded-down star sum?
#                 What is the cap (the user remembers 5 stars; the wiki shows requirements up to x4)?
#                 Does a Wide Body Kit replace bumper/skirt reputation or add to it?

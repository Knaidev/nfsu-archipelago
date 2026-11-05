"""Locations (checks).

Check model:
  * Every vanilla reward of an event is a check ("#6 Rookie Tournament - Engine/Exhaust Packages: Level 1 (Street)").
    The game shows that reward in its "Race Victory Reward" popup, where the client can put the Archipelago item.
  * Events without a vanilla reward get one "Victory" check (shown in the Bank popup every win has).
  * Optional (style_point_checks): the first N style point milestones.
  * No extra checks per difficulty (there is no reward popup for them).
  * Choice events (the 7 time trials and #110) have NO checks: their reward is a choice of one part, so two items
    there could never both be taken. They stay playable and time trials still count for the finale.
"""
from typing import TYPE_CHECKING, Dict, List, Tuple

from BaseClasses import Location, LocationProgressType

from .data.events import CAREER_EVENTS, GOAL_EVENT, EventData
from .data.style_points import STYLE_MILESTONES
from .items import BASE_ID, GAME_NAME
from .options import option_value

if TYPE_CHECKING:
    from .world import NFSUWorld


#: Tier of each event range (design doc 3.3). Tier 5 = finale.
TIER_RANGES = {1: (1, 29), 2: (30, 65), 3: (66, 90), 4: (91, 110), 5: (111, 111)}
TIER_REGION = {1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4", 5: "Finale"}

#: Events whose vanilla reward is a choice (time trials + #110 "Good Samaritan"): no checks there.
CHOICE_EVENTS = frozenset(e.number for e in CAREER_EVENTS
                          if any("(Choice)" in u.split(":")[0] for u in e.vanilla_unlocks) or e.number == 15)
TIME_TRIAL_EVENTS = tuple(e.number for e in CAREER_EVENTS if e.race_type == "Time Trial")


class NFSULocation(Location):
    game = GAME_NAME


def tier_of(event_number: int) -> int:
    for tier, (lo, hi) in TIER_RANGES.items():
        if lo <= event_number <= hi:
            return tier
    raise ValueError(event_number)


def exclusion_type(event: EventData) -> str:
    """Name used by the excluded_race_types option."""
    return "Tournament" if event.tournament else event.race_type


def _reward_label(unlock: str) -> str:
    # "Performance Upgrades: Engine/Exhaust Packages: Level 1 (Street)" -> "Engine/Exhaust Packages: Level 1 (Street)"
    return unlock.split(": ", 1)[1] if ": " in unlock else unlock


def base_check_names(event: EventData) -> List[str]:
    """Checks sent for the first win of an event (any difficulty)."""
    rewards = [_reward_label(u) for u in event.vanilla_unlocks]
    if not rewards:
        rewards = ["Victory"]
    return [f"#{event.number} {event.name} - {r}" for r in rewards]


def won_name(event: EventData) -> str:
    return f"#{event.number} {event.name} (Won)"


def style_check_name(index: int) -> str:
    m = STYLE_MILESTONES[index]
    return f"Style Points {m.points:,} - {m.reward}"


#: Events that carry checks: every career event except the goal and the choice events.
CHECK_EVENTS: List[EventData] = [e for e in CAREER_EVENTS
                                 if e.number != GOAL_EVENT and e.number not in CHOICE_EVENTS]
#: Events that are raced but carry no checks (time trials count for the finale).
CHOICE_EVENT_DATA: List[EventData] = [e for e in CAREER_EVENTS if e.number in CHOICE_EVENTS]
GOAL_EVENT_DATA = next(e for e in CAREER_EVENTS if e.number == GOAL_EVENT)
GOAL_LOCATION = f"#{GOAL_EVENT_DATA.number} {GOAL_EVENT_DATA.name}"

LOCATION_NAME_TO_ID: Dict[str, int] = {}
#: event number -> its check ids (rewards or Victory) – used by the client.
EVENT_CHECK_IDS: Dict[int, Tuple[int, ...]] = {}
for _e in CHECK_EVENTS:
    _ids = []
    for _i, _name in enumerate(base_check_names(_e)):
        assert _i < 16
        LOCATION_NAME_TO_ID[_name] = BASE_ID + _e.number * 16 + _i
        _ids.append(LOCATION_NAME_TO_ID[_name])
    EVENT_CHECK_IDS[_e.number] = tuple(_ids)
STYLE_CHECK_IDS: Tuple[int, ...] = tuple(BASE_ID + 0x4000 + i for i in range(len(STYLE_MILESTONES)))
for _i in range(len(STYLE_MILESTONES)):
    LOCATION_NAME_TO_ID[style_check_name(_i)] = STYLE_CHECK_IDS[_i]

LOCATION_NAME_GROUPS: Dict[str, set] = {}
for _e in CHECK_EVENTS:
    for _n in base_check_names(_e):
        LOCATION_NAME_GROUPS.setdefault(TIER_REGION[tier_of(_e.number)], set()).add(_n)
        LOCATION_NAME_GROUPS.setdefault(exclusion_type(_e), set()).add(_n)
LOCATION_NAME_GROUPS["Style Points"] = {style_check_name(i) for i in range(len(STYLE_MILESTONES))}


def style_tier(index: int) -> int:
    """Rough tier in which a style milestone is reached in a normal career (3,000,000 points in total)."""
    share = STYLE_MILESTONES[index].points / STYLE_MILESTONES[-1].points
    return 1 if share <= 0.15 else 2 if share <= 0.4 else 3 if share <= 0.7 else 4


def check_count(world: "NFSUWorld") -> int:
    return sum(len(base_check_names(e)) for e in CHECK_EVENTS) + option_value(world.options, "style_point_checks")


def create_all_locations(world: "NFSUWorld") -> None:
    from .items import RACE_WON, TIME_TRIAL_WON, VICTORY, create_event

    opts = world.options
    excluded = world.effective_excluded_types
    race_count_goal = opts.goal == opts.goal.option_race_count

    def add(region, name, address):
        loc = NFSULocation(world.player, name, address, region)
        region.locations.append(loc)
        return loc

    for event in CHECK_EVENTS:
        region = world.get_region(TIER_REGION[tier_of(event.number)])
        for name in base_check_names(event):
            loc = add(region, name, LOCATION_NAME_TO_ID[name])
            if exclusion_type(event) in excluded:
                loc.progress_type = LocationProgressType.EXCLUDED
        if race_count_goal:
            add(region, won_name(event), None).place_locked_item(create_event(world, RACE_WON))

    # Choice events: no checks, but time trial wins count for the finale.
    for event in CHOICE_EVENT_DATA:
        if event.race_type == "Time Trial":
            region = world.get_region(TIER_REGION[tier_of(event.number)])
            add(region, won_name(event), None).place_locked_item(create_event(world, TIME_TRIAL_WON))

    for i in range(option_value(opts, "style_point_checks")):
        region = world.get_region(TIER_REGION[style_tier(i)])
        name = style_check_name(i)
        add(region, name, LOCATION_NAME_TO_ID[name])

    if not race_count_goal:
        finale = world.get_region(TIER_REGION[5])
        add(finale, GOAL_LOCATION, None).place_locked_item(create_event(world, VICTORY))

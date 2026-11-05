from typing import TYPE_CHECKING

from BaseClasses import CollectionState
from worlds.generic.Rules import set_rule

from .items import FINALE_ITEM, KEY_ITEM, RACE_WON, TIME_TRIAL_WON, VICTORY
from .locations import (CHECK_EVENTS, CHOICE_EVENT_DATA, GOAL_LOCATION, TIER_REGION, base_check_names,
                        style_check_name, style_tier, tier_of, won_name)
from .logic import has_parts, has_stars, part_requirement, star_gate
from .options import option_value

if TYPE_CHECKING:
    from .world import NFSUWorld


def _parts_rule(world: "NFSUWorld", tier: int, race_type: str):
    level, count, cats = part_requirement(world, tier, race_type)
    player = world.player
    if level <= 0 or count <= 0:
        return None
    return lambda state: has_parts(state, player, level, count, cats)


def set_all_rules(world: "NFSUWorld") -> None:
    opts = world.options
    player = world.player
    race_count_goal = opts.goal == opts.goal.option_race_count

    # Tier entrances: star gates.
    for tier, region_name in TIER_REGION.items():
        if tier == 5 and race_count_goal:
            continue
        entrance = world.get_entrance(f"To {region_name}")
        stars = star_gate(world, tier)
        if tier == 5:
            tt_needed = opts.time_trials_required.value

            def finale_rule(state: CollectionState, stars=stars, tt_needed=tt_needed) -> bool:
                return (state.has_all((FINALE_ITEM, KEY_ITEM), player)
                        and state.count(TIME_TRIAL_WON, player) >= tt_needed
                        and has_stars(state, player, stars))
            set_rule(entrance, finale_rule)
        elif stars > 0:
            set_rule(entrance, lambda state, stars=stars: has_stars(state, player, stars))

    # Checks (rewards / Victory) expect the parts of the event's tier.
    for event in CHECK_EVENTS:
        base = _parts_rule(world, tier_of(event.number), event.race_type)
        if base is None:
            continue
        for name in base_check_names(event) + ([won_name(event)] if race_count_goal else []):
            set_rule(world.get_location(name), base)
    for event in CHOICE_EVENT_DATA:
        rule = _parts_rule(world, tier_of(event.number), event.race_type)
        if event.race_type == "Time Trial" and rule is not None:
            set_rule(world.get_location(won_name(event)), rule)
    for i in range(option_value(opts, "style_point_checks")):
        rule = _parts_rule(world, style_tier(i), "Sprint")
        if rule is not None:
            set_rule(world.get_location(style_check_name(i)), rule)

    if race_count_goal:
        needed = opts.races_for_goal.value
        world.multiworld.completion_condition[player] = \
            lambda state: state.count(RACE_WON, player) + state.count(TIME_TRIAL_WON, player) >= needed
    else:
        finale_parts = _parts_rule(world, 5, "Sprint")
        if finale_parts is not None:
            set_rule(world.get_location(GOAL_LOCATION), finale_parts)
        world.multiworld.completion_condition[player] = lambda state: state.has(VICTORY, player)

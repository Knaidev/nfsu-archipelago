from dataclasses import dataclass
from typing import Any

from Options import (Choice, DeathLink, DefaultOnToggle, OptionCounter, OptionGroup, OptionSet,
                     PerGameCommonOptions, Range, Toggle)


RACE_TYPES = ("Circuit", "Sprint", "Drag", "Drift", "Knockout", "Tournament")
TRAPS = ("Nitro Drain Trap", "Grip Loss Trap", "Power Cut Trap", "Bank Tax Trap",
         "Style Crash Trap", "HUD Blackout Trap", "Pink Paint Trap")


# ---------------------------------------------------------------- Goal and scope
class Goal(Choice):
    """What you need to do to finish.
    finale: Win #111 "Wrath of Eddie". It unlocks once you have the required time trials,
            the "Finale: #111" item and "Samantha's Big Tease".
    race_count: Win a set number of events (see Races For Goal)."""
    display_name = "Goal"
    option_finale = 0
    option_race_count = 1
    default = 0


class RacesForGoal(Range):
    """Number of won events needed when Goal is race_count."""
    display_name = "Races For Goal"
    range_start = 10
    range_end = 100
    default = 80


class TimeTrialsRequired(Range):
    """How many of the 7 time trials must be won (any difficulty) before #111 unlocks."""
    display_name = "Time Trials Required"
    range_start = 0
    range_end = 7
    default = 7


# The checks of an event are its vanilla rewards (shown in the game's reward popup) – or one "Victory" check for
# events without a reward – sent for the first win on any difficulty. Time trials and #110 (rewards you choose
# from) have no checks. There are no extra checks per difficulty.


class StylePointChecks(Range):
    """EXPERIMENTAL – the client cannot read style points yet, so these checks can't be sent.
    Number of style point milestones (5,000 up to 3,000,000 points, 114 in total) that are checks."""
    display_name = "Style Point Checks"
    range_start = 0
    range_end = 114
    default = 0


class ExcludedRaceTypes(OptionSet):
    """Events of these types only hold filler items (they are excluded locations).
    Valid: Circuit, Sprint, Drag, Drift, Knockout, Tournament. Time trials cannot be excluded."""
    display_name = "Excluded Race Types"
    valid_keys = RACE_TYPES
    default = frozenset()


# ---------------------------------------------------------------- Logic
class LogicStrictness(Choice):
    """How many performance part categories logic expects before a tier's events are in logic.
    loose: about half of the relevant categories, one level lower at the end.
    normal: all relevant categories at the tier's level (Tier 4: Level 3 in 6 of 9).
    strict: all relevant categories at the tier's level, including Tier 4."""
    display_name = "Logic Strictness"
    option_loose = 0
    option_normal = 1
    option_strict = 2
    default = 1


class EventPacks(DefaultOnToggle):
    """Events are items. #1-#5 are open from the start; every other event is in one of up to 54
    "Event Pack" items, and the seed decides which events are in which pack (across all tiers).
    Tournaments still need their reputation stars in game. Off: tiers open by Star Gates as in 0.1."""
    display_name = "Event Packs"


class StartingEventPacks(Range):
    """Event Packs you start with (chosen among packs with at least one Tier 1 race)."""
    display_name = "Starting Event Packs"
    range_start = 0
    range_end = 10
    default = 2


class StarGates(Toggle):
    """Also lock tiers behind reputation stars from the visual parts you received (full stars, rounded down,
    using the game's star value per level): Tier 2 needs 2 stars, Tier 3 needs 3, Tier 4 needs 4. The finale
    always needs 5 (before scaling). Without Event Packs you most likely want this on."""
    display_name = "Star Gates"


class StarGateScale(Range):
    """Lower the star requirements to this percentage (rounded down)."""
    display_name = "Star Gate Scale"
    range_start = 50
    range_end = 100
    default = 100


class EarlyLevel1Parts(DefaultOnToggle):
    """Place the Level 1 performance parts early (sphere 1) in your own or another world."""
    display_name = "Early Level 1 Parts"


class LocalKeyItems(Toggle):
    """Keep "Finale: #111" and "Samantha's Big Tease" in your own game."""
    display_name = "Local Key Items"


# ---------------------------------------------------------------- Items and economy
# Performance parts are always progressive (Level 1, then 2, then 3): in game Level 3 can only be
# installed on top of Level 2, and Level 2 on top of Level 1.


# Visual parts are progressive per category (e.g. "Progressive Spoiler": Level 2, then Level 3 in the shop).
# You buy and install them yourself; the stars for the star gates count from the received items.


class CarsAsItems(DefaultOnToggle):
    """Cars are items: race wins no longer unlock cars, the car items do (15 cars, more with a random
    starting car)."""
    display_name = "Cars As Items"


class StartingCar(Choice):
    """vanilla: all five starter cars are available as usual.
    random_starter: one random starter car is available; the other four become items.
    random_car: one random car of all 20 is available; all other cars become items.
    The random options need Cars As Items."""
    display_name = "Starting Car"
    option_vanilla = 0
    option_random_starter = 2
    option_random_car = 1
    default = 0


class StartingBank(Range):
    """Bank you start with on top of the game's own starting money."""
    display_name = "Starting Bank"
    range_start = 0
    range_end = 10000
    default = 0


class BankMultiplier(Range):
    """Percentage applied to Bank Bonus items."""
    display_name = "Bank Multiplier"
    range_start = 50
    range_end = 300
    default = 100


class VanillaBankRewards(DefaultOnToggle):
    """Keep paying the game's normal Bank for winning events."""
    display_name = "Vanilla Bank Rewards"




# ---------------------------------------------------------------- Death Link and traps
# Death Link: sending and receiving live tested (drag + sprint). Traps have no in-game effect yet.
class NFSUDeathLink(DeathLink):
    """When you lose a race (or blow your engine in a drag), everyone with Death Link "dies".
    When someone else dies while you race, your engine blows ("Blown Engine") and you are out of the race."""


class DeathLinkTrigger(Choice):
    """What sends a death.
    lose_race: not finishing first (or failing the time/score target).
    last_place: finishing last."""
    display_name = "Death Link Trigger"
    option_lose_race = 0
    option_last_place = 1
    default = 0


class DeathLinkEffect(Choice):
    """What a received death does.
    fail_race: your engine blows ("Blown Engine") and the current race is lost.
    nitro_and_slowdown: nitrous is emptied and the car is slowed for a few seconds."""
    display_name = "Death Link Effect"
    option_fail_race = 0
    option_nitro_and_slowdown = 1
    default = 0


class DeathLinkAmnesty(Range):
    """Number of lost races that are ignored before a death is sent."""
    display_name = "Death Link Amnesty"
    range_start = 0
    range_end = 5
    default = 0


class TrapPercentage(Range):
    """EXPERIMENTAL – only the Bank Tax Trap works in game yet; the other traps do nothing.
    Percentage of filler items that are traps. The generator lowers it if needed to keep
    enough Bank in the pool (see Vanilla Bank Rewards)."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


class TrapWeights(OptionCounter):
    """Relative weight of each trap (0 disables it)."""
    display_name = "Trap Weights"
    valid_keys = TRAPS
    min = 0
    max = 100
    default = {trap: 10 for trap in TRAPS}


@dataclass
class NFSUOptions(PerGameCommonOptions):
    goal: Goal
    races_for_goal: RacesForGoal
    time_trials_required: TimeTrialsRequired
    excluded_race_types: ExcludedRaceTypes
    logic_strictness: LogicStrictness
    event_packs: EventPacks
    starting_event_packs: StartingEventPacks
    star_gates: StarGates
    star_gate_scale: StarGateScale
    early_level_1_parts: EarlyLevel1Parts
    local_key_items: LocalKeyItems
    cars_as_items: CarsAsItems
    starting_car: StartingCar
    starting_bank: StartingBank
    bank_multiplier: BankMultiplier
    vanilla_bank_rewards: VanillaBankRewards
    death_link: NFSUDeathLink
    death_link_trigger: DeathLinkTrigger
    death_link_amnesty: DeathLinkAmnesty


#: Options that exist in code but are not offered yet, because the client cannot do them in game (0.1):
#: StylePointChecks (style points not found), DeathLinkEffect (only "fail_race" works), TrapPercentage /
#: TrapWeights (trap effects not found). To offer one again, add it to NFSUOptions and OPTION_GROUPS.
DORMANT_DEFAULTS = {
    "style_point_checks": StylePointChecks.default,
    "death_link_effect": DeathLinkEffect.default,
    "trap_percentage": TrapPercentage.default,
    "trap_weights": TrapWeights.default,
}


def option_value(options: NFSUOptions, name: str) -> Any:
    """Value of an option, or the default of a dormant option that is not offered in this version."""
    option = getattr(options, name, None)
    return option.value if option is not None else DORMANT_DEFAULTS[name]


OPTION_GROUPS = [
    OptionGroup("Goal and Scope", [Goal, RacesForGoal, TimeTrialsRequired, ExcludedRaceTypes]),
    OptionGroup("Logic", [EventPacks, StartingEventPacks, LogicStrictness, StarGates, StarGateScale,
                          EarlyLevel1Parts, LocalKeyItems]),
    OptionGroup("Items and Economy", [CarsAsItems, StartingCar, StartingBank, BankMultiplier,
                                      VanillaBankRewards]),
    OptionGroup("Death Link", [NFSUDeathLink, DeathLinkTrigger, DeathLinkAmnesty], start_collapsed=True),
]

# Webhost presets (OptionSet/OptionCounter options are not allowed here).
PRESETS = {
    "Relaxed": {
        "logic_strictness": "loose",
        "star_gate_scale": 75,
        "bank_multiplier": 200,
        "starting_bank": 5000,
        "death_link": False,
    },
    "Standard": {
        "logic_strictness": "normal",
        "bank_multiplier": 100,
        "death_link": False,
    },
    "Hardcore": {
        "logic_strictness": "strict",
        "starting_car": "random_starter",
        "vanilla_bank_rewards": False,
    },
}

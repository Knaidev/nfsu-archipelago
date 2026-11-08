from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional

from BaseClasses import Item, ItemClassification as IC

from .data.cars import CARS, STARTER_CARS, UNLOCKABLE_CARS
from .data.parts import PERFORMANCE, UNIQUE_REWARDS, VISUAL
from .options import TRAPS, option_value
from .packs import PACK_ITEM_NAMES

if TYPE_CHECKING:
    from .world import NFSUWorld

GAME_NAME = "Need for Speed Underground"
BASE_ID = 0x4E465500  # "NFU\0" – stays below 2**31

FINALE_ITEM = "Finale: #111"
KEY_ITEM = "Samantha's Big Tease"
VICTORY = "Victory"                 # event item on #111
RACE_WON = "Race Won"               # event item, one per won event (race_count goal)
TIME_TRIAL_WON = "Time Trial Won"   # event item, one per won time trial


class NFSUItem(Item):
    game = GAME_NAME


class ItemData(NamedTuple):
    code: int
    classification: IC
    group: str


def progressive_name(category: str) -> str:
    return f"Progressive {category}"


#: Every visual category is a progressive item: each copy opens the next level in the shop (Level 1 stays
#: available from the start). The player buys and installs the parts; the stars count from the items.
#: E.g. Front Bumper [2, 3]: first item -> Level 2, second -> Level 3. Headlights/Taillights only have Level 3.
VISUAL_ITEM_LEVELS: Dict[str, List[int]] = {
    c.name: [lvl + 1 for lvl, ev in enumerate(c.unlock_event) if ev not in (None, 0)]
    for c in VISUAL
}

UNIQUE_ITEM_NAMES: Dict[int, str] = {
    7: "Unique Performance Part (TJ's Time Trial)",
    15: "Unique Hood (Jail Break)",
    26: "Unique Performance Part (Keep Them Coming)",
    47: "Unique Rims (Blue Light Special)",
    68: "Unique Vinyl (Dead of Night)",
    77: KEY_ITEM,
    96: "Unique Performance Part (Mods to the Max)",
    110: "Wide Body Kit (Good Samaritan)",
}
assert set(UNIQUE_ITEM_NAMES) == {u.event for u in UNIQUE_REWARDS}

BANK_ITEMS: Dict[str, int] = {
    "Bank Bonus (500)": 500,
    "Bank Bonus (1000)": 1000,
    "Bank Bonus (2500)": 2500,
    "Bank Bonus (5000)": 5000,
    "Bank Bonus (10000)": 10000,
}


def car_item_name(car: str) -> str:
    return f"Car: {car}"


def _build_table() -> Dict[str, ItemData]:
    # Order matters: IDs are assigned in this order. Only ever append.
    table: Dict[str, ItemData] = {}
    code = BASE_ID

    def add(name: str, cls: IC, group: str) -> None:
        nonlocal code
        table[name] = ItemData(code, cls, group)
        code += 1

    add(FINALE_ITEM, IC.progression, "Key Items")
    add(KEY_ITEM, IC.progression, "Key Items")
    for cat in PERFORMANCE:
        add(progressive_name(cat.name), IC.progression, "Performance Parts")
    for cat in VISUAL_ITEM_LEVELS:
        add(progressive_name(cat), IC.progression, "Visual Parts")
    # Unique time-trial parts are no items: the game gives them itself (choice events carry no checks).
    for car in CARS:
        add(car_item_name(car.name), IC.useful, "Cars")
    for name in BANK_ITEMS:
        add(name, IC.filler, "Bank")
    for trap in TRAPS:
        add(trap, IC.trap, "Traps")
    for name in PACK_ITEM_NAMES:     # 0.2: events as items (packs.py)
        add(name, IC.progression, "Event Packs")
    return table


ITEM_TABLE: Dict[str, ItemData] = _build_table()
ITEM_NAME_TO_ID: Dict[str, int] = {name: data.code for name, data in ITEM_TABLE.items()}

ITEM_NAME_GROUPS: Dict[str, set] = {}
for _name, _data in ITEM_TABLE.items():
    ITEM_NAME_GROUPS.setdefault(_data.group, set()).add(_name)


def create_item(world: "NFSUWorld", name: str) -> NFSUItem:
    data = ITEM_TABLE[name]
    return NFSUItem(name, data.classification, data.code, world.player)


def create_event(world: "NFSUWorld", name: str) -> NFSUItem:
    return NFSUItem(name, IC.progression, None, world.player)


# ------------------------------------------------------------------ pool

#: Bank needed to buy every performance level and one visual part per level the items open (one car).
#: Paint/decal prices are unknown (not counted).
REQUIRED_BANK = (sum(sum(c.cost) for c in PERFORMANCE)
                 + sum(c.cost[lvl - 1] or 0 for c in VISUAL for lvl in VISUAL_ITEM_LEVELS[c.name]))
BANK_SAFETY_FACTOR = 1.25


def car_pool(world: "NFSUWorld") -> List[str]:
    """Car items: the cars that unlock through events, plus the other starter cars when the start car is random.
    The start car itself is given at the start (world.create_items)."""
    if not world.options.cars_as_items:
        return []
    cars = [c.name for c in UNLOCKABLE_CARS]
    if world.starting_car is not None:
        cars = [c for c in STARTER_CARS if c != world.starting_car] + [c for c in cars if c != world.starting_car]
    return [car_item_name(c) for c in cars]


def progression_pool(world: "NFSUWorld") -> List[str]:
    names: List[str] = [FINALE_ITEM, KEY_ITEM]
    for cat in PERFORMANCE:
        # Always progressive: Level 3 can only be installed on top of Level 2, and 2 on top of 1.
        names += [progressive_name(cat.name)] * 3
    for cat, levels in VISUAL_ITEM_LEVELS.items():
        names += [progressive_name(cat)] * len(levels)
    names += car_pool(world)
    names += [n for n in world.pack_items if n not in world.starting_packs]
    return names


def pool_bank_target(world: "NFSUWorld") -> int:
    """Base (pre-multiplier) Bank that Bank Bonus items must add up to."""
    opts = world.options
    if opts.vanilla_bank_rewards:
        return 0
    needed = int(REQUIRED_BANK * BANK_SAFETY_FACTOR) - opts.starting_bank.value
    if needed <= 0:
        return 0
    # Items are multiplied by bank_multiplier in game, so the base value has to compensate.
    return -(-needed * 100 // opts.bank_multiplier.value)


def min_bank_slots(world: "NFSUWorld") -> int:
    """Filler slots that must hold Bank Bonus items to reach pool_bank_target."""
    return -(-pool_bank_target(world) // max(BANK_ITEMS.values()))


def filler_pool(world: "NFSUWorld", slots: int) -> List[str]:
    """Bank Bonus items and traps for the remaining slots, guaranteeing pool_bank_target."""
    rng = world.random
    opts = world.options
    target = pool_bank_target(world)
    denominations = sorted(BANK_ITEMS.items(), key=lambda kv: kv[1])
    max_value = denominations[-1][1]

    weights = {t: w for t, w in option_value(opts, "trap_weights").items() if w > 0}
    n_traps = round(slots * option_value(opts, "trap_percentage") / 100) if weights else 0
    # Keep enough Bank slots to reach the target.
    min_bank_slots = -(-target // max_value)
    n_traps = max(0, min(n_traps, slots - min_bank_slots))
    n_bank = slots - n_traps
    if n_bank * max_value < target:
        from Options import OptionError
        raise OptionError(f"{world.player_name}: not enough filler slots to place {target} Bank. "
                          f"Raise bank_multiplier or starting_bank, or turn vanilla_bank_rewards on.")

    # Start with small/medium bonuses, then upgrade until the target is reached.
    bank_idx = [rng.randrange(0, 3) for _ in range(n_bank)]
    total = sum(denominations[i][1] for i in bank_idx)
    while total < target:
        j = min(range(n_bank), key=lambda k: bank_idx[k])
        if bank_idx[j] == len(denominations) - 1:
            break
        total += denominations[bank_idx[j] + 1][1] - denominations[bank_idx[j]][1]
        bank_idx[j] += 1

    pool = [denominations[i][0] for i in bank_idx]
    if n_traps:
        trap_names = list(weights)
        pool += rng.choices(trap_names, weights=[weights[t] for t in trap_names], k=n_traps)
    return pool


def get_filler_item_name(world: "NFSUWorld") -> str:
    return "Bank Bonus (1000)"


def pick_starting_car(world: "NFSUWorld") -> Optional[str]:
    """The start car for random_starter / random_car (None for vanilla, or when cars are no items)."""
    opts = world.options
    if opts.starting_car == opts.starting_car.option_vanilla or not opts.cars_as_items:
        return None
    if opts.starting_car == opts.starting_car.option_random_starter:
        return world.random.choice(STARTER_CARS)
    return world.random.choice(CARS).name

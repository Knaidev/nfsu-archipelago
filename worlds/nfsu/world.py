import logging
from typing import Any, ClassVar, Dict, FrozenSet, List, Mapping, Optional, Set

from worlds.AutoWorld import World

from . import items, locations, packs, regions, rules
from .data.events import EVENTS_BY_NUMBER
from .data.parts import PERFORMANCE
from .logic import star_gate
from .options import NFSUOptions, option_value
from .web_world import NFSUWebWorld

logger = logging.getLogger("NFSU")


class NFSUWorld(World):
    """Need for Speed: Underground (PS2). Win street races on every difficulty, rebuild your car from
    parts found across the multiworld, raise your reputation and take Eddie's crown in #111."""

    game = items.GAME_NAME
    web = NFSUWebWorld()
    options_dataclass = NFSUOptions
    options: NFSUOptions
    topology_present = True
    origin_region_name = regions.ORIGIN_REGION

    item_name_to_id: ClassVar[Dict[str, int]] = items.ITEM_NAME_TO_ID
    location_name_to_id: ClassVar[Dict[str, int]] = locations.LOCATION_NAME_TO_ID
    item_name_groups = items.ITEM_NAME_GROUPS
    location_name_groups = locations.LOCATION_NAME_GROUPS

    effective_excluded_types: FrozenSet[str]
    starting_car: Optional[str]
    packs: List[List[int]]          # event numbers per Event Pack (index 0 = "Event Pack 1")
    pack_items: List[str]
    starting_packs: Set[str]
    MIN_PACK_ROOM: ClassVar[int] = 10
    SPHERE_ONE_MARGIN: ClassVar[int] = 4

    def generate_early(self) -> None:
        opts = self.options
        if opts.starting_car != opts.starting_car.option_vanilla and not opts.cars_as_items:
            logger.warning("%s: starting_car needs cars_as_items; using vanilla.", self.player_name)
        self.starting_car = items.pick_starting_car(self)
        self.packs, self.pack_items, self.starting_packs = [], [], set()

        # Make sure enough non-excluded checks remain for all non-filler items (Event Packs: at least
        # MIN_PACK_ROOM packs on top; they are merged if there is no room for all).
        excluded = frozenset(opts.excluded_race_types.value)
        needed = len(items.progression_pool(self)) + (self.MIN_PACK_ROOM if opts.event_packs else 0)
        if excluded and self._open_checks(excluded) < needed:
            logger.warning("%s: excluded_race_types leaves only %d open checks for %d items; ignoring it.",
                           self.player_name, self._open_checks(excluded), needed)
            excluded = frozenset()
        self.effective_excluded_types = excluded
        if opts.event_packs:
            self._make_event_packs(self._open_checks(excluded))

        if opts.local_key_items:
            opts.local_items.value |= {items.FINALE_ITEM, items.KEY_ITEM}

        if opts.early_level_1_parts:
            for cat in PERFORMANCE:
                self.multiworld.early_items[self.player][items.progressive_name(cat.name)] = 1

    def _open_checks(self, excluded: FrozenSet[str]) -> int:
        return (sum(len(locations.base_check_names(e)) for e in locations.CHECK_EVENTS
                    if locations.exclusion_type(e) not in excluded)
                + option_value(self.options, "style_point_checks"))

    def _make_event_packs(self, open_checks: int) -> None:
        """Shuffles the events into packs, as many as fit into the pool (see packs.py)."""
        opts = self.options
        start = opts.starting_event_packs.value
        base = len(items.progression_pool(self))           # no packs yet
        room = min(open_checks - base,                      # progression only on non-excluded checks
                   locations.check_count(self) - base - items.min_bank_slots(self))
        count = max(start + 1, min(packs.MAX_PACKS, room + start))
        if count > packs.MAX_PACKS or room < 1:
            from Options import OptionError
            raise OptionError(f"{self.player_name}: no room for Event Pack items ({room} free checks).")
        if count < packs.MAX_PACKS:
            logger.warning("%s: only room for %d Event Packs; packs were merged.", self.player_name, count)
        self.packs = packs.make_packs(self.random, count)
        self.pack_items = [packs.pack_item_name(i + 1) for i in range(len(self.packs))]
        # Starting packs: among packs with a Tier 1 race that needs no stars, so the start has something to do.
        easy = [name for name, pack in zip(self.pack_items, self.packs)
                if any(locations.tier_of(n) == 1 and not EVENTS_BY_NUMBER[n].reputation_required for n in pack)]
        others = [n for n in self.pack_items if n not in easy]
        self.random.shuffle(easy)
        self.random.shuffle(others)
        order = easy + others
        self.starting_packs = set(order[:start])
        # Sphere 1 must hold the early Level 1 parts: add easy packs until there are enough start checks
        # (solo seeds failed 9 of 30 times with 2 random starting packs).
        # With star gates, Tier 1 is all there is until 2 stars: more room for packs and visual items.
        needed = ((len(PERFORMANCE) if opts.early_level_1_parts else 0) + self.SPHERE_ONE_MARGIN
                  + (self.SPHERE_ONE_MARGIN if opts.star_gates else 0))
        extra = [n for n in easy if n not in self.starting_packs]
        while self._sphere_one_checks() < needed and extra:
            self.starting_packs.add(extra.pop(0))

    def _sphere_one_checks(self) -> int:
        """Non-excluded checks of Tier 1 events without a star requirement that are open from the start."""
        open_events = set(packs.START_EVENTS)
        for name, pack in zip(self.pack_items, self.packs):
            if name in self.starting_packs:
                open_events.update(pack)
        return sum(len(locations.base_check_names(e)) for e in locations.CHECK_EVENTS
                   if e.number in open_events and locations.tier_of(e.number) == 1
                   and not e.reputation_required
                   and locations.exclusion_type(e) not in self.effective_excluded_types)

    def create_regions(self) -> None:
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)

    def create_item(self, name: str) -> items.NFSUItem:
        return items.create_item(self, name)

    def get_filler_item_name(self) -> str:
        return items.get_filler_item_name(self)

    def create_items(self) -> None:
        pool_names: List[str] = items.progression_pool(self)
        if self.starting_car is not None:
            # car_pool() leaves the start car out; it is given at the start.
            self.multiworld.push_precollected(self.create_item(items.car_item_name(self.starting_car)))
        for name in sorted(self.starting_packs, key=self.pack_items.index):
            self.multiworld.push_precollected(self.create_item(name))

        slots = locations.check_count(self) - len(pool_names)
        if slots < 0:
            from Options import OptionError
            raise OptionError(f"{self.player_name}: {len(pool_names)} items do not fit into "
                              f"{locations.check_count(self)} locations.")
        pool_names += items.filler_pool(self, slots)
        self.multiworld.itempool += [self.create_item(n) for n in pool_names]

    def set_rules(self) -> None:
        rules.set_all_rules(self)

    def fill_slot_data(self) -> Mapping[str, Any]:
        data: Dict[str, Any] = self.options.as_dict(
            "goal", "races_for_goal", "time_trials_required", "star_gates",
            "cars_as_items", "starting_bank", "bank_multiplier",
            "vanilla_bank_rewards", "death_link", "death_link_trigger", "death_link_amnesty",
        )
        for name in ("style_point_checks", "death_link_effect"):   # dormant in 0.1, the client still reads them
            data[name] = option_value(self.options, name)
        data["star_gate_by_tier"] = {str(t): star_gate(self, t) for t in range(1, 6)}
        data["starting_car"] = self.starting_car
        data["event_packs"] = {name: pack for name, pack in zip(self.pack_items, self.packs)} if self.packs else None
        data["world_version"] = "0.3.2"
        return data

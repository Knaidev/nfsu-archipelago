import logging
from typing import Any, ClassVar, Dict, FrozenSet, List, Mapping, Optional

from worlds.AutoWorld import World

from . import items, locations, regions, rules
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

    def generate_early(self) -> None:
        opts = self.options
        if opts.starting_car != opts.starting_car.option_vanilla and not opts.cars_as_items:
            logger.warning("%s: starting_car needs cars_as_items; using vanilla.", self.player_name)
        self.starting_car = items.pick_starting_car(self)

        # Make sure enough non-excluded checks remain for all non-filler items.
        excluded = frozenset(opts.excluded_race_types.value)
        open_checks = sum(len(locations.base_check_names(e)) for e in locations.CHECK_EVENTS
                          if locations.exclusion_type(e) not in excluded) + option_value(opts, "style_point_checks")
        needed = len(items.progression_pool(self))
        if excluded and open_checks < needed:
            logger.warning("%s: excluded_race_types leaves only %d open checks for %d items; ignoring it.",
                           self.player_name, open_checks, needed)
            excluded = frozenset()
        self.effective_excluded_types = excluded

        if opts.local_key_items:
            opts.local_items.value |= {items.FINALE_ITEM, items.KEY_ITEM}

        if opts.early_level_1_parts:
            for cat in PERFORMANCE:
                self.multiworld.early_items[self.player][items.progressive_name(cat.name)] = 1

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
        data["world_version"] = "0.1.1"
        return data

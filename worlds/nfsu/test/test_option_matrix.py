"""Runs WorldTestBase's default tests (all-state reachability, empty-state start, full fill and sphere
walk-through) for many option combinations and every webhost preset."""
import itertools

from . import NFSUTestBase
from ..options import PRESETS

_MATRIX = itertools.product(
    ("loose", "normal", "strict"),        # logic_strictness
    (True, False),                        # star_gates
    (True, False),                        # local_key_items
)

for _strict, _gates, _local in _MATRIX:
    _name = f"TestMatrix_{_strict}_{'gates' if _gates else 'nogates'}_{'local' if _local else 'any'}"
    globals()[_name] = type(_name, (NFSUTestBase,), {"options": {
        "logic_strictness": _strict, "star_gates": _gates, "local_key_items": _local,
    }})

_EXCLUSIONS = {
    "Drag": ["Drag"],
    "DriftDrag": ["Drift", "Drag"],
    "AllButTT": ["Circuit", "Sprint", "Drag", "Drift", "Knockout", "Tournament"],
}
for _label, _types in _EXCLUSIONS.items():
    _name = f"TestExcluded_{_label}"
    globals()[_name] = type(_name, (NFSUTestBase,), {"options": {"excluded_race_types": _types}})

for _preset, _opts in PRESETS.items():
    _name = f"TestPreset_{_preset}"
    globals()[_name] = type(_name, (NFSUTestBase,), {"options": dict(_opts)})


class TestRandomCar(NFSUTestBase):
    options = {"starting_car": "random_car", "cars_as_items": True}


class TestRaceCountNoCars(NFSUTestBase):
    options = {"goal": "race_count", "races_for_goal": 100, "cars_as_items": False}


class TestNoTimeTrialsRequired(NFSUTestBase):
    options = {"time_trials_required": 0, "star_gate_scale": 50}


class TestRandomStarterNoVanillaBank(NFSUTestBase):
    options = {"starting_car": "random_starter", "vanilla_bank_rewards": False}

    def test_no_early_bank_by_default(self):
        from ..items import EARLY_BANK_ITEM
        self.assertIsNone(self.multiworld.local_early_items[self.player].get(EARLY_BANK_ITEM), "default 0")
        pool = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(pool.count(EARLY_BANK_ITEM), 0)


class TestTimeTrialItems(NFSUTestBase):
    """Time trials are items of their own, not part of the Event Packs."""
    options = {"time_trials_required": 3}

    def test_every_time_trial_has_an_item_and_no_pack(self):
        from ..items import TIME_TRIAL_ITEMS
        pool = [i.name for i in self.multiworld.itempool if i.player == self.player]
        for number, name in TIME_TRIAL_ITEMS.items():
            self.assertEqual(pool.count(name), 1, name)
            self.assertFalse(any(number in pack for pack in self.world.packs), number)

    def test_time_trial_needs_its_item(self):
        from ..items import TIME_TRIAL_ITEMS
        from ..locations import won_name
        from ..data.events import EVENTS_BY_NUMBER
        number, item = next(iter(TIME_TRIAL_ITEMS.items()))
        location = self.world.get_location(won_name(EVENTS_BY_NUMBER[number]))
        self.collect_all_but([item])
        self.assertFalse(location.can_reach(self.multiworld.state))
        self.collect_by_name(item)
        self.assertTrue(location.can_reach(self.multiworld.state))


class TestNoTimeTrialItemsWithoutPacks(NFSUTestBase):
    options = {"event_packs": False}

    def test_no_time_trial_items(self):
        from ..items import TIME_TRIAL_ITEMS
        pool = {i.name for i in self.multiworld.itempool if i.player == self.player}
        self.assertFalse(pool & set(TIME_TRIAL_ITEMS.values()))


class TestLargeBankBonuses(NFSUTestBase):
    options = {"vanilla_bank_rewards": False, "large_bank_bonuses": True, "early_bank_bonuses": 2}

    def test_all_pool_bank_is_7000(self):
        from ..items import BANK_VALUES, EARLY_BANK_ITEM, LARGE_BANK_ITEM
        bank = [i.name for i in self.multiworld.itempool if i.player == self.player and i.name in BANK_VALUES]
        self.assertEqual(set(bank), {LARGE_BANK_ITEM, EARLY_BANK_ITEM})
        self.assertEqual(bank.count(EARLY_BANK_ITEM), 2, "early bonuses stay small")


class TestLargeBankIgnoredWithVanillaBank(NFSUTestBase):
    options = {"vanilla_bank_rewards": True, "large_bank_bonuses": True}

    def test_option_is_ignored(self):
        from ..items import LARGE_BANK_ITEM
        self.assertNotIn(LARGE_BANK_ITEM, [i.name for i in self.multiworld.itempool if i.player == self.player])


class TestTwoEarlyBankBonuses(NFSUTestBase):
    options = {"vanilla_bank_rewards": False, "early_bank_bonuses": 2}

    def test_two_are_placed_early(self):
        from ..items import EARLY_BANK_ITEM
        self.assertEqual(self.multiworld.local_early_items[self.player].get(EARLY_BANK_ITEM), 2)


class TestNoEarlyBankWithVanillaBank(NFSUTestBase):
    options = {"vanilla_bank_rewards": True, "early_bank_bonuses": 2}

    def test_option_is_ignored(self):
        from ..items import EARLY_BANK_ITEM
        self.assertNotIn(EARLY_BANK_ITEM, [i.name for i in self.multiworld.itempool if i.player == self.player])

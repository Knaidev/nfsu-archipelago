"""Item/location counts, sphere 1, finale requirements, bank."""
from BaseClasses import CollectionState

from . import NFSUTestBase
from ..data.parts import PERFORMANCE
from ..items import BANK_ITEMS, FINALE_ITEM, KEY_ITEM, REQUIRED_BANK, TIME_TRIAL_WON
from ..locations import (CHECK_EVENTS, CHOICE_EVENTS, GOAL_LOCATION, LOCATION_NAME_TO_ID, base_check_names,
                         tier_of)
from ..logic import max_reputation, starting_reputation

BASE_CHECKS = 139  # vanilla rewards + "Victory" of the 102 events with checks


def _real_locations(world):
    return [loc for loc in world.multiworld.get_locations(world.player) if loc.address is not None]


class TestCountsEasy(NFSUTestBase):
    options = {}

    def test_item_count_equals_location_count(self):
        world = self.multiworld.worlds[self.player]
        self.assertEqual(len(_real_locations(world)), BASE_CHECKS)
        own_items = [i for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(len(own_items), BASE_CHECKS)

    def test_choice_events_have_no_checks(self):
        names = {loc.name for loc in _real_locations(self.multiworld.worlds[self.player])}
        for n in CHOICE_EVENTS:
            self.assertFalse(any(name.startswith(f"#{n} ") for name in names), n)
        self.assertEqual(sorted(CHOICE_EVENTS), [7, 15, 26, 47, 68, 77, 96, 110])

    def test_rewards_are_checks(self):
        six = next(e for e in CHECK_EVENTS if e.number == 6)
        self.assertEqual(len(base_check_names(six)), 3)  # Engine, Drivetrain, Tyre Level 1
        self.assertIn("#21 Gut Check Time - Victory", LOCATION_NAME_TO_ID)


class TestDormantOptions(NFSUTestBase):
    """0.1 does not offer style point checks, traps or other Death Link effects (no in-game effect yet)."""

    def test_not_offered_and_inactive(self):
        from ..options import DORMANT_DEFAULTS, TRAPS, NFSUOptions
        world = self.multiworld.worlds[self.player]
        for name in DORMANT_DEFAULTS:
            self.assertNotIn(name, NFSUOptions.type_hints, name)
        self.assertEqual(len(_real_locations(world)), BASE_CHECKS, "no style point checks")
        own = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertFalse(set(TRAPS) & set(own), "no traps")
        self.assertEqual(world.fill_slot_data()["death_link_effect"], 0)


class TestSphereOne(NFSUTestBase):
    options = {"logic_strictness": "strict"}

    def test_tier1_rewards_in_sphere_1(self):
        state = CollectionState(self.multiworld)
        for event in CHECK_EVENTS:
            if tier_of(event.number) != 1:
                continue
            for name in base_check_names(event):
                self.assertTrue(state.can_reach_location(name, self.player), name)

    def test_tier2_needs_level1_parts_and_two_stars(self):
        name = base_check_names(next(e for e in CHECK_EVENTS if e.number == 31))[0]
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name([f"Progressive {c.name}" for c in PERFORMANCE])
        self.assertFalse(self.can_reach_location(name), "no stars yet")
        self.collect_by_name(["Progressive Front Bumper"] * 2 + ["Progressive Rear Bumper"] * 2)  # 2.2 stars
        self.assertTrue(self.can_reach_location(name))


class TestFinaleRequirements(NFSUTestBase):
    options = {"goal": "finale", "time_trials_required": 7}

    def test_finale_needs_key_items(self):
        state = self.multiworld.get_all_state()
        self.assertTrue(state.can_reach_location(GOAL_LOCATION, self.player))
        for item_name in (FINALE_ITEM, KEY_ITEM):
            st = self.multiworld.get_all_state()
            st.remove(self.get_item_by_name(item_name))
            self.assertFalse(st.can_reach_location(GOAL_LOCATION, self.player), item_name)

    def test_finale_needs_time_trials(self):
        entrance = self.multiworld.get_entrance("To Finale", self.player)
        st = self.multiworld.get_all_state()
        self.assertTrue(entrance.access_rule(st))
        st.prog_items[self.player][TIME_TRIAL_WON] = 6
        self.assertFalse(entrance.access_rule(st))


class TestRaceCountGoal(NFSUTestBase):
    options = {"goal": "race_count", "races_for_goal": 50}

    def test_no_finale_location(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn(GOAL_LOCATION, names)


class TestReputationModel(NFSUTestBase):
    def test_reputation_bounds(self):
        # Stars only come from received items; everything together must clear the finale gate (5).
        self.assertEqual(starting_reputation(), 0)
        self.assertAlmostEqual(max_reputation(), 7.6)

    def test_visual_items_are_progressive_per_category(self):
        from ..items import VISUAL_ITEM_LEVELS
        own = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(own.count("Progressive Front Bumper"), 2)
        self.assertEqual(own.count("Progressive Headlights"), 1)
        self.assertEqual(sum(len(v) for v in VISUAL_ITEM_LEVELS.values()), 26)


class TestCars(NFSUTestBase):
    options = {"starting_car": "random_starter"}

    def test_random_starter(self):
        from ..data.cars import CARS, STARTER_CARS
        world = self.multiworld.worlds[self.player]
        self.assertIn(world.starting_car, STARTER_CARS)
        own = {i.name for i in self.multiworld.itempool if i.player == self.player}
        start = {i.name for i in self.multiworld.precollected_items[self.player]}
        self.assertEqual(start, {f"Car: {world.starting_car}"})
        self.assertEqual({n for n in own if n.startswith("Car: ")},
                         {f"Car: {c.name}" for c in CARS} - start, "all other cars are items")


class TestCarsVanilla(NFSUTestBase):
    def test_starters_are_no_items(self):
        from ..data.cars import STARTER_CARS
        own = {i.name for i in self.multiworld.itempool if i.player == self.player}
        self.assertEqual(len([n for n in own if n.startswith("Car: ")]), 15)
        self.assertFalse(any(f"Car: {c}" in own for c in STARTER_CARS))


class TestBankWithoutVanillaRewards(NFSUTestBase):
    options = {"vanilla_bank_rewards": False, "bank_multiplier": 50}

    def test_enough_bank(self):
        world = self.multiworld.worlds[self.player]
        base = sum(BANK_ITEMS.get(i.name, 0) for i in self.multiworld.itempool if i.player == self.player)
        effective = base * world.options.bank_multiplier.value // 100 + world.options.starting_bank.value
        self.assertGreaterEqual(effective, REQUIRED_BANK)

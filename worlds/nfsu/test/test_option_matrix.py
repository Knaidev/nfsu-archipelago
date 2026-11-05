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

from typing import TYPE_CHECKING

from BaseClasses import Region

from .locations import TIER_REGION

if TYPE_CHECKING:
    from .world import NFSUWorld

ORIGIN_REGION = "Menu"


def create_and_connect_regions(world: "NFSUWorld") -> None:
    mw = world.multiworld
    menu = Region(ORIGIN_REGION, world.player, mw)
    mw.regions.append(menu)
    previous = menu
    for tier in sorted(TIER_REGION):
        if tier == 5 and world.options.goal == world.options.goal.option_race_count:
            break
        region = Region(TIER_REGION[tier], world.player, mw)
        mw.regions.append(region)
        previous.connect(region, f"To {TIER_REGION[tier]}")
        previous = region

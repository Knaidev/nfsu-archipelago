from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld

from .options import OPTION_GROUPS, PRESETS


class NFSUWebWorld(WebWorld):
    theme = "partyTime"
    rich_text_options_doc = False
    option_groups = OPTION_GROUPS
    options_presets = PRESETS
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Need for Speed: Underground (PS2, PCSX2) for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["NFSU Archipelago contributors"],
        )
    ]

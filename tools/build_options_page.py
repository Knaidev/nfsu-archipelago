"""Builds build/nfsu_options.html: a stand-alone page to create a player YAML (like archipelago.gg's
player-options page), generated from the world's options so it always matches the apworld.

    python tools/build_options_page.py --archipelago <Archipelago source with worlds/nfsu>
"""
import argparse
import inspect
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "tools" / "options_page.html"
LIST_KINDS = {  # Item & Location options -> what they list
    "local_items": "items", "non_local_items": "items", "start_hints": "items", "start_inventory": "counts",
    "start_location_hints": "locations", "exclude_locations": "locations", "priority_locations": "locations",
}


def _doc(cls) -> str:
    return inspect.cleandoc(cls.__doc__ or "")


def describe(key: str, cls) -> dict:
    from Options import Choice, NamedRange, OptionSet, Range, Toggle
    d = {"key": key, "name": getattr(cls, "display_name", key), "doc": _doc(cls)}
    if issubclass(cls, Toggle):
        d.update(kind="toggle", default=bool(cls.default))
    elif issubclass(cls, Choice):
        names = [name for name, value in cls.options.items() if cls.name_lookup.get(value) == name]
        d.update(kind="choice", choices=names, default=cls.name_lookup[cls.default])
    elif issubclass(cls, Range):
        d.update(kind="range", min=cls.range_start, max=cls.range_end, default=int(cls.default),
                 named=dict(getattr(cls, "special_range_names", {})) if issubclass(cls, NamedRange) else {})
    elif issubclass(cls, OptionSet):
        d.update(kind="set", valid=sorted(cls.valid_keys), default=sorted(cls.default))
    else:
        raise TypeError(f"{key}: option type {cls.__mro__[1].__name__} is not supported by the options page")
    return d


def collect() -> dict:
    from Options import Visibility, get_option_groups
    from worlds.nfsu.options import PRESETS, TRAPS
    from worlds.nfsu.world import NFSUWorld

    groups, lists = [], []
    for group, options in get_option_groups(NFSUWorld, Visibility.simple_ui).items():
        if group == "Item & Location Options":
            for key, cls in options.items():
                if key in LIST_KINDS:
                    lists.append({"key": key, "name": cls.display_name, "doc": _doc(cls), "kind": LIST_KINDS[key]})
            continue
        groups.append({"name": group, "options": [describe(k, c) for k, c in options.items()]})

    skip_items = set(TRAPS)                                   # traps are not in the pool yet
    items = sorted(n for n in NFSUWorld.item_name_to_id if n not in skip_items)
    item_groups = sorted(g for g in NFSUWorld.item_name_groups if g not in ("Traps", "Everything"))
    style = set(NFSUWorld.location_name_groups.get("Style Points", ()))   # style checks are not offered yet
    locations = sorted((n for n in NFSUWorld.location_name_to_id if n not in style), key=_location_key)
    location_groups = sorted(g for g in NFSUWorld.location_name_groups if g not in ("Style Points", "Everywhere"))
    manifest = json.loads((ROOT / "worlds" / "nfsu" / "archipelago.json").read_text(encoding="utf-8"))
    return {
        "game": NFSUWorld.game, "world_version": manifest.get("world_version", ""),
        "ap_version": manifest.get("minimum_ap_version", ""), "groups": groups, "lists": lists,
        "items": items, "item_groups": item_groups, "locations": locations, "location_groups": location_groups,
        "presets": PRESETS,
    }


def _location_key(name: str):
    head = name.split(" ", 1)[0]
    return (int(head[1:]) if head.startswith("#") and head[1:].isdigit() else 999, name)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archipelago", required=True, help="Archipelago source folder that contains worlds/nfsu")
    p.add_argument("--out", default=str(ROOT / "build" / "nfsu_options.html"))
    a = p.parse_args()
    os.environ.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")
    sys.path.insert(0, str(pathlib.Path(a.archipelago).resolve()))
    os.chdir(a.archipelago)
    data = json.dumps(collect(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*OPTIONS_DATA*/{}", data)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Built {out} ({out.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()

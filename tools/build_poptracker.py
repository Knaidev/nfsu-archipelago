"""Builds build/nfsu_poptracker.zip, a PopTracker pack with Archipelago autotracking.

    python tools/build_poptracker.py --archipelago <path to Archipelago source>

Everything in the pack is generated from the world's own data (events, checks, items), so it always matches
the apworld. The images are plain drawn panels (Pillow); the pack contains no game assets.

Tabs: "Events" (all 111 events as a grid; a field is cleared when all its checks are sent), "Time Trials" (the
events without checks, which the NFSU client reports through Archipelago's data storage) and "Items".
"""
import argparse
import io
import json
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Need for Speed: Underground menu look: dark navy panels, light blue lines and text.
BG = (8, 20, 40)
PANEL = (16, 44, 84)
PANEL_HI = (24, 70, 128)
LINE = (70, 160, 235)
TEXT = (225, 240, 255)
DIM = (130, 170, 215)
HEX_BG = "#081428"

COLS, CELL_W, CELL_H, MARGIN, HEADER = 12, 92, 66, 14, 44
LOCATION_SIZE = 26
TYPE_SHORT = {"Circuit": "CIR", "Sprint": "SPR", "Drag": "DRG", "Drift": "DFT", "Knockout": "KO",
              "Time Trial": "TT"}


def font(size: int, bold: bool = True):
    from PIL import ImageFont
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def clean(name: str) -> str:
    """PopTracker builds "@location/section" paths, so names must not contain a slash."""
    return name.replace("/", "-")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def item_icon(label: str, sub: str = "") -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, 62, 62), radius=9, fill=PANEL, outline=LINE, width=2)
    size = 26 if len(label) <= 3 else 20 if len(label) <= 4 else 15
    d.text((32, 27 if sub else 32), label, font=font(size), fill=TEXT, anchor="mm")
    if sub:
        d.text((32, 50), sub, font=font(11, bold=False), fill=DIM, anchor="mm")
    return png(img)


def grid_map(title: str, cells, cols: int, cell_w: int, cell_h: int):
    """cells: list of (lines, highlight). Returns (png bytes, [(x, y) centre of the marker in each cell])."""
    from PIL import Image, ImageDraw
    rows = -(-len(cells) // cols)
    width, height = 2 * MARGIN + cols * cell_w, HEADER + MARGIN + rows * cell_h
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.text((MARGIN, HEADER // 2), title, font=font(22), fill=TEXT, anchor="lm")
    d.line((MARGIN, HEADER - 4, width - MARGIN, HEADER - 4), fill=LINE, width=2)
    centres = []
    for i, (lines, highlight) in enumerate(cells):
        x, y = MARGIN + (i % cols) * cell_w, HEADER + (i // cols) * cell_h
        d.rounded_rectangle((x + 2, y + 2, x + cell_w - 3, y + cell_h - 3), radius=6,
                            fill=PANEL_HI if highlight else PANEL, outline=LINE, width=1)
        d.text((x + 8, y + 7), lines[0], font=font(14), fill=TEXT)
        for k, line in enumerate(lines[1:]):
            d.text((x + 8, y + 26 + 13 * k), line, font=font(10, bold=False), fill=DIM)
        centres.append((x + cell_w - 8 - LOCATION_SIZE // 2, y + cell_h // 2))
    return png(img), centres


def wrap(text: str, width: int):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur] if cur else lines


def lua_value(value) -> str:
    """A Lua literal: lists as tables, strings as UTF-8 (Lua has no JSON-style unicode escape)."""
    if isinstance(value, (list, tuple)):
        return "{" + ", ".join(lua_value(v) for v in value) + "}"
    return json.dumps(value, ensure_ascii=False)


def lua_table(mapping, key_fmt="[%s]") -> str:
    return "{\n" + "".join("  %s = %s,\n" % (key_fmt % k, lua_value(v)) for k, v in mapping.items()) + "}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archipelago", required=True, help="Archipelago source folder that contains worlds/nfsu")
    p.add_argument("--out", default=str(ROOT / "build" / "nfsu_poptracker.zip"))
    a = p.parse_args()

    sys.path.insert(0, a.archipelago)
    from worlds.nfsu.data.cars import CARS
    from worlds.nfsu.data.events import EVENTS, GOAL_EVENT
    from worlds.nfsu.data.parts import PERFORMANCE
    from worlds.nfsu.items import (FINALE_ITEM, ITEM_NAME_TO_ID, KEY_ITEM, VISUAL_ITEM_LEVELS, car_item_name,
                                   progressive_name)
    from worlds.nfsu.locations import CHOICE_EVENTS, EVENT_CHECK_IDS, LOCATION_NAME_TO_ID
    from worlds.nfsu.packs import PACK_ITEM_NAMES

    manifest = json.loads((ROOT / "worlds" / "nfsu" / "archipelago.json").read_text(encoding="utf-8"))
    location_names = {v: k for k, v in LOCATION_NAME_TO_ID.items()}
    events = [e for e in EVENTS if 1 <= e.number <= GOAL_EVENT]
    no_checks = [e for e in events if not EVENT_CHECK_IDS.get(e.number)]   # time trials, #110, the finale
    files = {}

    # ------------------------------------------------------------------ maps
    cells = []
    for e in events:
        lines = ["#%d" % e.number, TYPE_SHORT.get(e.race_type, e.race_type[:3].upper())]
        if e.tournament:
            lines.append("tourney")
        if e.reputation_required:
            lines.append("%d star%s" % (e.reputation_required, "" if e.reputation_required == 1 else "s"))
        cells.append((lines, e.number == GOAL_EVENT or e.number in CHOICE_EVENTS))
    files["images/maps/events.png"], event_xy = grid_map(
        "UNDERGROUND MODE  –  EVENTS", cells, COLS, CELL_W, CELL_H)
    tt_cells = [(["#%d" % e.number] + wrap(e.name, 22)[:2] + [e.race_type], e.number == GOAL_EVENT)
                for e in no_checks]
    files["images/maps/special.png"], special_xy = grid_map(
        "TIME TRIALS AND FINALE  –  NO CHECKS, WON IN GAME", tt_cells, 3, 4 * CELL_W, CELL_H + 14)
    files["maps/maps.json"] = json.dumps([
        {"name": "events", "location_size": LOCATION_SIZE, "location_border_thickness": 2,
         "img": "images/maps/events.png"},
        {"name": "special", "location_size": LOCATION_SIZE, "location_border_thickness": 2,
         "img": "images/maps/special.png"},
    ], indent=1)

    # ------------------------------------------------------------------ locations
    locations, check_codes, win_codes = [], {}, {}
    special_index = {e.number: i for i, e in enumerate(no_checks)}
    for i, e in enumerate(events):
        name = clean("#%d %s" % (e.number, e.name))
        ids = EVENT_CHECK_IDS.get(e.number, ())
        sections = []
        for loc_id in ids:
            section = clean(location_names[loc_id].split(" - ", 1)[1])
            sections.append({"name": section, "item_count": 1})
            check_codes[loc_id] = "@%s/%s" % (name, section)
        if not ids:
            sections.append({"name": "Won in game", "item_count": 1})
            win_codes[e.number] = "@%s/Won in game" % name
        spots = [{"map": "events", "x": event_xy[i][0], "y": event_xy[i][1]}]
        if e.number in special_index:
            x, y = special_xy[special_index[e.number]]
            spots.append({"map": "special", "x": x, "y": y})
        rule = "$finale_open" if e.number == GOAL_EVENT else "$event_open|%d" % e.number
        locations.append({"name": name, "access_rules": [rule], "sections": sections, "map_locations": spots})
    files["locations/locations.json"] = json.dumps(locations, indent=1)

    # ------------------------------------------------------------------ items
    items, item_codes, rows = [], {}, {"packs": [], "performance": [], "visual": [], "cars": [], "key": []}

    def add(name, code, kind, label, sub="", group="key", maximum=0):
        entry = {"name": name, "type": kind, "img": "images/items/%s.png" % code, "codes": code}
        if kind == "consumable":
            entry["max_quantity"] = maximum
        items.append(entry)
        files["images/items/%s.png" % code] = item_icon(label, sub)
        item_codes[ITEM_NAME_TO_ID[name]] = [code, kind]
        rows[group].append(code)

    add(FINALE_ITEM, "finale", "toggle", "FIN", "finale")
    add(KEY_ITEM, "samantha", "toggle", "KEY", "Samantha")
    for n, name in enumerate(PACK_ITEM_NAMES, 1):
        add(name, "pack_%d" % n, "toggle", str(n), "pack", "packs")
    for cat in PERFORMANCE:
        short = "".join(w[0] for w in re.split(r"[ /&]+", cat.name) if w)[:3].upper()
        add(progressive_name(cat.name), "perf_" + slug(cat.name), "consumable",
            short if len(short) > 1 else cat.name[:3].upper(), cat.name[:9], "performance", 3)
    for cat, levels in VISUAL_ITEM_LEVELS.items():
        if progressive_name(cat) in ITEM_NAME_TO_ID and levels:
            add(progressive_name(cat), "vis_" + slug(cat), "consumable", cat[:3].upper(), cat[:9], "visual",
                len(levels))
    for car in CARS:
        if car_item_name(car.name) in ITEM_NAME_TO_ID:
            add(car_item_name(car.name), "car_" + slug(car.name), "toggle", car.name.split()[-1][:5],
                car.name.split()[0][:9], "cars")
    files["items/items.json"] = json.dumps(items, indent=1)

    # ------------------------------------------------------------------ layout
    def grid(codes, per_row):
        return {"type": "itemgrid", "item_margin": "2,2", "item_size": "44,44",
                "rows": [codes[i:i + per_row] for i in range(0, len(codes), per_row)]}

    def group(header, content):
        return {"type": "group", "header": header, "background": HEX_BG, "content": content}

    files["layouts/tracker.json"] = json.dumps({"tracker_default": {
        "type": "tabbed", "background": HEX_BG,
        "tabs": [
            {"title": "Events", "content": {"type": "map", "maps": ["events"]}},
            {"title": "Time Trials", "content": {"type": "map", "maps": ["special"]}},
            {"title": "Items", "content": {"type": "array", "orientation": "vertical", "background": HEX_BG,
                                          "content": [
                                              group("Finale", grid(rows["key"], 12)),
                                              group("Event Packs", grid(rows["packs"], 18)),
                                              group("Performance", grid(rows["performance"], 18)),
                                              group("Visual", grid(rows["visual"], 18)),
                                              group("Cars", grid(rows["cars"], 18)),
                                          ]}},
        ]}}, indent=1)

    # ------------------------------------------------------------------ scripts
    files["scripts/data.lua"] = (
        "-- Generated by tools/build_poptracker.py – do not edit.\n"
        "CHECK_CODES = %s\n\nWIN_CODES = %s\n\nITEM_CODES = %s\n\nALL_SECTIONS = %s\n" % (
            lua_table(check_codes), lua_table(win_codes), lua_table(item_codes),
            "{\n" + "".join("  %s,\n" % lua_value(c) for c in list(check_codes.values()) + list(win_codes.values()))
            + "}"))
    files["scripts/init.lua"] = INIT_LUA
    files["scripts/autotracking/archipelago.lua"] = ARCHIPELAGO_LUA
    files["manifest.json"] = json.dumps({
        "name": "Need for Speed: Underground (Archipelago)",
        "game_name": manifest["game"],
        "package_uid": "nfsu_archipelago",
        "package_version": manifest["world_version"],
        "platform": "ps2",
        "author": "nfsu-archipelago contributors",
        "min_poptracker_version": "0.25.6",
        "variants": {"standard": {"display_name": "Standard", "flags": ["ap"]}},
    }, indent=1)
    files["README.txt"] = README_TXT % manifest["world_version"]

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files):
            data = files[name]
            zf.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    print(f"Built {out} ({out.stat().st_size // 1024} KiB, {len(files)} files; {len(check_codes)} checks, "
          f"{len(win_codes)} events without checks, {len(items)} items)")


INIT_LUA = """-- Need for Speed: Underground – PopTracker pack for the Archipelago world.
Tracker:AddItems("items/items.json")
Tracker:AddMaps("maps/maps.json")
Tracker:AddLocations("locations/locations.json")
Tracker:AddLayouts("layouts/tracker.json")

ScriptHost:LoadScript("scripts/data.lua")

-- Which Event Pack holds an event; filled from the seed's slot data when connected.
PACK_OF = {}
PACKS_KNOWN = false

-- Access rule of an event: #1-#5 are always open, the others need their Event Pack. Without a connection
-- (or with the Event Packs option off) every event counts as open.
function event_open(number)
    local n = tonumber(number)
    if n == nil or n <= 5 or not PACKS_KNOWN then
        return true
    end
    local pack = PACK_OF[n]
    if pack == nil then
        return true
    end
    return Tracker:ProviderCountForCode("pack_" .. pack) > 0
end

-- The finale needs its two key items (stars and time trials are not tracked here).
function finale_open()
    return Tracker:ProviderCountForCode("finale") > 0 and Tracker:ProviderCountForCode("samantha") > 0
end

-- The Archipelago object exists when the variant has the "ap" flag.
if Archipelago ~= nil then
    ScriptHost:LoadScript("scripts/autotracking/archipelago.lua")
end
"""

ARCHIPELAGO_LUA = """-- Archipelago autotracking: items, sent checks and the events the NFSU client reports as won.
local CUR_INDEX = -1
local WON_KEY = nil

local function clear_section(code)
    local obj = Tracker:FindObjectForCode(code)
    if obj then
        obj.AvailableChestCount = 0
    end
end

local function mark_won(value)
    if type(value) ~= "table" then
        return
    end
    for _, number in pairs(value) do
        local code = WIN_CODES[tonumber(number)]
        if code then
            clear_section(code)
        end
    end
end

function onClear(slot_data)
    CUR_INDEX = -1
    for _, code in ipairs(ALL_SECTIONS) do
        local obj = Tracker:FindObjectForCode(code)
        if obj then
            obj.AvailableChestCount = obj.ChestCount
        end
    end
    for _, entry in pairs(ITEM_CODES) do
        local obj = Tracker:FindObjectForCode(entry[1])
        if obj then
            if entry[2] == "consumable" then
                obj.AcquiredCount = 0
            else
                obj.Active = false
            end
        end
    end
    PACK_OF = {}
    PACKS_KNOWN = false
    if slot_data and type(slot_data["event_packs"]) == "table" then
        for name, events in pairs(slot_data["event_packs"]) do
            local pack = tonumber(string.match(name, "%d+"))
            if pack then
                PACKS_KNOWN = true
                for _, number in pairs(events) do
                    PACK_OF[tonumber(number)] = pack
                end
            end
        end
    end
    -- Checks that were already sent before the tracker connected.
    for _, location_id in ipairs(Archipelago.CheckedLocations or {}) do
        onLocation(location_id, "")
    end
    if Archipelago.PlayerNumber and Archipelago.PlayerNumber > -1 then
        WON_KEY = "NFSU_won_" .. Archipelago.TeamNumber .. "_" .. Archipelago.PlayerNumber
        Archipelago:SetNotify({WON_KEY})
        Archipelago:Get({WON_KEY})
    end
end

function onItem(index, item_id, item_name, player_number)
    if index <= CUR_INDEX then
        return
    end
    CUR_INDEX = index
    local entry = ITEM_CODES[item_id]
    if not entry then
        return
    end
    local obj = Tracker:FindObjectForCode(entry[1])
    if obj then
        if entry[2] == "consumable" then
            obj.AcquiredCount = obj.AcquiredCount + obj.Increment
        else
            obj.Active = true
        end
    end
end

function onLocation(location_id, location_name)
    local code = CHECK_CODES[location_id]
    if code then
        clear_section(code)
    end
end

function onStored(key, value, old_value)
    if key == WON_KEY then
        mark_won(value)
    end
end

Archipelago:AddClearHandler("nfsu clear", onClear)
Archipelago:AddItemHandler("nfsu item", onItem)
Archipelago:AddLocationHandler("nfsu location", onLocation)
Archipelago:AddRetrievedHandler("nfsu won (get)", onStored)
Archipelago:AddSetReplyHandler("nfsu won (set)", onStored)
"""

README_TXT = """Need for Speed: Underground - PopTracker pack for the Archipelago world (version %s)

Install: put this .zip (do not unpack it) into PopTracker's "packs" folder, start PopTracker, open the pack and
click "AP" to connect with the same server address and slot name as the NFSU client.

Events tab: one field per event. A field is cleared when all checks of the event are sent; an event you cannot
enter yet (its Event Pack is missing) is shown as not accessible.
Time Trials tab: the events without checks (time trials, the choice event and the finale). They are cleared
when the NFSU client (0.4 or newer) reports them as won.
Items tab: Event Packs, parts, cars and the two finale items you have received.

This pack contains no game assets; all images are plain drawn panels.
"""


if __name__ == "__main__":
    main()

"""PS2 memory addresses for Need for Speed: Underground.

Values that are None are still placeholders – found so far (NTSC-U): Bank, event status table, last race
difficulty, last won event, map availability patch. See research/RAM_Adressen_Anleitung.md,
research/Patch_Kartenfreigabe.md and tools/pine_memscan.py.

Addresses are EE RAM addresses as PINE sees them (0x00000000-0x01FFFFFF). The client checks the game serial
reported by PCSX2 and only uses the table of a known version. A feature whose address is still None is
skipped and reported once in the client log ("not mapped yet"), so the client can be tested piece by piece.

Value formats are guesses and must be confirmed together with the address ("TODO" notes).
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

SERIAL_NTSC_U = "SLUS-20811"

#: (address, original word, patched word)
CodePatch = Tuple[Tuple[int, int, int], ...]


@dataclass(frozen=True)
class AddressMap:
    # ---------------------------------------------------------------- game state
    #: u32 – which screen the game is in. Map the raw values in GAME_MODES below.
    game_mode: Optional[int] = None
    #: u32 – nonzero while a race is loaded: from the start until back on the map, results screen included.
    #: NTSC-U 0x005005A8 (u32 0/1): 1 in sprint (#2, racing + results), knockout and drag (#4, racing, blown-engine
    #: pause, results), 0 in the shop and twice on the map. Equivalent alternatives: 0x004E7364,
    #: 0x005016AC, 0x005084A0, 0x004EA6B0, 0x0047F298. NOT 0x004D41B0 (racer list, stays 0 in drag races).
    race_active: Optional[int] = None
    #: u32 pointer to the race info object; the player's position (u32, 1 = first) is at +race_position_offset,
    #: followed by the positions of the other racers (then racer pointers). Only valid while race_active.
    #: NTSC-U 0x004D3CC0 / +0x9D8 (live: 4, 1, 3 during #2 and 4 on its results screen; #5 knockout won 1 of 4;
    #: #4 drag 4 of 4 after a blown engine, 1 of 4 when won; #13 drift lists only the player: 1 of 1).
    #: A blown engine (drag) shows no results popups – the game pauses instead, so it is not counted as a loss.
    #: Win/loss itself comes from the results popups ("Sorry, you lost this event." = lost).
    race_info_pointer: Optional[int] = None
    race_position_offset: int = 0
    race_max_racers: int = 8

    # ---------------------------------------------------------------- career
    #: Base address of the per-event status table, events 0..112, `event_stride` bytes each.
    #: NTSC-U: 0x004AC9E4, 1 byte per event (index = event number, #0 = prologue), 0 locked / 1 available /
    #: 2 won. Found: after the prologue 02 01 01 01 01 01 00…, winning #1 -> byte 1 = 2,
    #: winning #2 -> byte 2 = 2.
    event_table: Optional[int] = None
    event_stride: int = 0
    #: Offset inside one entry: u8 status, with the raw values below.
    event_status_offset: int = 0
    event_status_locked: Optional[int] = None
    event_status_available: Optional[int] = None
    event_status_won: Optional[int] = None
    #: Status of the event that is being raced right now (selected/started, not yet booked). The client never
    #: overwrites it. NTSC-U: 3 – #4 showed 3 on the results screen and switched to 2 (+ Bank) back on the map.
    event_status_active: Optional[int] = None
    #: Offset inside one entry: u8 highest difficulty won (0-2), if the game stores it.
    #: NTSC-U: the game does NOT store a difficulty per event – see last_race_difficulty.
    event_difficulty_offset: Optional[int] = None
    #: u8 – difficulty of the last race actually driven (0 Easy, 1 Medium, 2 Hard); not changed by just
    #: selecting a difficulty. The client reads it when an event switches to "won".
    #: NTSC-U: 0x004AC9E0 – 0 after an Easy win (#1), 1 after a Medium win (#2), stayed 1 while Hard was only
    #: selected; 1 again after a Medium win of #4. TODO: confirm with a Hard (2) win.
    last_race_difficulty: Optional[int] = None
    #: i32 – number of the last won event (-1 before the first win). NTSC-U: 0x004ADA20 (-1 -> 1 -> 2).
    last_won_event: Optional[int] = None
    #: u8 – current Underground Mode "set" (0-65). NTSC-U: there is no such variable – see availability_patch.
    career_set: Optional[int] = None
    #: Code patch that turns off the game's own event unlocking. When the Race Map is built, the game resets
    #: every "available" (1) event to 0 and unlocks again from per-event prerequisite lists. With the patch the
    #: client alone decides which events are available, and events of several sets show at the same time.
    #: NTSC-U: 0x00316800 "addiu sp,sp,-64; sd s2,32(sp)" -> "jr ra; nop" (research/Patch_Kartenfreigabe.md,
    #: found with a PCSX2 read breakpoint, live tested: #1–#13 shown at once).
    availability_patch: CodePatch = ()
    #: Event numbers (wiki numbering, data/events.py) are not always the game's table index: NTSC-U has no
    #: record #85, so wiki #85..#112 are game #86..#113 (e.g. wiki #91 "Eddie's Posse Part 1" = game #92).
    #: Listed here: the game indices that have no event. Found from the event records in RAM.
    event_index_gaps: Tuple[int, ...] = ()

    # ---------------------------------------------------------------- shop unlock patch
    #: The shop asks IsPartUnlocked(category, level) (NTSC-U 0x00316BA0): it searches the event whose reward list
    #: contains (category, level) and returns "that event is won". The patch replaces that last step with a byte
    #: lookup in a client-written table, so parts come from Archipelago items instead of race wins.
    #: Category ids: data/addresses.py PART_CATEGORY_ID; levels 1-3, 4 = unique (choice event) part.
    #: Parts no event lists (e.g. Level 1 visual parts) stay always available.
    part_unlock_patch: CodePatch = ()
    #: Byte table read by the patched code: address of (category, level) = part_unlock_table + category*4 + level-1.
    #: NTSC-U: unused entries 128..227 of the 256-byte event status table (no event records there; saved with the
    #: profile, harmless without the patch).
    part_unlock_table: Optional[int] = None

    # ---------------------------------------------------------------- car unlock patch
    #: IsCarUnlocked(career, car hash) (NTSC-U 0x00316DE0) works like IsPartUnlocked: the event whose reward list
    #: has the car must be won; cars no event lists (starter cars) are always available. The patch replaces the
    #: whole function with a search in the game's car hash list (`car_hash_list`) and a byte lookup in
    #: `car_unlock_table` (same index); hashes not in the list stay available.
    car_unlock_patch: CodePatch = ()
    #: u32 list of car name hashes (bStringHash, e.g. "SKYLINE"), in game order. The client checks it against
    #: CAR_HASH_ORDER before applying the patch.
    car_hash_list: Optional[int] = None
    #: Byte table: 1 = car available, index = position in CAR_HASH_ORDER.
    #: NTSC-U: entries 228..248 of the 256-byte event status table (right after part_unlock_table).
    car_unlock_table: Optional[int] = None

    # ---------------------------------------------------------------- money
    #: u32 – Bank of the Underground Mode profile.
    #: NTSC-U: 0x004ADA0C – found by a memory search (find 10000 -> refine 2000 = 1 hit), write test 2500 shown in game.
    #: Neighbours at that time: +4 = 10000, +8 = 8000 (maybe "earned" / "spent" totals; not needed so far).
    bank: Optional[int] = None

    # ---------------------------------------------------------------- current car / race effects (traps, experimental)
    #: Base of the installed performance level per category of the current car (u8 each).
    installed_performance: Optional[int] = None
    #: float – nitrous left in the current race.
    nitrous_amount: Optional[int] = None
    #: float – a speed/power scale of the player car, used for the slowdown effect. TODO: find one.
    player_speed_scale: Optional[int] = None
    #: u8 – HUD visible flag.
    hud_visible: Optional[int] = None
    #: float/u8 – style point multiplier of the current race.
    style_multiplier: Optional[int] = None
    #: u32 – paint colour id of the current car.
    paint_color: Optional[int] = None
    #: u8 – write 1 to end the current race as lost (if such a flag exists). TODO.
    force_race_loss: Optional[int] = None

    # ---------------------------------------------------------------- engine heat / blown engine (drag, Death Link)
    # Player racer = the pointer right behind the position list (race_info_pointer, race_position_offset + 4 * n).
    # Heat object = *(*(racer + racer_sim_offset) + sim_engine_heat_offset). NTSC-U (Drop The Klutch):
    # +0x8C float temperature 0..1 (HUD 0x0013DF60), +0x98 time the temperature reached the limit, +0x94 u32
    # blown. The heat update (0x00196BE8) sets blown after more than 1.0 s at the limit; the race manager
    # (0x0014C10C) then drops the racer with the "Blown Engine" popup. Both only run while
    # engine_heat_enabled != 0 (drag races). Live test: blown = 1 written with a cold engine -> "Blown Engine".
    # Sprint live test: engine_heat_enabled = 1 + blown = 1 -> results screen, player 4th "Blown Engine", popup
    # "Sorry, you lost". The flag stays 1 until the next race setup; the client switches it off itself.
    #: u32 – race option "engine heat simulated", 1 in drag races. NTSC-U: 0x0046FB20.
    engine_heat_enabled: Optional[int] = None
    racer_sim_offset: Optional[int] = None
    sim_engine_heat_offset: Optional[int] = None
    engine_blown_offset: Optional[int] = None
    #: Lowest address a valid heap pointer in that chain can have (results screen: stale values like 0x0003F24D).
    heap_pointer_min: int = 0x00100000

    # ---------------------------------------------------------------- "Race Victory Reward" popups
    # After a win the game builds all reward popups up front as a ring list of text nodes, already on the results
    # screen (research/Belohnungs_Popup_und_Shop.md). The client writes the Archipelago items into them.
    #: u32 pointer to the results/reward object; 0 when no reward popups exist (map, menus, racing).
    #: NTSC-U: 0x005013B0 (0 on the map, 0x01310780 on results + reward screen of #6).
    reward_popup_owner: Optional[int] = None
    #: Offset of the list head (sentinel: +0 first node, +4 last node) inside that object. NTSC-U: 0x0C.
    reward_popup_list_offset: int = 0x0C
    #: Node: +0 next, +4 prev, +8 type tag, +0x0C ASCII text ('^' = line break). NTSC-U tag 0x2CCB70AA.
    #: Other tags in the same list are skipped (NTSC-U 0x6A765215 = "Style Reward" popup, style point vinyls).
    reward_popup_tag: Optional[int] = None
    reward_popup_text_offset: int = 0x0C
    #: Characters the client may write per node (nodes are 0x140 bytes apart; originals are up to ~100 chars).
    reward_popup_max_chars: int = 200

    # ---------------------------------------------------------------- "now playing" banner
    # The game shows the current song (title + artist) in a small banner. The client reuses it for
    # "Received …" / "Sent …" messages: it writes two strings and triggers the banner.
    # Find the strings with `tools/pine_memscan.py findstr "<song title>"` while the banner is visible.
    #: char buffer of the first banner line (song title), null-terminated ASCII.
    banner_line1: Optional[int] = None
    #: char buffer of the second banner line (artist).
    banner_line2: Optional[int] = None
    #: Maximum characters per line (buffer size - 1).
    banner_max_chars: int = 0
    #: u8/u32 that starts the banner animation (e.g. a timer or "show" flag), and the value to write.
    banner_trigger: Optional[int] = None
    banner_trigger_value: int = 1
    banner_trigger_size: int = 1

    # ---------------------------------------------------------------- Archipelago save block
    #: 8 unused bytes inside the memory card save data that the client may use:
    #: u32 received-item index (Bank/traps already applied) + u32 flags. Must survive saving/loading.
    ap_save_block: Optional[int] = None

    #: Raw game_mode values -> names used by the client ("menu", "career_menu", "racing", "results").
    game_modes: Dict[int, str] = field(default_factory=dict)


ADDRESSES: Dict[str, AddressMap] = {
    SERIAL_NTSC_U: AddressMap(
        bank=0x004ADA0C,
        event_table=0x004AC9E4,
        event_stride=1,
        event_status_offset=0,
        event_status_locked=0,
        event_status_available=1,
        event_status_won=2,
        event_status_active=3,
        last_race_difficulty=0x004AC9E0,
        last_won_event=0x004ADA20,
        reward_popup_owner=0x005013B0,
        reward_popup_tag=0x2CCB70AA,
        race_active=0x005005A8,
        race_info_pointer=0x004D3CC0,
        race_position_offset=0x9D8,
        engine_heat_enabled=0x0046FB20,
        racer_sim_offset=0x34,
        sim_engine_heat_offset=0x48,
        engine_blown_offset=0x94,
        availability_patch=(
            (0x00316800, 0x27BDFFC0, 0x03E00008),   # addiu sp, sp, -64  ->  jr ra
            (0x00316804, 0xFFB20020, 0x00000000),   # sd s2, 32(sp)      ->  nop (delay slot)
        ),
        event_index_gaps=(85,),
        # In 0x00316BA0, after the matching event record was found (s1 = career 0x004AC698, s2 = level,
        # s3 = category): "return Status[event] == 2" -> "return table[category*4 + level - 1]".
        part_unlock_patch=(
            (0x00316BE0, 0x0C0C5C18, 0x00131080),   # jal StatusPtr        -> sll  v0, s3, 2
            (0x00316BE4, 0x0200282D, 0x00521021),   # daddu a1, s0, zero   -> addu v0, v0, s2
            (0x00316BE8, 0x80420000, 0x00511021),   # lb v0, 0(v0)         -> addu v0, v0, s1
            (0x00316BEC, 0x38420002, 0x804203CB),   # xori v0, v0, 2       -> lb   v0, 0x3CB(v0)
            (0x00316BF0, 0x10000013, 0x10000013),   # b 0x00316C40 (epilogue, unchanged)
            (0x00316BF4, 0x2C420001, 0x00000000),   # sltiu v0, v0, 1      -> nop
        ),
        part_unlock_table=0x004ACA64,  # = career 0x004AC698 + 0x3CB + 1
        # IsCarUnlocked(a0 career, a1 hash) -> for i in 0..20: if list[i] == hash: return table[i]; return 1
        car_unlock_patch=(
            (0x00316DE0, 0x27BDFFC0, 0x3C03004C),   # lui   v1, 0x004C
            (0x00316DE4, 0xFFB10010, 0x246360F8),   # addiu v1, v1, 0x60F8      (v1 = car_hash_list)
            (0x00316DE8, 0x0080882D, 0x0000402D),   # daddu t0, zero, zero
            (0x00316DEC, 0xFFB20020, 0x8C690000),   # loop: lw t1, 0(v1)
            (0x00316DF0, 0x3C040049, 0x11250007),   # beq   t1, a1, found
            (0x00316DF4, 0xFFBF0030, 0x25080001),   # addiu t0, t0, 1           (delay slot)
            (0x00316DF8, 0xFFB00000, 0x2D0A0015),   # sltiu t2, t0, 21
            (0x00316DFC, 0x00A0902D, 0x00000000),   # nop (R5900 short loop)
            (0x00316E00, 0x0C07666C, 0x1540FFFA),   # bne   t2, zero, loop
            (0x00316E04, 0x24846610, 0x24630004),   # addiu v1, v1, 4           (delay slot)
            (0x00316E08, 0x10400009, 0x03E00008),   # jr    ra                  (not in list)
            (0x00316E0C, 0x24020001, 0x24020001),   # addiu v0, zero, 1         (unchanged)
            (0x00316E10, 0x10000019, 0x3C02004B),   # found: lui v0, 0x004B
            (0x00316E14, 0xDFBF0030, 0x00481021),   # addu  v0, v0, t0          (t0 = index + 1)
            (0x00316E18, 0x0C0C5C18, 0x03E00008),   # jr    ra
            (0x00316E1C, 0x0200282D, 0x8042CAC7),   # lb    v0, -0x3539(v0)     (0x004ACAC7 + index + 1)
        ),
        car_hash_list=0x004C60F8,
        car_unlock_table=0x004ACAC8,
    ),
}

#: Game category id used by IsPartUnlocked / the event reward lists (NTSC-U, read from the event records:
#: entries (0, category, level) – e.g. #6 lists 18/19/20 Level 1, #7 the same three as unique Level 4).
PART_CATEGORY_ID: Dict[str, int] = {
    # visual (data/parts.py VISUAL names; Vinyl and Wide Body Kit only have unique parts)
    "Paint": 0, "Decals": 1, "Muffler Tip": 2, "Rims": 3, "Window Tint": 4, "Side Skirts": 5, "Headlights": 6,
    "Vinyl": 7, "Spoiler": 8, "Front Bumper": 9, "Taillights": 10, "Rear Bumper": 11, "Hood": 12,
    "Roof Scoop": 13, "Neon": 14, "Wide Body Kit": 15,
    # performance (data/parts.py PERFORMANCE names)
    # 16/24 live-corrected: a Progressive Nitrous item (id 16 at the time) unlocked the Weight Reduction
    # kit in the shop. Brakes and Tires are live-confirmed; Suspension 21 is not confirmed yet.
    "Weight Reduction": 16, "Brakes": 17, "Engine/Exhaust": 18, "Drivetrain": 19, "Tires": 20, "Suspension": 21,
    "Turbo": 22, "ECU & Fuel": 23, "Nitrous": 24,
}

#: Unique (Level 4) parts per choice event (wiki numbers): the categories the game lists for that event.
UNIQUE_PART_CATEGORIES: Dict[int, Tuple[str, ...]] = {
    7: ("Engine/Exhaust", "Drivetrain", "Tires"),
    15: ("Hood",),
    26: ("ECU & Fuel", "Turbo", "Brakes"),
    47: ("Rims",),
    68: ("Vinyl",),
    77: ("Spoiler",),
    96: ("Weight Reduction", "Nitrous", "Suspension"),
    110: ("Wide Body Kit",),
}

#: The game's car hash list (NTSC-U 0x004C60F8, 21 u32): (internal name, data/cars.py name). Hashes are
#: bStringHash(internal name) – found from the event reward lists (type 2 entries) and the list in RAM.
#: "MINI" is in the list but not a career car (left available).
CAR_HASH_ORDER: Tuple[Tuple[str, Optional[str]], ...] = (
    ("FOCUS", "Ford Focus ZX3"), ("NEON", "Dodge Neon"), ("CELICA", "Toyota Celica GT-S"),
    ("SUPRA", "Toyota Supra"), ("ECLIPSE", "Mitsubishi Eclipse GSX"), ("S2000", "Honda S2000"), ("MINI", None),
    ("RSX", "Acura RSX Type-S"), ("IMPREZA", "Subaru Impreza 2.5 RS"), ("LANCER", "Mitsubishi Lancer ES"),
    ("INTEGRA", "Acura Integra Type-R"), ("CIVIC", "Honda Civic Si"), ("TIBURON", "Hyundai Tiburon GT V6"),
    ("350Z", "Nissan 350Z"), ("RX7", "Mazda RX-7"), ("PEUGOT", "Peugeot 206"), ("GOLF", "Volkswagen Golf GTI"),
    ("SENTRA", "Nissan Sentra SE-R Spec V"), ("MIATA", "Mazda MX-5"), ("240SX", "Nissan 240SX"),
    ("SKYLINE", "Nissan Skyline GT-R (R34)"),
)


def string_hash(text: str) -> int:
    """The game's bStringHash: h = h * 33 + c, starting at 0xFFFFFFFF."""
    h = 0xFFFFFFFF
    for c in text.encode("ascii"):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


#: Paint id used by the "Pink Paint Trap". TODO: fill in.
PINK_PAINT_ID: Optional[int] = None

"""Game interface: everything the client reads from / writes to NFSU memory goes through this class.

Every method needs one or more addresses from data/addresses.py. If one is still a placeholder (None),
NotMapped is raised and the caller skips that feature. When addresses are found, usually only this file
(and the value formats in data/addresses.py) need to change.
"""
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from ..data.addresses import ADDRESSES, CAR_HASH_ORDER, PINK_PAINT_ID, AddressMap, string_hash
from ..data.parts import PERFORMANCE
from .pine import Pine

logger = logging.getLogger("NFSU")

EVENT_NUMBERS = range(0, 113)


def banner_text(text: str, max_chars: int) -> bytes:
    """Plain ASCII (the game font has no other glyphs), shortened with '...' if too long."""
    clean = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)
    if len(clean) > max_chars:
        clean = clean[:max(0, max_chars - 3)].rstrip() + "..."
    return clean.encode("ascii")


class NotMapped(Exception):
    """A memory address needed for this feature is still a placeholder."""


class WrongGame(Exception):
    pass


#: Text of the only results popup after a lost event (NTSC-U, seen in game).
LOST_POPUP_TEXT = "Sorry, you lost"
#: First byte of the client's counter in the save data (see AddressMap.ap_save_block).
SAVE_BLOCK_MAGIC = 0xA5


@dataclass
class RaceResult:
    won: bool
    position: Optional[int] = None
    racers: int = 0

    @property
    def last_place(self) -> bool:
        # Drift races list only the player (live #13: "1 of 1"): without a field, a loss counts as last place.
        if self.position is None or self.racers <= 1:
            return not self.won
        return self.position >= self.racers


class NFSUInterface:
    def __init__(self, pine: Optional[Pine] = None) -> None:
        self.pine = pine or Pine()
        self.serial: Optional[str] = None
        self.addr: Optional[AddressMap] = None

    # ------------------------------------------------------------------ connection
    def connect(self) -> bool:
        """Connects to PCSX2 and checks the game serial. Returns True when ready."""
        if not self.pine.connect():
            return False
        serial = self.pine.game_id().strip()
        if not serial:
            return False  # emulator running but no game booted yet
        if serial not in ADDRESSES:
            self.serial, self.addr = None, None
            raise WrongGame(f"PCSX2 is running '{serial}'. Supported: {', '.join(ADDRESSES)} "
                            f"(Need for Speed: Underground, NTSC-U).")
        self.serial, self.addr = serial, ADDRESSES[serial]
        return True

    def disconnect(self) -> None:
        self.pine.disconnect()
        self.serial, self.addr = None, None

    @property
    def ready(self) -> bool:
        return self.pine.connected and self.addr is not None

    def _a(self, name: str) -> int:
        value = getattr(self.addr, name) if self.addr else None
        if value is None:
            raise NotMapped(name)
        return value

    # ------------------------------------------------------------------ state
    def game_mode(self) -> str:
        raw = self.pine.read32(self._a("game_mode"))
        return self.addr.game_modes.get(raw, "unknown")

    def in_race(self) -> bool:
        """True while a race is loaded (start until back on the map, results screen included)."""
        return self.pine.read32(self._a("race_active")) != 0

    def race_positions(self) -> Tuple[Optional[int], int]:
        """(player position, number of racers) while a race is loaded, else (None, 0).
        The racer count is the longest prefix of the position list that is a permutation of 1..n."""
        a = self.addr
        base = self.pine.read32(self._a("race_info_pointer"))
        if not 0 < base < 0x02000000:
            return None, 0
        start = base + a.race_position_offset
        values = self.pine.batch_read([(start + 4 * i, 4) for i in range(a.race_max_racers)])
        for n in range(len(values), 0, -1):
            if sorted(values[:n]) == list(range(1, n + 1)):
                return values[0], n
        return None, 0

    def race_result(self) -> Optional[RaceResult]:
        """Result while the results popups are on screen, else None. Lost = the game's "Sorry, you lost this
        event." popup; any other results popup list (rewards, Bank, possibly rewritten by the client) = won."""
        found = self.reward_popups()
        if not found:
            return None
        won = not any(text.startswith(LOST_POPUP_TEXT) for _, text in found[1])
        try:
            position, racers = self.race_positions()
        except NotMapped:
            position, racers = None, 0
        return RaceResult(won, position, racers)

    # ------------------------------------------------------------------ career
    def game_index(self, number: int) -> int:
        """Game table index of an event (wiki numbering, data/events.py); skips the game's unused indices."""
        index = number
        for gap in sorted(self.addr.event_index_gaps if self.addr else ()):
            if index >= gap:
                index += 1
        return index

    def event_number(self, index: int) -> Optional[int]:
        """Event number (wiki numbering) of a game table index, or None for an unused/unknown index."""
        for number in EVENT_NUMBERS:
            if self.game_index(number) == index:
                return number
        return None

    def _event_entry(self, number: int) -> int:
        return self._a("event_table") + self.game_index(number) * self.addr.event_stride

    def _status_bytes(self) -> List[int]:
        """Status of every event in EVENT_NUMBERS order (stride 1: one read)."""
        a = self.addr
        if a.event_stride == 1:
            raw = self.pine.read_bytes(self._a("event_table") + a.event_status_offset,
                                       self.game_index(EVENT_NUMBERS[-1]) + 1)
            return [raw[self.game_index(n)] for n in EVENT_NUMBERS]
        return list(self.pine.batch_read([(self._event_entry(n) + a.event_status_offset, 1) for n in EVENT_NUMBERS]))

    def event_results(self) -> Dict[int, Optional[int]]:
        """Won events: event number -> difficulty won (0-2), or None if the game does not store it."""
        a = self.addr
        won = a.event_status_won if a else None
        if won is None or a.event_stride <= 0:
            raise NotMapped("event_status_won / event_stride")
        if a.event_difficulty_offset is None:
            return {n: None for n, s in zip(EVENT_NUMBERS, self._status_bytes()) if s == won}
        reads = [(self._event_entry(n) + a.event_status_offset, 1) for n in EVENT_NUMBERS]
        if a.event_difficulty_offset is not None:
            reads += [(self._event_entry(n) + a.event_difficulty_offset, 1) for n in EVENT_NUMBERS]
        values = self.pine.batch_read(reads)
        status = values[:len(EVENT_NUMBERS)]
        diffs = values[len(EVENT_NUMBERS):]
        return {n: min(2, d) for n, s, d in zip(EVENT_NUMBERS, status, diffs) if s == won}

    def last_race_difficulty(self) -> int:
        return min(2, self.pine.read8(self._a("last_race_difficulty")))

    def last_won_event(self) -> Optional[int]:
        value = self.pine.read32(self._a("last_won_event"))
        return None if value >= 0x80000000 else self.event_number(value)

    # ------------------------------------------------------------------ code patches
    def _patch(self, name: str):
        patch = getattr(self.addr, name) if self.addr else ()
        if not patch:
            raise NotMapped(name)
        return patch

    def patch_state(self, name: str) -> str:
        """"patched", "original" or "unknown" (neither – different game version or another patch)."""
        patch = self._patch(name)
        words = self.pine.batch_read([(addr, 4) for addr, _, _ in patch])
        if all(w == new for w, (_, _, new) in zip(words, patch)):
            return "patched"
        if all(w == old for w, (_, old, _) in zip(words, patch)):
            return "original"
        return "unknown"

    def apply_patch(self, name: str) -> bool:
        """Writes a code patch from data/addresses.py if the original code is there. True when active."""
        state = self.patch_state(name)
        if state == "original":
            self.pine.batch_write([(addr, 4, new) for addr, old, new in self._patch(name) if old != new])
            state = self.patch_state(name)
        return state == "patched"

    def remove_patch(self, name: str) -> None:
        """Restores the original code."""
        if self.patch_state(name) == "patched":
            self.pine.batch_write([(addr, 4, old) for addr, old, new in self._patch(name) if old != new])

    # map availability patch
    def availability_patch_state(self) -> str:
        return self.patch_state("availability_patch")

    def apply_availability_patch(self) -> bool:
        """Turns off the game's own event unlocking. Returns True when the patch is active."""
        return self.apply_patch("availability_patch")

    def remove_availability_patch(self) -> None:
        """Restores the original code (the game then unlocks events by its own rules again)."""
        self.remove_patch("availability_patch")

    # race Bank patch
    def apply_bank_reward_patch(self) -> bool:
        """Event wins pay no Bank (vanilla_bank_rewards off). True when active."""
        return self.apply_patch("bank_reward_patch")

    def remove_bank_reward_patch(self) -> None:
        self.remove_patch("bank_reward_patch")

    # shop unlock patch
    def apply_part_unlock_patch(self) -> bool:
        """Makes the shop ask the client's part table instead of the event status. True when active."""
        self._a("part_unlock_table")
        return self.apply_patch("part_unlock_patch")

    def remove_part_unlock_patch(self) -> None:
        self.remove_patch("part_unlock_patch")

    def write_part_unlocks(self, unlocked: Dict[Tuple[int, int], bool]) -> None:
        """(game category id, level 1-4) -> unlocked. Only writes bytes that differ."""
        base = self._a("part_unlock_table")
        size = (max(c for c, _ in unlocked) + 1) * 4 if unlocked else 0
        current = self.pine.read_bytes(base, size) if size else b""
        writes = []
        for (category, level), on in unlocked.items():
            offset = category * 4 + level - 1
            if current[offset] != int(on):
                writes.append((base + offset, 1, int(on)))
        if writes:
            self.pine.batch_write(writes)

    def set_events_available(self, open_events: Iterable[int], won: Dict[int, int],
                             reopen: Iterable[int]) -> None:
        """Makes exactly the given events available; locks the others. Won events stay won unless listed
        in `reopen` (they need a higher difficulty), which are set back to available."""
        a = self.addr
        if a is None or None in (a.event_status_available, a.event_status_locked) or a.event_stride <= 0:
            raise NotMapped("event_status_available / event_status_locked")
        open_set, reopen_set = set(open_events), set(reopen)
        current = self._status_bytes()  # EVENT_NUMBERS starts at 0, so current[n] is event n
        writes = []
        for n in EVENT_NUMBERS[1:]:
            if n in won and n not in reopen_set:
                continue
            if current is not None and a.event_status_active is not None and current[n] == a.event_status_active:
                continue  # being raced right now – never touch
            if current is not None and current[n] == a.event_status_won and n not in reopen_set:
                continue
            value = a.event_status_available if n in open_set else a.event_status_locked
            writes.append((self._event_entry(n) + a.event_status_offset, 1, value))
        self.pine.batch_write(writes)

    # car unlock patch
    def car_list_matches(self) -> bool:
        """True when the game's car hash list is the one the car patch expects (CAR_HASH_ORDER)."""
        base = self._a("car_hash_list")
        words = self.pine.batch_read([(base + 4 * i, 4) for i in range(len(CAR_HASH_ORDER))])
        return list(words) == [string_hash(internal) for internal, _ in CAR_HASH_ORDER]

    def apply_car_unlock_patch(self) -> bool:
        """Makes car availability come from the client's car table. True when active."""
        self._a("car_unlock_table")
        if self.patch_state("car_unlock_patch") == "original" and not self.car_list_matches():
            return False
        return self.apply_patch("car_unlock_patch")

    def remove_car_unlock_patch(self) -> None:
        self.remove_patch("car_unlock_patch")

    def write_car_unlocks(self, unlocked: Dict[str, bool]) -> None:
        """Car name (data/cars.py) -> available. Cars not given (and "MINI") stay available. Only writes changes."""
        base = self._a("car_unlock_table")
        current = self.pine.read_bytes(base, len(CAR_HASH_ORDER))
        writes = []
        for i, (_, name) in enumerate(CAR_HASH_ORDER):
            value = int(unlocked.get(name, True)) if name is not None else 1
            if current[i] != value:
                writes.append((base + i, 1, value))
        if writes:
            self.pine.batch_write(writes)

    # ------------------------------------------------------------------ money
    def bank(self) -> int:
        """Bank as the game sees it: a signed 32-bit value (a too expensive purchase can make it negative)."""
        value = self.pine.read32(self._a("bank"))
        return value - (1 << 32) if value & 0x80000000 else value

    def add_bank(self, amount: int) -> int:
        new = max(0, min(0x7FFFFFFF, self.bank() + amount))
        self.pine.write32(self._a("bank"), new)
        return new

    # ------------------------------------------------------------------ race effects (traps, experimental)
    def installed_performance(self) -> Dict[str, int]:
        base = self._a("installed_performance")
        values = self.pine.batch_read([(base + i, 1) for i in range(len(PERFORMANCE))])
        return {c.name: v for c, v in zip(PERFORMANCE, values)}

    def set_installed_performance(self, levels: Dict[str, int]) -> None:
        base = self._a("installed_performance")
        index = {c.name: i for i, c in enumerate(PERFORMANCE)}
        self.pine.batch_write([(base + index[name], 1, lvl) for name, lvl in levels.items()])

    # ------------------------------------------------------------------ effects
    def drain_nitrous(self) -> None:
        self.pine.write_float(self._a("nitrous_amount"), 0.0)

    def set_speed_scale(self, scale: float) -> None:
        self.pine.write_float(self._a("player_speed_scale"), scale)

    def set_hud_visible(self, visible: bool) -> None:
        self.pine.write8(self._a("hud_visible"), int(visible))

    def set_style_multiplier(self, value: float) -> None:
        self.pine.write_float(self._a("style_multiplier"), value)

    def paint_pink(self) -> None:
        if PINK_PAINT_ID is None:
            raise NotMapped("PINK_PAINT_ID")
        self.pine.write32(self._a("paint_color"), PINK_PAINT_ID)

    def force_race_loss(self) -> None:
        self.pine.write8(self._a("force_race_loss"), 1)

    # ------------------------------------------------------------------ engine heat (drag)
    def _engine_heat_object(self) -> Optional[int]:
        """Address of the player's engine heat object while a race is loaded, else None."""
        a = self.addr
        for name in ("racer_sim_offset", "sim_engine_heat_offset", "engine_blown_offset"):
            self._a(name)
        _, racers = self.race_positions()
        if not racers:
            return None
        base = self.pine.read32(self._a("race_info_pointer"))
        # The racer pointers follow the position list, which has room for 4 racers: in a drift (only the player)
        # the free slots hold 0xAAAAAAAA and the player's racer pointer is 4 slots in (seen in game). So take
        # the first heap pointer behind the used positions.
        start = base + a.race_position_offset + 4 * racers
        words = self.pine.batch_read([(start + 4 * i, 4) for i in range(a.race_max_racers)])
        pointer = next((w for w in words if a.heap_pointer_min <= w < 0x02000000), None)
        if pointer is None:
            return None
        for offset in (a.racer_sim_offset, a.sim_engine_heat_offset):
            pointer = self.pine.read32(pointer + offset)
            if not a.heap_pointer_min <= pointer < 0x02000000:   # on the results screen the chain is stale
                return None
        return pointer

    def engine_heat_enabled(self) -> bool:
        return self.pine.read32(self._a("engine_heat_enabled")) != 0

    def set_engine_heat_enabled(self, enabled: bool) -> None:
        self.pine.write32(self._a("engine_heat_enabled"), int(enabled))

    def engine_blown(self) -> bool:
        """True once the player's engine blew (drag; the game drops the racer and pauses, no results popups)."""
        if not self.engine_heat_enabled():
            return False
        heat = self._engine_heat_object()
        return heat is not None and self.pine.read32(heat + self.addr.engine_blown_offset) != 0

    def engine_health(self) -> Optional[bool]:
        """True = blown, False = running fine, None = no engine to judge (heat check off, as outside drag, or no
        race object yet/any more, as on a loading or results screen)."""
        if not self.engine_heat_enabled():
            return None
        heat = self._engine_heat_object()
        if heat is None:
            return None
        return self.pine.read32(heat + self.addr.engine_blown_offset) != 0

    def blow_engine(self) -> Optional[bool]:
        """Blows the player's engine: the game shows "Blown Engine" and drops the racer. Drag: the game pauses;
        other races (live-tested in a sprint): results screen, "Blown Engine", last place, "you lost" popup.
        Outside drag the engine heat check is switched on for that (engine_heat_enabled = 1); the caller has to
        switch it off again once the race is over. Returns None if no race is running, else whether the heat
        check had to be switched on."""
        heat = self._engine_heat_object()
        if heat is None:
            return None
        switched_on = not self.engine_heat_enabled()
        if switched_on:
            self.set_engine_heat_enabled(True)
        self.pine.write32(heat + self.addr.engine_blown_offset, 1)
        return switched_on

    # ------------------------------------------------------------------ reward popups
    def active_event(self) -> Optional[int]:
        """Number of the event that is being raced / on its results screen (status 'active'), if any."""
        a = self.addr
        if a is None or a.event_status_active is None or a.event_stride <= 0:
            raise NotMapped("event_status_active")
        status = self._status_bytes()
        hits = [n for n, s in zip(EVENT_NUMBERS, status) if s == a.event_status_active]
        return hits[0] if len(hits) == 1 else None

    def reward_popups(self) -> Optional[Tuple[int, List[Tuple[int, str]]]]:
        """(owner pointer, [(node address, text), …]) while reward popups exist, else None."""
        a = self.addr
        owner = self.pine.read32(self._a("reward_popup_owner"))
        if not 0 < owner < 0x02000000 or a.reward_popup_tag is None:
            return None
        head = owner + a.reward_popup_list_offset
        nodes: List[Tuple[int, str]] = []
        node = self.pine.read32(head)
        for _ in range(16):
            if node == head:
                break
            if not 0 < node < 0x02000000:
                return None
            nxt, _prev, tag = self.pine.batch_read([(node, 4), (node + 4, 4), (node + 8, 4)])
            # Other popup types share the list (e.g. "Style Reward", tag 0x6A765215, after drift events):
            # they are not event rewards, so they are skipped and left untouched.
            if tag == a.reward_popup_tag:
                raw = self.pine.read_bytes(node + a.reward_popup_text_offset, a.reward_popup_max_chars + 1)
                nodes.append((node, raw.split(b"\x00", 1)[0].decode("ascii", "replace")))
            node = nxt
        return (owner, nodes) if nodes else None

    def write_popup_text(self, node: int, text: str) -> None:
        a = self.addr
        data = banner_text(text, a.reward_popup_max_chars) + b"\x00"
        self.pine.batch_write([(node + a.reward_popup_text_offset + i, 1, b) for i, b in enumerate(data)])

    # ------------------------------------------------------------------ "now playing" banner
    def show_banner(self, line1: str, line2: str) -> None:
        a = self.addr
        if a is None or a.banner_max_chars <= 0:
            raise NotMapped("banner_max_chars")
        writes = []
        for name, text in (("banner_line1", line1), ("banner_line2", line2)):
            data = banner_text(text, a.banner_max_chars) + b"\x00"
            base = self._a(name)
            writes += [(base + i, 1, b) for i, b in enumerate(data)]
        writes.append((self._a("banner_trigger"), a.banner_trigger_size, a.banner_trigger_value))
        self.pine.batch_write(writes)

    # ------------------------------------------------------------------ AP save block
    def read_save_block(self) -> Optional[Tuple[int, int]]:
        raw = self.pine.read_bytes(self._a("ap_save_block"), 4)
        if raw[0] != SAVE_BLOCK_MAGIC:
            return None          # never written in this career
        return (raw[1] & 0x7F) | ((raw[2] & 0x7F) << 7), raw[3] & 0x7F

    def write_save_block(self, index: int, flags: int) -> None:
        base = self._a("ap_save_block")
        index = min(index, 0x3FFF)
        data = bytes([SAVE_BLOCK_MAGIC, 0x80 | (index & 0x7F), 0x80 | (index >> 7), 0x80 | (flags & 0x7F)])
        self.pine.batch_write([(base + i, 1, b) for i, b in enumerate(data)])

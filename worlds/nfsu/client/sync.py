"""Game synchronisation, independent of the network part so it can be unit tested with a fake interface.

`GameSync.tick()` is called about ten times per second (in a worker thread) and:
  1. reads won events and returns the location IDs to send (cumulative per difficulty),
  2. computes which events must be available (tiers by the stars of the received visual items, #111 by
     finale conditions,
     won events re-opened while higher checks are missing) and writes that,
  3. writes the shop and car tables from the Archipelago item state and patches the game to use them (race
     wins no longer unlock parts or cars),
  4. applies one-time items (Bank, traps) exactly once, using a counter stored in the save data,
  5. handles traps and Death Link around races,
  6. reports the goal.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from ..data.addresses import PART_CATEGORY_ID, UNIQUE_PART_CATEGORIES
from ..data.cars import CARS, UNLOCKABLE_CARS
from ..data.events import EVENTS_BY_NUMBER, GOAL_EVENT, TIME_TRIALS
from ..data.parts import PERFORMANCE, VISUAL
from ..logic import full_stars, reputation_from
from ..items import (BANK_ITEMS, FINALE_ITEM, KEY_ITEM, UNIQUE_ITEM_NAMES, VISUAL_ITEM_LEVELS, car_item_name,
                     progressive_name)
from ..data.events import CAREER_EVENTS
from ..locations import EVENT_CHECK_IDS, tier_of
from ..options import TRAPS
from ..packs import START_EVENTS
from .interface import NFSUInterface, NotMapped, RaceResult

logger = logging.getLogger("NFSU")

EPILOGUE_EVENT = 112

#: Events the client may open: all career events 1-110 (incl. choice events, which carry no checks).
PLAYABLE_EVENTS = tuple(e.number for e in CAREER_EVENTS if 1 <= e.number <= 110)

FLAG_STARTING_BANK = 1 << 0
BANK_TAX_PERCENT = 10
SLOWDOWN_SCALE = 0.6
RACE_TRAPS = ("Nitro Drain Trap", "Grip Loss Trap", "Power Cut Trap", "Style Crash Trap", "HUD Blackout Trap")
INSTANT_TRAPS = ("Bank Tax Trap", "Pink Paint Trap")
assert set(RACE_TRAPS) | set(INSTANT_TRAPS) == set(TRAPS)


# ====================================================================== settings
@dataclass
class Settings:
    goal: int = 0
    races_for_goal: int = 80
    time_trials_required: int = 7
    star_gates: bool = True
    star_gate_by_tier: Dict[int, int] = field(default_factory=lambda: {1: 0, 2: 2, 3: 3, 4: 4, 5: 5})
    cars_as_items: bool = True
    starting_bank: int = 0
    bank_multiplier: int = 100
    vanilla_bank_rewards: bool = True
    death_link: bool = False
    death_link_trigger: int = 0   # 0 lose_race, 1 last_place
    death_link_effect: int = 0    # 0 fail_race, 1 nitro_and_slowdown
    death_link_amnesty: int = 0
    starting_car: Optional[str] = None
    #: "Event Pack N" -> event numbers (None: events are no items, tiers open by stars as in 0.1)
    event_packs: Optional[Dict[str, List[int]]] = None

    @classmethod
    def from_slot_data(cls, data: Mapping[str, Any]) -> "Settings":
        s = cls()
        for key in ("goal", "races_for_goal", "time_trials_required", "starting_bank",
                    "bank_multiplier", "death_link_trigger", "death_link_effect", "death_link_amnesty"):
            if key in data:
                setattr(s, key, int(data[key]))
        for key in ("star_gates", "cars_as_items", "vanilla_bank_rewards", "death_link"):
            if key in data:
                setattr(s, key, bool(data[key]))
        if "star_gate_by_tier" in data:
            s.star_gate_by_tier = {int(k): int(v) for k, v in data["star_gate_by_tier"].items()}
        s.starting_car = data.get("starting_car")
        if data.get("event_packs"):
            s.event_packs = {str(k): [int(n) for n in v] for k, v in data["event_packs"].items()}
        return s


# ====================================================================== pure helpers
@dataclass
class ItemState:
    performance: Dict[str, int]
    visual: Dict[str, int]
    cars: Optional[Dict[str, bool]]
    uniques: Dict[int, bool]
    has_finale: bool
    has_key: bool


def item_state(names: List[str], s: Settings) -> ItemState:
    count: Dict[str, int] = {}
    for n in names:
        count[n] = count.get(n, 0) + 1
    perf = {c.name: min(3, count.get(progressive_name(c.name), 0)) for c in PERFORMANCE}
    visual = {}
    for c in VISUAL:
        base = 1 if c.unlock_event[0] == 0 else 0
        got = min(count.get(progressive_name(c.name), 0), len(VISUAL_ITEM_LEVELS[c.name]))
        visual[c.name] = VISUAL_ITEM_LEVELS[c.name][got - 1] if got else base
    cars = None
    if s.cars_as_items:
        # vanilla start: the five starter cars are free; random start: only the start car (also sent as item).
        cars = {c.name: bool(count.get(car_item_name(c.name)))
                or c.name == s.starting_car
                or (s.starting_car is None and c.unlock_event is None)
                for c in CARS}
    uniques = {event: bool(count.get(name)) for event, name in UNIQUE_ITEM_NAMES.items()}
    return ItemState(perf, visual, cars, uniques, bool(count.get(FINALE_ITEM)), bool(count.get(KEY_ITEM)))


def part_unlocks(names: List[str], results: Mapping[int, int], s: Settings) -> Dict[Tuple[int, int], bool]:
    """Shop table for the part unlock patch: (game category id, level) -> unlocked.

    Performance: progressive items (Level n needs n items). Visual: progressive items per category (Level 1 is
    always for sale). Unique parts (Level 4): the choice event is won.
    """
    state = item_state(names, s)
    out: Dict[Tuple[int, int], bool] = {}
    for c in PERFORMANCE:
        cid = PART_CATEGORY_ID[c.name]
        for level in (1, 2, 3):
            out[(cid, level)] = state.performance[c.name] >= level
    for c in VISUAL:
        cid = PART_CATEGORY_ID[c.name]
        for level in (1, 2, 3):
            out[(cid, level)] = level == 1 or state.visual[c.name] >= level
    for event, categories in UNIQUE_PART_CATEGORIES.items():
        for name in categories:
            out[(PART_CATEGORY_ID[name], 4)] = event in results
    return out


def event_check_ids(number: int) -> Set[int]:
    """Location IDs earned by the first win of `number` (any difficulty): its rewards, or Victory.
    Choice events (time trials, #110) have none."""
    return set(EVENT_CHECK_IDS.get(number, ()))


def checks_for_results(results: Mapping[int, int]) -> Set[int]:
    ids: Set[int] = set()
    for number in results:
        ids |= event_check_ids(number)
    return ids


_CHECK_EVENT: Dict[int, int] = {i: n for n, ids in EVENT_CHECK_IDS.items() for i in ids}


def results_from_checks(checked: Set[int]) -> Dict[int, int]:
    """Wins known from checks already on the server (they survive loading an older save)."""
    return {_CHECK_EVENT[loc]: 0 for loc in checked if loc in _CHECK_EVENT}


def merge_results(*sources: Mapping[int, int]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for src in sources:
        for n, d in src.items():
            out[n] = max(out.get(n, -1), d)
    return out


def time_trial_wins(results: Mapping[int, int]) -> int:
    return sum(1 for n in TIME_TRIALS if n in results)


def received_reputation(names: List[str]) -> float:
    """Stars from the received items – the same function the generator logic uses."""
    count: Dict[str, int] = {}
    for n in names:
        count[n] = count.get(n, 0) + 1
    return reputation_from(lambda name: count.get(name, 0))


def open_tiers(reputation: float, s: Settings) -> Set[int]:
    tiers = {1}
    for tier in (2, 3, 4):
        if not s.star_gates or full_stars(reputation) >= s.star_gate_by_tier.get(tier, 0):
            tiers.add(tier)
        else:
            break  # tiers open in order
    return tiers


def finale_open(results: Mapping[int, int], state: ItemState, s: Settings, reputation: float = 0.0) -> bool:
    # star_gate_by_tier already holds 0 where no stars are needed (0.1 seeds: all 0 with star_gates off).
    stars_ok = full_stars(reputation) >= s.star_gate_by_tier.get(5, 0)
    return (s.goal == 0 and state.has_finale and state.has_key and stars_ok
            and time_trial_wins(results) >= s.time_trials_required)


#: The race map lists at most 12 open events (fixed 12-slot list, 0x00315DD8 `slti 12`, lowest number first;
#: seen in game). The client decides which unlocked events get the slots.
MAP_SLOTS = 12


def received_packs(names: List[str], s: Settings) -> List[str]:
    if not s.event_packs:
        return []
    got = set(names)
    return [name for name in s.event_packs if name in got]


def unlocked_events(names: List[str], reputation: float, s: Settings) -> Set[int]:
    """Events the player may race (#1-#110): by Event Packs (if on) and open tiers."""
    tiers = open_tiers(reputation, s)
    if s.event_packs is None:
        events = set(PLAYABLE_EVENTS)
    else:
        events = set(START_EVENTS)
        for name in received_packs(names, s):
            events.update(s.event_packs[name])
    return {n for n in events if tier_of(n) in tiers}


def event_label(number: int) -> str:
    e = EVENTS_BY_NUMBER[number]
    return "#%d %s%s" % (number, e.name, " (%d★)" % e.reputation_required if e.reputation_required else "")


def can_enter(number: int, reputation: float) -> bool:
    """Tournaments need their reputation stars in game ("This Tournament requires 3 reputation stars")."""
    return full_stars(reputation) >= (EVENTS_BY_NUMBER[number].reputation_required or 0)


def map_events(unlocked: Set[int], results: Mapping[int, int], reputation: float,
               pinned: List[int] = ()) -> List[int]:
    """Unlocked, not yet won events in map order: pinned ones, then enterable ones, then the rest (each by
    number). The first MAP_SLOTS of them are opened in game."""
    todo = [n for n in sorted(unlocked) if n not in results]
    pins = [n for n in pinned if n in todo]
    rest = [n for n in todo if n not in pins]
    return pins + [n for n in rest if can_enter(n, reputation)] + [n for n in rest if not can_enter(n, reputation)]


def pin_problem(number: int, names: List[str], reputation: float, results: Mapping[int, int],
                s: Settings) -> Optional[str]:
    """Why an event cannot be pinned to the race map, or None if it can."""
    if number not in PLAYABLE_EVENTS:
        return f"#{number} is not a career event that can be pinned (#1-#110)."
    if number in results:
        return f"#{number} is already done (won, or its checks were already sent)."
    if number not in unlocked_events(list(names), reputation, s):
        if s.event_packs is not None and number not in START_EVENTS and not any(
                number in s.event_packs[name] for name in received_packs(list(names), s)):
            return f"#{number} is not unlocked yet: its Event Pack has not arrived."
        return f"#{number} is in a tier that needs more stars."
    return None


def open_events(reputation: float, results: Mapping[int, int], state: ItemState, s: Settings,
                names: List[str] = (), pinned: List[int] = ()) -> Set[int]:
    special = set()
    if finale_open(results, state, s, reputation):
        special.add(GOAL_EVENT)
    if GOAL_EVENT in results:
        special.add(EPILOGUE_EVENT)  # with the map patch the game no longer unlocks the epilogue by itself
    order = map_events(unlocked_events(list(names), reputation, s), results, reputation, pinned)
    return special | set(order[:MAP_SLOTS - len(special)])


def goal_reached(results: Mapping[int, int], s: Settings) -> bool:
    if s.goal == 0:
        return GOAL_EVENT in results
    return sum(1 for n in results if 1 <= n <= 110) >= s.races_for_goal


# ====================================================================== traps and death link
class TrapManager:
    def __init__(self) -> None:
        self.pending: List[str] = []
        self.active: List[str] = []
        self.saved_installed: Optional[Dict[str, int]] = None

    def queue(self, trap: str) -> None:
        self.pending.append(trap)

    def race_started(self, game: NFSUInterface, run: Callable) -> List[str]:
        """Applies all pending race traps. Returns log messages."""
        msgs = []
        if not self.pending:
            return msgs
        self.active, self.pending = self.pending, []
        installed = run("installed_performance", game.installed_performance)
        reduced = dict(installed) if installed else None
        for trap in self.active:
            if trap == "Nitro Drain Trap":
                run("nitrous_amount", game.drain_nitrous)
            elif trap == "Grip Loss Trap" and reduced is not None:
                reduced["Tires"] = 0
            elif trap == "Power Cut Trap" and reduced is not None:
                reduced["Engine/Exhaust"] = 0
                reduced["Turbo"] = 0
            elif trap == "Style Crash Trap":
                run("style_multiplier", game.set_style_multiplier, 1.0)
            elif trap == "HUD Blackout Trap":
                run("hud_visible", game.set_hud_visible, False)
            msgs.append(f"Trap active this race: {trap}")
        if reduced is not None and reduced != installed:
            self.saved_installed = installed
            run("installed_performance", game.set_installed_performance, reduced)
        return msgs

    def race_ended(self, game: NFSUInterface, run: Callable) -> None:
        if self.saved_installed is not None:
            run("installed_performance", game.set_installed_performance, self.saved_installed)
            self.saved_installed = None
        if "HUD Blackout Trap" in self.active:
            run("hud_visible", game.set_hud_visible, True)
        self.active = []


class DeathLinkTracker:
    def __init__(self, s: Settings) -> None:
        self.s = s
        self.losses = 0

    def should_send(self, result: RaceResult, forced: bool) -> bool:
        """forced: the race was lost because of a received death – never echo that."""
        if forced:
            return False
        died = result.last_place if self.s.death_link_trigger == 1 else not result.won
        if not died:
            return False
        self.losses += 1
        if self.losses > self.s.death_link_amnesty:
            self.losses = 0
            return True
        return False


# ====================================================================== banner
BANNER_SECONDS = 4.0
BANNER_QUEUE_MAX = 20


def banner_item_name(name: str) -> str:
    """Short display name: 'Progressive Turbo' -> 'Turbo Upgrade'."""
    if name.startswith("Progressive "):
        return name[len("Progressive "):] + " Upgrade"
    return name


class BannerQueue:
    """Messages for the in-game "now playing" banner, shown one after another."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.queue: deque = deque()
        self.last_shown = -BANNER_SECONDS

    def received(self, item: str, sender: Optional[str]) -> None:
        self._push(banner_item_name(item), f"from {sender}" if sender else "found it yourself")

    def sent(self, item: str, receiver: str) -> None:
        self._push(f"Sent {item}", f"to {receiver}")

    def _push(self, line1: str, line2: str) -> None:
        if len(self.queue) >= BANNER_QUEUE_MAX:
            # Big backlog (e.g. after reconnecting): replace with one summary line.
            count = len(self.queue) + 1
            self.queue.clear()
            self.queue.append((f"{count} items", "Archipelago"))
            return
        self.queue.append((line1, line2))

    def next_due(self) -> Optional[tuple]:
        if self.queue and self.clock() - self.last_shown >= BANNER_SECONDS:
            self.last_shown = self.clock()
            return self.queue.popleft()
        return None


# ====================================================================== reward popups
POPUP_TITLE = "ARCHIPELAGO!"


def reward_popup_texts(event: int, nodes: List[tuple], describe: Callable[[int], str]) -> List[tuple]:
    """Distributes the Archipelago items of `event` over the game's reward popups.

    The Bank popup ("... added to your Bank.") keeps its Bank line; every other popup (a vanilla unlock that
    Archipelago replaces) gets one found item. Items left over (e.g. events whose rewards have no popup of their
    own) are listed in the Bank popup. Choice events have no checks – their popups stay untouched."""
    ids = list(EVENT_CHECK_IDS.get(event, ()))
    if not ids:
        return []
    lines = [describe(i) for i in ids]
    bank_nodes = [(n, t) for n, t in nodes if "added to your Bank" in t]
    unlock_nodes = [(n, t) for n, t in nodes if (n, t) not in bank_nodes]
    writes = []
    for (node, _), line in zip(unlock_nodes, lines):
        writes.append((node, f"{POPUP_TITLE}^You found:^{line}"))
    rest = lines[len(unlock_nodes):]
    for node, _ in unlock_nodes[len(lines):]:
        writes.append((node, f"{POPUP_TITLE}^Nothing more here."))
    if bank_nodes:
        node, text = bank_nodes[0]
        bank_line = text.replace("Congratulations!", "").strip()
        if rest:
            writes.append((node, f"{POPUP_TITLE} You found:^" + "^".join(rest) + f"^{bank_line}"))
        else:
            writes.append((node, f"Congratulations!^{bank_line}^{POPUP_TITLE} items follow."))
    elif rest and unlock_nodes:
        node, _ = unlock_nodes[-1]
        writes[-1] = (node, f"{POPUP_TITLE}^You found:^" + "^".join(lines[len(unlock_nodes) - 1:]))
    return writes


# ====================================================================== received-item counter
class CounterStore:
    """Where the received-item counter lives when the game's save block is not mapped (see context.py)."""

    def load(self) -> Optional[Tuple[int, int]]:
        """(index, flags), or None while the value is not known yet."""
        raise NotImplementedError

    def save(self, index: int, flags: int) -> None:
        raise NotImplementedError


class MemoryCounterStore(CounterStore):
    """In-memory store, for tests."""

    def __init__(self, index: int = 0, flags: int = 0) -> None:
        self.value: Optional[Tuple[int, int]] = (index, flags)

    def load(self) -> Optional[Tuple[int, int]]:
        return self.value

    def save(self, index: int, flags: int) -> None:
        self.value = (index, flags)


# ====================================================================== tick
@dataclass
class TickResult:
    new_checks: Set[int] = field(default_factory=set)
    goal: bool = False
    send_death: Optional[str] = None
    messages: List[str] = field(default_factory=list)


class GameSync:
    def __init__(self, game: NFSUInterface, settings: Settings,
                 clock: Callable[[], float] = time.monotonic, counter_store: Optional["CounterStore"] = None) -> None:
        self.game = game
        self.s = settings
        self.counter_store = counter_store
        self.counter_ahead_logged = False
        self.won_seen: Optional[Set[int]] = None
        self.popups_written_for: Optional[tuple] = None
        #: location id -> "Turbo Upgrade" / "Hookshot for Bob"; set by the network client (scouted locations).
        self.describe: Callable[[int], str] = lambda location_id: "an Archipelago item"
        self.patch_logged: Optional[bool] = None
        self.shop_patch_logged: Optional[bool] = None
        self.car_patch_logged: Optional[bool] = None
        self.known_difficulty: Dict[int, int] = {}
        self.banners = BannerQueue(clock)
        self.traps = TrapManager()
        self.death = DeathLinkTracker(settings)
        self.missing: Set[str] = set()
        self.deducted: Set[tuple] = set()
        self.was_racing: Optional[bool] = None
        self.race_seen = False
        self.result_handled = False
        self.death_pending = False
        self.death_forced = False
        self.death_sent = False   # a death was sent for the current race attempt
        self.blown_handled = False
        self.heat_switched_on = False
        self.heat_blow_seen = False   # the engine read "blown" after we switched the heat check on
        self.reputation: Optional[float] = None
        self.results: Dict[int, int] = {}
        self.pinned: List[int] = []                  # /nfsu pin: events that get a race map slot first
        self.packs_seen: Optional[Set[str]] = None

    # Calls `fn`; a NotMapped address disables the feature for this tick and is reported once.
    def run(self, feature: str, fn: Callable, *args):
        try:
            return fn(*args)
        except NotMapped as e:
            self._report_missing(feature, e)
            return None

    def _report_missing(self, feature: str, e: NotMapped) -> None:
        if str(e) not in self.missing:
            self.missing.add(str(e))
            logger.warning("NFSU: '%s' is not mapped yet (data/addresses.py) – %s skipped.", e, feature)

    def receive_death(self) -> None:
        self.death_pending = True

    def tick(self, received: List[str], checked: Set[int]) -> TickResult:
        out = TickResult()
        s, game = self.s, self.game

        # 0. a win shows up first as reward popups on the results screen: send its checks right away and put the
        #    Archipelago items into the popups before the player clicks through.
        popup_win = self._handle_reward_popups()
        if popup_win is not None:
            self.results = merge_results(self.results, {popup_win: 0})

        # 1. won events -> checks (+ remove vanilla Bank if disabled)
        raw = self.run("event results", game.event_results)
        in_memory = None if raw is None else self._resolve_difficulties(raw)
        results = None
        if in_memory is not None:
            # Game memory + server checks + what this session already saw.
            results = merge_results(self.results, results_from_checks(checked), in_memory)
            self.results = results
            earned = checks_for_results(results)
            out.new_checks = earned - checked
            if not s.vanilla_bank_rewards:
                for n, won in in_memory.items():
                    ids = EVENT_CHECK_IDS.get(n)
                    if ids and ids[0] not in checked and (n, won) not in self.deducted:
                        bank = EVENTS_BY_NUMBER[n].bank[won] or 0
                        if self.run("bank", game.add_bank, -bank) is not None:
                            self.deducted.add((n, won))
            if goal_reached(results, s):
                out.goal = True
        if popup_win is not None:
            out.new_checks |= event_check_ids(popup_win) - checked

        # 2. shop unlocks and event availability
        state = item_state(received, s)
        if results is not None:
            self._sync_part_unlocks(received, results)
        if state.cars is not None:
            self._sync_car_unlocks(state.cars)
        self.reputation = received_reputation(received)
        out.messages += self._announce_packs(received)
        if results is not None and self._availability_patch_active():
            try:
                # Won events stay won (no checks per difficulty -> nothing to re-open).
                game.set_events_available(open_events(self.reputation, results, state, s, received, self.pinned),
                                          in_memory, ())
            except NotMapped as e:
                self._report_missing("event availability", e)

        # 3. one-time items
        out.messages += self._apply_consumables(received)

        # 4. races: traps and death link
        racing = self.run("race state", game.in_race)
        if racing is not None:
            # was_racing is None on the first tick: a race (or results screen) already loaded when the client
            # connects is not counted as a start.
            if racing and self.was_racing is False:
                self.race_seen = True
                self.result_handled = False
                self.death_forced = False
                self.death_sent = False
                out.messages += self.traps.race_started(game, self.run)
            if racing and self.death_pending:
                self.death_pending = False
                if self.result_handled or self.blown_handled:
                    out.messages.append("Death Link received after the race ended – ignored.")
                else:
                    out.messages.append("Death Link: " + self._apply_death())
                    self.death_forced = True
            if not racing and self.was_racing:
                self.traps.race_ended(game, self.run)
            self.was_racing = racing
            # The results popups exist while the race is still loaded (race_active stays set until the map).
            # Once the popups are gone while the race is still loaded (restart from the results screen), the next
            # results screen counts again.
            if self.race_seen:
                result = self.run("race result", game.race_result)
                if result is None:
                    if racing and self.result_handled:   # restarted from the results screen: a new attempt
                        self.result_handled = False
                        self.blown_handled = False
                        self.death_forced = False
                        self.death_sent = False
                elif not self.result_handled:
                    self.result_handled = True
                    out.messages.append("Race result: %s, position %s of %s" % (
                        "won" if result.won else "lost", result.position or "?", result.racers or "?"))
                    # One death per attempt: none after a blown engine already sent one or a received death.
                    if (s.death_link and not self.death_sent and not self.blown_handled
                            and self.death.should_send(result, self.death_forced)):
                        out.send_death = "lost a street race" if not result.last_place else "finished dead last"
                        self.death_sent = True
            # Drag: a blown engine drops the player (pause menu or results). Only checked before the result is
            # known: on the results screen the heat object is stale and can read as "blown" after a win.
            if self.race_seen and racing and not self.result_handled:
                blown = self.run("engine state", game.engine_blown)
                if blown and not self.blown_handled:
                    self.blown_handled = True
                    out.messages.append("Race result: lost, blown engine")
                    if (s.death_link and not self.death_sent
                            and self.death.should_send(RaceResult(False), self.death_forced)):
                        out.send_death = "blew the engine"
                        self.death_sent = True
                elif blown is False and self.blown_handled:
                    # Race restarted from the pause menu: an own blowout counts again. death_forced stays set
                    # until the race is left or restarted from the results screen, so a received death is never
                    # echoed back (seen in game: the flag read 1, 0, 1 after a received death).
                    self.blown_handled = False
                    self.death_sent = False
            elif not racing:
                self.blown_handled = False
            # A received death switched the engine heat check on outside drag: off again once that attempt is over
            # (results popups shown, engine no longer blown = restarted, or back on the map). Independent of
            # race_seen: in one test the client connected during a drift, the flag stayed 1 and the restarted
            # drift ran as a drag race.
            if self.heat_switched_on:
                over = not racing
                if racing:
                    if self.run("race result", game.race_result) is not None:
                        over = True
                    else:
                        blown = self.run("engine state", game.engine_blown)
                        if blown:
                            self.heat_blow_seen = True
                        elif blown is False and self.heat_blow_seen:
                            over = True
                if over:
                    self.heat_switched_on = False
                    self.heat_blow_seen = False
                    self.run("engine heat", game.set_engine_heat_enabled, False)
        if self.death_pending and racing is False:
            self.death_pending = False
            out.messages.append("Death Link received outside a race – ignored.")

        # 5. "now playing" banner for received/sent items
        banner = self.banners.next_due()
        if banner is not None:
            self.run("item banner", game.show_banner, *banner)
        return out

    def _handle_reward_popups(self) -> Optional[int]:
        """Returns the event number while its win popups are on screen (once per results screen it also rewrites
        the popup texts). None when there are no reward popups."""
        found = self.run("reward popups", self.game.reward_popups)
        if not found:
            self.popups_written_for = None
            return None
        owner, nodes = found
        if not any(text.startswith("Congratulations") for _, text in nodes):
            return None
        event = self.run("active event", self.game.active_event)
        if event is None:
            return None
        if self.popups_written_for != (owner, event):
            self.popups_written_for = (owner, event)
            for node, text in reward_popup_texts(event, nodes, self.describe):
                self.game.write_popup_text(node, text)
        return event

    def _sync_part_unlocks(self, received: List[str], results: Mapping[int, int]) -> None:
        """Writes the shop table, then makes sure the shop patch is active (table first: no window in which the
        patched shop sees an empty table)."""
        try:
            self.game.write_part_unlocks(part_unlocks(received, results, self.s))
            active = self.game.apply_part_unlock_patch()
        except NotMapped as e:
            self._report_missing("shop unlocks", e)
            return
        if active != self.shop_patch_logged:
            self.shop_patch_logged = active
            if active:
                logger.info("NFSU: shop patch active – parts come from Archipelago items.")
            else:
                logger.warning("NFSU: unexpected code at the shop patch address (other game version or patch) – "
                               "the shop unlocks parts by race wins.")

    def _sync_car_unlocks(self, cars: Dict[str, bool]) -> None:
        """Writes the car table, then makes sure the car patch is active (only with cars_as_items)."""
        try:
            self.game.write_car_unlocks(cars)
            active = self.game.apply_car_unlock_patch()
        except NotMapped as e:
            self._report_missing("car unlocks", e)
            return
        if active != self.car_patch_logged:
            self.car_patch_logged = active
            if active:
                logger.info("NFSU: car patch active – cars come from Archipelago items.")
            else:
                logger.warning("NFSU: unexpected code or car list at the car patch address (other game version?) – "
                               "cars unlock by race wins.")

    def _availability_patch_active(self) -> bool:
        """Applies the map patch if needed. Without it, the game would undo every availability write when the
        Race Map is built (and jump back to the first unfinished set), so nothing is written then."""
        try:
            active = self.game.apply_availability_patch()
        except NotMapped as e:
            self._report_missing("event availability", e)
            return False
        if active != self.patch_logged:
            self.patch_logged = active
            if active:
                logger.info("NFSU: map patch active – the client now decides which events are available.")
            else:
                logger.warning("NFSU: unexpected code at the map patch address (other game version or patch) – "
                               "event availability is left to the game.")
        return active

    def _resolve_difficulties(self, raw: Mapping[int, Optional[int]]) -> Dict[int, int]:
        """Fills in the difficulty for games that only store "won" per event (NFSU NTSC-U).

        An event that switches to "won" while the client watches gets the difficulty of the last race.
        Wins that were already there when the client started (or that happened while it was closed) count
        as Easy – the higher checks stay open and the event is re-opened for them."""
        out: Dict[int, int] = {}
        if self.won_seen is None:
            # First look after (re)starting: the most recently won event still has its difficulty in memory.
            last = self.run("last won event", self.game.last_won_event)
            newly = {last} & set(raw) if last is not None else set()
        else:
            newly = set(raw) - self.won_seen
        last_diff: Optional[int] = None
        for n, d in raw.items():
            if d is None:
                if n in newly:
                    if last_diff is None:
                        last_diff = self.run("last race difficulty", self.game.last_race_difficulty) or 0
                    d = last_diff
                else:
                    d = self.known_difficulty.get(n, 0)
            self.known_difficulty[n] = max(self.known_difficulty.get(n, 0), d)
            out[n] = d
        self.won_seen = set(raw)
        return out

    def _announce_packs(self, received: List[str]) -> List[str]:
        """One line per newly received Event Pack (a summary on the first tick after connecting)."""
        packs = set(received_packs(received, self.s))
        if self.packs_seen is None:
            self.packs_seen = packs
            if not self.s.event_packs:
                return []
            return ["Event Packs: %d of %d received, %d events unlocked (/nfsu events lists them)." % (
                len(packs), len(self.s.event_packs), len(unlocked_events(received, 99.0, self.s)))]
        new = [name for name in self.s.event_packs or () if name in packs - self.packs_seen]
        self.packs_seen = packs
        return ["%s: %s" % (name, ", ".join(event_label(n) for n in self.s.event_packs[name])) for name in new]

    def _apply_death(self) -> str:
        """Applies a received death; returns what happened (for the log)."""
        if self.s.death_link_effect == 0:
            # "Blown Engine": the racer drops out (drag: pause menu; other races: results screen, last place).
            switched_on = self.run("death link", self.game.blow_engine)
            if switched_on is not None:
                self.heat_switched_on = self.heat_switched_on or switched_on
                return "engine blown."
            try:
                self.game.force_race_loss()
                return "race failed."
            except NotMapped:  # no player car found: fall back to the nitro effect
                self.run("death link", self.game.drain_nitrous)
                return "nitrous drained."
        self.run("death link", self.game.drain_nitrous)
        self.run("death link", self.game.set_speed_scale, SLOWDOWN_SCALE)
        return "nitrous drained, car slowed down."

    def _counter(self):
        """Returns ((index, flags), save_function) for the received-item counter, or (None, None).

        Preferred: 8 bytes in the game's save data (follows the save file). Fallback: Archipelago data
        storage on the server (works now, but loading an older save/savestate loses Bank already paid out)."""
        try:
            return self.game.read_save_block(), self.game.write_save_block
        except NotMapped:
            pass
        if self.counter_store is None:
            if "ap_save_block" not in self.missing:
                self.missing.add("ap_save_block")
                logger.warning("NFSU: no place to store the received-item counter – Bank items and traps skipped.")
            return None, None
        block = self.counter_store.load()
        return (block, self.counter_store.save) if block is not None else (None, None)

    def _apply_consumables(self, received: List[str]) -> List[str]:
        if self.run("Bank items", self.game.bank) is None:
            return []
        block, save = self._counter()
        if block is None:
            return []  # without a persistent counter we would apply Bank twice after a restart
        index, flags = block
        if index > len(received):
            # Counter is ahead of the item list: items not synced yet after connecting, or a save from
            # another seed. Never go backwards – that would pay out everything again.
            if not self.counter_ahead_logged:
                self.counter_ahead_logged = True
                logger.info("NFSU: waiting for received items (counter %d > %d items).", index, len(received))
            return []
        msgs = []
        start_index = index
        if not flags & FLAG_STARTING_BANK:
            if self.s.starting_bank:
                self.game.add_bank(self.s.starting_bank)
                msgs.append(f"Starting Bank: +{self.s.starting_bank}")
            flags |= FLAG_STARTING_BANK
        for name in received[index:]:
            if name in BANK_ITEMS:
                amount = BANK_ITEMS[name] * self.s.bank_multiplier // 100
                self.game.add_bank(amount)
                msgs.append(f"{name}: +{amount} Bank")
            elif name == "Bank Tax Trap":
                tax = (self.game.bank() * BANK_TAX_PERCENT) // 100
                self.game.add_bank(-tax)
                msgs.append(f"Bank Tax Trap: -{tax} Bank")
            elif name == "Pink Paint Trap":
                self.run("pink paint", self.game.paint_pink)
                msgs.append("Pink Paint Trap!")
            elif name in RACE_TRAPS:
                self.traps.queue(name)
                msgs.append(f"{name} queued for your next race")
        if len(received) != start_index or not block[1] & FLAG_STARTING_BANK:
            save(len(received), flags)
        return msgs

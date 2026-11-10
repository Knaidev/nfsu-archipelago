"""Archipelago client for Need for Speed: Underground (PS2) via PCSX2/PINE."""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, handle_url_arg, \
    logger as common_logger, server_loop
from NetUtils import ClientStatus

from ..data.events import TIME_TRIALS
from ..items import GAME_NAME, ITEM_NAME_TO_ID
from .interface import NFSUInterface, WrongGame
from ..logic import full_stars
from .sync import (MAP_SLOTS, CounterStore, GameSync, Settings, banner_item_name, can_enter, event_label, pin_problem,
                   item_state, map_events, open_tiers, received_packs, received_reputation, time_trial_wins,
                   unlocked_events)

logger = logging.getLogger("NFSU")
ITEM_ID_TO_NAME = {v: k for k, v in ITEM_NAME_TO_ID.items()}
TICK_SECONDS = 0.1
RECONNECT_SECONDS = 3.0


class NFSUCommandProcessor(ClientCommandProcessor):
    def _cmd_pcsx2(self) -> bool:
        """Show the PCSX2 connection and reconnect if needed."""
        ctx: NFSUContext = self.ctx  # type: ignore
        ctx.request_pcsx2_reconnect = True
        self.output(f"PCSX2: {'connected' if ctx.game_interface.ready else 'not connected'} "
                    f"(slot {ctx.game_interface.pine.slot}). Reconnecting…")
        return True

    def _cmd_nfsu(self, *args: str) -> bool:
        """Status (stars, tiers, parts). /nfsu events: unlocked events and the 12 on the race map.
        /nfsu pin <nr> / /nfsu unpin <nr>: give an event a race map slot first (the map holds 12)."""
        ctx: NFSUContext = self.ctx  # type: ignore
        sync = ctx.sync
        if sync is None:
            self.output("Not connected to a slot yet.")
            return True
        if args and args[0].lower() == "events":
            return self._events(sync)
        if args and args[0].lower() in ("pin", "unpin"):
            return self._pin(sync, args[0].lower() == "pin", args[1:])
        rep = received_reputation(ctx.received_names())
        self.output(f"Stars from received parts: {rep} (full stars: {full_stars(rep)})")
        self.output(f"Open tiers: {sorted(open_tiers(rep, sync.s))}")
        self.output(f"Time trials won: {time_trial_wins(sync.results)}/{len(TIME_TRIALS)} "
                    f"(needed: {sync.s.time_trials_required})")
        state = item_state(ctx.received_names(), sync.s)
        self.output("Performance levels: " + ", ".join(f"{k} {v}" for k, v in state.performance.items()))
        self.output("Visual levels: " + ", ".join(f"{k} {v}" for k, v in state.visual.items()))
        if state.cars is not None:
            self.output("Cars: " + ", ".join(k for k, v in state.cars.items() if v))
        self.output("Uniques: " + (", ".join(str(k) for k, v in state.uniques.items() if v) or "none"))
        self.output(f"Finale item: {'yes' if state.has_finale else 'no'}, "
                    f"Samantha's Big Tease: {'yes' if state.has_key else 'no'}")
        if sync.missing:
            self.output("Not mapped yet: " + ", ".join(sorted(sync.missing)))
        return True

    def _events(self, sync: GameSync) -> bool:
        ctx: NFSUContext = self.ctx  # type: ignore
        names = ctx.received_names()
        rep = received_reputation(names)
        if sync.s.event_packs:
            got = received_packs(names, sync.s)
            self.output(f"Event Packs: {len(got)} of {len(sync.s.event_packs)}")
            for name in got:
                self.output(f"  {name}: " + ", ".join(event_label(n) for n in sync.s.event_packs[name]))
        order = map_events(unlocked_events(names, rep, sync.s), sync.results, rep, sync.pinned)
        self.output(f"Not yet won: {len(order)}; on the race map (max {MAP_SLOTS}):")
        for i, n in enumerate(order):
            tag = "map" if i < MAP_SLOTS else "   "
            note = " pinned" if n in sync.pinned else ("" if can_enter(n, rep) else " needs more stars")
            self.output(f"  {tag} {event_label(n)}{note}")
        return True

    def _pin(self, sync: GameSync, pin: bool, args) -> bool:
        try:
            number = int(str(args[0]).lstrip("#"))
        except (IndexError, ValueError):
            self.output("Usage: /nfsu pin <event number>  or  /nfsu unpin <event number>")
            return False
        if pin:
            ctx: NFSUContext = self.ctx  # type: ignore
            names = ctx.received_names()
            problem = pin_problem(number, names, received_reputation(names), sync.results, sync.s)
            if problem:
                self.output(f"Not pinned: {problem}")
                return False
        if number in sync.pinned:
            sync.pinned.remove(number)
        if pin:
            sync.pinned.insert(0, number)
        self.output(f"#{number} {'pinned' if pin else 'unpinned'}. Pinned: "
                    + (", ".join(f"#{n}" for n in sync.pinned) or "none")
                    + ". Reopen the race map to see the change.")
        return True

    def _cmd_deathlink(self, state: str = "") -> bool:
        """Switch Death Link on or off for this session (overrides the slot option): /deathlink on|off"""
        ctx: NFSUContext = self.ctx  # type: ignore
        if state.lower() not in ("on", "off"):
            current = ctx.sync.s.death_link if ctx.sync else ctx.death_link_override
            self.output(f"Death Link is {'on' if current else 'off'}. Usage: /deathlink on|off")
            return False
        ctx.set_death_link(state.lower() == "on")
        self.output(f"Death Link {state.lower()}.")
        return True


class ServerCounterStore(CounterStore):
    """Received-item counter in Archipelago's data storage (one key per team/slot).

    Read from the worker thread; written via the asyncio loop. After the first load the local copy is
    authoritative, so a slow SetReply can never make the client pay out the same item twice."""

    def __init__(self, ctx: "NFSUContext", loop: asyncio.AbstractEventLoop) -> None:
        self.ctx = ctx
        self.loop = loop
        self.key = f"NFSU_received_counter_{ctx.team}_{ctx.slot}"
        self.local: Optional[tuple] = None
        ctx.set_notify(self.key)

    def load(self) -> Optional[tuple]:
        if self.local is None:
            if self.key not in self.ctx.stored_data:
                return None  # Get not answered yet
            value = self.ctx.stored_data[self.key] or {}
            self.local = (int(value.get("index", 0)), int(value.get("flags", 0)))
        return self.local

    def save(self, index: int, flags: int) -> None:
        self.local = (index, flags)
        msg = {"cmd": "Set", "key": self.key, "default": {}, "want_reply": True,
               "operations": [{"operation": "replace", "value": {"index": index, "flags": flags}}]}
        asyncio.run_coroutine_threadsafe(self.ctx.send_msgs([msg]), self.loop)


class NFSUContext(CommonContext):
    game = GAME_NAME
    items_handling = 0b111  # all items, including own and starting inventory
    command_processor = NFSUCommandProcessor

    def __init__(self, server_address: Optional[str] = None, password: Optional[str] = None) -> None:
        super().__init__(server_address, password)
        self.game_interface = NFSUInterface()
        self.sync: Optional[GameSync] = None
        self.request_pcsx2_reconnect = False
        #: /deathlink or --death_link: overrides the slot's Death Link option (None = use the slot option).
        self.death_link_override: Optional[bool] = None
        self.goal_sent = False
        self.last_wrong_game: Optional[str] = None
        self.waiting_logged = False

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: Dict[str, Any]) -> None:
        if cmd == "Connected":
            try:
                settings = Settings.from_slot_data(args.get("slot_data") or {})
            except (ValueError, TypeError, AttributeError):
                logger.error("NFSU: the seed's slot data cannot be read. Was it generated with another apworld "
                             "version? The game is not synchronised.")
                self.sync = None
                return
            if self.death_link_override is not None:
                settings.death_link = self.death_link_override
            store = ServerCounterStore(self, asyncio.get_running_loop())
            self.sync = GameSync(self.game_interface, settings, counter_store=store)
            self.sync.describe = self.describe_location
            self.goal_sent = False
            from Utils import async_start
            async_start(self.update_death_link(settings.death_link))
            # Learn what lies on every own check, for the in-game reward popups (no hints are created).
            own = sorted(set(args.get("missing_locations", [])) | set(args.get("checked_locations", [])))
            async_start(self.send_msgs([{"cmd": "LocationScouts", "locations": own, "create_as_hint": 0}]))

    def on_print_json(self, args: Dict[str, Any]) -> None:
        super().on_print_json(args)
        if args.get("type") != "ItemSend" or self.sync is None or self.slot is None:
            return
        item = args["item"]
        receiving = args["receiving"]
        try:
            if receiving == self.slot:
                name = self.item_names.lookup_in_game(item.item)
                sender = None if item.player == self.slot else self.player_names[item.player]
                self.sync.banners.received(name, sender)
            elif item.player == self.slot:
                name = self.item_names.lookup_in_slot(item.item, receiving)
                self.sync.banners.sent(name, self.player_names[receiving])
        except (KeyError, AttributeError):
            pass

    def set_death_link(self, enabled: bool) -> None:
        self.death_link_override = enabled
        if self.sync is not None:
            self.sync.s.death_link = enabled
        if self.server:
            from Utils import async_start
            async_start(self.update_death_link(enabled))

    def on_deathlink(self, data: Dict[str, Any]) -> None:
        super().on_deathlink(data)
        if self.sync is not None:
            self.sync.receive_death()

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        self.sync = None
        await super().disconnect(allow_autoreconnect)

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago NFSU Client"
        return ui

    def describe_location(self, location_id: int) -> str:
        """Short text for a reward popup: the item on that check and, if it is not ours, who gets it."""
        info = self.locations_info.get(location_id)
        if info is None or self.slot is None:
            return "an Archipelago item"
        try:
            name = self.item_names.lookup_in_slot(info.item, info.player)
            if info.player == self.slot:
                return banner_item_name(name)
            return f"{name} for {self.player_names[info.player]}"
        except (KeyError, AttributeError):
            return "an Archipelago item"

    def received_names(self) -> List[str]:
        return [ITEM_ID_TO_NAME.get(item.item, "") for item in self.items_received]


async def pcsx2_loop(ctx: NFSUContext) -> None:
    last_attempt = 0.0
    while not ctx.exit_event.is_set():
        game = ctx.game_interface
        try:
            if ctx.request_pcsx2_reconnect:
                ctx.request_pcsx2_reconnect = False
                game.disconnect()
            if not game.ready:
                if time.monotonic() - last_attempt >= RECONNECT_SECONDS:
                    last_attempt = time.monotonic()
                    if await asyncio.to_thread(game.connect):
                        logger.info("Connected to PCSX2 (%s).", game.serial)
                        ctx.last_wrong_game = None
                        ctx.waiting_logged = False
                    elif not ctx.waiting_logged:
                        ctx.waiting_logged = True
                        logger.info("Waiting for PCSX2 with PINE enabled (slot %d) and the game running…",
                                    game.pine.slot)
                await asyncio.sleep(0.5)
                continue
            if ctx.sync is None or not ctx.server or ctx.slot is None:
                await asyncio.sleep(1.0)
                continue

            result = await asyncio.to_thread(ctx.sync.tick, ctx.received_names(), set(ctx.checked_locations))
            for msg in result.messages:
                logger.info(msg)
            if result.new_checks:
                await ctx.check_locations(result.new_checks)
            if result.send_death and ctx.sync.s.death_link:
                await ctx.send_death(f"{ctx.player_names[ctx.slot]} {result.send_death}")
            if result.goal and not ctx.goal_sent:
                ctx.goal_sent = True
                ctx.finished_game = True
                await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                logger.info("Goal complete!")
            await asyncio.sleep(TICK_SECONDS)
        except WrongGame as e:
            if str(e) != ctx.last_wrong_game:
                ctx.last_wrong_game = str(e)
                logger.warning(str(e))
            game.disconnect()
            await asyncio.sleep(RECONNECT_SECONDS)
        except (ConnectionError, TimeoutError) as e:
            logger.warning("PCSX2 connection lost: %s – retrying.", e)
            game.disconnect()
            await asyncio.sleep(RECONNECT_SECONDS)
        except Exception:  # keep the client alive, but show the bug
            common_logger.exception("NFSU client error")
            await asyncio.sleep(RECONNECT_SECONDS)


def launch(*launch_args: str) -> None:
    import colorama
    import Utils

    Utils.init_logging("NFSUClient", exception_logger="Client")

    async def main(args) -> None:
        ctx = NFSUContext(args.connect, args.password)
        if args.name:
            ctx.auth = args.name
        if args.death_link:
            ctx.death_link_override = args.death_link == "on"
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled and not getattr(args, "nogui", False):
            ctx.run_gui()
        ctx.run_cli()
        pcsx2_task = asyncio.create_task(pcsx2_loop(ctx), name="PCSX2 sync")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
        await pcsx2_task
        # Without the client the game should unlock events, parts and cars by its own rules again.
        for remove, what in ((ctx.game_interface.remove_availability_patch, "Map patch"),
                             (ctx.game_interface.remove_part_unlock_patch, "Shop patch"),
                             (ctx.game_interface.remove_car_unlock_patch, "Car patch"),
                             (ctx.game_interface.remove_bank_reward_patch, "Race Bank patch")):
            try:
                await asyncio.to_thread(remove)
                logger.info("%s removed.", what)
            except Exception:  # PCSX2 already closed, address not mapped, …
                pass
        ctx.game_interface.disconnect()

    parser = get_base_parser(description="Need for Speed: Underground (PS2) Archipelago client")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--death_link", choices=("on", "off"), default=None,
                        help="Override the slot's Death Link option (same as /deathlink).")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = handle_url_arg(parser.parse_args(launch_args), parser=parser)
    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()

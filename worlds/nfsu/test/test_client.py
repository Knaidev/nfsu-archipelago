"""Client tests without an emulator: a fake PINE server holds PS2 memory, a test address map is injected,
and the real Pine -> NFSUInterface -> GameSync stack runs against it."""
import socket
import struct
import threading
import unittest
from typing import Optional

from ..client import interface as interface_mod
from ..client.interface import NFSUInterface
from ..client.pine import Pine
from ..client.sync import GameSync, MemoryCounterStore, Settings
from ..locations import EVENT_CHECK_IDS


def C(n: int) -> set:
    """Check ids of event n: its vanilla rewards, or Victory."""
    return set(EVENT_CHECK_IDS[n])
from ..data import addresses as addresses_mod
from ..data.addresses import AddressMap
from ..data.parts import PERFORMANCE, VISUAL

TEST_SERIAL = "TEST-00001"
MAP = AddressMap(
    game_mode=0x100, race_active=0x104, race_info_pointer=0x110, race_position_offset=0x10, career_set=0x10A,
    event_table=0x1000, event_stride=4, event_status_offset=0, event_difficulty_offset=1,
    event_status_locked=0, event_status_available=1, event_status_won=2,
    bank=0x200,
    installed_performance=0x380, nitrous_amount=0x400, player_speed_scale=0x404, hud_visible=0x408,
    style_multiplier=0x40C, paint_color=0x410, force_race_loss=0x414, ap_save_block=0x500,
    engine_heat_enabled=0x418, racer_sim_offset=0x34, sim_engine_heat_offset=0x48, engine_blown_offset=0x94,
    heap_pointer_min=0x1000,
    banner_line1=0x600, banner_line2=0x620, banner_max_chars=20, banner_trigger=0x640, banner_trigger_value=90,
    availability_patch=((0x800, 0x27BDFFC0, 0x03E00008), (0x804, 0xFFB20020, 0x00000000)),
    reward_popup_owner=0x900, reward_popup_tag=0x2CCB70AA, event_status_active=3,
    part_unlock_patch=((0x840, 0x0C0C5C18, 0x00131080), (0x844, 0x10000013, 0x10000013),
                       (0x848, 0x2C420001, 0x00000000)),
    part_unlock_table=0x3000,
    car_unlock_patch=((0x860, 0x27BDFFC0, 0x3C03004C), (0x864, 0x24020001, 0x24020001),
                      (0x868, 0x0200282D, 0x8042CAC7)),
    car_hash_list=0x7200, car_unlock_table=0x7100,
)
PERF_INDEX = {c.name: i for i, c in enumerate(PERFORMANCE)}
SHOP_ORIGINAL = ((0x840, 0x0C0C5C18), (0x844, 0x10000013), (0x848, 0x2C420001))
CAR_ORIGINAL = ((0x860, 0x27BDFFC0), (0x864, 0x24020001), (0x868, 0x0200282D))


def shop(server, category: str, level: int) -> int:
    """Byte of the shop table the patched game reads for (category, level)."""
    from ..data.addresses import PART_CATEGORY_ID
    return server.u8(MAP.part_unlock_table + PART_CATEGORY_ID[category] * 4 + level - 1)


def car(server, name: str) -> int:
    """Byte of the car table the patched game reads for `name` (data/cars.py)."""
    from ..data.addresses import CAR_HASH_ORDER
    index = [n for _, n in CAR_HASH_ORDER].index(name)
    return server.u8(MAP.car_unlock_table + index)


VIS_INDEX = {c.name: i for i, c in enumerate(VISUAL)}


class FakePineServer:
    """Minimal PCSX2 PINE server (TCP) with 64 KiB of memory."""

    def __init__(self, serial: str = TEST_SERIAL) -> None:
        self.mem = bytearray(0x10000)
        self.serial = serial
        self.requests = 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.sock.close()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                while True:
                    head = self._recv(conn, 4)
                    if head is None:
                        break
                    size = struct.unpack("<I", head)[0]
                    body = self._recv(conn, size - 4)
                    if body is None:
                        break
                    self.requests += 1
                    reply = self._handle(body)
                    conn.sendall(struct.pack("<I", len(reply) + 4) + reply)

    @staticmethod
    def _recv(conn, n) -> Optional[bytes]:
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _handle(self, body: bytes) -> bytes:
        out = b"\x00"
        pos = 0
        while pos < len(body):
            op = body[pos]
            pos += 1
            if op <= 3:
                size = 1 << op
                addr = struct.unpack_from("<I", body, pos)[0]
                pos += 4
                out += bytes(self.mem[addr:addr + size])
            elif op <= 7:
                size = 1 << (op - 4)
                addr = struct.unpack_from("<I", body, pos)[0]
                pos += 4
                self.mem[addr:addr + size] = body[pos:pos + size]
                pos += size
            elif op in (0xB, 0xC):
                text = (self.serial if op == 0xC else "NEED FOR SPEED UNDERGROUND").encode() + b"\x00"
                out += struct.pack("<I", len(text)) + text
            elif op == 0xF:
                out += struct.pack("<I", 0)
            else:
                return b"\xff"
        return out

    # helpers
    def u8(self, addr: int, value: Optional[int] = None) -> int:
        if value is not None:
            self.mem[addr] = value
        return self.mem[addr]

    def u32(self, addr: int, value: Optional[int] = None) -> int:
        if value is not None:
            struct.pack_into("<I", self.mem, addr, value)
        return struct.unpack_from("<I", self.mem, addr)[0]

    def f32(self, addr: int, value: Optional[float] = None) -> float:
        if value is not None:
            struct.pack_into("<f", self.mem, addr, value)
        return struct.unpack_from("<f", self.mem, addr)[0]

    def event(self, n: int, status: Optional[int] = None, diff: Optional[int] = None):
        base = MAP.event_table + n * MAP.event_stride
        if status is not None:
            self.mem[base] = status
        if diff is not None:
            self.mem[base + 1] = diff
        return self.mem[base], self.mem[base + 1]


class ClientTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakePineServer()
        self.server.u32(0x800, 0x27BDFFC0)   # original game code at the map patch address
        self.server.u32(0x804, 0xFFB20020)
        for address, word in SHOP_ORIGINAL + CAR_ORIGINAL:  # original game code at the patch addresses
            self.server.u32(address, word)
        from ..data.addresses import CAR_HASH_ORDER, string_hash
        for i, (internal, _) in enumerate(CAR_HASH_ORDER):  # the game's car hash list
            self.server.u32(MAP.car_hash_list + 4 * i, string_hash(internal))
        self._old_addresses = dict(addresses_mod.ADDRESSES)
        interface_mod.ADDRESSES[TEST_SERIAL] = MAP
        self.game = NFSUInterface(Pine(self.server.port, timeout=2.0))
        self.assertTrue(self.game.connect())

    def tearDown(self) -> None:
        self.game.disconnect()
        self.server.close()
        interface_mod.ADDRESSES.clear()
        interface_mod.ADDRESSES.update(self._old_addresses)

    def make_sync(self, **settings) -> GameSync:
        return GameSync(self.game, Settings(**settings))


class TestPine(ClientTestBase):
    def test_read_write_sizes(self):
        p = self.game.pine
        p.write8(0x10, 0xAB)
        p.write16(0x20, 0xBEEF)
        p.write32(0x30, 0xDEADBEEF)
        p.write64(0x40, 0x0123456789ABCDEF)
        p.write_float(0x50, 2.5)
        self.assertEqual(p.read8(0x10), 0xAB)
        self.assertEqual(p.read16(0x20), 0xBEEF)
        self.assertEqual(p.read32(0x30), 0xDEADBEEF)
        self.assertEqual(p.read64(0x40), 0x0123456789ABCDEF)
        self.assertEqual(p.read_float(0x50), 2.5)

    def test_batch_and_bytes(self):
        p = self.game.pine
        self.server.mem[0x2000:0x2000 + 100] = bytes(range(100))
        before = self.server.requests
        self.assertEqual(p.read_bytes(0x2000, 100), bytes(range(100)))
        self.assertEqual(self.server.requests - before, 1, "read_bytes should use one batched message")
        p.batch_write([(0x3000, 1, 7), (0x3004, 4, 123456)])
        self.assertEqual(p.batch_read([(0x3000, 1), (0x3004, 4)]), [7, 123456])

    def test_game_id_and_wrong_game(self):
        self.assertEqual(self.game.serial, TEST_SERIAL)
        other = FakePineServer(serial="SLES-99999")
        try:
            g = NFSUInterface(Pine(other.port))
            with self.assertRaises(interface_mod.WrongGame):
                g.connect()
            g.disconnect()
        finally:
            other.close()

    def test_lost_connection_raises_connection_error(self):
        p = Pine(1, timeout=0.5)  # nothing listens on port 1
        with self.assertRaises(ConnectionError):
            p.read8(0)


class TestChecksAndEvents(ClientTestBase):
    def test_win_sends_all_rewards_and_stays_won(self):
        sync = self.make_sync()
        self.server.event(4, status=2, diff=1)  # #4: car + course = two checks, any difficulty
        result = sync.tick([], set())
        self.assertEqual(result.new_checks, C(4))
        self.assertEqual(len(C(4)), 2)
        sync.tick([], result.new_checks)
        self.assertEqual(self.server.event(4)[0], MAP.event_status_won, "won events are never re-opened")

    def test_already_checked_not_resent(self):
        sync = self.make_sync()
        self.server.event(3, status=2, diff=0)
        self.assertEqual(sync.tick([], C(3)).new_checks, set())

    def test_choice_events_open_but_send_nothing(self):
        sync = self.make_sync()
        self.server.event(7, status=2, diff=2)                 # TJ's Time Trial won on Hard
        self.assertEqual(sync.tick([], set()).new_checks, set())
        self.assertEqual(self.server.event(7)[0], MAP.event_status_won, "not re-opened, no checks")
        self.assertEqual(self.server.event(15)[0], MAP.event_status_available, "time trials are playable")

    def test_star_gates_open_tiers(self):
        sync = self.make_sync()
        sync.tick([], set())
        self.assertEqual(self.server.event(10)[0], MAP.event_status_available)   # tier 1
        self.assertEqual(self.server.event(31)[0], MAP.event_status_locked, "no stars yet")
        # Level 3 front and rear bumper (two items each) = 2.2 stars -> 2 full stars -> tier 2, but not tier 3.
        parts = ["Progressive Front Bumper"] * 2 + ["Progressive Rear Bumper"] * 2
        sync.tick(parts, set())
        self.assertEqual(self.server.event(31)[0], MAP.event_status_available)   # tier 2 (2 stars)
        self.assertEqual(self.server.event(70)[0], MAP.event_status_locked)      # tier 3 (3 stars)
        self.assertEqual(self.server.event(111)[0], MAP.event_status_locked)
        # Level 2 side skirts: +0.6 = 2.8 -> still 2 full stars.
        sync.tick(parts + ["Progressive Side Skirts"], set())
        self.assertEqual(self.server.event(70)[0], MAP.event_status_locked, "2.8 stars round down to 2")
        sync.tick(parts + ["Progressive Side Skirts"] * 2, set())
        self.assertEqual(self.server.event(70)[0], MAP.event_status_available, "3.1 stars -> tier 3")
        self.assertEqual(self.server.event(92)[0], MAP.event_status_locked, "tier 4 needs 4 stars")

    def test_finale_needs_stars(self):
        sync = self.make_sync(time_trials_required=0)
        sync.tick(["Finale: #111", "Samantha's Big Tease"], set())
        self.assertEqual(self.server.event(111)[0], MAP.event_status_locked, "finale needs 5 stars")

    def test_finale_unlock_and_goal(self):
        sync = self.make_sync(time_trials_required=7, star_gates=False)
        for tt in (7, 15, 26, 47, 68, 77):
            self.server.event(tt, status=2, diff=0)
        items = ["Finale: #111", "Samantha's Big Tease"]
        sync.tick(items, set())
        self.assertEqual(self.server.event(111)[0], MAP.event_status_locked, "only 6 of 7 time trials")
        self.server.event(96, status=2, diff=0)
        sync.tick(items, set())
        self.assertEqual(self.server.event(111)[0], MAP.event_status_available)
        self.assertFalse(sync.tick(items, set()).goal)
        self.server.event(111, status=2, diff=0)
        self.assertTrue(sync.tick(items, set()).goal)

    def test_race_count_goal(self):
        sync = self.make_sync(goal=1, races_for_goal=3)
        for n in (1, 2):
            self.server.event(n, status=2, diff=0)
        self.assertFalse(sync.tick([], set()).goal)
        self.server.event(3, status=2, diff=0)
        self.assertTrue(sync.tick([], set()).goal)


class TestItems(ClientTestBase):
    def test_shop_table_follows_items_not_wins(self):
        sync = self.make_sync()
        self.server.event(6, status=2, diff=0)   # vanilla: #6 would unlock Level 1 Engine/Drivetrain/Tires
        sync.tick(["Progressive Turbo", "Progressive Turbo", "Progressive Rims", "Progressive Spoiler",
                   "Progressive Headlights"], set())
        self.assertEqual([shop(self.server, "Turbo", lvl) for lvl in (1, 2, 3)], [1, 1, 0])
        self.assertEqual(shop(self.server, "Engine/Exhaust", 1), 0, "race wins no longer unlock parts")
        self.assertEqual([shop(self.server, "Rims", lvl) for lvl in (1, 2, 3)], [1, 1, 0], "Rims: progressive")
        self.assertEqual([shop(self.server, "Spoiler", lvl) for lvl in (2, 3)], [1, 0])
        self.assertEqual(shop(self.server, "Headlights", 3), 1, "headlights only have Level 3")
        self.assertEqual(shop(self.server, "Taillights", 3), 0)
        self.assertEqual(shop(self.server, "Front Bumper", 1), 1, "Level 1 visual parts stay for sale")

    def test_car_table_follows_items(self):
        sync = self.make_sync()
        self.server.event(4, status=2, diff=0)   # vanilla: #4 would unlock the Lancer
        sync.tick(["Car: Nissan Skyline GT-R (R34)"], set())
        self.assertEqual(car(self.server, "Mitsubishi Lancer ES"), 0, "race wins no longer unlock cars")
        self.assertEqual(car(self.server, "Nissan Skyline GT-R (R34)"), 1)
        self.assertEqual(car(self.server, "Dodge Neon"), 1, "vanilla start: starter cars are free")
        self.assertEqual([self.server.u32(a) for a, _ in CAR_ORIGINAL], [0x3C03004C, 0x24020001, 0x8042CAC7])
        self.game.remove_car_unlock_patch()
        self.assertEqual([self.server.u32(a) for a, _ in CAR_ORIGINAL], [w for _, w in CAR_ORIGINAL])

    def test_random_start_car_locks_other_starters(self):
        sync = self.make_sync(starting_car="Mazda MX-5")
        sync.tick(["Car: Mazda MX-5", "Car: Dodge Neon"], set())
        self.assertEqual(car(self.server, "Mazda MX-5"), 1)
        self.assertEqual(car(self.server, "Dodge Neon"), 1, "received as item")
        self.assertEqual(car(self.server, "Peugeot 206"), 0)

    def test_car_patch_needs_matching_car_list(self):
        self.server.u32(MAP.car_hash_list, 0x12345678)   # other game version / list moved
        self.make_sync().tick([], set())
        self.assertEqual(self.server.u32(0x860), 0x27BDFFC0, "patch not applied")

    def test_no_car_patch_without_cars_as_items(self):
        self.make_sync(cars_as_items=False).tick([], set())
        self.assertEqual(self.server.u32(0x860), 0x27BDFFC0)

    def test_progressive_levels_count_up(self):
        sync = self.make_sync()
        sync.tick(["Progressive Nitrous"] * 4, set())
        self.assertEqual([shop(self.server, "Nitrous", lvl) for lvl in (1, 2, 3)], [1, 1, 1], "capped at Level 3")
        self.assertEqual(shop(self.server, "Nitrous", 4), 0, "unique part needs the choice event")

    def test_unique_parts_follow_choice_events(self):
        sync = self.make_sync()
        self.server.event(7, status=2, diff=0)      # TJ's Time Trial won
        sync.tick([], set())
        self.assertEqual([shop(self.server, c, 4) for c in ("Engine/Exhaust", "Drivetrain", "Tires")], [1, 1, 1])
        self.assertEqual(shop(self.server, "Hood", 4), 0, "#15 not won")

    def test_shop_patch_applied_after_table_and_removed(self):
        self.make_sync().tick(["Progressive Turbo"], set())
        self.assertEqual([self.server.u32(a) for a, _ in SHOP_ORIGINAL], [0x00131080, 0x10000013, 0x00000000])
        self.assertEqual(shop(self.server, "Turbo", 1), 1)
        self.game.remove_part_unlock_patch()
        self.assertEqual([self.server.u32(a) for a, _ in SHOP_ORIGINAL], [w for _, w in SHOP_ORIGINAL])

    def test_shop_patch_leaves_foreign_code(self):
        self.server.u32(0x840, 0x12345678)
        self.make_sync().tick([], set())
        self.assertEqual(self.server.u32(0x840), 0x12345678)
        self.assertEqual(self.server.u32(0x848), 0x2C420001)

    def test_bank_items_applied_once(self):
        sync = self.make_sync(bank_multiplier=150, starting_bank=2000)
        self.server.u32(MAP.bank, 500)
        received = ["Progressive Turbo", "Bank Bonus (1000)"]
        sync.tick(received, set())
        self.assertEqual(self.server.u32(MAP.bank), 500 + 2000 + 1500)
        sync.tick(received, set())
        self.assertEqual(self.server.u32(MAP.bank), 4000, "no double application")
        self.assertEqual(self.server.u32(MAP.ap_save_block), 2)
        # A fresh client session (restart) must not apply anything again either.
        self.make_sync(bank_multiplier=150, starting_bank=2000).tick(received, set())
        self.assertEqual(self.server.u32(MAP.bank), 4000)

    def test_bank_tax_trap(self):
        sync = self.make_sync()
        self.server.u32(MAP.bank, 10000)
        sync.tick(["Bank Tax Trap"], set())
        self.assertEqual(self.server.u32(MAP.bank), 9000)

    def test_vanilla_bank_removed_once(self):
        sync = self.make_sync(vanilla_bank_rewards=False)
        self.server.u32(MAP.bank, 5000)
        self.server.u32(MAP.ap_save_block + 4, 1)  # starting bank already handled
        self.server.event(1, status=2, diff=1)      # #1 Medium pays 500
        result = sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.bank), 4500)
        sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.bank), 4500)
        sync.tick([], result.new_checks)
        self.assertEqual(self.server.u32(MAP.bank), 4500)


class TestRaces(ClientTestBase):
    """Layout found in NFSU NTSC-U (#2): race_active stays set on the results screen, the results
    popup list says won/lost, positions are u32 in a list behind a pointer."""
    INFO = 0x7400
    LOST = "Sorry, you lost this event.  Please try again."

    def results(self, lost, positions):
        self.server.u32(MAP.race_info_pointer, self.INFO)
        for i, p in enumerate(positions + [0x01195800]):           # a racer pointer follows the positions
            self.server.u32(self.INFO + MAP.race_position_offset + 4 * i, p)
        owner, node = 0x7500, 0x7600
        head = owner + 0x0C
        self.server.u32(0x900, owner)
        self.server.u32(head, node)
        self.server.u32(head + 4, node)
        self.server.u32(node, head)
        self.server.u32(node + 4, head)
        self.server.u32(node + 8, 0x2CCB70AA)
        text = (self.LOST if lost else "Congratulations!  You have 200 added to your Bank.").encode() + b"\x00"
        self.server.mem[node + 0x0C:node + 0x0C + len(text)] = text

    def race(self, sync, received, position, racers=4, back_to_map=True):
        self.server.u32(MAP.race_active, 0)
        sync.tick(received, set())                                  # on the map
        self.server.u32(MAP.race_active, 0x01173440)
        start = sync.tick(received, set())
        others = [p for p in range(1, racers + 1) if p != position]
        self.results(position != 1, [position] + others)
        end = sync.tick(received, set())                            # results screen (race still loaded)
        self.assertIsNone(sync.tick(received, set()).send_death, "a results screen counts once")
        self.server.u32(0x900, 0)                                   # popups clicked away
        if back_to_map:
            self.server.u32(MAP.race_active, 0)
        sync.tick(received, set())
        return start, end

    def test_race_result_from_popups_and_positions(self):
        self.race(self.make_sync(), [], 3)
        self.results(True, [3, 1, 4, 2])
        result = self.game.race_result()
        self.assertEqual((result.won, result.position, result.racers, result.last_place), (False, 3, 4, False))
        self.results(True, [4, 2, 1, 3])
        self.assertTrue(self.game.race_result().last_place)
        self.results(False, [1, 2])
        self.assertEqual((self.game.race_result().won, self.game.race_result().racers), (True, 2))
        self.results(True, [1])                                       # drift: only the player is listed
        self.assertTrue(self.game.race_result().last_place, "a lost drift counts as last place")
        self.results(False, [1])
        self.assertFalse(self.game.race_result().last_place)

    def test_lost_race_sends_death(self):
        sync = self.make_sync(death_link=True)
        self.assertIsNotNone(self.race(sync, [], 2)[1].send_death)
        self.assertIsNone(self.race(sync, [], 1)[1].send_death)

    def test_restart_from_results_counts_again(self):
        sync = self.make_sync(death_link=True)
        self.assertIsNotNone(self.race(sync, [], 3, back_to_map=False)[1].send_death)
        self.results(True, [4, 1, 2, 3])                              # restarted, lost again, never on the map
        self.assertIsNotNone(sync.tick([], set()).send_death)

    def test_death_link_amnesty(self):
        sync = self.make_sync(death_link=True, death_link_amnesty=1)
        self.assertIsNone(self.race(sync, [], 3)[1].send_death)
        self.assertIsNone(self.race(sync, [], 1)[1].send_death)       # a win does not count
        self.assertIsNotNone(self.race(sync, [], 4)[1].send_death)    # second loss -> death

    def test_last_place_trigger(self):
        sync = self.make_sync(death_link=True, death_link_trigger=1)
        self.assertIsNone(self.race(sync, [], 3)[1].send_death)
        self.assertIsNotNone(self.race(sync, [], 4)[1].send_death)

    def test_received_death_fails_race_without_echo(self):
        sync = self.make_sync(death_link=True)
        sync.tick([], set())                                        # on the map
        self.server.u32(MAP.race_active, 1)
        sync.tick([], set())
        sync.receive_death()
        sync.tick([], set())
        self.assertEqual(self.server.u8(MAP.force_race_loss), 1)
        self.results(True, [4, 1, 2, 3])
        self.assertIsNone(sync.tick([], set()).send_death)

    RACER, SIM, HEAT = 0x7800, 0x7900, 0x7A00

    def drag(self, sync, positions=(2, 1, 3, 4)):
        """Drag race loaded and running: positions, player racer pointer behind them, heat object chain."""
        self.server.u32(MAP.engine_heat_enabled, 1)
        self.server.u32(MAP.race_info_pointer, self.INFO)
        for i, p in enumerate(list(positions) + [self.RACER]):
            self.server.u32(self.INFO + MAP.race_position_offset + 4 * i, p)
        self.server.u32(self.RACER + MAP.racer_sim_offset, self.SIM)
        self.server.u32(self.SIM + MAP.sim_engine_heat_offset, self.HEAT)
        self.server.u32(MAP.race_active, 0)
        sync.tick([], set())                                        # on the map
        self.server.u32(MAP.race_active, 1)
        sync.tick([], set())

    def blown(self):
        return self.server.u32(self.HEAT + MAP.engine_blown_offset)

    def test_received_death_blows_engine_in_drag(self):
        sync = self.make_sync(death_link=True)
        self.drag(sync)
        sync.receive_death()
        out = sync.tick([], set())
        self.assertEqual(self.blown(), 1)
        self.assertEqual(self.server.u8(MAP.force_race_loss), 0)
        self.assertIsNone(out.send_death, "a received death is not echoed")
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_blown_engine_sends_death_once(self):
        sync = self.make_sync(death_link=True)
        self.drag(sync)
        self.assertIsNone(sync.tick([], set()).send_death)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)    # overheated by the player
        self.assertEqual(sync.tick([], set()).send_death, "blew the engine")
        self.assertIsNone(sync.tick([], set()).send_death)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 0)    # restart from the pause menu
        sync.tick([], set())
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)
        self.assertIsNotNone(sync.tick([], set()).send_death, "the restarted race counts again")

    def test_blown_engine_respects_amnesty_and_forced(self):
        sync = self.make_sync(death_link=True, death_link_amnesty=1)
        self.drag(sync)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)
        self.assertIsNone(sync.tick([], set()).send_death)          # first loss forgiven
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 0)
        sync.tick([], set())
        sync.receive_death()                                        # blown by a received death: no echo
        sync.tick([], set())
        self.assertEqual(self.blown(), 1)
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_received_death_blows_engine_in_sprint(self):
        """Seen in game: heat check switched on + blown in a sprint -> results screen "Blown Engine", 4th,
        "Sorry, you lost" popup. The heat check must be switched off again afterwards."""
        sync = self.make_sync(death_link=True)
        self.drag(sync, positions=(3, 1, 2, 4))
        self.server.u32(MAP.engine_heat_enabled, 0)                 # sprint: no heat simulation
        sync.tick([], set())
        sync.receive_death()
        self.assertIsNone(sync.tick([], set()).send_death)
        self.assertEqual((self.server.u32(MAP.engine_heat_enabled), self.blown()), (1, 1))
        self.results(True, [4, 1, 2, 3])                              # results screen, chain points elsewhere
        self.server.u32(self.INFO + MAP.race_position_offset + 16, self.RACER)
        self.assertIsNone(sync.tick([], set()).send_death, "a received death is not echoed")
        self.assertEqual(self.server.u32(MAP.engine_heat_enabled), 0, "heat check switched off again")
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_received_death_blows_engine_in_drift(self):
        """Seen in game (drift): only the player is listed, the free position slots hold 0xAAAAAAAA and the
        racer pointer comes after 4 slots. Before the fix a received death only drained the nitrous."""
        sync = self.make_sync(death_link=True)
        self.drag(sync, positions=(1, 0xAAAAAAAA, 0xAAAAAAAA, 0xAAAAAAAA))
        self.server.u32(MAP.engine_heat_enabled, 0)                 # drift: no heat simulation
        sync.tick([], set())
        sync.receive_death()
        out = sync.tick([], set())
        self.assertIn("Death Link: engine blown.", out.messages)
        self.assertEqual((self.server.u32(MAP.engine_heat_enabled), self.blown()), (1, 1))
        self.assertIsNone(out.send_death)

    def drift_on_connect(self, sync):
        """Drift already running when the client connects (no race start seen), then a received death."""
        self.server.u32(MAP.engine_heat_enabled, 0)
        self.server.u32(MAP.race_info_pointer, self.INFO)
        for i, p in enumerate([1, 0xAAAAAAAA, 0xAAAAAAAA, 0xAAAAAAAA, self.RACER]):
            self.server.u32(self.INFO + MAP.race_position_offset + 4 * i, p)
        self.server.u32(self.RACER + MAP.racer_sim_offset, self.SIM)
        self.server.u32(self.SIM + MAP.sim_engine_heat_offset, self.HEAT)
        self.server.u32(MAP.race_active, 1)
        sync.tick([], set())
        sync.receive_death()
        sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.engine_heat_enabled), 1)
        sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.engine_heat_enabled), 1, "stays on until the attempt is over")

    def test_heat_flag_off_at_results_when_connected_mid_race(self):
        """Seen in game: client connected during a drift, received death -> results -> restart ran as drag."""
        sync = self.make_sync(death_link=True)
        self.drift_on_connect(sync)
        self.results(True, [1])
        sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.engine_heat_enabled), 0)

    def test_heat_flag_off_when_race_restarted_after_received_death(self):
        sync = self.make_sync(death_link=True)
        self.drift_on_connect(sync)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 0)    # restarted: fresh engine
        sync.tick([], set())
        self.assertEqual(self.server.u32(MAP.engine_heat_enabled), 0)

    def test_no_death_from_stale_heat_after_a_win(self):
        """Seen in game (#11 drag): won, then 2 s later the stale heat object read "blown" -> false death."""
        sync = self.make_sync(death_link=True)
        self.drag(sync, positions=(1, 2, 3, 4))
        self.results(False, [1, 2, 3, 4])
        self.server.u32(self.INFO + MAP.race_position_offset + 16, self.RACER)
        self.assertIsNone(sync.tick([], set()).send_death)          # won
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)    # stale pointer on the results screen
        out = sync.tick([], set())
        self.assertIsNone(out.send_death)
        self.assertNotIn("Race result: lost, blown engine", out.messages)

    def test_blown_engine_and_lost_result_send_one_death(self):
        """Seen in game: own blowout, then the results popup "lost, 4 of 4" -> two deaths were sent."""
        sync = self.make_sync(death_link=True)
        self.drag(sync)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)
        self.assertIsNotNone(sync.tick([], set()).send_death)
        self.results(True, [4, 1, 2, 3])
        self.server.u32(self.INFO + MAP.race_position_offset + 16, self.RACER)
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_received_death_not_echoed_when_flag_flickers(self):
        """Seen in game: received death -> blown 1, 0, 1 within seconds -> a death was sent back."""
        sync = self.make_sync(death_link=True)
        self.drag(sync)
        sync.receive_death()
        self.assertIsNone(sync.tick([], set()).send_death)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 0)
        self.assertIsNone(sync.tick([], set()).send_death)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_no_blown_engine_outside_drag(self):
        sync = self.make_sync(death_link=True)
        self.drag(sync)
        self.server.u32(MAP.engine_heat_enabled, 0)
        self.server.u32(self.HEAT + MAP.engine_blown_offset, 1)    # stale value, heat not simulated
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_no_death_for_results_screen_on_connect(self):
        sync = self.make_sync(death_link=True)
        self.server.u32(MAP.race_active, 1)
        self.results(True, [4, 1, 2, 3])
        self.assertIsNone(sync.tick([], set()).send_death)

    def test_grip_trap_restores_parts(self):
        sync = self.make_sync()
        tires = MAP.installed_performance + PERF_INDEX["Tires"]
        self.server.u8(tires, 3)
        received = ["Grip Loss Trap", "HUD Blackout Trap"]
        self.server.u8(MAP.hud_visible, 1)
        sync.tick(received, set())               # queued
        self.assertEqual(self.server.u8(tires), 3)
        self.server.u8(MAP.race_active, 1)
        sync.tick(received, set())               # race starts
        self.assertEqual(self.server.u8(tires), 0)
        self.assertEqual(self.server.u8(MAP.hud_visible), 0)
        self.server.u8(MAP.race_active, 0)
        sync.tick(received, set())               # race ends
        self.assertEqual(self.server.u8(tires), 3)
        self.assertEqual(self.server.u8(MAP.hud_visible), 1)


class TestRealEventLayout(ClientTestBase):
    """Layout found in NFSU NTSC-U: 1 status byte per event, difficulty only as "last race difficulty"."""
    TABLE = 0x2000
    LAST_DIFF = 0x1FF0
    LAST_WON = 0x1FF4

    def setUp(self) -> None:
        super().setUp()
        import dataclasses
        interface_mod.ADDRESSES[TEST_SERIAL] = dataclasses.replace(
            MAP, event_table=self.TABLE, event_stride=1, event_difficulty_offset=None, event_status_active=3,
            last_race_difficulty=self.LAST_DIFF, last_won_event=self.LAST_WON)
        self.server.u32(self.LAST_WON, 0xFFFFFFFF)
        self.game.disconnect()
        self.assertTrue(self.game.connect())
        self.server.mem[self.TABLE:self.TABLE + 6] = bytes([2, 1, 1, 1, 1, 1])  # like a fresh career

    def status(self, n):
        return self.server.mem[self.TABLE + n]

    def test_win_while_watching(self):
        sync = self.make_sync()
        self.assertEqual(sync.tick([], set()).new_checks, set())
        self.server.u8(self.LAST_DIFF, 1)
        self.server.mem[self.TABLE + 2] = 2                     # #2 won (any difficulty)
        result = sync.tick([], set())
        self.assertEqual(result.new_checks, C(2))
        self.assertEqual(self.status(2), 2, "stays won")

    def test_wins_from_before_the_client_are_sent(self):
        self.server.u32(self.LAST_WON, 0xFFFFFFFF)
        self.server.mem[self.TABLE:self.TABLE + 6] = bytes([2, 2, 2, 1, 2, 1])   # won while the client was closed
        result = self.make_sync().tick([], set())
        self.assertEqual(result.new_checks, C(1) | C(2) | C(4))
        self.assertEqual(len(C(4)), 2, "#4 has two vanilla rewards (car + course)")

    def test_active_event_is_never_overwritten(self):
        self.server.mem[self.TABLE + 4] = 3                     # being raced
        sync = self.make_sync()
        sync.tick([], set())
        self.assertEqual(self.status(4), 3)
        self.assertEqual(self.status(10), 1, "other tier-1 events are opened")

    def test_checked_event_is_not_resent(self):
        self.server.mem[self.TABLE + 1] = 2
        sync = self.make_sync()
        self.assertEqual(sync.tick([], C(1)).new_checks, set())
        self.assertEqual(self.status(1), 2)


class TestEventIndexGap(TestRealEventLayout):
    """NTSC-U has no event record #85: wiki #85..#112 are game indices 86..113."""

    def setUp(self) -> None:
        super().setUp()
        import dataclasses
        interface_mod.ADDRESSES[TEST_SERIAL] = dataclasses.replace(
            interface_mod.ADDRESSES[TEST_SERIAL], event_index_gaps=(85,))
        self.game.disconnect()
        self.assertTrue(self.game.connect())

    def test_index_mapping(self):
        self.assertEqual([self.game.game_index(n) for n in (84, 85, 91, 111, 112)], [84, 86, 92, 112, 113])
        self.assertEqual([self.game.event_number(i) for i in (84, 85, 86, 113)], [84, None, 85, 112])

    def test_win_after_gap_uses_game_index(self):
        self.server.mem[self.TABLE + 92] = 2                    # game #92 = wiki #91 Eddie's Posse Part 1
        result = self.make_sync().tick([], set())
        self.assertEqual(result.new_checks, C(91))
        self.assertEqual(self.status(85), 0, "the unused index is never written")

    def test_last_won_event_is_translated(self):
        self.server.u32(self.LAST_WON, 92)
        self.assertEqual(self.game.last_won_event(), 91)

    def test_active_event_after_gap(self):
        self.server.mem[self.TABLE + 112] = 3
        self.assertEqual(self.game.active_event(), 111)


class TestMapPatch(ClientTestBase):
    def test_patch_applied_and_removed(self):
        self.make_sync().tick([], set())
        self.assertEqual(self.server.u32(0x800), 0x03E00008)
        self.assertEqual(self.server.u32(0x804), 0x00000000)
        self.game.remove_availability_patch()
        self.assertEqual(self.server.u32(0x800), 0x27BDFFC0)
        self.assertEqual(self.server.u32(0x804), 0xFFB20020)

    def test_unknown_code_means_no_availability_writes(self):
        self.server.u32(0x800, 0x12345678)
        self.make_sync().tick([], set())
        self.assertEqual(self.server.u32(0x800), 0x12345678, "foreign code is never overwritten")
        self.assertEqual(self.server.event(10)[0], 0, "no availability writes without the patch")

    def test_events_of_several_sets_open_at_once(self):
        self.make_sync().tick([], set())
        self.assertEqual([self.server.event(n)[0] for n in (1, 6, 14, 29)], [1, 1, 1, 1])
        self.assertEqual(self.server.event(30)[0], 0)

    def test_declined_time_trial_is_reopened(self):
        self.server.event(7, status=4)        # e.g. a declined time trial
        self.make_sync().tick([], set())
        self.assertEqual(self.server.event(7)[0], 1)

    def test_epilogue_after_finale(self):
        self.server.event(111, status=2, diff=0)
        self.make_sync().tick([], set())
        self.assertEqual(self.server.event(112)[0], 1)


class TestRewardPopups(ClientTestBase):
    """Popup list as found in NFSU NTSC-U after winning #6 (Bank popup + three unlock popups)."""
    OWNER = 0x3000

    def build(self, texts, tags=None):
        head = self.OWNER + 0x0C
        nodes = [0x3100 + i * 0x140 for i in range(len(texts))]
        tags = tags or [0x2CCB70AA] * len(texts)
        self.server.u32(0x900, self.OWNER)
        self.server.u32(head, nodes[0])
        self.server.u32(head + 4, nodes[-1])
        for i, (node, text) in enumerate(zip(nodes, texts)):
            self.server.u32(node, nodes[i + 1] if i + 1 < len(nodes) else head)
            self.server.u32(node + 4, nodes[i - 1] if i else head)
            self.server.u32(node + 8, tags[i])
            data = text.encode() + b"\x00"
            self.server.mem[node + 0x0C:node + 0x0C + len(data)] = data
        return nodes

    def text(self, node):
        return bytes(self.server.mem[node + 0x0C:node + 0x0C + 220]).split(b"\x00", 1)[0].decode()

    SIX = ["Congratulations!  You have 3750 added to your Bank.",
           "Congratulations!^You have unlocked the following Performance Upgrade.^Level 1 Engine / Exhaust Packages",
           "Congratulations!^You have unlocked the following Performance Upgrade.^Level 1 Drivetrain Packages",
           "Congratulations!^You have unlocked the following Performance Upgrade.^Level 1 Tire Packages"]

    def test_win_is_sent_on_the_results_screen_and_popups_show_items(self):
        sync = self.make_sync()
        ids = sorted(C(6))
        names = {ids[0]: "Turbo Upgrade", ids[1]: "Hookshot for Bob", ids[2]: "Bank Bonus (500)"}
        sync.describe = names.get
        self.server.event(6, status=3)                       # still "being raced" on the results screen
        nodes = self.build(self.SIX)
        result = sync.tick([], set())
        self.assertEqual(result.new_checks, C(6), "checks sent before going back to the map")
        self.assertEqual(self.text(nodes[1]), "ARCHIPELAGO!^You found:^Turbo Upgrade")
        self.assertEqual(self.text(nodes[2]), "ARCHIPELAGO!^You found:^Hookshot for Bob")
        self.assertEqual(self.text(nodes[3]), "ARCHIPELAGO!^You found:^Bank Bonus (500)")
        self.assertIn("You have 3750 added to your Bank.", self.text(nodes[0]))
        self.assertEqual(self.server.event(6)[0], 3, "the active event is never touched")

    def test_style_reward_popup_is_skipped(self):
        """Live list after winning #3 (drift): a 'Style Reward' node with another tag comes first."""
        sync = self.make_sync()
        sync.describe = lambda i: "Progressive Side Skirts"
        self.server.event(3, status=3)
        style = "Congratulations!^You have unlocked^the RadioShack XMOD Vinyl."
        nodes = self.build([style,
                            "Congratulations!  You have 375 added to your Bank.",
                            "Congratulations!^You have unlocked^Drift Track 1"],
                           tags=[0x6A765215, 0x2CCB70AA, 0x2CCB70AA])
        self.assertEqual(sync.tick([], set()).new_checks, C(3))
        self.assertEqual(self.text(nodes[0]), style, "style reward popup stays untouched")
        self.assertTrue(self.text(nodes[2]).startswith("ARCHIPELAGO!^You found:^Progressive Side Skirts"))

    def test_event_without_reward_lists_item_in_bank_popup(self):
        sync = self.make_sync()
        sync.describe = lambda i: "Car: Mazda RX-7 for Alice"
        self.server.event(21, status=3)                      # #21 has no vanilla reward -> "Victory"
        nodes = self.build(["Congratulations!  You have 200 added to your Bank."])
        self.assertEqual(sync.tick([], set()).new_checks, C(21))
        self.assertEqual(self.text(nodes[0]),
                         "ARCHIPELAGO! You found:^Car: Mazda RX-7 for Alice^You have 200 added to your Bank.")

    def test_popups_written_once_and_choice_events_untouched(self):
        sync = self.make_sync()
        self.server.event(7, status=3)                       # time trial: no checks
        nodes = self.build(self.SIX[:2])
        self.assertEqual(sync.tick([], set()).new_checks, set())
        self.assertEqual(self.text(nodes[1]), self.SIX[1])

    def test_no_popups_no_win(self):
        sync = self.make_sync()
        self.server.event(6, status=3)                       # racing, no popup object yet
        self.assertEqual(sync.tick([], set()).new_checks, set())


class TestServerCounter(ClientTestBase):
    """Bank items with the counter on the server (no save block in game memory)."""

    def setUp(self) -> None:
        super().setUp()
        import dataclasses
        interface_mod.ADDRESSES[TEST_SERIAL] = dataclasses.replace(MAP, ap_save_block=None)
        self.game.disconnect()
        self.assertTrue(self.game.connect())
        self.server.u32(MAP.bank, 1000)

    def test_bank_paid_once_with_server_counter(self):
        store = MemoryCounterStore()
        received = ["Bank Bonus (500)", "Progressive Turbo", "Bank Bonus (1000)"]
        GameSync(self.game, Settings(), counter_store=store).tick(received, set())
        self.assertEqual(self.server.u32(MAP.bank), 2500)
        self.assertEqual(store.value[0], 3)
        # Client restart with the same server value: nothing is paid again.
        GameSync(self.game, Settings(), counter_store=store).tick(received, set())
        self.assertEqual(self.server.u32(MAP.bank), 2500)
        # One new item later.
        GameSync(self.game, Settings(), counter_store=store).tick(received + ["Bank Bonus (2500)"], set())
        self.assertEqual(self.server.u32(MAP.bank), 5000)

    def test_counter_not_loaded_yet_pays_nothing(self):
        class NotLoaded(MemoryCounterStore):
            def load(self):
                return None
        GameSync(self.game, Settings(), counter_store=NotLoaded()).tick(["Bank Bonus (500)"], set())
        self.assertEqual(self.server.u32(MAP.bank), 1000)

    def test_counter_ahead_of_items_never_goes_back(self):
        # Right after connecting the counter can be known before the item list arrives.
        store = MemoryCounterStore(index=2, flags=1)
        sync = GameSync(self.game, Settings(), counter_store=store)
        sync.tick([], set())
        self.assertEqual(store.value, (2, 1), "counter must not be reset")
        sync.tick(["Bank Bonus (500)", "Bank Bonus (1000)"], set())
        self.assertEqual(self.server.u32(MAP.bank), 1000, "already paid items are not paid again")
        sync.tick(["Bank Bonus (500)", "Bank Bonus (1000)", "Bank Bonus (500)"], set())
        self.assertEqual(self.server.u32(MAP.bank), 1500)

    def test_no_store_and_no_save_block_pays_nothing(self):
        sync = GameSync(self.game, Settings())
        sync.tick(["Bank Bonus (500)"], set())
        self.assertEqual(self.server.u32(MAP.bank), 1000)
        self.assertIn("ap_save_block", sync.missing)


class TestBanner(ClientTestBase):
    def text(self, addr):
        raw = bytes(self.server.mem[addr:addr + 32])
        return raw.split(b"\x00", 1)[0].decode()

    def test_banner_shown_one_after_another(self):
        now = [100.0]
        sync = GameSync(self.game, Settings(), clock=lambda: now[0])
        sync.banners.received("Progressive Turbo", "Bob")
        sync.banners.sent("Hookshot", "Alice")
        sync.tick([], set())
        self.assertEqual(self.text(MAP.banner_line1), "Turbo Upgrade")
        self.assertEqual(self.text(MAP.banner_line2), "from Bob")
        self.assertEqual(self.server.u8(MAP.banner_trigger), 90)
        self.server.u8(MAP.banner_trigger, 0)
        now[0] += 1.0
        sync.tick([], set())
        self.assertEqual(self.server.u8(MAP.banner_trigger), 0, "second banner waits")
        now[0] += 4.0
        sync.tick([], set())
        self.assertEqual(self.text(MAP.banner_line1), "Sent Hookshot")
        self.assertEqual(self.text(MAP.banner_line2), "to Alice")

    def test_long_text_and_non_ascii_are_cut(self):
        sync = self.make_sync()
        sync.banners.received("Unique Performance Part (Mods to the Max)", "Jürgen")
        sync.tick([], set())
        line1 = self.text(MAP.banner_line1)
        self.assertLessEqual(len(line1), 20)
        self.assertTrue(line1.endswith("..."))
        self.assertEqual(self.text(MAP.banner_line2), "from J?rgen")

    def test_backlog_is_summarised(self):
        sync = self.make_sync()
        for i in range(25):
            sync.banners.received(f"Item {i}", "Bob")
        self.assertLessEqual(len(sync.banners.queue), 20)


class TestPlaceholders(ClientTestBase):
    def test_unmapped_addresses_do_not_crash(self):
        interface_mod.ADDRESSES[TEST_SERIAL] = AddressMap()
        self.game.disconnect()
        self.assertTrue(self.game.connect())
        sync = self.make_sync(death_link=True)
        result = sync.tick(["Bank Bonus (1000)", "Grip Loss Trap"], set())
        self.assertEqual(result.new_checks, set())
        self.assertIn("event_status_won / event_stride", sync.missing)
        self.assertIn("bank", sync.missing)

    def test_shipped_table_is_placeholder_for_ntsc_u(self):
        self.assertIn(addresses_mod.SERIAL_NTSC_U, self._old_addresses)


class TestClientModules(unittest.TestCase):
    def test_context_and_component_import(self):
        from ..client import context
        from worlds.LauncherComponents import components
        self.assertTrue(issubclass(context.NFSUContext, object))
        self.assertIn("NFSU Client", [c.display_name for c in components])

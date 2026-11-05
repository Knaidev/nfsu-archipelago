"""PINE memory scanner for finding NFSU addresses (like a tiny Cheat Engine for PCSX2).

Needs only Python 3.8+ and PCSX2 with PINE enabled (slot 28011). No Archipelago needed.

Typical workflow (see research/RAM_Adressen_Anleitung.md):
    python tools/pine_memscan.py info
    python tools/pine_memscan.py snap before            # dump EE RAM to scans/before.bin
    ... win a race in the game ...
    python tools/pine_memscan.py snap after
    python tools/pine_memscan.py diff before after --size 1 --changed --limit 50
    python tools/pine_memscan.py find --value 12500 --size 4      # e.g. current Bank
    python tools/pine_memscan.py refine --value 13000             # keep addresses that now hold 13000
    python tools/pine_memscan.py findstr "Get Low" --ignore-case  # find a text, e.g. the song banner
    python tools/pine_memscan.py watch 0x00ABCDEF --size 4         # print a value live
    python tools/pine_memscan.py read 0x00ABCDEF --length 64
"""
import argparse
import json
import pathlib
import struct
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worlds" / "nfsu" / "client"))
from pine import Pine  # noqa: E402  (standalone module, no Archipelago imports)

EE_RAM_SIZE = 0x02000000
SCAN_DIR = pathlib.Path(__file__).resolve().parent / "scans"
CANDIDATES = SCAN_DIR / "candidates.json"
FMT = {1: "<B", 2: "<H", 4: "<I", 8: "<Q"}


def dump(pine: Pine, start: int, length: int) -> bytes:
    chunk = 0x40000  # 256 KiB per batch keeps replies under the PINE size limit
    out = bytearray()
    for off in range(0, length, chunk):
        n = min(chunk, length - off)
        out += pine.read_bytes(start + off, n)
        print(f"\r  {100 * (off + n) // length:3d}%", end="", flush=True)
    print()
    return bytes(out)


def value_at(data: bytes, off: int, size: int, as_float: bool):
    if as_float:
        return struct.unpack_from("<f", data, off)[0]
    return struct.unpack_from(FMT[size], data, off)[0]


def cmd_info(pine, a):
    print("Game ID:", pine.game_id())
    print("Title:  ", pine.game_title())
    print("Status: ", pine.status().name)


def cmd_snap(pine, a):
    SCAN_DIR.mkdir(exist_ok=True)
    start = int(a.start, 0)
    length = int(a.length, 0)
    print(f"Dumping 0x{start:08X}-0x{start + length:08X} …")
    data = dump(pine, start, length)
    (SCAN_DIR / f"{a.name}.bin").write_bytes(data)
    (SCAN_DIR / f"{a.name}.json").write_text(json.dumps({"start": start, "time": time.time()}))
    print(f"Saved scans/{a.name}.bin ({len(data)} bytes)")


def load(name):
    meta = json.loads((SCAN_DIR / f"{name}.json").read_text())
    return meta["start"], (SCAN_DIR / f"{name}.bin").read_bytes()


def cmd_diff(pine, a):
    s1, d1 = load(a.a)
    s2, d2 = load(a.b)
    if s1 != s2 or len(d1) != len(d2):
        sys.exit("Snapshots cover different ranges.")
    # Noise filter: pairs of snapshots taken while nothing relevant happened. Every byte that changed
    # between them is ignored.
    noisy = bytearray(len(d1))
    for pair in a.noise or []:
        n1, n2 = (load(x)[1] for x in pair.split(","))
        for off in range(len(d1)):
            if n1[off] != n2[off]:
                noisy[off] = 1
    size, shown = a.size, 0
    for off in range(0, len(d1) - size + 1, size):
        if any(noisy[off:off + size]):
            continue
        v1 = value_at(d1, off, size, a.float)
        v2 = value_at(d2, off, size, a.float)
        if (v1 != v2) == a.changed and (a.delta is None or v2 - v1 == a.delta):
            if a.changed or v1 == (a.equals if a.equals is not None else v1):
                print(f"0x{s1 + off:08X}: {v1} -> {v2}")
                shown += 1
                if shown >= a.limit:
                    print(f"… (limit {a.limit} reached)")
                    break


def cmd_find(pine, a):
    start, length = int(a.start, 0), int(a.length, 0)
    data = dump(pine, start, length)
    target = float(a.value) if a.float else int(a.value, 0)
    hits = [start + off for off in range(0, len(data) - a.size + 1, a.size)
            if value_at(data, off, a.size, a.float) == target]
    SCAN_DIR.mkdir(exist_ok=True)
    CANDIDATES.write_text(json.dumps({"size": a.size, "float": a.float, "addresses": hits}))
    print(f"{len(hits)} candidates saved. Change the value in game, then run 'refine'.")
    for h in hits[:20]:
        print(f"  0x{h:08X}")


def cmd_findstr(pine, a):
    """Finds an ASCII text (e.g. the song title while the "now playing" banner is visible)."""
    start, length = int(a.start, 0), int(a.length, 0)
    data = dump(pine, start, length)
    needle = a.text.encode("ascii")
    hay = data.lower() if a.ignore_case else data
    if a.ignore_case:
        needle = needle.lower()
    pos, hits = 0, []
    while True:
        pos = hay.find(needle, pos)
        if pos < 0:
            break
        hits.append(pos)
        pos += 1
    print(f"{len(hits)} hits for {a.text!r}")
    for off in hits[:a.limit]:
        end = data.find(b"\x00", off)
        end = off + 64 if end < 0 or end - off > 64 else end
        ctx_start = max(0, off - 16)
        print(f"  0x{start + off:08X}: {data[off:end]!r}   (bytes before: {data[ctx_start:off].hex(' ')})")


def cmd_refine(pine, a):
    c = json.loads(CANDIDATES.read_text())
    size, as_float = c["size"], c["float"]
    reqs = [(addr, size if not as_float else 4) for addr in c["addresses"]]
    values = pine.batch_read(reqs) if reqs else []
    keep = []
    for addr, raw in zip(c["addresses"], values):
        v = struct.unpack("<f", raw.to_bytes(4, "little"))[0] if as_float else raw
        if a.value is not None:
            target = float(a.value) if as_float else int(a.value, 0)
            ok = v == target
        else:
            ok = True
        if ok:
            keep.append(addr)
    c["addresses"] = keep
    CANDIDATES.write_text(json.dumps(c))
    print(f"{len(keep)} candidates left.")
    for h in keep[:20]:
        print(f"  0x{h:08X}")


def cmd_watch(pine, a):
    addr = int(a.address, 0)
    last = None
    try:
        while True:
            v = pine.read_float(addr) if a.float else pine.read(addr, a.size)
            if v != last:
                print(f"{time.strftime('%H:%M:%S')}  0x{addr:08X} = {v}")
                last = v
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass


def cmd_read(pine, a):
    addr, length = int(a.address, 0), int(a.length, 0)
    data = pine.read_bytes(addr, length)
    for i in range(0, len(data), 16):
        row = data[i:i + 16]
        print(f"0x{addr + i:08X}: {row.hex(' ')}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--slot", type=int, default=28011)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info")
    s = sub.add_parser("snap")
    s.add_argument("name")
    s.add_argument("--start", default="0x0")
    s.add_argument("--length", default=hex(EE_RAM_SIZE))

    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--size", type=int, default=1, choices=(1, 2, 4, 8))
    d.add_argument("--float", action="store_true")
    g = d.add_mutually_exclusive_group()
    g.add_argument("--changed", dest="changed", action="store_true", default=True)
    g.add_argument("--unchanged", dest="changed", action="store_false")
    d.add_argument("--delta", type=int, default=None, help="only changes by exactly this amount")
    d.add_argument("--equals", type=int, default=None, help="with --unchanged: only this value")
    d.add_argument("--limit", type=int, default=200)
    d.add_argument("--noise", action="append", metavar="SNAP1,SNAP2",
                   help="ignore bytes that changed between these two snapshots (repeatable)")

    f = sub.add_parser("find")
    f.add_argument("--value", required=True)
    f.add_argument("--size", type=int, default=4, choices=(1, 2, 4, 8))
    f.add_argument("--float", action="store_true")
    f.add_argument("--start", default="0x0")
    f.add_argument("--length", default=hex(EE_RAM_SIZE))

    fs = sub.add_parser("findstr")
    fs.add_argument("text")
    fs.add_argument("--ignore-case", action="store_true")
    fs.add_argument("--start", default="0x0")
    fs.add_argument("--length", default=hex(EE_RAM_SIZE))
    fs.add_argument("--limit", type=int, default=30)

    r = sub.add_parser("refine")
    r.add_argument("--value", default=None)

    w = sub.add_parser("watch")
    w.add_argument("address")
    w.add_argument("--size", type=int, default=4, choices=(1, 2, 4, 8))
    w.add_argument("--float", action="store_true")
    w.add_argument("--interval", type=float, default=0.2)

    rd = sub.add_parser("read")
    rd.add_argument("address")
    rd.add_argument("--length", default="64")

    a = p.parse_args()
    pine = Pine(a.slot, timeout=5.0)
    if a.cmd not in ("diff",) and not pine.connect():
        sys.exit(f"Cannot reach PCSX2 on PINE slot {a.slot}. Enable PINE in PCSX2 (Settings → Advanced).")
    try:
        globals()[f"cmd_{a.cmd}"](pine, a)
    finally:
        pine.disconnect()


if __name__ == "__main__":
    main()

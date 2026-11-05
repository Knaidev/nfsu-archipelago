"""Find NFSU event records by their prerequisite list (+156: int16 ids, +168: mode, +170: count) and list
callers of the availability recompute function 0x00316800."""
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mips import RAM, dis, word  # noqa: E402

# Record of #6 should list 1..5 (mode 0 = all, count 5).
needle = struct.pack("<5h", 1, 2, 3, 4, 5)
pos = 0
while True:
    pos = RAM.find(needle, pos)
    if pos < 0:
        break
    rec = pos - 156
    mode, count = struct.unpack_from("<hh", RAM, rec + 168)
    rid, rtype = struct.unpack_from("<ii", RAM, rec)
    print(f"prereq list 1..5 at 0x{pos:08X} -> record 0x{rec:08X}: id={rid} type={rtype} mode={mode} count={count}")
    pos += 2

print("== callers of 0x00316800 (jal):")
target = 0x0C000000 | (0x00316800 >> 2)
for a in range(0x00100000, 0x00400000, 4):
    if word(a) == target:
        print(f"  0x{a:08X}: {dis(a)}")
print("== callers of 0x003165F0 (set status):")
target = 0x0C000000 | (0x003165F0 >> 2)
for a in range(0x00100000, 0x00400000, 4):
    if word(a) == target:
        print(f"  0x{a:08X}: {dis(a)}")

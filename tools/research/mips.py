"""Tiny MIPS (R5900 subset) disassembler + reference finder for the NFSU RAM snapshot."""
import pathlib, struct, sys

# RAM snapshot from tools/pine_memscan.py (not in the repository).
RAM = (pathlib.Path(__file__).resolve().parents[1] / "scans" / "set2.bin").read_bytes()
R = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
     "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]
I_OPS = {0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
         0x0F: "lui", 0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x28: "sb", 0x29: "sh",
         0x2B: "sw", 0x37: "ld", 0x3F: "sd", 0x19: "daddiu", 0x31: "lwc1", 0x39: "swc1", 0x1E: "lq", 0x1F: "sq"}
BR = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz", 0x14: "beql", 0x15: "bnel"}
SPECIAL = {0x00: "sll", 0x02: "srl", 0x03: "sra", 0x08: "jr", 0x09: "jalr", 0x21: "addu", 0x23: "subu",
           0x24: "and", 0x25: "or", 0x2A: "slt", 0x2B: "sltu", 0x2D: "daddu", 0x0A: "movz", 0x0B: "movn",
           0x18: "mult", 0x10: "mfhi", 0x12: "mflo"}


def word(addr):
    return struct.unpack_from("<I", RAM, addr)[0]


def dis(addr):
    w = word(addr)
    op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if w == 0:
        return "nop"
    if op == 0:
        fn = w & 0x3F
        name = SPECIAL.get(fn, f"special.{fn:#x}")
        if fn in (0, 2, 3):
            return f"{name} {R[rd]}, {R[rt]}, {(w >> 6) & 31}"
        if fn == 8:
            return f"jr {R[rs]}"
        return f"{name} {R[rd]}, {R[rs]}, {R[rt]}"
    if op in (2, 3):
        return f"{'j' if op == 2 else 'jal'} 0x{((w & 0x3FFFFFF) << 2) | (addr & 0xF0000000):08X}"
    if op in BR:
        return f"{BR[op]} {R[rs]}, {R[rt]}, 0x{addr + 4 + simm * 4:08X}"
    if op == 1:
        return f"regimm.{rt} {R[rs]}, 0x{addr + 4 + simm * 4:08X}"
    if op in I_OPS:
        n = I_OPS[op]
        if n == "lui":
            return f"lui {R[rt]}, 0x{imm:04X}"
        if op >= 0x1E and n not in ("daddiu",):
            return f"{n} {R[rt]}, {simm}({R[rs]})"
        return f"{n} {R[rt]}, {R[rs]}, {simm}"
    return f".word 0x{w:08X}"


def find_refs(target, lo=0x00100000, hi=0x00400000, window=0x40):
    """Find lui X,hi / (addiu|load|store) Y, lo(X) pairs that compute addresses in [target, target+window)."""
    hits = []
    for a in range(lo, hi, 4):
        w = word(a)
        if w >> 26 != 0x0F:
            continue
        reg, hi16 = (w >> 16) & 31, w & 0xFFFF
        for b in range(a + 4, min(a + 4 + 4 * 24, hi), 4):
            v = word(b)
            op = v >> 26
            if op in I_OPS and op != 0x0F and ((v >> 21) & 31) == reg:
                imm = v & 0xFFFF
                simm = imm - 0x10000 if imm & 0x8000 else imm
                full = ((hi16 << 16) + simm) & 0xFFFFFFFF
                if target <= full < target + window:
                    hits.append((a, b, full))
            if op == 0x0F and ((v >> 16) & 31) == reg:
                break
    return hits


if __name__ == "__main__":
    tgt = int(sys.argv[1], 0)
    win = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x80
    for a, b, full in find_refs(tgt, window=win):
        print(f"0x{b:08X}: {dis(b):40s} -> 0x{full:08X}   (lui at 0x{a:08X})")

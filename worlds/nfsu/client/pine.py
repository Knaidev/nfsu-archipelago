"""Client side of the PINE IPC protocol (PCSX2), used to read and write PS2 memory.

Based on the PINE client used by the Sly Cooper Archipelago world (worlds/sly1/pcsx2_interface/pine.py,
https://github.com/hoppel16/ArchipelagoBranchSly1), which is MIT licensed like Archipelago.
Protocol reference: https://github.com/GovanifY/pine

Changes for this project:
  * every request goes through one lock, so calls from several threads never interleave
    (PCSX2's PINE server can hang when it gets parallel/pipelined requests);
  * timeouts and broken sockets close the connection and raise ConnectionError, so the caller can
    simply reconnect;
  * batch reads/writes (several commands in one message) to keep the number of round trips low.

This module has no Archipelago imports, so tools/ can use it standalone.
"""
import os
import socket
import struct
import threading
from enum import IntEnum
from platform import system
from typing import Iterable, List, Optional, Sequence, Tuple

DEFAULT_SLOT = 28011


class IPCCommand(IntEnum):
    READ8 = 0x0
    READ16 = 0x1
    READ32 = 0x2
    READ64 = 0x3
    WRITE8 = 0x4
    WRITE16 = 0x5
    WRITE32 = 0x6
    WRITE64 = 0x7
    VERSION = 0x8
    SAVE_STATE = 0x9
    LOAD_STATE = 0xA
    TITLE = 0xB
    ID = 0xC
    UUID = 0xD
    GAME_VERSION = 0xE
    STATUS = 0xF


class EmulatorStatus(IntEnum):
    RUNNING = 0
    PAUSED = 1
    SHUTDOWN = 2


IPC_OK = 0x00
IPC_FAIL = 0xFF

_READ_CMD = {1: IPCCommand.READ8, 2: IPCCommand.READ16, 4: IPCCommand.READ32, 8: IPCCommand.READ64}
_WRITE_CMD = {1: IPCCommand.WRITE8, 2: IPCCommand.WRITE16, 4: IPCCommand.WRITE32, 8: IPCCommand.WRITE64}


class Pine:
    #: Maximum size of one request / one reply in bytes (PCSX2 limits).
    MAX_IPC_SIZE = 650000
    MAX_IPC_RETURN_SIZE = 450000

    def __init__(self, slot: int = DEFAULT_SLOT, timeout: float = 2.0) -> None:
        if not 0 < slot <= 65535:
            raise ValueError("PINE slot out of range")
        self.slot = slot
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ connection
    def _address(self):
        if system() == "Windows":
            return socket.AF_INET, ("127.0.0.1", self.slot)
        base = os.environ.get("XDG_RUNTIME_DIR" if system() == "Linux" else "TMPDIR", "/tmp")
        name = "pcsx2.sock" if self.slot == DEFAULT_SLOT else f"pcsx2.sock.{self.slot}"
        return socket.AF_UNIX, os.path.join(base, name)

    def connect(self) -> bool:
        with self._lock:
            if self._sock is not None:
                return True
            family, address = self._address()
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
            except OSError:
                sock.close()
                return False
            self._sock = sock
            return True

    def disconnect(self) -> None:
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                finally:
                    self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    # ------------------------------------------------------------------ transport
    def _transact(self, body: bytes) -> bytes:
        """Sends one message (without size prefix) and returns the reply payload after the result byte."""
        with self._lock:
            if self._sock is None and not self.connect():
                raise ConnectionError("PCSX2 (PINE) is not reachable. Is PINE enabled on slot %d?" % self.slot)
            message = struct.pack("<I", len(body) + 4) + body
            if len(message) > self.MAX_IPC_SIZE:
                raise ValueError("PINE request too large")
            try:
                self._sock.sendall(message)
                reply = self._recv_exact(4)
                size = struct.unpack("<I", reply)[0]
                if size < 5 or size > self.MAX_IPC_SIZE:
                    raise ConnectionError("Invalid PINE reply size %d" % size)
                rest = self._recv_exact(size - 4)
            except (OSError, ConnectionError) as e:
                # A timeout leaves the stream in an unknown state: always start over.
                self.disconnect()
                if isinstance(e, ConnectionError):
                    raise
                raise ConnectionError(f"Lost connection to PCSX2: {e}") from e
            if rest[0] == IPC_FAIL:
                raise ConnectionError("PCSX2 reported a failed PINE command (game not running?)")
            return rest[1:]

    def _recv_exact(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("PCSX2 closed the PINE connection")
            data += chunk
        return data

    # ------------------------------------------------------------------ memory
    def read(self, address: int, size: int) -> int:
        cmd = _READ_CMD[size]
        return int.from_bytes(self._transact(struct.pack("<BI", cmd, address))[:size], "little")

    def read8(self, address: int) -> int:
        return self.read(address, 1)

    def read16(self, address: int) -> int:
        return self.read(address, 2)

    def read32(self, address: int) -> int:
        return self.read(address, 4)

    def read64(self, address: int) -> int:
        return self.read(address, 8)

    def read_float(self, address: int) -> float:
        return struct.unpack("<f", self.read32(address).to_bytes(4, "little"))[0]

    def write(self, address: int, size: int, value: int) -> None:
        cmd = _WRITE_CMD[size]
        self._transact(struct.pack("<BI", cmd, address) + (value & ((1 << (8 * size)) - 1)).to_bytes(size, "little"))

    def write8(self, address: int, value: int) -> None:
        self.write(address, 1, value)

    def write16(self, address: int, value: int) -> None:
        self.write(address, 2, value)

    def write32(self, address: int, value: int) -> None:
        self.write(address, 4, value)

    def write64(self, address: int, value: int) -> None:
        self.write(address, 8, value)

    def write_float(self, address: int, value: float) -> None:
        self.write32(address, int.from_bytes(struct.pack("<f", value), "little"))

    def batch_read(self, requests: Sequence[Tuple[int, int]]) -> List[int]:
        """Reads several (address, size) pairs. Splits into as few messages as the size limits allow."""
        results: List[int] = []
        i = 0
        while i < len(requests):
            body = b""
            sizes: List[int] = []
            reply_len = 5
            while i < len(requests):
                address, size = requests[i]
                if len(body) + 9 > self.MAX_IPC_SIZE or reply_len + size > self.MAX_IPC_RETURN_SIZE:
                    break
                body += struct.pack("<BI", _READ_CMD[size], address)
                sizes.append(size)
                reply_len += size
                i += 1
            payload = self._transact(body)
            pos = 0
            for size in sizes:
                results.append(int.from_bytes(payload[pos:pos + size], "little"))
                pos += size
        return results

    def batch_write(self, writes: Iterable[Tuple[int, int, int]]) -> None:
        """Writes several (address, size, value) triples."""
        body = b""
        for address, size, value in writes:
            part = struct.pack("<BI", _WRITE_CMD[size], address) + \
                (value & ((1 << (8 * size)) - 1)).to_bytes(size, "little")
            if len(body) + len(part) + 4 > self.MAX_IPC_SIZE:
                self._transact(body)
                body = b""
            body += part
        if body:
            self._transact(body)

    def read_bytes(self, address: int, length: int) -> bytes:
        """Reads a memory range with batched 64-bit reads."""
        full, tail = divmod(length, 8)
        values = self.batch_read([(address + 8 * k, 8) for k in range(full)] +
                                 [(address + 8 * full + k, 1) for k in range(tail)])
        out = b"".join(v.to_bytes(8, "little") for v in values[:full])
        return out + bytes(values[full:])

    # ------------------------------------------------------------------ info
    def _read_string(self, cmd: IPCCommand) -> str:
        payload = self._transact(struct.pack("<B", cmd))
        length = struct.unpack("<I", payload[:4])[0]
        return payload[4:4 + length].split(b"\x00", 1)[0].decode("ascii", "replace")

    def game_id(self) -> str:
        return self._read_string(IPCCommand.ID)

    def game_title(self) -> str:
        return self._read_string(IPCCommand.TITLE)

    def status(self) -> EmulatorStatus:
        return EmulatorStatus(struct.unpack("<I", self._transact(struct.pack("<B", IPCCommand.STATUS))[:4])[0])

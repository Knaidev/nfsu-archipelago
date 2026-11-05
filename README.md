> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).

# Need for Speed: Underground – Archipelago

An [Archipelago](https://archipelago.gg) world and PCSX2 client for **Need for Speed: Underground** (PS2,
NTSC-U `SLUS-20811`). Race rewards become checks, and parts, cars and Bank come from the multiworld.

**Status: Alpha 0.1.** Everything listed below was tested in game, but a full run to the goal has not been
played yet. Expect bugs and please report them in the issues.

## Features

- **Checks** are the game's own race rewards (one per unlock in the "Race Victory Reward" popup, "Victory" for
  events without a reward). The popup shows the Archipelago item you found.
- **Items:** progressive performance parts, progressive visual parts per category, cars, Bank bonuses.
  The client patches the shop and the car lot so that only received parts and cars can be bought.
- **Progression:** four tiers of events, opened by reputation stars from received visual parts (star gates).
- **Goal:** win #111 "Wrath of Eddie" (needs time trials, the "Finale: #111" item and "Samantha's Big Tease"),
  or win a set number of events.
- **Death Link:** losing a race sends a death; a received death blows your engine ("Blown Engine").

Details: [game page](worlds/nfsu/docs/en_Need%20for%20Speed%20Underground.md) ·
[setup guide](worlds/nfsu/docs/setup_en.md) · example options in [`examples/`](examples).

## Installation

1. Install [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or newer.
2. Download `nfsu.apworld` from the [releases](../../releases) and double-click it.
3. Set up PCSX2 with PINE (slot 28011) and connect with **NFSU Client** – see the
   [setup guide](worlds/nfsu/docs/setup_en.md).

You need your own copy of the game. This project contains no game files.

## Not in this version

Traps, style point checks and the in-game "now playing" item banner exist only as unfinished code; their memory
addresses have not been found yet. Only the NTSC-U version of the game is supported.

## Development

- `worlds/nfsu/` – the world (`items.py`, `locations.py`, `options.py`, `logic.py`, `rules.py`, `world.py`),
  game data in `data/` (`addresses.py` holds every RAM address and code patch), the client in `client/`,
  tests in `test/`.
- `tools/build_apworld.py --archipelago <Archipelago source>` builds `build/nfsu.apworld`.
- `tools/pine_memscan.py` – RAM snapshots / search over PINE; `tools/research/` – data scrapers, MIPS disassembler.

Tests run with Archipelago's test runner from an Archipelago source checkout that contains `worlds/nfsu`:
`python -m pytest worlds/nfsu/test`.

## Credits

- Underground Mode event and reward data: [NFS Wiki](https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Underground_Mode).
- Need for Speed: Underground is a trademark of Electronic Arts. This is an unofficial fan project.

## License

[MIT](LICENSE)

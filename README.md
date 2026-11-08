> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).

# Need for Speed: Underground – Archipelago

An [Archipelago](https://archipelago.gg) world and PCSX2 client for **Need for Speed: Underground** (PS2,
NTSC-U `SLUS-20811`). Race rewards become checks, and parts, cars and Bank come from the multiworld.

**Status: Alpha 0.3.** Everything listed below was tested in game, but a full run to the goal has not been
played yet. Expect bugs and please report them in the issues.

## Features

- **Checks** are the game's own race rewards (one per unlock in the "Race Victory Reward" popup, "Victory" for
  events without a reward). The popup shows the Archipelago item you found.
- **Items:** progressive performance parts, progressive visual parts per category, cars, Event Packs, Bank bonuses.
  The client patches the shop and the car lot so that only received parts and cars can be bought.
- **Events as items:** #1–#5 are open from the start, all other events come in "Event Packs" whose contents
  the seed decides. Tournaments and the finale need reputation stars from received visual parts; optional
  star gates also lock whole tiers. The client fills the race map's 12 slots (`/nfsu events`, `/nfsu pin`).
- **Goal:** win #111 "Wrath of Eddie" (needs time trials, the "Finale: #111" item and "Samantha's Big Tease"),
  or win a set number of events.
- **Death Link:** losing a race sends a death; a received death blows your engine ("Blown Engine").
  Tournaments count as a whole: a lost round sends nothing, losing or leaving the tournament does.
- **First car:** with a random start car any car can be the first one; the client makes sure you can buy it.

Details: [game page](worlds/nfsu/docs/en_Need%20for%20Speed%20Underground.md) ·
[setup guide](worlds/nfsu/docs/setup_en.md).

## Quick start

You need your own copy of the game (NTSC-U `SLUS-20811`, as `.iso`). This project contains no game files.

1. Install [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or newer and
   [PCSX2](https://pcsx2.net/downloads) 2.x.
2. From the [releases page](../../releases) (newest release, *Assets*) download **`nfsu.apworld`** and
   **`nfsu_options.html`**. Double-click `nfsu.apworld` to install it (close the Archipelago Launcher first;
   a newer version replaces the old one).
3. **Create your YAML:** double-click `nfsu_options.html` – it opens in your browser (works offline). Enter your
   player name, pick a preset or options and click *Download YAML*.
4. **Enable PINE in PCSX2** (once): *Tools → Show Advanced Settings*, then *Settings → Advanced → PINE Settings*:
   tick *Enable*, slot **28011**.
5. Generate the game in the Archipelago Launcher (*Generate*), host it (upload the `.zip` on
   [archipelago.gg](https://archipelago.gg/uploads) or *Host* in the Launcher), start the game in PCSX2,
   open **NFSU Client** from the Launcher and connect. Start a new Underground Mode career.

Every step is explained in detail for first-time users in the
[setup guide](worlds/nfsu/docs/setup_en.md).

## Development

- `worlds/nfsu/` – the world (`items.py`, `locations.py`, `options.py`, `logic.py`, `rules.py`, `world.py`),
  game data in `data/` (`addresses.py` holds every RAM address and code patch), the client in `client/`,
  tests in `test/`.
- `tools/build_apworld.py --archipelago <Archipelago source>` builds `build/nfsu.apworld`.
- `tools/build_options_page.py --archipelago <Archipelago source>` builds `build/nfsu_options.html`, a stand-alone
  page to create a player YAML (generated from `options.py`; template `tools/options_page.html`).
- `tools/pine_memscan.py` – RAM snapshots / search over PINE; `tools/research/` – data scrapers, MIPS disassembler.

Tests run with Archipelago's test runner from an Archipelago source checkout that contains `worlds/nfsu`:
`python -m pytest worlds/nfsu/test`.

## Credits

- Underground Mode event and reward data: [NFS Wiki](https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Underground_Mode).
- Need for Speed: Underground is a trademark of Electronic Arts. This is an unofficial fan project.

## License

[MIT](LICENSE)

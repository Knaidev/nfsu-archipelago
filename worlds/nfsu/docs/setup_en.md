# Need for Speed: Underground – Setup Guide

> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).
>
> **Alpha 0.3** – expect bugs. Please report them on the project's GitHub page.

## Required software

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or newer
- `nfsu.apworld` from this project's releases
- [PCSX2](https://pcsx2.net/) 2.x with PINE support
- Your own NTSC-U copy of Need for Speed: Underground (PS2, SLUS-20811). Other versions are not supported.

## Installing the apworld

Double-click `nfsu.apworld`, or copy it into the `custom_worlds` folder of your Archipelago installation.

## Setting up PCSX2

1. In PCSX2, enable **Tools → Show Advanced Settings**.
2. Go to **Settings → Advanced → PINE Settings**, enable PINE and keep the slot at **28011**.

## Creating your options file

The easiest way: open **`nfsu_options.html`** from the release in your browser, pick your options and click
**Download YAML** (it works offline; option descriptions are behind the **?** buttons).

Or, in the Archipelago Launcher, choose **Generate Template Options**, then edit
`Need for Speed Underground.yaml`. Example files are in the project's `examples/` folder.

## Connecting

1. Start PCSX2 and load the game. Use a fresh Underground Mode profile for a new seed.
2. Start **NFSU Client** from the Archipelago Launcher.
3. Connect to the room (`/connect address:port`).

The client patches the game in memory while it runs (event availability, shop, car lot). When you close the
client, the game goes back to its normal unlock rules.

## Client commands

- `/nfsu` – stars, open tiers, time trials, received parts and cars
- `/nfsu events` – received Event Packs and all unlocked events, with the ones on the race map marked
- `/nfsu pin <number>` / `/nfsu unpin <number>` – keep an event on the race map (it shows 12 at most); reopen the
  race map afterwards
- `/pcsx2` – show the PCSX2 connection and reconnect
- `/deathlink on|off` – switch Death Link for this session (overrides your options file)

## Known limitations

- The count of received items is stored on the Archipelago server, not in your save. If you load an older save
  or savestate, Bank that was already paid out is not paid again.
- Only one program can use PINE at a time; close other PINE tools while the client runs.

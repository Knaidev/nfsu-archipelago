# Need for Speed: Underground – Setup Guide

> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).
>
> **Alpha 0.3** – expect bugs. Please report them on the project's GitHub page.

## Required software

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or newer
- From this project's [releases page](https://github.com/Knaidev/nfsu-archipelago/releases) (newest release,
  section *Assets*): `nfsu.apworld` and `nfsu_options.html`
- [PCSX2](https://pcsx2.net/downloads) 2.x and a PS2 BIOS dumped from your own console (PCSX2's first-start
  wizard asks for it)
- Your own NTSC-U copy of Need for Speed: Underground (PS2, SLUS-20811) as an `.iso`. Other versions are not
  supported.

## 1. Installing the apworld

1. Close the Archipelago Launcher if it is open.
2. Double-click `nfsu.apworld`. Archipelago copies it into the `custom_worlds` folder of your installation
   (Windows: `C:\ProgramData\Archipelago\custom_worlds`). A newer version simply replaces the old file.
   If double-clicking does not work, copy the file into that folder yourself.
3. Start the Launcher again. You should now see **NFSU Client** in its list.

## 2. Setting up PCSX2 (PINE)

The client talks to PCSX2 over **PINE**, PCSX2's built-in interface for tools. It is off by default and its
settings page is hidden, so you switch it on once (menu names as in PCSX2's English interface):

1. Start PCSX2 and finish the first-start wizard (BIOS, game folder).
2. In the menu bar open **Tools** and click **Show Advanced Settings**. If a warning appears, confirm it.
3. Open **Settings** and choose **Advanced** (in the menu or in the list on the left of the settings window).
4. Scroll down to **PINE Settings**, tick **Enable** and leave **Slot** at **28011**.
5. Close the settings window. The setting is saved; you only do this once. If the client later cannot find PCSX2,
   restart PCSX2.

You can switch *Show Advanced Settings* off again afterwards – PINE stays enabled.

## 3. Creating your options file (YAML)

**YAML creator page:** download [`nfsu_options.html`](https://github.com/Knaidev/nfsu-archipelago/releases)
from the newest release and double-click it – it opens in your web browser and works offline, nothing is uploaded.

1. Enter your **player name** (this is your slot name for connecting later).
2. Pick a **preset** (Relaxed / Standard / Hardcore) or set the options yourself. Options that differ from the
   defaults are marked; the **?** buttons explain each option.
3. Click **Download YAML**.

Alternative: in the Archipelago Launcher choose **Generate Template Options** and edit
`Need for Speed Underground.yaml` in a text editor. Example files are in the project's
[`examples/`](https://github.com/Knaidev/nfsu-archipelago/tree/main/examples) folder.

## 4. Generating and hosting a game

If someone else hosts the multiworld, send them your YAML and skip to step 5.

1. Put your YAML (and the YAMLs of everyone else) into the `Players` folder of your Archipelago installation
   (Windows: `C:\ProgramData\Archipelago\Players`). Remove YAMLs you do not want to play with.
2. In the Launcher click **Generate**. The game is written as a `.zip` into the `output` folder.
3. Host it, either:
   - **on archipelago.gg** (easiest, also for playing with others): open
     [archipelago.gg/uploads](https://archipelago.gg/uploads), upload the `.zip` and click **Create New Room**.
     The room page shows the address, e.g. `archipelago.gg:49802`.
   - **on your own PC:** in the Launcher click **Host** and choose the `.zip`. The address is normally
     `localhost:38281`; others connect to your IP address and that port.

## 5. Connecting

1. Start PCSX2 and boot the game.
2. Start **NFSU Client** from the Archipelago Launcher. Its log shows `Connected to PCSX2 (SLUS-20811)` once it
   finds the game (`/pcsx2` shows the connection state).
3. Enter the server address (e.g. `archipelago.gg:49802` or `localhost:38281`) at the top and click **Connect**, then enter your player name.
4. For a new game start a **new Underground Mode career**. If the game loads an old profile from the memory card,
   create a new profile instead.

After the prologue you choose your first car. While you choose it, the client shows 500,000 Bank so any car (also
an expensive random start car) can be bought; after the purchase the Bank is set to what the game's 10,000 would have
left (0 if the car costs more). Starting Bank and Bank items are paid after that (so a new career does not lose
them).

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

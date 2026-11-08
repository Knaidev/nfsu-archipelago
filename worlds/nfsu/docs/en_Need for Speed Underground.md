# Need for Speed: Underground

> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).
>
> **Alpha 0.3.** Race wins, the reward popups, Event Packs and the race map, the shop, cars, Bank and Death Link
> work with the PCSX2 client. A full run to the goal has not been played yet.

## What does randomization do to this game?

The checks are the game's own **race rewards**: every part, car or course an event unlocks in the original
game is one check, and the "Race Victory Reward" popup shows the Archipelago item you found there instead.
Events without a reward have one "Victory" check. The difficulty you race on does not matter.

Events that let you **choose** a reward (the seven time trials and #110) have no checks – you keep their
original unique part. Time trials still count for the finale.

Performance parts, visual parts and cars no longer unlock by winning events. They come from the multiworld
instead: each item opens the next level of its category in the shop (or a car at the car lot). You still buy
parts and cars with Bank.

**Events are items, too.** #1–#5 are open from the start; every other event (#6–#110) is in one
**Event Pack**. There is one pack per original event set, but the seed decides which events are in it – one
pack can hold e.g. #8, #19, #43, #44 and #56. You start with a few packs (option *Starting Event Packs*); the
client lists every new pack in its log. With *Event Packs* off, all events are open as in Alpha 0.1.

**Reputation stars** come from the visual part items you received (full stars, rounded down, using the game's
star value of each level). Tournaments still need their original stars in game (e.g. #30 needs 2) and the
finale needs 5. With the option *Star Gates* on, the events are also grouped into four tiers (1–29, 30–65,
66–90, 91–110) that open with 2, 3 and 4 stars. Logic also expects better performance parts for later tiers.

**The race map shows at most 12 open events** (a limit of the game). The client fills these slots: events you
pinned first, then events you can enter, then tournaments that still need stars. Won events free their slot.
Use `/nfsu events` to see all unlocked events and `/nfsu pin <number>` to put one on the map.

## What is the goal?

By default you win **#111 "Wrath of Eddie"**. It unlocks when you have:
- won the required number of time trials (default: all 7),
- received the **Finale: #111** item,
- received **Samantha's Big Tease**,
- 5 reputation stars.

Alternatively, the goal can be to win a set number of events.

## What items are there?

- Progressive performance parts (9 categories × 3 levels)
- Progressive visual parts per category (bumpers, skirts, spoiler, hood, roof scoop, rims, neon, muffler tip,
  window tint, lights, paint, decals – Level 2, then 3)
- Cars: the 15 cars that normally unlock through events; with **Starting Car** random_starter / random_car you
  start with one random car and all others are items
- Event Packs (see above)
- Bank bonuses

## Death Link

With Death Link on, losing a race (or blowing your engine in a drag race) sends a death. A death you receive
while racing blows your engine ("Blown Engine") and you are out of that race. Deaths received outside a race
are ignored. Death Link Amnesty lets you lose a few races before a death is sent.

## Which version of the game is supported?

Only the PS2 version, NTSC-U (SLUS-20811). The Underground Mode data comes from the
[NFS Wiki](https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Underground_Mode).
You need your own copy of the game. No game files are distributed.

# Need for Speed: Underground

> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).
>
> **Alpha 0.1.** Race wins, the reward popups, event availability, the shop, cars, Bank and Death Link work with
> the PCSX2 client. A full run to the goal has not been played yet.

## What does randomization do to this game?

The checks are the game's own **race rewards**: every part, car or course an event unlocks in the original
game is one check, and the "Race Victory Reward" popup shows the Archipelago item you found there instead.
Events without a reward have one "Victory" check. The difficulty you race on does not matter.

Events that let you **choose** a reward (the seven time trials and #110) have no checks – you keep their
original unique part. Time trials still count for the finale.

Performance parts, visual parts and cars no longer unlock by winning events. They come from the multiworld
instead: each item opens the next level of its category in the shop (or a car at the car lot). You still buy
parts and cars with Bank.

Events are grouped into four tiers (1–29, 30–65, 66–90, 91–110). A tier opens when you have enough
**reputation stars** from the visual part items you received (full stars, rounded down, using the game's star
value of each level): Tier 2 needs 2 stars, Tier 3 needs 3, Tier 4 needs 4 and the finale 5.
Logic also expects better performance parts for later tiers.

## What is the goal?

By default you win **#111 "Wrath of Eddie"**. It unlocks when you have:
- won the required number of time trials (default: all 7),
- received the **Finale: #111** item,
- received **Samantha's Big Tease**,
- 5 reputation stars (with star gates on).

Alternatively, the goal can be to win a set number of events.

## What items are there?

- Progressive performance parts (9 categories × 3 levels)
- Progressive visual parts per category (bumpers, skirts, spoiler, hood, roof scoop, rims, neon, muffler tip,
  window tint, lights, paint, decals – Level 2, then 3)
- Cars: the 15 cars that normally unlock through events; with **Starting Car** random_starter / random_car you
  start with one random car and all others are items
- Bank bonuses

## Death Link

With Death Link on, losing a race (or blowing your engine in a drag race) sends a death. A death you receive
while racing blows your engine ("Blown Engine") and you are out of that race. Deaths received outside a race
are ignored. Death Link Amnesty lets you lose a few races before a death is sent.

## Which version of the game is supported?

Only the PS2 version, NTSC-U (SLUS-20811). The Underground Mode data comes from the
[NFS Wiki](https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Underground_Mode).
You need your own copy of the game. No game files are distributed.

# Need for Speed: Underground

> **AI notice: the code of this project is not handwritten.** It was written by AI (Claude by Anthropic).
>
> **Version 0.4.** Race wins, the reward popups, Event Packs and the race map, the shop, cars, Bank and Death Link
> work with the PCSX2 client.

## What does randomization do to this game?

The checks are the game's own **race rewards**: every part, car or course an event unlocks in the original
game is one check, and the "Race Victory Reward" popup shows the Archipelago item you found there instead.
Events without a reward have one "Victory" check. The difficulty you race on does not matter.
A few events show one popup more than they have checks (the game also unlocks a track there); that popup says
"No Archipelago item here.".

Events that let you **choose** a reward (the seven time trials and #110) have no checks – you keep their
original unique part. Time trials still count for the finale.

Performance parts, visual parts and cars no longer unlock by winning events. They come from the multiworld
instead: each item opens the next level of its category in the shop (or a car at the car lot). You still buy
parts and cars with Bank.

**Events are items, too.** #1–#5 are open from the start; every other event (#6–#110) is in one
**Event Pack**. There is one pack per original event set, but the seed decides which events are in it – one
pack can hold e.g. #8, #19, #43, #44 and #56. You start with a few packs (option *Starting Event Packs*); the
client lists every new pack in its log. With *Event Packs* off, all events are open from the start.

**Reputation stars** come from the visual part items you received (full stars, rounded down, using the game's
star value of each level). Tournaments still need their original stars in game (e.g. #30 needs 2) and the
finale needs 5. With the option *Star Gates* on, the events are also grouped into four tiers (1–29, 30–65,
66–90, 91–110) that open with 2, 3 and 4 stars. Logic also expects better performance parts for later tiers.

**Tournaments need everything you have.** A tournament is several races in a row against strong opponents, and
you have to win it as a whole. Before you enter one, buy and install every performance upgrade you have
received so far – with fewer upgrades you will usually not win it, even if the event is open.

**The race map shows at most 12 open events** (a limit of the game). The client fills these slots: events you
pinned first, then events you can enter, then tournaments that still need stars. Won events free their slot.
Use `/nfsu events` to see all unlocked events and `/nfsu pin <number>` to put one on the map.

## What is the goal?

By default you win the finale, **"Wrath of Eddie"** (the game numbers it #112; this project and the item
"Finale: #111" use the wiki's number). It unlocks when you have:
- received the **Finale: #111** item,
- received **Samantha's Big Tease**,
- 5 reputation stars,
- won the required number of time trials (option *Time Trials Required*, default 0, up to all 7).

Alternatively, the goal can be to win a set number of events.

## What items are there?

- Progressive performance parts (9 categories × 3 levels)
- Progressive visual parts per category (bumpers, skirts, spoiler, hood, roof scoop, rims, neon, muffler tip,
  window tint, lights, paint, decals – Level 2, then 3)
- Cars: the 15 cars that normally unlock through events; with **Starting Car** random_starter / random_car you
  start with one random car and all others are items
- Event Packs (see above)
- Bank bonuses. By default races also pay their normal Bank. With *Vanilla Bank Rewards* off, races pay nothing
  and all Bank comes from these items: you start with 0 Bank (plus *Starting Bank*), and the options *Large
  Bank Bonuses* (every Bank item is 7,000) and *Early Bank Bonuses* (up to two 2,000 items on your own starting
  events) keep the run from stalling.

## Death Link

With Death Link on, losing a race (or blowing your engine in a drag race) sends a death. A death you receive
while racing blows your engine ("Blown Engine") and you are out of that race. Deaths received outside a race
are ignored. Death Link Amnesty lets you lose a few races before a death is sent.

Tournaments count as a whole: a lost round sends nothing. A death is sent when you lose or leave the
tournament – at the moment you go back to the race map, not on the results screen ("Restart Tournament" on that
screen sends none).

## Which version of the game is supported?

Only the PS2 version, NTSC-U (SLUS-20811). The Underground Mode data comes from the
[NFS Wiki](https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Underground_Mode).
You need your own copy of the game. No game files are distributed.

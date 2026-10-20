# 0023 — The shop: every item has an effect, none holds back practice

Date: 2026-10-20 · Status: accepted (amends the SPEC §18.2 "Spent on" column)

## Context

Coins came from missions, lessons and streaks, but the shop sold six items that did nothing after purchase, and the
app had no shop screen. The founder asked for the shop to work and left the choice to us.

The SPEC lists flat and avatar upgrades, cafés, flights between cities, NPC gifts and extra accent voices. One rule
holds for all of them: nothing purchasable may skip learning or assessment.

## Decision

The shop sells four items. Each one takes effect at once:

| Item | Coins | Effect |
| --- | --- | --- |
| `streak_freeze` | 50 | Covers one missed day once the week's free freeze is used. A learner can hold 2 spare freezes. A used freeze is written to the ledger (`freeze_used`, 0 coins, keyed by the date), so it is spent only once and that day stays covered. |
| `cafe_visit` | 30 | Held in `world_states.inventory` until the next new story day. The planner then adds one extra mission and makes sure the day includes the café; if the café is already on the route, the extra mission goes elsewhere. The purchase is refused if no café is open to the learner. |
| `npc_gift` | 60 | Only for a character the learner has spoken with in the story, at most once per character per day. The character's warmth rises by 0.2 and a story flag records the gift, so story beats and later scenes can reflect it. |
| `flat_upgrade` | 400 | Up to 3 upgrades. Each adds a décor layer (`content/art/decor/flat_N.svg`: a plant; a rug and lamp; shelves and a picture) to the learner's home, on the map and in home scenes. |

Every purchase is checked before any coins are taken, so a refused purchase costs nothing.

Not sold, and why:

- **Extra accent voices:** hearing many accents is exam practice (IELTS listening uses several). Putting it behind
  coins would hold back learning. Accent variety belongs in content for every learner.
- **Flights between cities:** each city is opened by the learner's exam goal, so a flight has nothing left to unlock.
- **Avatar items:** learners have no avatar to dress.

Any of these can come back once there is something real for it to change.

## Found on the way: ledger keys were global

`ledger.idempotency_key` was unique across all learners. The night pass pays the day's streak reward with the key
`streak:<day>`, so only the first learner whose night ran that day was paid; everyone else was silently refused.

Migration 0004 makes the key unique per learner, on `(user_id, idempotency_key)`. A test now pays two learners the
same day's streak reward.

## Evidence

- `packages/economy/tests/test_economy.py`: a bought freeze covers the second missed day in a week, and is spent once.
- `services/api/tests/test_phase2_to_5_api.py`:
  - freezes stop at 2;
  - Today reports spare freezes;
  - a café visit is held in the inventory;
  - a gift needs a met character, warms them and is limited to one per day;
  - the balance is right after each purchase;
  - the flat décor shows in the world view;
  - streak keys are per learner.
- `services/graphs/tests/test_phase2_graphs.py`: on every day of the rotation, a café visit adds exactly one mission,
  the day includes the café, and the visit is used up.

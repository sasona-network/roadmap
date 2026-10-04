# Part 5, steps 2 and 3: members, drawn readers and challenges on devnet

Four memberships took stakes, a round drew which of them reads each service, and two of the readings were challenged: one answered, and one that cannot be.

## What was built

| Instruction | What it does |
|---|---|
| `join_members` | Locks one stake, 10,000 coins on devnet, as a membership in the next seat |
| `ask_to_leave`, `leave` | Leaves the roster at once; the stake comes back after 45 days |
| `commit_reading` | Now refuses anyone but the member whose seat was drawn for the service |
| `challenge` | Challenges a reading within 30 days, for a 0.1 SOL bond |
| `open_evidence`, `write_evidence`, `answer_challenge` | The member puts the reply on chain, and answers with the nonce |
| `uphold_challenge` | After 7 days with no answer that held: the stake is taken |

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/ea754dbd699c8860789cfa36064663cc616b0323).

> **Temporary.** The stake, the bond and the challenger's tenth are devnet figures. The stakes taken are held with no way out until chargebacks are on chain (part 7).

## The memberships

Two keys hold two memberships each, seats 1 to 4. The round was committed after all four sat down.

## The round

The list is [`list.txt`](list.txt), three services. The round drew all three, and drew a seat for each:

| Reading | Service | Read by | Verdict |
|---|---|---|---|
| [`honest`](readings/honest) | `https://sandbox.example.net/run/rust` | membership 2 | delivered |
| [`canned`](readings/canned) | `https://data.example.com/prices` | membership 2 | wrong answer |
| [`false`](readings/false) | `https://search.example.org/query` | membership 3 | recorded as delivered, falsely |

As before, the services do not exist and each request went to a stand-in.

`false` is false on purpose, to show a challenge taking a stake. It was taken with [`false_reading.py`](false_reading.py): it does what the reader does, except that it records `delivered` whatever the reply says. Its folder holds the reply as received, and the verdict rule gives `wrong answer` on it.

## The challenges

- **`honest` was challenged and answered.** Its member put the 43-byte reply on chain, and it hashes to what the reading recorded and gives `delivered` for its nonce. The bond went to the member, and the reply is sealed.
- **`false` was challenged and cannot be answered.** Its member put their own reply on chain and tried to answer. The program refused: the verdict rule on that reply does not give the recorded verdict. The answer window closes on 11 October 2026. After that, anyone can uphold it, and the membership loses its stake.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It checks:

- **The roster:** no gaps, every seated membership is active and knows its seat, and the stakes vault holds every stake still owed.
- **The round:**
  - it was drawn from the seed committed
  - the draw re-runs to the same picks
  - its roster had the seats recorded
- **Each reading:**
  - the question, the nonce and the reply, as in part 3
  - it was taken by a member, with that member's key
  - it is the membership the draw gives. That is re-run from today's roster, which has not changed since the round.
- **The answered challenge:** the reply on chain is sealed, hashes to what was recorded, and gives the recorded verdict.
- **The open challenge:** the member's own reply gives another verdict, so no answer can hold. Once it is upheld, the reading no longer counts and the membership has lost its stake.

Swapping one reply for another makes it fail, and so does changing one line of the list. Both were tried.

## How it was tested

- **167 tests** on the compiled program:
  - 21 for members, 23 for challenges, and the rest from earlier parts, now read by drawn members
  - every attack the reviews found, as a regression test
- **The tests now start on today's clock and at slot 1,** as a chain does. Before, a reveal time that was never recorded looked the same as one just recorded.
- **57 deliberate breakages of the members and challenges code.** The tests catch every one.
  - Three got through at first. Two were checks that could never fail, because another check came first, and they were removed. The third was the clock above.
- **Three rounds of independent review,** set out in [the spec step](../part-5-spec).

# Part 3, steps 2 and 3: readings on chain, and anyone can re-check them

Two services that the [part 2 round](../part-2-draw) drew have been tested on devnet. Their questions were fixed on chain before they were called.

## What was built

| Instruction | What it does |
|---|---|
| `commit_reading` | Before calling a drawn service, records the hash of the question for it |
| `reveal_reading` | After the call, reveals the nonce, the reply's hash and the verdict. The program builds the question from the nonce itself and refuses unless it is the one committed |
| `mark_lapsed` | A reading not revealed within about an hour can only be marked lapsed, in public |

A nonce belongs to the reading that committed to it earliest. A service sees the nonce when it is called, which is after the honest reading was committed. So it can copy the nonce into a reading of its own, but if it does, the honest reading takes the nonce back.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/e31f6b38e846097053c2a9f31983cd947ed1f729), and the reader in [`sasona-node`](https://github.com/sasona-network/sasona-node).

> **Temporary.** For now the round's opener takes its readings. Members take that over when they come on chain in part 5.

## The two readings

The services on the devnet test list do not exist. Each request went to a stand-in from `sasona-node` instead, and the reader recorded where it sent it.

| | Service, as drawn | Stand-in | Verdict |
|---|---|---|---|
| [`honest`](readings/honest) | `https://sandbox.example.net/run/rust` | answers what the code prints | delivered |
| [`canned`](readings/canned) | `https://data.example.com/prices` | the same fixed reply to everything | wrong answer |

Each folder holds the question's exact bytes, the reply's exact bytes, and both transactions.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. For each reading it checks:

- the service is, byte for byte, one of the round's picks
- the question shown is the fair one for its nonce, and hashes to what was committed before the call
- the nonce belongs to this reading
- the reply shown hashes to what was recorded, and the verdict rule on it gives the recorded verdict

Swapping one reply for the other makes it fail; that was tried.

## What is still trusted

The member's word, as [sasona-protocol 2.6](https://github.com/sasona-network/sasona-protocol/blob/a89850c201887549c6bef21a2b3de72d980ae3bb/SPEC.md) says. The member holds the reply and the service does not sign it, so a member could record a reply they made up. Second readings by other members (part 4), and stakes members lose for false readings (part 5), are what make that costly.

## How it was tested

- 111 tests on the compiled program, 16 of them for readings. They include:
  - the program building every question in the protocol's test values
  - a changed question, or another nonce, refused
  - the same nonce used twice, in the same slot or later
  - a reveal in the commit's slot, at the end of the window and after it
  - lapsing, the reader check, and the drawn-round check
  - a service URL that doesn't match its hash
  - the copied-nonce attack, as a regression test
- 15 deliberate breakages in the readings code. The tests catch all 15.
- An independent review found that a service could copy the nonce it was sent into a reading of its own, reveal it first, and make the honest reading impossible to reveal, so the reader would look like the one who backed out. The earliest-commitment rule closes that, and the test above covers it.

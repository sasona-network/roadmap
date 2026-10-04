# Part 6, steps 2 and 3: quotes on devnet, and a ranking anyone can rebuild

The members who read the part 5 round quoted what they would charge to insure purchases from those services. The ranking below is rebuilt from the chain by [`verify.py`](verify.py), not taken from us.

## What was built

| Instruction | What it does |
|---|---|
| `set_quote` | The member who took a reading sets, changes or withdraws a rate in basis points on it. Refused unless the reading was revealed, says `delivered`, is no more than 30 days old, and the member is still active |

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/f527231b5ce5882cce8a98fcd37ea923af0894f4).

## The quotes

| Service | Reading | Quote |
|---|---|---|
| `https://sandbox.example.net/run/rust` | the honest reading from [part 5](../part-5-members) | 150 bps |
| `https://search.example.org/query` | the false reading from part 5 | 40 bps |
| `https://data.example.com/prices` | a reading that found it giving the wrong answer | refused: the program will not insure a service that did not deliver |

## The ranking

1. `https://search.example.org/query`, 40 bps
2. `https://sandbox.example.net/run/rust`, 150 bps

`https://data.example.com/prices` is not listed: no quote stands on it.

Search ranks first on a reading recorded falsely, on purpose. This is the weakness section 6.4 states: until purchases are covered, a quote costs nothing to give, so a member can rank a service high on a reading of their own. The challenge from part 5 is what corrects it here. Once its answer window closes on 11 October and it is upheld, that reading stops counting, no quote stands on search, and it leaves the list. The script knows both states and checks the one the chain is in.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It reads every reading, nonce record, membership and quote the program holds, and the published lists of the rounds in these proofs. A reading counts only if:

- it was revealed
- its nonce's record names it
- its service is one of its round's picks

It then ranks the services by sasona-protocol section 6, at the moment the ranking was published, and compares the result with the ranking above.

Two limits. A reading counts here only if its round's list is one of those published in these proofs; a reading in any other round is left out. And the ranking is for the moment it was published, using what the accounts say now: a reading upheld false since, or a member who has left since, changes it.

Changing one line of a round's list makes its readings stop counting, and the ranking no longer matches. That was tried.

## How it was tested

- **177 tests** on the compiled program, 10 of them for quotes.
- **12 deliberate breakages of the quote code.** The tests catch all 12.
- **Four rounds of independent review,** set out in [the spec step](../part-6-spec).

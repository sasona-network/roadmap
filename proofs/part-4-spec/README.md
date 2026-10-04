# Part 4, step 1: pairs, written down

How a service gets tested a second time, and what the two readings together can and cannot say.

## What was built

[`sasona-protocol` version 0.4.0](https://github.com/sasona-network/sasona-protocol/blob/86fb6cc081e64d5f2ab45674d2b251a52caa6a15/SPEC.md), section 3:

- **Which readings are re-read.** A re-read round is an ordinary round whose list is services that already have a reading, so the services are drawn. The share drawn and the share actually re-read are two numbers, and the spec forbids reporting the first as the second.
- **Which earlier reading a second one is set against.** Not the second reader's choice. It is the latest reading of that service that counts, revealed before the re-read round was committed. Ties are broken by commit slot, then identifier.
- **When a second reading counts.** Same service, byte for byte. A different round. A different reader.
- **What a pair settles.** `works_now` if the second delivered. `false_or_decayed` if the first delivered and the second did not. `agreed_fails` if neither did.
- **What it does not.** `false_or_decayed` is not a finding that the first reading was false. A service that worked in September can stop in November with nobody lying. A different key is not a different person until members stake (part 5).

## Check it yourself

[`vectors/pair.json`](https://github.com/sasona-network/sasona-protocol/blob/86fb6cc081e64d5f2ab45674d2b251a52caa6a15/vectors/pair.json) holds all 9 pairs of verdicts with their outcomes, 7 cases of when a second reading counts, and 7 cases of which reading is the latest. The Python and the Rust implementation match all of it.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review read the program against this section, twice. It found:

- **The second reader could name any earlier reading** of the service, and so pick the verdict to contradict. The first reading is now fixed by the rule above, and the program refuses one revealed after the re-read round was committed.
- **"Latest" had no tie-break,** so two checkers could disagree about the same pair. It has one now, with test values.
- **A reading that lost its nonce could have been the latest.** Only readings that count are candidates.
- **The opener still picks the moment a re-read round opens,** and so which reading is the latest then. That is not fixed by a rule in this version. 3.4 says so, and part 5 is where members are drawn to readings.

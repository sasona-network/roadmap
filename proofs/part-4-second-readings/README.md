# Part 4, steps 2 and 3: second readings on devnet

The two services read in [part 3](../part-3-readings) were read again, by a different key, in a re-read round. Each pair's outcome is recorded on chain.

## What was built

| Instruction | What it does |
|---|---|
| `commit_second_reading` | Commits a reading in a re-read round that names the first reading it re-tests. Refused unless the first was revealed before the round was committed, is of the same service, and was read by someone else |
| `settle_pair` | Once the second is revealed, records the outcome from the two verdicts. Anyone can call it |

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/8b6ccbad40e4bcec8f6fbe96846e9a0b6a1fb800), and `--first` in the reader in [`sasona-node`](https://github.com/sasona-network/sasona-node).

## The round

The list is [`list.txt`](list.txt): the two services with a reading. A round over it drew both. It was opened by `CFFSXFb3…`, not by `CCsLKV9y…`, which took the first readings.

## The two pairs

As in part 3, the services do not exist, and each request went to a stand-in.

| | Service | First reading | Second reading | Outcome |
|---|---|---|---|---|
| [`decayed`](pairs/decayed) | `https://sandbox.example.net/run/rust` | delivered | wrong answer | `false_or_decayed` |
| [`recovered`](pairs/recovered) | `https://data.example.com/prices` | wrong answer | delivered | `works_now` |

`decayed` is the case the protocol is careful about. The service passed, then failed. That does not say which reading was wrong, or whether either was. A service can stop working with nobody lying, and this outcome is never reported as a false reading.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It rebuilds the draw from `list.txt` and the chain, then for each pair checks:

- the second reading, the same way part 3 checks a reading: the question, the nonce, the reply and the verdict
- that the two readings are of the same service, by different readers
- that the first was revealed before the re-read round was committed
- that the first is the latest reading of the service that counts, out of every reading of it on chain
- that the outcome on chain follows from the two verdicts, and names these two readings

Swapping in the other pair's reply makes it fail, and so does naming the other service's first reading. Both were tried.

## What is still trusted

- **Each reading is its reader's word,** as in part 3. A pair is two readers' word.
- **Two keys are not two people.** Nothing here stops one person reading with both. Part 5 puts stakes behind readings.
- **The opener chooses when a re-read round opens.** Which reading gets re-read is fixed by a rule. When it happens is not, yet.

## How it was tested

- 123 tests on the compiled program, 12 of them for pairs. They include:
  - all 9 pairs of verdicts, 3 of them settled on chain
  - the first reader checking themselves
  - another service
  - the first's own round
  - a first that was never revealed
  - a re-read round committed before the first was revealed, and in the same slot
  - a second settled twice, before it was revealed, after it lapsed, and against a different first reading
- 24 deliberate breakages in the readings and pairs code. The tests catch all 24.
- An independent review, whose findings are in [the spec step](../part-4-spec).

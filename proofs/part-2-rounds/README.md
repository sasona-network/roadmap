# Part 2, step 2: rounds on chain

The contract now holds draws: what a round committed to, and the seed it was drawn with.

## What was built

| Instruction | What it does |
|---|---|
| `open_round` | Commits to a list of services by its fingerprint and size, how many to pick, and the hash of a secret seed. The opener puts up a 0.1 SOL bond. The round's address comes from the list's fingerprint, so a list can be drawn once. |
| `reveal_round` | Takes the seed, checks it against the commitment, and mixes it with the hash of the earliest slot at least 32 slots after the commitment, read from Solana's `SlotHashes`. The bond goes back to the opener. |
| `mark_withheld` | Once that slot hash has left `SlotHashes`, a few minutes later, a round still not revealed can only be marked withheld. It can never be drawn, and its bond stays locked for good. |

The rule that turns the final seed into the services picked is [`sasona-protocol` 0.2.0](https://github.com/sasona-network/sasona-protocol/blob/688da27a605492308daf14884d12e68347fd4bf8/SPEC.md). A test pins the program to it: given the protocol's test seed and entropy, the program produces the protocol's final seed.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/ae4b3d71c7fd385aeffd5b0536ca658404ef21c2)

## On devnet

| | |
|---|---|
| Upgrade | [`cnqXTcRx…`](https://explorer.solana.com/tx/cnqXTcRxq5WRgwFV4G9hzgh53AoLptTzD1fBJwkCEfv26fpvNw3NYgAU7tuhzC9oydqSs6GEZEVzVbbzddKHca8?cluster=devnet) |
| A round opened | [`646xCs8z…`](https://explorer.solana.com/tx/646xCs8zbZw87y1dmkJE9Qnuig98yo9Few8b48Mzo1Z3cAsYrKfFPRMXF1Aqmi9BgSKXNnuZsDXEX6BApHsKTEnR?cluster=devnet) |
| …and revealed, reading the real `SlotHashes` | [`2DrRSWHT…`](https://explorer.solana.com/tx/2DrRSWHT4H16kB7MhrN847Dj1142QUwLsi4WwJfvUSxzZCbxumDsTixQKZcpQL6TD4wK4KxCzDHSQWriamkEazCt?cluster=devnet) |
| The round | [`6P7gQS4E…`](https://explorer.solana.com/address/6P7gQS4EbVG8eykGsFbQ1iM7Jhgd5e7oHMFUqAaX1RF7?cluster=devnet) |

[Step 3](../part-2-draw) re-runs this round's draw.

## How it was tested

- 95 tests on the compiled program, 15 of them for rounds. They cover:
  - a skipped target slot, where the next slot is used
  - revealing too early, too late, twice, or with the wrong seed
  - a fake `SlotHashes` account
  - the bond going only to the opener
  - a round marked withheld only once it can no longer be revealed
  - the same list opened a second time, by anyone
  - reading `SlotHashes` as encoded by Solana's own crate, not by our assumption of its layout
  - the worst-case reveal staying well under the compute limit
- 14 deliberate breakages in the rounds code. The tests catch all 14.
- An independent review of the first version found that an opener could open many rounds for the same list, reveal them all, get every bond back and keep the result they liked. Rounds are now keyed on the list itself, so that cannot happen. The review also asked for the validator case to be named plainly, and the specification now does.

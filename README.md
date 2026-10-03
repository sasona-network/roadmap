# Sasona roadmap

Sasona is a decentralised payment network for AI agents. An agent says what it wants to buy, the network pays the seller, and the agent is billed only for what actually arrived. If a purchase does not deliver, the agent gets its money back.

The members of the network make that possible. They test the services agents buy from, and they stand behind what they tested with their own stake. Nobody in the middle decides who is trusted.

This repository is the plan, and the record of it being built.

> Everything here runs on Solana devnet. The coin has no value, and nothing touches mainnet.

## The parts

Each part is built, published, and proven before the next one starts.

| # | Part | What it does | Status |
|---|------|--------------|--------|
| 1 | The pool | A contract holds the money. A coin is only created when a dollar comes in. | Not started |
| 2 | Fair assignment | Who tests which service is drawn from a public seed, so anyone can re-run the draw. | Not started |
| 3 | Committed answers | The test is locked in before the seller replies, so the result can be checked afterwards. | Not started |
| 4 | Second readings | A different member re-tests a service, to catch a rating that was wrong or has gone stale. | Not started |
| 5 | Member stakes | A member stakes on the services they vouch for, and loses it if their reading was false. | Not started |
| 6 | Ranking by price | Services are ranked by what members charge to insure them, not by us. | Not started |
| 7 | Chargebacks | A buyer disputes a purchase, members drawn at random decide, and the buyer is paid back. | Not started |
| 8 | Payment channels | Many small payments settle on chain as one. | Not started |
| 9 | Spending limits | An agent's key can never spend more than the limit its owner set. | Not started |

## Proofs

When a part is done, it gets a folder in [`proofs/`](proofs/) with three things:

- what was built
- the devnet transactions that show it working
- a script you can run to check those transactions against the chain yourself

The script reads the chain directly. You don't need to trust our description of it.

## Repositories

| Repository | What's in it |
|------------|--------------|
| [`roadmap`](https://github.com/sasona-network/roadmap) | This plan, and the proofs |
| [`sasona-protocol`](https://github.com/sasona-network/sasona-protocol) | The rules every implementation follows, with test values to check against |
| [`sasona-program`](https://github.com/sasona-network/sasona-program) | The Solana contract |

More repositories are added as the parts that need them begin.

## Following along

Each part is a [milestone](https://github.com/sasona-network/roadmap/milestones), and each step in it is an issue that closes when the step is done.

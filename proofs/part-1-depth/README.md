# Part 1, step 4: adding depth

Anyone can now add dollars to the pool with nothing created against them.

## What was built

One instruction, `add_depth`. The dollars go into the pool and stop there: no coin is minted, burned or paid out. The same coins are then backed by more money, so the price rises and the pool can absorb a larger sale without anyone being handed a claim on it. Anyone can call it, because a caller can only give.

The reserve's share of every fee already works this way. This makes it possible on its own.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/e476a0104b42064882118ce54eff816f7f6a27f1)

## On devnet

| | |
|---|---|
| Upgrade | [`3Rq71J4y…`](https://explorer.solana.com/tx/3Rq71J4yvHgViY8uDWK2eJCNxDBdAJiYfRKjVisaZabcvs8ZFwJEXLDs6Wu3ZMjgudvGJzDWPb8y1TWzgMRKmL9C?cluster=devnet) |
| $50.00 of depth | [`4UAxgF72…`](https://explorer.solana.com/tx/4UAxgF72qDhT8D3HaE6DVU7EoJZUnsszsGctiBg7paMA7irSeuafoHXisQ6RqEVKFtPd3sScMNxCXdvrDcTPk33y?cluster=devnet) |

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It reads the transaction from the chain and checks that the giver's dollars arrived in the pool, that the only token movement in the whole transaction was that one transfer, and that the pool's coin did not move.

## How it was tested

- 56 tests on the compiled program, 6 of them for depth: dollars in and nothing minted, deposits after depth priced at the new ratio, and the attacks that must be refused (nothing added, a dollar of your own, someone else's dollars, your own account in place of the pool's).
- 5 deliberate breakages in `add_depth`. The tests catch all 5.
- The independent review of this step and the next found nothing to fix in `add_depth`.

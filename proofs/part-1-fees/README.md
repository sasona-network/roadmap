# Part 1, step 3: fees

A purchase's fee is now paid into the pool, and it moves the price.

## What was built

A purchase carries a markup of fifteen points over the seller's price, paid in dollars. The contract cuts it three ways:

| Part | Share of the markup | What happens to it |
|---|---|---|
| Reserve | 5 of the 15 points | Added to the pool as dollars first, with no coin made against it |
| Burn | 3%, which is 0.45% of the purchase | Buys coin from the pool, and the coin is destroyed |
| Participants | The rest | Buys coin from the pool for the people who made the purchase possible |

Buying coin with dollars, and minting nothing to match, is what moves the price up. The burn rounds up, so it is never less than 3% even on a payment of a fraction of a cent.

The participants' coin is shared between the developer whose agent made the purchase (4 points), the members who tested the service (2), whoever added it to the catalogue (1), whoever introduced the agent (1), and the network (2).

Entry fees that deposits had left waiting are now turned into coin the same way, without the reserve: 3% burned and the rest to the participants. Anyone can trigger this.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/af517f2c26cade7bed0a6504fe3b0f0de002d0d2)

> **Temporary, and will change.** None of the participant roles exists on chain yet. A share whose role nobody filled goes to the network, so for now the network receives all of it, and the network's coin waits in a vault held by the pool, with no instruction that moves it out. Both change when the parts that bring developers, members, submitters and marketers on chain are built.
>
> **Also temporary:** any caller can pay any fee, because there is no purchase on chain to tie it to yet. While all the coin goes to the network vault, that is harmless. It has to be tied to real purchases before participants are paid.

## On devnet

| | |
|---|---|
| Upgrade | [`33iT5CDu…`](https://explorer.solana.com/tx/33iT5CDu3qnnCJNGhBAxzVzXhCxrbdREBF8CTq3Q9mFqYVVWujZhkP4Yz26LQ8jxRwCnYsBS9dvf4cX6NprrQSTM?cluster=devnet) |
| A $1.50 markup, on a $10.00 purchase | [`4eNwGPDy…`](https://explorer.solana.com/tx/4eNwGPDyGP8Ni1awnP9qy1Hy3aSmDeW8cApRJJQ8VTvmh8DsBXAndvMm7ENq7UgzqZDPtMypSrEn4z764CiKhUTK?cluster=devnet) |
| Settling $235.50 of waiting entry fees | [`2Jq6WPFb…`](https://explorer.solana.com/tx/2Jq6WPFbL9rbRGUC5FzU5PvAiH5pRFowLC4o7HBPqsYVFyN27KUdrr2syN4xnzwyRGPrm1pQoJiUwGZhEdr5mdju?cluster=devnet) |
| The network's vault | [`CLR6NALJ…`](https://explorer.solana.com/address/CLR6NALJpfNd16ctDnbvQQN6WAjVMva5DAXYQ5hJxzo7?cluster=devnet) |

What the fee did, read from its own transaction:

| | |
|---|---|
| Paid | $1.50 |
| Kept in the pool as depth | $0.50 |
| Spent buying coin | $1.00 |
| Coin bought | 4,994.39 |
| Burned | 224.75 |
| To the network | 4,769.64 |

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. For each fee and each settlement it reads the transaction's own balances and burns from the chain, and checks that the payer paid exactly what the pool received, that the coin bought matches the pool's price with the reserve added first and not spent, that 3% was burned, and that the rest went to the network's vault, which the pool holds.

## How it was tested

- 50 tests on the compiled program, 15 of them for fees: the split of a markup, the burn on payments as small as one unit, 100,000 random buys that must never shrink the pool, sixty deposits, fees and settlements in random order with the books checked after each, and dollars sent straight to the fee account surviving a settlement.
- Attacks that must be refused: paying in a token of your own, paying from someone else's dollars, passing your own account for any of the pool's, and taking or burning the network's or the pool's coin yourself.
- 40 deliberate breakages. The tests caught 39. The one they missed removed the check that the coin passed in is the pool's coin; the token program refuses a fake one anyway, because every fee burns something. A test for it has been added for the next step.
- An independent review found nothing exploitable. It found that the burn rounded down to nothing on micro-payments, that the reserve should come off the top as the design says, and that one test ignored its own errors. All three were fixed before deploying.

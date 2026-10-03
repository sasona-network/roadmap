# Part 1, step 1: opening the pool

The contract is on devnet and the pool is open.

## What was built

One instruction, `open`. It creates the coin and the pool, and makes the first deposit. The coin's only mint authority is the pool's address, which is derived from the program and has no private key. Nobody can freeze the coin. The token the pool accepts as a dollar and the opening price are fixed in the program, so whoever opens it gains nothing by going first.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program)

## On devnet

| | |
|---|---|
| Program | [`7eiHSnDkM4WjJdY36D2Yqsjw893mCMUtBAwMCQ5adL99`](https://explorer.solana.com/address/7eiHSnDkM4WjJdY36D2Yqsjw893mCMUtBAwMCQ5adL99?cluster=devnet) |
| Coin | [`CUFfK9XRCUqFZUmMpq2N5cgvqkGoYfK4iqVKiQNJGnT6`](https://explorer.solana.com/address/CUFfK9XRCUqFZUmMpq2N5cgvqkGoYfK4iqVKiQNJGnT6?cluster=devnet) |
| Pool | [`8ehw265fqKGs79ZGKAX9RFiE1hTwPaMG6SX4aqPVgqkz`](https://explorer.solana.com/address/8ehw265fqKGs79ZGKAX9RFiE1hTwPaMG6SX4aqPVgqkz?cluster=devnet) |
| Dollar (a stand-in we created) | [`ACPdQtaC6HKgT8V4GVRke57vtZrbv3zDqTwvENBoRPCy`](https://explorer.solana.com/address/ACPdQtaC6HKgT8V4GVRke57vtZrbv3zDqTwvENBoRPCy?cluster=devnet) |
| Deploy | [`3wuWewCw…`](https://explorer.solana.com/tx/3wuWewCwv9xaZF69P9pfYct8wa1HzsmFXgWME4MdN91AnEEt2kWpFeJNDoQvHxZ1tR3yVXa8L7M8gR3kgWuaCDrw?cluster=devnet) |
| Opening deposit | [`3kshFbZa…`](https://explorer.solana.com/tx/3kshFbZaEDYVoPhuXnrJ825agQWHo22RBUNpUPod6y15Ury2UXeEqTfJTpkTvd79o9Qnd2Tcw48q5Ss6RyoQkByE?cluster=devnet) |

The opening deposit was $1,220 of test dollars:

| | |
|---|---|
| Entry fee, held for the fee split | $183.00 |
| Dollars in the pool | $1,037.00 |
| Coins in the pool | 5,185,000 |
| Coins outside the pool (free and guarantee) | 4,407,250 |
| Total supply | 9,592,250 |

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It derives every address from the program again, reads the chain directly, and checks:

- the program on devnet is the binary built from the published source
- only the pool can mint the coin, nobody can sign for the pool, nobody can freeze the coin
- every coin is either in the pool or outside it, and the pool's accounts hold what it has recorded
- the opening transaction is final and succeeded

## What is still trusted

- **The upgrade key.** On devnet the program can still be upgraded by `CCsLKV9yCucqYmdb1KarjsTD5pA6q2fzucBa9ozCTSFu`, and new code could mint. The script prints this key every time it runs.
- **The stand-in dollar.** We created it and we can mint it. On mainnet the pool will accept a real stablecoin.

## How it was tested

- 15 tests run the compiled program in a local simulator. Several are attacks: minting without the pool, taking a guarantee back, opening a second time, opening with a self-made dollar, paying with someone else's dollars. Each passes only when the attack is refused for the expected reason.
- A separate script breaks the program in 9 specific ways, one at a time, and checks that the tests catch each one. All 9 are caught.
- An independent review of the code before deploying found that anyone could open the pool first with a dollar they made themselves. That was fixed before deploying, and a test now covers it.

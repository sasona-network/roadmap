# Part 1, step 2: deposits

Anyone can now deposit into the pool, and a deposit does not move the price.

## What was built

One instruction, `deposit`. A deposit is split the same way as the opening: a 15% entry fee, and the rest divided into spread, guarantee and free coins. Coins are priced at the pool's own ratio of coins to dollars, and the pool mints its side to match what it receives, so the ratio stays where it was. Rounding always goes down, so a depositor can receive a fraction of a coin unit less, never more. Someone who deposits again adds to the same guarantee, which stays locked in a vault the depositor cannot move.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/c67865da6cbe3f3023a254c3cef8e4b5c7927ae3)

## On devnet

| | |
|---|---|
| Upgrade | [`4bmfssHQ…`](https://explorer.solana.com/tx/4bmfssHQEuGvxNDWfLp8iYf4drrjhJB3ecsrKXQpZ2ogDebBXd4n4uHWn92xVY5iaojLzDXUo3MEgngQ9KWAPJTU?cluster=devnet) |
| $100 from a new depositor, [`CFFSXFb3…`](https://explorer.solana.com/address/CFFSXFb3bShcMczc3EoH2NFd5W9irrqi2aBeyW493pzQ?cluster=devnet) | [`5K8fejTm…`](https://explorer.solana.com/tx/5K8fejTmtiNcrpoiZw4poN4UcVkDAYX5GGJuGdsaFHYj4dciRffPAzoQRtUqJjcNDLCJTrixz5tGDW2ko7u2umRq?cluster=devnet) |
| $250 more from the opener, [`CCsLKV9y…`](https://explorer.solana.com/address/CCsLKV9yCucqYmdb1KarjsTD5pA6q2fzucBa9ozCTSFu?cluster=devnet) | [`3r9fuofs…`](https://explorer.solana.com/tx/3r9fuofsMDh2fxJK6dyMd2rMi1HDJTWN1rNjm2nzNrtuSXZMZnzRtSNk6LvwbkxkkHqqk73Byy8V6pSWn4c5LgAc?cluster=devnet) |

The pool after both:

| | Before | After |
|---|---|---|
| Dollars in the pool | $1,037.00 | $1,334.50 |
| Coins in the pool | 5,185,000 | 6,672,500 |
| Coins a dollar | 5,000 | 5,000 |
| Fees held | $183.00 | $235.50 |
| Total supply | 9,592,250 | 12,344,125 |

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. On top of everything the step 1 script checks, it confirms the price is still exactly 5,000 coins a dollar, and that each depositor's guarantee record names them, matches their vault, and that the vault is held by the pool and not by them.

The program is upgraded as the roadmap moves on. [`binaries.json`](../binaries.json) lists every binary we have deployed with the source it was built from, and every proof checks that devnet runs one of them.

## What is still trusted

The same two things as step 1: the upgrade key, and the stand-in dollar we can mint.

## How it was tested

- 35 tests run the compiled program in a local simulator, 20 of them for deposits. They include 40 deposits of random sizes from four people with the books checked after each, a gift sent straight to the pool's accounts, and 100,000 random prices to check that rounding can never let the price fall.
- Attacks that must be refused: depositing before the pool opens, paying in a token of your own, using someone else's dollars, depositing into someone else's guarantee, sending your free coins elsewhere, and passing your own account where any of the pool's three accounts belong.
- 22 deliberate breakages, 13 of them in `deposit`. The tests catch all 22.
- An independent review found no way to exploit the deposit. It found that nothing tested swapping in your own account for the pool's fee or coin account, and that a deposit of a few units could skip the fee. Both are fixed and tested.

## Known limit

At 5,000 coins a dollar, the coin's supply counter fills after about $2 billion of total deposits, and deposits would stop. That does not matter on devnet. The price or the coin's decimals will be set before mainnet so the limit is out of reach.

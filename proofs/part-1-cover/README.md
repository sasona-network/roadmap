# Part 1, step 5: claims and release

A buyer whose purchase did not deliver can now be paid back, and the guarantees pay for it together.

## What was built

**One cover.** Every depositor's guarantee is cover for every buyer, so the guarantees now sit together in one vault held by the pool, and each depositor holds shares of it. Before this step each guarantee had a vault of its own; `join_cover` moved the two that existed on devnet into the cover and closed the old vaults.

**Claims.** A claim pays a buyer in dollars out of the pool. Two equal amounts of coin are burned with it: the pool's, so the price does not fall, and the cover's, so every share carries the loss alike. A claim can never empty the cover or leave it too thin for new deposits.

**Release.** A depositor asks for some of their guarantee back. The shares leave their guarantee but stay in the cover, still paying claims, for 45 days. After that, `release` pays them their shares' part of the cover as coins they hold, which is less than went in if claims were paid in the meantime.

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/bb115558e51e6e6ae0c0434915dcfb907c0915ca)

> **Temporary, and will change.**
>
> - **Who approves a claim.** Deciding claims belongs to members drawn at random, which is part 7 of the roadmap. Until then a claim is approved by the key that can already upgrade the program, so nothing new is trusted. The proof checks that key signed.
> - **Leaving ahead of a claim.** Once its notice has run out, a guarantee can still be released just ahead of a claim its owner can see coming. Releases will pause while a claim is pending, once claims are filed on chain in part 7.

## On devnet

| | |
|---|---|
| Upgrade | [`57WpmKSF…`](https://explorer.solana.com/tx/57WpmKSFb8HEdNZSWQ41VgrMX8YD46dxLZkCFNavHj4exzCb9NCR9zcnH8Yp7Ga4bwgz7mAoM16T5zqHYTyd6hZX?cluster=devnet) |
| The opener's guarantee joins the cover | [`3dZkUBAi…`](https://explorer.solana.com/tx/3dZkUBAitGUPcAaPfbNtGRqpyQo6AZLU14bWLXLjjeS7UEhP6YqDGm4x5e8fgbxHbEPDutHxsxv4gQLxpf3xkhm9?cluster=devnet) |
| The second depositor's joins | [`2H7QgsKT…`](https://explorer.solana.com/tx/2H7QgsKTAAh4WWyBLk4Tmhd89aWn6v7Adwf3QkHrUMeFEVUueUADftj3KWpd56QePpMaK6KuewTYcfN82d5A3zmt?cluster=devnet) |
| A $20.00 claim paid to a buyer | [`4j8Kvd2d…`](https://explorer.solana.com/tx/4j8Kvd2di6KYMYF3KrH78gDpHByViMoYVpMEeTsyh8X5un7uta7JsKDtyAaHLNUF6kezCrWZZaKogUTumXo7iJCU?cluster=devnet) |
| A $50.00 deposit after the claim | [`wyxHT6YB…`](https://explorer.solana.com/tx/wyxHT6YBrPi4rPzG3qrawYNqrQH9ABhfwpF4yku3QwEwwUp2HK6WRiHYyMn5L4FPpsUy1LRZSzqLnZNFm3KCxKV?cluster=devnet) |
| Half of a guarantee asked back, ready 18 November 2026 | [`5GZB8NRd…`](https://explorer.solana.com/tx/5GZB8NRdLKWnZofPhwVxWgcrnV9q7yXp84UWuELzJzyQ9eM72MyuMwq2YHJP4DHsny6Zpt6d16FyPZLdvQ6XmKwb?cluster=devnet) |
| The cover | [`CWnyYtor…`](https://explorer.solana.com/address/CWnyYtort2CxRB5WKJo7AJSCaJUpPwZZMuL4h26HBnm7?cluster=devnet) |

The claim, read from its own transaction: the buyer received $20.00, and 69,914.70 coins were burned from the pool and the same from the cover.

The release itself cannot happen on devnet before 18 November. The tests run it by moving the clock forward.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It checks that:

- the cover's vault is held by the pool and holds the coins the cover records
- each depositor's guarantee is now shares of it, and their old vault is closed
- every share is accounted for
- each claim was signed by the judge key, paid the buyer exactly what left the pool, and burned the same coins from the pool and the cover, at least the coins behind those dollars
- each request to leave waits 45 days

## How it was tested

- 80 tests on the compiled program, 23 of them for the cover. They cover:
  - a claim falling on every share alike, including after a fee has moved the price, so the amounts round
  - deposits after a claim not diluting anyone, and 100,000 random cases where new shares are never worth more than the coins paid for them
  - release after 45 days and not before, a claim during the notice still reaching the leaver, and the last one out taking every coin left
  - the move of old guarantees, including a stray coin sent to an old vault, which must not block it
- Attacks that must be refused:
  - a claim not signed by the judge, larger than the cover, thin enough to block deposits, paid in another token, or paid into the pool's own accounts
  - asking back or releasing someone else's guarantee, or asking back without the owner's signature
  - depositing or asking back while a guarantee is still in its old vault
- 65 deliberate breakages across the whole program. The first run caught 63. The two it missed changed which way a claim and a new share round, and only showed when amounts did not divide exactly. Tests for that were added, and all 65 are now caught.
- The independent review found:
  - a claim could leave the cover so thin that every later deposit would overflow
  - an owner could step out just ahead of a claim
  - a claim could be paid into the pool's own fee account
  - the command-line client no longer matched the program

  The first, third and fourth are fixed and tested. The second is narrowed by the 45-day notice and closes properly in part 7, as noted above. Writing the tests also found that one stray coin unit sent to an old vault could block its move for ever; that is fixed too.

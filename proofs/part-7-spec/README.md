# Part 7, step 1: purchases and chargebacks, written down

A buyer whose purchase did not deliver gets the price back. Nobody decides that by opinion: a member drawn for that chargeback alone tests the service again, and the rule of section 2 gives the verdict. The cover pays the buyer at once, and the member who insured the purchase pays the cover back out of their stake.

## What was built

[`sasona-protocol` version 0.7.0](https://github.com/sasona-network/sasona-protocol/blob/74ff072d32e32bd20d685c7580103730e4921ad1/SPEC.md), section 7:

- **Where a service is paid.** A reading records the address the service asks to be paid at, and a covered purchase pays only there.
- **A covered purchase.** The price goes to the merchant for good, and the premium to the member who quoted. A member insures only up to their stake, valued in dollars, less what their open purchases could cost and what they owe.
- **A chargeback** within 7 days, with a 5% deposit. The first one on a service in 30 days is free.
- **The replay.** It is a reading by a member drawn from a seed nobody holds, passing over the buyer's and the quoter's seats. A draw nobody uses counts once its hour is over. After 8 such draws, or 7 days, the buyer is paid.
- **What it settles.** If the service delivered, the buyer gets nothing back. If it did not, or nobody replayed, the cover pays the buyer and the quoter owes the cover. The replayer gets 5% either way.

## Check it yourself

[`vectors/chargeback.json`](https://github.com/sasona-network/sasona-protocol/blob/74ff072d32e32bd20d685c7580103730e4921ad1/vectors/chargeback.json) holds:
- 4 sets of amounts
- 4 rooms to insure
- 5 settlements
- the replay seeds and draws, with 6 cases of who is passed over

Every expected value is written by hand, and the Python and the Rust implementations match all of it.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review read the design three times before any code was written. It then read the code, and the fixes.

**The first draft let the buyer name the merchant, and paid every loss from the cover.** The review found three ways to drain the cover:
- buying from yourself on a service already failing
- an operator quoting their own service and then breaking it
- a member collecting premiums on a quote with nothing at stake

**What changed:**
- the reading records where the service is paid
- the member who quoted pays the cover back from their stake, and can insure only up to it
- the replay became its own draw from a seed nobody holds, and the replayer is paid whatever the verdict

**The second draft paid the replayer a flat fee, and valued what a member insures in coin.** The review found:
- a flat fee farms the cover through tiny purchases
- a coin value can be moved within one transaction
- a member could charge back their own purchase to cash out their stake ahead of a challenge
- declines could be bought, and when a draw counts was not defined

**What changed:**
- the fee is 5% of the price, and there is a minimum price
- room to insure is counted in dollars
- the cover pays at once, and the member's debt is taken only once their reading can no longer be challenged
- 8 draws or 7 days, every seat of the buyer's and the quoter's keys passed over, and the draw number in the seed

**The third draft did not count a debt not yet paid against the stake, and let an expired draw be drawn again for free.** Both are fixed:
- room to insure is the stake, less open purchases at their price plus 5%, less what is owed
- a draw whose entropy was never recorded counts as one of the 8

**The code review found that a member could charge down their own stake and keep their seat.** Now:
- a membership left with less than a whole stake leaves its seat
- a challenge upheld takes what the member owes before the challenger's tenth
- the buyer names the highest rate they accept, so a quote raised at the last moment does not charge them more
- a paid chargeback restarts the 30 days too

A second review of those fixes found nothing serious.

What is left is stated in 7.7. The main points:
- **The insurer pays when a service decays.** The paper puts that loss on the cover.
- **The replay tests the service now, not the buyer's request,** so a service that fails some of the time can go either way.
- **A replayer can make up either verdict.** Only the draw stands in the way.
- **Marking services that fail some of the time, and removing services with too many chargebacks,** are not covered yet.

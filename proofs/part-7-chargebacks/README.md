# Part 7, steps 2 and 3: purchases and chargebacks on devnet

A buyer made two covered purchases from a service and charged both back. Each time a member drawn at random tested the service again, and the program paid out what that test decided. Nobody chose the outcome.

## What was built

| Instruction | What it does |
|---|---|
| `buy` | A purchase covered by a member's quote. The price goes to the address the reading recorded, the premium to the member who quoted. Refused past the member's room to insure, or if the quote was raised past the rate the buyer accepted |
| `close_purchase` | After 7 days with no chargeback, gives the member back the room the purchase took |
| `charge_back` | Within 7 days, the buyer asks for the price back, with a 5% deposit unless nobody charged back the service in the last 30 days |
| `record_draw`, `commit_replay` | Fix the member drawn to replay the service, and have them commit to the test, as for any reading |
| `pass_draw` | Counts a draw nobody used once its hour is over, and draws again |
| `settle_chargeback` | Pays out what the replay decided; 7 days with no replay pays the buyer |
| `repay_cover` | Once the covering reading can no longer be challenged, takes what the member owes the cover out of their stake |

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/fa429c04b3b127fd41a61261df3369f753e703d8). The rules are section 7 of [`sasona-protocol` 0.7.0](https://github.com/sasona-network/sasona-protocol/blob/74ff072d32e32bd20d685c7580103730e4921ad1/SPEC.md).

## The run

A new round drew the one service on [`list.txt`](list.txt), and drew membership 3 to read it. The service does not exist, so as in earlier parts the request went to a stand-in. The stand-in named where it wanted to be paid, and the reading recorded that address. Membership 3 quoted 150 basis points on it.

| | Purchase 1 | Purchase 2 |
|---|---|---|
| Price, and premium to membership 3 | $1.00, $0.015 | $1.00, $0.015 |
| The service when the replay ran | working | broken: the stand-in switched to a wrong answer |
| Deposit | none: the first chargeback on the service | $0.05: the second within 30 days |
| Drawn to replay | membership 1. Memberships 3 and 4 could not be drawn: the key that quoted holds them | membership 1 |
| The replay found | delivered | wrong answer |
| The buyer | got nothing back | got the $1.00 and the deposit back, from the cover |
| The replayer | $0.05, from the cover | $0.05, from the cover |
| Membership 3 owes the cover | 174.79 coins | 3,670.52 coins |

What membership 3 owes is taken from its stake once its reading can no longer be challenged, 30 days after it was revealed. Until then it counts against what membership 3 can insure.

Every step is in [`run.sh`](run.sh) and its output in [`log.txt`](log.txt), failed attempts included: the reading was first tried with the key that was not drawn, and the client refused before anything was sent. The first purchase hit a bug in the client, which read a flag as the rate. That was fixed before the purchase went through.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It reads the accounts and transactions from devnet and checks:

- **The reading:**
  - the round's list is `list.txt`, and the draw picks its service
  - the question, the reply and the verdict
  - it was taken by the membership drawn, with its own key
  - it recorded the merchant's address, and membership 3 quoted it
- **Each purchase:**
  - it sits at the buyer's own address, and is covered at the quote's rate
  - the buyer paid the price to the merchant and the premium to membership 3
- **Each chargeback:**
  - it was made by the buyer within 7 days
  - its deposit follows the 30-day rule
  - its replay reproduces from the files in [`readings/`](readings)
  - the replayer is the membership the draw's seed gives, after passing over the buyer's and the quoter's seats
  - the dollars that moved when it settled are the ones section 7.5 gives for the replay's verdict
- **What membership 3 owes:** both debts are in its book.

Copying one replay's reply over the other's makes it fail, and so does calling the second chargeback free. Both were tried.

One limit: the check takes each draw's seed from the chain. It does not rebuild the seed from the slot hash it was made from, because the public endpoint does not serve old slot hashes.

## How it was tested

- **208 tests** on the compiled program, 33 of them for purchases and chargebacks.
- **72 deliberate breakages** of the purchase, chargeback, cover and challenge code. The tests catch all 72.
  - Nine got through at first. Eight now have a test:
    - a buyer's own seat drawn to replay
    - a membership that declined drawn again
    - a seat shown as passed over that should have been drawn
    - the replayer's pay sent to someone else
    - the price paid somewhere other than the recorded address
    - a member who asked to leave still insuring
    - a burned stake not taken off the coin outside the pool
    - a paid chargeback not restarting the 30 days
  - The ninth broke a check the quote already makes, so the check was removed.
- **Independent review** of the design, and then of the code. It is set out in [the spec step](../part-7-spec).

# Part 8, steps 2 and 3: a payment channel on devnet

An agent opened a channel for the node that buys for it. The node bought five times from a merchant and paid the merchant at once each time. The agent signed what it owed after each purchase, and the node took all five in one transaction. The agent's money sat in the program the whole time, not with us.

## What was built

| Instruction | What it does |
|---|---|
| `open_channel` | The agent's dollars, in an account of the channel's own, for the node that buys for it. A key of the agent's choosing signs the vouchers, and signs the opening to show it is held |
| `take_payment` | Pays the node against a voucher, checked by the ed25519 program in the instruction just before |
| `sweep_channel`, `settle_markup` | Move the markup to the network, then turn it into coin, 5 of its 15 points kept in the pool |
| `ask_to_close_channel`, `close_channel` | The node may close at any time; the agent, after a notice of 648,000 slots |
| `buy` | A covered purchase now pays the 15% markup too |

Source: [`sasona-program`](https://github.com/sasona-network/sasona-program/tree/1c5ec09325cc2fa993274a79e856b7e1a0c088e6). The rules are section 8 of [`sasona-protocol` 0.8.0](https://github.com/sasona-network/sasona-protocol/blob/14d4f5d30460c0402cee7fb497d311165cd2b4e2/SPEC.md).

## The run

The agent is the buyer key from part 7. The node is the deployer's key, standing in for our server. The merchant is part 7's stand-in.

| Step | What happened |
|---|---|
| Open | The agent put $2 in a channel for the node. A separate key signs its vouchers, so the agent's own key stays out of its purchases |
| Five purchases | For each, the node paid the merchant a cent at once, and the agent signed a voucher for everything it owed: 10,000 units, then 20,000, up to 50,000 |
| Take | The node showed only the last voucher. One transaction paid it 50,000 units, and kept the markup on them, 7,500, in the channel, owed to the network |
| Sweep | The 7,500 moved to the network's fee account |
| A covered purchase | $1 from the merchant on the reading of part 7, with its premium and now its markup, $0.15 |
| Settle | The $0.1575 of markup was turned into coin, $0.0525 of it kept in the pool |
| Close | The node closed the channel, and the agent got back $1.9425 and the rent |

Every step is in [`run.sh`](run.sh), and its output is in [`log.txt`](log.txt). The vouchers and the merchant's payments are in [`vouchers/`](vouchers). The first try at paying the merchant was refused, because its wallet held no SOL and the transfer tool asks before paying such an address. Nothing moved, and the run went on with that allowed.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It reads the transactions from devnet and checks:

- **The channel:** it is the agent's first one to the node, opened with $2 and a signer that signed the opening. The $2 went into the program's account and nowhere else.
- **Each purchase:** the node paid the merchant a cent. Each voucher is the signer's signature over the 90 bytes for what was owed so far, checked here against the signer's key.
- **The payment:** it came after all five purchases. The ed25519 check is the instruction just before it, over the signer's key and the bytes for 50,000 units. It paid the node 50,000 units, and 7,500 of markup was owed.
- **The markup:** the sweep, the covered purchase's $0.15, and the settle, with its 5 of 15 points kept.
- **The close:** the agent got back $2 less what was taken and its markup, and the channel and its account are gone.

Changing one character of a voucher makes it fail, and so does naming another key as the signer. Both were tried.

## How it was tested

- **223 tests** on the compiled program. 15 of them are for channels, and 8 of those attack the signature check:
  - no check at all, or another key
  - a smaller amount, another channel, or another cluster
  - the check pointed at other bytes, or two signatures in one check
  - an instruction between the check and the payment
  - a check told to verify fewer bytes than the voucher has
- **40 deliberate breakages** of the channel and markup code. The tests catch all 40.
  - One got through at first: removing the check on the message's length. The test then gave the ed25519 program too few bytes, so the program refused it for another reason. It now gives all 90 bytes and tells the ed25519 program to check 89, which would leave the amount's last byte unsigned.
- **Independent review** of the design four times and of the code once, set out in [the spec step](../part-8-spec).

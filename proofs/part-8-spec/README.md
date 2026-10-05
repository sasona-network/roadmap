# Part 8, step 1: payment channels, written down

An agent does not pay merchants itself: a node buys for it, our server today and any node later, and pays the merchant at once for each purchase. What the agent owes the node is many small amounts. Today the agent keeps a balance with us for them, and we hold that money. A channel holds it in the program instead: the agent signs, off chain, how much the node may take so far, and the node takes it in one transaction, for many purchases.

## What was built

[`sasona-protocol` version 0.8.0](https://github.com/sasona-network/sasona-protocol/blob/14d4f5d30460c0402cee7fb497d311165cd2b4e2/SPEC.md), section 8:

- **The markup on every purchase.** 15% of the price, rounded up, on a covered purchase and on a channel payment alike. It is held, then turned into coin by anyone: 5 of the 15 points stay in the pool, and the rest is shared. Until a purchase can be told from a participant paying itself, the participants' share goes to the network. A chargeback does not return it.
- **A channel.** The agent's dollars, for the node that buys for it, in an account of the channel's own. Each payer's channels take identifiers in order, so no channel address is ever used twice. A key named at the opening, which signs it, signs the vouchers.
- **A voucher.** The signer's signature over 90 bytes: a label, the program, the cluster, the channel and an amount. The amount is everything the payee may have taken so far, so the largest voucher is the only one that matters.
- **Taking payment.** Anyone may show a voucher; the money can only reach the node. The channel pays what it can cover, up to the voucher, and keeps the markup on it, owed to the network.
- **Closing.** The node may close at any time. The agent asks, and the node has 648,000 slots, about 72 hours, to take its last voucher.
- **The signature check,** written as rules the program must keep. Each has been the hole in some deployed program.

## Check it yourself

[`vectors/channel.json`](https://github.com/sasona-network/sasona-protocol/blob/14d4f5d30460c0402cee7fb497d311165cd2b4e2/vectors/channel.json) holds every expected value written by hand:
- markups and the largest payable amount
- the 90 bytes signed, and a signature over them
- a channel through its life: payments, a voucher shown twice, sweeps, dollars sent from outside, and the close
- the edges of the notice, to the slot

The Python and the Rust implementations match all of it. The signature is made with a key thrown away after: only its public half is written down.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review read the design four times before any code, and the code once.

**The first draft let old vouchers come back, and named no way to check a signature.** The review found:
- a channel closed and opened again with the same identifier made its old vouchers good again
- a voucher signed on devnet was good on mainnet
- the signature is checked by a separate instruction the program reads back, and the draft did not say how; reading it carelessly is how deployed programs have been robbed
- a voucher larger than the channel could pay was refused whole, and the payee kept only that one

**What changed:**
- the signed bytes name the program and the cluster
- the checks on the signature became rules
- a voucher pays what the channel can cover
- the notice moved to slots, so a cluster that stops cannot use it up

**The second draft still let a channel be reopened in the same slot.** It also let the payee hand the agent a key to sign with, and kept every channel's dollars in one account.

**What changed:**
- each payer's identifiers go up and never repeat
- the cluster number is compiled in, with the dollar it belongs to
- the signer must sign the opening and cannot be the payee

**The third draft made every payment on the network wait on the same accounts.** **What changed:** each channel has its own account, and the markup stays in it until anyone sweeps it.

**The fourth draft** needed two fixes of wording: name the addresses a channel cannot pay, and keep the books check beside the balance check. Then the review said it was ready for code.

**The code review found nothing that lets anyone take money.** It found:
- the fee account was checked against entry fees only, now that it also holds markup. Both are now checked together, so neither can be spent from the other's dollars.
- the check on the cluster number could never fail. It is now set with the dollar, and a mainnet build does not compile until both are chosen.
- some steps left no event on chain. Now every step does.

**A first version of the design had the merchant on the other side of the channel,** paid later from vouchers, with the agent refusing to sign when a merchant did not deliver. That is not the network. The merchant is paid at once by the node that buys. A merchant that does not deliver is answered by refunds, and in the paper by a count of chargebacks that ends in removal from the network. The channel is only between the agent and the node.

What is left is stated in 8.8:
- a purchase settled through a channel has no refund yet; a covered purchase is made directly
- the node is trusted to buy what it charges for
- the count of chargebacks per service, and removal, are not built yet
- the markup proves that someone paid, not that a purchase happened

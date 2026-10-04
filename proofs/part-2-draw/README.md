# Part 2, step 3: a draw anyone can re-run

A real round on devnet drew 5 services out of 40. This folder holds the list it drew from, and a script that rebuilds the draw from the chain and gets the same 5.

## The draw

The list is [`candidates.txt`](candidates.txt): 40 made-up test services on 9 hosts. One host lists 20 of them. The real catalogue stays private; this list exists to show the draw working.

The round drew:

1. `https://weather.example.com/week`
2. `https://sandbox.example.net/run/rust`
3. `https://data.example.com/prices`
4. `https://email.example.org/send`
5. `https://search.example.org/query`

The host with 20 services was not picked. Each pick draws a host first, so listing more services does not buy more of the draws.

## Check it yourself

```bash
python verify.py
```

Python 3.8 or later, nothing to install. It does what [`sasona-protocol`](https://github.com/sasona-network/sasona-protocol/blob/688da27a605492308daf14884d12e68347fd4bf8/SPEC.md) section 1.8 asks of a verifier:

- fingerprints `candidates.txt` and finds the round at the address derived from that fingerprint, which is the only place it can be
- checks that the revealed seed matches what was committed, that the list's size and fingerprint match, and that the entropy came from a slot after the commitment
- recomputes the final seed from the seed and the entropy
- draws again and compares the result with the 5 above

Change one line of the list, or one of the picks, and it fails. Both were tried.

## What is still trusted

- **The entropy itself.** The program reads the slot hash from Solana's `SlotHashes` when the seed is revealed. Standard Solana RPC does not serve old slot hashes, so the script trusts the program to have read it, and checks that the program is the published one.
- **The upgrade key**, as in every proof so far.

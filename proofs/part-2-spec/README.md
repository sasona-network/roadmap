# Part 2, step 1: the draw, written down

The rule that decides which services get tested is now written down, so it does not live inside one program.

## What was built

[`sasona-protocol` version 0.1.0](https://github.com/sasona-network/sasona-protocol/blob/cbc799109113a416811e7ca646c4e6edb9858a7f/SPEC.md) specifies the draw:

- how a list of services is fingerprinted, and how a host is read from each URL so one service cannot pose as several hosts by spelling
- what a round commits to before anything is known: the list, how many will be drawn, and the hash of a secret seed
- how that seed is mixed with the hash of a Solana slot that did not exist when the round was committed
- the exact steps that turn the result into the services picked, a host first and then an endpoint within it
- what a verifier checks, and what the draw does not promise

## Check it yourself

[`vectors/draw.json`](https://github.com/sasona-network/sasona-protocol/blob/cbc799109113a416811e7ca646c4e6edb9858a7f/vectors/draw.json) holds 8 draws with their inputs and results, 10 host spellings, and 10 lists every implementation must refuse. Two implementations match all of it:

```bash
git clone https://github.com/sasona-network/sasona-protocol
cd sasona-protocol
python reference/check.py
cd rust && cargo test
```

## How it was checked

- Changing any one detail breaks the values: the attempt counted little-endian, the zero byte between candidates left out, or a label misspelt. Each was tried, and each fails.
- An independent review of the first draft found that the number of picks was not committed, so an opener who saw the order could stop just before a service they did not want. It also found that a skipped Solana slot left the entropy undefined, that host spellings let one service count as many hosts, and that non-ASCII lowercasing differs between languages. All four are fixed in this version, and the limits it could not fix are stated in the spec.
- Both implementations are ours. One written by somebody else is what would really test the specification.

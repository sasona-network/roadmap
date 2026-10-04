# Part 5, step 1: members and challenges, written down

Who reads a service, what they put up to do it, and when they lose it.

## What was built

[`sasona-protocol` version 0.5.0](https://github.com/sasona-network/sasona-protocol/blob/dd6cea3d0de0410129ddb5764219c97cd1b1ecd1/SPEC.md), sections 4 and 5:

- **A membership is one stake.** A key can hold several, and each is one more chance to be drawn, so splitting the same coins over more keys buys nothing.
- **The roster is seats with no gaps.** A membership that leaves or loses its stake gives its seat to whoever sits last, so memberships that have gone are never drawn.
- **The reader is drawn, not chosen.** For each service, a seat is drawn from the round's own seed. It counts only if its member sat down before the round was committed. Otherwise someone could leave, rejoin into the last seat and read what was drawn to it.
- **A reading is committed within about an hour of the draw.** A service its member does not read by then goes unread, in public.
- **A reading can be challenged for 30 days.** The member then has 7 days to put the nonce and the reply on chain. If the reply hashes to what they recorded and gives the verdict they recorded, the challenger's bond is theirs. If not, they lose the whole stake.
- **What a challenge does not catch.** A reply made up well passes. A service that stopped working is never, by itself, grounds to take a stake. Both are stated in 5.4.
- **A reply is its first 10,000 bytes,** so every reading can be backed on chain if challenged.

## Check it yourself

[`vectors/reader.json`](https://github.com/sasona-network/sasona-protocol/blob/dd6cea3d0de0410129ddb5764219c97cd1b1ecd1/vectors/reader.json) holds 12 draws of a reader, with:

- seats that left
- seats sat in after the round
- the first reader passed over in a second reading
- a roster with nobody on it

The Python and the Rust implementation match all of it, and so does the program: a test pins its draw to these values.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review went over it three times. Each time it found something that would have broken a promise the paper makes:

- **A long reply could cost an honest member their stake.** A service could send more than a member could put on chain. A reply is now its first 10,000 bytes.
- **Memberships that had left stayed in the draw.** Someone could take thousands, leave, and leave most services unread for good. The roster is now seats with no gaps.
- **Seats let a member choose what they read,** by leaving and rejoining into a seat drawn for a service they wanted. A seat now reads only for rounds committed after its member sat down.
- **No time limits.** A member could be challenged forever, and had a day to answer. It is now 30 days to challenge and 7 to answer, both inside the 45 days' notice to leave.

What is left is stated in 4.5:

- A member can decline a reading, or leave, and so pass the draw on.
- Whoever upholds a challenge picks the moment a seat changes hands.
- A stake is the same size whatever it backs.

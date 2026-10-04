# Part 6, step 1: quotes and the ranking, written down

Services are ranked by what the members who read them would charge to insure a purchase from them. Nobody else sets the order.

## What was built

[`sasona-protocol` version 0.6.0](https://github.com/sasona-network/sasona-protocol/blob/f2b593aff9cab5df6ec67709731ce6014c86a3f2/SPEC.md), section 6:

- **A quote** is a rate in basis points, set by the member who took a reading, only on a reading that says `delivered`, within 30 days of it. They can change it or withdraw it.
- **A service's premium** is the lowest quote still standing on any of its readings. A quote stands while its reading counts and is current, and while its member is active.
- **A failing pair** is two readings next to each other that both found the service not delivering, taken by two different keys. Every quote given before the latest failing pair stops counting, so the service is off the list until a newer reading is quoted by its own member.
- **The ranking** is the listed services from the cheapest premium to the dearest. A service nobody will insure is not listed.

## Check it yourself

[`vectors/ranking.json`](https://github.com/sasona-network/sasona-protocol/blob/f2b593aff9cab5df6ec67709731ce6014c86a3f2/vectors/ranking.json) holds 24 premiums and 5 rankings, every expected value written by hand. The Python and the Rust implementation match all of it.

```bash
python reference/check.py
cd rust && cargo test
```

## How it was checked

An independent review read section 6 four times.

**The first draft took the lowest quote across every reading of the last 30 days.** A cheap quote then outlived a later reading that found the service failing.

**The second draft used only the latest reading.** The review found the opposite problem: one member drawn to read a rival could take it off the list:
- by recording it as failing, which a challenge cannot catch, because a failing reply is the easiest one to make up
- by never quoting
- by leaving

**The third draft took the lowest quote still standing, and took a service off the list only when its two latest readings failed, from two keys.** The review found that one later reading, with no quote of its own, then brought an old cheap quote back. **The rule now:** once two keys have found a service failing, every quote given before stops counting. The member whose quote is the premium carries the risk once purchases are covered (parts 7 and 8). So a quote that is too low costs whoever gave it.

What is left is stated in 6.4:
- A quote costs nothing to give until purchases are on chain.
- An operator holding memberships can still get its own service read and quoted cheaply.
- One person holding two memberships can still take a rival off the list, and one reading, quoted by its member, puts a service back.

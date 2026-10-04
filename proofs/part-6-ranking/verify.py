"""Rebuild the ranking from Solana devnet, as sasona-protocol SPEC.md section 6 orders it.

    python verify.py

Python 3.8+, standard library only. It reads every reading, nonce record,
membership and quote the program holds, checks each reading against its
round's published list, and ranks the services from that alone.
"""

import base64
import hashlib
import json
import struct
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PROOF = json.loads((HERE / "proof.json").read_text())
RPC = PROOF.get("rpc", "https://api.devnet.solana.com")

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
UPGRADEABLE_LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"

failures = 0


def check(what, ok, detail=""):
    global failures
    print(("  ok    " if ok else "  FAIL  ") + what + (f"   {detail}" if detail else ""))
    if not ok:
        failures += 1


# ------------------------------------------------------------------ base58

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(s):
    n = 0
    for c in s:
        n = n * 58 + ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw


def b58encode(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = ALPHABET[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


# ----------------------------------------------- program derived addresses
#
# An address derived from a program is valid only if it is NOT a point on the
# ed25519 curve. A private key always corresponds to a point on the curve, so
# an address off the curve is one nobody can sign for.

P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P


def on_curve(key):
    y = int.from_bytes(key, "little") & ((1 << 255) - 1)
    if y >= P:
        return False
    y2 = y * y % P
    x2 = (y2 - 1) * pow(D * y2 + 1, P - 2, P) % P
    return x2 == 0 or pow(x2, (P - 1) // 2, P) == 1


def find_pda(seeds, program):
    pid = b58decode(program)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pid + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58encode(h), bump
    raise ValueError("no address")


# --------------------------------------------------------------------- rpc

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, body, {"Content-Type": "application/json"})
    # The public devnet endpoint is sometimes slow; a timeout is not a failed check.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                reply = json.load(r)
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]


def account(address):
    v = rpc("getAccountInfo", [address, {"encoding": "base64", "commitment": "finalized"}])["value"]
    if v is None:
        return None
    v["bytes"] = base64.b64decode(v["data"][0])
    return v


# ---------------------------------------------------------------- the draw
#
# sasona-protocol SPEC.md section 1, copied here so this script stands alone.
# The same code is reference/draw.py in that repository.

import hmac

DOMAIN = b"sasona/draw/v1"


def host_of(candidate):
    if not candidate or any(not 0x21 <= ord(ch) <= 0x7E for ch in candidate):
        raise ValueError(f"not printable ASCII: {candidate!r}")
    scheme, sep, rest = candidate.partition("://")
    scheme = scheme.lower()
    if not sep or scheme not in ("http", "https"):
        raise ValueError(f"not http or https: {candidate!r}")
    for stop in "/?#":
        rest = rest.split(stop, 1)[0]
    rest = rest.rsplit("@", 1)[-1]
    host = "".join(chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in rest)
    default = ":443" if scheme == "https" else ":80"
    if host.endswith(default):
        host = host[: -len(default)]
    if host.endswith("."):
        host = host[:-1]
    if not host:
        raise ValueError(f"no host: {candidate!r}")
    return host


def fingerprint(candidates):
    h = hashlib.sha256()
    for c in candidates:
        h.update(c.encode("ascii") + b"\x00")
    return h.digest()


def draw(candidates, final, count):
    hosts, endpoints = [], {}
    for c in candidates:
        h = host_of(c)
        if h not in endpoints:
            hosts.append(h)
            endpoints[h] = []
        endpoints[h].append(c)

    def r(label, attempt):
        d = hmac.new(final, label + attempt.to_bytes(4, "big"), hashlib.sha256).digest()
        return int.from_bytes(d, "big")

    picked, attempt = [], 0
    while len(picked) < count and attempt < 64 * len(candidates):
        options = endpoints[hosts[r(b"host", attempt) % len(hosts)]]
        c = options[r(b"endpoint", attempt) % len(options)]
        if c not in picked:
            picked.append(c)
        attempt += 1
    return picked


# --------------------------------------------------------------- accounts

def u32(b, at):
    return struct.unpack_from("<I", b, at)[0]


def u64(b, at):
    return struct.unpack_from("<Q", b, at)[0]


def i64(b, at):
    return struct.unpack_from("<q", b, at)[0]


def disc(name):
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


def all_of(program, name):
    found = rpc("getProgramAccounts", [program, {"encoding": "base64", "commitment": "finalized",
                                                  "filters": [{"memcmp": {"offset": 0, "bytes": b58encode(disc(name))}}]}])
    return {a["pubkey"]: base64.b64decode(a["account"]["data"][0]) for a in found}


def parse_reading(b):
    n = u32(b, 40)
    at = 44 + n
    r = {"round": b58encode(b[8:40]), "endpoint": b[44:at].decode()}
    r["reader"] = b58encode(b[at:at + 32]); at += 32
    at += 32  # question hash
    r["commit_slot"] = u64(b, at); at += 8
    r["state"] = b[at]; at += 1
    at += 32  # reply hash
    r["verdict"] = b[at]; at += 1
    r["reveal_slot"] = u64(b, at); at += 8
    at += 1  # bump
    r["member"] = u32(b, at) if len(b) >= at + 4 else 0; at += 4
    r["reveal_time"] = i64(b, at) if len(b) >= at + 8 else 0
    return r


# ------------------------------------------------- sasona-protocol section 6

TERM_SECONDS = 30 * 24 * 60 * 60


def order(r):
    return (-r["revealed_slot"], r["committed_slot"], b58decode(r["id"]))


def weighed(readings, now):
    return sorted((r for r in readings if r["counts"] and r["revealed_time"] <= now), key=order)


def newer_than_failing_pair(readings, now):
    w = weighed(readings, now)
    for i in range(len(w) - 1):
        a, b = w[i], w[i + 1]
        if a["verdict"] != 1 and b["verdict"] != 1 and a["key"] != b["key"]:
            return w[:i]
    return w


def stands(r, now):
    return (r["verdict"] == 1 and now <= r["revealed_time"] + TERM_SECONDS and 1 <= r["quote"] <= 10_000
            and r["quote_by_reader"] and r["member_active"])


def behind(readings, now):
    standing = [r for r in newer_than_failing_pair(readings, now) if stands(r, now)]
    return min(standing, key=lambda r: (r["quote"], order(r))) if standing else None


def rank(services, now):
    listed = []
    for service, readings in services.items():
        r = behind(readings, now)
        if r is not None:
            listed.append((r["quote"], order(r), service))
    listed.sort()
    return [[service, p] for p, _, service in listed]


# ------------------------------------------------------------------ checks

def main():
    program = PROOF["program"]
    print(f"\nprogram {program}  on {RPC}\n")
    prog = account(program)
    pd = account(b58encode(prog["bytes"][4:36]))["bytes"]
    published = json.loads((HERE.parent / "binaries.json").read_text())
    running = next((b for b in published
                    if hashlib.sha256(pd[45:45 + b["bytes"]]).hexdigest() == b["sha256"]
                    and not any(pd[45 + b["bytes"]:])), None)
    check("the program runs a binary we published", running is not None, running["step"] if running else "")

    # Every round whose list is published in these proofs, and its picks.
    picks = {}
    for folder, name in PROOF["lists"].items():
        candidates = [l.strip() for l in (HERE.parent / folder / name).read_text().splitlines() if l.strip()]
        address, _ = find_pda([b"round", fingerprint(candidates)], program)
        a = account(address)
        check(f"the round for {folder}/{name} is on chain", a is not None, address)
        if a is None:
            continue
        b = a["bytes"]
        picks[address] = draw(candidates, b[191:223], struct.unpack_from("<H", b, 76)[0])

    readings = {a: parse_reading(b) for a, b in all_of(program, "Reading").items()}
    nonce_owner = {b58encode(b[8:40]) for b in all_of(program, "UsedNonce").values()}
    members = {u32(b, 40): b[48] for b in all_of(program, "Member").values()}
    quotes = {b58encode(b[8:40]): {"member": u32(b, 40), "rate": struct.unpack_from("<H", b, 44)[0]}
              for b in all_of(program, "Quote").values()}
    print(f"\n        {len(readings)} readings, {len(quotes)} quotes, {len(members)} memberships on chain")

    print("\nthe quotes")
    for reading, q in quotes.items():
        r = readings.get(reading)
        ok = r is not None and r["member"] == q["member"] and q["rate"] <= 10_000
        check(f"on a reading the program holds, by its member", ok,
              f"{r['endpoint'] if r else reading}: {q['rate']} bps" if r else reading)

    services = {}
    for address, r in readings.items():
        if r["state"] not in (1, 3):
            continue
        counts = (r["state"] == 1 and address in nonce_owner
                  and r["round"] in picks and r["endpoint"] in picks[r["round"]])
        q = quotes.get(address, {"rate": 0})
        services.setdefault(r["endpoint"], []).append({
            "id": address, "key": r["reader"], "revealed_slot": r["reveal_slot"], "committed_slot": r["commit_slot"],
            "revealed_time": r["reveal_time"], "counts": counts, "verdict": r["verdict"],
            "member_active": r["member"] > 0 and members.get(r["member"]) == 0,
            "quote": q["rate"], "quote_by_reader": address in quotes,
        })

    # Ranked at the moment it was published, so that quotes growing older than
    # 30 days do not change it. What can change is what the accounts say now:
    # a reading upheld false, or a member who has left.
    now = PROOF["at"]
    print(f"\nthe ranking at {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}, when it was published")
    ranking = rank(services, now)
    for i, (service, p) in enumerate(ranking, 1):
        print(f"        {i}. {service}   {p} bps")
    unlisted = sorted(s for s in services if s not in {x[0] for x in ranking})
    for s in unlisted:
        print(f"        not listed: {s}")

    false_reading = readings.get(PROOF["false_reading"])
    upheld = false_reading is not None and false_reading["state"] == 3
    want = PROOF["ranking_after_uphold"] if upheld else PROOF["ranking"]
    check("the ranking is the one published" + (", after the false reading was upheld" if upheld else ""),
          ranking == want, "")
    for name, reading in PROOF["refused"].items():
        r = readings.get(reading)
        check(f"no quote stands on {name}, whose reading did not deliver", r is not None and r["verdict"] != 1
              and reading not in quotes)

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

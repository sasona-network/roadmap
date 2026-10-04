"""Re-run a Sasona draw from Solana devnet and the published list.

    python verify.py

Python 3.8+, standard library only. It reads candidates.txt and proof.json
next to it, finds the round on chain from the list's own fingerprint, checks
it as sasona-protocol SPEC.md 1.8 requires, and draws the services again.
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


def option_key(data, at):
    tag = struct.unpack_from("<I", data, at)[0]
    return b58encode(data[at + 4:at + 36]) if tag == 1 else None



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

    print("\nthe list")
    candidates = [line.strip() for line in (HERE / "candidates.txt").read_text().splitlines() if line.strip()]
    try:
        hosts = {host_of(c) for c in candidates}
        valid = len(set(candidates)) == len(candidates)
    except ValueError as e:
        hosts, valid = set(), False
        print(f"        {e}")
    check("follows the rules for a list (SPEC 1.1)", valid, f"{len(candidates)} services on {len(hosts)} hosts")
    fp = fingerprint(candidates)

    print("\nthe round")
    round_address, _ = find_pda([b"round", fp], program)
    acc = account(round_address)
    check("exists at the address derived from this list, and only there", acc is not None, round_address)
    if acc is None:
        sys.exit(1)
    b = acc["bytes"]
    check("is owned by the program", acc["owner"] == program)
    opener = b58encode(b[8:40])
    committed_fp = b[40:72]
    pool_size, count = struct.unpack_from("<IH", b, 72)
    seed_hash = b[78:110]
    commit_slot = struct.unpack_from("<Q", b, 110)[0]
    state = b[118]
    seed = b[119:151]
    entropy_slot = struct.unpack_from("<Q", b, 151)[0]
    entropy = b[159:191]
    final = b[191:223]
    print(f"        opened by {opener} at slot {commit_slot:,}")

    check("was revealed", state == 1, {0: "still waiting", 1: "drawn", 2: "withheld"}.get(state, "?"))
    check("the seed matches what was committed", hashlib.sha256(seed).digest() == seed_hash)
    check("the list has as many services as committed", len(candidates) == pool_size, f"{pool_size}")
    check("the list's fingerprint matches the commitment", fp == committed_fp, fp.hex()[:16] + "…")
    check("the entropy comes from a slot after the commitment", entropy_slot >= commit_slot + 32,
          f"slot {entropy_slot:,}, {entropy_slot - commit_slot} after")
    check("the final seed is sha256(domain, seed, entropy)",
          hashlib.sha256(DOMAIN + seed + entropy).digest() == final, final.hex()[:16] + "…")

    print("\nthe draw")
    picks = draw(candidates, final, count)
    check("the count drawn is the count committed", len(PROOF["picks"]) == count, f"{count}")
    check("re-running it gives the published picks", picks == PROOF["picks"])
    for p in picks:
        print(f"        {p}")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

"""Re-check second readings against Solana devnet.

    python verify.py

Python 3.8+, standard library only. It rebuilds the re-read round's draw from
list.txt, then for each pair under pairs/ checks the second reading as
sasona-protocol SPEC.md 2.7 asks, and the pair as 3.5 asks.
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


# ------------------------------------------------- sasona-protocol section 2

def expected(nonce):
    return hashlib.sha256(nonce.encode("ascii")).hexdigest()[:16]


def canonical(nonce):
    code = 'import hashlib\nprint(hashlib.sha256("' + nonce + '".encode()).hexdigest()[:16])'
    q = {"capability": "execute", "nonce": nonce, "expect": expected(nonce), "tier": 1, "code": code,
         "command": ["python", "-c", code], "body": {"code": code, "language": "python"}}
    return json.dumps(q, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verdict_of(reply, nonce):
    if not reply:
        return 3
    return 1 if expected(nonce).encode("ascii") in reply else 2


NAMES = {1: "delivered", 2: "wrong_answer", 3: "empty"}


# ------------------------------------------------- sasona-protocol section 3

OUTCOMES = {1: "works_now", 2: "false_or_decayed", 3: "agreed_fails"}


def outcome(first, second):
    if second == 1:
        return 1
    if first == 1:
        return 2
    return 3


READING_DISCRIMINATOR = hashlib.sha256(b"account:Reading").digest()[:8]
NONCE_DISCRIMINATOR = hashlib.sha256(b"account:UsedNonce").digest()[:8]


def parse_reading(b):
    n = struct.unpack_from("<I", b, 40)[0]
    at = 44 + n
    r = {"round": b58encode(b[8:40]), "endpoint": b[44:at].decode()}
    r["reader"] = b58encode(b[at:at + 32]); at += 32
    r["question_hash"] = b[at:at + 32]; at += 32
    r["commit_slot"] = struct.unpack_from("<Q", b, at)[0]; at += 8
    r["state"] = b[at]; at += 1
    r["reply_hash"] = b[at:at + 32]; at += 32
    r["verdict"] = b[at]; at += 1
    r["reveal_slot"] = struct.unpack_from("<Q", b, at)[0]
    return r


def readings_of(endpoint, program):
    """Every reading of this service the program holds, by address."""
    key = struct.pack("<I", len(endpoint.encode())) + endpoint.encode()
    found = rpc("getProgramAccounts", [program, {"encoding": "base64", "commitment": "finalized", "filters": [
        {"memcmp": {"offset": 0, "bytes": b58encode(READING_DISCRIMINATOR)}},
        {"memcmp": {"offset": 40, "bytes": b58encode(key)}},
    ]}])
    return {a["pubkey"]: parse_reading(base64.b64decode(a["account"]["data"][0])) for a in found}


def holds_its_nonce(reading, program):
    """Whether a nonce record names this reading. One that lost its nonce to
    an earlier commitment does not count (SPEC.md 2.7)."""
    found = rpc("getProgramAccounts", [program, {"encoding": "base64", "commitment": "finalized", "filters": [
        {"memcmp": {"offset": 0, "bytes": b58encode(NONCE_DISCRIMINATOR)}},
        {"memcmp": {"offset": 8, "bytes": reading}},
    ]}])
    return len(found) == 1


def latest(readings, round_committed_slot):
    """SPEC.md 3.2: revealed latest, then committed earliest, then smallest id."""
    eligible = [a for a, r in readings.items() if r["counts"] and r["reveal_slot"] < round_committed_slot]
    if not eligible:
        return None
    return min(eligible, key=lambda a: (-readings[a]["reveal_slot"], readings[a]["commit_slot"], b58decode(a)))


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

    print("\nthe re-read round")
    candidates = [line.strip() for line in (HERE / "list.txt").read_text().splitlines() if line.strip()]
    fp = fingerprint(candidates)
    round_address, _ = find_pda([b"round", fp], program)
    acc = account(round_address)
    check("exists at the address derived from list.txt", acc is not None, round_address)
    if acc is None:
        sys.exit(1)
    b = acc["bytes"]
    pool_size, count = struct.unpack_from("<IH", b, 72)
    seed_hash, round_commit = b[78:110], struct.unpack_from("<Q", b, 110)[0]
    state, seed = b[118], b[119:151]
    entropy_slot, entropy, final = struct.unpack_from("<Q", b, 151)[0], b[159:191], b[191:223]
    print(f"        opened by {b58encode(b[8:40])} at slot {round_commit:,}")
    check("was drawn", state == 1)
    check("the list matches what was committed", b[40:72] == fp and pool_size == len(candidates))
    check("the seed matches what was committed", hashlib.sha256(seed).digest() == seed_hash)
    check("the entropy comes from a slot after the commitment", entropy_slot >= round_commit + 32)
    check("the final seed is sha256(domain, seed, entropy)", hashlib.sha256(DOMAIN + seed + entropy).digest() == final)
    picks = draw(candidates, final, count)
    check("re-running the draw gives the published picks", picks == PROOF["picks"])

    for name, want in PROOF["pairs"].items():
        folder = HERE / "pairs" / name
        meta = json.loads((folder / "reading.json").read_text())
        question = (folder / "question.json").read_bytes()
        reply = (folder / "reply.bin").read_bytes()
        service = meta["service"]
        print(f"\npair: {name}   {service}")

        # The second reading, as 2.7 asks of any reading.
        check("the service is, byte for byte, one of the round's picks", meta["round"] == round_address and service in picks)
        second_address, _ = find_pda([b"reading", b58decode(round_address), hashlib.sha256(service.encode()).digest()], program)
        sa = account(second_address)
        check("the second reading is on chain at the address for that round and service", sa is not None, second_address)
        if sa is None:
            continue
        s = parse_reading(sa["bytes"])
        nonce = meta["nonce"]
        check("it was revealed after it was committed", s["state"] == 1 and s["reveal_slot"] > s["commit_slot"])
        check("the question shown is the fair one for its nonce", question == canonical(nonce))
        check("the question hashes to what was committed before the call", hashlib.sha256(question).digest() == s["question_hash"])
        owner, _ = find_pda([b"nonce", bytes.fromhex(nonce)], program)
        o = account(owner)
        check("the nonce belongs to this reading", o is not None and b58encode(o["bytes"][8:40]) == second_address)
        check("the reply shown hashes to what was recorded", hashlib.sha256(reply).digest() == s["reply_hash"])
        check("the verdict rule on that reply gives the recorded verdict", verdict_of(reply, nonce) == s["verdict"],
              NAMES.get(s["verdict"], "?"))

        # The pair, as 3.5 asks.
        first_address = meta["first"]
        fa = account(first_address)
        f = (parse_reading(fa["bytes"]) if fa and fa["owner"] == program
             and fa["bytes"][:8] == READING_DISCRIMINATOR else None)
        check("the first is a reading the program holds", f is not None, first_address)
        if f is None:
            continue
        check("the first was revealed", f["state"] == 1, NAMES.get(f["verdict"], "?"))
        check("the services are the same bytes", f["endpoint"] == s["endpoint"] == service)
        check("the readers differ", f["reader"] != s["reader"], f"{f['reader'][:8]}... then {s['reader'][:8]}...")
        check("the first was revealed before the re-read round was committed", f["reveal_slot"] < round_commit,
              f"slot {f['reveal_slot']:,} then {round_commit:,}")
        # Whether each was one of its own round's picks is what the earlier
        # proofs check; here, every reading of the service on chain is weighed.
        others = readings_of(service, program)
        for a, r in others.items():
            r["counts"] = r["state"] == 1 and holds_its_nonce(a, program)
        before = sum(1 for r in others.values() if r["counts"] and r["reveal_slot"] < round_commit)
        check("it is the latest reading of the service that counts, as 3.2 orders them",
              latest(others, round_commit) == first_address, f"{before} counting reading(s) of it before the round")

        pair_address, _ = find_pda([b"pair", b58decode(second_address)], program)
        pa = account(pair_address)
        check("the pair is recorded on chain", pa is not None, pair_address)
        if pa is None:
            continue
        pb = pa["bytes"]
        check("the pair names these two readings", b58encode(pb[8:40]) == first_address and b58encode(pb[40:72]) == second_address)
        got = pb[72]
        check("the recorded outcome follows 3.3 from the two verdicts", got == outcome(f["verdict"], s["verdict"]),
              f"{NAMES[f['verdict']]} then {NAMES[s['verdict']]}: {OUTCOMES.get(got, 'not settled')}")
        check("the outcome is the one this proof expects", OUTCOMES.get(got) == want)

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

"""Re-check readings of drawn services against Solana devnet.

    python verify.py

Python 3.8+, standard library only. For each folder under readings/, it
reads the question's and the reply's exact bytes and checks them against the
reading recorded on chain, as sasona-protocol SPEC.md 2.7 asks.
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
    with urllib.request.urlopen(req, timeout=30) as r:
        reply = json.load(r)
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

    draw = json.loads((HERE.parent / "part-2-draw" / "proof.json").read_text())
    picks = draw["picks"]

    for name in PROOF["readings"]:
        folder = HERE / "readings" / name
        meta = json.loads((folder / "reading.json").read_text())
        question = (folder / "question.json").read_bytes()
        reply = (folder / "reply.bin").read_bytes()
        print(f"\nreading: {name}   {meta['service']}")

        check("the service is, byte for byte, one of the round's picks",
              meta["round"] == draw["round"] and meta["service"] in picks)
        address, _ = find_pda([b"reading", b58decode(meta["round"]), hashlib.sha256(meta["service"].encode()).digest()], program)
        acc = account(address)
        check("is recorded on chain at the address for that round and service", acc is not None, address)
        if acc is None:
            continue
        b = acc["bytes"]
        n = struct.unpack_from("<I", b, 40)[0]
        endpoint = b[44:44 + n].decode()
        at = 44 + n
        reader = b58encode(b[at:at + 32]); at += 32
        q_hash = b[at:at + 32]; at += 32
        commit_slot = struct.unpack_from("<Q", b, at)[0]; at += 8
        state = b[at]; at += 1
        r_hash = b[at:at + 32]; at += 32
        verdict = b[at]; at += 1
        reveal_slot = struct.unpack_from("<Q", b, at)[0]

        check("names the same service", endpoint == meta["service"])
        check("was revealed after it was committed", state == 1 and reveal_slot > commit_slot,
              f"slot {commit_slot:,} then {reveal_slot:,}")
        nonce = meta["nonce"]
        check("the question shown is the fair one for its nonce", question == canonical(nonce))
        check("the question hashes to what was committed before the call", hashlib.sha256(question).digest() == q_hash)
        owner, _ = find_pda([b"nonce", bytes.fromhex(nonce)], program)
        o = account(owner)
        check("the nonce belongs to this reading", o is not None and b58encode(o["bytes"][8:40]) == address)
        check("the reply shown hashes to what was recorded", hashlib.sha256(reply).digest() == r_hash,
              f"{len(reply)} bytes")
        check("the verdict rule on that reply gives the recorded verdict", verdict_of(reply, nonce) == verdict,
              NAMES.get(verdict, "?"))
        check("the recorded verdict is the one this proof expects", NAMES.get(verdict) == PROOF["readings"][name])

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

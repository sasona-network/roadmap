"""Check part 8 on Solana devnet: a payment channel between an agent and the
node that buys for it, five purchases paid to the merchant at once, one
payment out of the channel against the largest voucher, and the markup.

    python verify.py

Python 3.8+, standard library only. Every amount is read from the chain's
transactions; the vouchers are checked here against the signer's key.
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

USD = PROOF["usd"]
DOLLAR = 1_000_000
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




def u64(b, at):
    return struct.unpack_from("<Q", b, at)[0]


def tx(signature):
    return rpc("getTransaction", [signature, {"encoding": "json", "commitment": "finalized",
                                             "maxSupportedTransactionVersion": 0}])


def token_changes(t):
    """What each owner's dollar account gained or lost in a transaction."""
    out = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in t["meta"][side]:
            if b["mint"] == USD:
                out[b["owner"]] = out.get(b["owner"], 0) + sign * int(b["uiTokenAmount"]["amount"])
    return {k: v for k, v in out.items() if v}


def instructions_of(t):
    keys = t["transaction"]["message"]["accountKeys"]
    return [(keys[i["programIdIndex"]], b58decode(i["data"]), [keys[a] for a in i["accounts"]])
            for i in t["transaction"]["message"]["instructions"]]


def event(t, name):
    """The first event `name` the program emitted in a transaction."""
    d = hashlib.sha256(f"event:{name}".encode()).digest()[:8]
    for line in t["meta"]["logMessages"]:
        if line.startswith("Program data: "):
            b = base64.b64decode(line[len("Program data: "):])
            if b[:8] == d:
                return b[8:]
    return None


# ------------------------------------------------- sasona-protocol section 8

MARKUP_POINTS = 15
VOUCHER_DOMAIN = b"sasona/voucher/v1"
DEVNET = 1


def markup(price):
    return -(-MARKUP_POINTS * price // 100)


def voucher_message(program, channel, amount):
    return VOUCHER_DOMAIN + b58decode(program) + bytes([DEVNET]) + b58decode(channel) + amount.to_bytes(8, "big")


# RFC 8032 ed25519 verification, as in sasona-protocol reference/channel.py,
# so that the vouchers can be checked here with nothing installed.
_p = 2**255 - 19
_d = -121665 * pow(121666, _p - 2, _p) % _p
_q = 2**252 + 27742317777372353535851937790883648493


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % _p, (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C, D = 2 * P[3] * Q[3] * _d % _p, 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _recover_x(y, sign):
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * pow(2, (_p - 1) // 4, _p) % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * pow(5, _p - 2, _p) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _point(s):
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def ed25519_verify(public, message, signature):
    A, R = _point(public), _point(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if A is None or R is None or s >= _q:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _q
    left, right = _mul(s, _G), _add(R, _mul(h, A))
    return (left[0] * right[2] - right[0] * left[2]) % _p == 0 and (left[1] * right[2] - right[1] * left[2]) % _p == 0


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

    agent, node, merchant, signer = PROOF["agent"], PROOF["node"], PROOF["merchant"], PROOF["signer"]
    T = PROOF["transactions"]
    pool = find_pda([b"pool"], program)[0]

    print("\nthe channel")
    channel, _ = find_pda([b"channel", b58decode(agent), b58decode(node), (0).to_bytes(8, "little")], program)
    check("its address is the agent's first channel to the node", channel == PROOF["channel"], channel)
    t = tx(T["open"])
    e = event(t, "ChannelOpened")
    opened = e and (b58encode(e[0:32]), b58encode(e[32:64]), b58encode(e[64:96]), b58encode(e[96:128]), u64(e, 128))
    check("the agent opened it for the node, with $2, and a signer of its own",
          opened == (channel, agent, node, signer, 2 * DOLLAR) and signer not in (agent, node))
    check("the signer signed the opening", signer in t["transaction"]["message"]["accountKeys"][:t["transaction"]["message"]["header"]["numRequiredSignatures"]])
    check("the $2 went into the program, not to anybody", token_changes(t) == {agent: -2 * DOLLAR, channel: 2 * DOLLAR})

    print("\nfive purchases, each paid to the merchant at once")
    vouchers = HERE / "vouchers"
    last_slot = 0
    for n in range(1, 6):
        t = tx((vouchers / f"paid-{n}.txt").read_text().strip())
        check(f"purchase {n}: the node paid the merchant a cent", token_changes(t) == {node: -10_000, merchant: 10_000})
        last_slot = max(last_slot, t["slot"])
        sig = bytes.fromhex((vouchers / f"{n * 10_000}.txt").read_text().strip())
        check(f"voucher {n}: the signer's, for everything owed so far, {n * 10_000} units",
              ed25519_verify(b58decode(signer), voucher_message(program, channel, n * 10_000), sig))

    print("\nthe node takes payment once, with the largest voucher")
    t = tx(T["take"])
    check("after all five purchases", t["slot"] > last_slot)
    ixs = instructions_of(t)
    ed = [i for i, (pid, _, _) in enumerate(ixs) if pid == "Ed25519SigVerify111111111111111111111111111"]
    ours = [i for i, (pid, _, _) in enumerate(ixs) if pid == program]
    check("the signature check is the instruction just before the program's", len(ed) == 1 and ours == [ed[0] + 1])
    if ed:
        d = ixs[ed[0]][1]
        at = lambda i: int.from_bytes(d[i:i + 2], "little")
        key, msg = d[at(6):at(6) + 32], d[at(10):at(10) + at(12)]
        check("it checks one signature, by the signer, over the 90 bytes for 50,000 units",
              d[0] == 1 and b58encode(key) == signer and msg == voucher_message(program, channel, 50_000)
              and ed25519_verify(key, msg, d[at(2):at(2) + 64]))
    e = event(t, "ChannelPaid")
    check("the node was paid 50,000 units, and 7,500 of markup is owed", token_changes(t) == {channel: -50_000, node: 50_000}
          and e is not None and (u64(e, 32), u64(e, 40), u64(e, 48)) == (50_000, 50_000, markup(50_000)))

    print("\nthe markup")
    t = tx(T["sweep"])
    check("the sweep moved the 7,500 to the network's fee account", token_changes(t) == {channel: -7_500, pool: 7_500})
    t = tx(T["buy"])
    check("a covered purchase pays its markup too: $0.15 on $1",
          token_changes(t) == {agent: -(DOLLAR + 15_000 + 150_000), merchant: DOLLAR, PROOF["quoter"]: 15_000, pool: 150_000})
    t = tx(T["settle"])
    e = event(t, "MarkupSettled")
    check("both were turned into coin, 5 of the 15 points kept in the pool",
          e is not None and u64(e, 0) == 157_500 and u64(e, 8) == 52_500)

    print("\nthe close")
    t = tx(T["close"])
    check("the node closed it, and the agent got back $2 less the 50,000 and its markup",
          token_changes(t) == {channel: -(2 * DOLLAR - 57_500), agent: 2 * DOLLAR - 57_500})
    check("the channel and its account are gone", account(channel) is None
          and account(find_pda([b"channel_usd", b58decode(channel)], program)[0]) is None)

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

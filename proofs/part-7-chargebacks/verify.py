"""Check part 7 on Solana devnet: a covered reading, two purchases, and the
two chargebacks, as sasona-protocol SPEC.md section 7 settles them.

    python verify.py

Python 3.8+, standard library only. Every number is read from the chain or
recomputed here; the files in readings/ are only the questions and replies.
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
    reply = reply[:10_000]
    if not reply:
        return 3
    return 1 if expected(nonce).encode("ascii") in reply else 2


NAMES = {1: "delivered", 2: "wrong_answer", 3: "empty"}


# ------------------------------------------------- sasona-protocol section 4

def seat_drawn(final, service, attempt, members):
    message = b"reader" + hashlib.sha256(service.encode("ascii")).digest() + attempt.to_bytes(4, "big")
    return 1 + int.from_bytes(hmac.new(final, message, hashlib.sha256).digest(), "big") % members


# --------------------------------------------------------------- accounts

def u32(b, at):
    return struct.unpack_from("<I", b, at)[0]


def u64(b, at):
    return struct.unpack_from("<Q", b, at)[0]


def i64(b, at):
    return struct.unpack_from("<q", b, at)[0]


def members_of(program):
    b = account(find_pda([b"members"], program)[0])["bytes"]
    return {"count": u32(b, 8), "seated": u32(b, 12)}


def member(program, number):
    a = account(find_pda([b"member", struct.pack("<I", number)], program)[0])
    if a is None:
        return None
    b = a["bytes"]
    return {"owner": b58encode(b[8:40]), "number": u32(b, 40), "seat": u32(b, 44), "state": b[48],
            "stake": u64(b, 49), "leave_at": i64(b, 57), "open_challenges": u32(b, 65)}


def seat(program, k):
    b = account(find_pda([b"seat", struct.pack("<I", k)], program)[0])["bytes"]
    return {"member": u32(b, 8), "owner": b58encode(b[12:44]), "since": u64(b, 44)}


def reading_at(address):
    a = account(address)
    if a is None:
        return None
    b = a["bytes"]
    n = u32(b, 40)
    at = 44 + n
    r = {"round": b58encode(b[8:40]), "endpoint": b[44:at].decode()}
    r["reader"] = b58encode(b[at:at + 32]); at += 32
    r["question_hash"] = b[at:at + 32]; at += 32
    r["commit_slot"] = u64(b, at); at += 8
    r["state"] = b[at]; at += 1
    r["reply_hash"] = b[at:at + 32]; at += 32
    r["verdict"] = b[at]; at += 1
    r["reveal_slot"] = u64(b, at); at += 8
    at += 1  # bump
    r["member"] = u32(b, at); at += 4
    r["reveal_time"] = i64(b, at)
    return r


def token_amount(address):
    a = account(address)
    return u64(a["bytes"], 64) if a else 0


def reading_pay_to(address):
    b = account(address)["bytes"]
    at = 44 + u32(b, 40) + 32 + 32 + 8 + 1 + 32 + 1 + 8 + 1 + 4 + 8
    return b58encode(b[at:at + 32])


def purchase_at(address):
    a = account(address)
    if a is None:
        return None
    b = a["bytes"]
    return {"buyer": b58encode(b[8:40]), "id": u64(b, 40), "reading": b58encode(b[48:80]), "member": u32(b, 80),
            "service": b[84:116], "price": u64(b, 116), "premium": u64(b, 124), "counted": u64(b, 132),
            "made_time": i64(b, 140), "state": b[156]}


def chargeback_at(address):
    a = account(address)
    if a is None:
        return None
    b = a["bytes"]
    return {"purchase": b58encode(b[8:40]), "buyer": b58encode(b[40:72]), "quoter": b58encode(b[72:104]),
            "member": u32(b, 104), "service": b[108:140], "price": u64(b, 140), "deposit": u64(b, 148),
            "made_time": i64(b, 156), "draw": b[164], "counted_draws": b[165], "draw_slot": u64(b, 166),
            "draw_members": u32(b, 174), "seed": b[178:210], "entropy_slot": u64(b, 210),
            "declined": [u32(b, 218 + 4 * i) for i in range(8)], "state": b[250], "owed_coins": u64(b, 251)}


def token_changes(signature):
    """What each owner's dollar account gained or lost in a transaction."""
    tx = rpc("getTransaction", [signature, {"encoding": "json", "commitment": "finalized",
                                            "maxSupportedTransactionVersion": 0}])
    out = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for t in tx["meta"][side]:
            if t["mint"] == USD:
                out[t["owner"]] = out.get(t["owner"], 0) + sign * int(t["uiTokenAmount"]["amount"])
    return out, tx["meta"]["err"]


# ------------------------------------------------- sasona-protocol section 7

FEE_BPS = 500
THIRTY_DAYS = 30 * 24 * 60 * 60
MAX_READER_ATTEMPTS = 64


def fee(price):
    return price * FEE_BPS // 10_000


def replay_drawn(c, service, seats):
    """7.4: the membership the draw gives, passing over the buyer's and the
    quoter's seats, those of memberships that declined, and seats sat in
    after the draw."""
    declined = set(c["declined"][:c["counted_draws"]])
    for attempt in range(MAX_READER_ATTEMPTS):
        k = seat_drawn(c["seed"], service, attempt, c["draw_members"])
        if k > len(seats):
            continue
        s = seats[k - 1]
        if s["since"] < c["draw_slot"] and s["owner"] not in (c["buyer"], c["quoter"]) and s["member"] not in declined:
            return s["member"]
    return None


def check_reply(folder, r):
    q = json.loads((folder / "reading.json").read_text())
    question = (folder / "question.json").read_bytes()
    reply = (folder / "reply.bin").read_bytes()
    check("its question is the one the protocol builds from its nonce", question == canonical(q["nonce"]))
    check("the question's hash is the one committed", hashlib.sha256(question).digest() == r["question_hash"])
    check("the reply's hash is the one revealed", hashlib.sha256(reply).digest() == r["reply_hash"])
    v = verdict_of(reply, q["nonce"])
    check(f"the reply gives the verdict revealed: {NAMES[v]}", v == r["verdict"])


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

    roster = members_of(program)
    seats = [seat(program, k) for k in range(1, roster["seated"] + 1)]

    # The reading that covers the purchases.
    print("\nthe reading")
    candidates = [l.strip() for l in (HERE / "list.txt").read_text().splitlines() if l.strip()]
    service = candidates[0]
    rnd, _ = find_pda([b"round", fingerprint(candidates)], program)
    rb = account(rnd)["bytes"]
    final, members_then = rb[191:223], u32(rb, 224)
    check("its round's list is list.txt, and the draw picks the service", draw(candidates, final, 1) == [service])
    reading, _ = find_pda([b"reading", b58decode(rnd), hashlib.sha256(service.encode()).digest()], program)
    check("the reading is the one proof.json names", reading == PROOF["reading"], reading)
    r = reading_at(reading)
    check("it was revealed", r["state"] == 1)
    check_reply(HERE / "readings" / "reading", r)
    m = member(program, r["member"])
    drawn = next((seat_drawn(final, service, a, members_then) for a in range(MAX_READER_ATTEMPTS)
                  if seat_drawn(final, service, a, members_then) <= len(seats)), None)
    check(f"membership {r['member']} took it, with its own key, in the seat drawn",
          m["owner"] == r["reader"] and drawn is not None and seats[drawn - 1]["member"] == r["member"])
    pay_to = reading_pay_to(reading)
    check("it records where the service asked to be paid", pay_to == PROOF["merchant"], pay_to)

    qb = account(find_pda([b"quote", b58decode(reading)], program)[0])["bytes"]
    rate = struct.unpack_from("<H", qb, 44)[0]
    check(f"its member quoted it: {rate} bps", u32(qb, 40) == r["member"] and rate == PROOF["rate"])

    # The purchases.
    owed = 0
    for name, p in PROOF["purchases"].items():
        print(f"\npurchase {name}: {p['story']}")
        address, _ = find_pda([b"purchase", b58decode(PROOF["buyer"]), struct.pack("<Q", p["id"])], program)
        check("the purchase is at the buyer's own address for its id", address == p["address"], address)
        pu = purchase_at(address)
        check("it is covered by the reading, at the quote's rate",
              pu["reading"] == reading and pu["member"] == r["member"]
              and pu["premium"] == pu["price"] * rate // 10_000 and pu["counted"] == pu["price"] + fee(pu["price"]),
              f"price {pu['price'] / 1e6:.2f}, premium {pu['premium'] / 1e6:.4f}")
        moved, err = token_changes(p["buy"])
        check("the buyer paid the price to the merchant and the premium to the member who quoted",
              err is None and moved.get(PROOF["merchant"]) == pu["price"]
              and moved.get(m["owner"]) == pu["premium"]
              and moved.get(PROOF["buyer"]) == -(pu["price"] + pu["premium"]))

        cb, _ = find_pda([b"chargeback", b58decode(address)], program)
        c = chargeback_at(cb)
        check("it was charged back, by its buyer", c is not None and c["buyer"] == PROOF["buyer"] and c["purchase"] == address)
        check("within 7 days of the purchase", c["made_time"] <= pu["made_time"] + 7 * 24 * 60 * 60)
        if p["free"]:
            check("it needed no deposit: the first on the service", c["deposit"] == 0)
        else:
            first = chargeback_at(find_pda([b"chargeback", b58decode(PROOF["purchases"][p["after"]]["address"])],
                                           program)[0])
            check("it needed the 5% deposit: another was made on the service in the 30 days before",
                  c["deposit"] == fee(c["price"]) and c["made_time"] < first["made_time"] + THIRTY_DAYS)

        replay, _ = find_pda([b"reading", b58decode(cb), bytes([c["draw"]])], program)
        rp = reading_at(replay)
        check("the replay was revealed", rp is not None and rp["state"] == 1, replay)
        check_reply(HERE / "readings" / f"replay-{name}", rp)
        who = replay_drawn(c, service, seats)
        check(f"membership {rp['member']} replayed it: the one the draw gives, passing over the buyer and the quoter",
              who == rp["member"] and member(program, rp["member"])["owner"] == rp["reader"])

        check("the chargeback is settled", c["state"] == 1)
        moved, err = token_changes(p["settle"])
        f = fee(c["price"])
        if rp["verdict"] == 1:
            want = {rp["reader"]: f}
            if c["deposit"] == 0:
                say = "the replay delivered: the buyer gets nothing back, the replayer 5% from the cover"
            else:
                say = "the replay delivered: the deposit went to the replayer"
        else:
            want = {PROOF["buyer"]: c["price"] + c["deposit"], rp["reader"]: f}
            say = "the replay did not deliver: the buyer got the price and the deposit back, the replayer 5%"
        people = {PROOF["buyer"], rp["reader"], PROOF["merchant"]}
        got = {k: v for k, v in moved.items() if k in people and v}
        check(say, err is None and got == {k: v for k, v in want.items() if v}, json.dumps(got))
        check("the member who quoted owes the cover what it paid", c["owed_coins"] > 0, f"{c['owed_coins'] / 1e6:.2f} coins")
        owed += c["owed_coins"]

    print("\nwhat the member who quoted owes")
    bb = account(find_pda([b"book", struct.pack("<I", r["member"])], program)[0])["bytes"]
    check("their book holds both debts, until the reading can no longer be challenged", u64(bb, 20) == owed,
          f"{u64(bb, 20) / 1e6:.2f} coins")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

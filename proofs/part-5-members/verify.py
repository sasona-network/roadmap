"""Re-check members, drawn readers and challenges against Solana devnet.

    python verify.py

Python 3.8+, standard library only. It rebuilds the round's draw from
list.txt, checks the roster, then each reading under readings/ as
sasona-protocol SPEC.md 2.7, 4.3 and 5.5 ask.
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


def challenge_of(program, reading):
    a = account(find_pda([b"challenge", b58decode(reading)], program)[0])
    if a is None:
        return None
    b = a["bytes"]
    return {"challenger": b58encode(b[40:72]), "deadline": i64(b, 72), "state": b[80]}


def evidence_of(program, reading):
    a = account(find_pda([b"evidence", b58decode(reading)], program)[0])
    if a is None:
        return None
    b = a["bytes"]
    n = u32(b, 41)
    return {"sealed": b[40] == 1, "reply": b[45:45 + n]}


def token_amount(address):
    a = account(address)
    return u64(a["bytes"], 64) if a else 0


MEMBER_STATES = {0: "active", 1: "leaving", 2: "left", 3: "lost its stake"}
CHALLENGE_STATES = {0: "open", 1: "answered", 2: "upheld"}


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

    print("\nthe members")
    ms = members_of(program)
    print(f"        {ms['count']} memberships taken, {ms['seated']} seated")
    stakes = 0
    for n in range(1, ms["count"] + 1):
        m = member(program, n)
        if m["state"] in (0, 1):
            stakes += m["stake"]
        print(f"        membership {n}: {m['owner'][:8]}..., {MEMBER_STATES[m['state']]}, seat {m['seat'] or '-'}")
    gaps = [k for k in range(1, ms["seated"] + 1) if seat(program, k)["member"] == 0]
    check("every seat on the roster holds a membership", not gaps, f"seats 1 to {ms['seated']}")
    agree = all(member(program, seat(program, k)["member"])["seat"] == k for k in range(1, ms["seated"] + 1))
    check("each membership seated knows its seat, and is active", agree and all(
        member(program, seat(program, k)["member"])["state"] == 0 for k in range(1, ms["seated"] + 1)))
    vault = token_amount(find_pda([b"stakes"], program)[0])
    check("the stakes vault holds every stake still owed", vault == stakes, f"{vault / 1e6:,.0f} coins")

    print("\nthe round")
    candidates = [line.strip() for line in (HERE / "list.txt").read_text().splitlines() if line.strip()]
    round_address, _ = find_pda([b"round", fingerprint(candidates)], program)
    acc = account(round_address)
    check("exists at the address derived from list.txt", acc is not None, round_address)
    if acc is None:
        print()
        print(f"{failures} check(s) failed")
        sys.exit(1)
    b = acc["bytes"]
    count = struct.unpack_from("<H", b, 76)[0]
    commit_slot, seed, entropy, final = u64(b, 110), b[119:151], b[159:191], b[191:223]
    members_then = u32(b, 224)
    check("was drawn, from the seed committed", b[118] == 1 and hashlib.sha256(seed).digest() == b[78:110])
    check("the final seed is sha256(domain, seed, entropy)", hashlib.sha256(DOMAIN + seed + entropy).digest() == final)
    picks = draw(candidates, final, count)
    check("re-running the draw gives the published picks", picks == PROOF["picks"])
    check("its roster had the seats recorded", members_then == PROOF["members_then"], f"M = {members_then}")
    unchanged = all(seat(program, k)["since"] < commit_slot for k in range(1, ms["seated"] + 1)) and ms["seated"] == members_then

    for name in PROOF["readings"]:
        folder = HERE / "readings" / name
        meta = json.loads((folder / "reading.json").read_text())
        question = (folder / "question.json").read_bytes()
        reply = (folder / "reply.bin").read_bytes()
        service = meta["service"]
        print(f"\nreading: {name}   {service}")
        address, _ = find_pda([b"reading", b58decode(round_address), hashlib.sha256(service.encode()).digest()], program)
        r = reading_at(address)
        check("is on chain for this round and service", r is not None and service in picks, address)
        if r is None:
            continue
        nonce = meta["nonce"]
        check("the question is the fair one for its nonce, and was committed", question == canonical(nonce)
              and hashlib.sha256(question).digest() == r["question_hash"])
        o = account(find_pda([b"nonce", bytes.fromhex(nonce)], program)[0])
        check("the nonce belongs to this reading", o is not None and b58encode(o["bytes"][8:40]) == address)
        check("the reply shown hashes to what was recorded", hashlib.sha256(reply).digest() == r["reply_hash"])
        m = member(program, r["member"]) if r["member"] else None
        check("was taken by a member, with that member's key", m is not None and m["owner"] == r["reader"],
              f"membership {r['member']}")
        if unchanged:
            # Nobody has sat down or left since the round, so today's roster is the one it was read from.
            want = None
            for a in range(16):
                k = seat_drawn(final, service, a, members_then)
                if k <= ms["seated"]:
                    want = seat(program, k)["member"]
                    break
            check("it is the membership the draw gives (4.3)", want == r["member"], f"membership {want}")
        else:
            print("        the roster has changed since the round, so the draw was checked by the program when the reading was committed")
        rule = verdict_of(reply, nonce)
        if name in PROOF.get("false", []):
            check("its recorded verdict does not follow from its own reply, as intended",
                  rule != r["verdict"], f"recorded {NAMES[r['verdict']]}, the rule gives {NAMES[rule]}")
        else:
            check("the verdict rule on that reply gives the recorded verdict", rule == r["verdict"], NAMES[r["verdict"]])

        c = challenge_of(program, address)
        if name in PROOF.get("challenges", {}):
            want = PROOF["challenges"][name]
            check("was challenged", c is not None, CHALLENGE_STATES.get(c["state"]) if c else "")
            if c is None:
                continue
            if want == "answered":
                e = evidence_of(program, address)
                check("the challenge was answered", c["state"] == 1)
                check("the reply on chain is sealed, and is the one recorded", e is not None and e["sealed"]
                      and hashlib.sha256(e["reply"]).digest() == r["reply_hash"], f"{len(e['reply']) if e else 0} bytes")
                check("the verdict rule on the reply on chain gives the recorded verdict",
                      e is not None and verdict_of(e["reply"], nonce) == r["verdict"])
            else:
                print(f"        deadline {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(c['deadline']))}")
                if c["state"] == 2:
                    check("the challenge was upheld, and the reading no longer counts", r["state"] == 3)
                    check("the membership lost its stake", m is not None and m["state"] == 3 and m["stake"] == 0)
                else:
                    check("no answer can hold: the member's own reply gives another verdict", rule != r["verdict"])
                    print("        not upheld yet: that can only happen after the deadline")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

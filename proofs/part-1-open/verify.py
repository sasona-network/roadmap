"""Check the opened Sasona pool against Solana devnet.

    python verify.py

Python 3.8+, standard library only. It reads proof.json next to it for the
program address and the transaction, then asks devnet directly. Nothing here
trusts our description: every address is derived again from the program, and
every number is read from the chain.
"""

import base64
import hashlib
import json
import struct
import sys
import urllib.request
from pathlib import Path

PROOF = json.loads((Path(__file__).parent / "proof.json").read_text())
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


def token_amount(address):
    return struct.unpack_from("<Q", account(address)["bytes"], 64)[0]


# ------------------------------------------------------------------ checks

def main():
    program = PROOF["program"]
    print(f"\nprogram {program}  on {RPC}\n")

    pool, _ = find_pda([b"pool"], program)
    coin, _ = find_pda([b"coin"], program)
    pool_usd, _ = find_pda([b"pool-usd"], program)
    pool_coin, _ = find_pda([b"pool-coin"], program)
    fees, _ = find_pda([b"fees"], program)

    print("the program")
    prog = account(program)
    check("is deployed and executable", prog is not None and prog["executable"])
    check("is owned by the upgradeable loader", prog["owner"] == UPGRADEABLE_LOADER)
    programdata = b58encode(prog["bytes"][4:36])
    pd = account(programdata)["bytes"]
    # programdata: 4-byte kind, 8-byte slot, then a 1-byte flag and the authority
    authority = b58encode(pd[13:45]) if pd[12] == 1 else None
    size = PROOF["binary"]["bytes"]
    deployed = hashlib.sha256(pd[45:45 + size]).hexdigest()
    check("runs the binary we published", deployed == PROOF["binary"]["sha256"], deployed[:16] + "…")
    print(f"        upgrade authority: {authority or 'none'}")
    print("        (on devnet the program can still be upgraded by that key; this is stated, not hidden)")

    print("\nthe coin")
    m = account(coin)
    check("exists at the address derived from the program", m is not None, coin)
    check("is a token of the standard token program", m["owner"] == TOKEN_PROGRAM)
    d = m["bytes"]
    mint_authority = option_key(d, 0)
    supply = struct.unpack_from("<Q", d, 36)[0]
    decimals = d[44]
    freeze_authority = option_key(d, 46)
    check("can only be minted by the pool", mint_authority == pool, str(mint_authority))
    check("nobody can sign for the pool's address", not on_curve(b58decode(pool)))
    check("nobody can freeze it", freeze_authority is None)
    check("has 6 decimals", decimals == 6)

    print("\nthe pool")
    pa = account(pool)
    check("is owned by the program", pa is not None and pa["owner"] == program)
    b = pa["bytes"]
    usd_mint = b58encode(b[9:41])
    coin_mint = b58encode(b[41:73])
    usd_reserve, coin_reserve, outside, fees_held = struct.unpack_from("<QQQQ", b, 73)
    check("records the coin it controls", coin_mint == coin)
    check("records the dollar it was opened with", usd_mint == PROOF["usd_mint"], usd_mint)
    check("every coin is in the pool or outside it", supply == coin_reserve + outside,
          f"{supply / 1e6:,.0f} = {coin_reserve / 1e6:,.0f} + {outside / 1e6:,.0f} coins")
    check("its coin account holds what it records", token_amount(pool_coin) == coin_reserve)
    check("its dollar account holds what it records", token_amount(pool_usd) == usd_reserve,
          f"${usd_reserve / 1e6:,.2f}")
    check("its fee account holds what it records", token_amount(fees) == fees_held,
          f"${fees_held / 1e6:,.2f}")

    print("\nthe opening transaction")
    tx = rpc("getTransaction", [PROOF["open_tx"], {"encoding": "json", "commitment": "finalized",
                                                   "maxSupportedTransactionVersion": 0}])
    check("is final on devnet", tx is not None)
    check("succeeded", tx["meta"]["err"] is None)
    keys = tx["transaction"]["message"]["accountKeys"]
    check("called this program", program in keys)
    check("created the coin", coin in keys)

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

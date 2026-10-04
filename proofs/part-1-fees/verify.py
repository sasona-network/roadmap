"""Check fees paid into the Sasona pool against Solana devnet.

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
import time
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


def token_amount(address):
    return struct.unpack_from("<Q", account(address)["bytes"], 64)[0]


# ------------------------------------------------------------- one fee tx

def fee_checks(tx, kind, program, pool_usd, pool_coin, fees, network):
    """Check one fee or settle transaction from its own balances and burns."""
    keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    meta = tx["meta"]
    check("called this program", program in keys)

    def balance(which, address):
        for b in meta[which]:
            if keys[b["accountIndex"]] == address:
                return int(b["uiTokenAmount"]["amount"])
        return 0

    def delta(address):
        return balance("postTokenBalances", address) - balance("preTokenBalances", address)

    burned = sum(int(ix["parsed"]["info"]["amount"])
                 for group in meta["innerInstructions"] for ix in group["instructions"]
                 if ix.get("program") == "spl-token" and ix.get("parsed", {}).get("type") == "burn")
    out = -delta(pool_coin)
    shared = delta(network)
    usd_before = balance("preTokenBalances", pool_usd)
    coins_before = balance("preTokenBalances", pool_coin)

    if kind == "fee":
        markup = delta(pool_usd)
        payer = keys[0]
        paid = sum(int(b["uiTokenAmount"]["amount"]) * (1 if which == "preTokenBalances" else -1)
                   for which in ("preTokenBalances", "postTokenBalances") for b in meta[which]
                   if b.get("owner") == payer and b["mint"] == PROOF["usd_mint"])
        reserve = markup * 5 // 15
        buy = markup - reserve
        check("the payer paid exactly what the pool received", paid == markup, f"${markup / 1e6:,.6f}")
    else:
        markup = -delta(fees)
        reserve = 0
        buy = markup
        check("the waiting entry fees moved into the pool", delta(pool_usd) == markup, f"${markup / 1e6:,.2f}")
    burn_usd = min(-(-markup * 300 // 10_000), buy)      # three percent, rounded up

    # The pool's dollar account held nothing beyond its records, so its balance
    # before is the reserve the price was read from.
    # The reserve goes in first, so the buy is priced against the deeper pool.
    expected = coins_before * buy // (usd_before + reserve + buy)
    check("coins bought match the pool's price, with the reserve not spent", out == expected,
          f"{out / 1e6:,.6f} coins for ${buy / 1e6:,.6f}")
    check("3% of the markup's coin was burned, rounded up", burned == -(-out * burn_usd // buy),
          f"{burned / 1e6:,.6f} coins")
    check("the rest went to the network", shared == out - burned, f"{shared / 1e6:,.6f} coins")
    if reserve:
        print(f"        kept in the pool as depth: ${reserve / 1e6:,.6f}")


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
    # The program is upgraded as the roadmap moves on, so the check is that it
    # runs one of the binaries we published, each tied to its source.
    published = json.loads((Path(__file__).parent.parent / "binaries.json").read_text())
    running = next((b for b in published
                    if hashlib.sha256(pd[45:45 + b["bytes"]]).hexdigest() == b["sha256"]
                    and not any(pd[45 + b["bytes"]:])), None)
    check("runs a binary we published", running is not None,
          f'from {running["step"]}' if running else "")
    if running:
        print(f'        source: {running["source"]}')
        if running["sha256"] != PROOF["binary"]["sha256"]:
            print("        (upgraded since this proof; the checks below are still read from the chain now)")
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

    print("\nthe network's coin")
    network, _ = find_pda([b"network"], program)
    nv = account(network)
    check("sits at the address derived from the program", nv is not None, network)
    check("is held by the pool, which has no key", nv is not None and b58encode(nv["bytes"][32:64]) == pool)
    print("        (temporary: every participant seat is empty, so the network takes all of it,")
    print("         and nothing can move it out yet. Both change in later parts.)")

    for kind, sigs in (("fee", PROOF["fee_txs"]), ("settle", PROOF["settle_txs"])):
        for sig in sigs:
            print(f"\n{'a fee' if kind == 'fee' else 'settling entry fees'}  {sig[:8]}…")
            tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "finalized",
                                              "maxSupportedTransactionVersion": 0}])
            check("is final and succeeded", tx is not None and tx["meta"]["err"] is None)
            if tx is None:
                continue
            fee_checks(tx, kind, program, pool_usd, pool_coin, fees, network)

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

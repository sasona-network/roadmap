"""Check the Sasona cover, claims and releases against Solana devnet.

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

    print("\nthe cover")
    cover, _ = find_pda([b"cover"], program)
    cover_vault, _ = find_pda([b"cover-vault"], program)
    ca = account(cover)
    check("is owned by the program", ca is not None and ca["owner"] == program, cover)
    total_shares, cover_coins = struct.unpack_from("<QQ", ca["bytes"], 9)
    cv = account(cover_vault)
    check("its vault is held by the pool, which has no key", cv is not None and b58encode(cv["bytes"][32:64]) == pool)
    check("its vault holds the coins it records", token_amount(cover_vault) == cover_coins,
          f"{cover_coins / 1e6:,.0f} coins behind {total_shares / 1e6:,.0f} shares")

    held = 0
    for who in PROOF["depositors"]:
        g = account(find_pda([b"guarantee", b58decode(who)], program)[0])
        if g is None:
            check(f"{who[:8]}… has a guarantee", False)
            continue
        shares = struct.unpack_from("<Q", g["bytes"], 40)[0]
        exit_ = account(find_pda([b"exit", b58decode(who)], program)[0])
        waiting = struct.unpack_from("<Q", exit_["bytes"], 40)[0] if exit_ else 0
        held += shares + waiting
        check(f"{who[:8]}…'s guarantee is shares of the cover", b58encode(g["bytes"][8:40]) == who,
              f"{shares / 1e6:,.0f} held" + (f", {waiting / 1e6:,.0f} asked back" if waiting else ""))
        check(f"{who[:8]}…'s old vault is closed", account(find_pda([b"guarantee-vault", b58decode(who)], program)[0]) is None)
    check("every share is accounted for by these depositors", held == total_shares)

    def tx_of(sig):
        tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "finalized",
                                          "maxSupportedTransactionVersion": 0}])
        check("is final and succeeded", tx is not None and tx["meta"]["err"] is None)
        return tx

    def balances(tx):
        keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]

        def bal(which, address):
            for b in tx["meta"][which]:
                if keys[b["accountIndex"]] == address:
                    return int(b["uiTokenAmount"]["amount"])
            return 0
        return keys, bal

    for sig in PROOF["join_txs"]:
        print(f"\njoining the cover  {sig[:8]}…")
        tx = tx_of(sig)
        ops = [ix["parsed"]["type"] for g in tx["meta"]["innerInstructions"] for ix in g["instructions"]
               if ix.get("program") == "spl-token"]
        check("moved the old vault's coins and closed it", "transfer" in ops and "closeAccount" in ops, ", ".join(ops))

    for sig in PROOF["claim_txs"]:
        print(f"\na claim  {sig[:8]}…")
        tx = tx_of(sig)
        keys, bal = balances(tx)
        signers = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"] if k["signer"]]
        check("was approved by the judge key, for now the program's upgrade key", PROOF["judge"] in signers)
        paid = bal("preTokenBalances", pool_usd) - bal("postTokenBalances", pool_usd)
        usd0, coins0 = bal("preTokenBalances", pool_usd), bal("preTokenBalances", pool_coin)
        to = [keys[b["accountIndex"]] for b in tx["meta"]["postTokenBalances"]
              if b["mint"] == PROOF["usd_mint"] and keys[b["accountIndex"]] not in (pool_usd, fees)]
        got = sum(bal("postTokenBalances", a) - bal("preTokenBalances", a) for a in to)
        check("the buyer received what left the pool", got == paid and paid > 0, f"${paid / 1e6:,.2f}")
        burns = {ix["parsed"]["info"]["account"]: int(ix["parsed"]["info"]["amount"])
                 for g in tx["meta"]["innerInstructions"] for ix in g["instructions"]
                 if ix.get("program") == "spl-token" and ix["parsed"]["type"] == "burn"}
        expected = -(-paid * coins0 // usd0)
        check("the pool burned the coins behind those dollars, so the price did not fall",
              burns.get(pool_coin) == expected, f"{expected / 1e6:,.6f} coins")
        check("the cover burned the same, so the guarantees carried it", burns.get(cover_vault) == expected)

    for sig in PROOF["ask_back_txs"]:
        print(f"\nasking a guarantee back  {sig[:8]}…")
        tx = tx_of(sig)
        owner = tx["transaction"]["message"]["accountKeys"][0]["pubkey"]
        e = account(find_pda([b"exit", b58decode(owner)], program)[0])
        if e is None:
            print("        (released since)")
            continue
        shares, ready_at = struct.unpack_from("<Qq", e["bytes"], 40)
        days = (ready_at - tx["blockTime"]) / 86400
        check("waits 45 days, still paying claims", days >= 45 - 1 / 24,
              f"{shares / 1e6:,.0f} shares, ready {time.strftime('%Y-%m-%d', time.gmtime(ready_at))}")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

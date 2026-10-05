#!/usr/bin/env bash
# The part 8 run on devnet, step by step.
#
#     bash run.sh <step>
#
# The agent is the buyer key. The node that buys for it is the deployer key,
# standing in for our server. The merchant is the stand-in from part 7, paid
# at once for each purchase. Keys are read from ~/.config/sasona and never
# leave it; vouchers are signatures, not keys, and are published.
set -euo pipefail

C="${SASONA_CLIENT:-$HOME/.cache/sasona-program-build/target/release/sasona}"
K="$HOME/.config/sasona"
HERE="$(cd "$(dirname "$0")" && pwd)"
USD=ACPdQtaC6HKgT8V4GVRke57vtZrbv3zDqTwvENBoRPCy
# The covered reading from part 7, and its merchant.
READING=3bhHnFZtbdCyYbr437Qb4PchF5tCcbfm8rz3EzAT7qek
MERCHANT=HZtTgTbNVZH7CvTz1Nw3TND25PejnmpoSgErLFo9uQHC
NODE_KEY="$K/devnet-deployer.json"
cd "$HERE"

state() { python3 -c "import json,sys; print(json.load(open('state.json')).get(sys.argv[1], ''))" "$1" 2>/dev/null || true; }
save() {
    python3 - "$1" "$2" <<'EOF'
import json, sys
from pathlib import Path
p = Path("state.json")
d = json.loads(p.read_text()) if p.exists() else {}
d[sys.argv[1]] = sys.argv[2]
p.write_text(json.dumps(d, indent=1) + "\n")
EOF
}

case "$1" in
keys)
    # A key that only signs vouchers, so that the agent's own key stays out
    # of its purchases.
    [ -f "$K/channel-signer.json" ] || solana-keygen new --no-bip39-passphrase -s -o "$K/channel-signer.json" >/dev/null
    save signer "$(solana-keygen pubkey "$K/channel-signer.json")"
    save node "$(solana-keygen pubkey "$NODE_KEY")"
    ;;
open)
    "$C" open-channel "$(state node)" 0 2 --signer "$K/channel-signer.json" --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    save channel "$(grep -ao "channel [1-9A-HJ-NP-Za-km-z]*" log.txt | tail -1 | cut -d' ' -f2)"
    ;;
purchases)
    # Five purchases at a cent. For each, the node pays the merchant at
    # once, and the agent signs everything it owes the node so far.
    mkdir -p vouchers
    for n in 1 2 3 4 5; do
        spl-token transfer -u devnet --owner "$NODE_KEY" --fee-payer "$NODE_KEY" --allow-unfunded-recipient "$USD" 0.01 "$MERCHANT" 2>&1 \
            | tee -a log.txt | grep -ao "Signature: [1-9A-HJ-NP-Za-km-z]*" | cut -d' ' -f2 > "vouchers/paid-$n.txt"
        "$C" voucher "$(state channel)" $((n * 10000)) --keypair "$K/channel-signer.json" > "vouchers/$((n * 10000)).txt"
    done
    ls vouchers | tee -a log.txt
    ;;
take)
    # The node takes only the largest voucher: one transaction for five purchases.
    "$C" take-payment "$(state channel)" 50000 "$(cat vouchers/50000.txt)" --keypair "$NODE_KEY" 2>&1 | tee -a log.txt
    ;;
sweep)
    "$C" sweep-channel "$(state channel)" --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
buy)
    # A covered purchase, which now pays the markup too.
    "$C" buy "$READING" 3 1 --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
settle)
    "$C" settle-markup --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
close)
    "$C" close-channel "$(state channel)" --keypair "$NODE_KEY" 2>&1 | tee -a log.txt
    ;;
*)
    echo "steps: keys open purchases take sweep buy settle close"; exit 2
    ;;
esac

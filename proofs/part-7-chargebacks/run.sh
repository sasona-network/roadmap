#!/usr/bin/env bash
# The part 7 run on devnet, step by step. Each step is safe to run again.
#
#     bash run.sh <step>
#
# Keys are read from ~/.config/sasona and never leave it.
set -euo pipefail

C="${SASONA_CLIENT:-$HOME/.cache/sasona-program-build/target/release/sasona}"
K="$HOME/.config/sasona"
NODE="${SASONA_NODE:-$(cd "$(dirname "$0")/../../../sasona-node" && pwd)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
USD=ACPdQtaC6HKgT8V4GVRke57vtZrbv3zDqTwvENBoRPCy
SERVICE=https://runner.example.org/run/python
KEYS=(devnet-deployer depositor-2)
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
merchant)
    # Where the stand-in asks to be paid: a key of its own, with a dollar account.
    [ -f "$K/merchant.json" ] || solana-keygen new --no-bip39-passphrase -s -o "$K/merchant.json" >/dev/null
    m=$(solana-keygen pubkey "$K/merchant.json")
    spl-token create-account -u devnet --owner "$m" --fee-payer "$K/devnet-deployer.json" "$USD" || true
    save merchant "$m"
    ;;
round)
    echo "$SERVICE" > list.txt
    "$C" open-round list.txt 1 --keypair "$K/devnet-deployer.json" 2>&1 | tee -a log.txt
    sleep 30
    "$C" reveal-round list.txt --keypair "$K/devnet-deployer.json" 2>&1 | tee -a log.txt
    ;;
read)
    # The stand-in, honest, naming the merchant. Only the member drawn can read.
    round=$(grep -ao "round [1-9A-HJ-NP-Za-km-z]*" log.txt | tail -1 | cut -d' ' -f2)
    save round "$round"
    python3 "$NODE/standin/seller.py" honest 8407 "$(state merchant)" & seller=$!
    trap 'kill $seller' EXIT
    sleep 1
    for k in "${KEYS[@]}"; do
        if python3 "$NODE/reader/read.py" --round "$round" --service "$SERVICE" --send-to http://127.0.0.1:8407 \
            --client "$C" --keypair "$K/$k.json" --out readings/reading 2>&1 | tee -a log.txt; then
            save reader "$k"; break
        fi
    done
    ;;
quote)
    h=$(printf %s "$SERVICE" | sha256sum | cut -d' ' -f1)
    reading=$(solana find-program-derived-address 7eiHSnDkM4WjJdY36D2Yqsjw893mCMUtBAwMCQ5adL99 \
        string:reading pubkey:"$(state round)" hex:"$h" | awk '{print $1}')
    save reading "$reading"
    "$C" quote "$reading" 150 --keypair "$K/$(state reader).json" 2>&1 | tee -a log.txt
    ;;
buy)
    # bash run.sh buy <id>: a $1 purchase by the buyer.
    "$C" buy "$(state reading)" "$2" 1 --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
charge-back)
    p=$(grep -ao "purchase [1-9A-HJ-NP-Za-km-z]*" log.txt | sed -n "${2}p" | cut -d' ' -f2)
    save "purchase-$2" "$p"
    "$C" charge-back "$p" --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
replay)
    # bash run.sh replay <id> <honest|canned>: whoever was drawn replays.
    p=$(state "purchase-$2")
    python3 "$NODE/standin/seller.py" "$3" 8408 "$(state merchant)" & seller=$!
    trap 'kill $seller' EXIT
    sleep 1
    for k in "${KEYS[@]}"; do
        if python3 "$NODE/reader/read.py" --replay "$p" --service "$SERVICE" --send-to http://127.0.0.1:8408 \
            --client "$C" --keypair "$K/$k.json" --out "readings/replay-$2" 2>&1 | tee -a log.txt; then
            save "replayer-$2" "$k"; break
        fi
    done
    ;;
pass)
    "$C" pass-draw "$(state "purchase-$2")" --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
settle)
    "$C" settle-chargeback "$(state "purchase-$2")" --keypair "$K/buyer.json" 2>&1 | tee -a log.txt
    ;;
*)
    echo "steps: merchant round read quote buy charge-back replay pass settle"; exit 2
    ;;
esac

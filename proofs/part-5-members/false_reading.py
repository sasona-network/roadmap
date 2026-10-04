"""Take one reading and record it falsely, on purpose, to show a challenge
taking a stake.

    python false_reading.py --round <round> --service <url as drawn> \\
        --client <path to the sasona client> --keypair <path> --out <folder> \\
        --send-to <url> --reader <path to sasona-node/reader/read.py>

It does what sasona-node's reader does, except the verdict: the reply is
recorded as received, and the verdict is written as `delivered` whatever the
reply says. A member who did this could not answer a challenge, because the
verdict rule run on their own reply gives something else.

Standard library only.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import urllib.request
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    for name in ("--round", "--service", "--client", "--keypair", "--out", "--send-to", "--reader"):
        p.add_argument(name, required=True)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location("read", args.reader)
    read = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(read)

    nonce = os.urandom(16).hex()
    question = read.canonical(nonce)
    question_hash = hashlib.sha256(question).hexdigest()
    commit_tx = read.client(args, "commit-reading", args.round, args.service, question_hash)
    print(f"committed  {commit_tx}")

    body = json.dumps({"code": read.code_for(nonce), "language": "python"}).encode()
    req = urllib.request.Request(args.send_to, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        reply = r.read(read.MAX_REPLY_BYTES)
    reply_hash = hashlib.sha256(reply).hexdigest()
    honest = read.verdict(reply, nonce)
    print(f"reply      {len(reply)} bytes, really {read.VERDICTS[honest]}, recorded as delivered")

    reveal_tx = read.client(args, "reveal-reading", args.round, args.service, nonce, reply_hash, "1")
    print(f"revealed   {reveal_tx}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "question.json").write_bytes(question)
    (out / "reply.bin").write_bytes(reply)
    (out / "reading.json").write_text(json.dumps({
        "round": args.round, "service": args.service, "sent_to": args.send_to,
        "nonce": nonce, "question_hash": question_hash, "reply_hash": reply_hash,
        "verdict": 1, "verdict_the_rule_gives": honest, "commit_tx": commit_tx, "reveal_tx": reveal_tx,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()

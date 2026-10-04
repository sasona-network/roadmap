"""Check that every commit the proofs link to exists in its repository.

    python scripts/check_links.py

A proof that names a source commit is only worth something if that commit
is the one that was built. This finds every link of the form
github.com/sasona-network/<repository>/(tree|blob)/<commit> in the proofs and
the roadmap, and asks GitHub whether the commit exists.

Python 3.8+, standard library only.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"github\.com/sasona-network/([a-z0-9-]+)/(?:tree|blob)/([0-9a-f]{7,40})")


def exists(repo, commit):
    url = f"https://api.github.com/repos/sasona-network/{repo}/commits/{commit}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"}), timeout=30) as r:
                return json.load(r)["sha"].startswith(commit)
        except urllib.error.HTTPError as e:
            if e.code in (404, 422):
                return False
            if attempt == 2:
                raise
        time.sleep(3 * (attempt + 1))
    return False


def main():
    found = {}
    for path in sorted(ROOT.rglob("*")):
        if path.suffix not in (".md", ".json") or ".git" in path.parts:
            continue
        for repo, commit in LINK.findall(path.read_text(encoding="utf-8")):
            found.setdefault((repo, commit), []).append(path.relative_to(ROOT))
    bad = 0
    for (repo, commit), where in sorted(found.items()):
        ok = exists(repo, commit)
        print(("  ok    " if ok else "  FAIL  ") + f"{repo} {commit[:12]}" + ("" if ok else f"   named in {', '.join(map(str, where))}"))
        bad += not ok
    print(f"\n{len(found)} commits linked, {bad} missing" if bad else f"\nall {len(found)} linked commits exist")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

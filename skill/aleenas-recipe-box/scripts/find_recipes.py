#!/usr/bin/env python3
"""
Quick keyword lookup across Aleena's recipes.

    python3 find_recipes.py "trout"            # one term
    python3 find_recipes.py "chickpea" "lemon" # all terms must match
    python3 find_recipes.py --min-stars 4 "farro"

Searches name, instructions, tags, and notes (case-insensitive). Prints each
match with its rating, tags, and a short snippet, best-rated first.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "references", "recipes.json")


def main(argv):
    min_stars = 0
    terms = []
    i = 0
    while i < len(argv):
        if argv[i] == "--min-stars":
            min_stars = int(argv[i + 1]); i += 2
        else:
            terms.append(argv[i].lower()); i += 1
    if not terms:
        print(__doc__); return

    with open(DATA) as f:
        data = json.load(f)
    hits = []
    for r in data["recipes"]:
        hay = " ".join([r["name"], r.get("instructions", ""), " ".join(r["tags"]),
                        r.get("notes", ""), r.get("url") or ""]).lower()
        if r["stars"] >= min_stars and all(t in hay for t in terms):
            hits.append(r)
    hits.sort(key=lambda r: (-r["stars"], r["name"].lower()))

    if not hits:
        print(f"No recipes mention {' + '.join(terms)}. Try a broader term, or read "
              "references/recipes.md for substitution ideas."); return
    print(f"{len(hits)} recipe(s) matching {' + '.join(terms)}:\n")
    for r in hits:
        body = r.get("url") or re.sub(r"\s+", " ", r.get("instructions", ""))
        snippet = body if len(body) <= 160 else body[:157] + "..."
        print(f"{'★' * r['stars']:<5} {r['name']}")
        print(f"      tags: {', '.join(r['tags'][:10])}")
        print(f"      {snippet}")
        if r.get("notes"):
            n = re.sub(r"\s+", " ", r["notes"])
            print(f"      notes: {n if len(n) <= 140 else n[:137] + '...'}")
        print()


if __name__ == "__main__":
    main(sys.argv[1:])

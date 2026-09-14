#!/usr/bin/env python3
"""
Build the shareable Claude skill from the current recipe snapshot.

    python3 build_skill.py

Reads recipes-cache.json and staples.json, regenerates
skill/aleenas-recipe-box/references/{recipes.md,recipes.json}, and zips the
skill folder into dist/aleenas-recipe-box.skill (a .skill file is a zip with
the skill folder at its root). Send that file to anyone; in Claude they can
click "Save skill" to install it.
"""

import json
import os
import re
import time
import zipfile

DIR = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(DIR, "skill", "aleenas-recipe-box")
REFS = os.path.join(SKILL, "references")
DIST = os.path.join(DIR, "dist")


def load():
    with open(os.path.join(DIR, "recipes-cache.json")) as f:
        cache = json.load(f)
    try:
        with open(os.path.join(DIR, "staples.json")) as f:
            staples = sorted(json.load(f).get("staples", []))
    except OSError:
        staples = []
    return cache, staples


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render_md(cache, staples):
    recipes = sorted(cache["recipes"], key=lambda r: (-r["stars"], r["name"].lower()))
    when = time.strftime("%Y-%m-%d", time.localtime(cache.get("fetched_at", time.time())))
    st = set(staples)
    out = [f"# Aleena's Recipe Box — full collection",
           f"",
           f"Snapshot {when} · {len(recipes)} recipes · sorted best-rated first.",
           f"",
           f"**Pantry staples assumed on hand** (not listed in tags below): {', '.join(staples)}.",
           f"",
           f"## Index",
           f""]
    for stars in (5, 4, 3, 2, 1):
        names = [r["name"] for r in recipes if r["stars"] == stars]
        if names:
            out.append(f"- {'★' * stars}: " + " · ".join(names))
    out.append("")
    out.append("## Recipes")
    out.append("")
    for r in recipes:
        tags = [t for t in r["tags"] if t not in st]
        out.append(f"### {r['name']}  ·  {'★' * r['stars']}")
        if tags:
            out.append(f"Tags: {', '.join(tags)}  ")
        if r.get("url"):
            out.append(f"Recipe (link): {r['url']}  ")
        else:
            body = re.sub(r"\n{2,}", "\n", r["instructions"]).strip()
            out.append(f"Instructions: {body}  ")
        if r.get("notes"):
            notes = re.sub(r"\n{2,}", " ", r["notes"]).strip()
            out.append(f"Notes: {notes}  ")
        out.append("")
    return "\n".join(out)


def main():
    cache, staples = load()
    os.makedirs(REFS, exist_ok=True)
    with open(os.path.join(REFS, "recipes.md"), "w") as f:
        f.write(render_md(cache, staples))
    with open(os.path.join(REFS, "recipes.json"), "w") as f:
        json.dump({"snapshot": cache.get("fetched_at"), "staples": staples,
                   "recipes": cache["recipes"]}, f, ensure_ascii=False, indent=1)

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "aleenas-recipe-box.skill")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(SKILL):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
            for name in sorted(files):
                if name in (".DS_Store",) or name.endswith(".pyc"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, os.path.dirname(SKILL))
                z.write(full, rel)
    size = os.path.getsize(out) // 1024
    print(f"built {out} ({size} KB, {len(cache['recipes'])} recipes)")


if __name__ == "__main__":
    main()

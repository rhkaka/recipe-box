#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "google-api-python-client",
#   "google-auth-oauthlib",
#   "google-auth-httplib2",
# ]
# ///
"""
Build the static GitHub Pages copy of Recipe Box into docs/.

    uv run build_static.py        # then commit docs/ and push

Writes docs/index.html (the frontend with static mode switched on) and
docs/data.json (a snapshot of the recipes + staples). The hosted copy can
search, filter, and sort; it can't refresh from the sheet or use "Cook with".
"""

import json
import os
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import server  # noqa: E402

OUT = os.path.join(DIR, "docs")


def main():
    st = server.refresh(force=True, interactive=True)
    if not st["recipes"]:
        sys.exit(f"no recipes available: {st['error']}")
    os.makedirs(OUT, exist_ok=True)

    data = {
        "recipes": st["recipes"],
        "staples": server.read_staples(),
        "source": "snapshot",
        "fetched_at": st["fetched_at"] or time.time(),
        "sheet_url": server.SHEET_URL,
        "sheet_title": st["sheet_title"],
    }
    with open(os.path.join(OUT, "data.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    with open(server.HTML_FILE) as f:
        html = f.read()
    marker = "<script>\n(() => {"
    assert marker in html, "frontend script marker not found"
    html = html.replace(marker, "<script>window.RB_STATIC = true;</script>\n" + marker, 1)
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(html)
    with open(os.path.join(OUT, ".nojekyll"), "w") as f:
        f.write("")

    print(f"wrote docs/ with {len(st['recipes'])} recipes via {st['source']}")


if __name__ == "__main__":
    main()

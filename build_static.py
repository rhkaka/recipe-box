#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cryptography",
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

If RECIPE_BOX_PASSWORD is set (in the shell or recipes/.env), data.json is
encrypted with AES-256-GCM using a key derived from the password (PBKDF2,
SHA-256, 300k iterations) and the page asks for the password before showing
anything. Change the password by editing .env and rebuilding.
"""

import base64
import hashlib
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
    password = os.environ.get("RECIPE_BOX_PASSWORD", "").strip()
    if password:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt, iv, iterations = os.urandom(16), os.urandom(12), 300_000
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=32)
        plaintext = json.dumps(data, ensure_ascii=False).encode()
        ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
        payload = {
            "encrypted": True,
            "kdf": "PBKDF2-SHA256", "iterations": iterations,
            "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(iv).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }
        with open(os.path.join(OUT, "data.json"), "w") as f:
            json.dump(payload, f)
        locked = "password-protected"
    else:
        with open(os.path.join(OUT, "data.json"), "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        locked = "NOT password-protected (set RECIPE_BOX_PASSWORD in .env to lock it)"

    with open(server.HTML_FILE) as f:
        html = f.read()
    marker = "<script>\n(() => {"
    assert marker in html, "frontend script marker not found"
    html = html.replace(marker, "<script>window.RB_STATIC = true;</script>\n" + marker, 1)
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(html)
    with open(os.path.join(OUT, ".nojekyll"), "w") as f:
        f.write("")

    print(f"wrote docs/ with {len(st['recipes'])} recipes via {st['source']}, {locked}")


if __name__ == "__main__":
    main()

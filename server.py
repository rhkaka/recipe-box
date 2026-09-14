#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=1.0",
#   "google-api-python-client",
#   "google-auth-oauthlib",
#   "google-auth-httplib2",
# ]
# ///
"""
Recipe Box server.

Reads the recipe spreadsheet from Google Sheets and serves a searchable
single-page site.

Run:   uv run recipes/server.py      (installs deps on first run)
       python3 recipes/server.py    (works too, but "Cook with" needs the
                                     anthropic SDK, which needs Python 3.10+)
Open:  http://localhost:8090        (this Mac)
       http://<mac-ip>:8090         (phone on the same Wi-Fi)

Data source order (first one that works wins):
  1. Google Sheets API using the OAuth desktop credentials in
     ../ledger/credentials.json (or recipes/credentials.json). The token is
     cached at ~/.recipes/token.json; an existing ~/.practice-dashboard
     token is reused if present so no new consent screen is needed.
  2. Public CSV export (only works if the sheet is shared "anyone with link").
  3. recipes/recipes-cache.json, written after every successful fetch.

"Cook with X" suggestions call Claude (claude-opus-5) and need
ANTHROPIC_API_KEY set in the environment.
"""

import csv
import io
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingredients import tag_text  # noqa: E402
import ai  # noqa: E402

PORT = int(os.environ.get("PORT", "8090"))
SHEET_ID = os.environ.get(
    "SHEET_ID", "1fTzqegAoU8ShadIttSYx25tQKQxDWtY0LYfXzrXH5jQ")
GID = int(os.environ.get("GID", "0"))
CACHE_TTL = 300  # seconds before an automatic re-fetch

DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DIR, "index.html")
CACHE_FILE = os.path.join(DIR, "recipes-cache.json")
STAPLES_FILE = os.path.join(DIR, "staples.json")
CREDENTIAL_CANDIDATES = [
    os.path.join(DIR, "credentials.json"),
    os.path.join(DIR, "..", "ledger", "credentials.json"),
]
TOKEN_PATH = os.path.expanduser("~/.recipes/token.json")
LEGACY_TOKEN_PATHS = [os.path.expanduser("~/.practice-dashboard/token.json")]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={GID}#gid={GID}"

_lock = threading.Lock()
_state = {"recipes": [], "source": None, "fetched_at": 0, "error": None,
          "sheet_title": None}


# ---------------------------------------------------------------- parsing

STAR = "⭐"
URL_RX = re.compile(r"^https?://\S+$", re.IGNORECASE)


def count_stars(cell):
    return cell.count(STAR)


def clean_text(text):
    """Collapse the long runs of spaces the sheet uses as paragraph breaks."""
    text = text.replace("\\!", "!").strip()
    text = re.sub(r"[ \t]{3,}", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def rows_to_recipes(rows):
    recipes = []
    for i, row in enumerate(rows):
        row = list(row) + [""] * (4 - len(row))
        name, body, stars, notes = (c.strip() for c in row[:4])
        if not name:
            continue
        if i == 0 and name.lower() in ("name", "recipe", "title", "dish"):
            continue  # header row, if one is ever added
        is_link = bool(URL_RX.match(body))
        tag_source = name if is_link else f"{name}\n{body}"
        recipes.append({
            "id": i,
            "name": name,
            "url": body if is_link else None,
            "instructions": "" if is_link else clean_text(body),
            "stars": count_stars(stars),
            "notes": clean_text(notes),
            "tags": tag_text(tag_source),
        })
    return recipes


# ---------------------------------------------------------- google sheets

def _find_credentials():
    for p in CREDENTIAL_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def get_credentials(interactive):
    """Return google OAuth credentials, or None if unavailable."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None

    if not os.path.exists(TOKEN_PATH):
        for legacy in LEGACY_TOKEN_PATHS:
            if os.path.exists(legacy):
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                shutil.copy(legacy, TOKEN_PATH)
                break

    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH)
        except Exception:
            creds = None

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            return None
        cred_file = _find_credentials()
        if not cred_file:
            return None
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
        creds = flow.run_local_server(port=0)

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return creds


def fetch_via_api(interactive=False):
    from googleapiclient.discovery import build
    creds = get_credentials(interactive)
    if creds is None:
        raise RuntimeError("no Google OAuth token available")
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    meta = svc.spreadsheets().get(
        spreadsheetId=SHEET_ID, fields="sheets.properties").execute()
    title = None
    for s in meta.get("sheets", []):
        if s["properties"].get("sheetId") == GID:
            title = s["properties"]["title"]
    if title is None:
        title = meta["sheets"][0]["properties"]["title"]
    result = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"'{title}'").execute()
    return result.get("values", []), title


def fetch_via_csv():
    url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
           f"/export?format=csv&gid={GID}")
    req = urllib.request.Request(url, headers={"User-Agent": "recipe-box"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        if "text/csv" not in resp.headers.get("Content-Type", ""):
            raise RuntimeError("sheet is not publicly readable")
        text = resp.read().decode("utf-8")
    return list(csv.reader(io.StringIO(text))), None


def load_cache():
    with open(CACHE_FILE) as f:
        return json.load(f)


def refresh(force=False, interactive=False):
    """Populate _state from the best available source. Returns _state."""
    with _lock:
        fresh = time.time() - _state["fetched_at"] < CACHE_TTL
        if _state["recipes"] and fresh and not force:
            return dict(_state)

        errors = []
        for source, fn in (("google-sheets-api", lambda: fetch_via_api(interactive)),
                           ("csv-export", fetch_via_csv)):
            try:
                rows, title = fn()
                recipes = rows_to_recipes(rows)
                if not recipes:
                    raise RuntimeError("sheet returned no rows")
                _state.update(recipes=recipes, source=source, error=None,
                              fetched_at=time.time(), sheet_title=title)
                with open(CACHE_FILE, "w") as f:
                    json.dump({"fetched_at": _state["fetched_at"],
                               "sheet_title": title, "recipes": recipes},
                              f, indent=1, ensure_ascii=False)
                return dict(_state)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{source}: {e}")

        err = " | ".join(errors)
        if not _state["recipes"] and os.path.exists(CACHE_FILE):
            try:
                cached = load_cache()
                _state.update(recipes=cached["recipes"], source="cache",
                              fetched_at=cached.get("fetched_at", 0),
                              sheet_title=cached.get("sheet_title"))
            except Exception as e:  # noqa: BLE001
                err += f" | cache: {e}"
        _state["error"] = err
        return dict(_state)


# --------------------------------------------------------------- staples

_staples_lock = threading.Lock()


def read_staples():
    with _staples_lock:
        try:
            with open(STAPLES_FILE) as f:
                items = json.load(f).get("staples", [])
        except (OSError, ValueError):
            items = []
    return sorted({str(x).strip().lower() for x in items if str(x).strip()})


def write_staples(items):
    cleaned = sorted({str(x).strip().lower() for x in items if str(x).strip()})
    with _staples_lock:
        with open(STAPLES_FILE, "w") as f:
            json.dump({"staples": cleaned}, f, indent=2, ensure_ascii=False)
    return cleaned


# ------------------------------------------------------------------ http

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            with open(HTML_FILE, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif parsed.path == "/api/recipes":
            force = parse_qs(parsed.query).get("refresh", ["0"])[0] == "1"
            st = refresh(force=force)
            payload = {
                "recipes": st["recipes"],
                "source": st["source"],
                "fetched_at": st["fetched_at"],
                "error": st["error"],
                "sheet_title": st["sheet_title"],
                "sheet_url": SHEET_URL,
                "staples": read_staples(),
            }
            self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
        elif parsed.path == "/api/staples":
            self._send(200, json.dumps({"staples": read_staples()}).encode(),
                       "application/json; charset=utf-8")
        elif parsed.path == "/api/cook":
            q = parse_qs(parsed.query)
            ingredient = q.get("ingredient", [""])[0]
            force = q.get("refresh", ["0"])[0] == "1"
            st = refresh()
            try:
                result = ai.suggest(ingredient, st["recipes"], read_staples(), force=force)
                self._send(200, json.dumps(result, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            except ai.AIError as e:
                self._send(200, json.dumps({"error": e.code, "message": e.message}).encode(),
                           "application/json; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(200, json.dumps({"error": "unexpected", "message": str(e)}).encode(),
                           "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/staples":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            items = body["staples"]
            assert isinstance(items, list)
        except Exception:  # noqa: BLE001
            self._send(400, b'{"error":"expected {\"staples\": [...]}"}',
                       "application/json")
            return
        self._send(200, json.dumps({"staples": write_staples(items)}).encode(),
                   "application/json; charset=utf-8")


if __name__ == "__main__":
    print("\n  Recipe Box\n")
    print("  Loading recipes...", end="", flush=True)
    st = refresh(force=True, interactive=True)
    n = len(st["recipes"])
    print(f" {n} recipes via {st['source']}")
    if st["error"]:
        print(f"  Note: {st['error']}")
    try:
        import anthropic  # noqa: F401
        key_ok = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        print("  Cook with: ready" if key_ok else
              "  Cook with: set ANTHROPIC_API_KEY to enable suggestions")
    except ImportError:
        print("  Cook with: unavailable (run with `uv run recipes/server.py`)")
    ip = get_local_ip()
    print(f"\n  Mac:    http://localhost:{PORT}")
    print(f"  Phone:  http://{ip}:{PORT}  (same Wi-Fi)\n")
    print("  Ctrl+C to stop\n")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")

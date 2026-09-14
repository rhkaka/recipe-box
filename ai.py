"""
AI-backed "cook with X" suggestions.

Given an ingredient the user has on hand, ask Claude which recipes in their
own collection it fits (as-is, as a substitute, or as an addition) and how to
adapt each one. Results are cached on disk per ingredient + catalog version.
"""

import hashlib
import json
import os
import threading
import time

MODEL = "claude-opus-5"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai-cache.json")
_lock = threading.Lock()

SYSTEM = """You are helping a home cook use an ingredient they have on hand.
You are given their personal recipe collection: each entry has an id, name,
star rating (their own rating, 1-5), ingredient tags, and either full
instructions or a link. Their notes reflect their taste, so weight them.

Given an ingredient, pick the recipes where it fits best and explain concretely
how to use it there. Be practical and specific: what it replaces, how cooking
time or method changes, seasoning tweaks, what to watch for. Prefer recipes
they rated highly. Return 4 to 8 matches, best first. Only use ids from the
catalog. If the ingredient is a protein, think about which recipes' proteins
it can stand in for and how the cook time differs; if it's a vegetable or
pantry item, think about where it adds something rather than forcing it in.
Finish with one new dish idea in the style of their collection."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string",
                    "description": "One or two sentences on how this ingredient fits their cooking overall."},
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Recipe id from the catalog"},
                    "fit": {"type": "string", "enum": ["already uses it", "substitute", "addition"]},
                    "replaces": {"type": "string",
                                 "description": "What it stands in for, or empty string if not a substitute"},
                    "how": {"type": "string",
                            "description": "2-4 sentences: exactly how to adapt this recipe"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["id", "fit", "replaces", "how", "confidence"],
                "additionalProperties": False,
            },
        },
        "new_idea": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "how": {"type": "string", "description": "A short paragraph describing the dish and method"},
            },
            "required": ["name", "how"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "matches", "new_idea"],
    "additionalProperties": False,
}


class AIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _catalog_text(recipes, staples):
    lines = []
    for r in recipes:
        tags = [t for t in r["tags"] if t not in staples]
        body = f"link: {r['url']}" if r.get("url") else r["instructions"].replace("\n", " ")
        line = (f"[{r['id']}] {r['name']} | {r['stars']}/5 stars | tags: {', '.join(tags)}\n"
                f"    recipe: {body}")
        if r.get("notes"):
            line += f"\n    notes: {r['notes'].replace(chr(10), ' ')}"
        lines.append(line)
    return "\n".join(lines)


def _load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)


def suggest(ingredient, recipes, staples, force=False):
    """Return {"ingredient", "summary", "matches", "new_idea", "cached", "model"}."""
    ingredient = " ".join(ingredient.lower().split())
    if not ingredient:
        raise AIError("bad_request", "Tell me an ingredient first.")

    catalog = _catalog_text(recipes, set(staples))
    version = hashlib.sha1(catalog.encode()).hexdigest()[:12]
    key = f"{ingredient}@{version}"

    with _lock:
        cache = _load_cache()
        if key in cache and not force:
            return dict(cache[key], cached=True)

    try:
        import anthropic
    except ImportError:
        raise AIError("no_sdk",
                      "The anthropic package isn't installed for this Python. "
                      "Run the server with: uv run recipes/server.py")

    has_key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
               or os.path.exists(os.path.expanduser("~/.config/anthropic")))
    if not has_key:
        raise AIError("no_api_key",
                      "No Anthropic API key found. Put ANTHROPIC_API_KEY=sk-ant-... in "
                      "recipes/.env (see .env.example) and restart the server.")

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[
                {"type": "text", "text": SYSTEM},
                {"type": "text", "text": "RECIPE COLLECTION\n" + catalog,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user",
                       "content": f"I have: {ingredient}. Which of my recipes should I make with it, and how?"}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except anthropic.AuthenticationError:
        raise AIError("bad_api_key",
                      "The Anthropic API rejected the key (401). Check ANTHROPIC_API_KEY "
                      "in recipes/.env for typos or an expired key, then restart the server.")
    except anthropic.PermissionDeniedError:
        raise AIError("bad_api_key",
                      "The Anthropic API refused this key (403). It may lack access to "
                      f"{MODEL} or have no credit. Check console.anthropic.com.")
    except anthropic.RateLimitError:
        raise AIError("rate_limited", "Rate limited by the API. Try again in a minute.")
    except anthropic.APIStatusError as e:
        raise AIError("api_error", f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise AIError("network", "Couldn't reach the Anthropic API. Check the connection.")

    if response.stop_reason == "refusal":
        raise AIError("refused", "The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise AIError("truncated", "The response was cut off. Try again.")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    valid_ids = {r["id"] for r in recipes}
    seen = set()
    matches = []
    for m in data.get("matches", []):
        if m["id"] in valid_ids and m["id"] not in seen:
            seen.add(m["id"])
            matches.append(m)

    result = {
        "ingredient": ingredient,
        "summary": data.get("summary", ""),
        "matches": matches,
        "new_idea": data.get("new_idea"),
        "model": response.model,
        "created_at": time.time(),
        "usage": {
            "input": response.usage.input_tokens,
            "cache_read": response.usage.cache_read_input_tokens,
            "output": response.usage.output_tokens,
        },
    }
    with _lock:
        cache = _load_cache()
        cache[key] = result
        _save_cache(cache)
    return dict(result, cached=False)

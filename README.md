# Aleena’s Recipe Box

A locally hosted site that reads your recipe spreadsheet from Google Sheets and
lets you search recipes, filter by ingredient, and sort by star rating.

## Run

```bash
cp recipes/.env.example recipes/.env   # then paste your Anthropic key into it
uv run recipes/server.py               # or double-click recipes/start.command
```

The key can also be exported in the shell instead of using `.env`.

`uv run` reads the dependency list at the top of `server.py` and installs the
Google and Anthropic SDKs into a cached environment on first run (Python 3.11+
is required by the Anthropic SDK; the system Python is 3.9). Plain
`python3 recipes/server.py` still works for browsing recipes, but the
"Cook with" tab will report that the SDK is missing.

Then open http://localhost:8090 on the Mac, or `http://<mac-ip>:8090` from a
phone on the same Wi-Fi (the server prints the exact address on startup).

## How it reads the sheet

The sheet is private, so the server uses the same Google OAuth desktop
credentials as the practice dashboard (`ledger/credentials.json`). On first run
it reuses the existing `~/.practice-dashboard/token.json` if present, otherwise
it opens a browser for consent (read-only scope) and caches the token at
`~/.recipes/token.json`.

Fallbacks, in order: public CSV export (only if the sheet is shared "anyone with
the link"), then `recipes/recipes-cache.json`, which is rewritten after every
successful fetch so the site still works offline.

Data is re-read every 5 minutes, or immediately with the **Refresh** button.

## Hosted copy (GitHub Pages)

A static snapshot lives at https://rhkaka.github.io/recipe-box/ and is served
from the `docs/` folder. It supports search, ingredient filters, and rating
sort. It can't refresh from the sheet or use "Cook with", and staple edits
there are saved per browser. To update it after changing the sheet:

```bash
uv run build_static.py
git add docs && git commit -m "Update snapshot" && git push
```

## Sheet layout

No header row. Columns: `A` name, `B` recipe (a URL or the instructions),
`C` star rating as ⭐️ emoji, `D` notes. Add rows anywhere; nothing else to do.

## Ingredient tags

There is no ingredient column, so tags are inferred by matching the name and
instructions against the dictionary in `ingredients.py`. Add or tweak entries
there, then hit Refresh. Anything not in the dictionary can still be searched:
type it in the ingredient box and press Enter to filter on recipe text.

## Staples

Pantry staples (garlic, soy sauce, cumin, ...) are hidden from the ingredient
chips and recipe cards so the filter only shows ingredients worth planning
around. Click **Staples** above the chips to add or remove items; the list is
saved to `staples.json` and applies on every device. Staples still show up in
search and in the recipe detail view.

## Cook with… (AI suggestions)

The second tab takes an ingredient you have on hand (steelhead trout, paneer,
a bag of kale) and asks Claude Opus 5 to read through your whole collection and
pick the recipes where it fits, marking each as *already uses it*, *substitute*
(and what it replaces), or *addition*, with concrete notes on how to adapt
cook times, method, and seasoning. It ends with one new dish idea in the style
of your collection.

- Needs `ANTHROPIC_API_KEY` in the environment. Get one at
  https://console.anthropic.com/settings/keys.
- Answers are saved in `ai-cache.json` per ingredient, so repeat questions are
  free and instant; "Ask again" forces a fresh answer.
- The recipe catalog is sent with prompt caching enabled, so several questions
  within a few minutes reuse the cached context.
- Refusal fallbacks are enabled (`fallbacks: "default"`), so if the primary
  model declines a request the API retries on a fallback model automatically.
- Rough cost: about 12k input tokens per fresh question, so a few cents each.

## Files

- `server.py` – HTTP server + Google Sheets fetch + caching (deps declared inline for `uv run`)
- `ai.py` – "Cook with" suggestions via the Anthropic SDK
- `ingredients.py` – ingredient dictionary (tag, regex)
- `index.html` – the whole frontend, no build step
- `build_static.py` – writes the GitHub Pages snapshot into `docs/`
- `staples.json` – pantry staples hidden from the ingredient filter (editable in the UI)
- `recipes-cache.json` – last successful fetch (generated)
- `ai-cache.json` – saved AI answers (generated)

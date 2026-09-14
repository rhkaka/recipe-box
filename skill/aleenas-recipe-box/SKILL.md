---
name: aleenas-recipe-box
description: Aleena's personal recipe collection (about 90 home-cooked recipes with her own star ratings, instructions, and tasting notes) and how to cook from it. Use this whenever the user asks what to cook or make, says they have an ingredient on hand ("I have steelhead trout", "what can I do with a bag of kale", "leftover roast chicken"), wants a recipe or the instructions for a dish from Aleena's box, asks for dinner or meal-prep ideas, wants to swap or substitute an ingredient in one of her dishes, or mentions Aleena's recipes or recipe box at all — even if they don't use the word "recipe".
---

# Aleena's Recipe Box

This skill carries a snapshot of Aleena's recipe spreadsheet. Every recipe has a
name, her 1–5 star rating, the instructions (or a link, for recipes she cooks from
a website), ingredient tags, and her notes from actually making it. The notes are
the most valuable part: they say what worked, what she'd change, and what she'd
add next time. Treat them as her taste, and let them shape your suggestions.

## Where the data is

- `references/recipes.md` — the whole collection, best-rated first, with an index
  at the top and the list of pantry staples. It is around 15k tokens. For anything
  beyond a one-recipe lookup, read the entire file; the best "what can I make
  with X" answers come from seeing every recipe, because the good matches are
  often substitutions that no keyword search would find.
- `scripts/find_recipes.py "<term>"` — quick keyword lookup across names,
  instructions, tags, and notes. Handy for "do I have a daal recipe" style
  questions, or to double-check you didn't miss a literal mention.
- `references/recipes.json` — the same data as JSON, if you need to process it.

## "What can I make with X?"

This is the main job. Someone has an ingredient and wants to use it in a dish
they already know and like. Read the full collection, then work through it the
way a good cook would:

1. Figure out what the ingredient *is* in cooking terms: a rich fish, a lean
   protein, a leafy green, a fresh cheese, a pantry item. That tells you what it
   can stand in for and what it adds.
2. Pick 4 to 8 recipes where it genuinely fits, best first. Lean toward the ones
   she rated 4 or 5 stars, and toward recipes whose notes say "make this often"
   or "great for meal prep". A 3-star recipe can still make the list if the
   ingredient fixes the exact thing her notes complained about.
3. Label each one honestly: it already uses the ingredient, it's a substitute
   (say what it replaces), or it's an addition.
4. Explain *how* to adapt it in two to four concrete sentences: what changes in
   cook time and method (a thin fish fillet needs minutes, not the 40 minutes
   written for chicken thighs), how to season it differently, and what to watch
   for. Reference the actual step in her instructions where the change happens.
5. Pantry staples (listed at the top of `recipes.md`) are assumed to be around.
   If someone says they have garlic or cumin, there's no need to hunt for
   recipes; ask what else they have, or just point at a few favorites.
6. Finish with one new dish idea that borrows from her collection, so the
   answer opens a door rather than only sorting the existing ones.

Be practical, specific, and short per recipe. She is going to cook from this,
so vague advice ("adjust seasoning to taste") is less useful than "add the lemon
at the end instead of in the marinade, because the fish will go mushy".

### Answer format

```
**Steelhead trout** cooks like salmon: rich, forgiving, done in 8–12 minutes.
One or two sentences on how it fits her cooking overall.

1. **Miso glazed mahi mahi** ★★★★ — *substitute for mahi mahi*
   How to adapt it, in 2–4 sentences.
2. **Salmon feta pasta** ★★★★ — *substitute for salmon*
   ...

**New idea: Miso-lime steelhead rice bowl** — a short paragraph.
```

## Other things people ask

- **"Give me the recipe for X"** — reproduce her instructions faithfully; don't
  tidy them into a different recipe. Add the notes below, because they contain
  the fixes she discovered. If the recipe is a link, say so and give the URL.
- **"What should I make this week / for meal prep"** — pull from the 4 and 5 star
  recipes, aim for variety across proteins and cuisines, and favor the ones whose
  notes mention meal prep or reheating well. Note the ones that don't reheat
  well (some notes say so).
- **"What did she think of X" / "is X any good"** — quote her rating and notes.
- **"Substitute Y in X"** — same reasoning as above, focused on one recipe.
- **"Something quick / healthy / vegetarian"** — the tags and instructions make
  this easy to filter; lentils, chickpeas, tofu, and the salads are the
  vegetarian core of the collection.

## Keeping it current

The snapshot date and recipe count are in the header of `references/recipes.md`.
The collection is rebuilt from the spreadsheet by the owner; if a user says a
recipe is missing, it was probably added after the snapshot.

# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── agent.py                   # Planning loop and session management
├── tools.py                   # Three tool implementations
├── app.py                     # Gradio interface
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Then open the URL shown in your terminal (usually `http://localhost:7860`).

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Searches the mock listings dataset for secondhand clothing items that match a user's natural-language description, optional size, and optional price ceiling.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords or natural language describing the item (e.g., `"vintage graphic tee"`). Price and size language is stripped before this reaches the tool — it contains only style/item keywords. |
| `size` | `str \| None` | Size string to filter by. Matching is case-insensitive and uses `in` containment, so `"M"` matches listing sizes like `"S/M"` or `"M/L"`. Pass `None` to skip size filtering. |
| `max_price` | `float \| None` | Maximum price, inclusive. Pass `None` to skip price filtering. |

**Output:** A `list[dict]` of matching listing dictionaries, sorted by relevance score (best match first). Returns an empty list if nothing matches. Each dict contains: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

**Scoring:** Keywords from `description` are matched against a searchable string built from the listing's title, description, category, brand, style tags, and colors. A title match is worth 3 points; a match in any other field is worth 1 point. Listings with a score of 0 are dropped. If `description` is empty (e.g., a price-only query like "under $35"), all filtered candidates are returned without scoring.

---

### Tool 2: `suggest_outfit`

**Purpose:** Given a selected thrifted item and the user's saved wardrobe, asks the Groq LLM to generate 1–2 complete outfit suggestions. Handles empty wardrobes gracefully by generating general styling advice instead.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict (the item the user is considering buying). |
| `wardrobe` | `dict` | A wardrobe dict with an `"items"` key containing a list of wardrobe item dicts. May be empty. |

**Output:** A non-empty `str` with outfit suggestions. If the wardrobe has saved items, the suggestions prioritize those pieces by name. If the wardrobe is empty, the LLM offers general styling ideas and notes that no wardrobe items were available.

---

### Tool 3: `create_fit_card`

**Purpose:** Generates a short, shareable social-media-style caption (2–4 sentences) from the outfit suggestion and selected item. Intended to sound like a real OOTD post, not a product description.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit()`. |
| `new_item` | `dict` | The listing dict for the thrifted item. |

**Output:** A `str` containing a caption that naturally mentions the item name, price, and platform once each. Uses a higher LLM temperature (`1.2`) so the output varies across calls. If `outfit` is empty or whitespace-only, returns a descriptive error string instead of raising an exception.

---

## Planning Loop

The agent runs a fixed, linear workflow — the same three tools always execute in the same order. What changes is whether the workflow terminates early based on tool output.

**Steps:**

1. **Parse the query.** Regular expressions extract `max_price` and `size` from the raw query string. Price language (`under`, `below`, `less than`, `up to`, `max`) and size tokens (`S`, `M`, `L`, `W30`, etc.) are stripped out of the description before it is passed to `search_listings`, so the keyword scorer only sees style/item terms.

2. **Call `search_listings`.** The parsed description, size, and max price are passed to the tool. Results are stored in `session["search_results"]`.

3. **Branch on results.** If the result list is empty, `session["error"]` is set to a helpful message and the function returns immediately. `suggest_outfit` and `create_fit_card` are never called.

4. **Select the top result.** `results[0]` is stored in `session["selected_item"]`. The tool already returns results sorted by relevance, so the first item is the best match.

5. **Call `suggest_outfit`.** Receives the selected item and the user's wardrobe. Result stored in `session["outfit_suggestion"]`.

6. **Call `create_fit_card`.** Receives the outfit suggestion and the selected item. Result stored in `session["fit_card"]`.

7. **Return the session.** The Gradio interface reads `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` and displays each in its own output panel.

The loop has one decision point: whether `search_listings` returned anything. All other steps are unconditional.

---

## State Management

All data produced during a run is stored in a single session dictionary that lives for the duration of one user interaction. Tools do not store state — they accept inputs and return values, and the planning loop is responsible for moving data between them.

**Session structure:**

```python
session = {
    "query": str,               # original user query, unmodified
    "parsed": {                 # extracted from query by regex
        "description": str,     # style/item keywords only (price+size stripped)
        "size": str | None,
        "max_price": float | None,
    },
    "search_results": list,     # all results returned by search_listings()
    "selected_item": dict | None,  # results[0], passed to suggest_outfit()
    "wardrobe": dict,           # user's wardrobe, loaded before run_agent() is called
    "outfit_suggestion": str | None,  # returned by suggest_outfit()
    "fit_card": str | None,     # returned by create_fit_card()
    "error": str | None,        # set on early termination; None on success
}
```

**Data flow between tools:**

- `search_listings` → writes to `session["search_results"]` → `session["selected_item"]` is set from there
- `session["selected_item"]` + `session["wardrobe"]` → passed directly into `suggest_outfit()`
- `suggest_outfit()` result → `session["outfit_suggestion"]` → passed into `create_fit_card()`
- `create_fit_card()` result → `session["fit_card"]` → displayed in the Gradio fit card panel

No tool reads from or writes to the session directly. The planning loop owns the session and is the only thing that updates it.

---

## Error Handling

### `search_listings` — No matching results

If no listings survive price/size filtering, or if all remaining listings score 0 on keyword matching, `search_listings` returns `[]`. The planning loop checks for this immediately after the call:

```python
if not results:
    session["error"] = (
        "No matching listings found. "
        "Try broadening your search or increasing your budget."
    )
    return session
```

`suggest_outfit` and `create_fit_card` are never called. The Gradio handler checks `session["error"]` and surfaces the message in the first output panel, leaving the outfit and fit card panels blank.

**Concrete test case:** Query `"designer ballgown size XXS under $5"` — no listing in the dataset is priced under $5 in any category, so price filtering removes all candidates and `search_listings` returns `[]`. The session comes back with `error` set and no other output fields populated.

---

### `suggest_outfit` — Empty wardrobe

If `wardrobe["items"]` is an empty list, the tool does not raise an exception or return an empty string. Instead it sends a different prompt to the LLM:

```
They haven't saved any wardrobe items yet, so you can't pull from their closet.
Start your response by acknowledging this (one sentence). Then suggest 2–3 complete outfit ideas anyway...
```

**Concrete test case:** Selecting "Empty wardrobe (new user)" in the Gradio UI and querying `"vintage graphic tee under $30"` — the outfit panel returns a full suggestion that opens by acknowledging the empty wardrobe, then proposes outfits using generic wardrobe staples (e.g., "relaxed straight-leg jeans, white sneakers, a lightweight canvas overshirt").

---

### `create_fit_card` — Missing or empty outfit string

The function guards against an empty or whitespace-only `outfit` at the top of the function before any LLM call:

```python
if not outfit or not outfit.strip():
    return (
        f"Couldn't generate a fit card — no outfit suggestion was provided for "
        f"{new_item.get('title', 'this item')}. Try running suggest_outfit first."
    )
```

**Concrete test case:** Calling `create_fit_card("", {"title": "Vintage Band Tee"})` directly returns `"Couldn't generate a fit card — no outfit suggestion was provided for Vintage Band Tee. Try running suggest_outfit first."` without hitting the Groq API.

---

## Spec Reflection

**What matched the plan:** The overall structure — a linear three-tool pipeline with a single early-exit branch after `search_listings` — is exactly what I described in `planning.md`. The session dictionary fields, the tool signatures, and the Gradio output mapping all match the spec closely. The LLM prompts for `suggest_outfit` (wardrobe-aware vs. general styling) also follow the plan.

**What changed during implementation:** The biggest divergence was in query parsing and listing scoring. The original plan described parsing `description` by removing price/size language, but the first implementation set `description = query` (the full raw string). This caused queries like `"under $35"` to pass keywords like `"under"` and `"$35"` to the scorer, which matched nothing and returned zero results — even though 25 listings are priced under $35. This required two fixes: stripping price/size language from `description` in `agent.py`, and adding a short-circuit in `search_listings` to return all filtered candidates when the keyword list is empty.

The scoring weights (title = 3, other field = 1) were also not in the original plan — they emerged from testing. Without the title bonus, a listing like `"Vintage Band Tee"` would score the same as one where "vintage" only appears in a style tag, making the ranking less useful.

**What I'd do differently:** I'd write the query-parsing test first. The bug where `description = query` passed price language into the keyword scorer would have been caught immediately by a test like `assert "under" not in session["parsed"]["description"]`. Testing parsing in isolation before wiring it into the full pipeline would have surfaced this much earlier.

---

## AI Usage

### Instance 1 — Implementing `search_listings` and iterating on query parsing

**Input to Claude Code:** The Tool 1 spec from `planning.md` (inputs, return value, scoring approach, failure mode), the `load_listings()` function signature, and the function stub with docstring from `tools.py`.

**What it produced:** A working `search_listings` implementation with price/size filtering and keyword scoring. The initial scoring logic matched keywords against a joined searchable string with a uniform weight of 1 for any match.

**What I changed:** I added a title-match bonus (weight 3 vs. 1 for other fields) after testing queries like `"vintage graphic tee"` and noticing that listings where "vintage" appeared only in `style_tags` ranked the same as listings where "vintage" appeared in the title. The title bonus made top results noticeably more relevant in manual testing.

The more significant change came in `agent.py`: Claude initially set `description = query`, which passed the full user input — including price language — directly to the scorer. This caused pure price/size queries like `"under $35"` to return zero results. I overrode this by adding regex substitution to strip price and size text from the description before using it as search keywords, and adding a guard in `search_listings` to return all filtered candidates when the keyword list is empty.

---

### Instance 2 — Implementing `run_agent` and the planning loop

**Input to Claude Code:** The Planning Loop and State Management sections from `planning.md`, the architecture diagram (Mermaid flowchart), the Error Handling table, and the `run_agent` TODO stub in `agent.py`.

**What it produced:** A complete `run_agent` implementation that initialized the session, called the three tools in sequence, and handled the early-exit case when `search_listings` returned no results.

**What I changed:** The generated parsing regex handled the `"under $30"` pattern correctly, but did not strip size tokens from `description`. For example, querying `"graphic tee size M"` passed `"graphic tee size M"` as description keywords, meaning `"size"` and `"M"` became search terms. `"M"` is common enough in listing text that it inflated scores for unrelated items. I extended the description-cleaning step to also strip the size token (with and without the word `"size"` preceding it) so only genuine style and item keywords reach the scorer.

I also adjusted the error message wording — the generated message was terse (`"No listings found."`) — to something more useful that hints at what the user can change (`"Try broadening your search or increasing your budget."`).

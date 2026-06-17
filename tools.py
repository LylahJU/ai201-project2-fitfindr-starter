"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Filter by price and size
    candidates = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and size.lower() not in listing["size"].lower():
            continue
        candidates.append(listing)

    # Score by keyword overlap against searchable text fields
    keywords = [w.lower() for w in (description or "").split() if w]
    if not keywords:
        return candidates

    def score(listing: dict) -> int:
        title = listing["title"].lower()

        searchable = " ".join([
            title,
            listing["description"],
            listing["category"],
            listing.get("brand") or "",
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
        ]).lower()

        score = 0

        for kw in keywords:
            if kw in title:
                score += 3      # title match
            elif kw in searchable:
                score += 1      # other field match

        return score

    scored = [(score(l), l) for l in candidates]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]

# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_summary = (
        f"Item: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Condition: {new_item.get('condition', 'unknown')}\n"
        f"Price: ${new_item.get('price', '?')} on {new_item.get('platform', '?')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A user is considering buying this secondhand item:\n\n{item_summary}\n\n"
            "They haven't saved any wardrobe items yet, so you can't pull from their closet. "
            "Start your response by acknowledging this (one sentence). "
            "Then suggest 2–3 complete outfit ideas anyway, treating each piece as something "
            "they would need to find or already own. "
            "Be specific about colors, silhouettes, and overall vibe. "
            "Keep it conversational and concise."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}, {', '.join(item.get('colors', []))})"
            + (f" — {item['notes']}" if item.get("notes") else "")
            for item in wardrobe_items
        )
        prompt = (
            f"A user is considering buying this secondhand item:\n\n{item_summary}\n\n"
            f"Here are the pieces they already own:\n{wardrobe_lines}\n\n"
            "Suggest 1–2 complete outfit combinations. Rules:\n"
            "- Always prefer pieces from their wardrobe. Only suggest something they don't "
            "own if their wardrobe has nothing in that category, or every option in that "
            "category clashes badly (wrong color family, completely different aesthetic).\n"
            "- The new item is the centerpiece — do not label it. "
            "- If the suggested outfit includes pieces not in the wardrobe, label it '(not in your wardrobe)' "
            "so it's clear what they already have.\n"
            "- If you had to go outside their wardrobe for a piece, briefly explain why "
            "nothing they own worked for that slot.\n"
            "- End each outfit with 1–2 sentences on the overall vibe.\n"
            "Keep the tone casual and practical."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return (
            f"Couldn't generate a fit card — no outfit suggestion was provided for "
            f"{new_item.get('title', 'this item')}. Try running suggest_outfit first."
        )

    client = _get_groq_client()

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
        f"The thrifted find: {new_item['title']} — ${new_item.get('price', '?')} "
        f"from {new_item.get('platform', 'a secondhand app')}.\n\n"
        f"The full outfit:\n{outfit}\n\n"
        "Guidelines:\n"
        "- Sound like a real person posting their OOTD, not a product description\n"
        "- Mention the item name, price, and platform once each, worked in naturally\n"
        "- Capture the specific vibe of this outfit (don't be vague)\n"
        "- No hashtags"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.2,
    )

    return response.choices[0].message.content

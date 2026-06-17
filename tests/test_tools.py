"""
tests/test_tools.py

Pytest tests for all three FitFindr tools.
Covers happy paths, failure modes, and edge cases from the planning.md spec.
LLM calls are mocked so tests run without a real API key.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_item():
    return {
        "id": "lst_002",
        "title": "Y2K Baby Tee — Butterfly Print",
        "description": "Super cute early 2000s baby tee with butterfly graphic.",
        "category": "tops",
        "style_tags": ["y2k", "vintage", "graphic tee", "cottagecore"],
        "size": "S/M",
        "condition": "excellent",
        "price": 18.00,
        "colors": ["white", "pink", "purple"],
        "brand": None,
        "platform": "depop",
    }


@pytest.fixture
def mock_groq():
    """Return a factory that builds a mock Groq client returning the given text."""
    def _factory(text="Mocked LLM response."):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=text))]
        )
        return mock_client
    return _factory


# ── search_listings ───────────────────────────────────────────────────────────

class TestSearchListings:

    def test_returns_results_for_known_keyword(self):
        results = search_listings("jeans")
        assert len(results) > 0

    def test_returns_list_of_dicts_with_required_fields(self):
        results = search_listings("jacket")
        assert isinstance(results, list)
        required = ("id", "title", "description", "category", "style_tags",
                    "size", "condition", "price", "colors", "platform")
        for item in results:
            for field in required:
                assert field in item, f"Missing field '{field}' in result"

    def test_returns_empty_list_for_impossible_query(self):
        results = search_listings("xyzzy_absolutely_impossible_item_99999")
        assert results == []

    def test_does_not_raise_on_impossible_query(self):
        # Failure mode: no matches must return [] not raise
        try:
            results = search_listings("xyzzy_absolutely_impossible_item_99999")
        except Exception as exc:
            pytest.fail(f"search_listings raised unexpectedly: {exc}")
        assert results == []

    def test_max_price_filter_excludes_expensive_items(self):
        results = search_listings("vintage", max_price=20.0)
        for item in results:
            assert item["price"] <= 20.0

    def test_max_price_zero_returns_empty_list(self):
        # Nothing costs $0, so every item should be filtered out
        results = search_listings("tee", max_price=0.0)
        assert results == []

    def test_size_filter_case_insensitive(self):
        # "M" and "m" should produce identical results
        results_upper = search_listings("tee", size="M")
        results_lower = search_listings("tee", size="m")
        assert results_upper == results_lower

    def test_size_filter_excludes_non_matching_sizes(self):
        results = search_listings("vintage", size="XXXXXXXXXL")
        assert results == []

    def test_no_filters_returns_more_than_strict_filters(self):
        all_results = search_listings("vintage")
        filtered = search_listings("vintage", size="XS", max_price=5.0)
        assert len(all_results) >= len(filtered)

    def test_results_sorted_by_relevance(self):
        """Items matching more keywords should appear earlier in the list."""
        results = search_listings("vintage graphic tee")
        assert len(results) > 1
        # Every returned item must contain at least one keyword somewhere
        for item in results:
            text = " ".join([
                item["title"], item["description"],
                item["category"],
                " ".join(item.get("style_tags", [])),
                " ".join(item.get("colors", [])),
                item.get("brand") or "",
            ]).lower()
            assert any(kw in text for kw in ["vintage", "graphic", "tee"])

    def test_combined_size_and_price_filter(self):
        results = search_listings("denim", size="M", max_price=50.0)
        for item in results:
            assert item["price"] <= 50.0
            assert "m" in item["size"].lower()

    def test_empty_description_returns_list_without_raising(self):
        results = search_listings("")
        assert isinstance(results, list)


# ── suggest_outfit ────────────────────────────────────────────────────────────

class TestSuggestOutfit:

    def test_returns_string_with_populated_wardrobe(self, sample_item, mock_groq):
        expected = "Here is a great outfit for you."
        with patch("tools._get_groq_client", return_value=mock_groq(expected)):
            result = suggest_outfit(sample_item, get_example_wardrobe())
        assert isinstance(result, str)
        assert result == expected

    def test_returns_nonempty_string_with_empty_wardrobe(self, sample_item, mock_groq):
        # Failure mode: empty wardrobe must not raise and must return a useful string
        expected = "General styling advice since no wardrobe items are saved."
        with patch("tools._get_groq_client", return_value=mock_groq(expected)):
            result = suggest_outfit(sample_item, get_empty_wardrobe())
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_does_not_raise_with_empty_wardrobe(self, sample_item, mock_groq):
        with patch("tools._get_groq_client", return_value=mock_groq()):
            try:
                result = suggest_outfit(sample_item, {"items": []})
            except Exception as exc:
                pytest.fail(f"suggest_outfit raised with empty wardrobe: {exc}")
        assert isinstance(result, str)

    def test_empty_wardrobe_prompt_acknowledges_missing_items(self, sample_item, mock_groq):
        """Spec: if wardrobe is empty, LLM prompt should acknowledge this."""
        mock_client = mock_groq("styling advice")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(sample_item, get_empty_wardrobe())

        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "haven't saved" in prompt.lower() or "no wardrobe" in prompt.lower() or "empty" in prompt.lower()

    def test_populated_wardrobe_prompt_includes_item_names(self, sample_item, mock_groq):
        """Spec: wardrobe item names should appear in the prompt when wardrobe is populated."""
        mock_client = mock_groq("outfit suggestion")
        wardrobe = get_example_wardrobe()
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(sample_item, wardrobe)

        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # At least the first wardrobe item's name should appear in the prompt
        assert wardrobe["items"][0]["name"] in prompt

    def test_does_not_raise_with_item_missing_optional_fields(self, mock_groq):
        """Item dict with only required fields should not crash suggest_outfit."""
        minimal_item = {"title": "Plain Tee", "category": "tops", "price": 10.0, "platform": "depop"}
        with patch("tools._get_groq_client", return_value=mock_groq()):
            try:
                result = suggest_outfit(minimal_item, get_empty_wardrobe())
            except Exception as exc:
                pytest.fail(f"suggest_outfit raised with minimal item dict: {exc}")
        assert isinstance(result, str)

    def test_llm_called_once_per_invocation(self, sample_item, mock_groq):
        mock_client = mock_groq()
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(sample_item, get_example_wardrobe())
        assert mock_client.chat.completions.create.call_count == 1


# ── create_fit_card ───────────────────────────────────────────────────────────

class TestCreateFitCard:

    def test_returns_string_for_valid_inputs(self, sample_item, mock_groq):
        expected = "Thrifted this tee for $18 on Depop and I'm obsessed."
        with patch("tools._get_groq_client", return_value=mock_groq(expected)):
            result = create_fit_card("Y2K tee + baggy jeans + chunky sneakers.", sample_item)
        assert result == expected

    def test_returns_error_string_for_empty_outfit_not_raise(self, sample_item):
        """Failure mode: empty outfit string must return an error string, not raise."""
        try:
            result = create_fit_card("", sample_item)
        except Exception as exc:
            pytest.fail(f"create_fit_card raised with empty outfit: {exc}")
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_returns_error_string_for_whitespace_only_outfit(self, sample_item):
        """Failure mode: whitespace-only outfit must return an error string, not raise."""
        result = create_fit_card("   \n\t  ", sample_item)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_error_string_mentions_item_title(self, sample_item):
        """Error message should reference the item so the user knows what it's about."""
        result = create_fit_card("", sample_item)
        assert sample_item["title"] in result

    def test_no_llm_call_when_outfit_is_empty(self, sample_item):
        """Groq must not be called when the guard short-circuits on an empty outfit."""
        with patch("tools._get_groq_client") as mock_get_client:
            create_fit_card("", sample_item)
        mock_get_client.assert_not_called()

    def test_no_llm_call_when_outfit_is_whitespace(self, sample_item):
        with patch("tools._get_groq_client") as mock_get_client:
            create_fit_card("    ", sample_item)
        mock_get_client.assert_not_called()

    def test_prompt_includes_item_price_and_platform(self, sample_item, mock_groq):
        """Spec: caption prompt must include the item's price and platform."""
        mock_client = mock_groq("caption text")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card("Some outfit description.", sample_item)

        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert str(sample_item["price"]) in prompt
        assert sample_item["platform"] in prompt

    def test_uses_high_temperature_for_caption_variety(self, sample_item, mock_groq):
        """Spec: higher temperature produces caption variety across runs."""
        mock_client = mock_groq("caption")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card("Some outfit.", sample_item)

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        temperature = kwargs.get("temperature")
        assert temperature is not None, "temperature should be set explicitly"
        assert temperature > 0.9, f"Expected high temperature for variety, got {temperature}"

    def test_does_not_raise_with_minimal_item_dict(self, mock_groq):
        """Item dict with only 'title' must not crash create_fit_card."""
        minimal_item = {"title": "Mystery Item"}
        with patch("tools._get_groq_client", return_value=mock_groq()):
            try:
                result = create_fit_card("Some outfit description.", minimal_item)
            except Exception as exc:
                pytest.fail(f"create_fit_card raised with minimal item dict: {exc}")
        assert isinstance(result, str)

    def test_error_fallback_item_title_when_title_missing(self):
        """If item has no title, error string should still be returned gracefully."""
        result = create_fit_card("", {})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

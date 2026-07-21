"""Section-output cleaning and transcript context-fitting."""
import pytest

from app.config import settings
from app.pipeline import TRUNCATION_MARKER, clean_section, fit_transcript


# --- clean_section ---


def test_strips_hedged_meta_opener():
    raw = (
        "This conversation appears to be a meeting or call between John and two others. "
        "The team agreed to ship on Friday."
    )
    assert clean_section(raw) == "The team agreed to ship on Friday."


def test_keeps_confident_meeting_opener():
    # The TL;DR section legitimately opens like this — it must survive.
    raw = "This conversation is a meeting between Anna and Ben about the Q3 launch."
    assert clean_section(raw) == raw


def test_strips_here_is_and_based_on():
    assert clean_section("Here is the summary: We shipped.") == "We shipped."
    assert clean_section("Based on the transcript, the team shipped.") == "the team shipped."
    assert clean_section("Sure! - decision one") == "- decision one"


def test_strips_duplicate_title_heading():
    assert clean_section("## Key decisions\n- ship Friday", "Key decisions") == "- ship Friday"
    assert clean_section("**TL;DR**\nWe shipped.", "TL;DR") == "We shipped."


def test_keeps_unrelated_heading_and_plain_content():
    assert clean_section("## Roadmap\n- item", "Key decisions") == "## Roadmap\n- item"
    assert clean_section("None", "Action items") == "None"


def test_strips_stacked_boilerplate():
    raw = (
        "Sure! Here is the section: This transcript appears to be a call between two people. "
        "- decided X"
    )
    assert clean_section(raw) == "- decided X"


# --- fit_transcript ---


def test_fit_transcript_noop_when_within_budget():
    assert fit_transcript("short", budget=100) == "short"


def test_fit_transcript_cuts_middle_keeps_ends():
    text = "START " + ("x" * 10000) + " END"
    out = fit_transcript(text, budget=2000)
    assert len(out) <= 2100
    assert out.startswith("START")
    assert out.endswith("END")
    assert TRUNCATION_MARKER in out


def test_fit_transcript_budget_follows_context_setting(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_tokens", 100000)
    big = "y" * 60000
    assert fit_transcript(big) == big  # a large window keeps the whole transcript
    monkeypatch.setattr(settings, "llm_context_tokens", 2048)
    out = fit_transcript(big)
    assert len(out) < len(big)
    assert TRUNCATION_MARKER in out


def test_fit_transcript_marker_survives_tiny_budget():
    out = fit_transcript("z" * 5000, budget=10)  # floor kicks in, still valid output
    assert TRUNCATION_MARKER in out
    assert isinstance(out, str) and out

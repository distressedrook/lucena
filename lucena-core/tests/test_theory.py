"""`lucena_core.theory` — the Wikibooks opening-theory accessor.

FEN identity is shared with `openings`: exact on the first four FEN fields,
then an en-passant-stripped fallback. These tests pin that matching and the
stub/attribution contract against a controlled fixture, plus one smoke check
against the real bundled table.
"""

import json

import chess
import pytest

from lucena_core import theory


@pytest.fixture
def fixture_table(tmp_path, monkeypatch):
    """Point `theory` at a tiny hand-written table and clear its caches."""
    sicilian = chess.Board()
    sicilian.push_san("e4"); sicilian.push_san("c5")   # after 1.e4 c5
    data = {
        "entries": {
            sicilian.fen(): {
                "fen": sicilian.fen(), "moves": ["e4", "c5"],
                "name": "Sicilian defence", "eco": "B20-B99",
                "description": "1...c5 is the Sicilian defence.",
                "responses": ["2. Nf3 - Open Sicilian"],
                "source_url": "https://en.wikibooks.org/wiki/x",
            },
        },
    }
    p = tmp_path / "wb.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(theory, "_PATH", p)
    theory._entries.cache_clear()
    theory._ep_stripped.cache_clear()
    yield sicilian.fen()
    theory._entries.cache_clear()
    theory._ep_stripped.cache_clear()


def test_exact_match(fixture_table):
    e = theory.theory_for(fixture_table)
    assert e is not None
    assert e["name"] == "Sicilian defence"
    assert theory.has_theory(fixture_table) is True


def test_ep_stripped_fallback(fixture_table):
    # The harvest replays with python-chess, which writes ep "-" after
    # 1.e4 c5 (no capturer). A runtime FEN from a core that records ep on
    # ANY double push writes "c6" instead — exact match misses, the
    # ep-stripped fallback must still resolve it. (This is the whole reason
    # the fallback exists; it mirrors openings._ep_stripped_table.)
    assert " - " in fixture_table               # sanity: stored ep is legal-only
    with_ep = fixture_table.replace(" - ", " c6 ")
    assert theory.theory_for(with_ep) is not None
    assert theory.theory_for(with_ep)["eco"] == "B20-B99"


def test_unknown_position_is_none(fixture_table):
    assert theory.theory_for(chess.Board().fen()) is None    # startpos
    assert theory.has_theory(chess.Board().fen()) is False


def test_missing_table_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(theory, "_PATH", tmp_path / "nope.json")
    theory._entries.cache_clear(); theory._ep_stripped.cache_clear()
    assert theory.theory_for(chess.Board().fen()) is None    # no crash
    theory._entries.cache_clear(); theory._ep_stripped.cache_clear()


def test_real_bundle_has_sicilian():
    """Smoke check against the shipped table (skips if not yet harvested)."""
    theory._entries.cache_clear(); theory._ep_stripped.cache_clear()
    if not theory._entries():
        pytest.skip("wikibooks_theory.json not present")
    b = chess.Board(); b.push_san("e4"); b.push_san("c5")
    e = theory.theory_for(b.fen())
    assert e is not None and "source_url" in e
    assert e["source_url"].startswith("https://en.wikibooks.org/")


# -- harvest parser (tools/wikibooks_harvest.py) ------------------------------

def _harvest_module():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    import wikibooks_harvest as H
    return H


def test_description_handles_any_heading_level():
    """A page whose first section heading is level-3+ ('=== … ===') must
    still yield its prose — the level-2-only regex silently dropped these as
    stubs (Codex finding 2026-07-24)."""
    H = _harvest_module()
    lvl3 = ("=== Some Line ===\nThis is real theory prose describing the "
            "position at length.\n=== References ===\nfootnotes")
    d = H._description(lvl3)
    assert d.startswith("This is real theory prose")
    assert "References" not in d               # next-heading boundary holds
    # the common level-2 case is unaffected
    lvl2 = "== Sicilian ==\nThe Sicilian is sharp.\n=== Open ===\nmore"
    assert H._description(lvl2) == "The Sicilian is sharp."


def test_description_move_list_only_is_stub():
    """A page whose body is just an echoed move list collapses to empty (so
    MIN_DESC drops it)."""
    H = _harvest_module()
    assert H._description("== 2. Nf3 ==\n1. e4 c5 2. Nf3\n== References ==\nx") == ""


def test_description_strips_single_move_preamble():
    """A lone move on its own line ('1. e4') is preamble too — stripped so the
    real paragraph that follows becomes the description."""
    H = _harvest_module()
    ex = "== 1. e4 ==\n1. e4\nThe King's Pawn opening grabs the centre at once."
    assert H._description(ex) == "The King's Pawn opening grabs the centre at once."

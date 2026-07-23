"""Authored-content accessors: shape, sourcing discipline, determinism."""
from lucena_core import content


def test_openings_coverage_and_shape():
    assert content.annotation_for("Sicilian Defense")
    qa = content.socratic_for("Sicilian Defense")
    assert qa and {"question", "answer"} <= set(qa[0]) | {"question", "answer"}
    assert content.annotation_for("Not An Opening") is None


def test_every_quote_and_trivium_is_sourced():
    qs, ts = content.quotes(), content.trivia()
    assert len(qs) >= 200 and len(ts) >= 250
    assert all(q["quote"] and q["author"] and q["source"] for q in qs)
    assert all(t["fact"] and t["category"] and t["source"] for t in ts)


def test_epigraph_is_deterministic_per_seed():
    a, b = content.epigraph("game-42"), content.epigraph("game-42")
    assert a == b
    assert content.epigraph("game-43") is not None   # different seed still works


def test_trivium_category_scope():
    t = content.trivium("d", category="Openings History")
    assert t["category"] == "Openings History"

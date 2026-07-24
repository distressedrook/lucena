"""Black-box tests for `lucena_core.metrics.space_report`'s edge rule.

The space badge names a side only when its RAW regional space lead reaches
`_SPACE_EDGE_MIN` (2). These tests pin that boundary and the color-mirror
anti-symmetry so the h3/a6 single-nudge case (raw lead 1) can never regain a
badge, and so a real raw-lead-2 front keeps one. python-chess is used only as
a board constructor/oracle (permitted under tests/).
"""

import chess
import pytest

from lucena_core import metrics


def _pawns(white, black):
    """A minimal legal FEN: both kings on the e-file plus the given pawns
    (by square name). Kept off the a/h files so they never add to the
    queenside/kingside space count under test."""
    b = chess.Board.empty()
    b.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    b.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    for name in white:
        b.set_piece_at(chess.parse_square(name), chess.Piece(chess.PAWN, chess.WHITE))
    for name in black:
        b.set_piece_at(chess.parse_square(name), chess.Piece(chess.PAWN, chess.BLACK))
    return b.fen()


# region under test = queenside (files a,b,c). Each row: (white pawns,
# black pawns, expected raw lead W-B, expected edge).
_EDGE_CASES = [
    # both fronts equally advanced -> lead 0, no edge even though both hold space
    (["a4"], ["a5"], 0, None),
    # one square more advanced -> lead 1 (the h3/a6 shape) -> NO badge
    (["a4"], ["a6"], 1, None),
    (["a3"], [],     1, None),
    # a genuinely more-advanced front -> lead 2 -> fires
    (["a4"], [],     2, "White"),
    (["a4", "b4"], ["a6"], 3, "White"),
]


@pytest.mark.parametrize("white,black,lead,edge", _EDGE_CASES)
def test_space_edge_raw_lead_boundary(white, black, lead, edge):
    sp = metrics.space_report(_pawns(white, black))
    q = sp["queenside"]
    assert q["white"]["raw"] - q["black"]["raw"] == lead
    assert q["edge"] == edge


@pytest.mark.parametrize("white,black,lead,edge", _EDGE_CASES)
def test_space_edge_color_mirror_antisymmetry(white, black, lead, edge):
    """Mirroring the board (swap colors + flip ranks) must flip the raw lead
    sign and the named side; a None edge stays None."""
    fen = _pawns(white, black)
    mfen = chess.Board(fen).mirror().fen()
    mq = metrics.space_report(mfen)["queenside"]
    assert mq["white"]["raw"] - mq["black"]["raw"] == -lead
    mirrored_edge = {"White": "Black", "Black": "White", None: None}[edge]
    assert mq["edge"] == mirrored_edge


def test_space_edge_reported_h3_a6_position_has_no_badge():
    """The real Giuoco Pianissimo that surfaced the bug (White h3, Black a6):
    single rook-pawn nudges on opposite wings must name no side."""
    fen = "r1bq1rk1/1pp2ppp/p1np1n2/2b1p3/2B1P3/3P1N1P/PPP2PP1/RNBQR1K1 w - - 0 8"
    sp = metrics.space_report(fen)
    assert sp["kingside"]["edge"] is None
    assert sp["queenside"]["edge"] is None
    assert sp["center"]["edge"] is None


def test_space_report_retains_percentile_score_as_payload():
    """`score` (the GM percentile) is no longer a decision input but must
    stay in the payload as diagnostics."""
    sp = metrics.space_report(_pawns(["a4"], []))
    for region in ("queenside", "center", "kingside"):
        for side in ("white", "black"):
            entry = sp[region][side]
            assert "score" in entry and isinstance(entry["score"], float)
            assert "raw" in entry and isinstance(entry["raw"], int)

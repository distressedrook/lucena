"""game_phase / development_debts — the 2026-07-25 redefinition.

Opening vs middlegame is DEVELOPMENT, stated concretely: a minor still on its
original square, or a king still on e1/e8 holding castling rights. No ply
window, no book lookup, no rook-connection tell (owner: "the ply 20 isn't
working ... be concrete about what opening means", "sometimes the rook may
not be connected at all"). The game reaches the middlegame the moment EITHER
side finishes; `developed` reports it per side so a lagging side's debt is
still visible to consumers. Endgame stays material-gated and takes
precedence.
"""

import chess

from lucena_core.reads import development_debts, game_phase


def test_startpos_is_the_opening_with_every_debt():
    gp = game_phase(chess.STARTING_FEN)
    assert gp["phase"] == "opening"
    assert gp["developed"] == {"white": False, "black": False}
    d = development_debts(chess.Board(), chess.WHITE)
    assert d["minors"] == ["Bc1", "Bf1", "Nb1", "Ng1"]
    assert d["uncastled"] is True


def test_middlegame_when_either_side_finishes():
    # Both sides castled with every minor off its home square.
    fen = "r2q1rk1/pp2bppp/2n1bn2/3pp3/3PP3/2N1BN2/PPPQBPPP/R4RK1 w - - 6 11"
    gp = game_phase(fen)
    assert gp["phase"] == "middlegame"
    assert gp["developed"] == {"white": True, "black": True}
    assert gp["why"] == "both sides developed"


def test_a_lagging_side_still_reads_as_undeveloped():
    # White is done; Black's Bc8 never came out. Middlegame — but the debt is
    # not erased by the phase, it is reported per side (this is the case that
    # started the redefinition).
    fen = "r1bq2k1/p4R2/2np2rb/2p4Q/PpN1P2P/3P2P1/1PP5/5RK1 b - - 0 26"
    gp = game_phase(fen)
    assert gp["phase"] == "middlegame"
    assert gp["developed"] == {"white": True, "black": False}
    assert "Black still developing" in gp["why"]
    assert development_debts(chess.Board(fen), chess.BLACK)["minors"] == ["Bc8"]


def test_no_ply_cap():
    # Move 30, both sides shuffling with bishops home and kings on e1/e8: an
    # opening by development, whatever the move number says (the old rule
    # called this a middlegame purely because fullmove > 20).
    fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 10 30"
    gp = game_phase(fen)
    assert gp["phase"] == "opening"
    assert gp["developed"] == {"white": False, "black": False}


def test_endgame_takes_precedence_over_a_home_minor():
    # Nb1 is still home, but the material bar decides first.
    gp = game_phase("4k3/5ppp/8/8/8/8/5PPP/1N2K3 w - - 0 40")
    assert gp["phase"] == "endgame"
    assert gp["developed"]["white"] is False     # per-side truth still reported


def test_home_is_the_piece_s_OWN_square_not_the_back_rank():
    # A bishop retreated to b1 and a knight sitting on c1 are DEVELOPED
    # pieces standing on the back rank — b1 is a knight's home, c1 a
    # bishop's. Keying the test on the rank instead of the piece type would
    # invent debts here and hold the game in the opening forever.
    b = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/1BN1K3 w - - 0 25")
    assert development_debts(b, chess.WHITE)["minors"] == []
    # ...while the real thing — a knight on b1, a bishop on c1 — is a debt.
    b2 = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/1NB1K3 w - - 0 25")
    assert development_debts(b2, chess.WHITE)["minors"] == ["Bc1", "Nb1"]


def test_a_committed_king_is_not_a_debt():
    # King on e1 having LOST its rights is committed, not undeveloped — the
    # debt is castling rights you still hold and haven't used.
    b = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 20")
    assert development_debts(b, chess.WHITE)["uncastled"] is False
    b2 = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/4K2R w K - 0 20")
    assert development_debts(b2, chess.WHITE)["uncastled"] is True

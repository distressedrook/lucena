"""arms — the candidate explanations, and the leakage stripper.

Each arm turns a banked position into text a reader sees. They are scored
against the same baseline (no text at all), so an arm's whole job is to be the
only thing that differs.

| arm | source | role |
|---|---|---|
| A | raw MultiPV=4 from `eng_shards` | the floor — the status quo everyone complains about |
| B | `position_read.render(post_verify_json(...))` | the shipped deterministic read |
| C | `lexicalize.py` prose | DEFERRED — needs paid API; see `arm_c` |
| D | `actual_ucis` | what was really played, a human-play reference |

## Two modes, both reported

Naming the move is the shipped read's *job* — arm B says things like "Knight to
g5". A blanket strip would gut the artifact instead of testing it. So:

  * **as-shipped** — nothing removed. Answers "does the read help a player
    choose well?", the product question.
  * **stripped** — the answer move removed in every spelling. Answers "does the
    reader understand, or is it following instructions?"

The GAP between the two is the finding: a large as-shipped lift with a small
stripped lift means the read is a good hint machine and a weak explanation.

The stripper deliberately does NOT remove square names wholesale. The weakness
lines are ABOUT squares ("Holes at d3, b4, d4"); deleting those deletes the
content rather than the answer. It targets move tokens and piece-plus-
destination constructions, and its recall is measured (`--audit`), not assumed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import chess

import bank

_PLANS_SRC = Path(__file__).resolve().parent.parent / "lucena-plans" / "src"
if str(_PLANS_SRC) not in sys.path:
    sys.path.insert(0, str(_PLANS_SRC))

REDACTED = "[…]"

PIECE_WORDS = {
    "K": ("king",), "Q": ("queen",), "R": ("rook",),
    "B": ("bishop",), "N": ("knight",), "P": ("pawn",),
}


# ---------------------------------------------------------------- arms ------
def arm_a(pid: str, fen: str, pvs: list[dict], rolls: list[list[str]]) -> str | None:
    """The raw engine dump — deliberately unhelpful, and the number to beat.

    Rendered the way an engine UI shows it: each line's eval and its moves in
    SAN, best first. This is what a player actually sees today.
    """
    if not pvs:
        return None
    sign = 1 if bank.white_to_move(fen) else -1
    ordered = sorted((p for p in pvs if p.get("ucis")),
                     key=lambda p: -sign * p["cp"])
    lines = []
    for i, pv in enumerate(ordered, 1):
        board = chess.Board(fen)
        sans = []
        for uci in pv["ucis"][:12]:
            try:
                move = chess.Move.from_uci(uci)
                sans.append(board.san(move))
                board.push(move)
            except (ValueError, AssertionError):
                break
        cp = sign * pv["cp"] / 100.0
        lines.append(f"Line {i} ({cp:+.2f}): {' '.join(sans)}")
    return "\n".join(lines) if lines else None


def arm_b(pid: str, fen: str, pvs: list[dict], rolls: list[list[str]]) -> str | None:
    """The shipped deterministic read. Returns None when `render` declines
    (no plan and no weakness) — the caller records that as a skip, not as an
    empty explanation, because an empty string is a different stimulus."""
    import fact_sheet
    import position_read
    try:
        post = fact_sheet.post_verify_json(fen, pvs, rolls)
    except Exception:
        return None
    return position_read.render(post)


def arm_c(pid: str, fen: str, pvs: list[dict], rolls: list[list[str]]) -> str | None:
    """DEFERRED. `lexicalize.py` calls Gemini, which costs money per position.

    Arms A, B and D need no LLM on the producer side, so the first number is
    obtainable at zero cost — and if it shows the deterministic read already
    beats the raw dump, arm C's marginal question ("does prose beat structured
    text?") is worth paying for. Ordering it the other way spends money before
    the harness has demonstrated it can measure anything.

    Note when it IS built: the local student is Gemma and this arm's lexicalizer
    is Gemini — same vendor lineage, so same-family affinity may inflate it.
    Record that as a caveat on arm C specifically.
    """
    return None


def arm_d(pid: str, fen: str, pvs: list[dict], rolls: list[list[str]],
          actual_ucis: list[str] | None = None) -> str | None:
    """What was actually played in the game — a human-play reference.

    NOT a ceiling: the game continuation is one player's choice at one moment,
    frequently not eval-equal. It is here because "a strong human went this
    way" is a different kind of information from an engine line, and worth
    measuring separately.
    """
    if not actual_ucis:
        return None
    board = chess.Board(fen)
    sans = []
    for uci in actual_ucis[:12]:
        try:
            move = chess.Move.from_uci(uci)
            sans.append(board.san(move))
            board.push(move)
        except (ValueError, AssertionError):
            break
    if not sans:
        return None
    return "The game continued: " + " ".join(sans)


ARMS = {"A": arm_a, "B": arm_b, "C": arm_c, "D": arm_d}


# ------------------------------------------------------------ stripper ------
def _san_variants(fen: str, uci: str) -> set[str]:
    """Every spelling of one move the text might use."""
    out: set[str] = {uci}
    board = chess.Board(fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return out
    if move not in board.legal_moves:
        return out
    san = board.san(move)
    out.add(san)
    out.add(san.rstrip("+#"))
    out.add(san.replace("x", ""))
    piece = board.piece_at(move.from_square)
    dest = chess.square_name(move.to_square)
    out.add(dest)
    if piece:
        for word in PIECE_WORDS[piece.symbol().upper()]:
            out.add(f"{word} to {dest}")
            out.add(f"{word} {dest}")
    return {v for v in out if v}


def strip_move(text: str, fen: str, uci: str) -> tuple[str, int]:
    """Remove every spelling of `uci` from `text`. Returns (text, n_removed).

    The count is the point: it makes stripper recall measurable instead of
    assumed. A strip that silently removes nothing would let a leaked answer
    through under the label "stripped".
    """
    removed = 0
    out = text
    # Longest first, so "knight to g5" is caught before the bare "g5" inside it.
    for variant in sorted(_san_variants(fen, uci), key=len, reverse=True):
        pattern = re.compile(
            (r"\b" if variant[0].isalnum() else "") + re.escape(variant)
            + (r"\b" if variant[-1].isalnum() else ""),
            re.IGNORECASE)
        out, n = pattern.subn(REDACTED, out)
        removed += n
    return out, removed


def render(arm: str, pid: str, row: dict, pvs: list[dict],
           rolls: list[list[str]]) -> str | None:
    fn = ARMS[arm]
    if arm == "D":
        return fn(pid, row["fen"], pvs, rolls, row.get("actual_ucis"))
    return fn(pid, row["fen"], pvs, rolls)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="render each arm for one position, and audit the stripper")
    ap.add_argument("--id", default=None)
    ap.add_argument("--audit", action="store_true",
                    help="also show the stripped form and removal counts")
    args = ap.parse_args()

    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts("2400v2400")
    pid = args.id or sorted(set(bench) & set(eng) & set(rolls))[0]
    row = bench[pid]

    print(f"id  {pid}\nfen {row['fen']}\n")
    best = sorted(((1 if bank.white_to_move(row["fen"]) else -1) * p["cp"], p)
                  for p in eng[pid] if p.get("ucis"))[-1][1]
    answer = best["ucis"][0]
    print(f"answer move (UCI) {answer}\n")

    for arm in ("A", "B", "C", "D"):
        text = render(arm, pid, row, eng[pid], rolls[pid])
        print(f"=== ARM {arm} " + "=" * 50)
        if text is None:
            print("(declined / deferred)\n")
            continue
        print(text)
        if args.audit:
            stripped, n = strip_move(text, row["fen"], answer)
            print(f"\n--- stripped ({n} removals) ---")
            print(stripped)
        print()

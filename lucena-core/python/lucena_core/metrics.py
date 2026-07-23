"""Deterministic position metrics — the sheet-JSON score family, batch 2
(2026-07-23 owner work order). Pure geometry, no engine, every score
carries its evidence. Batch 1 (activity norms, king danger,
attack_viability, region_control, development_lag) lives in `positional`;
this module holds the newer reads:

  space_report     — per-region space (territory behind the pawn front)
                     AND the owner's counter-metric: space leaves holes
                     behind, so each region reports how exploitable the
                     space-taker's wake is for the opponent.
  pawn_breaks      — the lever inventory: which pawn breaks each side
                     still has (a side with none is strategically spent).
  passer_report    — passer momentum: rank, escort, blockade, free path.
  color_complex    — light/dark square control shares + the weak-complex
                     flag (low share with no bishop of that color).
  trapped_pieces   — pieces with no safe move (trapped) or one (restricted).

All shares/scores are uncalibrated raw geometry — the percentile/validation
treatment (activity precedent) follows per-metric as each earns it.
"""
from __future__ import annotations

import chess

_REGION_FILES = {"queenside": (0, 1, 2), "center": (3, 4),
                 "kingside": (5, 6, 7)}

# Benchmark verdicts (metrics_benchmark.py, full GM corpus, 2026-07-23) —
# which metrics may be SPOKEN vs carried as data only:
#   validated : passer_report (r +0.092), color_complex weak_for flag
#               (-8/-9pp), trapped_pieces (r +0.072), space_report space
#               (r +0.053), development_lag notable flag (+8.8pp quartile
#               spread; linear lag is noise — the gate design vindicated)
#   data-only : pawn_breaks (r +0.029 — inventory is real, edge claim is
#               not); the SPENT interpretation (no-breaks = handicap) is
#               RETIRED (benchmarked dead)
#   data-only : space exploitability wake — BOTH instruments (attacked-now
#               and viability-reach) benchmarked flat; the square list is
#               descriptive data, never an "eats the edge" claim. The real
#               test of that thesis needs the engine leg (GM space-takers
#               manage their wake — selection hides the counterfactual).
METRIC_TIERS = {"passer_report": "validated", "color_complex": "validated",
                "trapped_pieces": "validated", "space_report": "validated",
                "development_lag": "validated-flag-only",
                "pawn_breaks": "data-only"}


def _reachable(b: chess.Board, color: bool, sq: int) -> bool:
    """Can a `color` piece attack `sq` after ONE safe move? (the
    attack_viability reach test, scoped to a single target square)."""
    enemy_pawn_atk = chess.SquareSet()
    for p in b.pieces(chess.PAWN, not color):
        enemy_pawn_atk |= b.attacks(p)
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for s in b.pieces(pt, color):
            for t in b.attacks(s):
                pc = b.piece_at(t)
                if pc is not None and pc.color == color:
                    continue
                if t in enemy_pawn_atk:
                    continue
                b2 = b.copy(stack=False)
                b2.remove_piece_at(s)
                b2.set_piece_at(t, chess.Piece(pt, color))
                if sq in b2.attacks(t):
                    return True
    return False


# ---- space + exploitability -------------------------------------------------

def space_report(fen: str) -> dict:
    """Per region: each side's SPACE (squares its pawn front has claimed —
    ranks strictly behind the most advanced own pawn on each file, counted
    from the 2nd rank) and the EXPLOITABILITY of that space's wake (owner
    2026-07-23: 'white has more space, sure, but can this be exploited?'):
    holes behind the front that the OPPONENT can REACH — squares no own
    pawn can ever re-guard that an enemy piece attacks now, occupies, or
    is ONE SAFE MOVE from attacking (the attack_viability reach test —
    the attacked-now version benchmarked flat, metrics_benchmark
    2026-07-23; this is the upgraded instrument)."""
    b = chess.Board(fen)
    out = {}
    fronts = {}
    for color in (chess.WHITE, chess.BLACK):
        f2r = {}
        for s in b.pieces(chess.PAWN, color):
            f, r = chess.square_file(s), chess.square_rank(s)
            rel = r if color == chess.WHITE else 7 - r
            f2r[f] = max(f2r.get(f, 0), rel)
        fronts[color] = f2r
    for region, files in _REGION_FILES.items():
        blk = {}
        for color in (chess.WHITE, chess.BLACK):
            enemy = not color
            space = sum(max(0, fronts[color].get(f, 1) - 1) for f in files)
            # the wake: holes behind the front no own pawn can ever guard,
            # that the enemy attacks or sits on
            weak = []
            from .geometry import is_hole as _is_hole   # audited definition
            for f in files:
                front = fronts[color].get(f, 0)
                for rel in range(2, front):
                    r = rel if color == chess.WHITE else 7 - rel
                    sq = chess.square(f, r)
                    if not _is_hole(b, sq, color):
                        continue
                    pc = b.piece_at(sq)
                    eyed = bool(b.attackers(enemy, sq)) or \
                        (pc is not None and pc.color == enemy) or \
                        _reachable(b, enemy, sq)
                    if eyed:
                        weak.append(chess.square_name(sq))
            key = "white" if color == chess.WHITE else "black"
            blk[key] = {"space": space, "exploitable": weak}
        d = blk["white"]["space"] - blk["black"]["space"]
        blk["edge"] = ("White" if d >= 2 else "Black" if d <= -2 else None)
        out[region] = blk
    return out


# ---- pawn breaks ------------------------------------------------------------

def pawn_breaks(fen: str) -> dict:
    """The lever inventory: pawn pushes (one or two steps, push square
    empty) after which the pawn attacks an enemy pawn — the breaks each
    side still HAS. `playable` = the push square isn't outgunned (enemy
    attackers <= own defenders of the square); the rest are `prepared`
    ideas needing support first."""
    b = chess.Board(fen)
    out = {}
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        step = 8 if color == chess.WHITE else -8
        home = 1 if color == chess.WHITE else 6
        epawns = b.pieces(chess.PAWN, enemy)
        rows = []
        for s in b.pieces(chess.PAWN, color):
            targets = []
            for n in (1, 2):
                if n == 2 and chess.square_rank(s) != home:
                    break
                t = s + n * step
                if not 0 <= t <= 63 or b.piece_at(t) is not None:
                    break
                atk = chess.BB_PAWN_ATTACKS[color][t]
                hit = [chess.square_name(p) for p in epawns
                       if chess.BB_SQUARES[p] & atk]
                if hit:
                    playable = (len(b.attackers(enemy, t))
                                <= len(b.attackers(color, t)))
                    targets.append({"push": chess.square_name(t),
                                    "targets": sorted(hit),
                                    "playable": playable})
            for t in targets:
                t["pawn"] = chess.square_name(s)
                rows.append(t)
        out["white" if color == chess.WHITE else "black"] = rows
    return out


# ---- passers ---------------------------------------------------------------

def passer_report(fen: str) -> dict:
    """Passer momentum, statically: each passed pawn's square, relative
    rank (0 home .. 6 about to promote), escort (own pawn or piece guards
    it), blockade (enemy piece on the stop square), and whether the path
    to promotion is currently empty."""
    b = chess.Board(fen)
    from .geometry import passers as _passers    # the ONE copy (2026-07-23)
    out = {}
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        rows = []
        for s in _passers(b, color):
            f, r = chess.square_file(s), chess.square_rank(s)
            ahead = range(r + 1, 8) if color == chess.WHITE else range(0, r)
            rel = r if color == chess.WHITE else 7 - r
            stop = s + (8 if color == chess.WHITE else -8)
            stop_pc = b.piece_at(stop) if 0 <= stop <= 63 else None
            path = [chess.square(f, rr) for rr in ahead]
            rows.append({
                "square": chess.square_name(s),
                "rank": rel,
                "escorted": bool(b.attackers(color, s)),
                "blockaded": stop_pc is not None
                             and stop_pc.color == enemy,
                "path_clear": all(b.piece_at(q) is None for q in path),
            })
        rows.sort(key=lambda p: -p["rank"])
        out["white" if color == chess.WHITE else "black"] = rows
    return out


# ---- color complex ----------------------------------------------------------

def color_complex(fen: str) -> dict:
    """Control share of the light and dark squares (attacker counts +
    occupation, the region_control convention) and the weak-complex flag:
    a side below 0.4 share on a color WITH no bishop of that color has a
    weakness it cannot repair."""
    b = chess.Board(fen)
    from .geometry import control_share as _cs   # the ONE copy (2026-07-23)

    def share(sq) -> float:
        return _cs(b, sq)

    out = {}
    for name, mask in (("light", chess.BB_LIGHT_SQUARES),
                       ("dark", chess.BB_DARK_SQUARES)):
        sqs = list(chess.SquareSet(mask))
        w = sum(share(q) for q in sqs) / len(sqs)
        has = {c: any(chess.BB_SQUARES[s] & mask
                      for s in b.pieces(chess.BISHOP, c))
               for c in (chess.WHITE, chess.BLACK)}
        out[name] = {
            "white": round(w, 2), "black": round(1 - w, 2),
            "weak_for": ("White" if w < 0.4 and not has[chess.WHITE] else
                         "Black" if 1 - w < 0.4 and not has[chess.BLACK]
                         else None),
        }
    return out


# ---- trapped pieces ---------------------------------------------------------

def trapped_pieces(fen: str) -> dict:
    """Pieces (N/B/R/Q) with no safe move (`trapped`) or exactly one
    (`restricted`). Safe = the destination isn't guarded by an enemy pawn,
    and if attacked at all, it is at least as defended (a cheap SEE
    stand-in — geometry, not tactics; the tactics layer prices the rest)."""
    b = chess.Board(fen)
    out = {"white": [], "black": []}
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        pawn_atk = chess.SquareSet()
        for p in b.pieces(chess.PAWN, enemy):
            pawn_atk |= b.attacks(p)
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            for s in b.pieces(pt, color):
                safe = 0
                for t in b.attacks(s):
                    pc = b.piece_at(t)
                    if pc is not None and pc.color == color:
                        continue
                    if t in pawn_atk:
                        continue
                    if len(b.attackers(enemy, t)) > len(b.attackers(color, t)):
                        continue
                    safe += 1
                    if safe > 1:
                        break
                if safe <= 1:
                    out["white" if color == chess.WHITE else "black"].append({
                        "piece": chess.piece_symbol(pt).upper(),
                        "square": chess.square_name(s),
                        "state": "trapped" if safe == 0 else "restricted",
                    })
    return out

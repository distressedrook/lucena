"""Deterministic positional analysis — the five classical terms, in centipawns.

Grounds the coach's opening "analysis" beat: material, king safety, piece
activity, pawn structure and centre control, each computed exactly from board
geometry (no engine call, no LLM) with constants adopted from published
standards, never invented:

- piece-square tables + material values: PeSTO (R. Friederich), machine-
  extracted into `_pesto.py` by tools/gen_pesto.py — 768 constants, never
  hand-typed;
- king safety: the CPW attack-units -> safety-table model (Glaurung 1.2 table;
  zone = king ring + three forward squares; units N/B=2 R=3 Q=5);
- mobility / pawn-structure weights: CPW reference values, simplified where
  noted.

These terms are SALIENCE, never a verdict (the LLD §2.3 hierarchy applies
unchanged): they are never summed into an eval and never adjudicate who is
better — Stockfish owns the verdict, and a term that contradicts the engine
loses. The terms decompose *why*, so the coach leads with the dimension that
actually characterises the position and cites exact features instead of
eyeballing the board. All cp values are White-POV; `standing` strings are
plain sentences the coach reads verbatim (no raw numbers — contract rule).

Known honest limitation: static king safety is a *middlegame pawn-shield*
model. It tapers out in endgames, where a concrete mating attack (a king
caught on h5) is tactical, not positional — that danger is the null-move
threat probe's job, not this module's. The two are complementary by design.
"""

from __future__ import annotations

from ._pesto import EG_TABLE, EG_VALUE, MG_TABLE, MG_VALUE
from .reads import PIECE_NAME, king_square, occupancy

# --- CPW king-safety model (Glaurung 1.2 safety table, verbatim) ------------
SAFETY_TABLE = [
    0, 0, 0, 1, 1, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 25, 30, 36, 42, 48,
    55, 62, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190,
    200, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 310, 320, 330,
    340, 350, 360, 370, 380, 390, 400, 410, 420, 430, 440, 450, 460, 470,
    480, 490, 500, 510, 520, 530, 540, 550, 560, 570, 580, 590, 600, 610,
    620, 630, 640, 650, 650, 650, 650, 650, 650, 650, 650, 650, 650, 650,
    650, 650, 650, 650, 650, 650, 650, 650, 650,
]
_ATTACK_UNITS = {"N": 2, "B": 2, "R": 3, "Q": 5}   # per attacked zone square

# game-phase increments (PeSTO): minors 1, rooks 2, queens 4; 24 = full MG
_PHASE_INC = {"N": 1, "B": 1, "R": 2, "Q": 4}

# simplified CPW-style mobility: cp per square above/below a typical count
_MOBILITY = {"N": (4, 4), "B": (6, 3), "R": (7, 2), "Q": (13, 1)}  # (baseline, weight)

# pawn-structure weights (mg, eg), simplified CPW reference values
_ISOLATED = (-15, -12)          # per isolated pawn
_DOUBLED = (-10, -20)           # per extra pawn on a file
_ISLAND = (-8, -8)              # per island beyond the first
_PASSED = [(0, 0), (5, 15), (12, 25), (20, 40), (35, 65), (60, 105),
           (100, 160), (0, 0)]  # by relative rank (0 = home, 6 = about to promote)

# centre model: occupation + attack differential on the four core squares
_CORE = ("d4", "e4", "d5", "e5")
_OCCUPY = {"P": (18, 6), "N": (8, 4), "B": (8, 4), "R": (4, 2), "Q": (4, 2)}
_CONTROL = (7, 3)               # cp per net attacker on a core square

_FILES = "abcdefgh"
_LEAD_THRESHOLD = 25            # |cp| for a term to lead the analysis


def _fr(square: str) -> tuple[int, int]:
    return _FILES.index(square[0]), int(square[1]) - 1


def _sq(f: int, r: int) -> str:
    return _FILES[f] + str(r + 1)


def _on(f: int, r: int) -> bool:
    return 0 <= f < 8 and 0 <= r < 8


def _pst(table: dict, piece: str, color: str, square: str) -> int:
    """PeSTO tables are published a8-first (White's visual view); Black mirrors
    the rank."""
    f, r = _fr(square)
    idx = (7 - r) * 8 + f if color == "white" else r * 8 + f
    return table[piece][idx]


def _taper(mg: float, eg: float, phase: float) -> float:
    return mg * phase + eg * (1.0 - phase)


def _side_name(color: str) -> str:
    return "White" if color == "white" else "Black"


# --- shared geometry ---------------------------------------------------------

def _attack_maps(board):
    """One pass over all 64 squares: per-square attacker counts and, inverted,
    per-piece attacked-square sets. `board.attackers` is the only primitive."""
    ctrl: dict[str, tuple[int, int]] = {}
    attacks: dict[str, set[str]] = {}
    for f in range(8):
        for r in range(8):
            s = _sq(f, r)
            w = board.attackers(s, "white")
            b = board.attackers(s, "black")
            ctrl[s] = (len(w), len(b))
            for a in w + b:
                attacks.setdefault(a, set()).add(s)
    return ctrl, attacks


def _phase(occ) -> float:
    gp = sum(_PHASE_INC.get(p.piece, 0) for p in occ.values())
    return min(gp, 24) / 24.0


# --- the five terms ----------------------------------------------------------

def _material_term(board) -> dict:
    """Tapered PeSTO material in cp; the standing sentence is the exact-imbalance
    phrase (single source of truth in mcp.response — lazy import, noted layering
    wart until material() moves engine-side)."""
    from .reads import material as _material

    occ = occupancy(board)
    ph = _phase(occ)
    cp = 0.0
    for _, p in sorted(occ.items()):     # canonical float order (see _activity_term)
        v = _taper(MG_VALUE[p.piece], EG_VALUE[p.piece], ph)
        cp += v if p.color == "white" else -v
    return {"cp": round(cp), "standing": _material(board)["standing"]}


def _king_zone(ksq: str, color: str) -> list[str]:
    """CPW zone: the king ring plus three squares two ranks toward the enemy."""
    kf, kr = _fr(ksq)
    zone = [_sq(kf + df, kr + dr) for df in (-1, 0, 1) for dr in (-1, 0, 1)
            if (df or dr) and _on(kf + df, kr + dr)]
    fwd = 2 if color == "white" else -2
    zone += [_sq(kf + df, kr + fwd) for df in (-1, 0, 1) if _on(kf + df, kr + fwd)]
    return zone


def _king_safety_term(board, occ, ph: float) -> dict:
    features = {}
    danger = {}
    pst = {}
    for color in ("white", "black"):
        enemy = "black" if color == "white" else "white"
        ksq = king_square(board, color)
        if ksq is None:                          # analysis boards can be kingless
            danger[color], pst[color] = 0.0, 0.0
            continue
        kf, kr = _fr(ksq)
        pst[color] = _taper(_pst(MG_TABLE, "K", color, ksq),
                            _pst(EG_TABLE, "K", color, ksq), ph)

        # attack units: enemy N/B/R/Q attacks into the zone (CPW weights)
        zone = _king_zone(ksq, color)
        units, attackers = 0, {}
        for zs in zone:
            for a in board.attackers(zs, enemy):
                p = occ.get(a)
                if p is not None and p.piece in _ATTACK_UNITS:
                    units += _ATTACK_UNITS[p.piece]
                    attackers[a] = p.piece
        zone_penalty = SAFETY_TABLE[min(units, 99)] if len(attackers) >= 2 else 0

        # pawn shield: the three files around the king, one/two steps ahead
        fwd = 1 if color == "white" else -1
        shield, shield_penalty = 0, 0
        for df in (-1, 0, 1):
            if not _on(kf + df, kr + fwd):
                continue
            p1 = occ.get(_sq(kf + df, kr + fwd))
            p2 = occ.get(_sq(kf + df, kr + 2 * fwd)) if _on(kf + df, kr + 2 * fwd) else None
            if p1 is not None and p1.color == color and p1.piece == "P":
                shield += 1
            elif p2 is not None and p2.color == color and p2.piece == "P":
                shield += 1
                shield_penalty += 6              # advanced one step: half airy
            else:
                shield_penalty += 14             # no pawn on this file at all

        # open / half-open files beside the king (only if enemy heavy pieces exist)
        own_pawn_files = {_fr(s)[0] for s, p in occ.items()
                          if p.color == color and p.piece == "P"}
        enemy_pawn_files = {_fr(s)[0] for s, p in occ.items()
                            if p.color == enemy and p.piece == "P"}
        heavy = any(p.piece in ("R", "Q") and p.color == enemy for p in occ.values())
        open_files, file_penalty = [], 0
        if heavy:
            for df in (-1, 0, 1):
                f = kf + df
                if not _on(f, 0) or f in own_pawn_files:
                    continue
                open_files.append(_FILES[f])
                file_penalty += 15 if f not in enemy_pawn_files else 10

        # centred, uncastled king (2026-07-22): a king still on the d/e
        # file with enemy heavies on and an open/half-open file beside it
        # is the classic "stuck in the middle" danger — which the other
        # components structurally miss (the zone gate needs TWO attackers,
        # so a lone staring queen counts zero; the shield happily credits
        # e6/f7 pawns while the king's ADDRESS is the problem). Gated on
        # `open_files` so it can never fire in closed positions or at the
        # start position (all files closed there), and on `heavy` via
        # open_files' own gate.
        center_penalty = 0
        if kf in (3, 4) and open_files:
            has_q = any(p.piece == "Q" and p.color == enemy
                        for p in occ.values())
            center_penalty = 35 if has_q else 15

        # shield/file penalties are middlegame concepts; zone attacks keep a
        # small endgame tail (a cornered king can still be hunted)
        danger[color] = _taper(zone_penalty + shield_penalty + file_penalty
                               + center_penalty,
                               zone_penalty / 4.0, ph)
        features[color] = {
            "king": ksq,
            "danger": round(danger[color]),   # the composite (2026-07-23:
                                              # exposed for the efficacy
                                              # studies + future norm)
            "zone_attackers": sorted(f"{PIECE_NAME.get(pc, pc)} on {s}"
                                     for s, pc in attackers.items()),
            "attack_units": units,
            "shield_pawns": shield,
            "open_files_nearby": open_files,
            "centered_uncastled": center_penalty > 0,
        }

    cp = (danger["black"] - danger["white"]) + (pst["white"] - pst["black"])
    worse = max(danger, key=lambda c: danger[c])
    d = danger[worse]
    if d >= 100:
        ft = features[worse]
        bits = [f"{len(ft['zone_attackers'])} enemy pieces attack the squares around it"]
        if ft["open_files_nearby"]:
            bits.append(f"the {'/'.join(ft['open_files_nearby'])}-file beside it is open")
        if ft["shield_pawns"] == 0:
            bits.append("it has no pawn shield")
        standing = f"{_side_name(worse)}'s king is in danger — " + ", and ".join(bits)
    elif d >= 40:
        standing = f"{_side_name(worse)}'s king is a little exposed"
    else:
        standing = "both kings are reasonably safe"
    return {"cp": round(cp), "standing": standing, "features": features}


# The 0-1 normalized activity score is a GM-PRACTICE PERCENTILE, now
# PHASE-CONDITIONED (2026-07-23 owner ruling: "rooks and queens always lose
# in the middlegame" — the flat grids pooled endgame rooks, which own the
# distribution's top, so no middlegame rook could ever score well): norm
# 0.62 = "more active than 62% of same-type pieces in the SAME PHASE of GM
# play". Grids are raw-score quantiles (p0..p100, step 5) fitted over the
# full GM corpus (33,769 games, 4.7M piece observations, phases via
# reads.game_phase with hysteresis) by
# lucena-plans/research/experiments/studies/activity_calibration2.py —
# regenerate there if the score formula or classifier changes. Embedded
# like the PeSTO tables: data, hand-checked, deterministic.
_ACT_QUANTILES = {
    "opening": {
        "N": [-169.9, -29.0, -29.0, -26.9, -25.0, -23.0, -9.0, -3.0, 12.0,
              16.0, 16.0, 18.0, 20.0, 20.7, 21.0, 21.0, 21.0, 24.3, 25.0,
              28.0, 145.0],
        "B": [-79.0, -32.0, -30.3, -29.4, -27.3, -24.0, -18.3, -17.0, -17.0,
              -17.0, -15.0, -15.0, -5.0, 1.0, 5.1, 9.7, 13.0, 16.0, 21.0,
              24.0, 65.0],
        "R": [-81.0, -38.0, -38.0, -38.0, -36.0, -36.0, -35.5, -33.0, -33.0,
              -33.0, -32.0, -31.0, -31.0, -29.3, -29.0, -27.0, -25.0, -7.0,
              -5.0, -1.0, 69.7],
        "Q": [-60.2, -7.8, -4.8, -3.0, -2.0, -2.0, -1.0, -1.0, 0.0, 0.0,
              0.8, 1.0, 1.6, 2.0, 2.0, 3.0, 3.0, 4.0, 5.0, 6.6, 59.0],
    },
    "middlegame": {
        "N": [-165.9, -29.0, -17.6, -9.0, -5.0, -1.2, 4.0, 12.0, 14.9, 16.0,
              17.8, 19.3, 20.2, 21.2, 23.0, 24.3, 26.0, 29.0, 34.5, 49.0,
              145.0],
        "B": [-82.1, -26.8, -18.5, -15.3, -9.5, -5.0, -0.5, 1.5, 3.8, 6.0,
              8.0, 10.0, 11.8, 13.8, 16.0, 17.7, 20.0, 22.0, 25.0, 30.0,
              68.0],
        "R": [-85.0, -31.0, -28.5, -26.2, -23.7, -20.5, -16.3, -11.0, -7.8,
              -6.3, -5.0, -3.0, -1.0, 1.3, 3.8, 6.0, 8.1, 10.3, 13.5, 19.0,
              87.1],
        "Q": [-61.2, -20.2, -15.2, -11.2, -8.0, -6.0, -4.8, -3.5, -2.5,
              -1.7, -1.0, -0.0, 1.0, 1.6, 2.6, 3.6, 5.0, 7.0, 11.0, 20.7,
              62.7],
    },
    "endgame": {
        "N": [-113.3, -29.7, -21.5, -14.7, -4.8, -0.8, 2.8, 6.2, 10.7, 13.3,
              15.7, 18.2, 21.8, 25.5, 28.0, 30.2, 33.0, 35.0, 37.8, 42.0,
              70.2],
        "B": [-52.6, -21.3, -16.0, -11.7, -7.2, -4.0, -1.0, 1.8, 4.3, 6.2,
              8.2, 10.4, 12.8, 14.0, 16.3, 18.8, 20.2, 22.4, 25.4, 29.1,
              47.1],
        "R": [-43.3, -18.3, -13.0, -9.8, -7.5, -5.0, -2.9, -1.0, 1.0, 2.7,
              4.5, 6.5, 8.5, 11.0, 13.2, 15.8, 18.5, 21.7, 25.8, 31.7,
              52.6],
        "Q": [-53.8, -20.2, -15.9, -12.3, -8.9, -5.5, -0.2, 4.3, 7.5, 10.3,
              13.0, 16.2, 20.0, 23.2, 26.0, 28.3, 31.0, 34.4, 38.7, 43.3,
              57.3],
    },
}

# development baseline: RAW mean activity score per (side, type, ply),
# plies 8-20, full GM corpus (activity_calibration2.py). SIDE-CONDITIONED
# (owner ruling 2026-07-23: "black is statistically always behind" — Black
# trails White by a tempo BY CONSTRUCTION, so lag judges each side against
# its OWN curve, or every Black position would "lag").
_DEV_BASELINE = {
    "white": {
        "N": {8: -0.4, 9: 3.8, 10: 3.3, 11: 5.8, 12: 4.9, 13: 6.7, 14: 6.1,
              15: 7.9, 16: 7.3, 17: 9.6, 18: 8.8, 19: 10.7, 20: 9.8},
        "B": {8: -16.3, 9: -12.2, 10: -12.6, 11: -8.3, 12: -9.1, 13: -5.5,
              14: -5.9, 15: -3.0, 16: -3.7, 17: -1.2, 18: -1.8, 19: 0.7,
              20: -0.0},
        "R": {8: -34.0, 9: -31.8, 10: -31.7, 11: -29.8, 12: -29.7,
              13: -27.6, 14: -27.6, 15: -25.4, 16: -25.3, 17: -23.2,
              18: -23.2, 19: -21.0, 20: -21.0},
        "Q": {8: 1.1, 9: 1.3, 10: 1.2, 11: 1.5, 12: 1.3, 13: 1.3, 14: 1.2,
              15: 1.2, 16: 0.9, 17: 0.9, 18: 0.6, 19: 0.5, 20: 0.3},
    },
    "black": {
        "N": {8: 0.6, 9: 0.4, 10: 3.1, 11: 2.3, 12: 4.8, 13: 4.3, 14: 6.6,
              15: 5.9, 16: 7.9, 17: 7.2, 18: 8.9, 19: 7.9, 20: 9.8},
        "B": {8: -16.4, 9: -16.7, 10: -13.8, 11: -14.5, 12: -11.3,
              13: -11.8, 14: -8.9, 15: -9.5, 16: -6.6, 17: -7.3, 18: -4.5,
              19: -5.2, 20: -2.9},
        "R": {8: -34.2, 9: -34.2, 10: -32.2, 11: -32.2, 12: -30.6,
              13: -30.6, 14: -28.6, 15: -28.6, 16: -26.2, 17: -26.2,
              18: -24.2, 19: -24.2, 20: -22.3},
        "Q": {8: 0.3, 9: 0.3, 10: 0.5, 11: 0.4, 12: 0.5, 13: 0.4, 14: 0.6,
              15: 0.4, 16: 0.3, 17: 0.1, 18: -0.0, 19: -0.3, 20: -0.3},
    },
}
DEV_LAG_NOTABLE = -15   # raw points behind own-side baseline before the
                        # margin may SPEAK it (data below, speech above —
                        # the annoyance gate, owner 2026-07-23)


def _act_norm(piece: str, score: float, phase: str = "middlegame") -> float:
    """Raw activity score -> same-phase GM-practice percentile in [0, 1],
    by linear interpolation on the (phase, type) quantile grid."""
    q = _ACT_QUANTILES.get(phase, _ACT_QUANTILES["middlegame"])[piece]
    if score <= q[0]:
        return 0.0
    if score >= q[-1]:
        return 1.0
    for i in range(1, len(q)):
        if score <= q[i]:
            lo, hi = q[i - 1], q[i]
            frac = (score - lo) / (hi - lo) if hi > lo else 1.0
            return ((i - 1) + frac) / (len(q) - 1)
    return 1.0


def _activity_term(board, occ, attacks, ph: float,
                   phase_name: str = "middlegame") -> dict:
    sums = {"white": 0.0, "black": 0.0}
    worst = {"white": None, "black": None}
    per_piece = {"white": [], "black": []}
    # Sorted by square: float accumulation order is part of determinism. The
    # Rust-era code summed in piece_list order; at exact .5 cp boundaries the
    # rounding depended on it (observed: 6/1000 corpus positions off by 1cp).
    # Canonical order makes the result a function of the position alone.
    for s, p in sorted(occ.items()):
        if p.piece not in _MOBILITY:             # kings/pawns live in other terms
            continue
        place = _taper(_pst(MG_TABLE, p.piece, p.color, s),
                       _pst(EG_TABLE, p.piece, p.color, s), ph)
        base, weight = _MOBILITY[p.piece]
        mob = sum(1 for t in attacks.get(s, ())
                  if occ.get(t) is None or occ[t].color != p.color)
        score = place + (mob - base) * weight
        sums[p.color] += score
        # per-piece breakdown (2026-07-23, sheet-JSON activity block): the
        # loop already knows every minor/major's score — keep it instead of
        # throwing it away. `score` is cp-flavored: PeSTO placement (phase-
        # tapered) + weighted mobility above the piece's baseline.
        per_piece[p.color].append({"square": s, "piece": p.piece,
                                   "score": round(score, 1), "mobility": mob,
                                   "placement": round(place, 1),
                                   "norm": round(_act_norm(p.piece, score,
                                                           phase_name), 2)})
        # tie-break on square so identical scores pick the same piece every run
        if worst[p.color] is None or (score, s) < worst[p.color][:2]:
            worst[p.color] = (score, s, p.piece)
    cp = sums["white"] - sums["black"]

    features = {}
    for color in ("white", "black"):
        # most-active first BY THE NORMALIZED SCORE (owner 2026-07-23);
        # raw-score then square tie-breaks keep it deterministic
        features[f"pieces_{color}"] = sorted(
            per_piece[color],
            key=lambda e: (-e["norm"], -e["score"], e["square"]))
        features[f"score_{color}"] = round(sums[color])
        if worst[color] is not None:
            _, s, pc = worst[color]
            features[f"worst_piece_{color}"] = {"square": s, "piece": pc}
    # The least-active piece lives in `features` (worst_piece_*) for a caller that wants it — NOT
    # glued onto the standing, where it fired on every activity mention (even at dead balance, always
    # naming the side-to-move's back rook) and dragged noise into the briefing.
    if cp >= _LEAD_THRESHOLD:
        standing = "White's pieces are the more active"
    elif cp <= -_LEAD_THRESHOLD:
        standing = "Black's pieces are the more active"
    else:
        standing = "piece activity is roughly balanced"
    return {"cp": round(cp), "standing": standing, "features": features}


def _pawn_features(occ, color: str) -> dict:
    enemy = "black" if color == "white" else "white"
    own = [s for s, p in occ.items() if p.color == color and p.piece == "P"]
    theirs = [s for s, p in occ.items() if p.color == enemy and p.piece == "P"]
    files: dict[int, list[int]] = {}
    for s in own:
        f, r = _fr(s)
        files.setdefault(f, []).append(r)
    efiles: dict[int, list[int]] = {}
    for s in theirs:
        f, r = _fr(s)
        efiles.setdefault(f, []).append(r)

    doubled = sorted(_FILES[f] for f, rs in files.items() if len(rs) > 1)
    isolated = sorted(s for s in own
                      if not any((_fr(s)[0] + d) in files for d in (-1, 1)))
    passed = []
    for s in own:
        f, r = _fr(s)
        ahead = range(r + 1, 8) if color == "white" else range(0, r)
        if not any(df in efiles and any(er in ahead for er in efiles[df])
                   for df in (f - 1, f, f + 1)):
            passed.append(s)
    islands, prev = 0, False
    for f in range(8):
        here = f in files
        islands += here and not prev
        prev = here
    extra_on_file = sum(len(rs) - 1 for rs in files.values())
    return {"doubled_files": doubled, "isolated": isolated,
            "passed": sorted(passed), "islands": islands,
            "_extra": extra_on_file}


def _pawns_term(board, occ, ph: float) -> dict:
    feats, score = {}, {}
    for color in ("white", "black"):
        f = _pawn_features(occ, color)
        cp = 0.0
        cp += len(f["isolated"]) * _taper(*_ISOLATED, ph)
        cp += f["_extra"] * _taper(*_DOUBLED, ph)
        cp += max(0, f["islands"] - 1) * _taper(*_ISLAND, ph)
        for s in f["passed"]:
            _, r = _fr(s)
            rel = r if color == "white" else 7 - r
            cp += _taper(*_PASSED[rel], ph)
        score[color] = cp
        feats[color] = {k: v for k, v in f.items() if not k.startswith("_")}
    cp = score["white"] - score["black"]

    phrases: list[tuple[float, str]] = []
    for color in ("white", "black"):
        name, f = _side_name(color), feats[color]
        if f["passed"]:
            best = max(f["passed"],
                       key=lambda s: _fr(s)[1] if color == "white" else 7 - _fr(s)[1])
            rel = _fr(best)[1] if color == "white" else 7 - _fr(best)[1]
            phrases.append((_taper(*_PASSED[rel], ph),
                            f"{name} has a passed pawn on {best}"))
        for s in f["isolated"]:
            phrases.append((abs(_taper(*_ISOLATED, ph)),
                            f"{name}'s {s} pawn is isolated"))
        for fl in f["doubled_files"]:
            phrases.append((abs(_taper(*_DOUBLED, ph)),
                            f"{name} has doubled pawns on the {fl}-file"))
    phrases.sort(key=lambda t: -t[0])
    standing = ("; ".join(p for _, p in phrases[:2])
                if phrases else "both pawn structures are healthy")
    return {"cp": round(cp), "standing": standing, "features": feats}


def _center_term(occ, ctrl, ph: float) -> dict:
    cp = 0.0
    held = {"white": [], "black": []}
    detail = {}
    for s in _CORE:
        p = occ.get(s)
        if p is not None and p.piece in _OCCUPY:
            v = _taper(*_OCCUPY[p.piece], ph)
            cp += v if p.color == "white" else -v
            held[p.color].append(s)
        w, b = ctrl[s]
        cp += (w - b) * _taper(*_CONTROL, ph)
        detail[s] = {"white_attackers": w, "black_attackers": b}
    if cp >= _LEAD_THRESHOLD:
        standing = "White controls the centre"
    elif cp <= -_LEAD_THRESHOLD:
        standing = "Black controls the centre"
    else:
        standing = "the centre is contested"
    for color in ("white", "black"):
        if held[color]:
            standing += f"; {_side_name(color)} holds {', '.join(held[color])}"
    return {"cp": round(cp), "standing": standing, "features": detail}


# --- assembly ----------------------------------------------------------------

def analyze_positional(board) -> dict:
    """The five-term positional decomposition for `board`.

    Returns `{phase, terms:{material,king_safety,activity,pawns,center},
    leads:[...]}` where each term is `{cp, standing, features?}` (cp White-POV)
    and `leads` names the terms salient enough to open the coaching with,
    strongest first. Purely board-geometric: no engine, deterministic, same
    input -> same output."""
    occ = occupancy(board)
    ph = _phase(occ)
    ctrl, attacks = _attack_maps(board)
    from .reads import game_phase as _gp
    try:
        phase_name = _gp(board.fen)["phase"]
    except Exception:
        phase_name = "middlegame"
    terms = {
        "material": _material_term(board),
        "king_safety": _king_safety_term(board, occ, ph),
        "activity": _activity_term(board, occ, attacks, ph, phase_name),
        "pawns": _pawns_term(board, occ, ph),
        "center": _center_term(occ, ctrl, ph),
    }
    leads = [k for k in sorted(terms, key=lambda k: -abs(terms[k]["cp"]))
             if abs(terms[k]["cp"]) >= _LEAD_THRESHOLD][:2]
    return {"phase": round(ph, 2), "terms": terms, "leads": leads}


# ---- attack viability ------------------------------------------------------
# (2026-07-23, owner request): the PROSPECTIVE sibling of the king-safety
# danger term. Danger prices attack infrastructure that EXISTS (attackers in
# the zone, files already open); this scores the viability of BUILDING it —
# the gap the annotator-validation test exposed ("attack on the king"
# comments scored BELOW control against the static term: annotators speak
# before the infrastructure exists). Classical attacking theory compiled to
# geometry: latent attackers, storm pawns + hooks, openable lines, a stable
# center, the queen. Hand-authored weights — audited by
# lucena-plans/research/experiments/studies/attack_viability_validation.py
# (corpus-scale validation before speech) and NOT yet percentile-calibrated.

_VIA_MAX = 14.0


def attack_viability(fen: str) -> dict:
    """{'white': {...}, 'black': {...}} — each side AS THE ATTACKER against
    the enemy king: score (raw), norm (score/max, clamped), components
    [{name, pts, why}]. Deterministic geometry; no engine."""
    import chess as _c
    b = _c.Board(fen)
    out = {}
    for color in (_c.WHITE, _c.BLACK):
        enemy = not color
        ek = b.king(enemy)
        comps = []
        if ek is None:
            out["white" if color else "black"] = {
                "score": 0, "norm": 0.0, "components": []}
            continue
        from .geometry import king_zone as _kz     # shared zone (2026-07-23)
        kf, kr = _c.square_file(ek), _c.square_rank(ek)
        zone = _kz(ek, enemy)
        enemy_pawn_atk = set()
        for ps in b.pieces(_c.PAWN, enemy):
            enemy_pawn_atk |= set(b.attacks(ps))

        # 1. LATENT ATTACKERS: pieces already bearing on the zone (x2) plus
        # pieces one SAFE move from bearing on it (landing square not
        # guarded by an enemy pawn) — the attack mass that can assemble.
        now, reach = [], []
        for pt in (_c.KNIGHT, _c.BISHOP, _c.ROOK, _c.QUEEN):
            for s in b.pieces(pt, color):
                if set(b.attacks(s)) & zone:
                    now.append(s)
                    continue
                found = False
                for t in b.attacks(s):
                    pc = b.piece_at(t)
                    if pc is not None and pc.color == color:
                        continue
                    if t in enemy_pawn_atk:
                        continue
                    b2 = b.copy(stack=False)
                    b2.remove_piece_at(s)
                    b2.set_piece_at(t, _c.Piece(pt, color))
                    if set(b2.attacks(t)) & zone:
                        found = True
                        break
                if found:
                    reach.append(s)
        pts = min(6, 2 * len(now) + len(reach))
        if pts:
            comps.append(("latent attackers", pts,
                          f"{len(now)} piece(s) already bear on the king "
                          f"zone, {len(reach)} more are one safe move away"))

        # 2. STORM PAWNS + HOOK: own pawns near the enemy king's files that
        # can still march, plus the classical hook (an advanced enemy
        # shield pawn a storm pawn can lever open).
        storm = 0
        for s in b.pieces(_c.PAWN, color):
            f, r = _c.square_file(s), _c.square_rank(s)
            if abs(f - kf) <= 1 and abs(r - kr) <= 4:
                step = _c.square(f, r + (1 if color == _c.WHITE else -1)) \
                    if 0 <= r + (1 if color == _c.WHITE else -1) <= 7 else None
                if step is not None and b.piece_at(step) is None:
                    storm += 1
        hook = 0
        base = 1 if enemy == _c.WHITE else 6
        for s in b.pieces(_c.PAWN, enemy):
            f, r = _c.square_file(s), _c.square_rank(s)
            if abs(f - kf) <= 1 and r != base:
                hook = 1
                break
        pts = min(4, storm + hook)
        if pts:
            why = f"{storm} pawn(s) free to storm the king's wing"
            if hook:
                why += "; an advanced shield pawn offers a lever hook"
            comps.append(("storm pawns", pts, why))

        # 3. OPENABLE LINES: files beside the enemy king with no own pawn
        # (heavies can land or the file can open) — only with a heavy on.
        heavies = list(b.pieces(_c.ROOK, color)) + list(b.pieces(_c.QUEEN, color))
        own_pawn_files = {_c.square_file(s) for s in b.pieces(_c.PAWN, color)}
        lines = [f for f in (kf - 1, kf, kf + 1)
                 if 0 <= f <= 7 and f not in own_pawn_files] if heavies else []
        pts = min(2, len(lines))
        if pts:
            comps.append(("open lines", pts,
                          f"{len(lines)} file(s) by the king carry no own "
                          "pawn — heavies can use or open them"))

        # 4. STABLE CENTER: the classical precondition for a wing attack —
        # central rams with no central tension can't counter-open the middle.
        from .geometry import center_skeleton as _csk   # shared (2026-07-23)
        rams, tension = _csk(b)
        if rams >= 2 and tension == 0:
            comps.append(("stable center", 2,
                          "the center is locked — no central counterplay "
                          "can answer a wing attack"))
        elif tension == 0:
            comps.append(("stable center", 1, "no central pawn tension"))

        score = sum(p for _, p, _ in comps)
        if not b.pieces(_c.QUEEN, color) and score:
            score = round(score / 2)
            comps.append(("no queen", 0,
                          "own queen is off — attack potential halved"))
        out["white" if color == _c.WHITE else "black"] = {
            "score": score,
            "norm": round(min(1.0, score / _VIA_MAX), 2),
            "components": [{"name": n, "pts": p, "why": w}
                           for n, p, w in comps],
        }
    return out


# ---- region control --------------------------------------------------------
# (2026-07-23, owner request): deterministic control scores for the board's
# KEY REGIONS — center, wings, holes/outposts, open files. Control of a
# square = attacker share (occupation weighs extra, pawns most); a region's
# score is its mean square share. Pure geometry, no engine; every verdict
# carries its evidence. Shares are UNCALIBRATED means (0.5 = contested) —
# the percentile treatment can follow the activity precedent if a consumer
# needs cross-position claims.

_CORE_SQ = ("d4", "e4", "d5", "e5")
_LEAD_SHARE = 0.60          # region leader needs this share; else contested


def region_control(fen: str) -> dict:
    import chess as _c
    b = _c.Board(fen)

    from .geometry import control_share as _cs   # the ONE copy (2026-07-23)

    def _share(sq) -> float:
        return _cs(b, sq)

    def _region(squares) -> dict:
        s = sum(_share(sq) for sq in squares) / len(squares)
        leader = ("White" if s >= _LEAD_SHARE else
                  "Black" if s <= 1 - _LEAD_SHARE else None)
        return {"white": round(s, 2), "black": round(1 - s, 2),
                "leader": leader}

    center = _region([_c.parse_square(q) for q in _CORE_SQ])
    kingside = _region([_c.square(f, r) for f in (5, 6, 7)
                        for r in (2, 3, 4, 5)])
    queenside = _region([_c.square(f, r) for f in (0, 1, 2)
                         for r in (2, 3, 4, 5)])

    # holes: squares on the usable ranks of a camp that no pawn of that camp
    # can EVER guard (no friendly pawn on an adjacent file able to advance
    # into guarding position) — the permanent geography. An occupied hole
    # with own-pawn protection is the classical OUTPOST.
    from .geometry import is_hole as _is_hole    # the audited definition
    holes = []
    for camp, ranks in ((_c.BLACK, (3, 4, 5)), (_c.WHITE, (2, 3, 4))):
        beneficiary = not camp
        for r in ranks:
            for f in range(8):
                sq = _c.square(f, r)
                if not _is_hole(b, sq, camp):
                    continue
                # only holes a pawn COULD have guarded matter (files a-h
                # edge squares still qualify; off-board neighbours don't
                # make something a hole on an empty board — require at
                # least central-usable relevance: skip rank-edge noise by
                # requiring the beneficiary to reach it at all)
                share = _share(sq)
                bshare = share if beneficiary == _c.WHITE else 1 - share
                if bshare < 0.5 and b.piece_at(sq) is None:
                    continue                      # a hole nobody exploits
                pc = b.piece_at(sq)
                occupied = (pc is not None and pc.color == beneficiary
                            and pc.piece_type in (_c.KNIGHT, _c.BISHOP))
                pawn_backed = bool(b.attackers(beneficiary, sq)
                                   & b.pieces(_c.PAWN, beneficiary))
                holes.append({
                    "square": _c.square_name(sq),
                    "camp": "black" if camp == _c.BLACK else "white",
                    "controller": ("White" if share >= _LEAD_SHARE else
                                   "Black" if share <= 1 - _LEAD_SHARE
                                   else None),
                    "occupied": occupied,
                    "outpost": occupied and pawn_backed,
                })

    # files: open / half-open, and who holds them (heavies on the file)
    files = []
    wp_files = {_c.square_file(s) for s in b.pieces(_c.PAWN, _c.WHITE)}
    bp_files = {_c.square_file(s) for s in b.pieces(_c.PAWN, _c.BLACK)}
    for f in range(8):
        state = ("open" if f not in wp_files and f not in bp_files else
                 "half-open-white" if f not in wp_files else
                 "half-open-black" if f not in bp_files else None)
        if state is None:
            continue
        heavies = {"White": 0, "Black": 0}
        for r in range(8):
            pc = b.piece_at(_c.square(f, r))
            if pc is not None and pc.piece_type in (_c.ROOK, _c.QUEEN):
                heavies["White" if pc.color == _c.WHITE else "Black"] += 1
        controller = ("White" if heavies["White"] > heavies["Black"] else
                      "Black" if heavies["Black"] > heavies["White"] else
                      None)
        files.append({"file": _FILES[f], "state": state,
                      "controller": controller,
                      "heavies": heavies})

    return {"center": center, "kingside": kingside, "queenside": queenside,
            "holes": holes, "files": files}


def development_lag(fen: str) -> dict:
    """Per-piece development lag vs the SAME side's GM baseline (plies
    8-20 only — development is a defined concept only there). Owner rulings
    (2026-07-23): side-conditioned baselines (Black trails White by a tempo
    by construction), and an ANNOYANCE GATE — every lag is data, but only
    `notable` (>= 15 raw points behind own baseline) may be spoken.
    {'ply': n, 'white': [{piece, square, lag, notable}], 'black': [...]}
    — empty side lists outside plies 8-20."""
    parts = fen.split()
    fullmove = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 1
    ply = (fullmove - 1) * 2 + (0 if len(parts) > 1 and parts[1] == "w"
                                else 1)
    out = {"ply": ply, "white": [], "black": []}
    if not 8 <= ply <= 20:
        return out
    from .board import Board as _B
    d = analyze_positional(_B(fen))
    ft = d["terms"]["activity"]["features"]
    for color in ("white", "black"):
        for e in ft.get(f"pieces_{color}", []):
            base = _DEV_BASELINE[color].get(e["piece"], {}).get(ply)
            if base is None:
                continue
            lag = round(e["score"] - base, 1)
            out[color].append({"piece": e["piece"], "square": e["square"],
                               "lag": lag,
                               "notable": lag <= DEV_LAG_NOTABLE})
    return out

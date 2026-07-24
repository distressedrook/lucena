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

# ---- pawn-storm anticipation (2026-07-24) ----------------------------------
# Static king safety saw an attack only once ENEMY PIECES were in the zone; an
# opposite-wings game (Bobotsov-Tal 1958) is decided by the enemy PAWNS
# marching at the king long before a piece arrives — and the old term read
# White's king as ~safe the whole game. `storm` is a forward-looking term:
# enemy pawns advanced onto the king's flank (files within 2 of the king),
# weighted by how close they are (rank distance) and by file (adjacent files
# heavier), amplified 1.5x when the two kings castled on OPPOSITE wings (a
# mutual race). It rises move by move as the pawns advance — the anticipation
# the static components structurally miss.
STORM_REACH = 5          # ranks of look-ahead toward the king (dist beyond -> 0)
STORM_PER_PAWN = 18      # a pawn one rank off the king's shield, adjacent file
STORM_MAX = 72           # cap on the whole storm term

# ---- heavy-piece line pressure (2026-07-24) --------------------------------
# The other half of an attack the static term missed: enemy ROOKS/QUEEN bearing
# on the king along its own file or rank. A rook on the OPEN file the king
# sits on (Bobotsov-Tal: Rb8 vs the b1 king after ...cxb2 opened the b-file)
# is a major threat the shield/zone terms structurally under-price. Scored by
# how open the line is (defender pawns between the piece and the king).
LINE_OPEN = 22           # 0 defender pawns between the heavy and the king
LINE_HALF = 11           # exactly 1 (a half-open line)
LINE_MAX = 55            # cap on the whole line-pressure term

# DANGER_MAX = SAFETY_TABLE's own ceiling (650) + shield_penalty max (3*14)
# + file_penalty max (3*15) + center_penalty max (35) + storm max (72) +
# line-pressure max (55) = 899.
# `danger/DANGER_MAX` is a BOUNDED score, not a calibrated probability — "1.0"
# means "maxed out this formula", not "certain mate". The calibrated
# P(catastrophe) mapping (2026-07-24 king-safety calibration study,
# research/experiments/studies/king_danger_calibration/) is a SEPARATE
# artifact fit against engine-verified outcomes; it was fit BEFORE the storm
# and line-pressure terms, so it now needs a refit against the new danger
# (flagged, corpus job) — do not conflate the two under one "normalized" label.
DANGER_MAX = 899

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
ACTIVITY_GAP = 0.08             # 0-1 activity gap before the term speaks a
                                # verdict (see _activity_term's standing)


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

def _loose_squares(fen: str) -> dict[str, float]:
    """`geometry.loose_map` in this module's string-square dialect: square
    name -> pressure weight for a piece the enemy can win outright (SEE >
    0). Absent = full weight. See geometry.loose_map for the why."""
    import chess as _c
    from .geometry import loose_map as _lm
    return {_c.square_name(sq): w for sq, w in _lm(_c.Board(fen)).items()}


def _w(loose: dict[str, float] | None, square: str) -> float:
    return 1.0 if loose is None else loose.get(square, 1.0)


def _attack_maps(board, loose: dict[str, float] | None = None):
    """One pass over all 64 squares: per-square attacker WEIGHT and,
    inverted, per-piece attacked-square sets. `board.attackers` is the only
    primitive. Counts are SEE-discounted (2026-07-24): an attacker that is
    itself hanging does not really control the square it eyes."""
    ctrl: dict[str, tuple[float, float]] = {}
    attacks: dict[str, set[str]] = {}
    for f in range(8):
        for r in range(8):
            s = _sq(f, r)
            w = board.attackers(s, "white")
            b = board.attackers(s, "black")
            ctrl[s] = (sum(_w(loose, a) for a in w),
                       sum(_w(loose, a) for a in b))
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
    wart until material() moves engine-side).

    The STANDING is read off the SEE-settled board (owner ruling
    2026-07-24: "always show the quiescenced version"). The raw count
    would say "Black is up a queen for a bishop" about a queen the white
    KING captures for free on the next move. Costs ~0.9ms — nothing
    against the LLM call it feeds. NOTE: `cp` is still the RAW tapered
    PeSTO sum; it is a decomposition term on its own scale (and a fitted
    feature in the residual studies), not a spoken number — settling it
    too is a separate, deliberate change."""
    from .reads import material as _material

    occ = occupancy(board)
    ph = _phase(occ)
    cp = 0.0
    for _, p in sorted(occ.items()):     # canonical float order (see _activity_term)
        v = _taper(MG_VALUE[p.piece], EG_VALUE[p.piece], ph)
        cp += v if p.color == "white" else -v
    try:
        from .board import Board as _LB
        from .metrics import _quiesce as _q          # lazy: metrics <-> positional
        settled = _material(_LB(_q(board.fen)[1]))["standing"]
    except Exception:
        settled = _material(board)["standing"]       # never lose the sentence
    return {"cp": round(cp), "standing": settled}


def _king_zone(ksq: str, color: str) -> list[str]:
    """CPW zone: the king ring plus three squares two ranks toward the enemy."""
    kf, kr = _fr(ksq)
    zone = [_sq(kf + df, kr + dr) for df in (-1, 0, 1) for dr in (-1, 0, 1)
            if (df or dr) and _on(kf + df, kr + dr)]
    fwd = 2 if color == "white" else -2
    zone += [_sq(kf + df, kr + fwd) for df in (-1, 0, 1) if _on(kf + df, kr + fwd)]
    return zone


def _king_safety_term(board, occ, ph: float,
                      loose: dict[str, float] | None = None) -> dict:
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

        # attack units: enemy N/B/R/Q attacks into the zone (CPW weights),
        # SEE-DISCOUNTED (2026-07-24). A besieging piece that is itself
        # hanging is not besieging anything — it comes off the board next
        # move. The motivating case scored 254 off a queen the defending
        # KING captured for free on move one. A zero-weight attacker is
        # also kept OUT of `attackers`, so it cannot help satisfy the
        # two-attacker gate below.
        zone = _king_zone(ksq, color)
        units, attackers = 0.0, {}
        for zs in zone:
            for a in board.attackers(zs, enemy):
                p = occ.get(a)
                if p is not None and p.piece in _ATTACK_UNITS:
                    wt = _w(loose, a)
                    if wt <= 0:
                        continue
                    units += _ATTACK_UNITS[p.piece] * wt
                    attackers[a] = p.piece
        zone_penalty = (SAFETY_TABLE[min(int(round(units)), 99)]
                        if len(attackers) >= 2 else 0)

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
        # a hanging heavy cannot use (or open) the file beside the king
        heavy = any(p.piece in ("R", "Q") and p.color == enemy
                    and _w(loose, s) > 0 for s, p in occ.items())
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
                        and _w(loose, s) > 0 for s, p in occ.items())
            center_penalty = 35 if has_q else 15

        # pawn-storm ANTICIPATION: enemy pawns marching at the king's flank,
        # closer = heavier, amplified when the kings are on opposite wings (a
        # mutual race). This is the forward-looking term the others miss.
        storm = 0.0
        for s, p in occ.items():
            if p.color != enemy or p.piece != "P":
                continue
            pf, pr = _fr(s)
            if abs(pf - kf) > 2:
                continue
            dist = abs(pr - kr)                      # ranks between pawn & king
            if dist == 0 or dist > STORM_REACH:
                continue
            ff = 1.0 if abs(pf - kf) <= 1 else 0.55  # adjacent files weigh more
            storm += (STORM_REACH - dist) / STORM_REACH * STORM_PER_PAWN * ff
        if storm > 0:
            eksq = king_square(board, enemy)
            if eksq is not None:
                ekf = _fr(eksq)[0]
                if (kf <= 2 and ekf >= 5) or (kf >= 5 and ekf <= 2):
                    storm *= 1.5                     # opposite-wing castling
        storm = min(round(storm), STORM_MAX)

        # heavy-piece LINE PRESSURE: enemy R/Q on the king's own file or rank,
        # scored by how open the line between them is (defender pawns in the
        # way). A rook on the open file the king sits on is the piece half of
        # the attack the pawn storm only starts.
        line_pressure = 0
        for s, p in occ.items():
            if p.color != enemy or p.piece not in ("R", "Q") or _w(loose, s) <= 0:
                continue
            pf, pr = _fr(s)
            if pf != kf and pr != kr:                # not aligned with the king
                continue
            if pf == kf:                             # same file: count blockers by rank
                betw = range(min(pr, kr) + 1, max(pr, kr))
                blk = sum(1 for r in betw
                          if (q := occ.get(_sq(kf, r))) is not None
                          and q.color == color and q.piece == "P")
            else:                                    # same rank: blockers by file
                betw = range(min(pf, kf) + 1, max(pf, kf))
                blk = sum(1 for f in betw
                          if (q := occ.get(_sq(f, kr))) is not None
                          and q.color == color and q.piece == "P")
            if blk == 0:
                line_pressure += LINE_OPEN
            elif blk == 1:
                line_pressure += LINE_HALF
        line_pressure = min(line_pressure, LINE_MAX)

        # shield/file/storm/line penalties are middlegame concepts; zone
        # attacks keep a small endgame tail (a cornered king can still be hunted)
        danger[color] = _taper(zone_penalty + shield_penalty + file_penalty
                               + center_penalty + storm + line_pressure,
                               zone_penalty / 4.0, ph)
        features[color] = {
            "king": ksq,
            "danger": round(danger[color]),   # the composite (2026-07-23:
                                              # exposed for the efficacy
                                              # studies + future norm)
            "danger_bounded": round(min(1.0, danger[color] / DANGER_MAX), 3),
            "zone_attackers": sorted(f"{PIECE_NAME.get(pc, pc)} on {s}"
                                     for s, pc in attackers.items()),
            # int by contract (schema test); this is also EXACTLY the
            # value the SAFETY_TABLE lookup used, post-discount
            "attack_units": int(round(units)),
            "shield_pawns": shield,
            "open_files_nearby": open_files,
            "centered_uncastled": center_penalty > 0,
            "storm": int(storm),          # pawn-storm anticipation (2026-07-24)
            "line_pressure": int(line_pressure),   # heavies on the king's file/rank
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


def _mob_norm(board, square: str, p, ph: float) -> float:
    """Per-piece Stockfish-mobility norm, from this module's string-square
    dialect. Recomputes the area per call — fine at one call per piece;
    activity_score() does the batched version."""
    import chess as _c
    from .geometry import mobility_area, mobility_norm, piece_mobility
    try:
        b = _c.Board(board.fen)
        side = _c.WHITE if p.color == "white" else _c.BLACK
        sq = _c.parse_square(square)
        mob = piece_mobility(b, sq, side, mobility_area(b, side))
        return mobility_norm(p.piece, mob, ph)
    except Exception:
        return 0.5


def activity_score(fen: str, ph: float, color: str) -> float:
    """A side's ACTIVITY in [0, 1] — the SAME quantity as the term's `cp`,
    just rescaled (2026-07-24, owner: "cp and normalized, don't they
    represent the same thing?" — they should, and now they do).

    It is the side's summed tapered Stockfish MobilityBonus mapped onto its
    own achievable range: 0 = every piece fully smothered (each at its
    table's minimum), 1 = every piece maximally mobile.

    IT AGREES WITH `cp` AT EQUAL MATERIAL, NOT ALWAYS. (An earlier docstring
    claimed "can never disagree" — that is FALSE and the claim is retracted.)
    The rescale uses EACH SIDE'S OWN range, so once piece counts differ the
    denominators differ and the two can order the sides oppositely. Worked
    example: a lone rampant queen (mob 16) against six mediocre black pieces
    gives cp = -16 (Black, because six pieces sum to more raw bonus) but
    0.681 vs 0.527 (White).
    THAT DIVERGENCE IS CORRECT, and this number is the one to trust for
    "who is more active": a raw sum conflates HOW MUCH material you have
    with HOW ACTIVE it is, and material is the material term's job. `cp`
    remains right for what Stockfish uses it for — the centipawn mobility
    contribution inside an eval sum, where more pieces SHOULD contribute
    more. Two questions, two numbers; the standing reads off this one.

    Weighting therefore comes from Stockfish's table alone, which is the
    only place it belongs: the queen's range (-49..221) is wider than the
    knight's (-79..37) because a queen's mobility IS worth more."""
    import chess as _c
    from .geometry import (MOBILITY_BONUS, mobility_area, mobility_bonus,
                           piece_mobility)
    b = _c.Board(fen)
    side = _c.WHITE if color == "white" else _c.BLACK
    area = mobility_area(b, side)
    total = lo_total = hi_total = 0.0
    for pt, sym in ((_c.KNIGHT, "N"), (_c.BISHOP, "B"),
                    (_c.ROOK, "R"), (_c.QUEEN, "Q")):
        tbl = [mg * ph + eg * (1.0 - ph) for mg, eg in MOBILITY_BONUS[sym]]
        for sq in b.pieces(pt, side):
            total += mobility_bonus(sym, piece_mobility(b, sq, side, area), ph)
            lo_total += min(tbl)
            hi_total += max(tbl)
    if hi_total <= lo_total:
        return 0.0
    return round(max(0.0, min(1.0, (total - lo_total)
                              / (hi_total - lo_total))), 3)


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
                   phase_name: str = "middlegame",
                   loose: dict[str, float] | None = None) -> dict:
    """ACTIVITY = MOBILITY, the Stockfish model (2026-07-24, owner: "do the
    right thing / what engines actually do").

    `cp` is now the summed tapered Stockfish MobilityBonus — the engine's
    own activity term — NOT a PeSTO piece-square sum. PeSTO has no mobility
    term by design (it folds positional knowledge into the PSTs precisely so
    it never computes one), so a PST sum could not see activity at all: a
    rook on an OPEN file and the same rook on a CLOSED file scored
    identically. Measured on one open/locked pair with identical material,
    PST gave the same number for both; mobility separates them by 13 points.

    PeSTO placement is still REPORTED per piece as `placement` — it is
    material placement, which is what PeSTO is good at, and it no longer
    pretends to be activity.

    NOTE: mobility is deliberately NOT SEE-discounted here. `_ACT_QUANTILES`
    and `_DEV_BASELINE` are empirical grids fitted over millions of piece
    observations of the UNDISCOUNTED score; the `loose` flag is exposed per
    piece instead so consumers can see it."""
    import chess as _c
    from .geometry import mobility_area as _marea, mobility_bonus as _mbonus
    from .geometry import piece_mobility as _pmob
    try:
        _b = _c.Board(board.fen)
        _area = {"white": _marea(_b, _c.WHITE), "black": _marea(_b, _c.BLACK)}
    except Exception:
        _b, _area = None, None
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
        # SF mobility: safe squares only (the mobility area excludes squares
        # enemy pawns cover and our own blocked/low pawns sit on), scored
        # through Stockfish's own MobilityBonus table. Falls back to the raw
        # attack count only if the board could not be parsed.
        side = _c.WHITE if p.color == "white" else _c.BLACK
        if _b is not None:
            mob = _pmob(_b, _c.parse_square(s), side, _area[p.color])
        else:
            mob = sum(1 for t in attacks.get(s, ())
                      if occ.get(t) is None or occ[t].color != p.color)
        score = _mbonus(p.piece, mob, ph)
        sums[p.color] += score
        # per-piece breakdown: `score` is now the tapered SF MobilityBonus
        # (cp), `placement` the tapered PeSTO PST (material placement).
        per_piece[p.color].append({"square": s, "piece": p.piece,
                                   "score": round(score, 1), "mobility": mob,
                                   "placement": round(place, 1),
                                   "loose": _w(loose, s) < 1.0,
                                   # 0-1 within this piece's own STOCKFISH
                                   # MobilityBonus table — the activity read
                                   "norm": round(_mob_norm(board, s, p, ph), 2),
                                   # the GM-corpus percentile, kept for the
                                   # studies that were fitted against it
                                   "gm_pct": round(_act_norm(p.piece, score,
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
        # THE 0-1 ACTIVITY NUMBER — mean of the per-piece Stockfish mobility
        # norms. This is the one to display, and the standing below is read
        # off it so text and number can never contradict each other.
        features[f"activity_{color}"] = activity_score(board.fen, ph, color)
        if worst[color] is not None:
            _, s, pc = worst[color]
            features[f"worst_piece_{color}"] = {"square": s, "piece": pc}
    # The least-active piece lives in `features` (worst_piece_*) for a caller that wants it — NOT
    # glued onto the standing, where it fired on every activity mention (even at dead balance, always
    # naming the side-to-move's back rook) and dragged noise into the briefing.
    # The STANDING reads off the 0-1 activity numbers, NOT `cp` (2026-07-24).
    # They can disagree: `cp` is Stockfish's raw bonus sum, where a single
    # rampant queen (bonuses to 221) outweighs everything, while the 0-1 is
    # a per-type-normalized mean. On a locked test position cp said "White's
    # pieces are the more active" while the displayed numbers read W 0.585 /
    # B 0.598 — text contradicting the number it sits beside, which is the
    # exact complaint that started this rework.
    #
    # ACTIVITY_GAP is deliberately wider than a couple of squares: after
    # 1.e4 e5 2.Nf3 Nc6 Black is genuinely 3 safe squares up (its e5 pawn
    # denies d4 to White's knight; White's own Nf3 blocks the d1-h5
    # diagonal) — true, but not a verdict worth speaking when White's real
    # asset is the tempo, which mobility cannot see.
    # aw/ab are the per-side rescaled activity (each 0-1), so the comparison is
    # already MATERIAL-NEUTRAL — a queen's raw square-count does NOT swamp it
    # (that skew lived only in the summed `cp`/diff_cp, which the bar no longer
    # uses). This is exactly what surfaces a sacrifice's POSITIONAL comp: at
    # Harikrishna-Nesterov 10.Kxf2, down a queen, White reads 0.62 vs Black
    # 0.30 — the developed-minors-vs-dead-pieces compensation, made visible.
    aw = features.get("activity_white", 0.0)
    ab = features.get("activity_black", 0.0)
    if aw - ab >= ACTIVITY_GAP:
        leader, standing = "White", "White's pieces are the more active"
    elif ab - aw >= ACTIVITY_GAP:
        leader, standing = "Black", "Black's pieces are the more active"
    else:
        leader, standing = None, "piece activity is roughly balanced"
    # `leader` is the STRUCTURED verdict for the UI badge (owner 2026-07-24:
    # "normalization isn't the way we show this — show it as a badge"). The
    # 0-1 was false precision on screen: 0.681 vs 0.527 says nothing to a
    # reader, and it hid that the raw sum ordered the sides the other way.
    # The client renders this, never the number, and never parses the prose.
    features["leader"] = leader
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


def _center_term(occ, ctrl, ph: float,
                 loose: dict[str, float] | None = None) -> dict:
    cp = 0.0
    held = {"white": [], "black": []}
    detail = {}
    for s in _CORE:
        p = occ.get(s)
        if p is not None and p.piece in _OCCUPY:
            # a hanging occupier neither scores nor HOLDS the square
            wt = _w(loose, s)
            v = _taper(*_OCCUPY[p.piece], ph) * wt
            cp += v if p.color == "white" else -v
            if wt > 0:
                held[p.color].append(s)
        w, b = ctrl[s]                      # already SEE-discounted
        cp += (w - b) * _taper(*_CONTROL, ph)
        detail[s] = {"white_attackers": round(w, 1),
                     "black_attackers": round(b, 1)}
    if cp >= _LEAD_THRESHOLD:
        standing = "White controls the centre"
    elif cp <= -_LEAD_THRESHOLD:
        standing = "Black controls the centre"
    else:
        standing = "the centre is contested"
    for color in ("white", "black"):
        if held[color]:
            standing += f"; {_side_name(color)} holds {', '.join(held[color])}"
    # round micro float noise first: accumulation order differs between a
    # board and its mirror, and 1e-13 at a .5 boundary flipped the cp by 1
    # (2026-07-24 mirror audit)
    return {"cp": round(round(cp, 6)), "standing": standing,
            "features": detail}


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
    # ONE loose map per position, threaded into every term that counts
    # pressure (2026-07-24 SEE discount — see geometry.loose_map).
    try:
        loose = _loose_squares(board.fen)
    except Exception:
        loose = None
    ctrl, attacks = _attack_maps(board, loose)
    from .reads import game_phase as _gp
    try:
        phase_name = _gp(board.fen)["phase"]
    except Exception:
        phase_name = "middlegame"
    terms = {
        "material": _material_term(board),
        "king_safety": _king_safety_term(board, occ, ph, loose),
        "activity": _activity_term(board, occ, attacks, ph, phase_name,
                                   loose),
        "pawns": _pawns_term(board, occ, ph),
        "center": _center_term(occ, ctrl, ph, loose),
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
    from .geometry import loose_map as _lm, loose_weight as _lw
    b = _c.Board(fen)
    loose = _lm(b)          # SEE discount (2026-07-24): a hanging piece
                            # is not attack infrastructure
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
        mass = 2 * sum(_lw(loose, s) for s in now) \
            + sum(_lw(loose, s) for s in reach)
        pts = min(6, int(round(mass)))
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
        heavies = [s for s in (list(b.pieces(_c.ROOK, color))
                               + list(b.pieces(_c.QUEEN, color)))
                   if _lw(loose, s) > 0]
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
    from .geometry import loose_map as _lm, loose_weight as _lw
    loose = _lm(b)          # SEE discount (2026-07-24)

    def _share(sq) -> float:
        return _cs(b, sq, loose)

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
                # a hanging knight is not an outpost — it is a loss
                occupied = (pc is not None and pc.color == beneficiary
                            and pc.piece_type in (_c.KNIGHT, _c.BISHOP)
                            and _lw(loose, sq) > 0)
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
            sq_f = _c.square(f, r)
            pc = b.piece_at(sq_f)
            if pc is not None and pc.piece_type in (_c.ROOK, _c.QUEEN) \
                    and _lw(loose, sq_f) > 0:
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

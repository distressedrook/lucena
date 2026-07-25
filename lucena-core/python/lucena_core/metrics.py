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

# Minimum RAW regional space lead (White - Black, summed over the region's
# files) for the space badge to name a side. A lead of 1 is a single
# rook-pawn nudge (h3/a6) — prophylaxis, not space; >= 2 is a genuinely
# more-advanced front. See space_report's edge block.
_SPACE_EDGE_MIN = 2

# Space is TERRITORY, not a share (owner ruling 2026-07-23: "Black and
# White needn't add up to one; both sides may not have any space; 1, 2
# means nothing"). Each side's regional space gets an INDEPENDENT 0-1
# GM-percentile — the empirical CDF (value -> midrank percentile: fraction
# strictly below + half the ties), fitted over the full GM corpus by
# space_calibration.py. Distribution is color-symmetric, so both sides use
# one per-region map. norm 0.79 = "more space here than 79% of GM
# regional-space observations"; no-space maps to ~0.11 (low but common),
# and BOTH sides may sit there.
_SPACE_CDF = {
    "queenside": {0: 0.106, 1: 0.34, 2: 0.56, 3: 0.751, 4: 0.885, 5: 0.946,
                  6: 0.981, 7: 0.994, 8: 0.998, 9: 1.0},
    "center": {0: 0.114, 1: 0.315, 2: 0.536, 3: 0.79, 4: 0.933, 5: 0.976,
               6: 0.998, 7: 1.0},
    "kingside": {0: 0.134, 1: 0.466, 2: 0.729, 3: 0.855, 4: 0.937, 5: 0.971,
                 6: 0.989, 7: 0.996, 8: 0.999, 9: 1.0},
}


def _space_norm(region: str, space: int) -> float:
    """Raw regional space -> independent 0-1 GM percentile (clamped)."""
    cdf = _SPACE_CDF[region]
    if space in cdf:
        return cdf[space]
    hi = max(cdf)
    return cdf[hi] if space > hi else cdf[min(cdf)]

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
    from .geometry import loose_map as _lm, loose_weight as _lw
    loose = _lm(b)          # SEE discount (2026-07-24)
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
                    # a hole "eyed" only by a hanging piece is not exploited
                    eyed = any(_lw(loose, a) > 0
                               for a in b.attackers(enemy, sq)) or \
                        (pc is not None and pc.color == enemy
                         and _lw(loose, sq) > 0) or \
                        _reachable(b, enemy, sq)
                    if eyed:
                        weak.append(chess.square_name(sq))
            key = "white" if color == chess.WHITE else "black"
            blk[key] = {"score": _space_norm(region, space),
                        "raw": space, "exploitable": weak}
        # edge off the RAW lead (owner 2026-07-24: drop the GM-percentile
        # normalization here too). The edge is a HEAD-TO-HEAD lead within
        # one region — both sides measured on the same files — so the raw
        # difference is already apples-to-apples and the region-width
        # scaling the percentile handled cancels out. The percentile only
        # earned its keep for a side's ABSOLUTE level, which the badge never
        # used; worse, it turned a single rook-pawn nudge (h3/a6, raw lead 1)
        # into a fired badge. A real edge needs a >= 2 raw lead across the
        # region's files; `score` (the percentile) stays in the payload as
        # diagnostics only, no longer a decision input.
        lead = blk["white"]["raw"] - blk["black"]["raw"]
        blk["edge"] = ("White" if lead >= _SPACE_EDGE_MIN
                       else "Black" if lead <= -_SPACE_EDGE_MIN else None)
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
    from .geometry import loose_map as _lm, loose_weight as _lw
    loose = _lm(b)          # SEE discount (2026-07-24)
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
                    playable = (
                        sum(_lw(loose, a) for a in b.attackers(enemy, t))
                        <= sum(_lw(loose, a) for a in b.attackers(color, t)))
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
                # progress 0-1 (owner 2026-07-23: normalize every score) —
                # relative rank / 6 promotion steps; `rank` kept as the raw
                "score": round(rel / 6, 2),
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
    from .geometry import loose_map as _lm
    loose = _lm(b)          # SEE discount (2026-07-24): a complex is not
                            # "controlled" by pieces about to be captured

    def share(sq) -> float:
        return _cs(b, sq, loose)

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
    from .geometry import loose_map as _lm, loose_weight as _lw
    loose = _lm(b)          # SEE discount (2026-07-24): a square guarded
                            # only by a hanging piece is not really guarded,
                            # so it does not trap anything
    out = {"white": [], "black": []}
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        pawn_atk = chess.SquareSet()
        for p in b.pieces(chess.PAWN, enemy):
            if _lw(loose, p) > 0:
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
                    if sum(_lw(loose, a) for a in b.attackers(enemy, t)) \
                            > sum(_lw(loose, a) for a in b.attackers(color, t)):
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


# ---- material stability -----------------------------------------------------
# (2026-07-23, owner: "up a pawn now, but won't be soon" — the static
# material term counts a pawn in tension identically to a pawn in the bank.
# This is the tension/structure-aware read that says WHY a +1.5/+2 edge
# holds or dissolves. SEE prices the tension; structure flags the soft
# surplus. One deterministic ply of settle, never an engine line.)

_MAT_VAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
            chess.ROOK: 500, chess.QUEEN: 900}


def _static_material(b: chess.Board) -> int:
    return sum(v * (len(b.pieces(pt, chess.WHITE))
                    - len(b.pieces(pt, chess.BLACK)))
               for pt, v in _MAT_VAL.items())


def _pawn_flaws(b: chess.Board, color: bool) -> tuple[int, int]:
    """(doubled_extra, isolated) pawn counts for `color`."""
    files: dict[int, int] = {}
    for s in b.pieces(chess.PAWN, color):
        files[chess.square_file(s)] = files.get(chess.square_file(s), 0) + 1
    doubled = sum(c - 1 for c in files.values() if c > 1)
    iso = sum(1 for s in b.pieces(chess.PAWN, color)
              if not any((chess.square_file(s) + d) in files for d in (-1, 1)))
    return doubled, iso


def _best_grab(b: chess.Board):
    """The side-to-move's most profitable SEE capture (>0): (see, san) or
    (0, None)."""
    from .see import see as _see
    fen = b.fen()
    best = (0, None)
    for m in b.legal_moves:
        if b.is_capture(m):
            s = _see(fen, m.uci())
            if s > best[0]:
                best = (s, b.san(m))
    return best


def _best_grab_move(b: chess.Board):
    """(see, Move) for the side-to-move's most profitable SEE capture."""
    from .see import see as _see
    fen = b.fen()
    best = (0, None)
    for m in b.legal_moves:
        if b.is_capture(m):
            s = _see(fen, m.uci())
            if s > best[0]:
                best = (s, m)
    return best


def _quiesce(fen: str, cap: int = 10) -> tuple[int, str]:
    """(White-POV settled material, settled FEN) after the capture-only
    stand-pat negamax. The FEN is the position the value was read off —
    the SETTLED board — so callers can describe what actually survives
    the exchanges instead of what is nominally on the board right now
    (owner ruling 2026-07-24: never show a raw count to a user, always
    the quiescenced one)."""
    from .see import see as _see

    def q(b: chess.Board, depth: int) -> tuple[int, str]:
        stm = 1 if b.turn == chess.WHITE else -1
        cur_fen = b.fen()
        stand = stm * _static_material(b)
        if depth <= 0:
            return stand, cur_fen
        best, best_fen = stand, cur_fen
        for m in b.legal_moves:
            if not b.is_capture(m) or _see(cur_fen, m.uci()) <= 0:
                continue
            b.push(m)
            val, child_fen = q(b, depth - 1)
            b.pop()
            if -val > best:
                best, best_fen = -val, child_fen
        return best, best_fen

    b = chess.Board(fen)
    stm = 1 if b.turn == chess.WHITE else -1
    val, settled = q(b, cap)
    return stm * val, settled


def _quiescent_material(fen: str, cap: int = 10) -> int:
    """Static material (White-POV) after a STAND-PAT capture quiescence:
    negamax over SEE>0 captures only, where either side may also stop and
    bank the current count. Resolves hanging pieces and recapture chains
    that the raw count is blind to.

    Stand-pat is load-bearing (2026-07-24 mirror-audit fix): the earlier
    GREEDY chain walker forced every locally-SEE-profitable grab, so
    tie-broken-by-movegen-order chains diverged by whole pieces between a
    position and its color-mirror (observed -520 vs +470 on one board).
    A max over values has no tie-breaks: same input -> same output, and
    mirror(fen) -> exact negation. NOT tactical truth — captures only, no
    checks/forks — so trust it only where the character classifier says
    the position isn't sharp."""
    return _quiesce(fen, cap)[0]


def material_stability(fen: str) -> dict:
    """Is the material differential STABLE, or soft (about to move)?

    raw_cp        static material, White-POV (100/320/330/500/900).
    adjusted_cp   material after a SEE quiescence — the count that survives
                  the pending captures (hanging pieces / recapture chains
                  resolved). This is the number to READ, not raw_cp.
    soft_cp       adjusted_cp - raw_cp: HOW MUCH the nominal edge is soft,
                  signed White-POV (owner 2026-07-23: "tag soft by how
                  much; the read is material - soft + other terms"). 0 when
                  the softness is purely QUALITATIVE (a doubled pawn worth
                  less but not about to fall) — the `why` still warns.
    net_cp        legacy one-ply settle (kept; superseded by adjusted_cp).
    leader        White/Black/None (|raw| >= 100).
    soft     the leader's edge is not bankable — reasons in `why`:
             (a) TENSION: the trailing side wins material back (best SEE
                 grab covers >= 60% of the lead), or
             (b) STRUCTURAL: the surplus is a doubled/isolated pawn (worth
                 far less than its count), or
             (c) LIQUIDATABLE: a surplus pawn sits on SEE>=0 tension the
                 opponent can dissolve.
    threats  the SEE>0 captures on the board that change the count.
    """
    b = chess.Board(fen)
    raw = _static_material(b)
    # LEADER IS READ OFF THE SETTLED COUNT, never the raw one (owner
    # ruling 2026-07-24: "we shouldn't show SEE as a metric to the user,
    # always show the quiescenced version"). The raw count called Black
    # the leader by 570cp in a position where White's KING simply
    # captured the hanging queen next move and material was dead level.
    adjusted, settled_fen = _quiesce(fen)
    leader = ("White" if adjusted >= 100 else
              "Black" if adjusted <= -100 else None)

    stm_grab = _best_grab(b)
    opp_grab = (0, None)
    threats = []
    if stm_grab[1]:
        threats.append({"san": stm_grab[1], "see": stm_grab[0],
                        "side": "White" if b.turn == chess.WHITE else "Black"})
    if not b.is_check():
        bn = b.copy(stack=False)
        bn.push(chess.Move.null())
        opp_grab = _best_grab(bn)
        if opp_grab[1]:
            threats.append({"san": opp_grab[1], "see": opp_grab[0],
                            "side": "White" if bn.turn == chess.WHITE
                            else "Black"})
    # net = raw after the SIDE TO MOVE's free SEE grab only; the opponent's
    # best grab is a THREAT the mover will answer, not a settled loss (an
    # earlier version baked it in and credited a bxc6 Black simply parries)
    stm_sign = 1 if b.turn == chess.WHITE else -1
    net = raw + stm_sign * stm_grab[0]

    why, soft = [], False
    if leader is not None:
        lead_color = chess.WHITE if leader == "White" else chess.BLACK
        # (a) TENSION — the trailing side claws material back
        trail_grab = opp_grab if b.turn == lead_color else stm_grab
        if trail_grab[0] >= 0.6 * abs(raw):
            soft = True
            why.append(f"the trailing side wins material back with "
                       f"{trail_grab[1]}")
        # (b) STRUCTURAL — surplus is a damaged pawn
        pawn_diff = (len(b.pieces(chess.PAWN, chess.WHITE))
                     - len(b.pieces(chess.PAWN, chess.BLACK)))
        if (leader == "White" and pawn_diff >= 1) or \
           (leader == "Black" and pawn_diff <= -1):
            # DOUBLED only: an extra doubled pawn is the classic "nominal
            # not real" surplus. Isolated is NOT flagged — an extra
            # isolated pawn is often a healthy outside passer (an early
            # version over-fired on winning K+P endings).
            dbl, _iso = _pawn_flaws(b, lead_color)
            if dbl:
                soft = True
                why.append("the extra pawn is doubled")
        # (c) LIQUIDATABLE — a surplus pawn sits on SEE>=0 tension
        from .see import see as _see
        for s in b.pieces(chess.PAWN, lead_color):
            if not b.attackers(not lead_color, s):
                continue
            probe = b if b.turn != lead_color else None
            if probe is None:
                probe = b.copy(stack=False)
                if b.is_check():
                    continue
                probe.push(chess.Move.null())
            caps = [m for m in probe.legal_moves
                    if m.to_square == s and probe.is_capture(m)]
            if any(_see(probe.fen(), m.uci()) >= 0 for m in caps):
                soft = True
                why.append(f"the {chess.square_name(s)} pawn can "
                           "simply be traded off")
                break

    soft_cp = adjusted - raw
    if soft_cp and abs(soft_cp) >= 50:
        soft = True                       # a real material swing is pending
        side_word = "White" if soft_cp > 0 else "Black"
        why.insert(0, f"once the captures resolve, the material swings "
                       f"to {side_word}")

    # THE SPEAKABLE SENTENCE, read off the SETTLED board. `raw_standing`
    # describes the nominal position and is kept for diagnostics only —
    # it is the one that said "Black is up a queen for a bishop" about a
    # queen White captured for free on the next move. Consumers that
    # speak to a user must use `standing`.
    from .board import Board as _LB
    from .reads import material as _material
    standing = _material(_LB(settled_fen))["standing"]
    raw_standing = _material(_LB(fen))["standing"]
    return {"raw_cp": raw, "adjusted_cp": adjusted, "soft_cp": soft_cp,
            "net_cp": net, "leader": leader,
            "standing": standing, "raw_standing": raw_standing,
            "settled_fen": settled_fen,
            "soft": soft, "why": why, "threats": threats}


def settled_view(fen: str, pvs: list | None, cap: int = 8) -> dict | None:
    """Walk the engine's top line forward until the position is QUIET, then
    read the settled position (owner 2026-07-23: "play out ~5 moves till the
    opponent plays, snapshot that"). This is quiescence: the static material
    term is blind to tension, but the SETTLED position after the forced
    sequence tells the truth ("up a doubled pawn now" -> "up a clean pawn").

    Quiet = neither side has a SEE>0 capture and nobody is in check. Stops
    at the first quiet position after >=2 plies, or the cap (8 plies), or
    when the line ends. Returns the settled FEN, the SAN line walked, the
    per-term cp decomposition there, and material_stability on it. None if
    no engine line was supplied."""
    if not pvs or not pvs[0].get("ucis"):
        return None
    b = chess.Board(fen)
    line = []
    quiet = False
    for i, u in enumerate(pvs[0]["ucis"]):
        if i >= cap:
            break
        try:
            m = chess.Move.from_uci(u)
        except ValueError:
            break
        if m not in b.legal_moves:
            break
        line.append(b.san(m))
        b.push(m)
        if b.is_check():
            continue
        stm = _best_grab(b)
        bn = b.copy(stack=False)
        bn.push(chess.Move.null())
        opp = _best_grab(bn)
        if i >= 1 and stm[0] <= 0 and opp[0] <= 0:
            quiet = True
            break
    # `quiet`: stopped on a resolved position (no pending SEE>0 capture) —
    # only quiet endpoints are trustworthy to read terms off. A False means
    # we hit the cap or the line truncated mid-tension (an unresolved
    # exchange), and the snapshot is NOT a fair read.
    from .positional import analyze_positional
    from .board import Board as _LB
    terms = {k: v["cp"] for k, v in
             analyze_positional(_LB(b.fen()))["terms"].items()}
    return {"plies": len(line), "line": line, "fen": b.fen(),
            "quiet": quiet, "terms": terms,
            "material": material_stability(b.fen())}


# ---- per-line theories ------------------------------------------------------
# (2026-07-23, owner: "apply the same discipline (4pv / k-roll) to the line
# ENDINGS and concretely measure them — come up with a theory of why White
# is better; per-line theories.") The eval is a number; this is its
# DECOMPOSITION. Each engine line is walked to quiescence, the settled
# position measured, and the reason White stands better read off the
# terms. A feature EXPLAINS the edge only if it survives across every line
# (suggest proposes, the lines filter — the house method, applied to eval).

_TERM_WORDS = {
    "material": ("a material edge", "down material"),
    "king_safety": ("a safer king / the enemy king exposed", "a weaker king"),
    "activity": ("more active pieces", "more passive pieces"),
    "pawns": ("the sounder pawn structure", "the worse pawn structure"),
    "center": ("a firmer center", "a weaker center"),
}
_TERM_MENTION = 40      # |cp| at a line endpoint before a term is spoken
_TERM_ROBUST = 35       # min-across-lines cp for a term to EXPLAIN the edge


def _line_theory_words(terms: dict, leader_sign: int,
                       material: dict) -> list[str]:
    """The leader-favorable terms at one line endpoint, phrased, strongest
    first. `leader_sign` = +1 if White leads, -1 if Black."""
    out = []
    for t, cp in sorted(terms.items(), key=lambda kv: -leader_sign * kv[1]):
        favor = leader_sign * cp
        if favor < _TERM_MENTION:
            continue
        pos, _neg = _TERM_WORDS.get(t, (t, t))
        if t == "material" and material and material.get("soft"):
            pos = "a (soft) material edge"
        out.append(pos)
    return out


def line_theories(fen: str, pvs: list | None, rolls: list | None = None,
                  cap: int = 8, max_lines: int = 4) -> dict | None:
    """Decompose the engine's verdict across its own lines. For each of the
    top `max_lines` PVs (and any Maia rolls), walk to quiescence, measure
    the settled positional terms, and read off the leader-favorable ones.
    Returns per-line theories PLUS the robust synthesis: the terms that
    favor the leader at EVERY line endpoint (min-across-lines >= threshold)
    are the durable explanation; the rest are line-specific."""
    if not pvs or not pvs[0].get("ucis"):
        return None
    from .positional import analyze_positional
    from .board import Board as _LB
    start = {k: v["cp"] for k, v in
             analyze_positional(_LB(fen))["terms"].items()}
    lead_sign = 1 if (pvs[0].get("cp") or 0) >= 0 else -1
    leader = "White" if lead_sign > 0 else "Black"

    sources = [("engine", pv) for pv in pvs[:max_lines]]
    for r in (rolls or [])[:max_lines]:
        sources.append(("maia", {"cp": pvs[0].get("cp"), "ucis": r}))

    lines = []
    for src, pv in sources:
        sv = settled_view(fen, [pv], cap)
        if sv is None:
            continue
        end = sv["terms"]
        lines.append({
            "source": src, "cp": pv.get("cp"), "line": sv["line"],
            "fen": sv["fen"], "plies": sv["plies"], "quiet": sv["quiet"],
            "terms": end,
            "delta": {k: end[k] - start.get(k, 0) for k in end},
            "material": sv["material"],
            "theory": _line_theory_words(end, lead_sign, sv["material"]),
        })
    if not lines:
        return None

    # robust synthesis over QUIET endpoints only (an unresolved mid-exchange
    # snapshot is not a fair read); worst-case (min favoring the leader).
    quiet_lines = [ln for ln in lines if ln["quiet"]] or lines
    robust = {}
    for t in start:
        favor = [lead_sign * ln["terms"].get(t, 0) for ln in quiet_lines]
        robust[t] = {"min": min(favor), "max": max(favor),
                     "explains": min(favor) >= _TERM_ROBUST}
    explains = [t for t in start if robust[t]["explains"]]
    # phrase the robust explanation
    summary = [_TERM_WORDS.get(t, (t, t))[0] for t in
               sorted(explains, key=lambda t: -robust[t]["min"])]
    return {"leader": leader, "start_terms": start, "lines": lines,
            "robust": robust, "explains": explains, "summary": summary}

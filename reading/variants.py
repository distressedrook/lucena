"""variants — editorial variants of the shipped read, run as extra arms.

This is the payload the harness exists for. `position_read.render`'s editorial
constants are hand-set (CLAUDE.md hypothesis list); each variant changes ONE
decision and is scored by the same student against the same baseline, so a win
is attributable.

The layer rule stands: nothing here writes to `lucena-plans`. Variants are
post-processors over the ALREADY-RENDERED read (text-level) or thin recompositions
of arm outputs. If one wins, the owner rules on it, and only then does the
change move into `position_read.py` itself.

v0 variants, chosen off P9/P10's findings rather than the original list order:

  B2  cap plans at 2 per side          — hypothesis 2 (weaknesses are capped
      at 3, plans are uncapped; "true but long" is the failure mode)
  B3  engine-tier plans only           — hypothesis 3 (drop the human- and
      structure-tier bullets; tests the 2026-07-25 show-everything ruling)
  BM  the read + one line naming the engine's preferred start move
      — new, straight from P10: what little lift arm B shows concentrates
      where a move is named. If BM ≈ arm A and B ≈ baseline, the read's value
      on this task is entirely the hint, and the plan prose is decoration. If
      BM > A, prose + answer beats answer alone — the read helps a reader
      TRUST the move. That is a product-relevant distinction.

Registered into `arms.ARMS` so `score.py --arms B2,B3,BM` just works.
"""
from __future__ import annotations

import re

import chess

import arms
import bank

_PLAN_BULLET = re.compile(r"^- _")     # plan lines are "- _<tag>_ — ..."
_ENGINE_TAG = "- _Engine confirmed_"


def _split_read(text: str) -> list[str]:
    return text.split("\n")


def cap_plans(text: str, per_side: int) -> str:
    """Keep at most `per_side` plan bullets inside each **Side** block.
    Weakness bullets (no tag) are untouched — the cap asymmetry under test is
    exactly plans-unbounded-vs-weaknesses-capped."""
    out: list[str] = []
    kept = 0
    for line in _split_read(text):
        if line.startswith("**"):
            kept = 0
        if _PLAN_BULLET.match(line):
            kept += 1
            if kept > per_side:
                continue
        out.append(line)
    return "\n".join(out)


def engine_tier_only(text: str) -> str:
    """Drop every plan bullet not tagged engine-confirmed. Weaknesses stay.
    Plans render strongest-tier-first inside a side block, so this never
    removes a stronger bullet while keeping a weaker one."""
    return "\n".join(
        line for line in _split_read(text)
        if not _PLAN_BULLET.match(line) or line.startswith(_ENGINE_TAG))


def _best_first_san(fen: str, pvs: list[dict]) -> str | None:
    usable = [p for p in pvs if p.get("ucis")]
    if not usable:
        return None
    sign = 1 if bank.white_to_move(fen) else -1
    best = max(usable, key=lambda p: sign * p["cp"])
    try:
        return chess.Board(fen).san(chess.Move.from_uci(best["ucis"][0]))
    except (ValueError, AssertionError):
        return None


# ---- the arms --------------------------------------------------------------
def arm_b2(pid, fen, pvs, rolls):
    base = arms.arm_b(pid, fen, pvs, rolls)
    return cap_plans(base, 2) if base else None


def arm_b3(pid, fen, pvs, rolls):
    base = arms.arm_b(pid, fen, pvs, rolls)
    return engine_tier_only(base) if base else None


def arm_bm(pid, fen, pvs, rolls):
    """The read plus the engine's preferred start move, named once.

    Deliberately leaks the answer (leak rate 1.0 by construction, like arm A)
    — that is the point of the comparison, not a flaw. Its stripped condition
    is arm B plus a redaction mark, which is why the two-mode design still
    reports something meaningful for it.
    """
    base = arms.arm_b(pid, fen, pvs, rolls)
    move = _best_first_san(fen, pvs)
    if base is None or move is None:
        return base
    return f"{base}\n\nThe engine's preferred idea starts with {move}."


_EC_BULLET = re.compile(r"^- _Engine confirmed_ — (.+?)(?: — [a-z][^—]*)?\.$")


def arm_b4(pid, fen, pvs, rolls):
    """B4 "plan-as-direction" (LOOP.md queue #1, from P12).

    Hypothesis: the read fails not for lack of content but for lack of
    direction (+0.259 available vs +0.010 delivered). Take the read's OWN top
    engine-confirmed plan for the side to move and restate it up front as the
    immediate idea — no move named, nothing added that the sheet does not
    already assert.

    The directive line is derived ONLY from the read's text (the first
    engine-confirmed bullet in the **White** block, timing clause dropped) —
    never from the engine answer, or this would be H1 smuggled in and belong
    in the leaking division. Positions with no engine-confirmed White plan
    return the base read unchanged; the sweep's job is to measure the blend,
    and the log must report the directive-coverage fraction.
    """
    base = arms.arm_b(pid, fen, pvs, rolls)
    if base is None:
        return None
    lines = base.split("\n")
    try:
        start = lines.index("**White**")
    except ValueError:
        return base
    idea = None
    for line in lines[start + 1:]:
        if line.startswith("**"):
            break
        m = _EC_BULLET.match(line)
        if m:
            idea = m.group(1)
            break
    if idea is None:
        return base
    return f"Your best idea right now: {idea}.\n\n{base}"


def arm_b7(pid, fen, pvs, rolls):
    """B7 "immediate-plan-as-direction" (P14's correction of B4).

    B4 failed for a measured reason: the read's TOP engine-confirmed plan is
    decision-orthogonal — its piece matched the distractor more often than the
    answer (42 vs 34, neither 168/272). "Engine confirmed" means the plan
    appears somewhere within the horizon, not that the best move enacts it.

    The sheet itself distinguishes: timing=immediate ("available right now")
    means the plan FIRES NOW in an eval-equal line. B7 promotes only that
    bullet to the directive. Coverage is ~36%; the sweep measures the blend
    and the log reports the split.
    """
    base = arms.arm_b(pid, fen, pvs, rolls)
    if base is None:
        return None
    lines = base.split("\n")
    try:
        start = lines.index("**White**")
    except ValueError:
        return base
    for line in lines[start + 1:]:
        if line.startswith("**"):
            break
        m = _EC_BULLET.match(line)
        if m and "available right now" in line:
            return f"Your best idea right now: {m.group(1)}.\n\n{base}"
    return base


arms.ARMS.update({"B2": arm_b2, "B3": arm_b3, "BM": arm_bm, "B4": arm_b4,
                  "B7": arm_b7})


if __name__ == "__main__":
    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts("2400v2400")
    pid = sorted(set(bench) & set(eng) & set(rolls))[0]
    row = bench[pid]
    for name in ("B2", "B3", "BM"):
        text = arms.ARMS[name](pid, row["fen"], eng[pid], rolls[pid])
        print(f"=== {name} " + "=" * 50)
        print(text or "(declined)")
        print()

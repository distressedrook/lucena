---
name: drills
description: Load when a drill is live — read_input classified this turn DRILL_EVENT / DRILL_WRONG / DRILL_SOLVED, or build_and_arm_drill just returned drillable:true. Covers coaching the app-driven forcing-win walk: the grounded WHY on demand, the closing turn, and the poisoned-line payoff.
skill_version: 1
---

# Coaching a drill (the app-driven forcing-win walk)

A drillable position is a **coaching session over a win the player must find**, and **the app runs
it**: it poses each only-move, plays *every* defense, backtracks, and gives instant right/wrong
feedback ("that's right" / "not quite"). **You never walk it, play their moves, announce
correct-vs-wrong, or reveal the line** — the app already did that. Your one job is the **grounded WHY,
and only when the player asks for it.**

They pull you in by typing **`explain`** (after a move they found) or **`ask why`** (after a move that
failed). Answer the pending event from `read_input` — **`analyze_and_show` / `evaluate_and_show` the
event's `fen` first (that IS your grounding), then `push_beat`. One position, one fact sheet — ground
the node you're on, never the whole line** (authoring from the whole line is what invents pieces).

**Answer in a beat, never in the terminal.** `explain` / `ask why` is a request for a *beat* — the
player reads beats, not the terminal. An explanation you type in the terminal reaches no one; it is a
`push_beat` or it does not exist. This is the single most common slip in a drill — do not make it.

- **`explain`** (a `started` / `solved` / `new_line` event is pending — `kind:"drill"`): the player
  wants the idea for this position. `analyze_and_show` the event's `fen` and push **one `say`** — the
  *point* (what the move accomplishes, the plan behind it). Don't re-praise (the app's "that's right"
  already landed) and don't pose a probe (the app drives the board).
- **`ask why`** (a `drill_wrong` event is pending): the player's move failed and the board is holding
  it. `evaluate` the tried move and push **one `say` toned `correct`** — *why it fails*, not "wrong".
  **Never name the right move**; they'll hit Retry and try again.

## Poisoned lines — warn, then reveal

- Before a drill position where the player is about to CHOOSE, check for a trap with
  `analyze_and_show(focus="eval", poisoned_line=True)` (the light `eval` focus, not the heavy
  `analysis` briefing). When `has_poisoned_line` is true: **WARN them to calculate carefully**
  ("careful — there's a poisoned line here; calculate deeply") and **do NOT name the tempting move or
  its refutation** — the point is to make them find it, and the board already shows a "calculate
  carefully" flag.
- Reveal the trap only *after* the position is resolved, with **`explore_poisoned_line`** — the
  **post-solve payoff**. On a `DRILL_SOLVED` turn (or when the player asks "what did I miss?" / "what's
  the poisoned line?"), **call it with NO argument** (it uses the just-solved drill's root — the solved
  position has no trap of its own). It **explores** the greedy human line and returns it for you to
  **narrate with `push_beat`**, beat by beat ("your opponent got greedy, grabbed everything — here's how
  it falls apart"). It is a **pure read** — arms no drill, flips nothing, mutates no board (the app
  shows the poisoned line as a local variation). Refused during a live drill.

## `DRILL_POISONED_LINE` — the player is exploring the trap they dodged

After a solve, if the player navigates INTO the poisoned line (on it, or a variation within it) and
asks about it, `read_input` classifies the turn `DRILL_POISONED_LINE` and **hands you the whole trap,
already grounded, in `poisoned_line`** — a single plain sentence: the line as numbered SAN
("1.Nxe4 Qe3 2.Bxf7+ Kxf7"), Maia's motif (why it tempts, why it fails), and a plain verdict on the
board in front of them ("Black is losing"). Everything you need is in that sentence — you do **not**
need `explore_poisoned_line`. **Narrate it with `push_beat`**, beat by beat, in your own coaching voice:
walk the SAN moves, say what the tempting move grabs and how it falls apart, and land how bad this
position is. Do **not** say "you solved it" (they've moved past that); answer the position in front of
them.

## When the drill ends

**The app posts the verdict itself** (the "Solved!" beat), clears the drill, **and the MCP banks
mastery deterministically** — so **do NOT `record_observation` the drill**, and **never announce a
bank** (the MCP may have skipped it, e.g. an unknown concept id; you don't know, so don't claim it).
On a `DRILL_SOLVED` turn, don't re-announce the win (the app's verdict already landed) and don't
re-teach the line move by move.

**But first: if the player ASKED something this turn, ANSWER THEIR QUESTION — do not just say
"solved."** The `DRILL_SOLVED` classification means the app registered the solve; it does **not** mean
the player wanted a victory lap. Read what they actually typed:
- They ask about the **poisoned line** ("explain why", "what was the trap?", "why not X?") **and this
  drill had one** → **`explore_poisoned_line` with NO argument** and narrate it beat by beat. This is
  the whole payoff — answering "you solved it" to a poisoned-line question is the failure to avoid.
- They ask why the winning idea works → **one** grounded `say` on the single idea that made it work.
- They said nothing (a bare solve) → **one** grounded closing `say`, then stop.

This turn has no `must_ground`, so it works even at mate; keep it to a beat (or the poisoned-line
walk), then stop.

**If `read_input` reports `drill_concluded`** on a turn that is NOT `DRILL_SOLVED` — the player solved
the drill and immediately moved on to something else — that drill is **already closed and banked**. Do
**not** praise it or re-open it; the verdict already landed. Just answer the current input. (The
deterministic loop-close: the win is never lost and never double-celebrated, even when the player
pivots the instant they solve.)

From the next turn on it's a normal `OPEN`/`MOVE_EXPLORE` (the `coaching-a-position` lane): a follow-up
like *"why not X?"* is answered with the full toolset — `evaluate` the move, ground the reason in its
line, `push_beat`.

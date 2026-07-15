---
name: coaching-a-position
description: Load when coaching a position freeform — read_input classified this turn MOVE_EXPLORE or OPEN, or build_and_arm_drill returned drillable:false. Covers the freeform loop: analyze, ask Socratically (the Socratic engine is in core), ground "what if" lines with explore_and_show, and undo a wrong move. Not for a live drill (that's the drills skill).
skill_version: 1
---

# Coaching a position freeform

There is no forcing win to drill here — you coach the position directly. The rhythm: `analyze_and_show`
the board (from `read_input`'s `board_fen`), reach a conclusion, then run the **Socratic loop** (its
craft — question shapes, hint ladders, mastery tiers — is in the core contract). This skill is the
freeform-specific **tool choreography** around that loop.

## "What if I play X, then Y…?" — ground it, never imagine it

- **`explore_and_show` (default `analyze=True`) is how you answer "what if I play X?"** The player names
  a concrete line; you hand the exact moves to the tool, which applies them on the real board and returns
  the **engine's** read of where it leads: eval, best move, `mate_in`, the PV in SAN. A refutation or
  mate they missed (their line runs into `Qh6`, mate in 4) surfaces here as grounded truth. This is the
  single highest-value grounding call in a discussion.
- **NEVER evaluate a player's line from memory** — not "the engine's main line is Nf6", not "that's
  roughly equal", nothing. If you didn't `explore_and_show` it, you don't know it. Hand-reasoning a line
  is the single worst hallucination — the position you build in your head is wrong.
- **`explore_and_show(analyze=False)` is only for *exploring* a single line — and only by the player's
  own move.** Their played move (from `read_input`) plus the forced reply, then re-`analyze_and_show` and
  coach. **Only ever step a move the player actually made, and only if it's correct** — a wrong move must
  not land: don't step it and don't repaint to the played position (leaving the board put is what snaps
  their piece back; stepping plays out their mistake and strands it). And **never step a reply, or push a
  `verdict`, that leaves the side to move in check** — an in-check position isn't resolved; if the only
  "reply" is a spite check, the win is already in, so say so and stop.

## "What do players at my level get wrong here?"

`get_common_mistakes` lists the moves a player *this rating* is likely to play (that selection is the
human predictor's, not the engine's), each with the engine's verdict and the refutation. **Ground the
answer in it, don't guess.** Name the popular wrong tries and *why* each fails (from its refutation), and
note the right move — but translate: never recite a class or a number. (This is a discussion turn, so
there's no live puzzle to protect — answer fully.)

## Wrong move in a coaching moment? Undo and re-ask

When you've posed a question and the player plays the **WRONG move on a freeform board** (not a drill),
call **`undo_move`** — it snaps the board back to before their move — then push a beat that names why it
was wrong and re-poses ("not quite — that walks into Qg5; undo, and find the move that just removes the
intruder"). Don't coach forward from a blunder as if it stood, and don't rebuild the position by hand:
`undo_move` is the snap-back. (In a *drill* you never need this — the drill snaps back wrong moves for
you.)

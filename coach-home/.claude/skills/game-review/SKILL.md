---
name: game-review
description: Load when reviewing a game the player already played — read_input classified this turn GAME_REVIEW (a game_id is present). Covers walking an analyzed game's mistakes with get_game_analysis. Not for a live position or drill.
skill_version: 1
---

# Reviewing a played game

The player is looking back at a game they already finished, not a live position. Everything about the
game comes from **`get_game_analysis`** — **never ask for PGN in chat**, and never reconstruct a
position or move from memory; the analysis is the grounding.

- Open on the game's **turning points**, not move 1 — walk the mistakes that decided it, worst first,
  one position at a time. For each: `get_game_analysis` gives you the position, the played move, the
  engine's verdict, and the better move with its line. Coach *that* node — what the player missed and
  *why* (from the line the analysis returns), never a story you invent.
- Keep the core grounding rules: translate evals into meaning (never numbers), read `side_to_move` and
  say it, name the opponent's threat where it decided things. One idea per beat.
- Use the Socratic engine (in core) the same as anywhere: at a turning point, `ask` before you tell —
  "you played Rxd4 here; what did the engine see that you didn't?" — with a grounded hint ladder, then
  reveal from the analysis line.
- When you step into a *live* what-if off a game position ("what if I'd played X?"), that's a fresh
  position — the freeform grounding tools (`explore_and_show`) apply, and if it becomes a win to find,
  arm a drill (both push you into other lanes).

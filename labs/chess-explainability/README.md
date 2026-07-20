# Chess Explainability — Research Log (parked for v2)

**Status: PARKED.** Making chess move-commentary reliable is a **frontier v2 problem**. This folder
archives the research from the 2026-07-19 live-testing session so it can be picked up later. The
production decision that came out of it lives in memory: `llm-role-learning-harness.md` — **the LLM is a
learning harness only, it never interprets chess; per-move LLM explanation mostly goes away for v1.**

Nothing here is wired into the running backend. The *shipped* pieces (the deterministic reasoning layer,
the grounding filters) stay in `backend/` — see "What shipped" below — this is the *research* around them.

---

## 0. The one-line finding

The engine and the deterministic reasoning layer are **reliable**. Every unreliability we hit came from
the **fact layer** feeding the LLM ambiguous/abstract/stale facts, or from the LLM being asked to name an
**abstract** thing (a motif, a plan, an assessment). The reliability boundary is:

> **CONCRETE + verified** (a refutation line, a capture, the eval swing) → the LLM can translate to prose
> safely. **ABSTRACT characterization** (name the motif, assess the position, state the plan) → high
> invention surface → cut for v1.

The blunder "why" survives v1 precisely because it's anchored to a concrete, engine-verified refutation
line. The right-move "point" (name the pattern) is where fork/pin/a8 all crept in.

---

## 1. What SHIPPED (reliable, stays in v1) — `backend/python/lucena_backend/`

The deterministic reasoning layer — derive a move's causal point from the board, LLM only verbalizes:

- **`reasoning/line.py` — `describe_plan`** (multi-ply): walk the engine PV → the target the move
  actually wins, upgrading the single-ply hedge to a verified statement. Guards, hard-won:
  absolute-material `final > pre AND final > 0` (net gain over the line, ending ahead — not a swing/peak);
  target square not recaptured; a same-square recapture is phrased as a sequence, not an "undermine";
  lenient cp floor. **Validated: 101/101 on 150 Lichess puzzles** (`experiments/valplan.py`) against an
  INDEPENDENT final-board material verifier (the first verifier reused the reasoner's own walk and was
  self-confirming — a methodology lesson).
- **`reasoning/undermine.py` — `undermines_defender` / `attacks_defender`**: REMOVE (favourable capture
  of the sole defender → "wins the guard"), ATTACK-fork ("can't save both; one falls"). SEE decides
  win-vs-sacrifice. `attacks_defender` outranks `describe_plan` so a fork isn't reported as one horn.
- **Grounding filters** (`coaching/grounding.py`) — the fact-hygiene that came out of the failure taxonomy
  below: stale-fact `live_fen` filter; null-move-threat (`ignores` / `after a pass`) filter; `only defender`
  and `pinned` filters; `_deep_tactics` leads with the decisive (mate) clause; played-move excluded from
  solution-stripping; `_invented_moves` + `_invented_motif` deterministic guards; graceful `_gen_json` 429
  degradation.
- Design doc: `backend/docs/reason-deriver-design.md` (phases done / superseded / deferred, incl. the
  positional term-delta write-up).

---

## 2. What was EXPLORED and PARKED (didn't ship)

- **Positional five-term term-delta reasoner** (`experiments/valpos.py`): diff `analyze_positional`'s five
  terms (material / king-safety / activity / pawns / centre) before/after a move; the biggest positive
  non-material delta names the reason. **Verdict: not shippable raw** — it MISLABELS forcing tactics as
  positional ("improves king safety" on a mate). The engine cp *ceiling* (drop mate/crushing) is the
  discriminator that makes it viable, but it needs a quietness gate too, and Lichess is the wrong corpus
  (~80% tactical even in "positional" tags). PARKED as the positional sibling of the material reasoner.
- **Delta hypothesis** (`experiments/delta.py`): `unopposed_grab − real_PV_grab` = "what the opponent's
  defence saves". n=60: clean ~1/3 (material), noisy ~1/3 (greedy shallow overreach), forcing-blind ~1/3.
  Promising long-tail augmenter, NOT a foundation.
- **Unopposed-plan primitive** (`experiments/unopp.py`): "best move if the opponent passes for N moves" —
  reveals the target of quiet material plans; structurally blind to forcing/sacrificial (null-move illegal
  in check).

---

## 3. The FACT-LAYER FAILURE TAXONOMY (the core research)

Every failure found in live testing, its root cause, and the fix (✅ shipped) or the v2 work needed:

| # | Symptom (live) | Root cause | Status |
|---|---|---|---|
| 1 | "you/your rook" when it's the opponent's | perspective flip — facts not colour-absolute | ✅ absolute colours (older) |
| 2 | stale "Black threatens Rxc3+" after the rook left c3 | pre-move fact surfaced post-move | ✅ `live_fen` stale-filter |
| 3 | "if White ignores Nc5…" as the point | null-move threat = describes PASSING, not the move | ✅ `ignores`/`after a pass` filter |
| 4 | "removes the only defender… so it falls" (over-claim) | static defender fact over-read into a win | ✅ `only defender` filter + curated reasoner owns it |
| 5 | "checkmate on **a8**" from a bare `Ra4#` | model **deduced the board it wasn't given** (a8 = king sq) | ✅ prompt: name the mating MOVE, not a square (0/15 after) |
| 6 | "a **fork** attacking the king and rook" (none exists) | the **prompt itself listed "a fork"** as an example to copy | ✅ stripped all motif examples from prompts + `_invented_motif` guard |
| 7 | "your **rook is pinned**" as the point, move after move | static pin surfaced as a move's point; colourless | ✅ `pinned` filter (blunt — see §4) |
| 8 | pin/defender as the point instead of the mate | the mate clause named the PLAYED move → solution-stripped away | ✅ exclude the played move from stripping; `_deep_tactics` leads with the mate |
| 9 | "Uh oh" on solve | LLM 429 (rate-limit) broke the turn | ✅ `_gen_json` degrades to `{}` |

**The meta-lesson (item 6 especially):** models don't hallucinate chess this fundamentally — **we were
priming them**. Negation examples ("do NOT name a fork") and illustrative examples ("e.g. 'a fork'")
plant the exact word the model then uses. Prompts must not name the thing they forbid.

---

## 4. The FRONTIER v2 PROBLEM: a motif is MOVE-BASED, not a board condition

Item 7 is the crux and the reason this is a year-scale problem. "The rook is pinned" is a **standing
condition**; whether it's the *point* depends on whether **this move creates or exploits it** — which the
static fact cannot tell us. The blunt `pinned` filter kills the noise AND the legit case (a mate that
works *because* the pinned rook can't block). The right fix is a move-based `pin` reasoner (a `reasoning/`
motif, like undermine/fork):

- **Created pin** (cheap, ship first): pins-after − pins-before, attributed to the moved piece →
  "Bb5 pins the knight on c6 to the king." Colour-absolute, deterministic.
- **Exploited pin** (the mate case): counterfactual — does the pinned piece have a pseudo-legal move
  (ignoring the pin) that would defuse the move's threat/mate? If yes, the pin is **load-bearing** → the
  motif. If it couldn't have helped anyway, the pin is irrelevant background. Needs board manipulation the
  current immutable API doesn't make easy (temporarily freeing the pinned piece).

**Generalise:** every motif needs this treatment — one move-based deriver per motif, colour-correct and
relevance-filtered. Only then can commentary be both rich AND reliable. That is the v2 frontier.

---

## 5. The DECISION (see memory `llm-role-learning-harness.md`)

- **LLM = learning harness only** — intent classification, encouragement, flow, delivering AUTHORED study
  text (the pasted Lichess gamebook studies are the reliable RICH-commentary path — human-authored per
  position — and need no LLM chess interpretation). It NEVER names a motif, assesses a position, or states
  a plan.
- **v1 right move** → deterministic reasoning-layer point when it fires, else just "correct".
- **v1 wrong move (KEPT)** → the LLM explains, but strictly by translating the CONCRETE refutation line;
  no motif/assessment/mate-square/intent embellishment.
- **Do not** invest further in prompt-tuning rich move commentary — that's this parked v2 work.

## 6. Pointers
- Shipped code: `backend/python/lucena_backend/reasoning/`, `.../coaching/grounding.py`
- Design doc: `backend/docs/reason-deriver-design.md`
- Regression log: `backend/tests/eval/regression-log.md`
- Memory: `llm-role-learning-harness.md`, `research-tactic-reason-derivation.md`, `grounding-absolute-colours.md`
- Experiments: `./experiments/` (index in `experiments/README.md`)

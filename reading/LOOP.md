# The research loop

The self-driving iteration this layer was built for. Each cycle is one
hypothesis against the frozen eval, logged append-only, so progress compounds
instead of rediscovering itself. The human is in the loop only at the two
places the method requires: rulings, and anything that changes the sibling
layers.

## One iteration, exactly

1. **Read the tail of `LOG.md`** (the last 3 entries) and the scoreboard
   below. Do not re-derive settled facts; do not re-litigate retractions.
2. **Propose exactly ONE change.** A new variant in `variants.py`, a new
   probe, or a fix to a measured harness flaw. One editorial decision per
   variant — a win must be attributable. Name it (`B<n>` / `P<n>`), state the
   hypothesis in one sentence BEFORE running.
3. **Run it**: `score.py --limit 400 --arms <new> --tag <name>` (launch in
   background; the server is LM Studio on :1234 — `lms server start` if
   down). Baseline is always cached; a one-variant sweep is ~10-25 min.
4. **Verify before claiming**: McNemar vs baseline AND vs the best
   non-leaking variant to date; leak rate; if the result is surprising,
   inspect raw replies from `.cache/student/` before writing the verdict —
   twice this project a "finding" was a harness bug visible in raw output.
5. **Append a `P<n>` entry to `LOG.md`**: hypothesis · numbers · verdict ·
   what it changes for the next iteration. Retractions stay; never edit old
   entries.
6. **Commit** (`git -C ~/Development/lucena add reading && commit`), message
   states the verdict in the first line.

## Standing rules (from CLAUDE.md, non-negotiable in the loop)

- Never edit `benchmark_v1.jsonl`. Never write to `lucena-plans`/`lucena-tactics`.
- A variant that leaks the answer move is measured but competes in the
  LEAKING division (vs BM/A), not against the non-leaking read variants.
- Parse failures are abstentions, never wrong answers. Parse rate is reported
  per condition every sweep.
- No silent caps; coverage in every log entry.
- A human ruling is required to move any winning variant into
  `position_read.py`. The loop proposes; it never ships.

## Scoreboard (update each iteration)

| condition | acc | lift | p | division |
|---|---|---|---|---|
| baseline | 0.654 | — | — | — |
| BM (read + named move) | 0.992 | +0.338 | 1.8e-29 | leaking |
| H1 probe (piece-class hint) | 0.922 | +0.259 | 4.0e-21 | probe, not a read |
| A (raw dump) | 0.729 | +0.075 | 0.0018 | leaking |
| B3 (engine-tier only) | 0.697 | +0.043 | 0.40 vs B | non-leaking |
| **B (shipped read) — the number to beat** | **0.679** | **+0.025** | 0.32 | non-leaking |
| B2 (plans capped 2) | 0.679 | +0.025 | 1.0 vs B | non-leaking |
| D (game continuation) | 0.516 | −0.139 | 2e-10 | reference |

**Best non-leaking variant: none beats B yet.** The measured target: the
decision-relevance gap, +0.259 available (H1) vs +0.010 delivered (P10).

Tried and settled: B4 plan-as-direction NULL (P14 — top plan is
decision-orthogonal: points at the distractor's piece more often than the
answer's). B5 urgency-only framing retired as redundant with B4's mechanism.

## Queue (ranked; the loop takes the top item unless the last entry re-ranks)

1. **B7 "immediate-plan-as-direction"** — directive only from the
   timing=immediate engine-confirmed bullet ("available right now"), the one
   plan the sheet asserts FIRES NOW in an eval-equal line. ~36% coverage;
   report the split. P14's corrected form of B4.
2. **B6 side-to-move only** — drop Black's block entirely (reader is always
   White here): halves length, removes the opponent's plans as distractors.
3. **Ordering probe** — engine-confirmed plan FIRST vs last within the side
   block (primacy on a weak reader).
4. Re-rank after each result; retire the queue item its result obsoletes.

## Stop condition

Three consecutive iterations with no variant beating B (non-leaking, McNemar
p<0.05) → stop, write a closing entry stating the loop is exhausted on this
reader, and hand the open items to the human: the calibration page
(`gen_human_page.py`) and the pedagogy ruling on commitment (P11).

**FIRED 2026-07-30 — strikes 3 of 3 (B4, B7, B6). See LOG.md P16 closing
entry.** Final additions to the picture: B7 +0.036 on its directive subset
(p=0.55, better-aimed but still null); B6 significantly WORSE than B (net
−14, p=0.034 — the opponent's block carries real contrastive signal; the
two-sided read earns its length). The loop's handover: (a) the calibration
page `human_calibration.html` (40 positions, generated); (b) the P11
commitment ruling; (c) one evidence-backed feature request to lucena-plans —
plan-attribution of the eval-equal move ("this plan is what the best line
enacts"), since the sheet's plans are measurably decision-orthogonal and no
editing fixes that. Restart with /loop when a gate produces new information.

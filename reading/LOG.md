# reading — run log

Append-only. One entry per experiment or probe: what was asked, what was
measured, over what coverage, and the verdict. Coverage is always stated —
a number without its coverage reads as completeness it doesn't have.

---

## 2026-07-30 · P0 · bank coverage

**Asked:** are the banked artifacts complete enough to run the eval offline?

**Measured** (`bank.py`):

| artifact | rows |
|---|---|
| `benchmark_v1.jsonl` | 4000 |
| `eng_shards` | 4000 |
| `maia_shards_2400v1300` | 4000 |
| `maia_shards_2400v1800` | 4000 |
| `maia_shards` (labeled) | 4000 |
| `lift_shards` (labeled) | 94289 |

**Verdict:** complete. Arms A–D and the lift metric can run with no engine,
no GPU and no gRPC server. `lift_shards` at 94,289 is the older
pre-benchmark corpus scan (finding 12's anchor count), not a benchmark
artifact — don't join it to the 4,000 by id.

---

## 2026-07-30 · P1 · every benchmark position is White to move

**Asked:** incidental check while probing the rollout banks.

**Measured:** side-to-move across all 4,000 rows — `{'w': 4000}`. Anchors are
at even plies (20/30/40/50), so the anchor scheme guarantees it.

**Verdict — two consequences, both real:**

1. **Hypothesis 1 (side order) is NOT testable on `benchmark_v1`.**
   `position_read.render` iterates `("white", "black")`, and the concern was
   that a student playing Black reads the opponent's block first. On this
   benchmark the reader is always White, so the read already leads with the
   reader's side. The hypothesis is still live *for the product* — it just
   needs Black-to-move positions to measure. Mirroring the FENs does not
   work: the banked engine lines and Maia rollouts belong to the original
   positions, and Maia policy is not colour-symmetric in practice. So this
   is a `benchmark_v2` item (odd-ply anchors), not a cheap one.

2. Any per-colour comparison over this benchmark is confounded with
   ply parity. See P2.

---

## 2026-07-30 · P2 · which colour carries the weak policy (RETRACTED, then resolved)

**Asked:** in `maia_shards_2400v1300`, whose moves are the 1300 ones? Getting
this backwards would invert the foil arm without failing any test.

**First attempt — RETRACTED.** `probe_foil_side.py` tallied engine-agreement
by colour, scoring ply 0 directly against the eval-equal set and ply 1 by a
conditional proxy. It reported White 0.680 / Black 0.521, gap 0.159, "strong
side = white". **That result is invalid.** Because every position is White to
move (P1), White was *always* measured at ply 0 and Black *always* at ply 1 —
the gap compares two measurement methods, not two colours. Two tells were
visible in the output and should have been caught before reading the verdict:
`white n = 9600 = 600 × 16` exactly (every rollout scored, i.e. one ply only),
and `black n == white hits` exactly (the ply-1 proxy is conditioned on ply 0
being a hit).

**Second attempt — inconclusive.** Cross-band identity of the ply-0 move
multiset: 605/800 (0.756) identical for White, 508/800 (0.635) for Black.
Not decisive — 0.756 is most plausibly the fraction of positions where
White's choice is uncontested (the 40–60 gating makes obvious moves
deterministic and branches only at real decision points), so the divergence
is RNG, not policy.

**Third attempt — method-consistent.** White ply-0 engine agreement, same
direct measurement, both bands, 800 positions each:

| band | White ply-0 agreement |
|---|---|
| `2400v1300` | 0.6812 (8719/12800) |
| `2400v1800` | 0.6962 (8911/12800) |

1.5pp apart — far too small for a ~500-Elo policy difference, consistent with
RNG divergence at contested nodes. Points to White being the fixed 2400 side.

**Resolved by reading the generator**, which is what should have happened
first: `research/gpu_benchmark/plan_frequency_by_strength.py` documents these
as "compared across **opponent** strength bands (2400v2400 baseline vs
2400v1300 / 2400v1800)". So the 2400 is the side to move (White) and the
named band is the **opponent** (Black). `maia_shards` is the 2400v2400
baseline.

---

## 2026-07-30 · P3 · the foil arm needs new compute after all (CORRECTION)

**Prior claim (mine, stated twice):** the rating-conditioned banks give a
predicted student foil for free, so the foil arm costs zero engine/GPU time.

**Corrected:** wrong. Those banks vary the *opponent's* strength while the
side to move stays 2400. What the foil arm needs is the opposite — weak
policy on the **side to move** — and no bank holds it. Since every benchmark
position is White to move, the reader whose comprehension we measure is the
strong side, and "the move a 1300 would play here" does not exist on disk.

**What is still free** (unchanged, and it is most of the eval):

- Arms A (raw MultiPV from `eng_shards`), B (`position_read.render` over
  `post_verify_json`), C (`lexicalize.py`, verifier-gated), D (`actual_ucis`).
- The baseline-and-lift metric, the `random_ucis` floor, structure
  stratification, the leakage stripper, bits-per-lift.

**What a `1300v2400` roll would buy** (weak policy on the side to move):
a contrastive foil for quiet positions — the thing the tactical layer gets
free from a puzzle and the positional layer has never had (tactics
KNOWN_ISSUES #6 retired *attributed* intent as unverifiable; a *predicted*
foil is falsifiable). `gpu_bench.py` is resume-safe; ~1.6M Maia calls,
1–2h on a GPU. **Not started — needs a ruling on whether it is worth the
GPU time before the eval has shown anything.**

**Recommendation:** build and validate arms A–D first. They answer "does the
shipped read beat a raw PV dump, and by how much, for whom." If the answer is
yes-but-small, the foil roll is the obvious next lever and the eval will say
so with a number. Ordering it the other way spends GPU hours on a hypothesis
the harness can't yet score.

---

## 2026-07-30 · P4 · the baseline raw rollouts were there all along

**Asked:** arm B calls `fact_sheet.post_verify_json(fen, pvs, rolls)`, which
needs *raw* rolls. P0 recorded `maia_shards` as labeled-only, which would have
left the only raw banks as weak-opponent conditions.

**Measured:** `maia_shards/` holds four filename patterns, not one —
`argmax_*.jsonl` (40, labeled), **`bench_*.jsonl` (80, raw rollouts)**,
`ksample_*.jsonl` (12) and `ksample_ext_*.jsonl` (12). The `bench_*` rows have
the same `{id, k:16, samples}` shape as the other bands and cover all 4,000
positions.

So the 2400v2400 **baseline raw rollouts exist**, and they are the correct
rolls leg for arm B: `HUMAN_TAG` means "strong humans play this from here", so
feeding a weak-opponent bank would have biased the human tier in a way no test
would have caught. `bank.ROLLOUT_BANDS` now carries all three, baseline first.

**Verdict:** P0's characterisation of `maia_shards` was wrong (it read only
`argmax_*`). Arm B needs no new compute. `probe_bands.py` now covers three
bands:

| band | White ply-0 engine agreement |
|---|---|
| `2400v1300` | 0.6812 (8719/12800) |
| `2400v2400` | 0.6930 (8870/12800) |
| `2400v1800` | 0.6962 (8911/12800) |

Spread 0.0150 over 800 positions each — White's strength is band-independent,
as it must be if only the opponent varies. Note the baseline sits *between*
the two weak-opponent conditions rather than above both, which is another
reason not to read a strength ordering out of this number: at 1.5pp it is
measuring RNG divergence at contested nodes, not policy.

---

## 2026-07-30 · P5 · arm B runs end-to-end; one leakage rule is not enough

**Asked:** does `post_verify_json(fen, pvs, rolls)` accept the bank's shapes
directly, and does `position_read.render` produce a usable arm?

**Measured:** yes, with no adaptation — `eng_shards` pvs (`[{cp, ucis}]`) and
the 2400v2400 rollouts (`[[uci …] × 16]`) drop straight in. On `n10009_a40`
the render produced the full shipped read: assessment with character
("razor-sharp — one inaccuracy changes the verdict"), per-side weakness lines,
and six tagged plans across all three evidence tiers.

**Found, and it corrects this file's earlier blanket rule:** the read names
moves in prose by design — "_Strong humans play this_ — Knight to g5",
"trade a minor for a bishop (NxB or BxB)". A single strip-everything rule
would gut arm B rather than test it, because telling the player what to do is
the artifact's job.

**Verdict:** score two modes, as-shipped and stripped, and report both. The
GAP between them separates instruction-following from transferable
understanding — a large as-shipped lift with a small stripped lift means the
read is a good hint machine and a weak explanation. Neither mode alone can
see that. CLAUDE.md's measurement section updated.

**Consequence for the stripper:** it must handle prose move references
("Knight to g5"), not just SAN and coordinates. Square names alone cannot be
stripped wholesale — the weakness lines are *about* squares ("Holes at d3, b4,
d4") and removing them would delete the content rather than the answer. So the
stripper targets piece-name + destination-square constructions and explicit
move tokens, and its recall against the eval-equal move gets measured, not
assumed.

---

## 2026-07-30 · P6 · the local student cannot play a move (hard negative)

**Asked:** can `google/gemma-4-e4b` (7.5B, LM Studio, temp 0) serve as the
weak reader — i.e. produce a legal move from a FEN often enough for lift to be
measurable?

**Measured**, 20 benchmark positions, two conditions:

| condition | legal moves | eval-equal | latency |
|---|---|---|---|
| bare FEN | 3/20 (0.15) | 2/20 (0.10) | 4.6s/call |
| FEN + full legal-move list in the prompt | 6/20 (0.30) | 1/20 (0.05) | 4.3s/call |

**Verdict: unusable, and the mitigation does not rescue it.** Handing the
model an explicit enumeration of every legal move raised legality only to 30%
and *lowered* eval-equal accuracy. A reader that cannot reliably copy a move
out of a provided list is not failing at formatting, it is failing at the
task — so this is a capability limit and further prompt engineering would be
chasing noise.

Why it is fatal rather than merely weak: a 15–30% legality ceiling sits UNDER
every arm. Lift would be measured inside the residue, and most of the variance
would come from whether the model could read the board that time, not from
whether the explanation helped. That is precisely the "measuring the harness,
not the thing" failure this layer exists to avoid.

**Also noted:** the 18.4B MoE (`llama-3.2-8x3b-...-abliterated`) is worse —
~52s/call for 3 completion tokens (thrashing: 10.66GB on a 16GB machine) and
it answered `d4` to three different positions, a constant output with no
discrimination at all.

**Correction to an earlier claim of mine:** I argued a small local model was
methodologically *preferable*, not merely cheaper, because the student should
be weak. The weakness argument still holds, but it assumed the model could at
least produce legal moves. At 15–30% it cannot, so the premise was wrong.

**Consequence — the TASK is wrong, not just the model.** "Generate a move"
requires board reading this class of reader does not have. The fix is to ask
for **discrimination** instead: show the position and two candidate moves, ask
which is better. Answer space is one letter, so parse failure nearly vanishes;
chance baseline is a clean 50%, so lift is interpretable; and it still measures
whether an explanation transfers. Distractors come from the bank — the MultiPV
line with the largest cp gap from best is plausible-but-inferior, and the pair
order is flipped on a digest of the position id so there is no A/B bias.
Measured in P7.

---

## 2026-07-30 · P7 · the harness works; arm B undetermined; a parse confound found

**Asked:** can the reader do the DISCRIMINATION task (position + two candidate
moves, answer A or B) above chance, and does arm B move it?

**First, two harness failures of mine — not model findings, not logged as
such.** (a) `max_tokens=8` gave 0/30 parses in both modes: the model's
reasoning is unbounded and consumes any budget given (397 of 400 tokens,
empty content). (b) An earlier run crashed importing `lucena_core` because it
used system `python3` instead of the tactics venv.

**The fix — assistant prefill.** Seeding the assistant turn with `"Answer: "`
bypasses reasoning entirely: 0.6s/call, `reasoning_tokens=0`, direct answer,
versus 22s with `reasoning_effort=low` (which reasons 510 tokens and then
answers anyway). ~35× faster, and it makes statistical power affordable.

**Stated property of the harness, not a detail:** prefill forces an immediate
answer with no deliberation. For a weak-reader proxy that is defensible — a
first impression rather than a search — but it IS a change in what is
measured. It applies identically to the baseline and every arm, so it cannot
manufacture lift.

**Measured**, 60 pairs (median distractor gap 101cp), distractor = the MultiPV
line with the largest cp gap from best, pair order flipped on a digest of the
position id:

| condition | parsed | correct/60 | correct/parsed | latency |
|---|---|---|---|---|
| baseline | 58/60 | 38 (0.63) | **0.655** | 0.6s |
| arm B | 46/60 | 32 (0.53) | **0.696** | 1.4s |

**Verdicts:**

1. **The harness works.** Baseline 0.655 against a 50% chance floor (38/58,
   binomial p≈0.02). The reader can do this task, so there is headroom for an
   explanation to move.
2. **Arm B is undetermined.** Read on the all-cases denominator it looks
   harmful (0.63 → 0.53); conditioned on a parsed reply it looks mildly
   helpful (0.655 → 0.696). Both differences are inside noise at n≈50. This is
   NOT evidence of no effect, it is evidence the sample is too small.
3. **A parse-rate confound exists and must be controlled first.** Adding an
   explanation dropped the parse rate 58/60 → 46/60 — longer prompts make the
   model likelier to ignore the prefill. With parse failures scored as wrong,
   every arm comparison partly measures prompt length. `student.py` already
   separates parse failure from wrong move; the scratch script did not, which
   is exactly how the misleading headline arose.

**Next, in order:** (a) retry-on-parse-failure with a bounded retry count, and
report parse rate per arm as a first-class number, never folded into accuracy;
(b) scale to all 4,000 positions — at ~1s/call that is ~2h for two conditions,
so the noise problem is solved by running it, not by cleverness; (c) only then
compare arms.

---

## 2026-07-30 · P8 · P7's "parse-rate confound" was my parser (RETRACTION)

**Asked:** why did parse rates differ so much by condition (P7: baseline 58/60
vs arm B 46/60; the first `score.py` smoke run: baseline 0.75 vs arm A 0.25)?

**Measured:** inspected the raw replies in the student cache. The
"abstentions" were answers:

| raw reply | meaning |
|---|---|
| `🅰` `🅰️` `🅱` | enclosed-letter emoji, with and without the variation selector |
| `2` | the ordinal — option two |
| `\nA` | the form the parser did accept |

**Verdict — RETRACTED.** P7 concluded "adding an explanation drops the parse
rate, so arm comparisons partly measure prompt length." Wrong. The parser
accepted only `\b[AB]\b`, so every emoji and ordinal answer was silently
discarded, and prompt length shifted *which encoding the model reached for* —
manufacturing an apparent parse-rate difference out of a regex.

Worse than lost power: it was **asymmetric and biased**. Dropping `2` dropped
B-answers specifically, so the surviving sample was skewed toward A, and the
accuracy figures in P7 were computed on that skewed remainder. No conclusion
from P7's accuracy columns survives.

**Fix:** `parse_letter` accepts the emoji forms, the ordinals and bare
lowercase; `student.py` cache reads now **re-parse from stored raw text**
rather than trusting the stored verdict, so the parser is part of the
experiment and a parser change replays over the cache for free instead of
freezing old bugs into every later run.

**After the fix, same 12 pairs, re-scored from cache in 3 seconds:**

| condition | parse | acc | 95% CI | lift |
|---|---|---|---|---|
| baseline | 1.00 | 0.417 | [0.19,0.68] | — |
| A:shipped | 1.00 | 0.583 | [0.32,0.81] | +0.167 |
| A:stripped | 1.00 | 0.250 | [0.09,0.53] | −0.167 |
| B:shipped | 1.00 | 0.417 | [0.19,0.68] | 0.000 |
| B:stripped | 1.00 | 0.417 | [0.19,0.68] | 0.000 |
| D:shipped | 1.00 | 0.333 | [0.14,0.61] | −0.083 |
| D:stripped | 1.00 | 0.250 | [0.09,0.53] | −0.167 |

**Parse rate is 1.00 everywhere. The confound is gone.** n=12 is pure noise —
every CI spans chance — so none of these accuracies means anything yet. Two
structural facts do:

- **Leak rates: A 1.00, B 0.08, D 0.58.** Arm A always names the answer (it is
  the engine line). Arm B almost never does — so for arm B the shipped and
  stripped conditions are usually the same stimulus, and the two-mode design
  costs nothing there while remaining essential for A and D.
- **Arm A shipped 0.583 → stripped 0.250, i.e. below chance.** Strip the answer
  out of an engine dump and it becomes worse than no information at all.
  Directionally exactly what "a PV is a conclusion with the proof deleted"
  predicts, and a good sign the harness measures what it is supposed to.

**Also fixed:** the global paired subset collapsed to 1/12 (intersecting seven
conditions at ~0.6 parse rate). Pairing is now per comparison — each condition
against the baseline on the subset where both answered, with the baseline's
accuracy recomputed on that same subset as the subtrahend.

**Method note for the rest of this log:** two of the last three "findings"
about the model turned out to be defects in my harness (P7's max_tokens, P8's
parser). Both were caught by looking at raw output rather than at summary
statistics. Any future capability claim about the reader gets the raw replies
inspected before it goes in this file.

---

## 2026-07-30 · P9 · FIRST REAL RESULT: the shipped read shows no detectable
## effect on a weak reader's move choice

**Coverage:** 400 pairs from `benchmark_v1` (first 400 by sorted id with a
distractor gap ≥50cp; median gap 115cp), student `google/gemma-4-e4b` temp 0,
band 2400v2400, parse rate **1.00 in every condition**, 26 min wall.
`runs/20260730T043640-sweep400.json`.

| condition | acc | 95% CI | lift | net discordant | p (McNemar) |
|---|---|---|---|---|---|
| baseline | 0.654 | [0.61,0.70] | — | — | — |
| A:shipped | 0.729 | [0.68,0.77] | +0.075 | +30 | **0.0018** |
| A:stripped | 0.447 | [0.40,0.50] | −0.206 | −82 | 2.1e-20 |
| **B:shipped** | **0.679** | **[0.63,0.72]** | **+0.025** | **+10** | **0.32** |
| B:stripped | 0.679 | [0.63,0.72] | +0.025 | +10 | 0.33 |
| D:shipped | 0.516 | [0.47,0.57] | −0.139 | −55 | 2.0e-10 |
| D:stripped | 0.609 | [0.56,0.66] | −0.045 | −18 | 0.020 |

Leak rates: A 1.00, B 0.17, D 0.81.

**Result 1 — the baseline is sound.** 0.654 against a 50% floor, and it
replicates P7's 0.655 on a different slice. The reader can do the task, so
there was real headroom for an explanation to move.

**Result 2 — arm B has no detectable effect (p=0.32).** +2.5pp, 46 positions
helped against 36 hurt. The shipped deterministic read does not change what a
weak reader chooses. And because arm B names the answer only 17% of the time —
with shipped and stripped scoring identically — this is not a leakage story
either way. It is the first reader-side number this stack has ever had, and it
is null.

**Result 3 — the raw dump helps only by naming the answer (p=0.0018).** Arm A
carries the eval-equal move in every text (leak 1.00), which is exactly the
"conclusion with the proof deleted": maximally useful if you trust it, teaching
nothing.

**Result 4 — showing the actual game continuation HURTS (p=2e-10).** Arm D,
strongest negative that is not an artifact. Worth understanding: a real game's
continuation frequently is not the eval-equal move, so arm D often argues for
the distractor.

### Caveat that limits results 3 and 4 — an asymmetric-stripping flaw (mine)

`strip_move` removes only the ANSWER, leaving the distractor's line intact.
For arm A the stripped reader then sees PV lines 2-4 with the distractor
spelled out and the best move redacted, so it is being pointed at the wrong
option. **A:stripped (−0.206) and D:stripped (−0.045) are contaminated by this
and should not be read as findings.** Arm B is unaffected: leak 0.17, and
shipped ≡ stripped accuracy to three decimals.

Fix before the stripped mode is trusted for A/D: strip BOTH candidate moves, or
strip every move token, and re-measure. Cheap (cache serves the unchanged
conditions).

### Caveat that limits result 2 — the task may under-measure arm B

The distractor is another ENGINE line (2nd-4th PV), so it is usually a sensible
move. The read's plans ("rook activation", "break the bishop pair") can apply
to BOTH options, in which case arm B is genuinely uninformative *for this
discrimination* without being uninformative *about the position*. That is a
limitation of the task design, not established evidence about the read.

Two follow-ups that would separate the two explanations:
1. Restrict to positions where the read's named plan corresponds to exactly one
   of the options — if lift appears there, the read works and the task was
   diluting it.
2. Use a distractor the read's plans actively contradict, rather than the
   widest-gap engine line.

### Standing caveat

One weak local LLM is not a human learner. Whether 0.654 baseline and a null
arm-B effect reflect a human student is unvalidated — the cheap check is a
human answering the same pairs cold and then with arm B's text.

**Verdict: the instrument works and its first reading is null for the shipped
read.** That is the useful outcome: it says the next effort belongs in
selection and framing (the variants list) rather than in more detectors, and it
gives every future variant a number to beat.

---

## 2026-07-30 · P10 · the dilution caveat mostly falls: arm B's null is not
## hiding a plan-level signal

**Asked:** P9 left open that the discrimination task might under-measure arm B
— its plans could apply to both candidate moves, diluting real signal. Split
arm B's lift by which candidate its own text NAMES (the P9 leak machinery run
on both candidates; all answers served from cache, zero new inference).

**Measured**, B:shipped vs baseline, per-bucket McNemar:

| B's text names | n | base | armB | lift | p |
|---|---|---|---|---|---|
| neither candidate | 292 | 0.644 | 0.654 | +0.010 | 0.80 |
| the answer | 59 | 0.729 | 0.814 | +0.085 | 0.27 |
| the distractor | 38 | 0.658 | 0.711 | +0.053 | 0.69 |
| both | 11 | 0.455 | 0.455 | 0.000 | 1.0 |

**Verdict:** on the 73% of positions where the read names neither candidate,
lift is +0.010 (p=0.80) — indistinguishable from nothing. The read's
plan-level content ("rook activation", "break the bishop pair") is exactly
what should operate in this bucket if understanding transferred: a reader who
absorbed "rook activation" should prefer the rook-activating candidate without
the move being named. It does not happen. What little overall lift exists
concentrates where the text names a move (+0.085 at n=59, direction consistent
with hint value, underpowered).

So the P9 null survives its main methodological objection: it is not
dilution hiding a plan-level effect. The shipped read's true, verified,
tagged plan statements do not move a weak reader's choices at all.

**Remaining outs, in honesty:** (a) the naming proxy is textual — a plan can
correspond to a candidate without naming it, so the "neither" bucket contains
some positions where the plan implicitly picks a side; if anything that makes
the +0.010 MORE damning, since those are the positions where transfer should
show. (b) The weak-reader caveat stands: gemma may simply lack the chess to
map "rook activation" onto a move. The human calibration is the only way to
close that one.

---

## 2026-07-30 · P11 · symmetric strip + variants v0: recommendation salience
## dominates everything editorial

**Coverage:** same 400 pairs as P9, symmetric stripping (both candidates
redacted), parse rate 1.00 everywhere.
`runs/20260730T125452-sweep400-symstrip.json`,
`runs/20260730T131840-variants-v0.json`.

| condition | acc | lift | McNemar |
|---|---|---|---|
| baseline | 0.654 | — | (replicated 3×) |
| **BM: read + "the engine's preferred idea starts with <move>"** | **0.992** | **+0.338** | vs A: net +105, **p=1.8e-29** |
| A: raw dump (contains the same move) | 0.729 | +0.075 | vs baseline p=0.0018 |
| B3: engine-tier plans only | 0.697 | +0.043 | vs B: net +7, p=0.40 |
| B: shipped read | 0.679 | +0.025 | p=0.32 (P9) |
| B2: plans capped at 2/side | 0.679 | +0.025 | vs B: net 0, p=1.0 |
| A:stripped (SYMMETRIC) | 0.666 | +0.010 | vs baseline p=0.70 |
| D: game continuation | 0.516 | −0.139 | p=2e-10 (P9) |

**Result 1 — P9's stripping artifact confirmed and quantified.** With both
candidates redacted, A:stripped is +0.010 (p=0.70) — the −0.206 was entirely
the one-sided strip pointing at the distractor. Corrected thesis statement:
an engine line with its conclusion deleted transfers ~NOTHING (neutral), it
does not actively harm. D:shipped's −0.139 stands.

**Result 2 — the headline. Recommendation salience is worth +26pp; editorial
curation is worth ~nothing.** BM and arm A carry the SAME answer move. Buried
at the head of "Line 1 (+2.87): …" it yields 0.729; stated once as a
recommendation on top of the read it yields 0.992 (net +105 discordant
positions, p=1.8e-29 — the reader follows an explicit recommendation
essentially always). Meanwhile both curation variants are null: capping plans
changes nothing (net 0), engine-tier-only is +7 net (p=0.40). BM:stripped
falls back to 0.674 ≈ B, so the sentence carries all of it.

**What this does and does not license.** BM is instruction-following, not
understanding — its stripped form collapses. It does NOT say "ship the move."
It says: on this task, WHAT the read says matters far less than whether it
COMMITS. `position_read` deliberately never says "play this"; that single
choice, not the plan vocabulary, separates it from near-perfect task
performance. Whether a Socratic coach should commit is a pedagogy ruling —
the owner's, not this layer's — but it is now a quantified trade-off
(+2.5pp without commitment, +34pp with) instead of a taste call.

**Where the instrument goes next, given a null on curation:** the reader may
be too weak for curation effects to register (a 7.5B model may not map "rook
activation" to a move at ALL, in which case pruning tiers cannot matter).
The human calibration is now load-bearing for any further editorial variant —
without it, more variants ride on a reader that P10 suggests cannot use plan
prose. Run it before variants v1.

---

## 2026-07-30 · P12 · the reader CAN follow directive prose — the curation
## nulls are about the READ, not the reader

**Asked:** P11's gate, tested directly instead of waiting. Hint ladder,
auto-generated from ground truth, never naming the move: H1 "The best move
here is a <piece> move" (only where answer/distractor piece classes differ);
H2 "The best move here lands on the <file>-file" (only where destination
files differ).

**Measured** (`probe_directive.py`, `runs/directive.log`):

| hint | n | base | hint acc | lift | net | p |
|---|---|---|---|---|---|---|
| H1: piece class | 282 | 0.663 | 0.922 | +0.259 | +73 | 4.0e-21 |
| H2: file | 358 | 0.654 | 0.883 | +0.229 | +82 | 3.3e-16 |

**Verdict: decisive capability.** The reader maps even the crudest directive
description onto the correct candidate near-perfectly. So the P11 nulls are
evidence about the READ: "the best move is a rook move" is worth +26pp while
"rook activation: put a rook on the open/semi-open file" — true, verified,
tagged — is worth +1pp (P10, neither-named bucket). The read is
directive-capable prose delivered without direction: it describes the
position, never the decision, and its timing markers even push away from the
present move ("a longer-term idea, not for right now").

**The measured decision-relevance gap of the shipped read: +0.259 available
(H1) vs +0.010 delivered.** Un-gates variants v1 with a precise target: make
true plan content decision-relevant WITHOUT naming a move.

---

## 2026-07-30 · P13 · character stratification: flat everywhere; QUIET —
## the read's home turf — is exactly zero

**Measured** (dynamism buckets, same 400 pairs, all answers from cache):

| bucket | n | base | armB | lift | p |
|---|---|---|---|---|---|
| DEAD | 13 | 0.615 | 0.462 | −0.154 | 0.63 |
| QUIET | 61 | 0.574 | 0.574 | +0.000 | 1.0 |
| DYNAMIC | 141 | 0.631 | 0.660 | +0.028 | 0.56 |
| SHARP | 107 | 0.645 | 0.692 | +0.047 | 0.46 |
| RAZOR | 78 | 0.769 | 0.808 | +0.038 | 0.51 |

No bucket significant; QUIET is +0.000 on the nose — the null hides no
home-turf effect. Baseline rises with sharpness (0.574 → 0.769): sharper
positions have more self-evident answers, squeezing headroom exactly where
explanations should matter least.

---

## 2026-07-30 · P14 · B4 "plan-as-direction" is null — because the read's top
## plan is DECISION-ORTHOGONAL (loop iteration 1; strike 1 of 3)

**Hypothesis (stated before running):** the read fails for lack of direction,
not content (P12); restating its own top engine-confirmed White plan as "Your
best idea right now: …" closes part of the +0.259/+0.010 gap without naming a
move.

**Measured** (400 pairs, directive coverage 272/400 = 68%, leak 0.17
unchanged; `runs/20260730T172543-B4-direction.json`):

| | acc | lift | p |
|---|---|---|---|
| B4 overall | 0.658 | +0.003 | — |
| B4, directive subset (n=272) | 0.680 | +0.022 | 0.54 |
| B4, no-directive subset (n=128) | 0.602 | −0.039 | 0.38 |
| B4 vs B (McNemar) | — | net −9 | 0.16 |

**Verdict: null, and the verification found the mechanism.** Among the 272
directive positions, the directive's plan mentions the ANSWER's piece 34
times, the DISTRACTOR's piece 42 times, neither 168. The read's top
engine-confirmed plan points at the wrong candidate slightly more often than
the right one. "Engine confirmed" means the plan appears somewhere in an
eval-equal line within the horizon — NOT that the best move enacts it. So
decision-framing failed because the content is decision-orthogonal, not
because framing does not work (P12 shows framing works when content points).

**This sharpens the project finding:** the shipped read's gap is not
phrasing; its plan inventory is not indexed to the present decision. The
sheet DOES carry the needed index — timing=immediate ("available right now")
marks plans that fire now in an eval-equal line.

**Queue updated:** B5 (urgency-only framing) retired — B4 already shows
framing over non-pointing content does nothing. New top item B7: directive
only from the timing=immediate engine-confirmed bullet (~36% coverage, but
those plans fire NOW). Strike count toward the stop condition: 1 of 3.

---

## 2026-07-30 · P15 · B7 "immediate-plan-as-direction" also null (loop
## iteration 2; strike 2 of 3)

**Hypothesis:** B4's failure was content selection, not framing — gating the
directive on the sheet's own timing=immediate marker ("available right now",
i.e. the plan fires now in an eval-equal line) should make it point at the
present decision.

**Measured** (400 pairs, directive coverage 140/400 = 35%, leak 0.17;
`runs/20260730T174827-B7-immediate.json`):

| | acc | lift | p |
|---|---|---|---|
| B7 overall | 0.664 | +0.010 | — |
| B7, directive subset (n=140) | 0.686 | +0.036 | 0.55 |

Pointing on the directive subset: answer 28, distractor 17, both 18, neither
77. The immediate gate DOES aim better than B4 (28:17 vs 34:42) — the sheet's
timing field is real information — but 55% of immediate plans still name
neither candidate's piece, and the effect does not register even where the
aim is right.

**Verdict: null, strike 2.** Across B2/B3/B4/B7 the pattern is now
consistent: NO rearrangement, pruning, or reframing of the sheet's existing
plan prose moves this reader. The only interventions that move it are
explicit move-level direction (BM +0.338, H1 +0.259, H2 +0.229). The sheet's
plan vocabulary lives at a level of abstraction ("activate a rook") that this
reader cannot cash into a specific move comparison — and per P12 that is not
because the reader ignores prose, but because the prose stops one step short
of the move.

**One queue item remains (B6, side-to-move only — a length/distraction axis,
already weakened by B2's null). If it fails, the stop condition fires.**

---

## 2026-07-30 · P16 · B6 significantly WORSE than B; strike 3 — the loop
## closes (loop iteration 3)

**Hypothesis:** dropping Black's block (reader is always White) halves length
and removes the opponent's plans as distractors.

**Measured** (400 pairs; `runs/20260730T181842-B6-sideonly.json`):

| | acc | lift | p |
|---|---|---|---|
| B6 overall | 0.644 | −0.010 | — |
| B6 vs B (McNemar) | — | net −14 (12 vs 26) | **0.034** |

**Verdict: strike 3, and the first SIGNIFICANT difference between two
non-leaking variants — in the wrong direction.** The opponent's block is not
noise: deleting it costs ~2-3pp. The reader uses Black's weaknesses and plans
as contrastive context for White's choice. A useful editorial fact in its own
right (the two-sided read earns its length), and the opposite of the
length-hurts intuition behind the variant.

## CLOSING ENTRY — the loop's verdict after 3 strikes

**Editorial search over the existing sheet is exhausted on this reader.**
Six variants (B2 cap, B3 engine-only, B4 direction, B6 side-only, B7
immediate-direction, plus BM as the leaking ceiling) and the full probe
ladder produced one consistent account:

1. The reader follows explicit move-level direction near-perfectly
   (BM 0.992, H1 0.922, H2 0.883 — all p<1e-15).
2. NO rearrangement, pruning, or reframing of the sheet's plan prose moves
   it (B2/B3/B4/B7 all null), because the plan vocabulary stops one step
   short of the move — and the sheet's plans are largely decision-orthogonal
   (P14: top plan points at the distractor's piece more often than the
   answer's; P15: even timing=immediate plans name neither piece 55% of the
   time).
3. The two-sided structure carries real signal (B6 significantly worse).

**What would actually move the metric, in order of evidence:** (a) a
commitment sentence — the owner's pedagogy ruling, P11; (b) plan content
INDEXED to the present decision — which is not an editing problem but a
lucena-plans capability: a "this plan is what the best line enacts" link,
i.e. plan-attribution of the eval-equal move. That is the concrete,
evidence-backed feature request this loop hands back to the plans layer.

**Open human gates:** the calibration page (`human_calibration.html`,
40 positions, ~20 min) — decides whether any of this transfers to a human
reader; and the P11 commitment ruling. The loop stops here; restart with
/loop after either gate produces new information.

---

## 2026-07-30 · P17 · FIRST HUMAN DATA POINT — consistent with the machine
## null; proxy validity reasonable

**Setup:** the owner (self-described weak player — i.e. the actual target
audience) answered all 40 calibration positions: 20 cold, 20 with the shipped
read, same pairs/order/candidates as the machine sweeps, no engine, answer key
not in the page. `runs/human_calibration_answers.json`.

| condition | human | gemma (same positions) | agreement |
|---|---|---|---|
| cold | 14/20 = 0.70 (p vs chance 0.12) | 0.75 | 0.65 |
| with read | 13/20 = 0.65 | 0.75 | 0.70 |

Human lift from the read: **−0.05** (between-position, n=20 per cell).

**Verdicts, with n=20 humility:**
1. The target audience can do the task — 0.70 cold, right beside the proxy's
   0.75 on identical items.
2. The read did not help the human either. −5pp is indistinguishable from
   zero at this n (±20pp), but it is directionally consistent with the
   machine null (P9) and offers no evidence against it.
3. Proxy validity: comparable accuracy and 65–70% item agreement. Good
   enough for the overnight-loop-on-gemma / human-check-at-milestones
   workflow; not good enough to skip human checks entirely.

**Caveats:** one subject; 20 per cell; cold and with-read are different
positions (within-subject, not within-position). A within-position human
design (same position, two sessions, order counterbalanced) would be the
next step up in rigor if a variant ever looks worth a real human study.

**Net effect on the record:** every load-bearing conclusion of the loop
(P9 null, P14/P15 decision-orthogonality, P16 closing verdict) survives its
first contact with a human reader. The open ruling remains P11: commitment.

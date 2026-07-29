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

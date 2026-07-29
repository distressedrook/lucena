# reading — does the student actually understand it?

**What this layer is:** the **reader-side** measurement the rest of the stack
doesn't have. `lucena-tactics` and `lucena-plans` measure whether a claim is
TRUE and COVERED. Nothing measures whether a person who reads the output
understands the position better afterwards. This layer is that number, and
nothing else. It detects no chess, names no plans, and ships in no product.

Created 2026-07-30 on branch `reading/comprehension-eval`. Run log: `LOG.md`.

## The gap this exists to close

Every validated number in the stack is producer-side:

| number | layer | what it measures |
|---|---|---|
| 86% mistake-explanation completeness | tactics | slot coverage |
| 87% mechanism label agreement | tactics | naming vs labels |
| theme coverage (pin 83/45, xRay 91/67, …) | tactics | detector recall |
| `pair_break` 82% confirm vs 4% random floor | plans | claim soundness |
| carlsbad row: none .529 / launched .551 / completed .580 | plans | plan value |

All of them answer "is what we said true?" None answers "did it land?"

The consequence is visible in the repos' own docs, where comprehension calls
get settled by taste because there is no measurement to settle them with:

- `lucena-plans` KNOWN_ISSUES #3 — "a student reading a bare weakness
  statement can't tell latent-but-real from currently-actionable." The
  recorded fix is the owner's phrasing.
- `lucena-plans` KNOWN_ISSUES #9 — no STRENGTHS section; "easy for a
  narrating model to over-weight — your position sounds terrible."
- `suggest.py` — effect-size ranking is "corpus-derived where audited,
  **prior otherwise**."
- `position_read.py` — owns "selection and ordering, rather than dumping
  every fact and hoping the narrator picks well," via hand-set constants.
- The 2026-07-25 ruling (surface every plan under three tags, drop nothing)
  was driven by a real comprehension defect — a correct plan flickering in and
  out across rolls of the same Carlsbad position. Exactly the class of
  question this layer answers with a number.

**Detection and verification are in good shape; they are the SUPPLY of true
facts. The bottleneck has moved to demand — which of the many true facts to
speak, in what order, with what hedge.** That is a search problem, and it is
what this layer scores.

## The thesis

**An explanation is understandable iff it transfers predictive power to a
weaker reader.** Prose quality, similarity to a human annotation, and
LLM-judge scores are all unusable as targets — the first two reward style, the
third rewards persuasion. Transfer is falsifiable.

Corollaries, inherited from the sibling layers and not up for renegotiation
here:

- **The verifier contract is a hard gate, not a term.** An explanation that
  fails `lexicalize.py`'s verification scores **zero**, not less. A
  metric-maximizing loop will otherwise discover that fabricated vocabulary
  reads beautifully. An unsound proof is worse than silence — including when
  it scores well.
- **Candidate-tier vocabulary is never spoken.** The graduation gate stands.
  This layer may not promote a detector by showing it helps a reader.
- **Human supplies definitions, not labels.** The loop produces adjudication
  packets; a human rules. Same firewall that moved mechanism agreement
  38% → 87%.

## The measurement

Per position, on the frozen benchmark:

1. **Baseline** — student sees the position alone, plays a move. This is the
   subtrahend; every arm is scored as lift over it, never in absolute terms.
2. **Arm** — student sees the position plus one arm's explanation.
3. **Score** — did the student play an eval-equal move? The eval-equal set is
   the first moves of the `eng_shards` MultiPV lines within a cp margin of
   best, **from the mover's point of view** (`bank.eval_equal_first_moves`;
   banked cp is normalized to White, so it is flipped before comparison).
   Stratified by structure and by character (`dynamism.py`'s
   DEAD/QUIET/DYNAMIC/SHARP/RAZOR).

Arms:

| arm | source | role |
|---|---|---|
| A | raw MultiPV=4 dump from `eng_shards` | the floor — the status quo everyone complains about |
| B | `position_read.render(post_verify_json(fen, pvs, rolls))` | the shipped deterministic read |
| C | `lexicalize.py` prose over the tactics factsheet | the LLM-lexicalized arm, verifier-gated |
| D | `actual_ucis` | what was really played — a human-play reference, not a ceiling |
| — | `random_ucis` | the seeded control, already in the benchmark |

Secondary metrics, both necessary:

- **Transfer** — read the explanation for P, then solve a sibling position
  with no explanation. Separates "taught an idea" from "leaked a move."
  Sibling retrieval by `structures` + feature delta.
- **Bits per point of lift** — lift ÷ tokens. The complaint about engine
  output is that it is long and true. Length must cost something.

**Move leakage is stripped from every arm, including D.** An explanation may
not name its own move in SAN, coordinates, or description. Unstripped arms
inflate trivially and are not comparable.

## The banked substrate (verified complete 2026-07-30 — `LOG.md` P0)

Everything runs on artifacts already under
`lucena-plans/research/experiments/`. **No engine, no GPU, no gRPC server** —
which is what makes each iteration deterministic and replayable, the same
property that lets `reduce_agreement.py` re-score a new grammar without
re-rolling.

| artifact | rows | shape | use |
|---|---|---|---|
| `benchmark_v1.jsonl` | 4000 | `id, fen, anchor, result, structures, kstudy, plies_total, actual_ucis, random_ucis` | the frozen eval set |
| `eng_shards/engine_*.jsonl` | 4000 | `{id, pvs:[{cp, ucis[~25]} × 4]}`, cp normalized to White | arm A; the eval-equal set |
| `maia_shards/bench_*.jsonl` | 4000 | `{id, k:16, samples:[[uci …25] × 16]}` | **2400v2400 baseline raw rollouts** — the correct rolls leg for `post_verify_json` |
| `maia_shards/argmax_*.jsonl` | 4000 | `{n, anchor, structures, actual_slow, random_slow, maia_fast, maia_slow}` | labeled plan sets, not raw moves |
| `maia_shards_2400v1800/bench_*.jsonl` | 4000 | as the baseline | weak-**opponent** condition |
| `maia_shards_2400v1300/bench_*.jsonl` | 4000 | as the baseline | weak-opponent condition |
| `lift_shards/shard_*.jsonl` | 94289 | `{n, anchor, structures, af, as, rf, rs}` | the older pre-benchmark corpus scan — **do not join to the 4,000 by id** |

Two keying schemes coexist — `id` (`n1883_a30`) in the benchmark and the raw
shards, `n` + `anchor` in the labeled ones. `bank.py` normalizes to `id`.
`maia_shards/` holds both kinds, distinguished only by filename pattern
(`bench_*` raw, `argmax_*` labeled), which is easy to read past — arm B's
rolls leg must be the **baseline** rollouts, since `HUMAN_TAG` means "strong
humans play this from here" and a weak-opponent bank would bias it.

**Every benchmark position is White to move** (`LOG.md` P1). Anchors sit at
even plies, so this is guaranteed by the anchor scheme, not incidental. It has
consequences for both the foil and the hypothesis list — see below.

## The foil: not free, and not in this bank

The tactical layer gets its foil for free — a puzzle supplies the user's
failed move, and `mechanism.py` explains the (line, foil) difference. Quiet
positions have no given foil, and tactics KNOWN_ISSUES #6 correctly retired
*attributed* intent as unverifiable.

A **predicted** foil is a different object and would be verifiable: the head
of a policy-ranked Maia rollout is a falsifiable claim about what a player at
that strength plays here.

**The rating-conditioned banks do not supply it** (`LOG.md` P3 — this
corrects an earlier claim in this file's first draft). Per
`gpu_benchmark/plan_frequency_by_strength.py`, they vary the **opponent's**
strength while the side to move stays 2400. With every position White to move,
the weak policy is always Black's, while the reader whose comprehension we
measure is White — the strong side. "What a 1300 would play here" is not on
disk.

Getting that backwards would have inverted the arm without failing a test,
which is why `probe_bands.py` exists as a standing regression on the
assumption rather than a comment asserting it.

Buying it is a `1300v2400` roll — weak policy on the side to move.
`gpu_bench.py` is resume-safe; ~1.6M Maia calls, 1–2h on a GPU. **Deferred
deliberately:** arms A–D already answer "does the shipped read beat a raw PV
dump, and for whom," and if that lift is real but small the foil roll is the
obvious next lever with a number behind it. Spending GPU hours before the
harness can score anything is the wrong order.

## Hypothesis list (from reading `position_read.render` — all measurable)

Every editorial decision in the shipped read, as a testable claim. These are
knobs that exist and are currently set by judgement, not defects:

1. ~~**Side order is hardcoded white-then-black**~~ — **not testable on
   `benchmark_v1`** (`LOG.md` P1). Every position is White to move, so the
   read already leads with the reader's side. Still live for the product;
   needs odd-ply anchors, i.e. a `benchmark_v2`. Mirroring the FENs does not
   work — the banked lines and rollouts belong to the original positions and
   Maia policy is not colour-symmetric in practice.
2. **Weaknesses cap at 3 (`MAX_WEAKNESSES`); plans have no cap** —
   `_side_plans` returns every detected plan across all three tiers. The
   asymmetry looks incidental. Try capping plans.
3. **Tier order strongest-first, nothing dropped** (2026-07-25). Try
   engine-tier-only; try dropping the structure tier.
4. **`effect` and `maia_frac` suppressed as "internal jargon."** The tag
   carries the whole confidence load. Try a calibrated number.
5. **`structs[:2]`** — structure cap.
6. **Material spoken only when not even.** Try always / never.
7. **Timing rides inside the sentence, never as a bare label.** Try labels.
8. **`render` returns None when there is no plan and no weakness** — the
   caller falls back. Measure what the fallback costs a reader.
9. **No STRENGTHS section** (KNOWN_ISSUES #9). Add one, measure.
10. **Weakness lines carry no exploited-vs-latent verdict**
    (KNOWN_ISSUES #3). The owner's proposed wording, measured both ways.

Run order: **2, 9, 10, 3** — largest expected effect among the testable ones.

## Layout

```
reading/
├── CLAUDE.md        this notebook
├── LOG.md           append-only run log
├── bank.py          read-only access to the banked artifacts (built)
├── probe_bands.py   regression: White is the 2400 side in every band (built)
├── arms.py          the four arms + the leakage stripper        (next)
├── student.py       the weak reader — no engine, temp 0, fixed prompt
└── score.py         lift, transfer, bits-per-lift; verifier failure ⇒ 0
```

## Rules

- **Never edit `benchmark_v1.jsonl`.** Frozen, sha-pinned. A different
  position set is `benchmark_v2`, exported on the analysis machine.
- **Held-out discipline.** A dev slice for the loop; a test slice touched only
  at milestones. Stratify by structure and character, not at random.
- **No silent caps.** If a run bounds coverage (top-N, sampling, skipped
  positions), `LOG.md` says what was dropped. Truncation reads as coverage
  otherwise.
- **Retract in the log, don't overwrite.** `LOG.md` P2 keeps a wrong result
  and why it was wrong; a log that only records successes can't be audited.
- **This layer never writes to the sibling layers.** It proposes; a human
  rules; the editorial change then moves into `position_read.py`.
- **Read-side only.** No detector lives here. If an experiment needs a new
  fact, that fact belongs in `plans`/`tactics` behind their graduation gates.

## Environment

- Runs under the tactics venv like the other research harnesses:
  `../lucena-tactics/.venv/bin/python`.
- Needs **no** engine and **no** gRPC server — banked artifacts only.
- Imports `lucena-plans/src` (`fact_sheet`, `position_read`, `dynamism`) and
  `lucena-tactics/src` (`factsheet`, `lexicalize`) as libraries.

## Relation to the sibling layers

- `lucena-tactics` = why a forcing line wins or loses. `lucena-plans` = what
  to do in a quiet position. Both produce claims. **This layer produces no
  claims — only measurements of how well theirs land.**
- Nothing currently composes tactics and plans into one read, and a real
  position needs both (tactics is ~0% on technique by design — tactics
  KNOWN_ISSUES #2). `dynamism.py`'s character buckets are the obvious router.
  Whether routing beats either layer alone is a question only this layer can
  answer.

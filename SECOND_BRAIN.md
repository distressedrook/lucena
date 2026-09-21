# Lucena — the chess second brain

**Status:** direction doc, 2026-07-29. Supersedes the coaching product. Not yet built.

Lucena remembers your chess. It does not have opinions about it.

It ingests every game you play, labels every position with the deterministic
vocabulary already built (`structures`, `weaknesses`, `detectors`, `mechanism`,
`plan_diff`, `has_tactics`), and makes that history queryable, trackable, and
drillable. What it never does is tell you what to think about a position.

## Why this shape

The two things that work in this project — puzzles and static analysis of a
position — are the two things that are **deterministic and verified**. The
coaching layer was lukewarm because it needed judgment, pedagogy and voice on
top of the labels, in the one place the model can't be trusted.

Every module in `lucena-plans/src` and `lucena-tactics/src` is a **labeling
function over positions**. That is an indexer, not a coach. A coach needs
labels + judgment + pedagogy + voice. A second brain needs labels + retrieval.
The labels exist and are corpus-validated. Postgres exists. One missing piece,
and it's deterministic.

Per-game claim quality was never going to carry a product — six high-precision
claims about one game is thin. Six claims across four hundred games,
aggregated, is not: *"your bad bishop in the Carlsbad, 34 occurrences, and the
rate is flat over six months."* The 2026-07-27 precision ruling is the
precondition for this, not a casualty of it. Aggregation over high-precision
facts yields signal; aggregation over filler yields "castle kingside."

## The one abstraction: facts have no author, judgments do

Everything in the brain is one of two layers.

| | **Fact layer** | **Judgment layer** |
|---|---|---|
| Produced by | detectors, engine, census | a human |
| Opinionated | never | always |
| Attributed | no | **yes — `author: coach \| self`** |
| Examples | "bad bishop on c1", structure = Carlsbad, engine verdict, mechanism = deflection | "this is your main problem", "drill this weekly", "ignore this one" |

The system generates only facts. Judgments always come from a person. That is
the same **calculate vs. interpret** invariant the project has always had —
but now the interpreting party is a *human*, not an LLM, which is why the
boundary is finally enforceable rather than policed.

Everything downstream reads the judgment layer without caring who authored it.
That is what makes two views one product.

## The two views

**Coached.** The student's coach is the author. The coach sees a roster, opens
a student, reads the fact layer (recurring patterns, this week's games, what
recurred since the last lesson), and writes judgments: what to work on, what
to drill, what to ignore. Between sessions Lucena executes and measures. The
coach's unpaid prep time — reviewing the week, remembering what was assigned,
noticing whether it's actually improving — is the thing being automated.

**Solo.** The student is their own author. Identical brain, identical facts;
they write the judgments themselves.

**Solo is not a lesser tier — it's the funnel.** A solo user who later hires a
coach migrates nothing: the coach becomes a second author on a brain that
already holds months of labeled history. That is the highest-value conversion
in the product and it costs zero engineering at the transition.

### Solo must never show a blank page

Second brains die of empty input. Ours doesn't have to, because the fact layer
is already populated before the user writes anything. Solo onboarding is
**curation, not authorship**:

> 34 positions where you had a bad bishop. Work on this? [keep / not now / never]

Writing is hard and rare; curating is easy and common. The detectors propose,
the human dispositions — `suggest proposes, verify filters`, applied to the
human layer.

**Second-order payoff:** the 2026-07-27 ruling records that "the owner reading
positions is currently the only sentence-level test, and that does not scale."
Solo curation *is* that test, scaled — every keep/discard is a human verdict
on whether one detector's claim about one position deserved to be surfaced.
Instrument it from day one; it is the missing validation layer, arriving as a
side effect of a feature we wanted anyway.

## The core loop

This is the product. Everything else is a feature.

```
 games auto-ingest (Lichess / Chess.com API)
        ↓
 every position labeled          ← gamepass.py, the existing detectors
        ↓
 patterns aggregated across history   ← the new part
        ↓
 a human dispositions them       ← coach writes, or solo student curates
        ↓
 drills generated from YOUR OWN positions  ← lucena-tactics drill trees
        ↓
 recurrence measured over time
        ↓
 (back to the top, with a trend line)
```

Puzzles and static analysis — the two things that work — are its two halves.
Drills are now **core**, reversing the earlier "park, don't delete" ruling.

## What dies, what survives

**Dies** (`backend/python/lucena_backend/coaching/`): `coach.py`,
`freeform.py`, `prompts.py`, `mode_prompts.py`, `lesson.py`,
`lesson_store.py`, `strategies.py`, `book_voice.py`, `library.py`, the
`ConversationLoop`, and the Lesson-vs-freeform mode machine. This is where the
opinions lived.

**Survives untouched:** `engine/`, `lucena-core/`, all of `lucena-tactics/`,
all of `lucena-plans/src/`, `grounding_tools/`.

**Gets promoted:** `pipelines/gamepass.py`, built and never wired. In a coach,
walking every position of every game is optional infrastructure. Here it is
the ingest path — the product's front door.

**The LLM's remaining surface** is tiny and safe, exactly as specified on
2026-07-20: natural-language → structured query, phrasing deterministic
numbers, extracting a note into the judgment layer. It never sees a FEN. Every
grounding filter for invented motifs simply disappears — there is no position
for it to be wrong about.

## Data model sketch

- `player` — links a Lichess/Chess.com account; owns a brain.
- `coach_link` — coach ↔ player, so a coach's roster is a query and a player
  can gain or lose a coach without touching their data.
- `game`, `position` — the ingested history. Positions are **content-keyed**
  (existing convention: precomputed and position-keyed, never per-session), so
  analysis amortizes across every user who ever reaches that position.
- `observation` — a fact: (position, detector, label, evidence tier). Machine
  only. Never edited by a human.
- `judgment` — (player, subject, verdict, **author**, authored_at). The entire
  opinion surface of the product, and the only table a human writes to.
- `drill_assignment` / `drill_result` — the measured loop.

## Unit economics

Analysis is per-position and shared, not per-user. ~80 positions/game, ~1s at
100k nodes: a 500-game backfill is ~11 CPU-hours — cents, once, amortized.
Ongoing ingest of ~20 games/month is negligible. $5/month carries Stockfish
comfortably. **Maia's GPU rollouts are the line item to watch.**

Acquisition is the binding constraint, not compute: $10k/month at $5 needs
~2,000 subscribers ≈ 100 coaches × 20 students. That is why coaches are the
distribution channel and not merely the positioning.

## Open decisions

1. **Client platform.** `mac-client` is SwiftUI/macOS. A coach roster wants
   web — coaches check a student from a phone before a lesson, and most chess
   players are on Windows. The Mac shell is likely wrong for this and it is
   cheap to decide now, expensive after the roster is built twice.
2. **Does solo cost $5 too, or is it free/cheaper as the funnel?** Free solo
   has real (if small and shared) backfill cost; $5 solo is a harder sell than
   $5 to someone already paying a coach $300/month.
3. **Does the coach see the student's solo judgments?** Privacy question with a
   product answer; affects whether `judgment` needs visibility scoping.
4. **What is the minimum ingest depth** that makes the aggregate view feel
   alive on day one — 50 games? 500? Drives onboarding latency.

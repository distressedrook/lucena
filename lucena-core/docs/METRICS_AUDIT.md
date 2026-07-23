# Positional-metrics consolidation audit (2026-07-23)

Owner request: "Positionally, we have built a bunch of numbers. Some
already exist, some don't. Let's consolidate. Conduct an audit and surface
items that we already compute."

Verdict up front: **six concepts are computed in two or more places.** The
single-source-of-truth layer should be **lucena-core** (every private
layer imports it; plans may keep corpus-specific variants only where the
definition genuinely differs — and then the difference must be named).

## Duplicated computations

| # | concept | implementations | recommendation |
|---|---------|-----------------|----------------|
| 1 | **hole detection** | `positional.region_control` (inline, ranks-scoped) · `metrics.space_report` wake (inline, behind-front) · `plans/weaknesses.is_hole` + `occupied_outposts` (the corpus-audited original) | ONE `is_hole(b, sq, side)` in core (port the weaknesses.py definition — it is the audited one); region_control/space_report call it; plans re-exports from core |
| 2 | **space** | `metrics.space_report` (per-region, pawn-front territory) · `plans/plan_diff.snapshot` `{t}.space` = `sum(side_rank(p)-1)` (the CALIBRATED one — the ±6 AVOID-TRADES/SIMPLIFY threshold is fitted to THIS formula, 25,562 games) | keep BOTH but name them: snapshot's is `space_rank_sum` (calibrated, whole-board), metrics' is `space_territory` (regional). The ±6 gate must never be applied to the regional number |
| 3 | **square-control share** | `positional.region_control._share` · `metrics.color_complex.share` (verbatim copy) | one `control_share(b, sq)` in core; both call it |
| 4 | **king zone** | `positional._king_zone` (CPW, string squares) · `positional.attack_viability` (inline reimplementation, int squares) | one zone helper (int-square version); the term adapts |
| 5 | **central rams / tension / locked center** | `plans/closed_v0.skeleton` + `center_locked` · `positional.attack_viability` stable-center (inline copy — core cannot import plans) · `plans/tension.central_tension` | move `skeleton`/`center_locked` INTO core (they are pure geometry); plans re-exports (the drill/facts shim precedent, direction inverted) |
| 6 | **passer detection** | `positional._pawn_features` (eval term) · `metrics.passer_report` (inline) · `plans/plan_diff._passers` | one `passers(b, side)` in core reads; all three call it |

Near-duplicates that are genuinely DIFFERENT (keep, but document):
- material-value tables: `_pesto.MG/EG_VALUE` (tapered eval), `reads._MATERIAL_VALUE` (1/3/3/5/9 counting), `reads._PHASE_NPM` = `plans service._NPM` (endgame bar — these two ARE the same table and service should import core's), `plan_diff` piece values (diff labeling). The 1/3/3/5/9 trio should collapse to one core constant; PeSTO stays separate by design.
- king danger (`positional._king_safety_term`) vs `plans/weaknesses.exposed_king` (boolean weakness for the census) — different contracts (score vs corpus-audited flag); keep both, but exposed_king could gate on the core danger score after a calibration pass.
- center: `positional._center_term` (cp eval term) vs `region_control.center` (share) — same squares, different units/consumers; keep both, cross-reference in docstrings.

## Newly built vs already existed (the "did we already have this?" table)

| new metric | pre-existing overlap |
|---|---|
| region_control.center | `_center_term` (cp version existed) |
| region_control.holes/outposts | `weaknesses.occupied_outposts`/`is_hole` existed (audited, lift 2.85) |
| region_control.files | king-safety open-files (scoped) + plans rook_activation trigger existed |
| space_report | snapshot `{t}.space` existed AND is calibrated |
| color_complex | `weaknesses.weak_color_complex` existed (audited) — the share is new, the flag overlaps |
| attack_viability | new (no prior art) |
| passer_report | `_pawn_features.passed` + `plan_diff._passers` existed; escort/blockade/path flags are new |
| pawn_breaks | plans lever machinery (backward_push SEE gate) existed for ONE case; general inventory is new |
| trapped_pieces | new (worst_piece was the nearest thing) |
| development_lag | new (baselines new) |
| game_phase | `plans service.is_endgame` existed (same NPM bar — service should delegate) |

## Benchmark tiers (metrics_benchmark.py, full corpus)

validated: passer_report (+0.092) · color_complex flag (−8/−9pp) ·
trapped (+0.072) · space diff (+0.053) · development_lag notable flag
(+8.8pp quartile; linear lag is noise). data-only: pawn_breaks (+0.029).
retired: the SPENT interpretation. **exploitability wake: retired as an
edge-eater claim** — both instruments (attacked-now AND viability-reach)
benchmarked flat; the square list stays as descriptive data only. A real
test of the owner's thesis needs the engine leg (counterfactual), not
observational GM data (space-takers manage their wake — selection).

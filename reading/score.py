"""score — the measurement. Baseline vs each arm, paired.

Runs the discrimination task (`LOG.md` P6/P7) over a slice of the frozen
benchmark and reports, per condition:

  * **parse rate** — how often the reader answered at all. A first-class
    number, NEVER folded into accuracy. P7's misleading headline came from
    scoring abstentions as wrong answers.
  * **paired accuracy** — accuracy restricted to positions where EVERY
    condition answered. This is the primary metric. Comparing each condition on
    its own parsed subset is a selection effect: a condition that abstains on
    the hard positions looks good on the easy remainder.
  * **own-parsed accuracy** — reported alongside, with that caveat attached.
  * **leak rate** — how often the arm's text named the answer move, which is
    what makes the as-shipped/stripped distinction meaningful (or not: arm B
    frequently never names it).

Chance is 50% by construction, so lift is interpretable without a model of the
reader's absolute skill.

Conditions: `baseline` (no text), then each arm in as-shipped and stripped
form. When stripping removes nothing the prompt is byte-identical to
as-shipped, so the student cache serves it for free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import chess

import arms
import bank
from student import Student, available_models

RUNS = Path(__file__).resolve().parent / "runs"
MIN_GAP_CP = 50          # distractor must be genuinely worse, not near-equal


def build_pair(pid: str, fen: str, pvs: list[dict]) -> dict | None:
    """(best, distractor) from the MultiPV set, or None if unusable.

    The distractor is the widest-gap line, so it is plausible (an engine line)
    but clearly inferior. Order is flipped on a digest of the position id —
    deterministic, and it removes any A/B position bias without needing an RNG
    (which would break replay).
    """
    usable = [p for p in pvs if p.get("ucis")]
    if len(usable) < 2:
        return None
    sign = 1 if bank.white_to_move(fen) else -1
    ranked = sorted(((sign * p["cp"], p) for p in usable), key=lambda x: -x[0])
    (best_cp, best), (worst_cp, worst) = ranked[0], ranked[-1]
    gap = best_cp - worst_cp
    if gap < MIN_GAP_CP:
        return None
    board = chess.Board(fen)
    try:
        best_san = board.san(chess.Move.from_uci(best["ucis"][0]))
        foil_san = board.san(chess.Move.from_uci(worst["ucis"][0]))
    except (ValueError, AssertionError):
        return None
    if best_san == foil_san:
        return None
    flip = int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 2
    option_a, option_b = (foil_san, best_san) if flip else (best_san, foil_san)
    return {"id": pid, "fen": fen, "a": option_a, "b": option_b,
            "answer": "B" if flip else "A", "gap_cp": gap,
            "answer_uci": best["ucis"][0]}


def wilson(hits: int, n: int) -> tuple[float, float]:
    """95% Wilson interval — small-n honest, unlike the normal approximation.
    Reported because the whole point of P7 was that n=50 could not distinguish
    the arms, and an interval says that where a bare rate does not."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def run(limit: int, model: str, arm_names: list[str],
        band: str = "2400v2400") -> dict:
    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts(band)
    ids = sorted(set(bench) & set(eng) & set(rolls))

    pairs = []
    for pid in ids:
        p = build_pair(pid, bench[pid]["fen"], eng[pid])
        if p:
            pairs.append(p)
        if len(pairs) >= limit:
            break

    student = Student(model)
    conditions = ["baseline"]
    for a in arm_names:
        conditions += [f"{a}:shipped", f"{a}:stripped"]

    # answers[pid][condition] = "A" / "B" / None(abstained); missing = arm declined
    answers: dict[str, dict[str, str | None]] = defaultdict(dict)
    leaks = defaultdict(int)
    declined = defaultdict(int)
    latency = defaultdict(float)
    calls = defaultdict(int)

    for i, pair in enumerate(pairs, 1):
        pid, fen = pair["id"], pair["fen"]
        r = student.choose(fen, pair["a"], pair["b"])
        answers[pid]["baseline"] = r.value
        latency["baseline"] += r.latency_s
        calls["baseline"] += 1

        for arm in arm_names:
            text = arms.render(arm, pid, bench[pid], eng[pid], rolls[pid])
            if text is None:
                declined[arm] += 1
                continue
            stripped, removed = arms.strip_move(text, fen, pair["answer_uci"])
            if removed:
                leaks[arm] += 1
            for label, body in ((f"{arm}:shipped", text),
                                (f"{arm}:stripped", stripped)):
                r = student.choose(fen, pair["a"], pair["b"], body)
                answers[pid][label] = r.value
                latency[label] += r.latency_s
                calls[label] += 1
        if i % 25 == 0:
            print(f"  … {i}/{len(pairs)}", file=sys.stderr, flush=True)

    # Pairing is PER COMPARISON: each condition against the baseline on the
    # subset where BOTH answered. A single global intersection across every
    # condition collapses — 7 conditions at ~0.6 parse rate leaves ~3% of the
    # slice — and throws away the power the sweep was run to get.
    by_id = {p["id"]: p for p in pairs}
    out_conditions = {}
    for c in conditions:
        present = [p for p in pairs if c in answers[p["id"]]]
        answered = [p for p in present if answers[p["id"]][c] is not None]
        own_hits = sum(answers[p["id"]][c] == p["answer"] for p in answered)

        # vs-baseline paired subset for THIS condition
        both = [p for p in present
                if answers[p["id"]][c] is not None
                and answers[p["id"]].get("baseline") is not None]
        hits = sum(answers[p["id"]][c] == p["answer"] for p in both)
        base_hits = sum(answers[p["id"]]["baseline"] == p["answer"] for p in both)

        out_conditions[c] = {
            "n_present": len(present),
            "n_answered": len(answered),
            "parse_rate": len(answered) / len(present) if present else 0.0,
            "own_parsed_accuracy": own_hits / len(answered) if answered else None,
            "n_paired": len(both),
            "paired_hits": hits,
            "paired_accuracy": hits / len(both) if both else None,
            "paired_ci95": wilson(hits, len(both)),
            # The baseline's OWN accuracy on this same subset — the correct
            # subtrahend. Using the global baseline rate instead would compare
            # two different position sets.
            "baseline_on_subset": base_hits / len(both) if both else None,
            "lift": (hits - base_hits) / len(both) if both else None,
            "mean_latency_s": latency[c] / calls[c] if calls[c] else 0.0,
        }

    return {
        "model": model,
        "band": band,
        "n_pairs": len(pairs),
        "min_gap_cp": MIN_GAP_CP,
        "median_gap_cp": sorted(p["gap_cp"] for p in pairs)[len(pairs) // 2]
                         if pairs else None,
        "arms": {a: {"declined": declined[a],
                     "leak_rate": leaks[a] / max(1, len(pairs) - declined[a])}
                 for a in arm_names},
        "conditions": out_conditions,
    }


def report(res: dict) -> None:
    print(f"model  {res['model']}")
    print(f"pairs  {res['n_pairs']}  (median gap {res['median_gap_cp']}cp, "
          f"min {res['min_gap_cp']}cp)   chance 0.500\n")

    print(f"{'condition':18s} {'parse':>6s} {'n_pair':>7s} {'acc':>7s} "
          f"{'95% CI':>14s} {'base':>7s} {'lift':>7s} {'s/call':>7s}")
    for c, d in res["conditions"].items():
        lo, hi = d["paired_ci95"]
        def f(x, w=7, p=3):
            return f"{x:{w}.{p}f}" if x is not None else " " * (w - 1) + "—"
        print(f"{c:18s} {d['parse_rate']:6.2f} {d['n_paired']:7d} "
              f"{f(d['paired_accuracy'])} {f'[{lo:.2f},{hi:.2f}]':>14s} "
              f"{f(d['baseline_on_subset'])} {f(d['lift'])} "
              f"{d['mean_latency_s']:7.2f}")

    print("\n`base` is the baseline's accuracy on that condition's OWN paired\n"
          "subset, so `lift` compares the same positions. Read the CI, not the\n"
          "point estimate: overlap means the slice is too small to separate the\n"
          "conditions — a statement about n, not about the arms.\n")

    for a, d in res["arms"].items():
        print(f"arm {a}: declined {d['declined']}  "
              f"leak rate {d['leak_rate']:.2f} "
              f"(fraction of texts naming the answer move)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--model", default="google/gemma-4-e4b")
    ap.add_argument("--arms", default="A,B,D")
    ap.add_argument("--band", default="2400v2400")
    ap.add_argument("--tag", default="", help="label for the run file")
    args = ap.parse_args()

    models = available_models()
    if not models:
        raise SystemExit("no local server on 127.0.0.1:1234 — `lms server start`")
    if args.model not in models:
        raise SystemExit(f"{args.model!r} not served; have {models}")

    arm_names = [a.strip().upper() for a in args.arms.split(",") if a.strip()]
    t0 = time.time()
    res = run(args.limit, args.model, arm_names, args.band)
    res["wall_s"] = time.time() - t0

    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = f"{stamp}{'-' + args.tag if args.tag else ''}.json"
    (RUNS / name).write_text(json.dumps(res, indent=1))

    report(res)
    print(f"\nwall {res['wall_s']:.0f}s  ->  runs/{name}")


if __name__ == "__main__":
    main()

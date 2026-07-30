"""gen_human_page — build the human-calibration page (self-contained HTML).

The one measurement this layer cannot make with a local model: is a weak LLM a
sane proxy for a human learner? The loop closed (LOG.md P16) with every
editorial variant null on the machine reader; whether a HUMAN gets value from
the read is the remaining open gate, and only a human can answer it.

Design (kept identical to the machine task so the numbers are comparable):

  * 40 positions sampled evenly across the same 400 pairs the sweeps used
    (every 10th by sorted order — deterministic, no RNG to break replay).
  * Same two candidates, same A/B order (the digest flip), same 50cp+ gap.
  * Within-subject: positions alternate cold / with arm B's read by sample
    index — 20 each, interleaved so fatigue spreads across both conditions.
  * Boards embedded as SVG (python-chess), White at the bottom — every
    benchmark position is White to move (LOG.md P1).
  * Answers persist in localStorage; export downloads JSON shaped for a
    paired analysis against the machine's cached answers on the same ids.

Honesty constraints: the answer key is NOT in the page (scoring happens back
here against the bank), and no engine evals are shown.

Output: reading/human_calibration.html — open in a browser, click through,
export, drop the JSON into reading/runs/.
"""
from __future__ import annotations

import json
from pathlib import Path

import chess
import chess.svg

import arms
import bank
import score

OUT = Path(__file__).resolve().parent / "human_calibration.html"
N_SAMPLES = 40


def build_items() -> list[dict]:
    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts("2400v2400")
    ids = sorted(set(bench) & set(eng) & set(rolls))
    pairs = []
    for pid in ids:
        p = score.build_pair(pid, bench[pid]["fen"], eng[pid])
        if p:
            pairs.append(p)
        if len(pairs) >= 400:
            break

    step = len(pairs) // N_SAMPLES
    items = []
    for i in range(N_SAMPLES):
        pr = pairs[i * step]
        pid = pr["id"]
        with_read = i % 2 == 1
        text = None
        if with_read:
            text = arms.render("B", pid, bench[pid], eng[pid], rolls[pid])
            if text is None:          # render declined -> fall back to cold
                with_read = False
        items.append({
            "id": pid,
            "svg": chess.svg.board(chess.Board(pr["fen"]), size=380),
            "a": pr["a"], "b": pr["b"],
            "condition": "with_read" if with_read else "cold",
            "text": text,
        })
    return items


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Lucena — human calibration (40 positions)</title>
<style>
 body {{ font: 16px/1.5 Georgia, serif; background:#F1EDE3; color:#222;
        max-width: 760px; margin: 2rem auto; padding: 0 1rem; }}
 .board {{ text-align:center; margin:1rem 0; }}
 .notes {{ background:#fff; border:1px solid #cbc4b4; padding: .8rem 1rem;
          white-space: pre-wrap; font-size:14px; margin:1rem 0; }}
 button.opt {{ font:inherit; font-size:18px; padding:.6rem 1.6rem; margin:.4rem;
              cursor:pointer; background:#fff; border:2px solid #444; }}
 button.opt:hover {{ background:#e8e2d2; }}
 .meta {{ color:#777; font-size:13px; }}
</style>
<h2>Which move is better?</h2>
<p class="meta">White to move in every position. Answer from your own judgement
— no engine. Some positions come with notes; read them if present. Progress is
saved locally; you can close and resume.</p>
<div id="app"></div>
<script>
const ITEMS = {items_json};
const KEY = "lucena_human_calibration_v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{{}}");
function save() {{ localStorage.setItem(KEY, JSON.stringify(state)); }}
function next() {{ return ITEMS.findIndex(it => !(it.id in state)); }}
function render() {{
  const i = next();
  const app = document.getElementById("app");
  if (i < 0) {{ done(app); return; }}
  const it = ITEMS[i];
  app.innerHTML =
    `<p class="meta">Position ${{i+1}} of ${{ITEMS.length}}</p>` +
    `<div class="board">${{it.svg}}</div>` +
    (it.text ? `<div class="notes">${{it.text}}</div>` : "") +
    `<div style="text-align:center">` +
    `<button class="opt" onclick="pick('${{it.id}}','A')">A: ${{it.a}}</button>` +
    `<button class="opt" onclick="pick('${{it.id}}','B')">B: ${{it.b}}</button>` +
    `</div>`;
}}
function pick(id, ans) {{
  state[id] = {{ answer: ans, t: Date.now() }};
  save(); render();
}}
function done(app) {{
  app.innerHTML = `<h3>Done — thank you.</h3>
    <button class="opt" onclick="exp()">Download answers</button>
    <button class="opt" onclick="if(confirm('Erase all answers?')){{state={{}};save();render();}}">Reset</button>`;
}}
function exp() {{
  const out = ITEMS.map(it => ({{
    id: it.id, condition: it.condition, answer: (state[it.id]||{{}}).answer || null
  }}));
  const blob = new Blob([JSON.stringify(out, null, 1)], {{type:"application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "human_calibration_answers.json";
  a.click();
}}
render();
</script>
"""


def main() -> None:
    items = build_items()
    n_read = sum(it["condition"] == "with_read" for it in items)
    OUT.write_text(PAGE.format(items_json=json.dumps(items)))
    print(f"wrote {OUT}")
    print(f"{len(items)} positions: {len(items)-n_read} cold, {n_read} with the read")
    print("open in a browser, answer, download the JSON into reading/runs/")


if __name__ == "__main__":
    main()

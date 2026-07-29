"""student — the weak reader whose comprehension is the measurement.

The student must be WEAK: the metric is lift over an unaided baseline, so a
reader that already answers correctly most of the time collapses the range.
A small local model gives that weakness for free — and costs nothing per call,
so a sweep can be re-run.

Runs against any OpenAI-compatible endpoint; in practice LM Studio on
127.0.0.1:1234 (`lms server status`). No API key, no cloud, no per-call cost.

## The task is DISCRIMINATION, not move generation

`LOG.md` P6 is a hard negative: a 7.5B local model produces a legal move from
a FEN only 15% of the time, and only 30% even when handed the complete list of
legal moves, with accuracy *falling*. A ceiling that low sits under every arm,
so lift would be measured inside the residue and most variance would come from
whether the model could read the board that time.

So the student is asked to CHOOSE between two named candidate moves. The answer
space is one letter, chance is a clean 50%, and board reading is no longer the
bottleneck. `ask()` (move generation) is kept for the record but is not the
measurement path — see its docstring.

## Assistant prefill

These models reason without bound: given 400 tokens they spend 397 on hidden
reasoning and return empty content (P7). Seeding the assistant turn with
`"Answer: "` bypasses it — 0.6s/call instead of 22s.

**This is a stated property of the harness, not an implementation detail.**
Prefill forces an immediate answer with no deliberation. For a weak-reader
proxy that is defensible — a first impression rather than a search — but it
changes what is measured, and it is applied identically to the baseline and
every arm so it cannot manufacture lift.

## Three things this module refuses to blur

  * **A parse failure is not a wrong answer.** It is recorded as an
    abstention. Folding the two together makes a chatty model look like a poor
    reader and moves the metric for reasons unrelated to comprehension — which
    is exactly how P7's misleading first headline arose.
  * **Every answer is cached** by (model, temperature, messages) digest, so
    re-scoring is free and a rerun replays rather than re-infers. The cache is
    part of the experiment record.
  * **Nothing here knows about arms.** The student sees a position, two
    options, and optionally some text. It never learns which arm wrote the
    text, so it cannot treat arms differently.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import chess

BASE_URL = "http://127.0.0.1:1234/v1"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "student"

CHOICE_SYSTEM = (
    "You are a chess player choosing a move. You will see a position and two "
    "candidate moves. Reply with ONLY the single letter A or B — whichever "
    "move is better. Do not explain."
)
MOVE_SYSTEM = (
    "You are playing a game of chess. Reply with ONLY your chosen move in "
    "standard algebraic notation (for example: Nf3, exd5, O-O). Do not explain."
)
PREFILL = "Answer: "

_LETTER = re.compile(r"\b([AB])\b")

# Small models answer the same question in several encodings. Measured in the
# cache after the first sweep: bare "A", the enclosed-letter emoji "🅰"/"🅱"
# (with and without the variation selector), and the ordinal "1"/"2" for
# first/second option. Treating any of these as an abstention silently drops
# real answers — and does it ASYMMETRICALLY, since prompt length shifts which
# encoding the model reaches for, which manufactures a fake parse-rate
# difference between arms (LOG.md P7/P8).
_ALIASES = {
    "A": "A", "B": "B", "a": "A", "b": "B",
    "\U0001F170": "A", "\U0001F171": "B",   # 🅰 🅱
    "1": "A", "2": "B",
}
_SAN_TOKEN = re.compile(
    r"\b(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?"
    r"|[a-h]x?[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)[+#]?")


@dataclass(frozen=True)
class Reply:
    """One student reply.

    `value` is the parsed answer ("A"/"B" for a choice, UCI for a move) or None
    if nothing parseable came back. `abstained` is the honest name for that
    case: the reader did not answer, which is not the same as answering wrongly.
    """
    value: str | None
    raw: str
    abstained: bool
    latency_s: float
    cached: bool


def _digest(model: str, temperature: float, messages: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(f"{model}\x00{temperature}\x00".encode())
    for m in messages:
        h.update(m["role"].encode())
        h.update(b"\x00")
        h.update(m["content"].encode())
        h.update(b"\x00")
    return h.hexdigest()[:32]


def parse_letter(reply: str) -> str | None:
    """"A" or "B" from a reply, across the encodings small models actually use.

    Returns None only when nothing answer-like is present — a genuine
    abstention, which is recorded as such and never scored as a wrong answer.
    """
    text = reply.strip()
    # Strip the variation selector so "🅰️" and "🅰" are one case.
    text = text.replace("️", "")
    if not text:
        return None
    m = _LETTER.search(text.upper())
    if m:
        return m.group(1)
    for ch in text:
        if ch in _ALIASES:
            return _ALIASES[ch]
    return None


def parse_move(reply: str, fen: str) -> str | None:
    """First LEGAL move mentioned in the reply, as UCI.

    Tolerant of `1. Nf3`, `**Nf3**`, `Nf3 is best` — discarding readable
    answers as parse failures would depress every arm and hide signal behind
    harness noise. Tolerance stops at legality: an illegal suggestion is a
    genuine wrong answer, not a formatting problem.
    """
    board = chess.Board(fen)
    for token in _SAN_TOKEN.findall(reply):
        try:
            return board.parse_san(token).uci()
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            continue
    return None


class Student:
    def __init__(self, model: str, temperature: float = 0.0,
                 max_tokens: int = 12, base_url: str = BASE_URL,
                 timeout: int = 600, cache_dir: Path = CACHE_DIR):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_dir = cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", model)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- prompt assembly -------------------------------------------------
    # One assembler, so a condition differs from the baseline ONLY by the
    # presence of the explanation. Any other difference would surface as lift
    # and be indistinguishable from comprehension.
    def _choice_messages(self, fen: str, option_a: str, option_b: str,
                         explanation: str | None) -> list[dict]:
        side = "White" if fen.split()[1] == "w" else "Black"
        parts = [f"FEN: {fen}", f"{side} to move."]
        if explanation:
            parts += ["", "Notes on this position:", explanation.strip()]
        parts += ["", f"A: {option_a}", f"B: {option_b}", "",
                  "Which is better, A or B?"]
        return [{"role": "system", "content": CHOICE_SYSTEM},
                {"role": "user", "content": "\n".join(parts)},
                {"role": "assistant", "content": PREFILL}]

    # ---- the measurement path -------------------------------------------
    def choose(self, fen: str, option_a: str, option_b: str,
               explanation: str | None = None) -> Reply:
        """Pick between two candidate moves. Returns "A", "B", or abstains."""
        messages = self._choice_messages(fen, option_a, option_b, explanation)
        key = _digest(self.model, self.temperature, messages)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            rec = json.loads(path.read_text())
            # Re-parse from the stored RAW text rather than trusting the stored
            # verdict: the parser is part of the experiment and changes as new
            # answer encodings are discovered, and a cache that served stale
            # verdicts would freeze old parser bugs into every later run.
            p = parse_letter(rec["raw"])
            return Reply(p, rec["raw"], p is None, rec["latency_s"], True)

        raw, latency = self._post(messages)
        parsed = parse_letter(raw)
        path.write_text(json.dumps(
            {"raw": raw, "parsed": parsed, "latency_s": latency,
             "fen": fen, "had_explanation": explanation is not None}, indent=1))
        return Reply(parsed, raw, parsed is None, latency, False)

    def _post(self, messages: list[dict]) -> tuple[str, float]:
        body = json.dumps({
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.load(resp)
        return payload["choices"][0]["message"]["content"], time.time() - t0

    # ---- kept for the record, not the measurement path -------------------
    def ask(self, fen: str, explanation: str | None = None) -> Reply:
        """Free move generation. NOT the measurement path.

        `LOG.md` P6: local 7.5B models answer legally only 15-30% of the time,
        which puts a ceiling under every arm. Kept so the negative result stays
        reproducible, and in case a larger model is ever available.
        """
        side = "White" if fen.split()[1] == "w" else "Black"
        parts = [f"FEN: {fen}", f"{side} to move."]
        if explanation:
            parts += ["", "Notes on this position:", explanation.strip()]
        parts += ["", "Your move?"]
        messages = [{"role": "system", "content": MOVE_SYSTEM},
                    {"role": "user", "content": "\n".join(parts)},
                    {"role": "assistant", "content": PREFILL}]
        key = _digest(self.model, self.temperature, messages)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            rec = json.loads(path.read_text())
            p = parse_move(rec["raw"], fen)      # re-parse; see choose()
            return Reply(p, rec["raw"], p is None, rec["latency_s"], True)
        raw, latency = self._post(messages)
        parsed = parse_move(raw, fen)
        path.write_text(json.dumps(
            {"raw": raw, "parsed": parsed, "latency_s": latency, "fen": fen},
            indent=1))
        return Reply(parsed, raw, parsed is None, latency, False)


def available_models(base_url: str = BASE_URL) -> list[str]:
    """Model ids the local server is serving — so a sweep fails fast with a
    useful message instead of a 404 from inside the loop."""
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=10) as resp:
            return [m["id"] for m in json.load(resp).get("data", [])]
    except (urllib.error.URLError, OSError):
        return []


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="one-shot student probe")
    ap.add_argument("--model", default="google/gemma-4-e4b")
    ap.add_argument("--fen", default="1q1r2k1/1p1b1pbn/r2p2p1/p2P3p/P3NB2/"
                                     "1QN4P/1P3PP1/2RR2K1 w - - 0 21")
    ap.add_argument("--a", default="Nxd6")
    ap.add_argument("--b", default="Bg3")
    args = ap.parse_args()

    models = available_models()
    if not models:
        raise SystemExit("no local server on 127.0.0.1:1234 — `lms server start`")
    if args.model not in models:
        raise SystemExit(f"{args.model!r} not served; have {models}")

    r = Student(args.model).choose(args.fen, args.a, args.b)
    print(f"answer    {r.value}")
    print(f"abstained {r.abstained}")
    print(f"latency   {r.latency_s:.2f}s (cached={r.cached})")
    print(f"raw       {r.raw[:120]!r}")

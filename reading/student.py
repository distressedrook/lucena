"""student — the weak reader whose comprehension is the measurement.

The student must be WEAK. The metric is lift over an unaided baseline, so a
reader that already finds the eval-equal move most of the time collapses the
range and the harness loses all sensitivity. A small local model is therefore
the methodologically preferred choice, not a budget compromise — and it costs
nothing per call, so a sweep can be re-run.

Runs against any OpenAI-compatible endpoint; in practice LM Studio on
127.0.0.1:1234 (`lms server status`). No API key, no cloud, no per-call cost.

Three things this module refuses to blur:

  * **A parse failure is not a wrong move.** An unparseable reply is a harness
    failure and is counted separately. Folding the two together would let a
    chatty model look like a weak player and would move the metric for reasons
    that have nothing to do with comprehension.
  * **Every answer is cached on disk** by (model, temperature, prompt) digest.
    At local-inference latencies a sweep is hours, so re-scoring must be free
    and a rerun must be replayable. The cache IS the experiment record.
  * **Nothing here knows about arms.** The student sees a position and
    optionally some text. It never learns which arm produced the text, so it
    cannot treat arms differently.
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

# Reply with the move only. Deliberately spare: the student is a reader, not a
# coach, and any instruction to "think" both slows it down and changes what is
# being measured from comprehension to reasoning ability.
SYSTEM = ("You are playing a game of chess. Reply with ONLY your chosen move "
          "in standard algebraic notation (for example: Nf3, exd5, O-O, Qxb7+). "
          "Do not explain. Do not add commentary.")

_SAN_TOKEN = re.compile(
    r"\b(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?"
    r"|[a-h]x?[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)[+#]?")


@dataclass(frozen=True)
class Answer:
    """One student reply. `move` is None iff the reply could not be parsed."""
    move: str | None          # UCI, legal in the position
    raw: str                  # the reply text, for audit
    parse_failed: bool
    latency_s: float
    cached: bool


def _digest(model: str, temperature: float, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, f"{temperature}", system, user):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()[:32]


def parse_move(reply: str, fen: str) -> str | None:
    """First legal move mentioned in the reply, as UCI. None if there is none.

    Tolerant of the shapes small models actually emit — `1. Nf3`, `**Nf3**`,
    `Nf3 is best` — because the alternative is discarding readable answers as
    parse failures and depressing every arm equally, which hides real signal
    behind harness noise. Tolerance stops at the first LEGAL move: an illegal
    suggestion is a genuine wrong answer, not a formatting problem.
    """
    board = chess.Board(fen)
    for token in _SAN_TOKEN.findall(reply):
        try:
            move = board.parse_san(token)
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            continue
        return move.uci()
    return None


class Student:
    def __init__(self, model: str, temperature: float = 0.0,
                 max_tokens: int = 120, base_url: str = BASE_URL,
                 timeout: int = 900, cache_dir: Path = CACHE_DIR):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_dir = cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", model)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- prompt assembly -------------------------------------------------
    # One place, so the baseline and the arms differ ONLY by the presence of
    # the explanation. Any other difference between the two prompts would show
    # up as lift and be indistinguishable from comprehension.
    def _user_message(self, fen: str, explanation: str | None) -> str:
        side = "White" if fen.split()[1] == "w" else "Black"
        parts = [f"FEN: {fen}", f"{side} to move."]
        if explanation:
            parts.append("")
            parts.append("Notes on this position:")
            parts.append(explanation.strip())
        parts.append("")
        parts.append("Your move?")
        return "\n".join(parts)

    # ---- transport -------------------------------------------------------
    def _post(self, user: str) -> tuple[str, float]:
        body = json.dumps({
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.load(resp)
        return payload["choices"][0]["message"]["content"], time.time() - t0

    def ask(self, fen: str, explanation: str | None = None) -> Answer:
        user = self._user_message(fen, explanation)
        key = _digest(self.model, self.temperature, SYSTEM, user)
        path = self.cache_dir / f"{key}.json"

        if path.exists():
            rec = json.loads(path.read_text())
            return Answer(rec["move"], rec["raw"], rec["parse_failed"],
                          rec["latency_s"], cached=True)

        raw, latency = self._post(user)
        move = parse_move(raw, fen)
        rec = {"move": move, "raw": raw, "parse_failed": move is None,
               "latency_s": latency, "fen": fen,
               "had_explanation": explanation is not None}
        path.write_text(json.dumps(rec, indent=1))
        return Answer(move, raw, move is None, latency, cached=False)


def available_models(base_url: str = BASE_URL) -> list[str]:
    """Model ids the local server is serving. Used to fail fast with a useful
    message rather than a 404 from inside a sweep."""
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=10) as resp:
            return [m["id"] for m in json.load(resp).get("data", [])]
    except (urllib.error.URLError, OSError):
        return []


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="one-shot student probe")
    ap.add_argument("--model", default="google/gemma-4-e4b")
    ap.add_argument("--max-tokens", type=int, default=120)
    ap.add_argument("--fen", default="r4rk1/p4pbp/1qp1p1p1/3pP3/2pP4/"
                                     "QPPbB3/P2N1PPP/R3R1K1 w - - 0 16")
    args = ap.parse_args()

    models = available_models()
    if not models:
        raise SystemExit("no local server on 127.0.0.1:1234 — `lms server start`")
    if args.model not in models:
        raise SystemExit(f"{args.model!r} not served; have {models}")

    s = Student(args.model, max_tokens=args.max_tokens)
    a = s.ask(args.fen)
    print(f"move          {a.move}")
    print(f"parse_failed  {a.parse_failed}")
    print(f"latency       {a.latency_s:.1f}s (cached={a.cached})")
    print(f"raw           {a.raw[:200]!r}")

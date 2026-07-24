#!/usr/bin/env python3
"""Harvest the Wikibooks *Chess Opening Theory* book into a bundled,
FEN-keyed theory file (`lucena_core/data/wikibooks_theory.json`).

WHY a bundled snapshot, not a live fetch: the coach's grounding must be
deterministic and offline (no runtime dependency on Wikimedia, no per-turn
latency). This is a ONE-TIME tooling job, the same shape as whatever
produced `openings.tsv`.

KEYING: Wikibooks pages are titled by MOVE PATH
(`Chess Opening Theory/1. e4/1...c5/2. Nf3`); we replay that path to the
resulting FEN and key on it — which merges transpositions for free (two
move orders reaching the same position share one entry), something the
move-path keying can't do.

LICENSE: Wikibooks text is CC BY-SA. Every entry stores its `source_url`
so the product can attribute it; the text is shown VERBATIM (never
LLM-adapted), which keeps share-alike clear of our code.

Run:  python tools/wikibooks_harvest.py [--limit N] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import chess

API = "https://en.wikibooks.org/w/api.php"
UA = ("LucenaChessCoach/0.1 (opening-theory harvest, one-time; "
      "contact avismarahl@gmail.com)")
PREFIX = "Chess Opening Theory/"
PAGE_URL = "https://en.wikibooks.org/wiki/"
MIN_DESC = 80          # a description shorter than this is a stub/nav remnant

# move-number prefix on a path segment: "12. ", "12...", "1." etc.
_MOVENUM = re.compile(r"^\d+\.(\.\.)?\s*")
# a [[/2. Nf3|2. Nf3 - Open Sicilian]] response link inside {{Chess Position}}
_RESP = re.compile(r"\[\[/[^|\]]+\|([^\]]+)\]\]")
_ECO = re.compile(r"eco\s*=\s*(?:\[\[[^|\]]*\|)?([^\]\n|}]+)")


class FetchError(Exception):
    """A page could not be fetched (as opposed to being a legit stub). Kept
    DISTINCT from a skip so a rate-limited page is never silently dropped —
    the exact silent-miss failure openings.py warns about."""


def _get(params: dict, *, tries: int = 6) -> dict:
    """One API call, polite and retrying. `maxlag=5` is Wikimedia's asked-for
    politeness knob (server sheds us when replication lags); 429/503 and
    transient errors back off honouring Retry-After. Raises FetchError only
    after exhausting retries — callers must not treat that as 'no content'."""
    q = {**params, "format": "json", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(q)
    delay = 1.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                wait = float(e.headers.get("Retry-After") or 0) or delay
                time.sleep(min(wait, 30.0))
                delay = min(delay * 2, 30.0)
                continue
            raise FetchError(f"{e.code} on {params.get('titles') or url}") from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if attempt < tries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            raise FetchError(str(e)) from e
    raise FetchError("retries exhausted")


def all_titles(limit: int | None = None) -> list[str]:
    """Every subpage of the book, via list=allpages (paginated)."""
    out: list[str] = []
    cont = None
    while True:
        p = {"action": "query", "list": "allpages", "apnamespace": 0,
             "apprefix": PREFIX, "aplimit": "500"}
        if cont:
            p["apcontinue"] = cont
        d = _get(p)
        out += [x["title"] for x in d["query"]["allpages"]]
        if limit and len(out) >= limit:
            return out[:limit]
        cont = d.get("continue", {}).get("apcontinue")
        if not cont:
            return out
        time.sleep(0.1)


def title_to_moves(title: str) -> list[str]:
    """`Chess Opening Theory/1. e4/1...c5` -> ['e4', 'c5']."""
    return [m for seg in title.split("/")[1:]
            if (m := _MOVENUM.sub("", seg).strip())]


def replay(moves: list[str]) -> str:
    """SAN list -> FEN. Raises on any illegal/unparseable move."""
    b = chess.Board()
    for san in moves:
        b.push_san(san)
    return b.fen()


# a SAN move token (incl. castling, promotion, check/mate, annotation marks)
_SAN = re.compile(
    r"^(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?[!?]*$")


def _is_move_list_line(s: str) -> bool:
    """A line that is nothing but an echoed move list ('1. d4 Nf6 2. c4 d5',
    optionally with a leading '.' artifact) — preamble on many pages, not
    prose. Move numbers are stripped, then every remaining token must be SAN;
    a single non-move word (real prose) disqualifies the line."""
    toks = re.sub(r"\d+\.+", " ", s).split()
    return bool(toks) and all(_SAN.match(t) for t in toks)


def _description(extract: str) -> str:
    """The lead theory prose: the body of the FIRST section (heading of ANY
    level — some pages open with '===', not '=='), up to the NEXT heading of
    any level (so trailing '== References ==' / '== Footnotes ==' never leak
    in), with any leading echoed move-list line stripped. Verbatim otherwise.
    Pages whose body is only a move list collapse to empty here and are
    dropped by the MIN_DESC stub filter."""
    m = re.search(r"^={2,}.*?={2,}\s*$", extract, re.M)   # first heading, ANY level
    body = extract[m.end():] if m else extract
    nxt = re.search(r"^={2,}", body, re.M)                # next heading, ANY level
    if nxt:
        body = body[:nxt.start()]
    lines = body.strip().splitlines()
    while lines and _is_move_list_line(lines[0].strip()):
        lines.pop(0)
    return " ".join(" ".join(lines).split()).strip()


def _name(extract: str, wikitext: str, title: str) -> str:
    """Opening name for this position: the first `== · name ==` heading, the
    template's first positional arg, or the last path segment as a fallback."""
    m = re.search(r"^==\s*(?:[^·=]*·\s*)?(.+?)\s*==\s*$", extract, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{\{Chess Position\s*\n?\|\s*([^\n|]+)", wikitext)
    if m and "=" not in m.group(1):
        return m.group(1).strip()
    return title.split("/")[-1].strip()


def _responses(wikitext: str) -> list[str]:
    """Labeled candidate continuations from the {{Chess Position}} template,
    e.g. '2. Nf3 - Open Sicilian'."""
    m = re.search(r"responses\s*=(.*?)(?:\n\}\}|\n\|)", wikitext, re.S)
    if not m:
        return []
    seen, out = set(), []
    for lab in _RESP.findall(m.group(1)):
        lab = lab.strip()
        if lab and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out


def _eco(wikitext: str) -> str | None:
    m = _ECO.search(wikitext)
    return m.group(1).strip() if m else None


def harvest_one(title: str) -> dict | None:
    """One page -> an entry, or None for a LEGIT skip (unparseable/illegal
    move path, or a genuine stub). Raises FetchError if the page could not
    be fetched — that is NOT a skip and must be retried, never dropped."""
    try:
        moves = title_to_moves(title)
        if not moves:
            return None
        fen = replay(moves)                       # illegal path -> legit skip
    except (ValueError, chess.InvalidMoveError,
            chess.IllegalMoveError, chess.AmbiguousMoveError):
        return None
    d = _get({"action": "query", "prop": "extracts|revisions",
              "explaintext": 1, "rvprop": "content", "rvslots": "main",
              "titles": title, "redirects": 1})          # raises FetchError
    page = next(iter(d["query"]["pages"].values()))
    extract = (page.get("extract") or "")
    rev = page.get("revisions", [{}])[0]
    wikitext = rev.get("slots", {}).get("main", {}).get("*", "") or ""
    desc = _description(extract)
    if len(desc) < MIN_DESC:                       # stub filter
        return None
    return {
        "fen": fen,
        "moves": moves,
        "name": _name(extract, wikitext, title),
        "eco": _eco(wikitext),
        "description": desc,
        "responses": _responses(wikitext),
        "source_url": PAGE_URL + urllib.parse.quote(title.replace(" ", "_")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=2)   # polite: Wikimedia
    ap.add_argument("--out", default=str(
        Path(__file__).resolve().parent.parent
        / "python" / "lucena_core" / "data" / "wikibooks_theory.json"))
    a = ap.parse_args()

    titles = all_titles(a.limit)
    print(f"[harvest] {len(titles)} subpages; fetching with "
          f"{a.workers} workers…", flush=True)

    entries: dict[str, dict] = {}
    kept = skipped = 0
    failures: list[str] = []

    def _add(e: dict) -> None:
        # transposition merge: keep the SHORTEST move path reaching the FEN
        prev = entries.get(e["fen"])
        if prev is None or len(e["moves"]) < len(prev["moves"]):
            entries[e["fen"]] = e

    def _run(items: list[str], note: str) -> None:
        nonlocal kept, skipped
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = {ex.submit(harvest_one, t): t for t in items}
            for i, (fut, t) in enumerate(((f, futs[f]) for f in futs), 1):
                try:
                    e = fut.result()
                except FetchError:
                    failures.append(t)               # retried, never dropped
                    continue
                if e is None:
                    skipped += 1
                else:
                    _add(e); kept += 1
                if i % 250 == 0:
                    print(f"[harvest] {note} {i}/{len(items)}  kept={kept} "
                          f"skipped={skipped} fails={len(failures)} "
                          f"uniq={len(entries)}", flush=True)

    _run(titles, "pass1")
    # retry the fetch failures once more (they are NOT stubs) — a still-failing
    # page after this is reported, never silently absent
    if failures:
        retry, failures = failures, []
        print(f"[harvest] retrying {len(retry)} fetch failures…", flush=True)
        _run(retry, "retry")
    if failures:
        print(f"[harvest] WARNING: {len(failures)} pages still unfetched "
              f"(NOT stubs): {failures[:10]}{'…' if len(failures) > 10 else ''}",
              flush=True)

    payload = {
        "_license": "Content: Wikibooks 'Chess Opening Theory', CC BY-SA 4.0. "
                    "Each entry's source_url is its attribution.",
        "_source": "https://en.wikibooks.org/wiki/Chess_Opening_Theory",
        "entries": entries,
    }
    Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"[harvest] wrote {len(entries)} unique-FEN entries "
          f"(kept {kept}, skipped {skipped}) -> {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

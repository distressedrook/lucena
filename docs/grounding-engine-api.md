# Grounding Engine — gRPC contract (v0.1, decisions folded in 2026-07-14)

> The **open, stateless** chess-truth service. Every RPC is a **pure function of its request** — no
> sessions, no board paint, no gate, no player state. Engine *processes* (Stockfish, Maia) stay warm,
> and it may hold **reference assets** (openings DB, etc.) to enrich fact sheets — reference data,
> *not* session state, so the API still carries no state. The backend is the only client; it reaches
> the engine ONLY through this contract.
>
> **Two inputs, ever: a FEN or a PGN.** A FEN yields a **fact sheet**; a PGN yields an **annotated
> fact sheet** (the engine walks the game itself — no per-move round-trips). Fact sheets are
> **engine-owned and natural-language-first**. On top of those two entry points the engine exposes the
> granular grounding RPCs below (Analyze / Evaluate / ExploreLine / Hints / Maia behaviour / …) as
> additional surfaces the backend can call directly.

## Design rules (from the legacy surface audit + the 2026-07-14 decisions)

1. **SAN is the only notation on the wire.** The system stores exactly one notation — **SAN** — and
   **the backend never sees UCI.** The engine converts **SAN → UCI at its entry** (Stockfish and Maia
   only speak UCI) and **UCI → SAN at its exit**. UCI exists *only* inside the engine, between those
   two converters. Every move that crosses this contract — request or response — is SAN. (`board.py`'s
   `.san()`/`.uci()` already do the conversion.)
2. **Determinism is explicit.** Analysis takes a `Limit` = exactly one of `movetime_ms` (prod,
   non-reproducible) | `nodes` (reproducible, needs `threads=1`) | `depth`, plus `multipv`. No ambient
   engine option-state — each request fully specifies it.
3. **Rating is per-request.** Maia-flavoured calls take `rating` (and optional `oppo_rating`) as
   fields — never ambient `player_rating`.
4. **Truth vs behaviour are separate services.** `Truth` (Stockfish + board core) works with no Maia.
   `Behaviour` (Maia) is optional and never returns an eval.
5. **The engine owns the fact sheet, natural-language-first.** It composes all deterministic grounding
   — material standing, eval-in-words, tactical/positional facts, the game-walk annotations — into the
   sheet; `material`, `positional`, the detectors, `hints`, and the PGN walk (`gamepass`) are
   **internal composers**, not backend concerns.
6. **Excluded on purpose (backend concerns, NOT engine):** board paint (`board_push`), the awaiting
   gate + classification, `deliver`/`note` coach glue, `player_tendency`/`move_read`/`move_meaning`
   (Maia NL glue + rating), the ≤400-token `enforce_budget` trim. The engine returns *structured
   truth*; the backend composes delivery.
7. **Unary only, cached internally.** Every RPC is one request → one response (no server-streaming —
   analysis returns once). The engine **caches by `(fen, limit, multipv)`** internally (pure function);
   invisible to the contract.
8. **Version-pinned:** Stockfish 18 (NNUE eval parser) asserted at engine startup; surfaced in
   `GetInfo`.

## Proto

```proto
syntax = "proto3";
package lucena.engine.v1;

// ── shared value objects ────────────────────────────────────────────────
message Limit {                       // exactly one — determinism knob
  oneof kind { uint32 movetime_ms = 1; uint64 nodes = 2; uint32 depth = 3; }
  uint32 threads = 4;                 // default 1 for reproducibility
}
message Score { oneof kind { int32 cp = 1; int32 mate = 2; } }   // POV = side to move
message Eval  { int32 cp = 1; double win_pct = 2; string glyph = 3; } // glyph ∈ "","?!","?","??","!"
message PieceOn { string square = 1; string piece = 2; string color = 3; } // piece 'P'..'K'; color white|black
message Material { int32 white = 1; int32 black = 2; int32 net = 3; string standing = 4; } // net = White-POV pawns; standing = plain English
message Line { uint32 rank = 1; Eval eval = 2; repeated string pv_san = 3; }   // SAN only (no UCI on the wire)
message Fact {                        // the salience layer; drives arrows + mastery
  string id = 1;                      // "F1".. (assigned by the engine at assembly)
  string kind = 2;                    // hanging|threat|defender-removed|fork|pin|combination
  repeated string squares = 3;        // 2 → arrow a→b; 1 → highlight
  string text = 4;                    // short human sentence (no id, no eval)
  string concept_id = 5;              // mastery routing
  double salience = 6;                // 0..1 (backend may drop)
  string provenance = 7;             // see|nullmove|static|... (backend may drop)
}

// ── request commons ─────────────────────────────────────────────────────
message Position { string fen = 1; }  // the one universal input

// ── Truth: Stockfish + board core (no Maia) ─────────────────────────────
service Truth {
  rpc ValidateFen (Position) returns (ValidateResp);            // legality + side_to_move
  rpc DetectFens  (TextReq)  returns (DetectFensResp);          // FENs embedded in free text
  rpc ParsePgn    (TextReq)  returns (ParsePgnResp);            // full PGN or bare movetext → Game (structural)
  rpc AnnotateGame(TextReq)  returns (AnnotateGameResp);        // PGN → ANNOTATED FACT SHEET — SKELETON, PARKED this cycle (shape only, not implemented)

  rpc Analyze     (AnalyzeReq)   returns (AnalyzeResp);         // FEN → FACT SHEET: pieces/material/eval/lines/facts(/positional), NL-first
  rpc Evaluate    (EvaluateReq)  returns (EvaluateResp);        // candidate move(s): class/glyph/Δwin%/best/refutation
  rpc Hints       (HintsReq)     returns (HintsResp);           // grounded hint ladder
  rpc ExploreLine (ExploreReq)   returns (ExploreResp);         // walk moves + optional end-position read

  rpc LegalMoves  (Position)     returns (MovesResp);           // pure board geometry (as needed)
  rpc Apply       (ApplyReq)     returns (Position);            // fen + move(SAN) → fen
  rpc GetInfo     (Empty)        returns (InfoResp);            // engine + Stockfish version, warmup status
}

message ValidateResp   { bool legal = 1; string side_to_move = 2; string error = 3; }
message TextReq        { string text = 1; }
message DetectFensResp { repeated string fens = 1; }            // legal, normalised
message ParsePgnResp {
  bool ok = 1; string error = 2;
  string result = 3; string start_fen = 4;
  map<string,string> headers = 5;
  repeated Ply plies = 6;
}
message Ply { uint32 ply = 1; uint32 move_no = 2; string side = 3; string san = 4;   // SAN only
              string fen_before = 5; string fen_after = 6; }

// PGN → annotated fact sheet (engine walks the game itself). Shape lifted from gamepass; refined at port.
message AnnotateGameResp {
  bool ok = 1; string error = 2;
  string result = 3; string start_fen = 4; map<string,string> headers = 5;
  repeated AnnotatedPly plies = 6;        // per-move annotation
  repeated string summary = 7;            // game-level fact sheet (turning points, themes) — NL
}
message AnnotatedPly {
  uint32 ply = 1; uint32 move_no = 2; string side = 3; string san = 4; string fen_after = 5;
  string class = 6; string glyph = 7; double delta_win_pct = 8; Eval eval = 9;
  string note = 10;                        // short NL annotation of the move
}

message AnalyzeReq {
  string fen = 1; Limit limit = 2; uint32 multipv = 3;          // default multipv 2
  Focus focus = 4;                                             // FULL | EVAL | THREATS | POSITIONAL
  Limit fact_limit = 5;                                        // short probe for the fact sheet (e.g. 300ms)
  uint32 top_facts = 6;                                        // ≤5
}
enum Focus { FULL = 0; EVAL = 1; THREATS = 2; POSITIONAL = 3; }
message AnalyzeResp {
  string fen = 1; string side_to_move = 2; repeated PieceOn pieces = 3;
  Material material = 4; Eval eval = 5;
  repeated Line lines = 6;
  repeated Fact facts = 7;
  Positional positional = 8;                                   // present only when FOCUS=POSITIONAL
}
message Positional { string phase = 1; repeated string leads = 2; map<string,Term> terms = 3; }
message Term { int32 cp = 1; string standing = 2; repeated string features = 3; }

message EvaluateReq { string fen = 1; repeated string moves = 2; Limit limit = 3; } // moves = SAN; 1 = deep read, ≤4 = compare
message EvaluateResp {
  string fen = 1; string side_to_move = 2; Material material = 3;
  // single-move deep read:
  string san = 4; string captured = 5; string class = 6; string glyph = 7;
  double delta_win_pct = 8; Eval eval = 9;
  BestMove best = 10; repeated string refutation_pv = 11; repeated Fact facts = 12;
  // multi-move compare:
  repeated MoveRank ranked = 13; string verdict = 14;          // "A > B > C"
}
message BestMove { string san = 1; repeated string pv_san = 2; Eval eval = 3; }
message MoveRank { string san = 1; Eval eval = 2; double delta_win_pct = 3; }   // SAN only

message HintsReq  { string fen = 1; Limit limit = 2; }
message HintsResp { string fen = 1; string best_san = 2; repeated Hint hints = 3; } // hints [] when no tactical handle
message Hint { uint32 rung = 1; string text = 2; repeated string squares = 3; string provenance = 4; }

message ExploreReq  { string fen = 1; repeated string moves = 2; bool analyze = 3; Limit limit = 4; } // moves = SAN, 1..12
message ExploreResp {
  string end_fen = 1; string side_to_move = 2; repeated string line_san = 3;
  string terminal = 4;                                         // "checkmate"|"stalemate"|""
  Material material = 5; Eval eval = 6; string best_san = 7; repeated string pv_san = 8; int32 mate_in = 9;
}
message ApplyReq { string fen = 1; string move = 2; }          // move = SAN
message MovesResp { repeated string san = 1; }                 // SAN only
message Empty {}
message InfoResp { string engine_version = 1; uint32 stockfish_major = 2; bool maia_available = 3; }

// ── Behaviour: Maia (optional; predicts human moves; NEVER an eval) ──────
service Behaviour {
  rpc TopHumanMoves  (MaiaReq)          returns (MaiaResp);
  rpc CommonMistakes (CommonMistakesReq) returns (CommonMistakesResp); // Maia selects, Stockfish rules
  rpc PoisonedLine   (PoisonedLineReq)   returns (PoisonedLineResp);   // trap the player at this level might fall for
}
message MaiaReq  { string fen = 1; uint32 rating = 2; uint32 oppo_rating = 3; uint32 n = 4; }
message MaiaResp { repeated MaiaMove moves = 1; }
message MaiaMove { string san = 1; uint32 rank = 2; double policy = 3; repeated int32 wdl = 4; Score eval = 5; } // SAN; eval never surfaced to player
message CommonMistakesReq { string fen = 1; uint32 rating = 2; Limit limit = 3; }
message CommonMistakesResp { uint32 rating = 1; string side_to_move = 2; string best_san = 3;
                            repeated MistakeMove moves = 4; repeated string mistakes = 5; }
message MistakeMove { string san = 1; uint32 rank = 2; string class = 3; double delta_win_pct = 4; repeated string refutation = 5; } // refutation = SAN
message PoisonedLineReq  { string fen = 1; uint32 rating = 2; }         // fen REQUIRED (no session default)
message PoisonedLineResp { string fen = 1; bool has_poisoned_line = 2;
                          repeated PoisonedStep poisoned_line = 3; string fatal = 4; string idea = 5; }
message PoisonedStep { string san = 1; string fen = 2; }       // SAN only
```

## Locked (2026-07-14)
- **Fact `id` + the whole fact sheet are engine-owned.** The engine composes the sheet (NL-first) and
  assigns `F1`.. by its own deterministic ranking. `material`, `positional`, the detectors, `hints`,
  and the PGN walk are internal composers, not backend calls.
- **Notation: SAN-only on the wire.** UCI never crosses this contract; the engine converts SAN→UCI at
  entry and UCI→SAN at exit (design rule 1).
- **`Positional`/`Term`** — reuse `positional.py`'s shape verbatim; do not slim it (not a contract
  concern).
- **Streaming — none.** Every RPC is unary (analysis returns once).
- **Caching — yes, internal**, by `(fen, limit, multipv)` (pure function); invisible to the contract.
- **Version-pin** — Stockfish 18 asserted at startup, surfaced in `GetInfo`.

## Parked this cycle
- **`AnnotateGame` (PGN → annotated fact sheet) — skeleton only.** The RPC + `AnnotateGameResp` /
  `AnnotatedPly` shape stay in the contract (lifted from `gamepass`) so the surface is designed, but
  it is **not implemented this cycle** (heavy game-walk, not hot-path; the game-review flow it feeds is
  already ▢ in `orchestrator.md`). Refine the exact fields when the walk is actually ported.

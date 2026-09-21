<p align="center">
  <img src="assets/wordmark.png" width="340" alt="Lucena">
</p>

<h1 align="center">Lucena</h1>

<p align="center">An engine-grounded, Socratic chess coach for understanding the positions you actually play.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-blue" alt="AGPL-3.0-or-later"></a>
  <img src="https://img.shields.io/badge/status-archived%20research%20preview-orange" alt="Archived research preview">
  <img src="https://img.shields.io/badge/client-SwiftUI-F05138" alt="SwiftUI">
  <img src="https://img.shields.io/badge/backend-Python-3776AB" alt="Python">
</p>

> Lucena began as a product attempt and became a useful engineering case study: a full-stack exploration of deterministic chess analysis, probabilistic language models, native macOS software, and reproducible research.

## Project status

Lucena is no longer being developed as a commercial product. The business did not reach a viable model, but the engineering work remains useful for learning, experimentation, and discussion.

The repository is intentionally preserved as an open-source case study in:

- grounding language-model interfaces in deterministic domain facts;
- designing stateful WebSocket applications;
- building a native macOS client around a thin network protocol;
- separating calculation, interpretation, and persistence;
- testing chess logic with adversarial and differential cases;
- using research and measurement to retire ideas that did not validate.

## What Lucena does

Lucena is designed to answer more than “what is the best move?” It aims to help a player understand:

- what the position demanded;
- which plan or tactical mechanism mattered;
- what changed after a move;
- how to recognize the pattern in a future game.

The architecture has a strict calculate–interpret boundary:

```text
Player input
    │
    ▼
Deterministic conversation loop
    ├── board and move validation
    ├── Stockfish analysis
    ├── Maia human-move modelling
    ├── tactical and positional grounding
    └── structured coaching facts
             │
             ▼
      one grounded LLM generation
             │
             ▼
      coaching beats shown to the player
```

The LLM interprets grounded facts. It does not calculate variations, change the board, or mutate application state.

## Architecture

```text
┌──────────────────────┐
│   Native macOS app   │
│       SwiftUI        │
└──────────┬───────────┘
           │ WebSocket + REST
           ▼
┌────────────────────────────────────────┐
│             Python backend             │
│  ConversationLoop · state machine      │
│  coaching · prompts · persistence      │
│  provider-agnostic LLM adapter         │
└──────────────┬───────────────┬─────────┘
               │               │
               ▼               ▼
        ┌────────────┐  ┌──────────────┐
        │ PostgreSQL │  │ LLM provider │
        └────────────┘  └──────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│ Grounding: Stockfish · Maia · board    │
│ truth · tactics · drills · plans       │
└────────────────────────────────────────┘
```

Important design decisions include:

- one bounded LLM generation per coaching turn;
- deterministic state mutation in the backend, never in the model;
- SAN at the product boundary and UCI only inside engine integration;
- versioned WebSocket updates with reconnect-safe command handling;
- relational durable state rather than an opaque session JSON blob;
- honest degradation to deterministic facts when the LLM is unavailable.

See [docs/architecture.md](docs/architecture.md), [docs/backend-api.md](docs/backend-api.md), and [LLD.md](LLD.md).

## Repository map

```text
.
├── backend/          Python application layer and coaching loop
├── engine/           Stockfish and Maia wrapper
├── lucena-core/      Board truth, SEE, positional analysis, and gRPC support
├── lucena-tactics/   Tactical detection, drills, forcing lines, and fact sheets
├── lucena-plans/     Position-to-plan research and verification
├── mac-client/       Native SwiftUI macOS client
├── docs/             Architecture, protocols, and research notes
├── docker/           Container build and licensing support
├── compose.yaml      Local container stack
└── serve.sh          Local development launcher
```

The historical research layers remain valuable, but they are not presented as a claim that every experiment succeeded. The negative results and abandoned directions are part of the project record.

## Experimental research

The most substantial part of Lucena was not the UI. It was the attempt to turn chess plans from plausible-sounding annotations into measurable, falsifiable objects.

The research program asked four questions:

1. Can a detector identify plans in strong human games rather than merely in engine lines?
2. Can plan labels be separated from states, mechanisms, and random geometric coincidences?
3. Can engine and human-move models agree on plans from the same position?
4. Does explaining a plan actually help a player choose a move?

The experiments used 33,769 GM classical games, 311,000 elite online games, 94,289 corpus anchors, 599 human-annotated games, a frozen 4,000-position benchmark, and a smaller 120-position engine/Maia/GM agreement set. Results and scripts are preserved in [`lucena-plans/docs/FINDINGS-2026-07-21.md`](lucena-plans/docs/FINDINGS-2026-07-21.md), [`lucena-plans/research/`](lucena-plans/research/), and the [reading-study log](reading/LOG.md).

### From chess folklore to measurable plans

Each candidate plan was represented as an event-anchored detector over a move sequence: a prepared break, an outpost occupation, a rook activation, a weakness harvest, or a similar observable choreography. A candidate had to beat a seeded-random baseline, survive outcome calibration, and—where used in the product—be verified against engine lines or Maia rollouts from the exact position.

This process produced useful distinctions that are easy to blur in prose:

- **Mechanisms** are vocabulary, such as a rook lift or knight reroute. They are nameable but carry no reliability claim.
- **Plans** are corpus-audited and can carry lift and outcome measurements.
- **Campaigns** are compositions of plans over longer windows, such as promotion, king attack, or conversion.
- **States** are not automatically plans. A weakness or a closed position may be strategically relevant without being an executable recommendation.

### Selected findings

| Question | Evidence | Engineering consequence |
|---|---|---|
| Do plan detectors generalize? | The minority-attack detector found 127 instances in 33,769 GM classical games; a static trajectory filter produced a roughly 42% tactical false-positive rate before engine verification. | Static geometry is a candidate generator, never the final adjudicator. |
| Which plans beat random play? | At 94,289 anchors, fast-horizon lift included `pair_break` 15.66×, `remove_defender` 7.11×, `prepared_break` 3.39×, `rook_activation` 2.58×, and `weakness_harvest` 2.74×. Several ideas were at or below random: `bind_squeeze` 0.33×, `majority_roll` 0.91×, and `rook_lift` 0.91×. | The vocabulary is evidence-weighted; attractive strategic language can be actively misleading. |
| Does the plan horizon matter? | Twelve-ply windows improved specificity for fast plans; 25-ply windows surfaced slow plans but raised the random floor dramatically. | Verification uses per-family horizons rather than one universal rollout length. |
| Can external annotations validate the detectors? | In a phase-matched 599-game validation set, seventh-rank concepts reached 64% versus 14% control, bishop-pair concepts 78%/55% versus 30%/10%, and outposts 33% versus 10%. | External corpora became regression evidence instead of relying on hand-picked examples. |
| Does a campaign add signal? | Across 29,730 GM games, campaign completion rose monotonically from absent to fragment to partial to full; full promotion campaigns moved from 0.458 to 0.626 (+17 percentage points). | Plans compose into a separate campaign layer with a different epistemic contract. |
| How many Maia rollouts are enough? | A convergence study over 300 positions and 3,443 position/plan cells settled at K*=9, where incremental change fell below 0.03. | The production verification contract uses nine gated Maia rollouts rather than an arbitrary sample count. |
| Is “one best plan” a valid representation? | In 120 equal-evaluation middlegame positions, engine lines contained about 3.4 equally plausible plans on average; 55% of GM/engine agreement occurred in PVs 2–4. | The product presents ranked plan candidates instead of pretending every position has one canonical plan. |

Several negative findings were equally important. Rook lifts, bare pawn storms, bind-and-squeeze, majority rolls, and multi-hop knight reroutes either failed the random-floor test or behaved like states/routes rather than plans. The minority attack also turned out to be a broader “two pawns versus three with a semi-open c-file” pattern rather than a Carlsbad-only concept, with materially different outcomes by structure family.

### Grounding and model-behavior experiments

The project also tested whether a language model could narrate a fact sheet without access to the board or engine. In the grounding test, Sonnet produced zero board-fact hallucinations across two rounds and correctly incorporated a newly added fact. Gemini Flash-Lite made two errors in the first round and zero in the second; the result supported the architecture, while also motivating larger-sample evaluation before treating the smaller model as fully reliable. The model is therefore downstream of the fact sheet, not a source of chess truth.

### The reader study: the most important product result

The final research loop measured whether explanations changed move choice. A weak-reader proxy evaluated 400 paired positions from the benchmark, with a 50% decision floor and McNemar tests for paired changes.

The sequence of experiments was deliberately cumulative:

- The shipped plan read produced only **+2.5 percentage points** of lift, not statistically distinguishable from zero (`p=0.32`).
- An explicit piece-class hint produced **+25.9pp** (`p=4.0e-21`); an explicit destination-file hint produced **+22.9pp** (`p=3.3e-16`). The reader could follow direction.
- Reordering, pruning, or reframing plan prose remained null. Even plan attribution that correctly distinguished the best line from the inferior line produced only **+0.6pp** (`p=0.90`).
- The experiment therefore located a sharp abstraction boundary: this reader could use move-level direction, but could not reliably map “rook activation” to “therefore play Re2 rather than h3.”
- A human calibration on 40 positions was directionally consistent: 0.70 cold versus 0.65 with the read, with appropriately wide uncertainty from the small sample. It validated the proxy enough for iteration, but did not replace human research.
- The final production experiment added a recommendation only when the first engine move had a grounded plan witness: **0.679 → 0.842**, or **+18.8pp**. Removing the move returned performance to 0.682, showing that the gain came from the commitment, not from extra plan prose.

That result became a product rule: recommend a move only when the system can explain what the move achieves. If there is no grounded “why,” the system remains Socratic rather than fabricating confidence. The full iteration history, including retractions, null results, and stop conditions, is in [`reading/LOG.md`](reading/LOG.md) and [`reading/LOOP.md`](reading/LOOP.md).

### What this demonstrates technically

The experiments turned the project into more than a chess UI:

- hypotheses were pre-registered informally before variants were run;
- random and phase-matched controls were used to expose detector folklore;
- confidence intervals and paired tests prevented small lifts from becoming product claims;
- banked engine/Maia outputs made grammar changes cheap to re-score;
- negative findings retired entire classes of ideas instead of accumulating prompt patches;
- the final product behavior was changed only after a measurable reader result.

## Quick start

The complete development stack currently targets macOS and requires Python 3.11+, PostgreSQL, Stockfish, and an LLM API key.

```bash
git clone --recursive https://github.com/distressedrook/lucena.git
cd lucena

python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -e engine -e lucena-core -e backend

export GEMINI_API_KEY="your-key"
./serve.sh
```

The development services listen at:

```text
WebSocket: ws://127.0.0.1:8766/ws
REST:      http://127.0.0.1:8766
```

Useful commands:

```bash
./serve.sh status
./serve.sh logs
./serve.sh stop
```

For the container workflow, see [DOCKER.md](DOCKER.md). For the public engine package, see [engine/README.md](engine/README.md).

## Testing

```bash
# Engine
cd engine
pip install -e ".[dev]"
pytest tests/

# Core
cd ../lucena-tactics
.venv/bin/python -m pytest ../lucena-core/tests/

# Tactics
.venv/bin/python -m pytest tests/

# Backend
cd ../backend
PYTHONPATH=python .venv/bin/python -m pytest tests/

# macOS client
cd ../mac-client
xcodebuild -project Lucena.xcodeproj -scheme Lucena \
  -destination 'platform=macOS' CODE_SIGNING_ALLOWED=NO build
```

The test suites cover board legality, adversarial tactical positions, engine protocols, state transitions, coaching handlers, persistence, reconnect semantics, and Swift client reducers/models.

## Contributing

Lucena is open for educational contributions, bug fixes, experiments, and documentation improvements. Start with [CONTRIBUTING.md](CONTRIBUTING.md), then read the relevant layer documentation before changing a contract.

Please include tests for behavioral changes and preserve the calculate–interpret boundary. Research contributions should state the hypothesis, baseline, measurement, and negative results—not only the most favorable output.

## License and third-party software

Lucena is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).

The project invokes or incorporates software with its own terms, including Stockfish, Maia, python-chess, PostgreSQL, SwiftUI, and bundled data sources. Their notices and source obligations remain applicable; see the relevant [third-party notices](engine/THIRD-PARTY-NOTICES.md) and component documentation.

The software is provided “as is,” without warranty. It is a research project, not a substitute for a chess coach or professional advice.

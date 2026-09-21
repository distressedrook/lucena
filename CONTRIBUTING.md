# Contributing to Lucena

Lucena is an archived but living open-source engineering case study. Contributions are welcome when they improve correctness, reproducibility, documentation, accessibility, or the educational value of the project.

## Before opening a change

1. Read the relevant architecture and API documents in `docs/`.
2. Check whether the change crosses a repository boundary.
3. Avoid committing credentials, model outputs containing private data, virtual environments, caches, or generated build artifacts.
4. Add or update focused tests for behavioral changes.

## Engineering constraints

- The engine calculates chess truth; the language model interprets grounded facts.
- The model must not set the board, mutate state, or invent an evaluation.
- Keep UCI internal and use SAN at the product boundary.
- Bound network calls and degrade explicitly when dependencies fail.
- Preserve deterministic behavior where a node limit and fixed configuration make it possible.

## Research contributions

Research changes should document the hypothesis, baseline, dataset, metric, and limitations. Negative or null results are valuable project output and should not be removed merely because they weaken a claim.

## Pull requests

Describe the user-visible or research-level outcome, list validation performed, and call out known limitations. New dependencies must include their license and provenance. By contributing, you agree that your contribution is licensed under the repository's AGPL-3.0-or-later license.

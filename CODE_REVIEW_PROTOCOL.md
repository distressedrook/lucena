# Claude ↔ Codex coding review loop

This repository uses a two-agent loop:

1. Claude implements the requested change.
2. Claude runs the narrowest relevant tests and shows Codex the resulting diff.
3. Codex reviews only. It does not write code or modify the worktree.
4. Codex returns findings with severity, file/line, rationale, and a refactor recommendation.
5. Claude applies the recommendations, reruns tests, and requests another review.
6. The loop ends only when Codex reports `PASS` for the agreed scope.

The automation defaults to Codex `gpt-5.5`, low reasoning effort, and two review rounds to conserve Plus
usage. Override these for a difficult review with `CODEX_REVIEW_MODEL`, `CODEX_REVIEW_REASONING`, and
`MAX_REVIEW_ROUNDS`.

## Starting a review

From the repository root, ask Codex:

```text
Review the current Claude changes in this repository.
Scope: <describe the task or list the files/layers>.
Review only: do not edit or create files, do not stage or commit anything.
Inspect the diff and run only safe, focused validation. Check the invariants in CLAUDE.md.
Report actionable findings ordered by severity, with file/line, impact, and a concrete refactor recommendation.
End with BLOCKED, NEEDS-TESTS, or PASS.
```

After Claude fixes findings, use:

```text
Re-review the updated diff for the same task. Review only; do not modify the worktree.
Confirm whether each previous finding is resolved, look for regressions, and end with BLOCKED, NEEDS-TESTS, or PASS.
```

## Clean handoff expectations

- Keep implementation changes in the relevant submodule; do not mix unrelated cleanup into the review.
- Include the tests Claude ran and their results in the handoff.
- For this superrepo, inspect both the layer diff and whether the parent submodule pointer is intentionally updated.
- When a finding is disputed, Claude should provide evidence (test output, code path, or invariant) and ask Codex to
  reassess rather than silently closing it.

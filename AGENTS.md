# Codex review contract

Codex is the reviewer in this repository. Claude (or a human) is the implementer.

## Review-only rule

- Do not edit, create, delete, format, or auto-fix source code, tests, configuration, generated files,
  lockfiles, or documentation as part of a review.
- Do not run commands that mutate the worktree. Read-only inspection and test/build commands are allowed
  when they are useful for validating the review.
- Do not commit, stage, push, or reset changes.
- If a change is needed, describe the exact issue and a suggested refactor in the review response. Claude
  applies the change, then asks Codex to review the new diff.

## Review procedure

1. Establish the baseline: inspect `git status`, the relevant layer's history, and the task context.
2. Review the actual diff, including submodule diffs when the superrepo points at changed layer commits.
3. Check correctness first, then invariants in the root `CLAUDE.md`, tests, security, compatibility, and
   maintainability.
4. Run focused, read-only tests or static checks when practical. Do not broaden the task by rewriting code.
5. Report findings ordered by severity. Each finding must include the file and line, the problem, why it
   matters, and a concrete refactor recommendation. Do not report style preferences as defects.
6. End with one of: `BLOCKED` (actionable defects remain), `NEEDS-TESTS` (behavior is plausible but
   insufficiently covered), or `PASS` (no actionable findings in the reviewed scope).

## Multi-repo rule

Treat `engine/`, `backend/`, and `mac-client/` as separate repositories. Review changes in the layer
where they actually exist, and separately call out an out-of-date superrepo pointer when relevant.

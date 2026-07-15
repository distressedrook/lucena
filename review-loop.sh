#!/usr/bin/env bash
set -euo pipefail

# Autonomous Claude (implement) -> Codex (review) loop.
# This script never commits or pushes. Run it from a clean branch so the review
# is limited to the change Claude makes for the supplied task.

ROOT="$(cd "$(dirname "$0")" && pwd)"
MAX_ROUNDS="${MAX_REVIEW_ROUNDS:-2}"
CODEX_MODEL="${CODEX_REVIEW_MODEL:-gpt-5.5}"
CODEX_REASONING="${CODEX_REVIEW_REASONING:-low}"
TASK="${*:-}"

if [[ -z "$TASK" ]]; then
  echo "Usage: $0 \"task for Claude to implement\"" >&2
  exit 2
fi

command -v claude >/dev/null || { echo "claude CLI not found" >&2; exit 127; }
command -v codex >/dev/null || { echo "codex CLI not found" >&2; exit 127; }

if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "Worktree is not clean. Commit or stash existing changes before starting." >&2
  git -C "$ROOT" status --short >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/lucena-review.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

IMPLEMENT_PROMPT=$(cat <<EOF
You are the implementation agent for this task in $ROOT.

Task:
$TASK

Implement the task completely. You may edit the relevant files and run focused tests.
Do not commit, stage, push, or reset anything. Respect CLAUDE.md.
EOF
)

echo "== Claude: implementation =="
claude -p --permission-mode acceptEdits "$IMPLEMENT_PROMPT"

for ((round=1; round<=MAX_ROUNDS; round++)); do
  echo
  echo "== Codex: review round $round/$MAX_ROUNDS =="
  REVIEW_PROMPT=$(cat <<EOF
Review the current Claude changes for this task:
$TASK

You are review-only. Do not edit or create files, do not stage or commit, and do not auto-fix.
Use the repository's AGENTS.md review contract. Review the uncommitted diff, run only safe focused
validation if useful, and report actionable findings ordered by severity. Every finding needs a file/line,
impact, and a concrete refactor recommendation. End with exactly one machine-readable line:
VERDICT: BLOCKED, VERDICT: NEEDS-TESTS, or VERDICT: PASS.
EOF
)
  codex exec --sandbox read-only -C "$ROOT" -m "$CODEX_MODEL" \
    -c "model_reasoning_effort=\"$CODEX_REASONING\"" \
    review --uncommitted "$REVIEW_PROMPT" | tee "$TMP/review-$round.txt"

  if grep -Eq '^VERDICT:[[:space:]]*PASS[[:space:]]*$' "$TMP/review-$round.txt"; then
    echo
    echo "Review loop complete: PASS"
    exit 0
  fi

  if (( round == MAX_ROUNDS )); then
    echo "Review loop stopped after $MAX_ROUNDS rounds; Claude must address the latest findings." >&2
    exit 1
  fi

  FINDINGS="$(cat "$TMP/review-$round.txt")"
  echo
  echo "== Claude: fixes for review round $round =="
  CLAUDE_FIX_PROMPT=$(cat <<EOF
Rework the implementation for the same task:
$TASK

Codex's latest review is below. Apply only the necessary fixes, add or update focused tests where needed,
and rerun relevant tests. You are the implementation agent: you may edit files, but do not commit, stage,
push, or reset anything.

--- Codex review ---
$FINDINGS
--- end review ---
EOF
  )
  claude -p --permission-mode acceptEdits "$CLAUDE_FIX_PROMPT"
done

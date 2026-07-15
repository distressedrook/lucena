#!/usr/bin/env bash
set -euo pipefail

# Autonomous Claude (implement) -> Codex (review) loop.
# This script never commits or pushes. Run it from a clean branch so the review
# is limited to the change Claude makes for the supplied task.
#
#   ./review-loop.sh "task for Claude to implement"
#   REVIEW_ONLY=1 ./review-loop.sh "describe the change already in the worktree"
#
# Env:
#   MAX_REVIEW_ROUNDS=2    review rounds before giving up
#   CODEX_REVIEW_MODEL     model for the reviewer
#   CODEX_REVIEW_REASONING reasoning effort for the reviewer
#   REVIEW_ONLY=1          skip the implement step and review what is already in the worktree
#                          (implies a dirty worktree, so the clean check is skipped)
#   ALLOW_DIRTY=1          do not require a clean worktree before implementing
#   CONTEXT_FILE=path      extra context (a plan, a design doc) appended to the Claude prompts.
#                          Without it, claude -p starts cold, knowing only the task string.
#   REVIEW_DIR=path        repo/layer to review (default: ROOT). AGENTS.md says review a change in
#                          the layer where it actually lives, e.g. REVIEW_DIR=backend.

ROOT="$(cd "$(dirname "$0")" && pwd)"
MAX_ROUNDS="${MAX_REVIEW_ROUNDS:-2}"
CODEX_MODEL="${CODEX_REVIEW_MODEL:-gpt-5.5}"
CODEX_REASONING="${CODEX_REVIEW_REASONING:-low}"
REVIEW_ONLY="${REVIEW_ONLY:-0}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"
CONTEXT_FILE="${CONTEXT_FILE:-}"
REVIEW_DIR="${REVIEW_DIR:-$ROOT}"
TASK="${*:-}"

if [[ -z "$TASK" ]]; then
  echo "Usage: $0 \"task for Claude to implement\"" >&2
  echo "       REVIEW_ONLY=1 $0 \"describe the change already in the worktree\"" >&2
  exit 2
fi

command -v codex >/dev/null || { echo "codex CLI not found" >&2; exit 127; }
[[ "$REVIEW_ONLY" == "1" ]] || command -v claude >/dev/null || { echo "claude CLI not found" >&2; exit 127; }

REVIEW_DIR="$(cd "$REVIEW_DIR" && pwd)"

CONTEXT=""
if [[ -n "$CONTEXT_FILE" ]]; then
  [[ -r "$CONTEXT_FILE" ]] || { echo "CONTEXT_FILE not readable: $CONTEXT_FILE" >&2; exit 2; }
  CONTEXT=$'\n\n--- Context ---\n'"$(cat "$CONTEXT_FILE")"$'\n--- end context ---'
fi

# REVIEW_ONLY reviews what is already in the worktree, so a dirty tree is the whole point.
if [[ "$REVIEW_ONLY" != "1" && "$ALLOW_DIRTY" != "1" ]]; then
  if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
    echo "Worktree is not clean. Commit or stash existing changes before starting," >&2
    echo "or pass ALLOW_DIRTY=1 (implement anyway) / REVIEW_ONLY=1 (review what is here)." >&2
    git -C "$ROOT" status --short >&2
    exit 1
  fi
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/lucena-review.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

if [[ "$REVIEW_ONLY" == "1" ]]; then
  echo "== Claude: implementation SKIPPED (REVIEW_ONLY=1); reviewing the current worktree =="
else
  IMPLEMENT_PROMPT=$(cat <<EOF
You are the implementation agent for this task in $ROOT.

Task:
$TASK

Implement the task completely. You may edit the relevant files and run focused tests.
Do not commit, stage, push, or reset anything. Respect CLAUDE.md.$CONTEXT
EOF
)

  echo "== Claude: implementation =="
  claude -p --permission-mode acceptEdits "$IMPLEMENT_PROMPT"
fi

for ((round=1; round<=MAX_ROUNDS; round++)); do
  echo
  echo "== Codex: review round $round/$MAX_ROUNDS =="
  REVIEW_PROMPT=$(cat <<EOF
Review the current Claude changes for this task:
$TASK

Inspect the uncommitted diff yourself: run \`git status --short\` and \`git diff\`, and read any new
untracked files. Include submodule diffs when the superrepo points at changed layer commits.

You are review-only. Do not edit or create files, do not stage or commit, and do not auto-fix.
Use the AGENTS.md review contract in this repo. Run only safe focused validation if useful, and
report actionable findings ordered by severity. Every finding needs a file/line, impact, and a
concrete refactor recommendation. Do not report style preferences as defects.
End with exactly one machine-readable line:
VERDICT: BLOCKED, VERDICT: NEEDS-TESTS, or VERDICT: PASS.$CONTEXT
EOF
)
  # NOTE: this is deliberately plain "codex exec", NOT "codex exec review --uncommitted PROMPT".
  # codex-cli rejects that combination: the --uncommitted flag cannot be used together with a
  # PROMPT argument (the stdin form with - hits the same error, since - counts as a PROMPT).
  # The exit condition of this loop depends on our own prompt (the VERDICT line), so we cannot drop
  # prompt to keep the flag. Instead the reviewer is told to scope itself to the uncommitted diff,
  # which is what CODE_REVIEW_PROTOCOL.md documents anyway.
  #
  # </dev/null is REQUIRED: when a prompt is passed as an argument AND stdin is not a TTY, codex
  # appends stdin as a <stdin> block and blocks waiting for EOF. Without this the loop hangs
  # forever anywhere stdin is piped or detached (tmux send-keys, CI, nohup).
  codex exec --sandbox read-only -C "$REVIEW_DIR" -m "$CODEX_MODEL" \
    -c "model_reasoning_effort=\"$CODEX_REASONING\"" \
    "$REVIEW_PROMPT" </dev/null | tee "$TMP/review-$round.txt"

  if grep -Eq '^VERDICT:[[:space:]]*PASS[[:space:]]*$' "$TMP/review-$round.txt"; then
    echo
    echo "Review loop complete: PASS"
    exit 0
  fi

  if (( round == MAX_ROUNDS )); then
    echo "Review loop stopped after $MAX_ROUNDS rounds; Claude must address the latest findings." >&2
    exit 1
  fi

  if [[ "$REVIEW_ONLY" == "1" ]]; then
    echo "REVIEW_ONLY=1: not PASS, and there is no implement step to apply fixes. Stopping." >&2
    exit 1
  fi

  FINDINGS="$(cat "$TMP/review-$round.txt")"
  echo
  echo "== Claude: fixes for review round $round =="
  CLAUDE_FIX_PROMPT=$(cat <<EOF
Rework the implementation for the same task:
$TASK

The latest Codex review is below. Apply only the necessary fixes, add or update focused tests where needed,
and rerun relevant tests. You are the implementation agent: you may edit files, but do not commit, stage,
push, or reset anything.

If you believe a finding is wrong, do not silently ignore it: per CODE_REVIEW_PROTOCOL.md, say so and
give evidence (test output, the code path, or the CLAUDE.md invariant) so it can be reassessed.

--- Codex review ---
$FINDINGS
--- end review ---$CONTEXT
EOF
  )
  claude -p --permission-mode acceptEdits "$CLAUDE_FIX_PROMPT"
done

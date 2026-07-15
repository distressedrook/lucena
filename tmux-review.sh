#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SESSION="${LUCENA_REVIEW_SESSION:-lucena-review}"
TASK="${*:-}"

if [[ -z "$TASK" ]]; then
  echo "Usage: $0 \"task for Claude to implement\"" >&2
  exit 2
fi
command -v tmux >/dev/null || { echo "tmux not found" >&2; exit 127; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists. Attach with: tmux attach -t $SESSION" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" -c "$ROOT"
tmux rename-window -t "$SESSION":0 review-loop
tmux split-window -h -t "$SESSION":0 -c "$ROOT"
tmux select-pane -t "$SESSION":0.0

# Keep the second pane available for read-only inspection while the controller
# runs Claude and Codex sequentially in the first pane.
tmux send-keys -t "$SESSION":0.1 'echo "Inspection pane: use read-only commands here; do not edit during the loop."' C-m

printf -v quoted_task '%q' "$TASK"
tmux send-keys -t "$SESSION":0.0 "./review-loop.sh $quoted_task" C-m

echo "Started tmux session '$SESSION'."
echo "Attach: tmux attach -t $SESSION"
echo "Stop:   tmux kill-session -t $SESSION"

"""Sibling-repo bootstrap for lucena-tactics — the server-side twin of the
backend's grounding_tools/_tactics_path.py.

The gRPC server is deployment composition, not a library: it serves the
tactical layer (facts / hints / brilliant) over the wire, and the tactical
layer lives above lucena_core in the dependency order. A runtime sys.path
reach-up here keeps the package graph acyclic (core never *depends* on
tactics; only the server process composes both). Append, never prepend;
LUCENA_TACTICS_DIR overrides.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure() -> None:
    tactics_dir = Path(os.environ.get(
        "LUCENA_TACTICS_DIR",
        str(Path(__file__).resolve().parents[4] / "lucena-tactics")))
    src = str(tactics_dir / "src")
    if src not in sys.path:
        sys.path.append(src)

# Lucena multi-repo layout

> `gh` may be authed as a work account (`avismara-c`). For any GitHub action, switch to the
> `distressedrook` personal account first (`gh auth switch --user distressedrook`). SSH pushes already
> use the pinned `~/.ssh/id_ed25519` (distressedrook) key.


One private **superrepo** (`lucena`) with three submodules — each layer its own repo, one clonable thing:

```
lucena/            PUBLIC superrepo — pins each layer's commit; shared ops (serve.sh, docs)
├── engine/        → lucena-engine   PUBLIC  (AGPL-3.0)   — the open release
├── backend/       → lucena-backend  PRIVATE (proprietary)
└── mac-client/    → lucena-mac      PRIVATE (proprietary)
```

## Clone / bootstrap
```
git clone --recursive git@github.com:<owner>/lucena.git
cd lucena
python3.13 -m venv backend/.venv
backend/.venv/bin/pip install -e ./engine -e ./backend    # in-process link, relative path
```

## Working with Claude (single session, all layers)
Launch Claude Code in the superrepo root. It edits across `engine/`, `backend/`, `mac-client/` in one
session exactly as before — the filesystem is one tree. Only git is split:

- Commit a layer: `git -C engine commit ...` (each submodule is its own repo, own history).
- After committing a submodule, **bump the pointer** in the superrepo:
  `git -C <root> add engine && git -C <root> commit -m "bump engine"` — this records which engine
  commit goes with this backend/mac state (reproducible pinning).
- Push: `git -C engine push`, then `git -C . push` for the pointer.

## The component and licensing boundaries
- `engine` is AGPL-3.0 and public; you dual-license it (AGPL to the world, proprietary use by you as
  sole author — see `engine/NOTICE`, `engine/CONTRIBUTING.md` CLA).
- The GPL-hygiene gate (`engine/tests/test_gpl_hygiene.py`) keeps python-chess out of the shipped
  library. Stockfish/Maia stay subprocesses.
- Keep the superrepo **private** — a public superrepo can't `--recursive` a private submodule and
  would leak the private repos' URLs.

## Distribution reminders (when shipping the app / hosting)
- Bundle `engine/LICENSE` + `NOTICE` + `THIRD-PARTY-NOTICES.md` and a Stockfish GPL source offer in
  the app's acknowledgements screen.
- Hosted tier: expose the engine source (link to `lucena-engine`) for AGPL §13.

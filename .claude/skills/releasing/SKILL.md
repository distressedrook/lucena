---
name: releasing
description: How to release Lucena — the pre-production gate in RELEASE_CHECKLIST.md (including the no-migration-mechanism blocker), publishing the engine to PyPI (version bump, tag, Trusted Publishing), and the AGPL licensing rules for contributions. Use when cutting a release, publishing lucena-engine, tagging a version, or asking what blocks the first production deploy.
---

# Releasing

- **`RELEASE_CHECKLIST.md` gates the first production deploy** — what's deliberately deferred while
  pre-production. Blocking one: **there is no migration mechanism**, so a schema change reaches fresh
  schemas only and means recreating the dev DB.

- **Engine → PyPI:** bump `engine/pyproject.toml`, tag `vX.Y.Z`, push the tag — CI builds wheels + sdist
  and publishes via Trusted Publishing. Same version can't be re-uploaded; bump on a failed run.
- Lucena components are released under AGPL-3.0-or-later. Contributors follow
  (`engine/CONTRIBUTING.md`) and do not need a proprietary relicensing CLA.

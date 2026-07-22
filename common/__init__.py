"""common — shared packages used by more than one Lucena repo.

Lives directly in the superrepo (not a submodule) and is now itself a
proper Python package (2026-07-22): consumers append the SUPERREPO ROOT to
sys.path (not this directory) and import `common.<package>`, e.g.
`from common.engine_client import Probes` — this is what lets a future
`common.<anything else>` resolve the same way, instead of every new shared
package needing its own bespoke sys.path entry.
"""

import importlib, pkgutil, sys, os
import lucena_backend, lucena_backend.httpserver
# force known lazy imports referenced inside functions
for m in ["lucena_backend.persistence.sessions","lucena_backend.coaching.loop",
          "lucena_backend.coaching.freeform","lucena_backend.coaching.coach",
          "lucena_backend.coaching.mode_prompts","lucena_backend.coaching.prompts",
          "lucena_backend.coaching.book_voice","lucena_backend.coaching.strategies",
          "lucena_backend.coaching.library","lucena_backend.coaching.lesson_store",
          "lucena_backend.grounding_tools.live_analysis","lucena_backend.grounding_tools.drill",
          "lucena_backend.grounding_tools.drill_feedback","lucena_backend.grounding_tools.puzzle_content"]:
    try: importlib.import_module(m)
    except Exception as e: print("IMPORT FAIL", m, e)
loaded={m.__file__ for n,m in sys.modules.items() if n.startswith("lucena_backend") and getattr(m,"__file__",None)}
root=os.path.dirname(lucena_backend.__file__)
allpy=set()
for dp,_,fs in os.walk(root):
    if "_pb" in dp or "egg-info" in dp or "__pycache__" in dp: continue
    for f in fs:
        if f.endswith(".py") and f!="__init__.py": allpy.add(os.path.join(dp,f))
print("\n=== .py files NOT loaded by the live app (dead-code candidates) ===")
for p in sorted(allpy-loaded):
    print("  ", os.path.relpath(p, root))

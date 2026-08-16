# Maya Sanity Check Framework

A scene-validation framework for Maya: independent, self-contained checks (topology, UVs, pivots, construction history, naming, keyframes...) run before export to catch problems early, with a PySide UI to review, ignore, or auto-fix each one.

### What's here

| Class | Role | Notable technical points |
|---|---|---|
| `SanityCheck` | Base class every rule implements | Common `run()` / `fix()` / `ignore()` / `reset()` interface, so the manager and UI never need to know what a specific check actually inspects |
| 16 check subclasses (`NonManifoldCheck`, `NgonsCheck`, `PivotToOriginCheck`, `UvsCheck`, `KeyframesCheck`, `LockedAttributesCheck`, `UniqueObjectNamesCheck`, `SceneSavedCheck`...) | One rule each | Several implement `fix()` for one-click auto-repair (e.g. `SceneSavedCheck` triggers a save), not just detection |
| `SanityCheckManager` | Runs every check, aggregates results by category (Scene / Modeling) | Exposes `has_blocking_failures()` so a caller - an exporter, for instance - can gate on it without knowing which specific checks exist |
| `SanityCheckWidget` / `SanityCheckDetailsDialog` | PySide UI | Pass/fail/warning list with per-check ignore/fix actions and a detailed report dialog |

Originally built to gate the export button in a USD Model Exporter (see [usd-maya-exporters](https://github.com/arthurJusteau/usd-maya-exporters)), but the framework itself has nothing USD-specific about it - it's a general scene-validation pattern.

### Setup
```python
from sanity_check import SanityCheckManager, SanityCheckWidget

manager = SanityCheckManager()
manager.set_output_groups(my_output_groups)
results = manager.run_all_checks()
```

Requires Python with PySide2 or PySide6 (auto-detected), running inside Maya (`maya.cmds`).

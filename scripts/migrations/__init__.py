"""Migrations: one module per change of layout, `scripts/migrations/NNNN_slug.py`.

Each module defines
    ID    = "NNNN-slug"          # unique; runs in ascending order
    TITLE = "one line for the update plan"
    def plan(ctx) -> list[Step]   # ctx: tool, tier, config_dir, home, kit_root, entry, Step, plan_file, backup_path

An empty plan means the migration does not apply, so the check and the work cannot disagree. plan()
must not write anything: test_update.py hashes HOME and the clone around every plan. Once its work is
done, plan() returns no writing step. Writes go through install.apply and its backups; besides the
file kinds, a step may be `move` (argv = [new path]), `delete` or `git` (argv after `git -C <dest>`),
each with its kind as its status. Any of them makes the apply need the printed `--plan <id>`, and a
step that fails leaves its migration out of `migrations_applied`.

An install runs every ID not in its own `migrations_applied` (set membership, not a version range), so
an install adopted at an unknown version still gets each one.

STARTER_TEST_MIGRATIONS names one more folder of migrations. Only the tests set it, so the test-only
migration in scripts/tests/fixtures/migrations never ships as a real step.
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

NAME = re.compile(r"\d{4}_[a-z0-9_]+\.py")
TEST_DIR_ENV = "STARTER_TEST_MIGRATIONS"


def discover(shipped: Path) -> list:
    """Every migration module, sorted by ID. Raises ValueError on a duplicate or malformed one."""
    dirs = [shipped] + ([Path(os.environ[TEST_DIR_ENV])] if os.environ.get(TEST_DIR_ENV) else [])
    mods = []
    for d in dirs:
        for p in sorted(d.glob("*.py")) if d.is_dir() else []:
            if not NAME.fullmatch(p.name):
                continue
            spec = importlib.util.spec_from_file_location(f"starter_migration_{p.stem}", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for attr in ("ID", "TITLE", "plan"):
                if not hasattr(mod, attr):
                    raise ValueError(f"{p}: migration has no {attr}")
            if not str(mod.ID).startswith(p.name[:4]):
                raise ValueError(f"{p}: ID {mod.ID!r} does not start with the file's number")
            mods.append(mod)
    ids = [m.ID for m in mods]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate migration IDs: {', '.join(dupes)}")
    return sorted(mods, key=lambda m: m.ID)

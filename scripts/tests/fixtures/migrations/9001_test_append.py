"""Test-only migration: appends one line to <config_dir>/starter-migration-test.txt. It lives under
scripts/tests/fixtures, so it runs only when the tests point STARTER_TEST_MIGRATIONS here."""
ID = "9001-test-append"
TITLE = "test only: append a line to starter-migration-test.txt"
LINE = b"migrated by 9001-test-append\n"


def plan(ctx):
    dest = ctx.config_dir / "starter-migration-test.txt"
    have = dest.read_bytes() if dest.is_file() else b""
    if LINE in have:
        return []
    s = ctx.Step("migration 9001 test file", dest, "file", payload=have + LINE)
    s.status = "update" if dest.exists() else "create"
    return [s]

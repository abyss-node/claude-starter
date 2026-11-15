"""Test-only migration with a `git` step: sets starter.migrated = 9002 in <home>/mig-repo's git config.
It lives under scripts/tests/fixtures, so it runs only when a test points STARTER_TEST_MIGRATIONS here.
STARTER_TEST_GIT_VERB replaces `config`, so a test can make the step fail."""
import os
import subprocess

ID = "9002-test-git"
TITLE = "test only: set starter.migrated in mig-repo's git config"


def plan(ctx):
    repo = ctx.home / "mig-repo"
    if not (repo / ".git").is_dir():
        return []
    r = subprocess.run(["git", "-C", str(repo), "config", "--get", "starter.migrated"], capture_output=True)
    if r.stdout.decode("utf-8", "replace").strip() == "9002":
        return []
    verb = os.environ.get("STARTER_TEST_GIT_VERB", "config")
    return [ctx.Step("migration 9002 git config", repo, "git", status="git",
                     detail=f"git {verb} starter.migrated 9002", argv=[verb, "starter.migrated", "9002"])]

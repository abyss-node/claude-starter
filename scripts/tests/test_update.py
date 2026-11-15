"""The install record, --update against a local bare remote, migrations, the launcher and the update
notice. Every run uses a throwaway HOME and a scratch clone of this working tree; nothing touches the
real ~/.agents, ~/.codex, ~/.claude or ~/.config."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
TEST_MIGRATIONS = Path(__file__).resolve().parent / "fixtures" / "migrations"
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
TRAILER = "\n\nVerified: test fixture -> n/a\nUnverified: none"
STOP = ("If you are an AI agent: stop here. Show the user this plan and end your turn. Apply it only after "
        "they reply yes.")


# No global or system git config, here and in every run: a real autocrlf would check files out with
# CRLF that the scratch runs, which read no global config, then see as modified.
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git(cwd, *a, check=True):
    r = subprocess.run(["git", *GIT_ID, "-C", str(cwd), *a], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, env=GIT_ENV)
    assert r.returncode == 0 or not check, r.stdout + r.stderr
    return r.stdout.strip()


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    """This working tree, committed as v0.4.0 in a scratch repo."""
    root = tmp_path_factory.mktemp("upd-src") / "src"
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    for rel in filter(None, files):
        p = REPO / rel
        if p.is_file() and not rel.startswith("tmp/"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, root / rel)
    if not (root / "kit.json").exists():
        (root / "kit.json").write_text('{"name": "claude-starter", "version": "0.4.0"}\n', encoding="utf-8")
    git(root.parent, "init", "-q", "-b", "main", str(root))
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-gpg-sign", "-m", "v0.4.0" + TRAILER)
    git(root, "tag", "v0.4.0")
    return root


def clean_env(home: Path) -> dict:
    drop = ("CODEX_", "OPENCODE_CONFIG_DIR", "COPILOT_HOME", "CURSOR_CONFIG_DIR", "COMMIT_GUARD", "CLAUDECODE",
            "STARTER_TEST_MIGRATIONS")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               CLAUDE_CONFIG_DIR=str(home / ".claude"), CODEX_HOME=str(home / ".codex"),
               COMMIT_GUARD_DIR=str(home / "guard-data"), TEMP=str(home.parent), TMP=str(home.parent),
               PYTHONIOENCODING="utf-8", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def run(k, *a, script="install.py", extra=None):
    env = dict(k.env, **(extra or {}))
    return subprocess.run([sys.executable, str(k.kit / "scripts" / script), *a], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=600)


@pytest.fixture
def k(src, tmp_path):
    """A clone of a bare remote of `src`, installed for codex (starter tier, no guard)."""
    home = tmp_path / "home"
    home.mkdir()
    bare, kit = tmp_path / "remote.git", tmp_path / "kit"
    git(tmp_path, "clone", "-q", "--bare", str(src), str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(kit))
    ns = SimpleNamespace(kit=kit, bare=bare, home=home, env=clean_env(home), tmp=tmp_path)
    r = run(ns, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    return ns


def record(k) -> dict:
    return json.loads((k.home / ".agents" / "starter" / "installs.json").read_text(encoding="utf-8"))


def release(k, version: str, line: str = "Updated text.", edit=None) -> str:
    """Push a newer tagged release to the bare remote: one changed skill, kit.json and a CHANGELOG entry,
    plus whatever `edit(work_tree)` changes."""
    work = k.tmp / f"work-{version}"
    git(k.tmp, "clone", "-q", str(k.bare), str(work))
    if edit:
        edit(work)
    skill = work / "adapters" / "codex" / "skills" / "checkpoint" / "SKILL.md"
    skill.write_bytes(skill.read_bytes() + f"\n{line}\n".encode())
    (work / "kit.json").write_text(json.dumps({"name": "claude-starter", "version": version}) + "\n",
                                   encoding="utf-8")
    log = work / "CHANGELOG.md"
    old = log.read_text(encoding="utf-8") if log.exists() else "# Changelog\n"
    log.write_text(old.replace("# Changelog\n", f"# Changelog\n\n## v{version}\n\n- {line}\n", 1)
                   if "# Changelog\n" in old else f"## v{version}\n\n- {line}\n\n" + old, encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "--no-gpg-sign", "-m", f"v{version}" + TRAILER)
    git(work, "tag", f"v{version}")
    git(work, "push", "-q", "origin", "HEAD:main", "--tags")
    return git(work, "rev-parse", "HEAD")


def state(k) -> dict:
    """HOME, the clone's files and HEAD: everything a plan must leave alone (fetched refs excepted)."""
    out = {"HEAD": git(k.kit, "rev-parse", "HEAD"), "status": git(k.kit, "status", "--porcelain")}
    for base, skip in ((k.home, None), (k.kit, ".git")):
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base)
            if skip and rel.parts[0] == skip:
                continue
            out[f"{base.name}/{rel.as_posix()}"] = p.read_bytes() if p.is_file() else None
    return out


def plan_id(stdout: str) -> str:
    m = re.search(r"^claude-starter update, plan ([0-9a-f]{16}):", stdout, re.M)
    assert m, stdout[-3000:]
    return m.group(1)


# ---- the record --------------------------------------------------------------------------------

def test_fresh_install_writes_the_record(k):
    rec = record(k)
    assert rec["schema"] == 1 and rec["plan"] is None and rec["onboarded_at"] is None and rec["scope"] is None
    assert rec["notices"] == {"update": None}
    assert Path(rec["kit"]["kit_root"]) == k.kit and rec["kit"]["version"] == "0.4.0"
    assert rec["kit"]["sha"] == git(k.kit, "rev-parse", "HEAD") and Path(rec["kit"]["remote"]) == k.bare
    (entry,) = rec["installs"]
    assert entry["tool"] == "codex" and entry["tier"] == "starter" and not entry["adopted"]
    assert entry["options"]["guard"] == {"state": "declined", "repos": []}
    skill = str(k.home / ".agents" / "skills" / "checkpoint" / "SKILL.md")
    assert len(entry["files"][skill]) == 64


def test_install_for_you_asks_about_update_notices(k):
    r = run(k, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0
    tail = r.stdout.split("=== For you (the person at the keyboard) ===", 1)[1]
    assert "Update notices: choose" in tail and "starter.py" in tail and "notices on" in tail
    assert "notices off" in tail


def test_second_install_from_another_clone_exits_2(k, src, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(k.bare), str(other))
    before = state(k)
    r = subprocess.run([sys.executable, str(other / "scripts" / "install.py"), "--tool", "codex", "--tier",
                        "starter", "--yes", "--no-guard"], env=k.env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=300)
    assert r.returncode == 2 and str(k.kit) in r.stderr, r.stderr
    assert state(k) == before


# ---- --update ----------------------------------------------------------------------------------

def test_offline_update_is_a_no_op(k):
    before = state(k)
    r = run(k, "--update", "--offline")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert "Nothing to update" in r.stdout
    assert state(k) == before


def test_newer_tag_plan_then_apply_then_nothing(k):
    sha = release(k, "0.4.1")
    before = state(k)
    r = run(k, "update", script="starter.py")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert state(k) == before, "planning wrote something"
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[-1] == STOP  # the stop line is last, so nothing after it can carry --yes
    pid = plan_id(r.stdout)
    pinned = [ln for ln in lines if "--plan " + pid in ln]
    assert len(pinned) == 2 and all(f"--to {sha}" in ln and "starter.py" in ln for ln in pinned)
    assert "## v0.4.1" in r.stdout and "checkpoint" in r.stdout and "BACKUP+REPLACE" in r.stdout

    r = run(k, "update", "--yes", "--to", sha, "--plan", pid, script="starter.py")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert git(k.kit, "rev-parse", "HEAD") == sha
    assert record(k)["kit"]["version"] == "0.4.1" and record(k)["kit"]["sha"] == sha
    skill = k.home / ".agents" / "skills" / "checkpoint" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").rstrip().endswith("Updated text.")
    assert list(skill.parent.glob("SKILL.md.bak-*"))

    after = state(k)
    r = run(k, "--update")
    assert r.returncode == 0 and "Nothing to update" in r.stdout, r.stdout[-3000:] + r.stderr
    assert state(k) == after, "a second update wrote something"


def test_plan_drift_is_refused(k):
    sha = release(k, "0.4.1")
    pid = plan_id(run(k, "--update").stdout)
    agent = k.home / ".codex" / "agents" / "verifier.toml"
    agent.write_bytes(agent.read_bytes() + b"\n# my edit\n")
    before = state(k)
    r = run(k, "--update", "--yes", "--to", sha, "--plan", pid)
    assert r.returncode == 2 and "plan changed" in r.stderr, r.stdout[-2000:] + r.stderr
    assert state(k) == before and git(k.kit, "rev-parse", "HEAD") != sha


def test_update_yes_without_the_pin_exits_2(k):
    sha = release(k, "0.4.1")
    before = state(k)
    r = run(k, "--update", "--yes")
    assert r.returncode == 2 and "--to <sha> --plan <id>" in r.stderr, r.stdout[-2000:] + r.stderr
    assert state(k) == before and git(k.kit, "rev-parse", "HEAD") != sha


def test_failed_fetch_exits_3_writing_nothing(k):
    git(k.kit, "remote", "set-url", "origin", str(k.tmp / "no-such-remote.git"))
    before = state(k)
    r = run(k, "--update")
    assert r.returncode == 3, r.stdout[-2000:] + r.stderr
    assert "CANNOT FETCH; nothing was written" in r.stderr and "starter.py" in r.stderr
    assert state(k) == before


@pytest.mark.skipif(not shutil.which("icacls"), reason="needs Windows icacls")
def test_unwritable_record_dir_exits_3_writing_nothing(k):
    rdir = k.home / ".agents" / "starter"
    deny = subprocess.run(["icacls", str(rdir), "/deny", "*S-1-1-0:(WD,AD)"], capture_output=True)
    assert deny.returncode == 0
    try:
        before = state(k)
        r = run(k, "--update", "--offline", extra={"CODEX_THREAD_ID": "x"})
        after = state(k)
    finally:
        subprocess.run(["icacls", str(rdir), "/remove:d", "*S-1-1-0"], capture_output=True)
    assert r.returncode == 3, r.stdout[-2000:] + r.stderr
    assert "CANNOT WRITE" in r.stderr and "Codex sandbox" in r.stderr and after == before


# ---- migrations --------------------------------------------------------------------------------

MIG = {"STARTER_TEST_MIGRATIONS": str(TEST_MIGRATIONS)}


def test_plain_yes_over_a_migration_exits_2_then_the_pinned_apply_runs_it_once(k):
    before = state(k)
    r = run(k, "--update", "--offline", "--yes", extra=MIG)
    assert r.returncode == 2 and "--plan <id>" in r.stderr, r.stdout[-2000:] + r.stderr
    assert state(k) == before
    plan = run(k, "--update", "--offline", extra=MIG)
    assert plan.returncode == 0 and "9001-test-append" in plan.stdout, plan.stdout[-2000:] + plan.stderr
    assert state(k) == before, "planning a migration wrote something"
    r = run(k, "--update", "--offline", "--yes", "--to", git(k.kit, "rev-parse", "HEAD"), "--plan",
            plan_id(plan.stdout), extra=MIG)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    test_file = k.home / ".codex" / "starter-migration-test.txt"
    assert test_file.read_bytes().count(b"migrated by 9001-test-append") == 1
    assert "9001-test-append" in record(k)["installs"][0]["migrations_applied"]
    # Re-plan after apply: no writing step, from the whole update or from the migration's own plan().
    after = state(k)
    r = run(k, "--update", "--offline", extra=MIG)
    assert r.returncode == 0 and "Nothing to update" in r.stdout, r.stdout[-3000:]
    assert state(k) == after
    sys.path.insert(0, str(SCRIPTS))
    import migrations
    os.environ["STARTER_TEST_MIGRATIONS"] = str(TEST_MIGRATIONS)
    try:
        mods = migrations.discover(SCRIPTS / "migrations")
    finally:
        del os.environ["STARTER_TEST_MIGRATIONS"]
    ctx = SimpleNamespace(config_dir=k.home / ".codex", Step=__import__("install").Step)
    for m in mods:
        assert not [s for s in m.plan(ctx) if s.status in ("create", "update", "merge", "delete", "move")], m.ID


def test_shipped_migrations_never_include_the_test_one():
    sys.path.insert(0, str(SCRIPTS))
    import migrations
    env = os.environ.pop("STARTER_TEST_MIGRATIONS", None)
    try:
        ids = [m.ID for m in migrations.discover(SCRIPTS / "migrations")]
    finally:
        if env is not None:
            os.environ["STARTER_TEST_MIGRATIONS"] = env
    assert "9001-test-append" not in ids


# ---- adoption ----------------------------------------------------------------------------------

def test_install_without_a_record_is_adopted(k):
    (k.home / ".agents" / "starter" / "installs.json").unlink()
    r = run(k, "--update", "--offline")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr
    assert re.search(r"adopted: codex at .*\.codex \(tier starter", r.stdout), r.stdout[-2000:]
    assert r.stdout.rstrip("\n").split("\n")[-1] == STOP


# ---- the launcher ------------------------------------------------------------------------------

def test_launcher_passes_child_exit_codes(k):
    assert run(k, "update", "--yes", script="starter.py", extra=MIG).returncode == 2
    assert run(k, "nonsense", script="starter.py").returncode == 2
    r = run(k, "status", script="starter.py")
    assert r.returncode == 0 and "codex" in r.stdout and "update notices: never asked" in r.stdout


@pytest.mark.parametrize("name", ["starter.py", "install.py", "update_check.py"])
def test_no_exec_replaces_the_process(name):
    """os.exec* on Windows returns exit 0 to the caller before the child finishes (bpo-19124)."""
    tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
    bad = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr.startswith(("exec", "spawn"))
           and isinstance(n.value, ast.Name) and n.value.id == "os"]
    assert not bad, f"{name}: os.exec*/spawn* at lines {bad}"


# ---- the update notice -------------------------------------------------------------------------

def notice(k):
    r = run(k, script="update_check.py")
    assert r.returncode == 0 and not r.stderr, r.stderr
    return r.stdout


def test_notice_is_silent_until_turned_on_and_without_a_record(k):
    release(k, "0.4.1")
    assert notice(k) == ""
    assert run(k, "notices", "off", script="starter.py").returncode == 0
    assert notice(k) == ""
    (k.home / ".agents" / "starter" / "installs.json").unlink()
    assert notice(k) == ""


def test_notice_prints_exactly_one_line_for_a_newer_tag(k):
    assert run(k, "notices", "on", script="starter.py").returncode == 0
    assert notice(k) == ""  # no newer tag yet
    (k.home / ".agents" / "starter" / "update-check.json").unlink()
    release(k, "0.4.1")
    assert notice(k) == ("claude-starter v0.4.1 is available (you have v0.4.0). Ask your agent to run "
                         "starter-update to see what changed.\n")
    assert git(k.kit, "tag", "--list", "v0.4.1") == "", "the notice fetched into the clone"


def test_notice_uses_a_fresh_cache_and_is_silent_offline(k):
    assert run(k, "notices", "on", script="starter.py").returncode == 0
    rec = record(k)
    rec["kit"]["remote"] = str(k.tmp / "no-such-remote.git")
    (k.home / ".agents" / "starter" / "installs.json").write_text(json.dumps(rec), encoding="utf-8")
    t0 = time.time()
    assert notice(k) == ""  # offline: silent, exit 0
    assert time.time() - t0 < 10
    cache = k.home / ".agents" / "starter" / "update-check.json"
    cache.write_text(json.dumps({"checked_at": time.time(), "remote": rec["kit"]["remote"], "newest": "9.9.9"}),
                     encoding="utf-8")
    assert "v9.9.9 is available" in notice(k)
    cache.write_text(json.dumps({"checked_at": time.time() - 2 * 86400, "remote": rec["kit"]["remote"],
                                 "newest": "9.9.9"}), encoding="utf-8")
    assert notice(k) == ""  # a stale cache is re-checked, and the remote is unreachable


# ---- the commit guard through an update ---------------------------------------------------------

GUARD_REL = Path("plugins") / "starter" / "hooks" / "commit-guard" / "guard.py"
FAKE_KEY = "AKIA" + "FAKE1234FAKE5678"  # assembled at runtime; not a real credential


def commit(k, repo: Path, name: str, text: str) -> subprocess.CompletedProcess:
    """Stage one file and commit it in `repo` with the kit's scratch env, so the hooks read the scratch
    guard data dir, never the real one."""
    (repo / name).write_text(text, encoding="utf-8")
    env = dict(k.env, GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run(["git", "-C", str(repo), "add", name], env=env, check=True, capture_output=True)
    return subprocess.run(["git", *GIT_ID, "-C", str(repo), "commit", "-q", "-m", "add " + name + TRAILER],
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)


def test_update_guard_repo_installs_the_hooks_and_a_hooked_repo_still_blocks_after_update(k):
    repo = k.tmp / "hooked"
    git(k.tmp, "init", "-q", str(repo))
    data = k.home / "guard-data"
    r = run(k, "--update", "--offline", "--yes", "--guard-repo", str(repo))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    hooks = [p.name for p in (repo / ".git" / "hooks").iterdir() if not p.name.endswith(".sample")]
    assert "pre-commit" in hooks and (data / "guard.py").is_file(), (hooks, r.stdout[-2000:])
    assert record(k)["installs"][0]["options"]["guard"] == {"state": "installed", "repos": [str(repo.resolve())]}
    (data / "config.json").write_text(json.dumps({"mode": "block", "require_record": False}), encoding="utf-8")

    sha = release(k, "0.4.1", edit=lambda w: (w / GUARD_REL).write_bytes((w / GUARD_REL).read_bytes()
                                                                         + b"\n# guard 0.4.1\n"))
    plan = run(k, "--update")
    assert plan.returncode == 0 and re.search(r"BACKUP\+REPLACE +commit guard copy", plan.stdout), plan.stdout[-3000:]
    r = run(k, "--update", "--yes", "--to", sha, "--plan", plan_id(plan.stdout))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert (data / "guard.py").read_bytes() == (k.kit / GUARD_REL).read_bytes()
    assert (data / "guard.py").read_bytes().endswith(b"# guard 0.4.1\n")
    blocked = commit(k, repo, "leak.txt", f"key={FAKE_KEY}\n")
    assert blocked.returncode != 0 and "aws-access-key" in blocked.stdout + blocked.stderr, blocked.stdout + blocked.stderr

    # The planted violation: without the copy the hooked repo's commit goes through (the guard skips).
    (data / "guard.py").unlink()
    skipped = commit(k, repo, "leak2.txt", f"key={FAKE_KEY}\n")
    assert skipped.returncode == 0, skipped.stdout + skipped.stderr
    git(repo, "update-ref", "-d", "HEAD")  # undo that unguarded first commit; its files stay staged
    # An update puts the copy back, because the record names a hooked repo, and the repo blocks again.
    r = run(k, "--update", "--offline", "--yes")
    assert r.returncode == 0 and (data / "guard.py").is_file(), r.stdout[-3000:] + r.stderr
    again = commit(k, repo, "leak3.txt", f"key={FAKE_KEY}\n")
    assert again.returncode != 0, again.stdout + again.stderr


# ---- orphans, adoption, and the move and git step kinds ------------------------------------------

def test_orphan_is_deleted_only_with_the_pin_and_an_edited_orphan_stays(k):
    agents = k.home / ".codex" / "agents"
    gone, edited = agents / "retired.toml", agents / "retired-edited.toml"
    gone.write_bytes(b"name = 'retired'\n")
    edited.write_bytes(b"name = 'retired-edited'\n")
    rec = record(k)
    rec["installs"][0]["files"][str(gone)] = __import__("hashlib").sha256(gone.read_bytes()).hexdigest()
    rec["installs"][0]["files"][str(edited)] = "0" * 64  # what the kit shipped; the user changed it since
    (k.home / ".agents" / "starter" / "installs.json").write_text(json.dumps(rec), encoding="utf-8")
    before = state(k)
    r = run(k, "--update", "--offline", "--yes")
    assert r.returncode == 2 and "--plan <id>" in r.stderr and state(k) == before, r.stdout[-2000:] + r.stderr
    plan = run(k, "--update", "--offline")
    assert re.search(r"BACKUP\+DELETE +orphan retired\.toml", plan.stdout), plan.stdout[-3000:]
    assert "you edited it, so it stays" in plan.stdout
    r = run(k, "--update", "--offline", "--yes", "--to", git(k.kit, "rev-parse", "HEAD"), "--plan",
            plan_id(plan.stdout))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert not gone.exists() and list(agents.glob("retired.toml.bak-*")) and edited.is_file()
    assert str(gone) not in record(k)["installs"][0]["files"]


def test_adoption_names_the_newest_matching_tag_and_finds_orphans_by_shipped_bytes(k):
    def retire(w):  # 0.4.1 no longer ships the codex verifier agent
        (w / "adapters" / "codex" / "agents" / "verifier.toml").unlink()
    sha = release(k, "0.4.1", edit=retire)
    git(k.kit, "fetch", "-q", "--tags", "origin")
    git(k.kit, "merge", "-q", "--ff-only", sha)
    verifier = k.home / ".codex" / "agents" / "verifier.toml"
    mine = k.home / ".codex" / "agents" / "mine.toml"  # the user's own agent, shipped by no release
    mine.write_bytes(b"name = 'mine'\n")
    (k.home / ".agents" / "starter" / "installs.json").unlink()
    plan = run(k, "--update", "--offline")
    assert plan.returncode == 0, plan.stdout[-3000:] + plan.stderr
    assert re.search(r"adopted: codex at .*\(tier starter, version 0\.4\.1\)", plan.stdout), plan.stdout[-3000:]
    assert re.search(r"BACKUP\+DELETE +orphan verifier\.toml", plan.stdout), plan.stdout[-3000:]
    assert "mine.toml" not in plan.stdout
    assert "update notices: the apply's closing block asks" in plan.stdout
    r = run(k, "--update", "--offline", "--yes", "--no-guard", "--to", sha, "--plan", plan_id(plan.stdout))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert not verifier.exists() and mine.is_file()
    assert "notices on" in r.stdout.split("=== For you", 1)[1]


def test_adoption_of_an_edited_block_says_so(k):
    rules = k.home / ".codex" / "AGENTS.md"
    rules.write_bytes(rules.read_bytes().replace(b"\n", b"\nmy own line inside the block\n", 3))
    (k.home / ".agents" / "starter" / "installs.json").unlink()
    plan = run(k, "--update", "--offline")
    assert "version <=0.3.1 or edited" in plan.stdout, plan.stdout[-3000:]


def test_move_and_git_steps_apply(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import install
    old, new = tmp_path / "a" / "old.txt", tmp_path / "b" / "new.txt"
    old.parent.mkdir()
    old.write_bytes(b"x")
    s = install.Step("move", old, "move", status="move", argv=[str(new)])
    install.apply(s, sys.executable)
    assert s.status == "moved" and new.read_bytes() == b"x" and not old.exists()
    old.write_bytes(b"y")
    s = install.Step("move", old, "move", status="move", argv=[str(new)])
    install.apply(s, sys.executable)  # the target exists: nothing moves
    assert s.status == "failed" and old.read_bytes() == b"y" and new.read_bytes() == b"x"
    repo = tmp_path / "r"
    git(tmp_path, "init", "-q", str(repo))
    s = install.Step("git", repo, "git", status="run", argv=["config", "starter.test", "1"])
    install.apply(s, sys.executable)
    assert s.status == "done" and git(repo, "config", "starter.test") == "1"
    s = install.Step("git", repo, "git", status="run", argv=["no-such-verb"])
    install.apply(s, sys.executable)
    assert s.status == "failed" and "exited" in s.detail


# ---- what the person is told -------------------------------------------------------------------

def test_noop_apply_says_nothing_changed_and_non_claude_notice_names_checkpoint(k):
    r = run(k, "--update", "--offline", "--yes")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    tail = r.stdout.split("=== For you", 1)[1]
    assert "Nothing to update" in tail and "Updated to" not in tail and "Restart" not in tail
    assert "checkpoint and lanes commands print one line" in tail and "new session" not in tail


def test_repeat_commands_carry_the_guard_answer(k):
    sys.path.insert(0, str(SCRIPTS))
    import install
    a = SimpleNamespace(tool="cursor", tier="starter", config_dir=None, project=None, guard_repo=[], no_guard=True)
    assert all(ln.endswith("--no-guard --yes") for ln in install.install_lines(a))
    cursor = "\n".join(install.next_cursor(k.home, a))
    assert cursor.count("--no-guard --project <your-repo> --yes") == 2, cursor
    guard = install.install_lines(a, " --guard-repo <your-repo> --yes")
    assert not any("--no-guard" in ln for ln in guard)


@pytest.mark.skipif(not shutil.which("icacls"), reason="needs Windows icacls")
def test_codex_sandbox_refusal_command_runs_in_the_users_terminal(tmp_path):
    home = tmp_path / "home"
    (home / "locked").mkdir(parents=True)  # CODEX_HOME does not exist yet, under a folder that refuses writes
    env = dict(clean_env(home), CODEX_HOME=str(home / "locked" / "codex"), CODEX_THREAD_ID="x")
    locked = home / "locked"
    assert subprocess.run(["icacls", str(locked), "/deny", "*S-1-1-0:(WD,AD)"], capture_output=True).returncode == 0
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "install.py"), "--tool", "codex", "--tier", "starter",
                            "--yes", "--no-guard"], env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=300)
    finally:
        subprocess.run(["icacls", str(locked), "/remove:d", "*S-1-1-0"], capture_output=True)
    assert r.returncode == 3, r.stdout[-2000:] + r.stderr
    (cmd,) = [ln for ln in r.stderr.splitlines() if ln.strip().startswith("bash:") and "install.py" in ln]
    assert cmd.rstrip().endswith("--no-guard --yes"), cmd


def test_notice_is_bounded_when_the_remote_hangs_and_the_failure_is_cached(k):
    assert run(k, "notices", "on", script="starter.py").returncode == 0
    rec = record(k)
    rec["kit"]["remote"] = "https://10.255.255.1/x.git"  # unroutable: the connect hangs until killed
    (k.home / ".agents" / "starter" / "installs.json").write_text(json.dumps(rec), encoding="utf-8")
    t0 = time.time()
    assert notice(k) == ""
    assert time.time() - t0 < 8, "the 3 s bound did not hold"
    cache = json.loads((k.home / ".agents" / "starter" / "update-check.json").read_text(encoding="utf-8"))
    assert cache["newest"] == "" and cache["failed"] is True
    t0 = time.time()
    assert notice(k) == ""
    assert time.time() - t0 < 2.5, "a failed check was retried within the day"


def test_notice_line_prints_at_most_once_a_day(k):
    assert run(k, "notices", "on", script="starter.py").returncode == 0
    release(k, "0.4.1")
    assert "v0.4.1 is available" in notice(k)
    assert notice(k) == ""  # shown today already
    cache = k.home / ".agents" / "starter" / "update-check.json"
    c = json.loads(cache.read_text(encoding="utf-8"))
    cache.write_text(json.dumps(dict(c, shown_at=time.time() - 2 * 86400)), encoding="utf-8")
    assert "v0.4.1 is available" in notice(k)


def test_notices_without_a_record_exits_2_and_says_how(k):
    (k.home / ".agents" / "starter" / "installs.json").unlink()
    r = run(k, "notices", "on", script="starter.py")
    assert r.returncode == 2 and "update" in r.stderr and "apply" in r.stderr, r.stderr


# ---- re-runs with a hooked repo, git steps, --dry-run, and what the plan asks -------------------

def hook_files(repo: Path) -> dict:
    """Each installed hook's bytes and mtime: a re-install rewrites them even when the bytes match."""
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in (repo / ".git" / "hooks").iterdir() if not p.name.endswith(".sample")}


def test_a_second_run_with_the_same_guard_repo_writes_nothing(k):
    repo = k.tmp / "hooked"
    git(k.tmp, "init", "-q", str(repo))
    r = run(k, "--update", "--offline", "--yes", "--guard-repo", str(repo))
    assert r.returncode == 0 and "pre-commit" in hook_files(repo), r.stdout[-3000:] + r.stderr
    hooks, before = hook_files(repo), state(k)
    time.sleep(0.05)
    r = run(k, "--update", "--offline", "--yes", "--guard-repo", str(repo))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert "Nothing to update" in r.stdout.split("=== For you", 1)[1], r.stdout[-3000:]
    assert hook_files(repo) == hooks and state(k) == before
    r = run(k, "--tool", "codex", "--tier", "starter", "--yes", "--guard-repo", str(repo))
    assert r.returncode == 0 and re.search(r"SKIP \(already installed\) +commit guard \(git hooks\)", r.stdout)
    assert hook_files(repo) == hooks
    # Anything guard.py install would change is planned again: an edited hook, a stale guard copy.
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_bytes(hook.read_bytes() + b"# my edit\n")
    dry = run(k, "--tool", "codex", "--tier", "starter", "--dry-run", "--guard-repo", str(repo))
    assert re.search(r"RUN +commit guard \(git hooks\)", dry.stdout), dry.stdout[-3000:]
    assert run(k, "--tool", "codex", "--tier", "starter", "--yes", "--guard-repo", str(repo)).returncode == 0
    copy = k.home / "guard-data" / "guard.py"
    copy.write_bytes(copy.read_bytes() + b"\n# stale\n")
    dry = run(k, "--tool", "codex", "--tier", "starter", "--dry-run", "--guard-repo", str(repo))
    assert re.search(r"RUN +commit guard \(git hooks\)", dry.stdout), dry.stdout[-3000:]


TEST_MIGRATIONS_GIT = Path(__file__).resolve().parent / "fixtures" / "migrations_git"
MIG_GIT = {"STARTER_TEST_MIGRATIONS": str(TEST_MIGRATIONS_GIT)}


def test_every_writing_step_kind_is_probed_and_pinned(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import install
    repo, old = tmp_path / "r", tmp_path / "a" / "x.txt"
    git(tmp_path, "init", "-q", str(repo))
    old.parent.mkdir()
    old.write_bytes(b"x")
    steps = [install.Step("g", repo, "git", status="git", argv=["config", "a.b", "1"]),
             install.Step("d", old, "delete", status="delete"),
             install.Step("m", old, "move", status="move", argv=[str(tmp_path / "b" / "y.txt")])]
    assert all(s.writes for s in steps) and all(install.needs_pin([s]) for s in steps)
    dirs = {os.path.normcase(str(d.resolve())) for d in install.write_targets(steps)[0]}
    for want in (repo / ".git", old.parent, tmp_path / "b"):
        assert os.path.normcase(str(want.resolve())) in dirs, (want, dirs)
    with pytest.raises(ValueError):
        install.write_targets([install.Step("x", old, "no-such-kind", status="create")])


def test_a_git_step_is_pinned_applied_once_and_a_failed_one_leaves_its_migration_unrecorded(k):
    repo = k.home / "mig-repo"
    git(k.home, "init", "-q", str(repo))
    head = git(k.kit, "rev-parse", "HEAD")
    before = state(k)
    r = run(k, "--update", "--offline", "--yes", extra=MIG_GIT)
    assert r.returncode == 2 and "--plan <id>" in r.stderr, r.stdout[-2000:] + r.stderr
    assert state(k) == before

    failing = dict(MIG_GIT, STARTER_TEST_GIT_VERB="no-such-verb")
    plan = run(k, "--update", "--offline", extra=failing)
    assert plan.returncode == 0 and re.search(r"GIT +migration 9002 git config", plan.stdout), plan.stdout[-3000:]
    assert "9002-test-git" in plan.stdout and state(k) == before
    r = run(k, "--update", "--offline", "--yes", "--to", head, "--plan", plan_id(plan.stdout), extra=failing)
    assert r.returncode == 1 and "record was not advanced" in r.stderr, r.stdout[-3000:] + r.stderr
    assert "9002-test-git" not in record(k)["installs"][0]["migrations_applied"]
    assert state(k) == before

    plan = run(k, "--update", "--offline", extra=MIG_GIT)
    r = run(k, "--update", "--offline", "--yes", "--to", head, "--plan", plan_id(plan.stdout), extra=MIG_GIT)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert git(repo, "config", "starter.migrated") == "9002"
    assert "9002-test-git" in record(k)["installs"][0]["migrations_applied"]
    after = state(k)
    r = run(k, "--update", "--offline", extra=MIG_GIT)
    assert r.returncode == 0 and "Nothing to update" in r.stdout and state(k) == after, r.stdout[-3000:]


def test_update_dry_run_wins_over_yes(k):
    head = git(k.kit, "rev-parse", "HEAD")
    pid = plan_id(run(k, "--update", "--offline", extra=MIG).stdout)
    before = state(k)
    r = run(k, "--update", "--offline", "--dry-run", "--yes", "--to", head, "--plan", pid, extra=MIG)
    assert r.returncode == 0 and "dry run" in r.stdout, r.stdout[-3000:] + r.stderr
    assert r.stdout.rstrip("\n").split("\n")[-1] == STOP and state(k) == before
    sha = release(k, "0.4.1")
    pid = plan_id(run(k, "--update").stdout)
    before = state(k)
    r = run(k, "update", "--dry-run", "--yes", "--to", sha, "--plan", pid, script="starter.py")
    assert r.returncode == 0 and state(k) == before, r.stdout[-3000:] + r.stderr
    r = run(k, "--update", "--dry-run", "--yes", "--to", sha, "--plan", pid)
    assert r.returncode == 0 and state(k) == before and git(k.kit, "rev-parse", "HEAD") == head


def test_go_back_line_has_a_bash_and_a_powershell_form(k):
    old = git(k.kit, "rev-parse", "HEAD")
    sha = release(k, "0.4.1")
    pid = plan_id(run(k, "--update").stdout)
    r = run(k, "--update", "--yes", "--to", sha, "--plan", pid)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    tail = r.stdout.split("=== For you", 1)[1]
    # shlex.quote leaves a plain POSIX path bare and quotes one holding an apostrophe or a backslash.
    assert re.search(rf"bash: +git -C (?:'.*'|\S+) checkout {old}$", tail, re.M), tail
    assert re.search(rf"PowerShell: +git -C '.*' checkout {old}$", tail, re.M), tail


def test_a_never_asked_guard_goes_into_a_new_plan_not_this_plans_apply(k):
    rec = record(k)
    del rec["installs"][0]["options"]["guard"]
    (k.home / ".agents" / "starter" / "installs.json").write_text(json.dumps(rec), encoding="utf-8")
    head = git(k.kit, "rev-parse", "HEAD")
    plan = run(k, "--update", "--offline", extra=MIG)  # a no-op plan asks nothing
    assert "commit guard for codex: ask the user, then make the plan again" in plan.stdout, plan.stdout[-3000:]
    assert "to the apply command" not in plan.stdout
    pid = plan_id(plan.stdout)
    r = run(k, "--update", "--offline", "--yes", "--to", head, "--plan", pid, extra=MIG)
    assert r.returncode == 2 and "Make the plan again" in r.stderr, r.stderr
    # Why the answer cannot go into this apply: --guard-repo adds a step, so the pinned id no longer matches.
    repo = k.tmp / "hooked"
    git(k.tmp, "init", "-q", str(repo))
    r = run(k, "--update", "--offline", "--yes", "--to", head, "--plan", pid, "--guard-repo", str(repo), extra=MIG)
    assert r.returncode == 2 and "plan changed" in r.stderr, r.stderr
    plan = run(k, "--update", "--offline", "--guard-repo", str(repo), extra=MIG)
    pinned = [ln for ln in plan.stdout.splitlines() if "--plan " + plan_id(plan.stdout) in ln]
    assert len(pinned) == 2 and all("--guard-repo" in ln for ln in pinned), pinned
    r = run(k, "--update", "--offline", "--yes", "--to", head, "--plan", plan_id(plan.stdout), "--guard-repo",
            str(repo), extra=MIG)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert record(k)["installs"][0]["options"]["guard"]["state"] == "installed"

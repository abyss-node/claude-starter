"""The OpenCode load check: per major version, against a stand-in binary (fake_opencode.py) that runs
everywhere, and against the real `opencode` when one is on PATH.

OpenCode 2 removed `agent list` and `debug agent|skill|config`, and an installer that still asked for
them wrote every file and then exited 1 with "load check FAILED". The 2.x check asks a server through
`opencode api`; the tests below reproduce each way that can lie or hang on 2.3.0."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
import install  # noqa: E402
from test_adapters import sandbox_env  # noqa: E402

KIT_SKILLS = sorted(p.name for p in (install.ADAPTERS / "opencode" / "skills").iterdir())


def fake_bin(tmp_path: Path, **fake) -> "tuple[Path, Path]":
    """A bin folder whose `opencode` runs fake_opencode.py with these settings, and its state folder. The
    stub runs as a child of a shim, as the real binary does behind npm's (a .cmd file on Windows, a node
    script elsewhere), so killing only the shim would leave it running."""
    bindir, state = tmp_path / "fakebin", tmp_path / "fake-oc"
    bindir.mkdir(exist_ok=True)
    state.mkdir(exist_ok=True)
    (state / "fake.json").write_text(json.dumps(fake), encoding="utf-8")
    stub = TESTS / "fake_opencode.py"
    if os.name == "nt":
        (bindir / "opencode.cmd").write_text(f'@"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8")
    else:
        exe = bindir / "opencode"
        exe.write_text(f'#!/bin/sh\n"{sys.executable}" "{stub}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
    return bindir, state


def calls(state: Path) -> list:
    log = state / "calls.jsonl"
    return [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             timeout=60).stdout
        return re.search(rf"\b{pid}\b", out) is not None
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.fixture
def oc(tmp_path, monkeypatch):
    """The kit's OpenCode files in a config folder under tmp_path, an environment that points OpenCode at
    it, and use(**settings), which puts a stand-in `opencode` with those settings first on PATH."""
    home, cfg = tmp_path / "home", tmp_path / "xdg" / "opencode"
    home.mkdir()
    for d in ("agents", "skills", "commands"):
        shutil.copytree(str(install.ADAPTERS / "opencode" / d), str(cfg / d))
    for k in [k for k in os.environ if k.startswith("OPENCODE")]:
        monkeypatch.delenv(k)
    for k in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(k, str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg.parent))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(install, "OC_SETTLE_TIMEOUT", 4)  # how long a failing listing is re-read
    monkeypatch.setattr(install, "OC_POLL_INTERVAL", 0.05)
    monkeypatch.setattr(install, "OC_CALL_TIMEOUT", 30)
    path = os.environ["PATH"]

    def use(**fake) -> Path:
        bindir, state = fake_bin(tmp_path, **fake)
        monkeypatch.setenv("PATH", str(bindir) + os.pathsep + path)
        monkeypatch.setenv("FAKE_OC_DIR", str(state))
        return state

    def check():
        return install.opencode_check(cfg, install.plan_tool("opencode", "starter", cfg, None, []))
    return SimpleNamespace(cfg=cfg, home=home, use=use, check=check)


# ---- the rule evaluation and the path match, on plain data ---------------------------------------

ALLOW_ALL = {"action": "*", "resource": "*", "effect": "allow"}


def rule(action, resource, effect):
    return {"action": action, "resource": resource, "effect": effect}


@pytest.mark.parametrize("rules,denied", [
    ([ALLOW_ALL, rule("edit", "*", "deny")], True),
    ([ALLOW_ALL, rule("edit", "*", "deny"), rule("edit", "notes/*", "deny")], True),
    ([rule("*", "*", "deny")], True),
    ([ALLOW_ALL, rule("edit", "*", "deny"), rule("edit", "src/*", "allow")], False),  # a later allow wins there
    ([ALLOW_ALL, rule("edit", "*", "deny"), rule("e*", "x", "ask")], False),
    ([ALLOW_ALL, rule("edit", "src/*", "deny")], False),                             # not every resource
    ([rule("edit", "*", "deny"), ALLOW_ALL], False),                                 # the last match wins
    ([ALLOW_ALL, rule("shell", "*", "deny")], False),                                # another action
    ([], False),
], ids=["deny", "deny-then-narrower-deny", "star-deny", "later-allow", "later-pattern-ask", "narrow-deny",
        "deny-then-allow-all", "other-action", "no-rules"])
def test_oc2_denies_takes_the_last_matching_rule(rules, denied):
    assert install.oc2_denies(rules, "edit") is denied


def test_oc2_skills_needs_the_installed_file_not_just_the_name(tmp_path):
    dest = tmp_path / "cfg" / "skills" / "x" / "SKILL.md"
    steps = [install.Step("skill x", dest, "file")]
    other = str(tmp_path / "home" / ".claude" / "skills" / "x" / "SKILL.md")
    ok, lines = install._oc2_skills([{"name": "x", "path": other}], steps)
    assert not ok and other in lines[0] and str(dest) in lines[0], lines
    assert not install._oc2_skills([{"name": "x", "path": "skill://x/SKILL.md"}], steps)[0]
    assert not install._oc2_skills([], steps)[0]
    assert install._oc2_skills([{"name": "x", "path": other}, {"name": "x", "path": str(dest)}], steps)[0]


# ---- 2.x, against the stand-in ----------------------------------------------------------------------

def test_v2_check_passes_through_a_private_server_and_names_the_version(oc):
    state = oc.use(version="opencode v2.3.0")
    ok, lines, verdict = oc.check()
    assert ok, lines
    assert verdict == "passed (loaded by opencode) version 2.3.0"
    assert f"skills loaded from this install: {', '.join(KIT_SKILLS)}" in lines
    assert "commands loaded: /checkpoint, /lanes, /onboard, /starter-update" in lines
    assert "agent consultant: denied as written (edit, shell, subagent, webfetch, websearch)" in lines
    log = calls(state)
    servers = [json.loads(p.read_text(encoding="utf-8")) for p in (state / "servers").glob("*.json")]
    assert len(servers) == 1
    apis = [c for c in log if c["argv"][:1] == ["api"]]
    assert apis and all("--server" in c["argv"] for c in apis), "an api call went to the background service"
    assert {c["password"] for c in apis} == {servers[0]["password"]}
    assert not [c for c in log if c["argv"][:2] == ["agent", "list"]]
    assert not alive(servers[0]["pid"]), "the private server was left running"


def test_v2_reads_until_discovery_settles(oc, monkeypatch):
    monkeypatch.setattr(install, "OC_SETTLE_TIMEOUT", 20)
    state = oc.use(partial_reads=3)  # the first three answers to each operation are built-ins only
    ok, lines, _ = oc.check()
    assert ok, lines
    reads = [c["argv"][-1] for c in calls(state) if c["argv"][:1] == ["api"]]
    assert reads.count("skill.list") >= 5  # three partial, then the same full answer twice



def test_v2_takes_only_an_answer_that_stays(oc):
    # The first complete answer passes; every later one has an allow after the verifier's edit deny.
    oc.use(late_rules={"verifier": [{"action": "edit", "resource": "*", "effect": "allow"}]})
    ok, lines, _ = oc.check()
    assert not ok and lines[1] == "agent verifier: denied in its file but not denied by OpenCode: ['edit']", lines

def test_v2_never_asks_the_background_service(oc, tmp_path):
    # The service started earlier, with a config that has everything; this install lacks a skill.
    service = tmp_path / "service-config"
    shutil.copytree(str(oc.cfg), str(service))
    shutil.rmtree(str(oc.cfg / "skills" / "llm-app-guardrails"))
    state = oc.use(service_config_dir=str(service))
    ok, lines, verdict = oc.check()
    assert not ok and verdict == "FAILED"
    assert "skills not loaded from this install: llm-app-guardrails (not listed)" in lines, lines
    assert all("--server" in c["argv"] for c in calls(state) if c["argv"][:1] == ["api"])


def test_v2_password_in_the_users_environment_is_not_used(oc, monkeypatch):
    monkeypatch.setenv("OPENCODE_PASSWORD", "the-users-own")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "another")
    state = oc.use()
    ok, lines, _ = oc.check()
    assert ok, lines
    sent = {c["password"] for c in calls(state) if c["argv"][:1] in (["serve"], ["api"])}
    assert len(sent) == 1 and not sent & {"the-users-own", "another"}, sent


def test_v2_kit_skill_shadowed_by_a_same_named_one_fails(oc):
    shadow = oc.home / ".claude" / "skills" / "backend-build-guardrails" / "SKILL.md"
    shutil.rmtree(str(oc.cfg / "skills" / "backend-build-guardrails"))
    oc.use(extra_skills=[{"name": "backend-build-guardrails", "path": str(shadow)}])
    ok, lines, verdict = oc.check()
    assert not ok and verdict == "FAILED"
    assert f"backend-build-guardrails (loaded from {shadow}, not " in lines[1], lines


def test_v2_rule_after_an_agents_deny_fails(oc):
    oc.use(extra_rules={"verifier": [{"action": "edit", "resource": "src/*", "effect": "allow"}]})
    ok, lines, _ = oc.check()
    assert not ok
    assert lines[1] == "agent verifier: denied in its file but not denied by OpenCode: ['edit']", lines


def test_v2_missing_agent_or_command_fails(oc):
    (oc.cfg / "agents" / "consultant.md").unlink()
    oc.use()
    ok, lines, _ = oc.check()
    assert not ok and lines[1] == "`opencode api agent.list` is missing: consultant", lines
    (oc.cfg / "agents" / "consultant.md").write_bytes((install.ADAPTERS / "opencode/agents/consultant.md").read_bytes())
    (oc.cfg / "commands" / "onboard.md").unlink()
    ok, lines, _ = oc.check()
    assert not ok and lines[1] == "commands not loaded: onboard", lines


def test_v2_project_folders_above_the_check_do_not_count(oc, tmp_path):
    """The check runs in a temporary folder; a `.opencode/commands` above it (here tmp_path, the temp
    root) would otherwise stand in for a missing kit command."""
    (oc.cfg / "commands" / "onboard.md").unlink()
    above = tmp_path / ".opencode" / "commands"
    above.mkdir(parents=True)
    (above / "onboard.md").write_text("---\ndescription: not the kit's\n---\nx\n", encoding="utf-8")
    oc.use()
    ok, lines, _ = oc.check()
    assert not ok and lines[1] == "commands not loaded: onboard", lines


def test_v2_listing_that_never_settles_fails_in_bounded_time(oc, monkeypatch):
    monkeypatch.setattr(install, "OC_SETTLE_TIMEOUT", 1)
    oc.use(partial_reads=10 ** 6)
    t0 = time.monotonic()
    ok, lines, _ = oc.check()
    assert not ok and time.monotonic() - t0 < 30
    assert lines[1].startswith("`opencode api agent.list` is missing: ")
    assert re.fullmatch(r"\(the last of \d+ reads of `opencode api agent.list` in 1s\)", lines[-1]), lines


# ---- never hang -----------------------------------------------------------------------------------

@pytest.mark.parametrize("where,want", [
    ("version", "`opencode --version` exited 124"),
    ("serve", "`opencode serve` printed no address in 2s"),
    ("api:skill.list", "`opencode api skill.list` exited 124"),
])
def test_a_call_that_hangs_fails_the_check_within_its_timeout(oc, monkeypatch, where, want):
    monkeypatch.setattr(install, "OC_CALL_TIMEOUT", 2)
    oc.use(hang=[where], hang_seconds=40)
    t0 = time.monotonic()
    ok, lines, verdict = oc.check()
    assert not ok and verdict == "FAILED"
    assert time.monotonic() - t0 < 25, "the check waited for a hung call"
    assert any(ln.startswith(want) for ln in lines), lines


def test_a_process_left_holding_the_output_does_not_stall_a_call(oc, tmp_path):
    oc.use(leak=True, hang_seconds=20)  # `api` exits at once, leaving a child that holds its output
    t0 = time.monotonic()
    rc, out = install._run_bounded([shutil.which("opencode"), "api", "--server", "http://127.0.0.1:1", "agent.list"],
                                   dict(os.environ), str(tmp_path), 60)
    assert rc == 1 and "Could not reach server" in out, out
    assert time.monotonic() - t0 < 10, "the call waited for a child that outlived it"



def test_a_call_cannot_wait_at_a_prompt(oc, tmp_path):
    """Every opencode call gets a closed stdin. Here the installer's own stdin is a pipe nobody writes
    to, as when an agent runs it; a call that inherited it would sit at the prompt until its timeout."""
    oc.use(prompt=True)
    r, w = os.pipe()
    saved = os.dup(0)
    os.dup2(r, 0)
    try:
        t0 = time.monotonic()
        rc, out = install._run_bounded([shutil.which("opencode"), "api", "agent.list"], dict(os.environ),
                                       str(tmp_path), 15)
    finally:
        os.dup2(saved, 0)
        for fd in (r, w, saved):
            os.close(fd)
    assert rc == 1 and "no password entered" in out, (rc, out)
    assert time.monotonic() - t0 < 10

# ---- the version decides the check ----------------------------------------------------------------

def test_v1_check_still_asks_the_v1_commands(oc):
    state = oc.use(version="1.19.5")
    ok, lines, verdict = oc.check()
    assert ok, lines
    assert verdict == "passed (loaded by opencode) version 1.19.5"
    assert "agent consultant: tools off as written (bash, edit, task, webfetch, websearch, write)" in lines
    argv = [c["argv"] for c in calls(state)]
    assert ["agent", "list"] in argv and not [a for a in argv if a[:1] in (["serve"], ["api"])]


@pytest.mark.parametrize("printed,want", [
    ("opencode v3.1.0", "OpenCode 3.1.0 is a major version this installer cannot check (it knows 1.x and 2.x)"),
    ("0.9.2", "OpenCode 0.9.2 is a major version this installer cannot check"),
    ("nightly build", "`opencode --version` exited 0 without a version number:"),
])
def test_an_unknown_or_unreadable_version_fails_naming_it(oc, printed, want):
    state = oc.use(version=printed)
    ok, lines, verdict = oc.check()
    assert not ok and verdict == "FAILED"
    assert lines[0].startswith(want), lines
    assert [c["argv"] for c in calls(state)] == [["--version"]]


def test_install_with_a_v2_opencode_passes_end_to_end(tmp_path):
    bindir, _ = fake_bin(tmp_path)
    env = sandbox_env(tmp_path)
    for k in [k for k in env if k.startswith("OPENCODE")]:
        del env[k]
    env.update(PATH=str(bindir) + os.pathsep + env["PATH"], FAKE_OC_DIR=str(tmp_path / "fake-oc"),
               XDG_CONFIG_HOME=str(tmp_path / "home" / ".config"))
    r = subprocess.run([sys.executable, str(SCRIPTS / "install.py"), "--tool", "opencode", "--tier", "starter",
                        "--yes", "--no-guard"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert re.search(r"^load check +opencode +passed \(loaded by opencode\) version 2\.3\.0$", r.stdout, re.M)
    assert "`opencode agent list` (OpenCode 1.x) or `opencode debug agents` (2.x)" in r.stdout


# ---- the real opencode, when one is on PATH --------------------------------------------------------

def real_env(tmp_path: Path) -> dict:
    env = sandbox_env(tmp_path)
    for k in [k for k in env if k.startswith(("OPENCODE", "XDG_"))]:
        del env[k]
    home = Path(env["HOME"])
    env.update(XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local" / "share"),
               XDG_STATE_HOME=str(home / ".local" / "state"), XDG_CACHE_HOME=str(home / ".cache"),
               APPDATA=str(home / "AppData" / "Roaming"), LOCALAPPDATA=str(home / "AppData" / "Local"),
               OPENCODE_DISABLE_AUTOUPDATE="1")
    return env


@pytest.fixture(scope="module")
def real(tmp_path_factory) -> str:
    """The version of the `opencode` on PATH, asked in a throwaway home; skips when there is none."""
    exe = shutil.which("opencode")
    if not exe:
        pytest.skip("opencode not installed")
    out = subprocess.run([exe, "--version"], env=real_env(tmp_path_factory.mktemp("real-version")),
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"(\d+\.\d+\.\d+)", out)
    if not m:
        pytest.skip(f"`opencode --version` printed no version: {out!r}")
    return m.group(1)


def test_real_opencode_install_passes_and_names_its_version(real, tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPTS / "install.py"), "--tool", "opencode", "--tier", "starter",
                        "--yes", "--no-guard"], env=real_env(tmp_path), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert f"passed (loaded by opencode) version {real}" in r.stdout


def test_real_v2_same_named_skill_or_command_does_not_pass_for_the_kits(real, tmp_path, monkeypatch):
    """On 2.3.0 ~/.claude/skills loads too, one skill per name: with the kit's copy gone, a skill of the
    same name there is listed in its place. And a `.opencode/commands` above the working directory
    loads unless project config is off."""
    if not real.startswith("2."):
        pytest.skip(f"needs opencode 2.x on PATH, found {real}")
    env = real_env(tmp_path)
    for k in [k for k in os.environ if k.startswith(("OPENCODE", "XDG_"))]:
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(install, "OC_SETTLE_TIMEOUT", 20)  # the failing read below waits this long
    cfg = Path(env["XDG_CONFIG_HOME"]) / "opencode"
    for d in ("agents", "skills", "commands"):
        shutil.copytree(str(install.ADAPTERS / "opencode" / d), str(cfg / d))
    steps = install.plan_tool("opencode", "starter", cfg, None, [])
    assert install.opencode_check(cfg, steps)[0]
    shutil.rmtree(str(cfg / "skills" / "backend-build-guardrails"))
    shadow = Path(env["HOME"]) / ".claude" / "skills" / "backend-build-guardrails" / "SKILL.md"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("---\nname: backend-build-guardrails\ndescription: not the kit's\n---\nx\n", encoding="utf-8")
    ok, lines, verdict = install.opencode_check(cfg, steps)
    assert not ok and verdict == "FAILED"
    assert "backend-build-guardrails (loaded from " in lines[1] and str(shadow) in lines[1], lines
    # A command in a `.opencode/commands` above the check's folder (tmp_path, its temp root) loads
    # unless project config is off; it must not stand in for a missing kit command.
    shutil.copytree(str(install.ADAPTERS / "opencode" / "skills" / "backend-build-guardrails"),
                    str(cfg / "skills" / "backend-build-guardrails"))
    (cfg / "commands" / "onboard.md").unlink()
    above = tmp_path / ".opencode" / "commands"
    above.mkdir(parents=True)
    (above / "onboard.md").write_text("---\ndescription: not the kit's\n---\nx\n", encoding="utf-8")
    ok, lines, _ = install.opencode_check(cfg, steps)
    assert not ok and lines[1] == "commands not loaded: onboard", lines

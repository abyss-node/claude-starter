"""Tests for scripts/build_adapters.py and scripts/install.py.

Installs run in a throwaway HOME (tmp_path) with every relocation variable cleared, so nothing here
touches a real tool config. Real tools are only used when they are on PATH (codex, opencode).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import build_adapters as ba  # noqa: E402
import install  # noqa: E402

NEW_TOOLS = ("codex", "cursor", "copilot", "antigravity", "junie")
RELOCATE = ("CODEX_HOME", "COPILOT_HOME", "CURSOR_CONFIG_DIR", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR",
            "XDG_CONFIG_HOME", "COMMIT_GUARD_DIR")


def sandbox_env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in RELOCATE}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update(HOME=str(home), USERPROFILE=str(home), TEMP=str(tmp_path), TMP=str(tmp_path),
               TMPDIR=str(tmp_path), PYTHONIOENCODING="utf-8")
    return env


def run_install(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "install.py"), *args], env=sandbox_env(tmp_path),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def test_adapters_match_a_fresh_build():
    assert ba.main(["--check"]) == 0


# Headings every tier must carry, in the source templates and in every generated adapter. A rule
# that exists in only one tier ships as a silent gap: the full tier once had no confirm rule.
REQUIRED_RULE_HEADINGS = (
    "## Verification honesty",
    "## Confirm before anything outward-facing or irreversible",
    "## Debugging",
    "## Complexity budget",
    "## Comments and lifetime",
)


def _rule_files() -> list:
    templates = SCRIPTS.parent / "plugins" / "starter" / "templates"
    files = [templates / f"CLAUDE.{t}.md" for t in ba.TIERS]
    files += sorted((SCRIPTS.parent / "adapters").glob("*/AGENTS.*.md"))
    return files


def _headings(path: Path) -> set:
    lines = path.read_bytes().decode("utf-8").splitlines()
    return {ln.rstrip() for ln in lines if ln.startswith("## ")}


def test_rule_files_are_found_for_every_tier_and_tool():
    names = [f"{f.parent.name}/{f.name}" for f in _rule_files()]
    tools = {f.parent.name for f in _rule_files() if f.parent.name != "templates"}
    assert len(tools) >= 7
    for tier in ba.TIERS:
        assert f"templates/CLAUDE.{tier}.md" in names
        assert all(f"{t}/AGENTS.{tier}.md" in names for t in tools)


@pytest.mark.parametrize("path", _rule_files(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_tier_carries_the_required_rule_headings(path):
    missing = [h for h in REQUIRED_RULE_HEADINGS if h not in _headings(path)]
    assert not missing, f"{path.name} lacks {missing}"


def test_no_adapter_claims_the_commit_guard_is_always_installed():
    """Every generated file, not only the rules: the checkpoint skill once kept "The commit guard checks
    for this" after the rules were fixed, because the check scanned only AGENTS.*.md."""
    files = sorted(p for p in (SCRIPTS.parent / "adapters").rglob("*") if p.is_file())
    assert len(files) > 50
    conditional = 0
    for f in files:
        text = f.read_bytes().decode("utf-8")
        assert not ba.GUARD_CLAIM.search(text), f
        if re.search(r"commit\s+guard\s+is\s+installed", text):
            conditional += 1
            assert "--guard-repo" in text, f
    assert conditional >= 3 * len(ba.EMITTERS)  # both rules tiers and the checkpoint, for every tool


@pytest.mark.parametrize("claim", [
    "The commit guard checks for this, and a chat summary dies",
    "The `starter` commit guard checks this;",
    "The `starter`\nplugin's commit guard checks this on agent commits",
    "Codex's commit attribution is undocumented; the commit guard is the check.",
])
def test_lint_rejects_an_unconditional_commit_guard_claim(claim):
    with pytest.raises(SystemExit, match="unconditional commit guard claim"):
        ba.lint("codex", {"skills/x/SKILL.md": claim + "\n"})


def test_lint_accepts_the_conditional_commit_guard_wording():
    ba.lint("codex", {"skills/x/SKILL.md": "Where the commit guard is installed (installer `--guard-repo`) "
                                           "it checks this; elsewhere nothing does.\n"})


# README.md and AGENTS.md tell an agent what each installer exit leaves behind. Step 7 once said every
# non-zero exit had saved a report; the cannot-write refusal saves none on purpose, so an agent that
# followed it would tell the user about a report that does not exist.
SETUP_DOCS = ("README.md", "AGENTS.md")


def _setup_steps(doc: str) -> list:
    """The numbered setup steps of `doc`, each flattened to one line."""
    text = (SCRIPTS.parent / doc).read_bytes().decode("utf-8").replace("\r\n", "\n")
    steps = re.split(r"\n(?=\d+\. )", text)[1:]
    return [" ".join(re.split(r"\n\n(?=\S)", s, maxsplit=1)[0].split()) for s in steps]


@pytest.mark.parametrize("doc", SETUP_DOCS)
def test_setup_docs_say_which_exits_leave_a_report(doc):
    steps = _setup_steps(doc)
    failed = next(s for s in steps if "non-zero" in s)
    assert "Exit 1" in failed and "redacted report" in failed
    assert f"Exit {install.UNWRITABLE}" in failed and "no report was saved" in failed
    assert "stderr" in failed and "own terminal" in failed
    succeeded = next(s for s in steps if "If it succeeds" in s)
    assert "refuse" not in succeeded and "cannot write" not in succeeded
    assert install.FOR_YOU in succeeded
    for s in steps:  # the install prints the "For you" block last; a step naming another ending is stale
        if "It ends" in s:
            assert install.FOR_YOU in s.split("It ends", 1)[1][:80], s


def test_shared_skills_must_be_identical():
    built = {"codex": {"skills/x/SKILL.md": "a\n"}, "junie": {"skills/x/SKILL.md": "b\n"}}
    with pytest.raises(SystemExit, match="shared"):
        ba.check_shared_skills(built)


def test_antigravity_rules_over_the_cap_fail_the_build():
    src = ba.load_sources()
    src.rules["full"] += "x" * 30_000
    with pytest.raises(SystemExit, match="24000 bytes"):
        ba.emit_antigravity(src)


def test_unclassified_allow_command_stops_the_build():
    src = ba.load_sources()
    src.bash_allow.append("git push")
    with pytest.raises(SystemExit, match="neither PREFIX_SAFE nor PREFIX_UNSAFE"):
        ba.emit_codex(src)


def test_claude_tools_string_is_rejected_even_where_tools_is_allowed():
    with pytest.raises(SystemExit, match="Claude `tools:` string"):
        ba.lint("junie", {"agents/a.md": "---\ntools: Read, Grep, Glob\n---\n"}, fields=("tools",))


def test_prefix_tools_never_get_write_capable_commands():
    for tool, rel in (("codex", "rules/claude-starter.rules"), ("antigravity", "antigravity-cli.settings.json"),
                      ("junie", "junie.allowlist.json")):
        text = ba.EMITTERS[tool](ba.load_sources())[rel]
        for unsafe in ba.PREFIX_UNSAFE:
            assert f'"{unsafe}"' not in text and f"({unsafe})" not in text, (tool, unsafe)


def test_prefix_tools_allow_no_ruff_and_claim_no_any_arguments_safety():
    """`ruff format --check --cache-dir <dir>` writes a cache, so ruff is not prefix-safe."""
    for tool, rel, rule in (("codex", "rules/claude-starter.rules", '["ruff"'),
                            ("antigravity", "antigravity-cli.settings.json", "command(ruff"),
                            ("junie", "junie.allowlist.json", '"prefix": "ruff')):
        files = ba.EMITTERS[tool](ba.load_sources())
        assert rule not in files[rel], tool
        for name, text in files.items():
            assert "read-only with any arguments" not in text and "read-only with extra arguments" not in text, \
                (tool, name)
    for notes in (install.notes_codex, install.notes_antigravity):
        text = " ".join(notes(Path("nowhere"), None))
        assert "with any arguments" not in text, notes.__name__


def test_agents_never_grant_editing():
    for tool in NEW_TOOLS:
        for rel, text in ba.EMITTERS[tool](ba.load_sources()).items():
            if "agents/" in rel:
                for bad in ('"edit"', '"Edit"', '"Write"', '"write_file"'):
                    assert bad not in text.split("\n---", 1)[0], (tool, rel, bad)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tool", NEW_TOOLS)
def test_fresh_install_then_rerun_is_a_no_op(tmp_path, tool):
    first = run_install(tmp_path, "--tool", tool, "--tier", "starter", "--yes", "--no-guard")
    assert first.returncode == 0, first.stdout + first.stderr
    assert "passed" not in first.stdout.split("load check", 1)[1].splitlines()[0] or tool == "codex"
    if tool != "codex":
        assert "structurally checked; not verified against the real tool" in first.stdout
    second = run_install(tmp_path, "--tool", tool, "--tier", "starter", "--yes", "--no-guard")
    assert second.returncode == 0, second.stdout + second.stderr
    rows = second.stdout.split("\npiece", 1)[1]
    assert not [ln for ln in rows.splitlines() if ln.rstrip().endswith(("  installed", "  merged", "  updated"))]


def test_user_allowlist_survives_and_stays_first(tmp_path):
    junie = tmp_path / "home" / ".junie"
    junie.mkdir(parents=True)
    mine = {"defaultBehavior": "ask",
            "rules": {"executables": {"rules": [{"prefix": "git status", "action": "ask"}]}}}
    (junie / "allowlist.json").write_text(json.dumps(mine), encoding="utf-8")
    r = run_install(tmp_path, "--tool", "junie", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads((junie / "allowlist.json").read_text(encoding="utf-8"))
    rules = got["rules"]["executables"]["rules"]
    assert rules[0] == {"prefix": "git status", "action": "ask"}  # first match wins: the user's ask holds
    assert {"prefix": "git branch --show-current", "action": "allow"} in rules
    assert got["defaultBehavior"] == "ask"
    backups = list(junie.glob("allowlist.json.bak-*"))
    assert len(backups) == 1 and json.loads(backups[0].read_text(encoding="utf-8")) == mine


def test_cursor_keeps_required_keys_and_user_values(tmp_path):
    cur = tmp_path / "home" / ".cursor"
    cur.mkdir(parents=True)
    (cur / "cli-config.json").write_text(json.dumps(
        {"version": 1, "editor": {"vimMode": True}, "permissions": {"allow": ["Shell(ls)"], "deny": []}}),
        encoding="utf-8")
    r = run_install(tmp_path, "--tool", "cursor", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads((cur / "cli-config.json").read_text(encoding="utf-8"))
    assert got["version"] == 1 and got["editor"]["vimMode"] is True
    assert got["permissions"]["allow"] == ["Shell(ls)"]
    assert got["attribution"] == {"attributeCommitsToAgent": False, "attributePRsToAgent": False}
    assert "Cursor Settings > Rules" in r.stdout


def test_failure_saves_a_redacted_report_and_sends_nothing(tmp_path):
    gem = tmp_path / "home" / ".gemini" / "antigravity-cli"
    gem.mkdir(parents=True)
    (gem / "settings.json").write_text('{"permissions": {"allow": [,]}}', encoding="utf-8")
    r = run_install(tmp_path, "--tool", "antigravity", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 1
    assert "Nothing was sent" in r.stdout and "https://github.com/" in r.stdout
    reports = list((tmp_path / "claude-starter-reports").glob("install-failure-*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "not valid JSON" in text
    assert str(tmp_path / "home") not in text and str(tmp_path / "home").replace("\\", "/") not in text
    assert (gem / "settings.json").read_text(encoding="utf-8") == '{"permissions": {"allow": [,]}}'


def test_auto_picks_the_single_detected_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "detect", lambda: {"junie": ["~/.junie exists"], "codex": []})
    env = sandbox_env(tmp_path)
    monkeypatch.setattr(os, "environ", env)
    assert install.run(["--tool", "auto", "--tier", "starter", "--dry-run"]) == 0
    assert install.CTX["tool"] == "junie"


def test_auto_refuses_to_guess_between_several(monkeypatch, capsys):
    monkeypatch.setattr(install, "detect", lambda: {"junie": ["a"], "codex": ["b"]})
    assert install.run(["--tool", "auto", "--tier", "starter", "--dry-run"]) == 2
    assert "pass --tool explicitly" in capsys.readouterr().err


def test_frontmatter_parser_reads_what_the_adapters_write():
    fm = install.parse_frontmatter('---\nname: "a"\ndescription: >-\n  two\n  lines\ntools: ["Read"]\n'
                                   '# comment\n---\nbody')
    assert fm == {"name": "a", "description": "two lines", "tools": ["Read"]}
    with pytest.raises(ValueError):
        install.parse_frontmatter("---\nnot yaml at all\n---\n")


# --------------------------------------------------------------------------
# starter-update, the update notice and the version home
# --------------------------------------------------------------------------

REPO = SCRIPTS.parent
COMMAND_PATHS = ba.COMMAND_PATHS


def _built() -> dict:
    src = ba.load_sources()
    return {t: emit(src) for t, emit in ba.EMITTERS.items()}


def _update_texts() -> dict:
    texts = {"claude (source)": (REPO / "plugins/starter/commands/starter-update.md").read_bytes().decode("utf-8")}
    for t, files in _built().items():
        texts[t] = files[COMMAND_PATHS[t].format(n="starter-update")]
    return texts


def test_every_tool_maps_its_command_paths():
    assert set(COMMAND_PATHS) == set(ba.EMITTERS) | {"claude"} == set(ba.BUILDS)


@pytest.mark.parametrize("name", ba.PORTED_COMMANDS)
def test_every_ported_command_is_in_every_tool(name):
    built = _built()
    for t, files in built.items():
        assert COMMAND_PATHS[t].format(n=name) in files, (t, name)
    assert (REPO / "adapters" / "antigravity" / "config" / "skills" / name / "SKILL.md").is_file()


def test_a_ported_command_named_like_a_builtin_stops_the_build(monkeypatch):
    with pytest.raises(SystemExit, match="'update' is a built-in opencode command"):
        ba.check_builtin_collisions(["checkpoint", "update"])
    monkeypatch.setattr(ba, "PORTED_COMMANDS", ba.PORTED_COMMANDS + ("update",))
    with pytest.raises(SystemExit, match="collide with built-ins"):
        ba.load_sources()


def test_shipped_command_names_avoid_builtins():
    ba.check_builtin_collisions(ba.PORTED_COMMANDS)
    assert "update" in ba.BUILTIN_COMMANDS["opencode"]


def test_kit_json_is_the_version_every_manifest_carries():
    kit = json.loads((REPO / "kit.json").read_text(encoding="utf-8"))
    assert set(kit) == {"name", "version"} and kit["name"] == "claude-starter"
    assert re.fullmatch(r"\d+\.\d+\.\d+", kit["version"])
    plugin = json.loads((REPO / "plugins/starter/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert market["name"] == kit["name"]
    assert plugin["version"] == kit["version"]
    assert [p["version"] for p in market["plugins"]] == [kit["version"]]


@pytest.mark.parametrize("tool", ["claude (source)"] + sorted(ba.EMITTERS))
def test_starter_update_shows_the_plan_stops_and_applies_only_after_a_yes(tool):
    text = _update_texts()[tool]
    flat = " ".join(text.split())
    assert "explicitly asks to update this starter kit" in flat
    status = flat.index("starter.py status")
    plan = flat.index("starter.py update`")
    stop = flat.index("END YOUR TURN and wait for the user's reply")
    apply = flat.index("Apply, only after the user's yes.")
    assert status < plan < stop < apply
    assert "Show the user the whole plan" in flat
    assert "`--to <sha>` and `--plan <id>`" in flat
    assert "proves that a plan was printed, not that the user read it" in flat
    assert "python ~/.claude-starter/scripts/starter.py update" in text
    assert 'python "$HOME\\.claude-starter\\scripts\\starter.py" update' in text
    assert "--no-guard" in flat and "never choose for them" in flat
    if tool != "claude (source)":
        assert "claude plugin marketplace update" not in text


def test_codex_command_skills_carry_a_no_implicit_invocation_policy():
    """Codex starts a skill on its own unless agents/openai.yaml says otherwise (its default is true)."""
    built = _built()
    for name in ba.PORTED_COMMANDS:
        data = install.parse_skill_metadata(built["codex"][f"skills/{name}/agents/openai.yaml"])
        assert data == {"policy": {"allow_implicit_invocation": False}}, name
    for t, files in built.items():  # Codex-only: the shared SKILL.md copies stay byte-identical
        assert t == "codex" or not [r for r in files if r.endswith("agents/openai.yaml")], t
    ba.check_shared_skills(built)


def test_codex_install_checks_the_skill_policy_and_names_it(tmp_path):
    r = run_install(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    policy = tmp_path / "home" / ".agents" / "skills" / "starter-update" / "agents" / "openai.yaml"
    assert "allow_implicit_invocation: false" in policy.read_text(encoding="utf-8")
    assert "skill starter-update policy (shared)" in r.stdout and "allow_implicit_invocation: false" in r.stdout


def test_skill_policy_check_rejects_a_file_codex_would_read_otherwise(tmp_path):
    skill = tmp_path / "skills" / "x"
    (skill / "agents").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: x\ndescription: d\n---\n", encoding="utf-8")
    f = skill / "agents" / "openai.yaml"
    step = install.Step("skill x policy", f, "file")
    f.write_text(ba.CODEX_SKILL_POLICY.format(name="x"), encoding="utf-8")
    assert install.check_file("codex", step) is None
    f.write_text('interface:\n  display_name: "X"\npolicy:\n  allow_implicit_invocation: false\n', encoding="utf-8")
    assert install.check_file("codex", step) is None
    f.write_text("policy:\n  allow_implicit_invocation: true\n", encoding="utf-8")
    assert "expected false" in install.check_file("codex", step)
    f.write_text("interface:\n  display_name: x\n", encoding="utf-8")
    assert "expected false" in install.check_file("codex", step)
    for bad in ("policy: {allow_implicit_invocation: false}\n", "policy:\n  allow_implicit: false\n",
                "policy:\n  allow_implicit_invocation: false\nextra:\n", "dependencies:\n  tools:\n",
                "policy:\n    allow_implicit_invocation: false\n"):
        f.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            install.check_file("codex", step)
    (skill / "SKILL.md").unlink()
    f.write_text(ba.CODEX_SKILL_POLICY.format(name="x"), encoding="utf-8")
    assert "no SKILL.md" in install.check_file("codex", step)


PER_USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|(?<![\w.~])/(?:Users|home)/[^\s/]+/|/c/Users/")


def test_per_user_path_check_fires():
    for bad in ("C:\\Users\\someone\\.claude-starter", "/home/someone/.claude-starter", "/c/Users/x/y",
                "/Users/someone/kit"):
        assert PER_USER_PATH.search(bad), bad
    assert not PER_USER_PATH.search('python ~/.claude-starter/x.py and "$HOME\\.claude-starter\\x.py"')


def test_generated_files_carry_no_per_user_path():
    """Shared skills must be byte-identical for every user (build_adapters.SHARED_SKILLS_TOOLS), so the
    kit is always named by its documented location, never by the builder's own home."""
    for t, files in _built().items():
        for rel, text in files.items():
            m = PER_USER_PATH.search(text)
            assert not m, f"{t}/{rel}: {m.group(0)!r}"
    for name in ba.PORTED_COMMANDS:
        text = (REPO / "plugins/starter/commands" / f"{name}.md").read_bytes().decode("utf-8")
        assert not PER_USER_PATH.search(text), name


@pytest.mark.parametrize("name", ["checkpoint", "lanes"])
def test_checkpoint_and_lanes_relay_the_update_notice_first(name):
    for t, files in _built().items():
        text = files[COMMAND_PATHS[t].format(n=name)]
        body = text.split("\n---\n", 1)[-1]
        first = body.index("update_check.py")
        assert first < body.index("pass that line on to the user"), t
        for later in ("In order:", "## 1."):
            if later in body:
                assert first < body.index(later), (t, name)


# --------------------------------------------------------------------------
# SessionStart update notice (Claude Code plugin hook)
# --------------------------------------------------------------------------

NOTICE = REPO / "plugins" / "starter" / "hooks" / "update-notice" / "notice.py"
LINE = ("claude-starter v9.9.9 is available (you have v0.4.0). "
        "Ask your agent to run starter-update to see what changed.")


def run_notice(tmp_path: Path, stub: "str | None", where: str = ".claude-starter",
               record: "dict | None" = None) -> subprocess.CompletedProcess:
    home = tmp_path / "home"
    if stub is not None:
        scripts = home / where / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "update_check.py").write_text(stub, encoding="utf-8")
    if record is not None:
        rec = home / ".agents" / "starter"
        rec.mkdir(parents=True, exist_ok=True)
        (rec / "installs.json").write_text(json.dumps(record), encoding="utf-8")
    return subprocess.run([sys.executable, str(NOTICE)], env=sandbox_env(tmp_path), capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def test_notice_hook_shows_the_line_to_the_user_and_the_model(tmp_path):
    r = run_notice(tmp_path, f"print({LINE!r})\n")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["systemMessage"] == LINE
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert LINE in out["hookSpecificOutput"]["additionalContext"]


def test_notice_hook_follows_the_recorded_kit_root(tmp_path):
    """The record is built by install.py itself, so the hook is checked against the shape it writes."""
    kit = tmp_path / "home" / "elsewhere"
    record = install.new_record()
    record["kit"] = install.kit_facts(kit, sha="0" * 40)
    r = run_notice(tmp_path, f"print({LINE!r})\n", where="elsewhere", record=record)
    assert r.returncode == 0 and r.stdout, (r.stdout, r.stderr)
    assert json.loads(r.stdout)["systemMessage"] == LINE


@pytest.mark.parametrize("stub", [
    None,                                        # no clone at all
    "",                                          # notices off, or nothing newer: no output
    f"import sys\nprint({LINE!r})\nsys.exit(1)\n",  # a failing check is not relayed
    "raise SystemExit('boom')\n",
    "print('one')\nprint('two')\n",              # anything but exactly one line is not the notice
])
def test_notice_hook_is_silent_and_exits_0_otherwise(tmp_path, stub):
    r = run_notice(tmp_path, stub)
    assert r.returncode == 0 and r.stdout == "", (r.stdout, r.stderr)


def test_hooks_json_runs_the_notice_at_session_start():
    hooks = json.loads((REPO / "plugins/starter/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    (entry,) = hooks["SessionStart"]
    (h,) = entry["hooks"]
    assert entry["matcher"] == "startup" and h["type"] == "command"
    rel = re.search(r"\}\"?/(hooks/update-notice/run\.sh)$", h["command"]).group(1)
    assert (REPO / "plugins" / "starter" / rel).is_file()
    assert 0 < h["timeout"] <= 30


# --------------------------------------------------------------------------
# Entry docs
# --------------------------------------------------------------------------

APPLY_CMD = re.compile(r"install\.py[^`\n]*--yes[^`\n]*")


def guardless_applies(text: str) -> list:
    """Every literal `install.py ... --yes` command that names neither --guard-repo nor --no-guard: an
    agent that copies one as shown gets exit 2."""
    return [m.group(0) for m in APPLY_CMD.finditer(text)
            if "--guard-repo" not in m.group(0) and "--no-guard" not in m.group(0)]


def test_guardless_apply_check_fires():
    assert guardless_applies("run `python ~/.claude-starter/scripts/install.py --tool x --tier starter --yes`")
    assert not guardless_applies("`python install.py --tool x --yes --no-guard`")
    assert not guardless_applies("`python install.py --tool x --yes --guard-repo <path>`")


@pytest.mark.parametrize("doc", ["README.md", "AGENTS.md"])
def test_entry_docs_apply_commands_carry_a_guard_answer(doc):
    assert guardless_applies((REPO / doc).read_text(encoding="utf-8")) == []


# --------------------------------------------------------------------------
# Release bookkeeping: CHANGELOG.md lists every migration, and a changed kit carries a new version
# --------------------------------------------------------------------------

import migrations  # noqa: E402


def changelog_missing_ids(mig_dir: Path, changelog: str) -> list:
    """Migration IDs in mig_dir that CHANGELOG.md never names. starter-update shows the changelog as the
    account of what each migration does, so an unlisted one runs unexplained."""
    ids = [m.ID for m in migrations.discover(mig_dir)]
    return [i for i in ids if not re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", changelog)]


def test_changelog_check_fires_on_an_unlisted_migration(tmp_path, monkeypatch):
    monkeypatch.delenv(migrations.TEST_DIR_ENV, raising=False)
    (tmp_path / "0001_demo.py").write_text('ID = "0001-demo"\nTITLE = "demo"\ndef plan(ctx):\n    return []\n',
                                           encoding="utf-8")
    assert changelog_missing_ids(tmp_path, "### Migrations\n\n- `0001-demo-two`: other\n") == ["0001-demo"]
    assert changelog_missing_ids(tmp_path, "### Migrations\n\n- `0001-demo`: demo\n") == []


def test_every_migration_id_is_in_the_changelog(monkeypatch):
    monkeypatch.delenv(migrations.TEST_DIR_ENV, raising=False)
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog_missing_ids(SCRIPTS / "migrations", text) == []


RELEASE_TAG = "v[0-9]*.[0-9]*.[0-9]*"
VERSIONED = ("plugins", "adapters", "scripts")


def _git(*args: str) -> "tuple[int, str]":
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    return r.returncode, r.stdout.strip()


def _version_at(rev: "str | None") -> str:
    """The kit version at rev (None: the working tree). Before kit.json existed, plugin.json held it."""
    for rel in ("kit.json", "plugins/starter/.claude-plugin/plugin.json"):
        if rev is None:
            p = REPO / rel
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))["version"]
        else:
            rc, out = _git("show", f"{rev}:{rel}")
            if rc == 0:
                return json.loads(out)["version"]
    raise AssertionError(f"no version file at {rev or 'the working tree'}")


def bump_problem(rev: "str | None") -> "str | None":
    """Why the version at rev (None: the working tree) is wrong, or None. When plugins/, adapters/ or
    scripts/ changed since the newest release tag before rev, the version must be above that tag's,
    or an install from the changed tree records the old version and the updater calls it current."""
    rc, tag = _git("describe", "--tags", "--abbrev=0", "--match", RELEASE_TAG, rev or "HEAD")
    if rc:
        pytest.skip("no release tag reachable (a shallow clone fetches none); CI checks out full history")
    changed = _git("diff", "--name-only", tag, *([rev] if rev else []), "--", *VERSIONED)[1].split()
    if rev is None:
        changed += _git("ls-files", "--others", "--exclude-standard", "--", *VERSIONED)[1].split()
    have = _version_at(rev)
    if changed and tuple(map(int, have.split("."))) <= tuple(map(int, tag[1:].split("."))):
        return (f"{len(changed)} file(s) under {', '.join(VERSIONED)} changed since {tag} (first: {changed[0]}), "
                f"but the version is still {have}: bump kit.json, plugin.json and marketplace.json")
    return None


def test_version_bump_check_fires_on_a_commit_that_changed_the_kit_without_one():
    if _git("cat-file", "-e", "de5d558^{commit}")[0]:
        pytest.skip("de5d558 is not in this clone's history")
    problem = bump_problem("de5d558")
    assert problem and "changed since v0.3.1" in problem, problem


def test_version_is_bumped_when_the_kit_changed_since_the_last_release():
    assert bump_problem(None) is None

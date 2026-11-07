"""Tests for scripts/build_adapters.py and scripts/install.py.

Installs run in a throwaway HOME (tmp_path) with every relocation variable cleared, so nothing here
touches a real tool config. Real tools are only used when they are on PATH (codex, opencode).
"""
import json
import os
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
    first = run_install(tmp_path, "--tool", tool, "--tier", "starter", "--yes")
    assert first.returncode == 0, first.stdout + first.stderr
    assert "passed" not in first.stdout.split("load check", 1)[1].splitlines()[0] or tool == "codex"
    if tool != "codex":
        assert "structurally checked; not verified against the real tool" in first.stdout
    second = run_install(tmp_path, "--tool", tool, "--tier", "starter", "--yes")
    assert second.returncode == 0, second.stdout + second.stderr
    rows = second.stdout.split("\npiece", 1)[1]
    assert not [ln for ln in rows.splitlines() if ln.rstrip().endswith(("  installed", "  merged", "  updated"))]


def test_user_allowlist_survives_and_stays_first(tmp_path):
    junie = tmp_path / "home" / ".junie"
    junie.mkdir(parents=True)
    mine = {"defaultBehavior": "ask",
            "rules": {"executables": {"rules": [{"prefix": "git status", "action": "ask"}]}}}
    (junie / "allowlist.json").write_text(json.dumps(mine), encoding="utf-8")
    r = run_install(tmp_path, "--tool", "junie", "--tier", "starter", "--yes")
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
    r = run_install(tmp_path, "--tool", "cursor", "--tier", "starter", "--yes")
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
    r = run_install(tmp_path, "--tool", "antigravity", "--tier", "starter", "--yes")
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

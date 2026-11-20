"""Installer behaviour: preflight, merges that keep the user's bytes, the printed update commands and
what the console shows. Every install runs in a throwaway HOME (see test_adapters.sandbox_env)."""
import argparse
import errno
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_adapters as ba  # noqa: E402
import install  # noqa: E402
from test_adapters import run_install, sandbox_env  # noqa: E402

OC_PERMS = install.ADAPTERS / "opencode" / "opencode.permission.json"
SECRET = "hunter2" + "hunter2"


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ---- 6. OpenCode: a user "*" deny/ask blocks every kit allow ----------------

@pytest.mark.parametrize("star", ["deny", "ask"])
def test_opencode_star_deny_or_ask_blocks_kit_allows(tmp_path, star):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"permission": {"bash": {"*": star, "ls": "allow"}}}), encoding="utf-8")
    s = install.plan_json(OC_PERMS, cfg)
    merged = json.loads(s.payload) if s.payload else json.loads(cfg.read_text(encoding="utf-8"))
    assert list(merged["permission"]["bash"]) == ["*", "ls"], merged
    assert any(f"kept your '*' = {star}; kit allows not added" in n for n in s.notes), s.notes


def test_opencode_star_allow_still_gets_kit_allows(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"permission": {"bash": {"*": "allow"}}}), encoding="utf-8")
    merged = json.loads(install.plan_json(OC_PERMS, cfg).payload)
    assert "git status" in merged["permission"]["bash"]


# ---- 7. the update line reproduces the install --------------------------------

def _ps_split(cmd: str) -> list:
    """Split a PowerShell command made of bare words and single-quoted strings ('' is a quote)."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == " ":
            i += 1
        elif cmd[i] == "'":
            j, buf = i + 1, []
            while True:
                if cmd[j] == "'" and cmd[j + 1:j + 2] == "'":
                    buf.append("'")
                    j += 2
                elif cmd[j] == "'":
                    break
                else:
                    buf.append(cmd[j])
                    j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            j = cmd.find(" ", i)
            j = len(cmd) if j < 0 else j
            word = cmd[i:j]
            assert not set(word) & set("'\"$`&;|(){}@"), f"unquoted special character in {word!r}"
            out.append(word)
            i = j
    return out


def _flags(argv: list) -> dict:
    got: dict = {}
    for i, a in enumerate(argv):
        if a.startswith("--") and a != "--yes":
            got.setdefault(a, []).append(argv[i + 1])
    return got


def test_update_commands_reproduce_every_flag(tmp_path):
    cfg, proj = tmp_path / "O'Neil cfg", tmp_path / "my proj"
    g1, g2 = tmp_path / "g1", tmp_path / "it's g2"
    args = argparse.Namespace(tool="cursor", tier="full", config_dir=cfg, project=proj,
                              guard_repo=[str(g1), str(g2)])
    bash, ps = install.update_commands(args)
    assert len(bash) == 2 and len(ps) == 2
    assert not [ln for ln in bash + ps if "&&" in ln]
    for split, lines, form in ((shlex.split, bash, lambda p: p.as_posix()), (_ps_split, ps, str)):
        git, py = split(lines[0]), split(lines[1])
        assert git[0] == "git" and git[1] == "-C" and git[-1] == "pull"
        assert Path(git[2]) == install.ROOT
        assert py[0] == "python" and Path(py[1]) == install.ROOT / "scripts" / "install.py"
        assert py[-1] == "--yes"
        assert _flags(py) == {"--tool": ["cursor"], "--tier": ["full"],
                              "--config-dir": [form(cfg.resolve())], "--project": [form(proj.resolve())],
                              "--guard-repo": [form(g1.resolve()), form(g2.resolve())]}


@pytest.mark.skipif(not shutil.which("powershell"), reason="Windows PowerShell 5.1 not available")
def test_powershell_form_really_parses(tmp_path):
    args = argparse.Namespace(tool="generic", tier="starter", config_dir=tmp_path / "O'Neil cfg",
                              project=None, guard_repo=[])
    _, ps = install.update_commands(args)
    exe = "'" + sys.executable.replace("'", "''") + "'"
    echo = "& " + exe + " -c 'import sys,json;print(json.dumps(sys.argv[1:]))'"
    line = ps[1].replace("python", echo, 1)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", line],
                       capture_output=True, text=True, timeout=60)
    argv = json.loads(r.stdout.strip().splitlines()[-1])
    assert _flags(argv)["--config-dir"] == [str((tmp_path / "O'Neil cfg").resolve())]


def test_install_prints_both_update_forms(tmp_path):
    cfg = tmp_path / "O'Neil cfg"
    r = run_install(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(cfg), "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "update later (bash" in r.stdout and "update later (PowerShell" in r.stdout
    assert r.stdout.count("--config-dir") >= 2


# ---- 11. preflight: a bad target means nothing is written ----------------------

def test_malformed_json_writes_nothing(tmp_path):
    gem = tmp_path / "home" / ".gemini" / "antigravity-cli"
    gem.mkdir(parents=True)
    (gem / "settings.json").write_text('{"permissions": {"allow": [,]}}', encoding="utf-8")
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "antigravity", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode != 0
    assert snapshot(tmp_path / "home") == before
    assert "preflight" in (r.stdout + r.stderr).lower()
    assert list((tmp_path / "claude-starter-reports").glob("install-failure-*.md"))


def test_utf16_json_is_named_and_nothing_written(tmp_path):
    junie = tmp_path / "home" / ".junie"
    junie.mkdir(parents=True)
    (junie / "allowlist.json").write_bytes('{"rules": {}}'.encode("utf-16"))
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "junie", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode != 0
    assert "UTF-16" in r.stdout + r.stderr
    assert snapshot(tmp_path / "home") == before


def test_utf16_rules_file_writes_nothing(tmp_path):
    codex = tmp_path / "home" / ".codex"
    codex.mkdir(parents=True)
    (codex / "AGENTS.md").write_bytes("# mine\r\n".encode("utf-16"))
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode != 0
    assert "UTF-16" in r.stdout + r.stderr
    assert snapshot(tmp_path / "home") == before


def test_missing_opencode_binary_writes_nothing(tmp_path):
    env = sandbox_env(tmp_path)
    empty = tmp_path / "emptybin"
    empty.mkdir()
    env.update(PATH=str(empty), XDG_CONFIG_HOME=str(tmp_path / "home" / ".config"))
    r = subprocess.run([sys.executable, str(SCRIPTS / "install.py"), "--tool", "opencode", "--tier", "starter",
                        "--yes"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    assert r.returncode != 0
    assert "`opencode` not found" in r.stdout + r.stderr
    assert snapshot(tmp_path / "home") == {}


# ---- 12. line endings and BOM ---------------------------------------------------

def test_rules_append_keeps_mixed_line_endings_byte_identical(tmp_path):
    dest = tmp_path / "AGENTS.md"
    mine = b"line one\r\nline two\nline three\r\n"
    dest.write_bytes(mine)
    s = install.plan_rules(install.ADAPTERS / "codex" / "AGENTS.starter.md", dest)
    assert s.status == "merge"
    assert s.payload.startswith(mine)
    block = s.payload[len(mine):]
    assert block.count(b"\r\n") == block.count(b"\n")  # the block takes the file's dominant ending


def test_rules_replace_keeps_user_lines_byte_identical(tmp_path):
    dest = tmp_path / "AGENTS.md"
    head = b"# mine\r\nkeep me\n"
    tail = b"after\r\nlast line no newline"
    old = (install.BEGIN + "\nstale rules\n" + install.END + "\n").encode()
    dest.write_bytes(head + old + tail)
    s = install.plan_rules(install.ADAPTERS / "codex" / "AGENTS.starter.md", dest)
    assert s.status == "merge"
    assert s.payload.startswith(head) and s.payload.endswith(tail)
    assert b"stale rules" not in s.payload


def test_rules_rerun_with_crlf_block_is_a_no_op(tmp_path):
    dest = tmp_path / "AGENTS.md"
    src = install.ADAPTERS / "codex" / "AGENTS.starter.md"
    s = install.plan_rules(src, dest)
    dest.write_bytes(b"# mine\r\n\r\n" + s.payload.replace(b"\n", b"\r\n"))
    assert install.plan_rules(src, dest).status == "already installed"


def test_json_merge_keeps_bom_and_crlf_and_says_so(tmp_path):
    dest = tmp_path / "opencode.json"
    dest.write_bytes(b"\xef\xbb\xbf{\r\n  \"theme\": \"dark\"\r\n}\r\n")
    s = install.plan_json(OC_PERMS, dest)
    assert s.status == "merge"
    assert s.payload.startswith(b"\xef\xbb\xbf")
    assert s.payload.count(b"\n") == s.payload.count(b"\r\n")
    assert json.loads(s.payload.decode("utf-8-sig"))["theme"] == "dark"
    assert "re-serialised" in s.detail and "BOM" in s.detail and "CRLF" in s.detail


def test_json_merges_into_opencode_first_run_jsonc_stub(tmp_path):
    # OpenCode writes this stub on first run; skipping it left every fresh install without perms.
    stub = tmp_path / "opencode.jsonc"
    stub.write_text('{\n  "$schema": "https://opencode.ai/config.json"\n}\n', encoding="utf-8")
    s = install.plan_json(OC_PERMS, tmp_path / "opencode.json")
    assert s.status == "merge" and s.dest == stub
    merged = json.loads(s.payload)
    assert merged["$schema"] == "https://opencode.ai/config.json"
    assert install.contains(merged, json.loads(OC_PERMS.read_text(encoding="utf-8")))


def test_json_still_skips_a_jsonc_with_comments(tmp_path):
    (tmp_path / "opencode.jsonc").write_text('{\n  // mine\n  "theme": "dark"\n}\n', encoding="utf-8")
    s = install.plan_json(OC_PERMS, tmp_path / "opencode.json")
    assert s.status == "skipped" and "by hand" in s.detail


# ---- 13. misconverted kit path -------------------------------------------------

def test_installer_warns_when_running_from_a_misconverted_path(monkeypatch, capsys):
    monkeypatch.setattr(install, "ROOT", Path(r"C:\c\Users\x\claude-starter"))
    monkeypatch.setattr(install, "detect", lambda: {})
    assert install.main(["--detect"]) == 0
    err = capsys.readouterr().err
    assert "Git Bash" in err and "re-clone" in err.lower()
    assert r'git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"' in err


# ---- 15. load-check output is redacted on the console --------------------------

def test_load_check_output_is_redacted_before_printing(monkeypatch, capsys):
    monkeypatch.setattr(install, "report_failure", lambda text: None)
    args = argparse.Namespace(tool="opencode", tier="starter", config_dir=None, project=None, guard_repo=[])
    lines = ["`opencode agent list` exited 1:", f"config: OPENROUTER_API_KEY={SECRET}",
             "token sk-ant-" + "abcdefghijklmnop"]
    install.finish_run("opencode", "starter", [], False, lines, "FAILED", [], args, [])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and "abcdefghijklmnop" not in out.out + out.err
    assert "<redacted:" in out.out


# ---- 16. generic install and auto with nothing found ----------------------------

def test_generic_install_says_read_only_by_instruction_only(tmp_path):
    r = run_install(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"),
                    "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "READ-ONLY BY INSTRUCTION ONLY" in "\n".join(for_you_tail(r.stdout))


def test_auto_with_nothing_detected_names_the_next_step(monkeypatch, capsys):
    monkeypatch.setattr(install, "detect", lambda: {"codex": [], "junie": []})
    assert install.run(["--tool", "auto", "--tier", "starter", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert "--tool generic --config-dir <dir>" in err and "--tool <name>" in err


# ---- 9 and 10. Codex rules and the consultant -----------------------------------

@pytest.mark.skipif(not shutil.which("codex"), reason="codex not installed")
@pytest.mark.parametrize("cmd,allowed", [("git status", True), ("git push", False),
                                         ("git branch x", False),
                                         ("ruff format --check --cache-dir x", False),
                                         ("ruff format --check", False)])
def test_codex_execpolicy_on_generated_rules(cmd, allowed):
    rules = install.ADAPTERS / "codex" / "rules" / "claude-starter.rules"
    r = subprocess.run([shutil.which("codex"), "execpolicy", "check", "--rules", str(rules), "--", *cmd.split()],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    decision = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]).get("decision")
    assert (decision == "allow") is allowed, (cmd, decision)


def test_codex_consultant_disables_both_shell_tools_and_says_it_is_unverified():
    files = ba.EMITTERS["codex"](ba.load_sources())
    toml = files["agents/consultant.toml"]
    feats = toml.split("[features]", 1)[1]
    assert re.search(r"^shell_tool = false$", feats, re.M) and re.search(r"^unified_exec = false$", feats, re.M)
    phrase = "not verified that Codex honours [features] in agent files"
    assert phrase in toml
    for rel, text in files.items():
        assert "shell is off" not in text and "shell is switched off" not in text, rel
    notes = " ".join(install.notes_codex(Path("x"), argparse.Namespace()))
    assert phrase in notes and "shell is off" not in notes


# ---- a top-level OpenCode permission blocks kit allows too --------------------------

@pytest.mark.parametrize("perm", [{"*": "deny"}, {"*": "ask"}, "deny", "ask"],
                         ids=["star-deny", "star-ask", "string-deny", "string-ask"])
def test_opencode_top_level_permission_blocks_kit_bash_allows(tmp_path, perm):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"permission": perm}), encoding="utf-8")
    s = install.plan_json(OC_PERMS, cfg)
    merged = json.loads(s.payload) if s.payload else json.loads(cfg.read_text(encoding="utf-8"))
    p = merged["permission"]
    bash = p.get("bash", {}) if isinstance(p, dict) else {}
    assert not [k for k, v in bash.items() if v == "allow"], merged
    if isinstance(perm, dict):
        assert p["*"] == perm["*"]
    else:
        assert p == perm
    want = perm["*"] if isinstance(perm, dict) else perm
    assert any(n.startswith("permission:") and f"= {want}; kit allows not added" in n for n in s.notes), s.notes


# ---- replacing a block at line 1 keeps the file's BOM ---------------------------------

def test_rules_replace_at_line_one_keeps_the_bom(tmp_path):
    dest = tmp_path / "AGENTS.md"
    src = install.ADAPTERS / "codex" / "AGENTS.starter.md"
    dest.write_bytes(("﻿" + install.BEGIN + "\nstale rules\n" + install.END + "\nmine after\n").encode("utf-8"))
    s = install.plan_rules(src, dest)
    assert s.status == "merge"
    assert s.payload.startswith(b"\xef\xbb\xbf" + install.BEGIN.encode()), s.payload[:20]
    assert s.payload.endswith(b"mine after\n") and b"stale rules" not in s.payload
    dest.write_bytes(s.payload)
    assert install.plan_rules(src, dest).status == "already installed"


# ---- a preflight failure does not run the tool -----------------------------------------

def _fake_tool(bindir: Path, name: str) -> Path:
    """A stand-in for a tool binary that appends to $FAKE_TOOL_MARKER whenever it is run."""
    bindir.mkdir(exist_ok=True)
    if os.name == "nt":
        exe = bindir / f"{name}.cmd"
        exe.write_text('@echo off\r\necho called %*>>"%FAKE_TOOL_MARKER%"\r\necho 9.9.9\r\n', encoding="ascii")
    else:
        exe = bindir / name
        exe.write_text('#!/bin/sh\necho "called $*" >> "$FAKE_TOOL_MARKER"\necho 9.9.9\n', encoding="ascii")
        exe.chmod(0o755)
    return exe


def test_preflight_failure_does_not_probe_the_tool_version(tmp_path):
    env = sandbox_env(tmp_path)
    marker = tmp_path / "tool-was-run.txt"
    exe = _fake_tool(tmp_path / "fakebin", "opencode")
    env.update(PATH=str(tmp_path / "fakebin") + os.pathsep + env.get("PATH", ""),
               XDG_CONFIG_HOME=str(tmp_path / "home" / ".config"), FAKE_TOOL_MARKER=str(marker))
    # The stand-in really does leave a marker when it is run, so its absence below means something.
    subprocess.run([str(exe), "--version"], env=env, capture_output=True, timeout=60)
    assert marker.exists()
    marker.unlink()
    oc = tmp_path / "home" / ".config" / "opencode"
    oc.mkdir(parents=True)
    (oc / "opencode.json").write_text('{"permission": {,}}', encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "install.py"), "--tool", "opencode", "--tier", "starter",
                        "--yes"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    assert r.returncode != 0 and "preflight FAILED" in r.stderr, r.stdout + r.stderr
    assert not marker.exists(), marker.read_text()
    saved = list((tmp_path / "claude-starter-reports").glob("install-failure-*.md"))
    assert saved and "version not probed (preflight failure)" in saved[0].read_text(encoding="utf-8")


# ---- console output is redacted: crash tracebacks and tool notes -----------------------

def test_crash_traceback_is_redacted_on_the_console(monkeypatch, capsys):
    monkeypatch.setattr(install, "report_failure", lambda *a, **k: None)

    def boom(argv):
        raise RuntimeError(f"config said OPENROUTER_API_KEY={SECRET}")
    monkeypatch.setattr(install, "run", boom)
    assert install.main([]) == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err and SECRET not in err and "<redacted:" in err, err


def test_tool_notes_are_redacted_on_the_console(monkeypatch, capsys):
    monkeypatch.setattr(install, "report_failure", lambda *a, **k: None)
    args = argparse.Namespace(tool="claude", tier=None, config_dir=None, project=None, guard_repo=[])
    s = install.Step("plugin starter@claude-starter", Path("cfg"), "cli", status="installed",
                     notes=[f"warning: env ANTHROPIC_API_KEY={SECRET} ignored"])
    install.finish_run("claude", None, [s], True, [], "passed", [], args, [])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and "<redacted:" in out.out, out.out


# ---- the run ends with the "For you" block ----------------------------------------------
# Tests below strip the Codex agent markers: the suite may itself run inside a Codex session.

MARKERS = (*install.CODEX_MARKERS, "CLAUDECODE")


def clean_env(tmp_path: Path) -> dict:
    env = sandbox_env(tmp_path)
    for k in [k for k in env if k.startswith("CODEX_") or k in MARKERS]:
        del env[k]
    return env


def run_clean(tmp_path: Path, *args: str, extra: dict = None) -> subprocess.CompletedProcess:
    env = clean_env(tmp_path)
    env.update(extra or {})
    return subprocess.run([sys.executable, str(SCRIPTS / "install.py"), *args], env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)


@pytest.fixture
def sandboxed(tmp_path, monkeypatch):
    """An in-process run with HOME in tmp_path, no relocation variables and no agent markers."""
    home = tmp_path / "home"
    home.mkdir()
    for k in [k for k in os.environ if k.startswith("CODEX_") or k in MARKERS or k in (
            "COPILOT_HOME", "CURSOR_CONFIG_DIR", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR",
            "XDG_CONFIG_HOME", "COMMIT_GUARD_DIR")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(install, "report_failure", lambda *a, **k: pytest.fail(f"report_failure{a}"))
    return home


def tree(root: Path) -> dict:
    """Every file and folder under root (a folder maps to None), so an empty folder left behind shows."""
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def for_you_tail(stdout: str) -> list:
    """The lines after the For-you header, checked to be the last thing printed."""
    lines = stdout.rstrip("\n").split("\n")
    assert lines.count(install.FOR_YOU) == 1, stdout[-3000:]
    i = lines.index(install.FOR_YOU)
    tail = lines[i + 1:]
    assert tail, stdout[-2000:]
    stray = [ln for ln in tail if not re.match(r"\d+\. |   ", ln)]
    assert not stray, f"output after the For-you items: {stray}"
    assert "update later (PowerShell" in "\n".join(lines[:i]), "footer must come before the For-you block"
    return tail


def test_every_tool_must_say_what_its_user_does_next():
    for missing in ("after", "next_steps"):
        kw = {"after": install.no_notes, "next_steps": install.next_generic}
        del kw[missing]
        with pytest.raises(TypeError):
            install.Tool(None, (), **kw)
    for name, tool in [*install.TOOLS.items(), ("claude", install.CLAUDE)]:
        args = argparse.Namespace(tool=name, tier="starter", config_dir=None, project=None, guard_repo=[])
        assert tool.next_steps(Path("cfg"), args), name


NEEDS_LOADER = {"opencode": "opencode"}


@pytest.mark.parametrize("tool", sorted(install.TOOLS))
def test_successful_install_ends_with_the_for_you_block(tmp_path, tool):
    if tool in NEEDS_LOADER and not shutil.which(NEEDS_LOADER[tool]):
        pytest.skip(f"{tool} not installed; its install needs its loader")
    extra = {"XDG_CONFIG_HOME": str(tmp_path / "home" / ".config")}
    cfg = ("--config-dir", str(tmp_path / "cfg")) if tool == "generic" else ()
    r = run_clean(tmp_path, "--tool", tool, "--tier", "starter", *cfg, "--yes", "--no-guard", extra=extra)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    tail = "\n".join(for_you_tail(r.stdout))
    assert "Commit guard: NOT installed in any repo" in tail and "--guard-repo <your-repo> --yes" in tail
    assert "PowerShell:" in tail
    # An agent relays only this block, so no item may lean on text printed before it.
    assert not re.search(r"\b(above|earlier)\b", tail, re.I), tail
    # The block reports the guard as NOT installed, so no item in it may say the guard checks anything.
    assert not ba.GUARD_CLAIM.search(tail), tail
    if tool == "codex":
        assert "Quit and restart Codex, or open a new chat" in tail
        assert f'`codex debug prompt-input "x"` in a terminal and look for "{install.RULES_MARK}"' in tail
        assert '"claude-starter"' not in tail
        assert "what rules are you following?" in tail
        assert "Limits of this install:\n   - Agents are READ-ONLY BY INSTRUCTION ONLY" in tail
    if tool == "cursor":
        assert "The rules are NOT installed" in tail
        assert f"paste the whole of {install.ADAPTERS / 'cursor' / 'AGENTS.starter.md'}" in tail
        for shell in ("bash", "PowerShell"):
            # the install's guard answer travels with it: without one, the repeat command exits 2
            assert re.search(shell + r": +python .*install\.py'? --tool cursor --tier starter --no-guard "
                             r"--project <your-repo> --yes$", tail, re.M), (shell, tail)
    if tool == "copilot":
        assert str(install.ADAPTERS / "copilot" / "vscode-terminal-autoapprove.json") in tail
        assert "Preferences: Open User Settings (JSON)" in tail
    if tool == "opencode":
        assert "Restart opencode" in tail
    for name in ("RULES ARE NOT INSTALLED YET", "READ-ONLY BY INSTRUCTION ONLY", "No git allow rule"):
        assert r.stdout.count(name) <= 1, f"{name!r} printed outside the For-you block too"


def test_caveats_are_the_last_for_you_item_and_print_nowhere_else(capsys):
    args = argparse.Namespace(tool="generic", tier="starter", config_dir=Path("cfg"), project=None, guard_repo=[])
    s = install.Step("agent verifier", Path("cfg") / "agents" / "verifier.md", "file", status="installed")
    install.finish_run("generic", "starter", [s], True, [], "n/a", ["caveat one", "caveat two\nsecond line"],
                       args, ["do this next"])
    out = capsys.readouterr().out
    tail = for_you_tail(out)
    assert tail[0] == "1. do this next" and tail[1].startswith("2. Commit guard: NOT installed")
    assert tail[-4:] == ["3. Limits of this install:", "   - caveat one", "   - caveat two", "     second line"]
    assert out.count("caveat one") == 1


def test_no_caveats_means_no_limits_item(capsys):
    args = argparse.Namespace(tool="generic", tier="starter", config_dir=Path("cfg"), project=None, guard_repo=[])
    install.finish_run("generic", "starter", [], True, [], "n/a", [], args, ["do this next"])
    assert "Limits of this install" not in capsys.readouterr().out


def test_cursor_project_command_in_for_you_runs_once_the_repo_is_filled_in(tmp_path):
    repo = tmp_path / "it's my repo"
    args = argparse.Namespace(tool="cursor", tier="full", config_dir=None, project=None, guard_repo=[])
    item = install.next_cursor(Path("cfg"), args)[1]
    lines = [ln.strip() for ln in item.split("\n") if ln.strip().startswith(("bash:", "PowerShell:"))]
    assert len(lines) == 2, item
    for line, split, quote, form in ((lines[0], shlex.split, shlex.quote, repo.as_posix()),
                                     (lines[1], _ps_split, install._ps_quote, str(repo))):
        cmd = line.split(":", 1)[1].strip().replace("<your-repo>", quote(form))
        argv = split(cmd)
        assert argv[0] == "python" and Path(argv[1]) == install.ROOT / "scripts" / "install.py"
        assert argv[-1] == "--yes"
        assert _flags(argv) == {"--tool": ["cursor"], "--tier": ["full"], "--project": [form]}


def test_codex_self_check_marker_is_only_in_the_block_the_installer_writes():
    assert install.RULES_MARK == "BEGIN claude-starter rules"
    assert install.RULES_MARK in install.BEGIN and install.BEGIN_RX.match(install.BEGIN)
    # Codex also loads the AGENTS.md of the folder it runs in; the kit's own must not carry the marker,
    # or the check passes inside the clone with nothing installed.
    skip = {"tmp", ".git", ".claude", "node_modules"}
    loaded = [p for p in install.ROOT.rglob("AGENTS*.md") if p.name in ("AGENTS.md", "AGENTS.override.md")
              and not skip & set(p.relative_to(install.ROOT).parts)]
    assert install.ROOT / "AGENTS.md" in loaded
    for p in loaded:
        assert install.RULES_MARK not in p.read_text(encoding="utf-8"), p


@pytest.mark.skipif(not shutil.which("codex"), reason="codex not installed")
def test_codex_self_check_tells_installed_from_not_installed(tmp_path):
    """The For-you self-check, run for real: the marker shows only once the rules are installed, while
    "claude-starter" alone shows inside the kit's clone with nothing installed."""
    codex = tmp_path / "home" / ".codex"
    r = run_clean(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard", extra={"CODEX_HOME": str(codex)})
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    empty, elsewhere = tmp_path / "empty-codex-home", tmp_path / "elsewhere"
    empty.mkdir()
    elsewhere.mkdir()

    def prompt(home: Path, cwd: Path) -> str:
        env = clean_env(tmp_path)
        env["CODEX_HOME"] = str(home)
        p = subprocess.run([shutil.which("codex"), "debug", "prompt-input", "x"], cwd=str(cwd), env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
        assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
        return p.stdout

    assert install.RULES_MARK in prompt(codex, elsewhere)
    in_clone = prompt(empty, install.ROOT)
    assert "claude-starter" in in_clone and install.RULES_MARK not in in_clone


def test_for_you_names_the_guarded_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    r = run_clean(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"),
                  "--guard-repo", str(repo), "--yes")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    tail = "\n".join(for_you_tail(r.stdout))
    assert f"Commit guard: installed as git hooks in {repo.resolve()}" in tail
    assert "NOT installed" not in tail


# ---- --guard-repo on a folder that is not a git repo yet: the installer makes it one ----------------
# Beginners were stalled by being asked for a repo they did not have, so a plain project folder (or
# one that does not exist yet) is made a repo with git init, and only folders where a repo does harm
# are refused.

def _guard_install(tmp_path: Path, target: Path, mode: str = "--yes") -> subprocess.CompletedProcess:
    return run_clean(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"),
                     "--guard-repo", str(target), mode)


def _hooked(repo: Path) -> bool:
    hook = repo / ".git" / "hooks" / "pre-commit"
    return hook.is_file() and "# commit-guard-managed" in hook.read_text(encoding="utf-8")


def test_guard_repo_on_a_plain_folder_dry_run_plans_git_init_and_writes_nothing(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "notes.txt").write_text("mine\n", encoding="utf-8")
    (tmp_path / "home").mkdir()  # the sandbox HOME, which run_clean makes anyway
    before = tree(tmp_path)
    r = _guard_install(tmp_path, proj, "--dry-run")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert re.search(r"RUN +git init \(new repo\) +-> " + re.escape(str(proj.resolve())), r.stdout), r.stdout
    assert f"git init {proj.resolve()}" in r.stdout
    assert tree(tmp_path) == before


def test_guard_repo_on_a_plain_folder_makes_the_repo_and_installs_the_hooks(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "notes.txt").write_text("mine\n", encoding="utf-8")
    r = _guard_install(tmp_path, proj)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert (proj / ".git").is_dir() and _hooked(proj)
    assert (proj / "notes.txt").read_text(encoding="utf-8") == "mine\n"
    tail = "\n".join(for_you_tail(r.stdout))
    assert f"Commit guard: installed as git hooks in {proj.resolve()}" in tail
    assert "ran git init there" in tail and "deleting its .git folder undoes" in tail
    again = _guard_install(tmp_path, proj, "--dry-run")  # now a repo: no second git init
    assert again.returncode == 0 and "git init (new repo)" not in again.stdout, again.stdout[-2000:]


def test_guard_repo_on_a_folder_that_does_not_exist_yet_creates_it(tmp_path):
    proj = tmp_path / "projects" / "new-app"
    dry = _guard_install(tmp_path, proj, "--dry-run")
    assert dry.returncode == 0, dry.stdout[-3000:] + dry.stderr
    assert "does not exist yet, so it is created" in dry.stdout
    assert not (tmp_path / "projects").exists()
    r = _guard_install(tmp_path, proj)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert (proj / ".git").is_dir() and _hooked(proj)


def test_guard_repo_in_a_subfolder_of_a_repo_uses_that_repo(tmp_path):
    repo = tmp_path / "repo"
    sub = repo / "src" / "app"
    sub.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    r = _guard_install(tmp_path, sub)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    assert "git init (new repo)" not in r.stdout
    assert not (sub / ".git").exists() and not (repo / "src" / ".git").exists()
    assert _hooked(repo)
    tail = "\n".join(for_you_tail(r.stdout))
    assert f"Commit guard: installed as git hooks in {repo.resolve()}." in tail


@pytest.mark.parametrize("where", ["home", "kit clone", "kit clone subfolder", "file"])
def test_guard_repo_refuses_folders_a_repo_would_harm(tmp_path, where):
    home = tmp_path / "home"
    home.mkdir()
    kit = home / ".claude-starter"
    (kit / "scripts").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(kit)], check=True, capture_output=True)
    (tmp_path / "a-file").write_text("x\n", encoding="utf-8")
    target = {"home": home, "kit clone": kit, "kit clone subfolder": kit / "scripts",
              "file": tmp_path / "a-file"}[where]
    before = tree(tmp_path)
    r = _guard_install(tmp_path, target)
    assert r.returncode == 2, r.stdout[-3000:] + r.stderr
    assert tree(tmp_path) == before  # no .git, no hooks, no config, no record
    assert "Nothing was written" in r.stderr and "--no-guard" in r.stderr
    why = {"home": "is your home directory", "kit clone": "is this kit's own clone",
           "kit clone subfolder": "is this kit's own clone", "file": "is a file, not a folder"}[where]
    assert why in r.stderr and why in r.stdout, r.stderr  # in the plan, and in the refusal
    if where != "file":
        assert str(home / "projects" / "<name>") in r.stderr


def test_guard_repo_refuses_the_kit_this_installer_runs_from(tmp_path):
    # A dry run only: a broken refusal must not reach the real clone's hooks.
    r = _guard_install(tmp_path, install.ROOT, "--dry-run")
    assert r.returncode == 2 and "is this kit's own clone" in r.stderr, r.stdout[-3000:] + r.stderr


def test_guard_target_refuses_a_filesystem_root_and_a_folder_holding_home(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "home", lambda: tmp_path / "home")
    root = Path(tmp_path.anchor)
    target, init, why = install.guard_target(str(root))
    assert why and "root of a drive or filesystem" in why, why
    target, init, why = install.guard_target(str(tmp_path))
    assert why and "holds your home directory" in why, why
    ok = install.guard_target(str(tmp_path / "home" / "projects" / "x"))
    assert ok == ((tmp_path / "home" / "projects" / "x").resolve(), True, None)


def test_two_paths_into_one_repo_plan_its_hooks_once(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    steps = install.plan_guards([str(repo), str(repo / "sub")])
    assert [(s.kind, s.dest) for s in steps] == [("guard", repo.resolve())]


class FakeClaude:
    """Stands in for `claude plugin ...`: an empty install that the plugin install then enables."""

    def __init__(self):
        self.calls = []
        self.installed = False

    def __call__(self, cmd, env, cwd):
        a = cmd[2:]
        self.calls.append(a)
        if a[:2] == ["marketplace", "list"]:
            return 0, "[]"
        if a[:1] == ["list"]:
            return 0, json.dumps([{"id": "starter@claude-starter", "enabled": True}] if self.installed else [])
        if a[:1] == ["install"]:
            self.installed = True
        return 0, ""


def _claude(monkeypatch, tmp_path):
    fake = FakeClaude()
    monkeypatch.setattr(install, "_run", fake)
    real_which = shutil.which
    monkeypatch.setattr(install.shutil, "which", lambda b, *a, **k: "claude" if b == "claude" else real_which(b))
    return fake


def test_claude_install_ends_with_the_for_you_block(sandboxed, tmp_path, monkeypatch, capsys):
    fake = _claude(monkeypatch, tmp_path)
    assert install.run(["--tool", "claude", "--config-dir", str(tmp_path / "claude-cfg"), "--yes", "--no-guard"]) == 0
    assert ["install", "starter@claude-starter", "--json"] in fake.calls
    tail = "\n".join(for_you_tail(capsys.readouterr().out))
    assert "Next: open Claude Code and run /starter:setup" in tail
    assert "Commit guard: NOT installed in any repo. Inside Claude Code" in tail
    assert "--tier" not in tail


# ---- a destination that cannot be written: refuse the whole install --------------------

def _block_writes_under(monkeypatch, blocked: Path):
    """Make every file creation under `blocked` fail the way a sandbox does (EACCES)."""
    real_open = os.open

    def guarded(path, flags, *a, **k):
        if str(path).startswith(str(blocked)) and flags & os.O_CREAT:
            raise PermissionError(errno.EACCES, "Access is denied", str(path))
        return real_open(path, flags, *a, **k)
    monkeypatch.setattr(os, "open", guarded)


def test_unwritable_codex_home_refuses_and_writes_nothing(sandboxed, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    blocked = sandboxed / ".codex"
    _block_writes_under(monkeypatch, blocked)
    before = tree(tmp_path)
    assert install.run(["--tool", "codex", "--tier", "starter", "--yes", "--no-guard"]) == install.UNWRITABLE == 3
    assert tree(tmp_path) == before  # not even the folders the probe made, nor ~/.agents/skills
    out = capsys.readouterr()
    assert install.FOR_YOU not in out.out
    err = out.err
    assert str(blocked) in err and "PermissionError" in err and "Access is denied" in err
    assert "nothing was written" in err.lower()
    assert "Codex sandbox (CODEX_THREAD_ID is set)" in err
    assert "not your tool's global config" in err and "your own terminal" in err
    assert re.search(r"PowerShell: python .*install\.py'? --tool codex --tier starter --no-guard --yes", err), err
    assert "If you are an AI agent: do not work around this" in err


def test_unwritable_without_codex_markers_says_so_plainly(sandboxed, tmp_path, monkeypatch, capsys):
    _block_writes_under(monkeypatch, sandboxed / ".agents")
    before = tree(tmp_path)
    assert install.run(["--tool", "cursor", "--tier", "starter", "--yes", "--no-guard"]) == 3
    assert tree(tmp_path) == before
    err = capsys.readouterr().err
    assert "sandboxed agent session, or a folder you cannot write to" in err and "Codex sandbox" not in err
    assert str(sandboxed / ".agents" / "skills") in err


def test_unwritable_guard_repo_refuses_the_whole_install(sandboxed, tmp_path, monkeypatch, capsys):
    # Codex keeps <writable root>/.git read-only, so the hooks can fail where the config would not.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _block_writes_under(monkeypatch, repo / ".git")
    before = tree(tmp_path)
    assert install.run(["--tool", "codex", "--tier", "starter", "--guard-repo", str(repo), "--yes"]) == 3
    assert tree(tmp_path) == before
    assert str(repo / ".git" / "hooks") in capsys.readouterr().err


def test_probe_leaves_no_trace(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    assert install.probe_dir(deep) is None
    assert not (tmp_path / "a").exists()
    (tmp_path / "x").mkdir()
    assert install.probe_dir(tmp_path / "x") is None
    assert list((tmp_path / "x").iterdir()) == []


@pytest.mark.skipif(not shutil.which("icacls"), reason="needs Windows icacls")
def test_really_unwritable_folder_refuses_on_windows(tmp_path):
    """No monkeypatching: an ACL that denies writing, as the Codex Windows sandbox applies."""
    codex = tmp_path / "home" / ".codex"
    codex.mkdir(parents=True)
    deny = subprocess.run(["icacls", str(codex), "/deny", "*S-1-1-0:(OI)(CI)(W)"], capture_output=True)
    assert deny.returncode == 0, deny.stdout + deny.stderr
    try:
        before = tree(tmp_path / "home")
        r = run_clean(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
        after = tree(tmp_path / "home")
    finally:
        subprocess.run(["icacls", str(codex), "/remove:d", "*S-1-1-0"], capture_output=True)
    assert r.returncode == 3, r.stdout[-2000:] + r.stderr
    assert after == before
    assert str(codex) in r.stderr and "PermissionError" in r.stderr


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_really_unwritable_folder_refuses_on_posix(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    home.chmod(0o500)
    try:
        r = run_clean(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
        left = sorted(p.name for p in home.iterdir())
    finally:
        home.chmod(0o700)
    assert r.returncode == 3, r.stdout[-2000:] + r.stderr
    assert left == [] and str(home / ".codex") in r.stderr


def test_a_write_that_fails_mid_apply_still_reports(sandboxed, tmp_path, monkeypatch, capsys):
    reported = []
    monkeypatch.setattr(install, "report_failure", lambda text, *a, **k: reported.append(text))
    real = Path.write_bytes

    def flaky(self, data):
        if self.name == "verifier.md":
            raise PermissionError(errno.EACCES, "Access is denied", str(self))
        return real(self, data)
    monkeypatch.setattr(Path, "write_bytes", flaky)
    rc = install.run(["--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"), "--yes", "--no-guard"])
    out = capsys.readouterr()
    assert rc == 1 and "FAILED: 1 piece(s) failed" in out.err
    assert reported and "verifier" in reported[0] and "Access is denied" in reported[0]
    assert install.FOR_YOU not in out.out


# ---- the dry run and the no-terminal run end by telling an agent to stop ------------------

TIER_ASK = "ask which tier (starter or full) and " + install.GUARD_ASK


@pytest.mark.parametrize("tool", ["codex", "cursor", "generic"])
def test_dry_run_ends_with_the_agent_stop_line(tmp_path, tool):
    cfg = ("--config-dir", str(tmp_path / "cfg")) if tool == "generic" else ()
    r = run_clean(tmp_path, "--tool", tool, "--tier", "starter", *cfg, "--dry-run")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[-2:] == ["dry run: nothing written.",
                          "If you are an AI agent: stop here. Show the user this plan, " + TIER_ASK
                          + ", and end your turn. Run with --yes only after they reply."]
    assert tree(tmp_path / "home") == {}


def test_claude_dry_run_stop_line_has_no_tier(sandboxed, tmp_path, monkeypatch, capsys):
    _claude(monkeypatch, tmp_path)
    assert install.run(["--tool", "claude", "--config-dir", str(tmp_path / "claude-cfg"), "--dry-run"]) == 0
    last = capsys.readouterr().out.rstrip("\n").split("\n")[-1]
    assert last == ("If you are an AI agent: stop here. Show the user this plan, ask " + install.GUARD_ASK
                    + ", and end your turn. Run with --yes only after they reply.")
    assert "which project folder they work in" in last and "~/projects/<name>" in last


STOP_WITH_TIER = ("If you are an AI agent: stop here. Show the user this plan, " + TIER_ASK
                  + ", and end your turn. Run with --yes only after they reply.")
YES_COMMAND = re.compile(r"install\.py\S*\s.*--yes")  # a ready-to-run apply command, in either shell


def test_no_terminal_run_ends_on_the_stop_line_with_no_yes_command(tmp_path):
    r = run_clean(tmp_path, "--tool", "codex", "--tier", "starter")  # stdin is DEVNULL
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[-2:] == ["no terminal and no --yes: dry run only, nothing written.", STOP_WITH_TIER]
    assert not [ln for ln in (r.stdout + r.stderr).split("\n") if YES_COMMAND.search(ln)], r.stdout[-2000:]
    assert "Re-run with --yes" not in r.stdout + r.stderr
    assert tree(tmp_path / "home") == {}


def _confirm_args(tool="codex", **kw):
    base = dict(tool=tool, tier=None if tool == "claude" else "starter", config_dir=None, project=None,
                guard_repo=[], dry_run=False, yes=False, no_guard=True)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_confirm_no_terminal_branch(monkeypatch, capsys, tool):
    monkeypatch.setattr(sys, "stdin", type("NoTty", (), {"isatty": lambda self: False})())
    args = _confirm_args(tool)
    assert install.confirm(args) == 0
    out = capsys.readouterr().out
    assert "Re-run with --yes" not in out
    assert out.rstrip("\n").split("\n")[-1] == install.agent_stop_line(args)
    assert not [ln for ln in out.split("\n") if YES_COMMAND.search(ln)], out
    assert (TIER_ASK in out) is (tool != "claude")


def test_confirm_eof_on_a_tty_takes_the_no_terminal_branch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())

    def eof(prompt):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert install.confirm(_confirm_args()) == 0
    assert "If you are an AI agent: stop here." in capsys.readouterr().out


@pytest.mark.parametrize("answer,want", [("y", None), ("yes", None), ("n", 1), ("", 1)])
def test_confirm_interactive_branch_is_unchanged(monkeypatch, capsys, answer, want):
    monkeypatch.setattr(sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())
    prompts = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or answer)
    assert install.confirm(_confirm_args()) == want
    assert prompts == ["\nApply this plan? [y/N] "]
    out = capsys.readouterr().out
    assert ("aborted; nothing written." in out) is (want == 1)
    assert "If you are an AI agent" not in out


@pytest.mark.parametrize("answer", ["--yes", "y"])
def test_apply_without_a_guard_choice_exits_2(monkeypatch, capsys, answer):
    """The record keeps the guard answer, so an apply that skipped the question must not become a no."""
    monkeypatch.setattr(sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda p: "y")
    args = _confirm_args(no_guard=False, yes=answer == "--yes")
    assert install.confirm(args) == 2
    assert "--no-guard" in capsys.readouterr().err
    assert install.confirm(_confirm_args(no_guard=False, yes=True, guard_repo=["r"])) is None


def test_yes_with_no_guard_choice_writes_nothing(tmp_path):
    r = run_clean(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"), "--yes")
    assert r.returncode == 2, r.stdout[-2000:] + r.stderr
    assert "--no-guard" in r.stderr and not (tmp_path / "cfg").exists() and tree(tmp_path / "home") == {}


def test_confirm_yes_and_dry_run(capsys):
    assert install.confirm(_confirm_args(yes=True)) is None
    assert install.confirm(_confirm_args(dry_run=True)) == 0
    assert capsys.readouterr().out.rstrip("\n").endswith("Run with --yes only after they reply.")


# ---- Codex's AGENTS.override.md hides the kit's rules -----------------------------------

@pytest.mark.parametrize("content,warned", [(b"my own rules\n", True), (b"", False), (None, False)])
def test_codex_override_file_is_warned_about(tmp_path, content, warned):
    codex = tmp_path / "home" / ".codex"
    codex.mkdir(parents=True)
    if content is not None:
        (codex / "AGENTS.override.md").write_bytes(content)
    r = run_clean(tmp_path, "--tool", "codex", "--tier", "starter", "--yes", "--no-guard")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr  # a warning, never a refusal
    tail = "\n".join(for_you_tail(r.stdout))
    assert ("AGENTS.override.md is not empty" in tail) is warned
    assert ("rules will not load" in r.stdout) is warned


def test_cursor_attribution_warning_says_the_guard_needs_guard_repo(tmp_path):
    """Cursor's guard caveat once said "the commit guard will flag" the trailer in a run whose For-you
    block said the guard was NOT installed in any repo."""
    (tmp_path / "cli-config.json").write_text(json.dumps({"attribution": {"attributeCommitsToAgent": True}}),
                                              encoding="utf-8")
    warning = [ln for ln in install.notes_cursor(tmp_path, None) if ln.startswith("WARNING")]
    assert len(warning) == 1
    assert "--guard-repo" in warning[0] and "Made with Cursor" in warning[0]

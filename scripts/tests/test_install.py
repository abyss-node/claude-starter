"""Installer behaviour: preflight, merges that keep the user's bytes, the printed update commands and
what the console shows. Every install runs in a throwaway HOME (see test_adapters.sandbox_env)."""
import argparse
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
    r = run_install(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(cfg), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "update later (bash" in r.stdout and "update later (PowerShell" in r.stdout
    assert r.stdout.count("--config-dir") >= 2


# ---- 11. preflight: a bad target means nothing is written ----------------------

def test_malformed_json_writes_nothing(tmp_path):
    gem = tmp_path / "home" / ".gemini" / "antigravity-cli"
    gem.mkdir(parents=True)
    (gem / "settings.json").write_text('{"permissions": {"allow": [,]}}', encoding="utf-8")
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "antigravity", "--tier", "starter", "--yes")
    assert r.returncode != 0
    assert snapshot(tmp_path / "home") == before
    assert "preflight" in (r.stdout + r.stderr).lower()
    assert list((tmp_path / "claude-starter-reports").glob("install-failure-*.md"))


def test_utf16_json_is_named_and_nothing_written(tmp_path):
    junie = tmp_path / "home" / ".junie"
    junie.mkdir(parents=True)
    (junie / "allowlist.json").write_bytes('{"rules": {}}'.encode("utf-16"))
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "junie", "--tier", "starter", "--yes")
    assert r.returncode != 0
    assert "UTF-16" in r.stdout + r.stderr
    assert snapshot(tmp_path / "home") == before


def test_utf16_rules_file_writes_nothing(tmp_path):
    codex = tmp_path / "home" / ".codex"
    codex.mkdir(parents=True)
    (codex / "AGENTS.md").write_bytes("# mine\r\n".encode("utf-16"))
    before = snapshot(tmp_path / "home")
    r = run_install(tmp_path, "--tool", "codex", "--tier", "starter", "--yes")
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
    install.finish_run("opencode", "starter", [], False, lines, "FAILED", [], args)
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and "abcdefghijklmnop" not in out.out + out.err
    assert "<redacted:" in out.out


# ---- 16. generic install and auto with nothing found ----------------------------

def test_generic_install_says_read_only_by_instruction_only(tmp_path):
    r = run_install(tmp_path, "--tool", "generic", "--tier", "starter", "--config-dir", str(tmp_path / "cfg"),
                    "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "READ-ONLY BY INSTRUCTION ONLY" in r.stdout


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
    install.finish_run("claude", None, [s], True, [], "passed", [], args)
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and "<redacted:" in out.out, out.out

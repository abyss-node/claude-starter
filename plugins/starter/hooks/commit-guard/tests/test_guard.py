"""Proves every commit-guard rule fires, never leaks the matched value, and respects modes/bypass."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

GUARD_DIR = Path(__file__).resolve().parent.parent
GUARD = GUARD_DIR / "guard.py"
sys.path.insert(0, str(GUARD_DIR))
import guard as G  # noqa: E402

BLOCK_GIT = G.GIT_BLOCK_EXIT


def make_aadhaar() -> str:
    """A fake 12-digit number with a valid Verhoeff checksum (first digit 2-9)."""
    body = "23456789012"
    for d in "0123456789":
        if G.verhoeff_valid(body + d):
            n = body + d
            return f"{n[:4]} {n[4:8]} {n[8:]}"
    raise AssertionError


# Fake values assembled at runtime. None is a real credential or a real person's data.
SECRETS = {
    "aws-access-key": "AKIA" + "FAKE1234FAKE5678",
    "github-token": "ghp_" + "Zq3Fx7Lm9Ab2Cd4Ef6Gh8Jk1Mn5Pq7Rs9TuV",
    "github-pat": "github_pat_" + "Q1w2E3r4T5y6U7i8O9p0AsDf",
    "anthropic-key": "sk-ant-" + "api03-FaKeFaKeFaKe1234",
    "openai-key": "sk-" + "FaKeFaKeFaKeFaKe1234Zz",
    "google-api-key": "AIza" + "SyFaKe0123456789abcdefghijklmnopqrs",
    "slack-token": "xoxb-" + "1234567890-FaKeFaKe",
    "private-key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
    "db-url-password": "postgres://appuser:" + "Zx9fakeSecret77" + "@db.internal:5432/app",
}
PII = {
    "in-mobile": "+91 " + "9123456780",
    "in-mobile-keyword": "phone: " + "9123456780",
    "in-mobile-zero": "reach 0" + "9123456780",
    "aadhaar": make_aadhaar(),
    "pan": "ABCPE" + "1234F",
    "email": "jane.fixture" + "@acmefixture.io",
}
ATTRIBUTION = {
    "ai-coauthor": "Co-Authored-By: Claude Sonnet <x@example.com>",
    "ai-noreply": "thanks <noreply" + "@anthropic.com>",
    "ai-generated-with": "Generated with [Claude Code](https://claude.com/claude-code)",
}


def write_config(path: Path, **cfg):
    # The verification-record rule is switched off by default so the older tests stay about their own rule;
    # the record tests turn it on explicitly.
    cfg.setdefault("require_record", False)
    cfg.setdefault("record_required_from", "2000-01-01T00:00:00+00:00")
    path.write_text(json.dumps(cfg))
    return path


@pytest.fixture
def env(tmp_path):
    cfg = write_config(tmp_path / "cfg.json", mode="block")
    gitcfg = tmp_path / "gitconfig"
    gitcfg.write_text("")
    trusted = tmp_path / "trusted.txt"
    trusted.write_text("")
    e = dict(os.environ)
    e.update(
        COMMIT_GUARD_CONFIG=str(cfg),
        COMMIT_GUARD_BYPASS_LOG=str(tmp_path / "bypass.log"),
        COMMIT_GUARD_TRUSTED=str(trusted),
        COMMIT_GUARD_STATE=str(tmp_path / "state"),
        COMMIT_GUARD_DIR=str(tmp_path / "data"),
        COMMIT_GUARD_HOME=str(tmp_path / "home"),
        GIT_CONFIG_GLOBAL=str(gitcfg),
        GIT_CONFIG_NOSYSTEM="1",
    )
    for k in ("COMMIT_GUARD_BYPASS", "COMMIT_GUARD_REASON"):
        e.pop(k, None)
    e["_cfg"], e["_trusted"], e["_data"] = str(cfg), str(trusted), str(tmp_path / "data")
    return e


def set_mode(env, **cfg):
    write_config(Path(env["_cfg"]), **cfg)


def trust(env, repo):
    Path(env["_trusted"]).write_text(str(repo) + "\n")


def sh(args, cwd, env, **kw):
    return subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True, **kw)


@pytest.fixture
def repo(tmp_path, env):
    r = tmp_path / "repo"
    r.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "dev@fixture-repo.test"],
              ["config", "user.name", "Dev"], ["config", "commit.gpgsign", "false"]):
        assert sh(["git", *a], r, env).returncode == 0
    return r


def stage(repo, env, name, content):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    assert sh(["git", "add", name], repo, env).returncode == 0


def guard(sub, repo, env, *args, stdin=None):
    return subprocess.run([sys.executable, str(GUARD), sub, *args], cwd=str(repo), env=env,
                          input=stdin, capture_output=True, text=True)


def out(p):
    return p.stdout + p.stderr


def install(repo, env):
    p = guard("install", repo, env, str(repo))
    assert p.returncode == 0, out(p)


def commit(repo, env, *msgs):
    args = ["git", "commit", "-q"]
    for m in msgs:
        args += ["-m", m]
    return sh(args, repo, env)


def has_commits(repo, env):
    return sh(["git", "log", "--oneline"], repo, env).returncode == 0


# ---- secrets / PII --------------------------------------------------------

@pytest.mark.parametrize("rule,value", list(SECRETS.items()) + list(PII.items()))
def test_diff_rule_fires_and_never_leaks(repo, env, rule, value):
    stage(repo, env, "src/app.txt", f"first line\nvalue = {value}\n")
    p = guard("pre-commit", repo, env)
    rid = rule.removesuffix("-keyword").removesuffix("-zero")
    # email is warn-only: it reports but never blocks, even in block mode
    assert p.returncode == (0 if rid == "email" else BLOCK_GIT)
    assert "src/app.txt:2  " + rid in out(p)
    text = out(p)
    assert value not in text
    assert value[-8:] not in text


def test_only_added_lines_scanned(repo, env):
    stage(repo, env, "a.txt", f"k = {SECRETS['aws-access-key']}\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0
    stage(repo, env, "a.txt", "k = removed\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == ""


def test_line_number_is_new_file_line(repo, env):
    stage(repo, env, "b.txt", "x\n\n\n" + f"t = {SECRETS['github-token']}\n")
    assert "b.txt:4  github-token" in out(guard("pre-commit", repo, env))


def test_binary_file_skipped(repo, env):
    (repo / "blob.bin").write_bytes(b"\x00\x01" + SECRETS["aws-access-key"].encode())
    sh(["git", "add", "blob.bin"], repo, env)
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == ""


def test_plus_plus_plus_content_line_not_mistaken_for_header(repo, env):
    stage(repo, env, "c.txt", "ok\n++ " + SECRETS["aws-access-key"] + "\n")
    assert "c.txt:2  aws-access-key" in out(guard("pre-commit", repo, env))


def test_email_allowlist(repo, env):
    stage(repo, env, "e.txt", "\n".join([
        "dev@fixture-repo.test", "1234+u@users.noreply.github.com", "noreply@github.com",
        "someone@example.com", "git@github.com:org/repo.git", "logo@2x.png",
    ]) + "\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == ""


def test_email_is_warn_only_and_does_not_block_with_secret_absent(repo, env):
    stage(repo, env, "e.txt", f"contact {PII['email']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and "email  (warn-only)" in out(p) and "never block" in out(p)


def test_email_plus_secret_still_blocks(repo, env):
    stage(repo, env, "e.txt", f"{PII['email']}\n{SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == BLOCK_GIT and "e.txt:1  email" in out(p) and "e.txt:2  aws-access-key" in out(p)


def test_db_url_placeholder_not_flagged(repo, env):
    stage(repo, env, "d.txt", "postgres://user:password@localhost/db\npostgres://u:${DB_PASS}@h/db\n")
    assert guard("pre-commit", repo, env).returncode == 0


# ---- PII false positives that tripped in the field ------------------------

FALSE_POSITIVES = [
    "2024 2025 2026",              # was aadhaar: fails Verhoeff
    '"lastfm_id": 7234567890',     # was mobile: id field, no phone context
    "size 9876543210",             # was mobile: no prefix, no phone keyword
    '"contact_id": 9123456780',    # keyword present but it is an id field
    "ERROR1234X",                  # was pan: 4th letter is not a holder type
    "total 8123456789 bytes",
    "const code = 100000000000;",
]


@pytest.mark.parametrize("line", FALSE_POSITIVES)
def test_known_false_positives_stay_quiet(repo, env, line):
    stage(repo, env, "fp.txt", line + "\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == "", out(p)


def test_verhoeff_known_vectors():
    assert G.verhoeff_valid("2363") and G.verhoeff_valid("123451")
    assert not G.verhoeff_valid("2364")
    assert not G.verhoeff_valid("202420252026")


def test_aadhaar_needs_first_digit_2_to_9_and_checksum(repo, env):
    good = make_aadhaar().replace(" ", "")
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    leading_one = "1" + good[1:]
    assert not G.verhoeff_valid(bad)
    stage(repo, env, "n.txt", f"{bad}\n{leading_one}\n")
    assert guard("pre-commit", repo, env).returncode == 0


def test_clean_commit_passes(repo, env):
    stage(repo, env, "ok.py", "print('hello')\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == ""
    m = repo / "msg.txt"
    m.write_text("Add hello\n\nplain body\n")
    assert guard("commit-msg", repo, env, str(m)).returncode == 0


# ---- message attribution ---------------------------------------------------

@pytest.mark.parametrize("rule,text", ATTRIBUTION.items())
def test_message_attribution_fires_with_instruction(repo, env, rule, text):
    m = repo / "msg.txt"
    m.write_text(f"Fix thing\n\n{text}\n")
    p = guard("commit-msg", repo, env, str(m))
    assert p.returncode == BLOCK_GIT
    assert f"commit-message  {rule}" in out(p)
    assert text not in out(p)
    assert "Remove the Co-Authored-By/Generated-with lines" in out(p)
    assert "attributed to the user only (house rule)" in out(p)


def test_attribution_is_blocking_in_warn_mode_too_only_when_mode_blocks(repo, env):
    set_mode(env, mode="warn", block_from="2999-01-01")
    m = repo / "msg.txt"
    m.write_text(f"x\n\n{ATTRIBUTION['ai-coauthor']}\n")
    p = guard("commit-msg", repo, env, str(m))
    assert p.returncode == 0 and "Remove the Co-Authored-By" in out(p)


def test_message_secret_fires_without_leak(repo, env):
    m = repo / "msg.txt"
    v = SECRETS["github-token"]
    m.write_text(f"oops {v}\n")
    p = guard("commit-msg", repo, env, str(m))
    assert "commit-message  github-token" in out(p) and v not in out(p)


# ---- modes and config validation ------------------------------------------

def test_warn_mode_exits_zero_but_warns(repo, env):
    set_mode(env, mode="warn", block_from="2999-01-01")
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0
    assert "w.txt:1  aws-access-key" in out(p) and "WARNING" in out(p)
    assert "blocks from 2999-01-01" in out(p)


def test_block_from_date_reached_blocks(repo, env):
    set_mode(env, mode="warn", block_from="2000-01-01")
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    assert guard("pre-commit", repo, env).returncode == BLOCK_GIT


@pytest.mark.parametrize("cfg_text", [
    "{not json", '{"mode": "warn", "block_from": 20261113}', '{"mode": "fast"}', "[1, 2]", '{"block_from": "soon"}'])
def test_invalid_config_fails_open_for_git_and_closed_for_claude(repo, env, cfg_text):
    Path(env["_cfg"]).write_text(cfg_text)
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and "fix config" in out(p) and "Traceback" not in out(p)
    p = guard("claude-hook", repo, env, stdin=hook_input(repo, 'git commit -m "x"'))
    assert p.returncode == 2 and "guard error, fix config" in p.stderr


def test_no_config_defaults_to_warn_and_nothing_is_shipped_next_to_the_code(repo, env):
    assert not (GUARD_DIR / "config.json").exists()
    Path(env["_cfg"]).unlink()
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and "WARNING only" in out(p) and "w.txt:1  aws-access-key" in out(p)
    p = guard("claude-hook", repo, env, stdin=hook_input(repo, 'git commit -m "x"'))
    assert p.returncode == 0 and "WARNING only" in p.stderr


def test_mutable_state_defaults_to_the_data_dir_not_the_code_dir():
    for name in ("CONFIG_PATH", "BYPASS_LOG", "TRUSTED_PATH", "STATE_DIR"):
        path = getattr(G, name)
        assert G.DATA_DIR in path.parents and G.CODE_DIR not in path.parents, name
    assert G.CODE_DIR == GUARD_DIR


# ---- allowlist -------------------------------------------------------------

def test_allowlist_suppresses_matching_rule_only(repo, env):
    (repo / ".claude" / "checks").mkdir(parents=True)
    (repo / ".claude" / "checks" / "allowlist.txt").write_text("# fixtures\nfixtures/*:aws-access-key\n")
    stage(repo, env, "fixtures/k.txt", f"{SECRETS['aws-access-key']}\n{SECRETS['github-token']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == BLOCK_GIT
    assert "aws-access-key" not in out(p)
    assert "fixtures/k.txt:2  github-token" in out(p)


def test_allowlist_wildcard_rule_and_other_path_still_flagged(repo, env):
    (repo / ".claude" / "checks").mkdir(parents=True)
    (repo / ".claude" / "checks" / "allowlist.txt").write_text("fixtures/*:*\n")
    stage(repo, env, "fixtures/k.txt", f"{SECRETS['aws-access-key']}\n")
    stage(repo, env, "src/k.txt", f"{SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert "src/k.txt:1  aws-access-key" in out(p) and "fixtures/k.txt" not in out(p)


def test_allowlist_keeps_email_suppressible(repo, env):
    (repo / ".claude" / "checks").mkdir(parents=True)
    (repo / ".claude" / "checks" / "allowlist.txt").write_text("*.csv:email\n")
    stage(repo, env, "people.csv", f"{PII['email']}\n")
    assert out(guard("pre-commit", repo, env)) == ""


# ---- per-repo checks and trust --------------------------------------------

def _checks(repo):
    d = repo / ".claude" / "checks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_failing_repo_check_blocks_and_shows_tail(repo, env):
    trust(env, repo)
    (_checks(repo) / "lint.py").write_text("import sys\nfor i in range(30): print('line', i)\nsys.exit(3)\n")
    stage(repo, env, "x.txt", "fine\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == BLOCK_GIT
    assert "repo-check  lint.py (exit 3)" in out(p)
    assert "line 29" in out(p) and "line 9\n" not in out(p)


@pytest.mark.parametrize("name,body", [
    ("c.sh", "echo failing-sh\nexit 4\n"),
    ("c.ps1", "Write-Output 'failing-ps'\nexit 5\n"),
])
def test_repo_check_script_types(repo, env, name, body):
    trust(env, repo)
    (_checks(repo) / name).write_text(body)
    stage(repo, env, "x.txt", "fine\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == BLOCK_GIT and f"repo-check  {name} (exit" in out(p)


def test_passing_repo_check_ok_and_runs_from_repo_root(repo, env):
    trust(env, repo)
    (_checks(repo) / "ok.py").write_text("import os, sys\nsys.exit(0 if os.path.isdir('.git') else 9)\n")
    stage(repo, env, "x.txt", "fine\n")
    assert guard("pre-commit", repo, env).returncode == 0


def test_untrusted_repo_checks_are_skipped_with_one_line(repo, env):
    marker = repo / "ran.txt"
    (_checks(repo) / "evil.py").write_text(f"open(r'{marker}', 'w').write('x')\nraise SystemExit(1)\n")
    stage(repo, env, "x.txt", "fine\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and not marker.exists()
    assert out(p).strip().count("\n") == 0 and "checks skipped" in out(p) and "trusted-repos.txt" in out(p)


def test_no_trusted_repos_file_ships_with_the_plugin():
    assert not (GUARD_DIR / "trusted-repos.txt").exists()


# ---- bypass ----------------------------------------------------------------

def test_human_bypass_skips_and_logs(repo, env, tmp_path):
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    e = dict(env, COMMIT_GUARD_BYPASS="1", COMMIT_GUARD_REASON="fixture data")
    p = guard("pre-commit", repo, e)
    assert p.returncode == 0 and "BYPASSED" in out(p)
    log = (tmp_path / "bypass.log").read_text()
    assert "fixture data" in log and "repo" in log and "pre-commit" in log


# ---- Claude hook path ------------------------------------------------------

def hook_input(repo, command, tool="Bash"):
    return json.dumps({
        "session_id": "abc123", "transcript_path": "/x/t.jsonl", "cwd": str(repo),
        "permission_mode": "default", "hook_event_name": "PreToolUse",
        "tool_name": tool, "tool_input": {"command": command, "description": "commit"},
        "tool_use_id": "toolu_01",
    })


def chook(repo, env, command, tool="Bash"):
    return guard("claude-hook", repo, env, stdin=hook_input(repo, command, tool))


@pytest.mark.parametrize("command", [
    'COMMIT_GUARD_BYPASS=1 git commit -m "x"',
    '$env:COMMIT_GUARD_BYPASS=1; git commit -m "x"',
    'COMMIT_GUARD_CONFIG=/tmp/x git commit -m "x"',
    'git commit --no-verify -m "x"',
    'git commit -n -m "x"',
    'git commit -nm "x"',
    'git commit -anm "x"',
    'git -c core.hooksPath=/dev/null commit -m "x"',
    'cd sub && git commit -m "x" --no-verify',
    'git -C sub commit --no-verify -m x',
    'bash -c "git commit --no-verify -m x"',
    "powershell -Command \"git commit -n -m x\"",
    "bash <<'EOF'\ngit commit -n -m x\nEOF",
    '& git commit -n -m x',
])
@pytest.mark.parametrize("mode", ["warn", "block"])
def test_claude_hook_blocks_agent_bypass_in_every_mode(repo, env, command, mode):
    set_mode(env, mode=mode, block_from="2999-01-01")
    p = chook(repo, env, command)
    assert p.returncode == 2 and "may not bypass" in p.stderr


# --- trigger tightening: only a real `git commit` invocation counts

SCRIPT_HEREDOC = ("cat > deploy.sh <<'EOF'\n#!/bin/sh\nCOMMIT_GUARD_BYPASS=1 git commit --no-verify -m wip\n"
                  "git commit -n -m x\nEOF\nchmod +x deploy.sh")


@pytest.mark.parametrize("command", [
    SCRIPT_HEREDOC,
    "cat > notes.md <<EOF\nrun `git commit --no-verify` only as the human, COMMIT_GUARD_BYPASS=1\nEOF",
    '@\'\ngit commit --no-verify\nCOMMIT_GUARD_BYPASS=1\n\'@ | Set-Content hook.ps1',
    'echo "git commit --no-verify"',
    "echo 'COMMIT_GUARD_BYPASS=1 git commit -n'",
    'python -c "print(\'git commit -n\')"',
    'git log --grep="git commit --no-verify"',
    'git status && grep -r "git commit" docs/',
    "git push --no-verify",
])
def test_claude_hook_ignores_text_that_only_mentions_git_commit(repo, env, command):
    stage(repo, env, "s.txt", f"t = {SECRETS['github-token']}\n")  # would block if it were treated as a commit
    p = chook(repo, env, command)
    assert p.returncode == 0 and out(p) == "", out(p)


def test_find_commits_parses_options_before_subcommand():
    assert G.find_commits("git -C x -c a=b commit -m y")[0]["C"] == ["x"]
    assert G.find_commits('git --no-pager -c core.editor=true commit')
    assert not G.find_commits("git commits")
    assert not G.find_commits("git log commit")
    assert len(G.find_commits("git add . && git commit -m a; git commit -m b")) == 2


def test_claude_hook_dash_n_in_message_text_is_not_a_bypass(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    assert chook(repo, env, 'git commit -m "add -n flag docs"').returncode == 0


def test_claude_hook_heredoc_message_with_dash_n_ok(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    cmd = "git commit -m \"$(cat <<'EOF'\nhandle \"quoted\" -n case, COMMIT_GUARD text\n\nbody\nEOF\n)\""
    assert chook(repo, env, cmd).returncode == 0


def test_claude_hook_ignores_non_commit_commands(repo, env):
    for c in ("ls -la", "git status", "git push --no-verify"):
        assert chook(repo, env, c).returncode == 0


def test_claude_hook_blocks_secret_in_block_mode_without_leak(repo, env):
    v = SECRETS["github-token"]
    stage(repo, env, "s.txt", f"t = {v}\n")
    p = chook(repo, env, 'git commit -m "add file"')
    assert p.returncode == 2
    assert "s.txt:1  github-token" in p.stderr and v not in out(p)


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_claude_hook_attribution_in_command(repo, env, tool):
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, 'git commit -m "x" -m "Co-Authored-By: Claude Sonnet <a@b.c>"', tool)
    assert p.returncode == 2 and "commit-message  ai-coauthor" in p.stderr
    assert "Remove the Co-Authored-By/Generated-with lines" in p.stderr
    assert "Claude Sonnet" not in out(p)


def test_claude_hook_attribution_in_heredoc_and_message_file(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    heredoc = "git commit -m \"$(cat <<'EOF'\nsubject\n\nGenerated with [Claude Code](u)\nEOF\n)\""
    p = chook(repo, env, heredoc)
    assert p.returncode == 2 and "ai-generated-with" in p.stderr
    (repo / "m.txt").write_text("s\n\nCo-Authored-By: Claude <n@example.com>\n")
    p = chook(repo, env, "git commit -F m.txt")
    assert p.returncode == 2 and "ai-coauthor" in p.stderr


def test_claude_hook_commit_a_scans_unstaged_tracked_changes(repo, env):
    stage(repo, env, "t.txt", "one\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0
    (repo / "t.txt").write_text(f"one\nk={SECRETS['aws-access-key']}\n")
    p = chook(repo, env, 'git commit -am "x"')
    assert p.returncode == 2 and "t.txt:2  aws-access-key" in p.stderr
    assert chook(repo, env, 'git commit -m "x"').returncode == 0  # nothing staged


def test_claude_hook_warn_mode_surfaces_warning_to_the_model(repo, env):
    """Exit-0 stderr never reaches the model; PreToolUse additionalContext does."""
    set_mode(env, mode="warn", block_from="2999-01-01")
    v = SECRETS["github-token"]
    stage(repo, env, "s.txt", f"t = {v}\n")
    p = chook(repo, env, 'git commit -m "x"')
    assert p.returncode == 0 and "WARNING" in p.stderr and "s.txt:1  github-token" in p.stderr
    payload = json.loads(p.stdout)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "s.txt:1  github-token" in hso["additionalContext"] and v not in p.stdout


def test_claude_hook_block_mode_prints_no_json_on_stdout(repo, env):
    stage(repo, env, "s.txt", f"t = {SECRETS['github-token']}\n")
    p = chook(repo, env, 'git commit -m "x"')
    assert p.returncode == 2 and p.stdout == ""


def test_claude_hook_resolves_cd_prefix(repo, env, tmp_path):
    stage(repo, env, "s.txt", f"t = {SECRETS['github-token']}\n")
    p = guard("claude-hook", tmp_path, env, stdin=hook_input(tmp_path, f'cd "{repo}" && git commit -m "x"'))
    assert p.returncode == 2 and "s.txt:1" in p.stderr


def test_claude_hook_garbage_stdin_is_harmless(repo, env):
    assert guard("claude-hook", repo, env, stdin="not json").returncode == 0


def test_claude_hook_untrusted_checks_note(repo, env):
    (_checks(repo) / "a.py").write_text("raise SystemExit(1)\n")
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, 'git commit -m "x"')
    assert p.returncode == 0 and "checks skipped" in p.stderr


# ---- internal errors -------------------------------------------------------

def _boom(*a, **k):
    raise RuntimeError("synthetic failure")


def test_internal_error_git_hook_warns_and_exits_zero_even_in_block_mode(env, monkeypatch, capsys):
    monkeypatch.setattr(G, "CONFIG_PATH", Path(env["_cfg"]))  # block mode
    monkeypatch.setattr(G, "cmd_pre_commit", _boom)
    assert G.main(["guard.py", "pre-commit"]) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "guard error" in err and "RuntimeError" in err


def test_internal_error_claude_hook_fails_closed_in_block_mode(env, monkeypatch, capsys):
    monkeypatch.setattr(G, "CONFIG_PATH", Path(env["_cfg"]))
    monkeypatch.setattr(G, "cmd_claude_hook", _boom)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))
    assert G.main(["guard.py", "claude-hook"]) == 2
    assert "guard error" in capsys.readouterr().err


def test_internal_error_claude_hook_fails_open_in_warn_mode(env, monkeypatch, capsys):
    set_mode(env, mode="warn", block_from="2999-01-01")
    monkeypatch.setattr(G, "CONFIG_PATH", Path(env["_cfg"]))
    monkeypatch.setattr(G, "cmd_claude_hook", _boom)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))
    assert G.main(["guard.py", "claude-hook"]) == 0
    assert "WARNING guard error" in capsys.readouterr().err


# ---- install / uninstall ---------------------------------------------------

def test_install_writes_only_the_three_hooks(repo, env):
    install(repo, env)
    hooks = sorted(p.name for p in (repo / ".git" / "hooks").iterdir() if not p.name.endswith(".sample"))
    assert hooks == ["commit-msg", "pre-commit", "pre-push"]
    assert G.HOOK_MARKER in (repo / ".git" / "hooks" / "pre-commit").read_text()


def test_install_is_idempotent_and_does_not_chain_to_itself(repo, env):
    install(repo, env)
    install(repo, env)
    assert not (repo / ".git" / "hooks" / "pre-commit.local").exists()


def test_install_chains_existing_hook_and_uninstall_restores_it(repo, env):
    h = repo / ".git" / "hooks" / "pre-commit"
    h.write_text("#!/bin/sh\necho local-hook-ran >&2\nexit 7\n", newline="\n")
    h.chmod(0o755)
    install(repo, env)
    assert (repo / ".git" / "hooks" / "pre-commit.local").exists()
    stage(repo, env, "ok.txt", "clean\n")
    p = commit(repo, env, "clean")
    assert p.returncode != 0 and "local-hook-ran" in out(p) and not has_commits(repo, env)
    p = guard("uninstall", repo, env, str(repo))
    assert p.returncode == 0 and "restored previous hook" in p.stdout
    assert "local-hook-ran" in h.read_text()
    assert not (repo / ".git" / "hooks" / "pre-commit.local").exists()
    assert not (repo / ".git" / "hooks" / "commit-msg").exists()


def test_chain_runs_local_hook_then_guard_when_local_passes(repo, env):
    h = repo / ".git" / "hooks" / "pre-commit"
    h.write_text("#!/bin/sh\necho local-hook-ran >&2\nexit 0\n", newline="\n")
    h.chmod(0o755)
    install(repo, env)
    stage(repo, env, "s.txt", f"t = {SECRETS['github-token']}\n")
    p = commit(repo, env, "x")
    assert p.returncode != 0 and "local-hook-ran" in out(p) and "s.txt:1  github-token" in out(p)


def test_install_respects_local_hooks_path_inside_repo(repo, env):
    sh(["git", "config", "core.hooksPath", ".githooks"], repo, env)
    install(repo, env)
    assert (repo / ".githooks" / "pre-commit").exists() and not (repo / ".git" / "hooks" / "pre-commit").exists()
    stage(repo, env, "s.txt", f"t = {SECRETS['aws-access-key']}\n")
    assert commit(repo, env, "x").returncode != 0


def test_install_refuses_hooks_dir_outside_the_repo(repo, env, tmp_path):
    shared = tmp_path / "shared-hooks"
    sh(["git", "config", "core.hooksPath", str(shared)], repo, env)
    p = guard("install", repo, env, str(repo))
    assert p.returncode == 1 and "shared and outside" in p.stderr and not shared.exists()


def test_install_refuses_non_repo(tmp_path, env):
    d = tmp_path / "plain"
    d.mkdir()
    assert guard("install", d, env, str(d)).returncode == 1


# ---- end to end through real git ------------------------------------------

def test_e2e_secret_blocked_by_installed_pre_commit(repo, env):
    install(repo, env)
    v = SECRETS["aws-access-key"]
    stage(repo, env, "s.txt", f"k = {v}\n")
    p = commit(repo, env, "add")
    assert p.returncode != 0
    assert "s.txt:1  aws-access-key" in out(p) and v not in out(p)
    assert not has_commits(repo, env)


def test_e2e_attribution_blocked_by_installed_commit_msg(repo, env):
    install(repo, env)
    stage(repo, env, "ok.txt", "clean\n")
    p = commit(repo, env, "x", "Co-Authored-By: Claude <n@example.com>")
    assert p.returncode != 0 and "commit-message  ai-coauthor" in out(p)
    assert "attributed to the user only" in out(p)
    assert not has_commits(repo, env)


def test_e2e_clean_commit_passes(repo, env):
    install(repo, env)
    stage(repo, env, "ok.txt", "clean\n")
    p = commit(repo, env, "clean commit")
    assert p.returncode == 0, out(p)
    assert sh(["git", "log", "--oneline"], repo, env).stdout.strip().endswith("clean commit")


def test_e2e_warn_mode_commit_goes_through_with_warning(repo, env):
    set_mode(env, mode="warn", block_from="2999-01-01")
    install(repo, env)
    stage(repo, env, "s.txt", f"k = {SECRETS['aws-access-key']}\n")
    p = commit(repo, env, "add")
    assert p.returncode == 0 and "WARNING" in out(p)


def test_e2e_human_bypass(repo, env, tmp_path):
    install(repo, env)
    stage(repo, env, "s.txt", f"k = {SECRETS['aws-access-key']}\n")
    p = sh(["git", "commit", "-q", "-m", "add"], repo, dict(env, COMMIT_GUARD_BYPASS="1", COMMIT_GUARD_REASON="e2e"))
    assert p.returncode == 0
    assert "e2e" in (tmp_path / "bypass.log").read_text()


def test_e2e_invalid_config_does_not_block_the_human(repo, env):
    install(repo, env)
    Path(env["_cfg"]).write_text('{"mode": "block", "block_from": 5}')
    stage(repo, env, "s.txt", f"k = {SECRETS['aws-access-key']}\n")
    p = commit(repo, env, "add")
    assert p.returncode == 0 and "fix config" in out(p)


@pytest.mark.parametrize("rc", [9009, 1, 127, 2])
def test_e2e_broken_python_never_blocks_a_commit(repo, env, tmp_path, rc):
    """A python that exists but fails (Store alias stub exits 9009) must not stop a clean commit."""
    install(repo, env)
    stub = tmp_path / "stub.py"
    stub.write_text(f"import sys\nsys.exit({rc})\n")
    for name in ("pre-commit", "commit-msg"):
        hp = repo / ".git" / "hooks" / name
        hp.write_text(hp.read_text().replace((Path(env["_data"]) / "guard.py").as_posix(), stub.as_posix()), newline="\n")
    stage(repo, env, "ok.txt", "clean\n")
    p = commit(repo, env, "clean")
    assert p.returncode == 0, out(p)
    assert "guard error" in out(p) and "guard skipped" in out(p)


def test_e2e_guard_block_exit_code_is_the_only_one_that_blocks(repo, env, tmp_path):
    install(repo, env)
    stub = tmp_path / "stub.py"
    stub.write_text(f"import sys\nsys.exit({BLOCK_GIT})\n")
    hp = repo / ".git" / "hooks" / "pre-commit"
    hp.write_text(hp.read_text().replace((Path(env["_data"]) / "guard.py").as_posix(), stub.as_posix()), newline="\n")
    stage(repo, env, "ok.txt", "clean\n")
    assert commit(repo, env, "clean").returncode != 0


def test_e2e_claude_hook_script_realistic_pretooluse_json(repo, env):
    """Run exactly as the harness does: python guard.py claude-hook, JSON on stdin."""
    v = SECRETS["github-token"]
    stage(repo, env, "s.txt", f"t = {v}\n")
    p = subprocess.run([sys.executable, str(GUARD), "claude-hook"],
                       input=hook_input(repo, 'git commit -m "add token file"'), cwd=str(repo),
                       env=env, capture_output=True, text=True)
    assert p.returncode == 2
    assert "s.txt:1  github-token" in p.stderr and "BLOCKED" in p.stderr
    assert v not in out(p)


# ---- second fix round ------------------------------------------------------

def test_passing_sh_repo_check_runs_under_apostrophe_home_and_writes_marker(repo, env):
    """Exit 127 (bash could not find the script) used to satisfy the failing-script test; a PASSING one cannot."""
    assert "'" in str(repo), "temp dir should carry the apostrophe that broke absolute paths"
    trust(env, repo)
    (_checks(repo) / "ok.sh").write_text("echo ran > sh-check-ran.marker\nexit 0\n", newline="\n")
    stage(repo, env, "x.txt", "fine\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and out(p) == "", out(p)
    assert (repo / "sh-check-ran.marker").exists()


def _seed_commit(repo, env):
    stage(repo, env, "seed.txt", "seed\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0


@pytest.mark.parametrize("seeded", [False, True])
def test_claude_hook_detects_secret_in_file_staged_by_same_command(repo, env, seeded):
    if seeded:
        _seed_commit(repo, env)
    v = SECRETS["github-token"]
    (repo / "k.txt").write_text(f"t = {v}\n")  # untracked, nothing staged yet
    p = chook(repo, env, 'git add k.txt && git commit -m t')
    assert p.returncode == 2 and "k.txt:1  github-token" in p.stderr and v not in out(p)


@pytest.mark.parametrize("add", ["git add -A", "git add .", "git add --all", "git add -f k.txt", "git stage k.txt",
                                 "git -C . add k.txt", "bash -c 'git add k.txt && git commit -m t'"])
def test_claude_hook_add_variants_are_scanned(repo, env, add):
    (repo / "k.txt").write_text(f"t = {SECRETS['aws-access-key']}\n")
    cmd = add if "commit" in add else f"{add} && git commit -m t"
    p = chook(repo, env, cmd)
    assert p.returncode == 2 and "k.txt:1  aws-access-key" in p.stderr


def test_claude_hook_add_scans_only_the_named_paths_and_respects_gitignore(repo, env):
    (repo / ".gitignore").write_text("ignored.txt\n")
    (repo / "ok.txt").write_text("fine\n")
    (repo / "other.txt").write_text(f"t = {SECRETS['aws-access-key']}\n")      # untracked, not added
    (repo / "ignored.txt").write_text(f"t = {SECRETS['aws-access-key']}\n")    # ignored, would not be added
    assert chook(repo, env, "git add ok.txt && git commit -m t").returncode == 0
    assert chook(repo, env, "git add . && git commit -m t").returncode == 2
    p = chook(repo, env, "git add . && git commit -m t")
    assert "other.txt:1" in p.stderr and "ignored.txt" not in p.stderr


def test_claude_hook_add_scans_modified_tracked_file_against_head(repo, env):
    stage(repo, env, "t.txt", "one\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0
    (repo / "t.txt").write_text(f"one\nk={SECRETS['aws-access-key']}\n")
    p = chook(repo, env, "git add t.txt && git commit -m t")
    assert p.returncode == 2 and "t.txt:2  aws-access-key" in p.stderr


def test_claude_hook_commit_am_with_modified_tracked_file_is_detected(repo, env):
    stage(repo, env, "t.txt", "one\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0
    v = SECRETS["github-token"]
    (repo / "t.txt").write_text(f"one\nk={v}\n")
    p = chook(repo, env, "git commit -am t")
    assert p.returncode == 2 and "t.txt:2  github-token" in p.stderr and v not in out(p)


def test_claude_hook_commit_with_pathspec_scans_those_paths(repo, env):
    stage(repo, env, "t.txt", "one\n")
    assert sh(["git", "commit", "-q", "-m", "seed", "--no-verify"], repo, env).returncode == 0
    (repo / "t.txt").write_text(f"one\nk={SECRETS['aws-access-key']}\n")
    assert chook(repo, env, "git commit t.txt -m t").returncode == 2


def test_claude_hook_clean_add_and_commit_passes(repo, env):
    (repo / "k.txt").write_text("nothing here\n")
    p = chook(repo, env, "git add k.txt && git commit -m t")
    assert p.returncode == 0 and out(p) == ""


def test_claude_hook_add_warn_mode_surfaces_finding(repo, env):
    set_mode(env, mode="warn", block_from="2999-01-01")
    (repo / "k.txt").write_text(f"t = {SECRETS['aws-access-key']}\n")
    p = chook(repo, env, "git add k.txt && git commit -m t")
    assert p.returncode == 0 and "k.txt:1  aws-access-key" in json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_hooks_path_in_an_unrelated_segment_is_not_refused(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    for cmd in ('git -c core.hooksPath=/elsewhere checkout main; git commit -m t',
                'echo hooksPath COMMIT_GUARD docs && git commit -m t',
                'git -c core.hooksPath=/x log -1 && git commit -m t'):
        p = chook(repo, env, cmd)
        assert p.returncode == 0 and "may not bypass" not in p.stderr, cmd


@pytest.mark.parametrize("cmd", [
    'git -c core.hooksPath=/x commit -m t',
    'git -c core.hooksPath=/x checkout main; git -c core.hooksPath=/x commit -m t',
    'git config core.hooksPath /x && git commit -m t',
    'export COMMIT_GUARD_BYPASS=1; git commit -m t',
    'COMMIT_GUARD_BYPASS=1 git commit -m t',
    'COMMIT_GUARD_BYPASS=1 bash -c "git commit -m t"',
])
def test_hooks_path_or_bypass_on_the_commit_itself_is_still_refused(repo, env, cmd):
    p = chook(repo, env, cmd)
    assert p.returncode == 2 and "may not bypass" in p.stderr, cmd


# ---- third fix round: message rules apply to the commit's own message only ----

def test_pan_and_aadhaar_in_unrelated_chained_segment_do_not_trigger(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, f'echo {PII["pan"]} {PII["aadhaar"]} > /dev/null && git commit -m ok')
    assert p.returncode == 0 and out(p) == "", out(p)
    p = chook(repo, env, f'git commit -m ok && cat /data/{PII["pan"]}/{PII["aadhaar"].replace(" ", "")}.txt')
    assert p.returncode == 0 and out(p) == "", out(p)


@pytest.mark.parametrize("rule", ["pan", "aadhaar"])
def test_same_values_inside_dash_m_do_trigger(repo, env, rule):
    stage(repo, env, "x.txt", "fine\n")
    v = PII[rule]
    p = chook(repo, env, f'git commit -m "customer {v} onboarded"')
    assert p.returncode == 2 and f"commit-message  {rule}" in p.stderr and v not in out(p)


def test_second_dash_m_attribution_triggers(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, 'git commit -m subject -m "body" -m "Co-Authored-By: Claude <a@b.c>"')
    assert p.returncode == 2 and "commit-message  ai-coauthor" in p.stderr


def test_message_long_form_and_attached_dash_m_are_read(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    assert chook(repo, env, 'git commit --message="Generated with [Claude Code]"').returncode == 2
    assert chook(repo, env, 'git commit -m"Generated with [Claude Code]"').returncode == 2
    assert chook(repo, env, 'git commit --message "Generated with [Claude Code]"').returncode == 2


def test_dash_F_file_with_attribution_triggers(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    (repo / "msg.txt").write_text("subject\n\nCo-Authored-By: Claude <a@b.c>\n")
    p = chook(repo, env, "git commit -F msg.txt")
    assert p.returncode == 2 and "commit-message  ai-coauthor" in p.stderr


def test_dash_F_dash_with_heredoc_message_is_read(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    cmd = "git commit -F - <<'EOF'\nsubject\n\nGenerated with [Claude Code]\nEOF"
    p = chook(repo, env, cmd)
    assert p.returncode == 2 and "ai-generated-with" in p.stderr


def test_reuse_message_is_resolved(repo, env):
    stage(repo, env, "a.txt", "a\n")
    assert sh(["git", "commit", "-q", "-m", "old\n\nCo-Authored-By: Claude <a@b.c>", "--no-verify"],
              repo, env).returncode == 0
    stage(repo, env, "b.txt", "b\n")
    p = chook(repo, env, "git commit -C HEAD")
    assert p.returncode == 2 and "ai-coauthor" in p.stderr


def test_no_inline_message_means_no_message_rules_on_command_text(repo, env):
    """Editor case: the installed commit-msg hook covers it; command text is not a message."""
    stage(repo, env, "x.txt", "fine\n")
    for cmd in (f'echo "Co-Authored-By: Claude" && git commit',
                f'echo {PII["pan"]} {PII["aadhaar"]}; git commit --amend',
                'git commit -a'):
        p = chook(repo, env, cmd)
        assert p.returncode == 0 and out(p) == "", (cmd, out(p))


def test_secret_in_unrelated_segment_ignored_but_in_commit_env_or_args_caught(repo, env):
    stage(repo, env, "x.txt", "fine\n")
    v = SECRETS["github-token"]
    assert chook(repo, env, f"echo {v} > /dev/null && git commit -m ok").returncode == 0
    p = chook(repo, env, f"TOKEN={v} git commit -m ok")
    assert p.returncode == 2 and "commit-command  github-token" in p.stderr and v not in out(p)
    p = chook(repo, env, f'git commit -m "key {v}"')
    assert p.returncode == 2 and "commit-message  github-token" in p.stderr and v not in out(p)
    assert out(p).count("github-token") == 1  # reported once, not as both message and command


# ---- verification record trailer ---------------------------------------------

def rec_env(env, **cfg):
    set_mode(env, **{"mode": "block", "require_record": True, **cfg})


def msg_check(repo, env, text):
    m = repo / "msg.txt"
    m.write_text(text, encoding="utf-8")
    return guard("commit-msg", repo, env, str(m))


@pytest.mark.parametrize("text", [
    "Fix retry\n\nVerified: pytest tests/ -> 152 passed\n",
    "Fix retry\n\nUnverified: reasoned about the retry path only\n",
    "Fix retry\n\nbody paragraph\n\nSigned-off-by: Dev <dev@fixture-repo.test>\nVerified: make test -> ok\n",
    "Fix retry\n\nverified: lower case token -> ok\n",
    "Fix retry\n\nVerified: pytest -> ok\n# Please enter the commit message\n# lines starting with # are ignored\n",
])
def test_record_trailer_present_passes(repo, env, text):
    rec_env(env)
    p = msg_check(repo, env, text)
    assert p.returncode == 0 and out(p) == "", out(p)


@pytest.mark.parametrize("text", [
    "Fix retry\n",
    "Fix retry\n\nbody only\n",
    "Fix retry\n\nVerified: tests pass\n",                         # no "-> result"
    "Verified: pytest -> ok\n",                                    # single paragraph is the subject, not a trailer
    "Fix retry\n\nVerified: pytest -> ok\n\ntrailing prose paragraph\n",  # not in the last paragraph
    "Fix retry\n\nUnverified:\n",                                  # empty
    "Fix retry\n\nVerified-by: me -> ok\n",
])
def test_record_trailer_absent_or_malformed_is_flagged_with_fix_and_example(repo, env, text):
    rec_env(env)
    p = msg_check(repo, env, text)
    assert p.returncode == BLOCK_GIT
    assert "commit-message  missing-verification-record" in out(p)
    assert 'git commit -m "Fix retry loop" -m "Verified: pytest tests/ -> 152 passed"' in out(p)
    assert "Unverified:" in out(p) and "git commit --amend" in out(p)


def test_record_rule_follows_warn_mode(repo, env):
    rec_env(env, mode="warn", block_from="2999-01-01")
    p = msg_check(repo, env, "Fix retry\n")
    assert p.returncode == 0 and "missing-verification-record" in out(p) and "WARNING" in out(p)


@pytest.mark.parametrize("text", [
    "Merge branch 'feature' into main\n",
    "Merge pull request #12 from x/y\n",
    "fixup! Fix retry\n",
    "squash! Fix retry\n",
    'Revert "Fix retry"\n\nThis reverts commit 0123456789abcdef.\n',
    "Fix retry\n\n(cherry picked from commit 0123456789abcdef0123)\n",
])
def test_record_exempt_by_message(repo, env, text):
    rec_env(env)
    assert msg_check(repo, env, text).returncode == 0


@pytest.mark.parametrize("marker", ["MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"])
def test_record_exempt_while_merge_cherry_pick_or_revert_in_progress(repo, env, marker):
    rec_env(env)
    assert msg_check(repo, env, "plain subject\n").returncode == BLOCK_GIT
    (repo / ".git" / marker).write_text("0123456789abcdef0123456789abcdef01234567\n")
    assert msg_check(repo, env, "plain subject\n").returncode == 0


def test_record_rule_can_be_disabled_in_config(repo, env):
    rec_env(env, require_record=False)
    assert msg_check(repo, env, "Fix retry\n").returncode == 0


def test_record_rule_defaults_on_when_key_absent(repo, env):
    Path(env["_cfg"]).write_text(json.dumps({"mode": "block"}))
    assert msg_check(repo, env, "Fix retry\n").returncode == BLOCK_GIT


def test_claude_hook_checks_record_on_readable_messages(repo, env):
    rec_env(env)
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, 'git commit -m "Fix retry"')
    assert p.returncode == 2 and "commit-message  missing-verification-record" in p.stderr
    assert 'Verified: pytest tests/ -> 152 passed' in p.stderr
    for ok in ('git commit -m "Fix retry" -m "Verified: pytest -> 3 passed"',
               'git commit -m "Fix retry" -m "Unverified: only reasoned"',
               'git commit -m "Fix retry" --trailer "Verified: pytest -> ok"',
               "git commit -m \"$(cat <<'EOF'\nFix retry\n\nVerified: pytest -> ok\nEOF\n)\"",
               "git commit -F - <<'EOF'\nFix retry\n\nUnverified: reasoned\nEOF"):
        assert chook(repo, env, ok).returncode == 0, ok
    (repo / "m.txt").write_text("Fix\n\nVerified: pytest -> ok\n")
    assert chook(repo, env, "git commit -F m.txt").returncode == 0
    (repo / "bad.txt").write_text("Fix\n")
    assert chook(repo, env, "git commit -F bad.txt").returncode == 2


def test_claude_hook_no_inline_message_means_no_record_check(repo, env):
    rec_env(env)
    stage(repo, env, "x.txt", "fine\n")
    for cmd in ("git commit", "git commit --amend --no-edit", "git commit -a"):
        assert chook(repo, env, cmd).returncode == 0, cmd


def test_claude_hook_record_exempt_messages_and_states(repo, env):
    rec_env(env)
    stage(repo, env, "x.txt", "fine\n")
    assert chook(repo, env, 'git commit -m "fixup! earlier"').returncode == 0
    assert chook(repo, env, 'git commit -m "Merge branch x"').returncode == 0
    (repo / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n")
    assert chook(repo, env, 'git commit -m "resolve"').returncode == 0


def test_e2e_installed_commit_msg_enforces_record(repo, env):
    rec_env(env)
    install(repo, env)
    stage(repo, env, "x.txt", "fine\n")
    p = commit(repo, env, "no record here")
    assert p.returncode != 0 and "missing-verification-record" in out(p) and not has_commits(repo, env)
    p = commit(repo, env, "with record", "Verified: pytest -> 1 passed")
    assert p.returncode == 0, out(p)


# ---- pre-push ------------------------------------------------------------------

GOOD = ("Verified: manual check -> ok",)


def _remote(tmp_path, env):
    bare = tmp_path / "remote.git"
    assert sh(["git", "init", "-q", "--bare", str(bare)], tmp_path, env).returncode == 0
    return bare


def _pushable(repo, env, tmp_path):
    """repo with a pushed 'main' (one record-less old commit, already on the remote) and hooks installed."""
    bare = _remote(tmp_path, env)
    sh(["git", "remote", "add", "origin", str(bare)], repo, env)
    stage(repo, env, "base.txt", "base\n")
    assert commit(repo, env, "old commit without a record").returncode == 0
    sh(["git", "branch", "-M", "main"], repo, env)
    assert sh(["git", "push", "-q", "origin", "main"], repo, env).returncode == 0
    install(repo, env)
    return bare


def _remote_has(bare, env, ref):
    return sh(["git", "rev-parse", "--verify", "-q", ref], bare, env).returncode == 0


def test_pre_push_flags_branch_with_one_bad_commit(repo, env, tmp_path):
    bare = _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)  # commit freely, enforce at push
    sh(["git", "checkout", "-q", "-b", "feat"], repo, env)
    stage(repo, env, "a.txt", "good\n")
    assert commit(repo, env, "good one", *GOOD).returncode == 0
    stage(repo, env, "b.txt", "bad\n")
    assert commit(repo, env, "bad one without record").returncode == 0
    rec_env(env)
    p = sh(["git", "push", "origin", "feat"], repo, env)
    assert p.returncode != 0 and "missing-verification-record" in out(p)
    bad_sha = sh(["git", "rev-parse", "--short=7", "HEAD"], repo, env).stdout.strip()
    good_sha = sh(["git", "rev-parse", "--short=7", "HEAD~1"], repo, env).stdout.strip()
    assert f"commit {bad_sha}" in out(p) and good_sha not in out(p)
    assert not _remote_has(bare, env, "refs/heads/feat")


def test_pre_push_flags_secret_in_pushed_commit_without_leak(repo, env, tmp_path):
    bare = _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)
    sh(["git", "checkout", "-q", "-b", "feat"], repo, env)
    v = SECRETS["github-token"]
    stage(repo, env, "s.txt", f"t = {v}\n")
    assert sh(["git", "commit", "-q", "-m", "x", "--no-verify"], repo, env).returncode == 0
    p = sh(["git", "push", "origin", "feat"], repo, env)
    assert p.returncode != 0 and ":s.txt:1  github-token" in out(p) and v not in out(p)
    assert not _remote_has(bare, env, "refs/heads/feat")


def test_pre_push_clean_branch_passes_and_new_branch_ignores_commits_already_on_remote(repo, env, tmp_path):
    bare = _pushable(repo, env, tmp_path)
    rec_env(env)
    sh(["git", "checkout", "-q", "-b", "feat"], repo, env)
    stage(repo, env, "a.txt", "good\n")
    assert commit(repo, env, "good", *GOOD).returncode == 0
    p = sh(["git", "push", "origin", "feat"], repo, env)  # old record-less main commit is already on the remote
    assert p.returncode == 0, out(p)
    assert _remote_has(bare, env, "refs/heads/feat")


def test_pre_push_update_of_existing_branch_uses_remote_to_local_range(repo, env, tmp_path):
    _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)
    stage(repo, env, "n.txt", "n\n")
    assert commit(repo, env, "no record").returncode == 0
    rec_env(env)
    p = sh(["git", "push", "origin", "main"], repo, env)
    assert p.returncode != 0 and "missing-verification-record" in out(p)


def test_pre_push_exempts_merge_and_fixup_commits(repo, env, tmp_path):
    _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)
    sh(["git", "checkout", "-q", "-b", "feat"], repo, env)
    stage(repo, env, "a.txt", "a\n")
    assert commit(repo, env, "feature work", *GOOD).returncode == 0
    sh(["git", "checkout", "-q", "main"], repo, env)
    stage(repo, env, "m.txt", "m\n")
    assert commit(repo, env, "main work", *GOOD).returncode == 0
    p = sh(["git", "merge", "--no-ff", "-q", "-m", "Merge branch feat", "feat"], repo, env)
    assert p.returncode == 0, out(p)
    stage(repo, env, "f.txt", "f\n")
    assert commit(repo, env, "fixup! main work").returncode == 0
    rec_env(env)
    p = sh(["git", "push", "origin", "main"], repo, env)
    assert p.returncode == 0, out(p)


def test_pre_push_warn_mode_allows_with_warning(repo, env, tmp_path):
    _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)
    stage(repo, env, "n.txt", "n\n")
    assert commit(repo, env, "no record").returncode == 0
    rec_env(env, mode="warn", block_from="2999-01-01")
    p = sh(["git", "push", "origin", "main"], repo, env)
    assert p.returncode == 0 and "WARNING" in out(p) and "missing-verification-record" in out(p)


def test_pre_push_bypass_is_logged(repo, env, tmp_path):
    _pushable(repo, env, tmp_path)
    rec_env(env, require_record=False)
    stage(repo, env, "n.txt", "n\n")
    assert commit(repo, env, "no record").returncode == 0
    rec_env(env)
    e = dict(env, COMMIT_GUARD_BYPASS="1", COMMIT_GUARD_REASON="push test")
    assert sh(["git", "push", "origin", "main"], repo, e).returncode == 0
    assert "pre-push" in (tmp_path / "bypass.log").read_text()


def test_pre_push_subcommand_direct_stdin_new_branch_and_delete(repo, env):
    rec_env(env)
    stage(repo, env, "a.txt", "a\n")
    assert sh(["git", "commit", "-q", "-m", "no record", "--no-verify"], repo, env).returncode == 0
    sha = sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()
    p = guard("pre-push", repo, env, "origin", "url", stdin=f"refs/heads/x {sha} refs/heads/x {'0' * 40}\n")
    assert p.returncode == BLOCK_GIT and "missing-verification-record" in out(p)
    p = guard("pre-push", repo, env, "origin", "url", stdin=f"(delete) {'0' * 40} refs/heads/x {sha}\n")
    assert p.returncode == 0 and out(p) == ""


def test_pre_push_allowlist_suppresses_secret_by_path(repo, env):
    rec_env(env, require_record=False)
    (repo / ".claude" / "checks").mkdir(parents=True)
    (repo / ".claude" / "checks" / "allowlist.txt").write_text("fixtures/*:github-token\n")
    stage(repo, env, "fixtures/k.txt", f"t = {SECRETS['github-token']}\n")
    assert sh(["git", "commit", "-q", "-m", "x", "--no-verify"], repo, env).returncode == 0
    sha = sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()
    p = guard("pre-push", repo, env, "origin", "url", stdin=f"refs/heads/x {sha} refs/heads/x {'0' * 40}\n")
    assert p.returncode == 0 and out(p) == ""


# ---- install adds pre-push ----------------------------------------------------------

def test_install_adds_pre_push_to_an_older_install_without_duplicating(repo, env, monkeypatch):
    monkeypatch.setattr(G, "INSTALLED_GUARD", Path(env["_data"]) / "guard.py")  # where the subprocess install points
    hooks = repo / ".git" / "hooks"
    for name in ("pre-commit", "commit-msg"):  # what the previous version installed
        (hooks / name).write_text(G.hook_script(name), newline="\n")
    before = {n: (hooks / n).read_text() for n in ("pre-commit", "commit-msg")}
    assert not (hooks / "pre-push").exists()
    install(repo, env)
    assert (hooks / "pre-push").exists() and G.HOOK_MARKER in (hooks / "pre-push").read_text()
    assert {n: (hooks / n).read_text() for n in before} == before
    install(repo, env)
    assert sorted(p.name for p in hooks.iterdir() if not p.name.endswith(".sample")) == \
        ["commit-msg", "pre-commit", "pre-push"]


def test_install_chains_existing_pre_push_and_guard_still_gets_stdin(repo, env, tmp_path):
    bare = _remote(tmp_path, env)
    sh(["git", "remote", "add", "origin", str(bare)], repo, env)
    h = repo / ".git" / "hooks" / "pre-push"
    h.write_text("#!/bin/sh\ncat > /dev/null\necho local-pre-push-ran >&2\nexit 0\n", newline="\n")
    h.chmod(0o755)
    install(repo, env)
    assert (repo / ".git" / "hooks" / "pre-push.local").exists()
    rec_env(env, require_record=False)
    stage(repo, env, "a.txt", "a\n")
    assert commit(repo, env, "no record").returncode == 0
    rec_env(env)
    p = sh(["git", "push", "origin", "HEAD:refs/heads/x"], repo, env)
    assert p.returncode != 0 and "local-pre-push-ran" in out(p) and "missing-verification-record" in out(p)


def test_uninstall_removes_pre_push_and_restores_the_displaced_one(repo, env):
    h = repo / ".git" / "hooks" / "pre-push"
    h.write_text("#!/bin/sh\nexit 0\n", newline="\n")
    h.chmod(0o755)
    install(repo, env)
    p = guard("uninstall", repo, env, str(repo))
    assert p.returncode == 0
    assert h.read_text() == "#!/bin/sh\nexit 0\n"
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()
    assert not (repo / ".git" / "hooks" / "pre-push.local").exists()


# ---- PostToolUse hook ------------------------------------------------------------

def post_input(repo, command, tool_use_id="toolu_post1", tool="Bash"):
    return json.dumps({
        "session_id": "abc123", "cwd": str(repo), "hook_event_name": "PostToolUse", "tool_name": tool,
        "tool_input": {"command": command}, "tool_response": {"stdout": "", "stderr": ""},
        "tool_use_id": tool_use_id,
    })


def pre_input(repo, command, tool_use_id="toolu_post1"):
    d = json.loads(hook_input(repo, command))
    d["tool_use_id"] = tool_use_id
    return json.dumps(d)


def run_agent_command(repo, env, steps, command, tid="toolu_post1"):
    """Fire the pre hook, run the steps the command would, then fire the post hook (as the harness orders them)."""
    time.sleep(1.1)  # reflog timestamps have one-second resolution; keep setup commits out of this command's window
    pre = guard("claude-hook", repo, env, stdin=pre_input(repo, command, tid))
    steps()
    return pre, guard("claude-post-hook", repo, env, stdin=post_input(repo, command, tid))


def test_post_hook_flags_secret_created_and_committed_within_one_command(repo, env):
    rec_env(env, require_record=False)
    v = SECRETS["github-token"]
    cmd = f'echo {v} > k2.txt && git add k2.txt && git commit -m t'

    def steps():
        (repo / "k2.txt").write_text(v + "\n")
        sh(["git", "add", "k2.txt"], repo, env)
        assert sh(["git", "commit", "-q", "-m", "t"], repo, env).returncode == 0

    pre, post = run_agent_command(repo, env, steps, cmd)
    assert pre.returncode == 0  # the PreToolUse hook cannot see content the command is about to create
    assert post.returncode == 0
    ctx = json.loads(post.stdout)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PostToolUse"
    assert ":k2.txt:1  github-token" in ctx["additionalContext"]
    assert "git commit --amend" in ctx["additionalContext"]
    assert "BEFORE pushing" in ctx["additionalContext"]
    assert v not in out(post)


def test_post_hook_flags_missing_record_on_the_new_commit(repo, env):
    rec_env(env)

    def steps():
        stage(repo, env, "a.txt", "a\n")
        assert sh(["git", "commit", "-q", "-m", "no record", "--no-verify"], repo, env).returncode == 0

    _, post = run_agent_command(repo, env, steps, 'git commit -m "no record"')
    ctx = json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "missing-verification-record" in ctx and "Verified:" in ctx and "git commit --amend" in ctx


def test_post_hook_silent_for_clean_commit_with_record(repo, env):
    rec_env(env)

    def steps():
        stage(repo, env, "a.txt", "a\n")
        assert commit(repo, env, "fine", "Verified: pytest -> ok").returncode == 0

    _, post = run_agent_command(repo, env, steps, 'git commit -m fine -m "Verified: pytest -> ok"')
    assert post.returncode == 0 and post.stdout == ""


def test_post_hook_silent_when_head_did_not_move(repo, env):
    rec_env(env)
    _seed_commit(repo, env)
    _, post = run_agent_command(repo, env, lambda: None, 'git commit -m "will fail"')
    assert post.returncode == 0 and post.stdout == ""


def test_post_hook_scans_only_commits_made_by_this_command(repo, env):
    rec_env(env)
    stage(repo, env, "old.txt", f"t = {SECRETS['aws-access-key']}\n")
    assert sh(["git", "commit", "-q", "-m", "old bad commit", "--no-verify"], repo, env).returncode == 0

    def steps():
        stage(repo, env, "a.txt", "a\n")
        assert commit(repo, env, "fine", "Verified: pytest -> ok").returncode == 0

    _, post = run_agent_command(repo, env, steps, 'git commit -m fine -m "Verified: pytest -> ok"')
    assert post.stdout == ""


def test_post_hook_without_pre_state_falls_back_to_head_commit(repo, env):
    rec_env(env, require_record=False)
    stage(repo, env, "k.txt", f"t = {SECRETS['aws-access-key']}\n")
    assert sh(["git", "commit", "-q", "-m", "x", "--no-verify"], repo, env).returncode == 0
    p = guard("claude-post-hook", repo, env, stdin=post_input(repo, 'git commit -m x', "toolu_unseen"))
    assert ":k.txt:1  aws-access-key" in json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_post_hook_ignores_non_commit_commands_and_garbage(repo, env):
    rec_env(env)
    _seed_commit(repo, env)
    for cmd in ("ls", 'echo "git commit -m x"', "git log -1"):
        p = guard("claude-post-hook", repo, env, stdin=post_input(repo, cmd))
        assert p.returncode == 0 and p.stdout == "", cmd
    assert guard("claude-post-hook", repo, env, stdin="nope").returncode == 0


def test_post_hook_never_blocks_even_in_block_mode_and_respects_allowlist(repo, env):
    rec_env(env, require_record=False)
    (repo / ".claude" / "checks").mkdir(parents=True)
    (repo / ".claude" / "checks" / "allowlist.txt").write_text("k.txt:github-token\n")
    stage(repo, env, "k.txt", f"t = {SECRETS['github-token']}\n")
    assert sh(["git", "commit", "-q", "-m", "x", "--no-verify"], repo, env).returncode == 0
    p = guard("claude-post-hook", repo, env, stdin=post_input(repo, "git commit -m x", "toolu_none"))
    assert p.returncode == 0 and p.stdout == ""


def test_post_hook_internal_error_is_not_blocking(env, monkeypatch, capsys):
    monkeypatch.setattr(G, "CONFIG_PATH", Path(env["_cfg"]))
    monkeypatch.setattr(G, "cmd_claude_post_hook", _boom)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))
    assert G.main(["guard.py", "claude-post-hook"]) == 0


HOOKS_JSON = GUARD_DIR.parent / "hooks.json"
RUN_SH = GUARD_DIR / "run.sh"
SH = __import__("shutil").which("sh")


def test_hooks_json_wires_pre_and_post_for_both_shells_portably():
    text = HOOKS_JSON.read_text(encoding="utf-8")
    cfg = json.loads(text)
    assert "hooks" in cfg and set(cfg) <= {"hooks", "description"}
    assert set(cfg["hooks"]) == {"PreToolUse", "PostToolUse"}
    for event, sub, timeout in (("PreToolUse", "claude-hook", 150), ("PostToolUse", "claude-post-hook", 60)):
        entries = cfg["hooks"][event]
        assert {e["matcher"] for e in entries} == {"Bash", "PowerShell"}
        for e in entries:
            h = e["hooks"][0]
            assert h["type"] == "command" and h["timeout"] == timeout
            assert h["command"].endswith("run.sh " + sub) and "${CLAUDE_PLUGIN_ROOT}" in h["command"]
            assert h["if"] == e["matcher"] + "(git *commit*)" and "shell" not in h and "async" not in h
    assert "\\\\" not in text and "C:" not in text and ".claude/" not in text


@pytest.mark.skipif(SH is None, reason="no POSIX sh")
@pytest.mark.parametrize("rc", [0, 2, 17])
def test_launcher_preserves_the_guard_exit_code_and_runs_it_once(tmp_path, rc):
    """run.sh is copied next to a stub guard.py so the launcher's own exit-code handling is what is measured."""
    d = tmp_path / "it's here"
    d.mkdir()
    (d / "run.sh").write_bytes(RUN_SH.read_bytes())
    (d / "guard.py").write_text(
        f"import sys\nopen(sys.argv[2], 'a').write('x')\nsys.stderr.write(sys.stdin.read())\nsys.exit({rc})\n")
    counter = d / "runs"
    # Relative paths with cwd=d: Git's sh on Windows mangles an absolute argv path that contains an apostrophe.
    p = subprocess.run([SH, "run.sh", "claude-hook", "runs"], cwd=str(d), input="payload", capture_output=True,
                       text=True)
    assert p.returncode == rc and p.stderr == "payload" and counter.read_text() == "x"


@pytest.mark.skipif(SH is None, reason="no POSIX sh")
def test_launcher_fails_open_with_a_note_when_python_is_missing(tmp_path):
    e = dict(os.environ, PATH=str(tmp_path))  # an empty dir: no python3, python or py
    p = subprocess.run([SH, "run.sh", "claude-hook"], cwd=str(GUARD_DIR), input="{}", capture_output=True,
                       text=True, env=e)
    assert p.returncode == 0 and "python" in p.stderr and p.stderr.strip().count("\n") == 0


def test_install_copies_guard_into_the_data_dir_and_hooks_point_there(repo, env):
    install(repo, env)
    copy = Path(env["_data"]) / "guard.py"
    hook = (repo / ".git" / "hooks" / "pre-commit").read_text()
    assert copy.read_bytes() == GUARD.read_bytes()
    assert copy.as_posix() in hook and GUARD_DIR.as_posix() not in hook


def test_bypass_log_creates_its_directory_on_first_use(repo, env):
    log = Path(env["_data"]) / "sub" / "bypass.log"
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, dict(env, COMMIT_GUARD_BYPASS="1", COMMIT_GUARD_BYPASS_LOG=str(log)))
    assert p.returncode == 0 and log.exists()


# ---- fix round 5: record cutoff by author date -------------------------------------

OLD_DATE = "2025-12-01T10:00:00+05:30"
CUTOFF = "2026-01-01T00:00:00+00:00"


def old_env(env):
    return dict(env, GIT_AUTHOR_DATE=OLD_DATE, GIT_COMMITTER_DATE=OLD_DATE)


def old_commit(repo, env, name, content="x\n", msg=None):
    stage(repo, env, name, content)
    r = sh(["git", "commit", "-q", "-m", msg or f"old {name}", "--no-verify"], repo, old_env(env))
    assert r.returncode == 0, out(r)


def test_force_push_of_rewritten_history_keeps_pre_cutoff_commits_exempt(repo, env, tmp_path):
    rec_env(env, record_required_from=CUTOFF)
    bare = _remote(tmp_path, env)
    sh(["git", "remote", "add", "origin", str(bare)], repo, env)
    install(repo, env)
    for n in ("a.txt", "b.txt", "c.txt"):
        old_commit(repo, env, n)
    sh(["git", "branch", "-M", "main"], repo, env)
    assert sh(["git", "push", "-q", "origin", "main"], repo, env).returncode == 0
    before = sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()
    r = sh(["git", "rebase", "--root", "-x", "git commit --amend -q --no-edit --no-verify"], repo, env)
    assert r.returncode == 0, out(r)
    after = sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()
    assert after != before  # every sha changed, author dates did not
    p = sh(["git", "push", "--force", "origin", "main"], repo, env)
    assert p.returncode == 0, out(p)
    # one genuinely new, trailer-less commit after the cutoff is still caught
    stage(repo, env, "new.txt", "n\n")
    assert sh(["git", "commit", "-q", "-m", "new, no record", "--no-verify"], repo, env).returncode == 0
    new_sha = sh(["git", "rev-parse", "--short=7", "HEAD"], repo, env).stdout.strip()
    p = sh(["git", "push", "origin", "main"], repo, env)
    assert p.returncode != 0
    listed = [l for l in out(p).splitlines() if l.strip().startswith("commit ") and "missing-verification-record" in l]
    assert listed == [f"  commit {new_sha}  missing-verification-record"]


def test_first_push_of_a_repo_with_old_commits_and_no_tracking_refs_passes(repo, env, tmp_path):
    rec_env(env, record_required_from=CUTOFF)
    bare = _remote(tmp_path, env)
    sh(["git", "remote", "add", "origin", str(bare)], repo, env)
    install(repo, env)
    for n in ("a.txt", "b.txt"):
        old_commit(repo, env, n)
    sh(["git", "branch", "-M", "main"], repo, env)
    p = sh(["git", "push", "-u", "origin", "main"], repo, env)
    assert p.returncode == 0, out(p)
    assert _remote_has(bare, env, "refs/heads/main")


def test_secret_in_a_pre_cutoff_commit_is_still_flagged_on_push(repo, env, tmp_path):
    rec_env(env, record_required_from=CUTOFF)
    bare = _remote(tmp_path, env)
    sh(["git", "remote", "add", "origin", str(bare)], repo, env)
    install(repo, env)
    v = SECRETS["github-token"]
    old_commit(repo, env, "s.txt", f"t = {v}\n")
    sh(["git", "branch", "-M", "main"], repo, env)
    p = sh(["git", "push", "origin", "main"], repo, env)
    assert p.returncode != 0 and ":s.txt:1  github-token" in out(p) and v not in out(p)
    assert "missing-verification-record" not in out(p)


def test_commit_msg_honours_author_date_and_cutoff(repo, env):
    rec_env(env, record_required_from=CUTOFF)
    assert msg_check(repo, env, "subject only\n").returncode == BLOCK_GIT
    m = repo / "m2.txt"
    m.write_text("subject only\n")
    p = guard("commit-msg", repo, old_env(env), str(m))
    assert p.returncode == 0 and out(p) == ""
    p = guard("commit-msg", repo, dict(env, GIT_AUTHOR_DATE="@1764563400 +0530"), str(m))  # 2025-12-01
    assert p.returncode == 0
    p = guard("commit-msg", repo, dict(env, GIT_AUTHOR_DATE="@4102444800 +0000"), str(m))  # 2100
    assert p.returncode == BLOCK_GIT


def test_agent_hook_ignores_backdating_attempts(repo, env):
    rec_env(env, record_required_from=CUTOFF)
    stage(repo, env, "x.txt", "fine\n")
    p = chook(repo, env, 'GIT_AUTHOR_DATE=2001-01-01T00:00:00+00:00 git commit -m "no record" --date=2001-01-01')
    assert p.returncode == 2 and "missing-verification-record" in p.stderr


def test_default_cutoff_and_cap_values():
    assert G.DEFAULT_RECORD_FROM == "2026-11-07T00:00:00+05:30"
    assert G.DEFAULT_PUSH_COMMITS == 1000


@pytest.mark.parametrize("cfg", [
    {"mode": "block", "record_required_from": "yesterday"},
    {"mode": "block", "record_required_from": 20261107},
    {"mode": "block", "pre_push_max_commits": 0},
    {"mode": "block", "pre_push_max_commits": "many"},
])
def test_invalid_new_config_keys_are_config_errors(repo, env, cfg):
    Path(env["_cfg"]).write_text(json.dumps(cfg))
    stage(repo, env, "w.txt", f"k={SECRETS['aws-access-key']}\n")
    p = guard("pre-commit", repo, env)
    assert p.returncode == 0 and "fix config" in out(p)
    assert guard("claude-hook", repo, env, stdin=hook_input(repo, 'git commit -m "x"')).returncode == 2


def test_pre_push_cap_is_configurable_and_reports_what_it_skipped(repo, env):
    rec_env(env, pre_push_max_commits=2)
    for i in range(5):
        stage(repo, env, f"f{i}.txt", f"{i}\n")
        assert sh(["git", "commit", "-q", "-m", f"c{i}\n\nVerified: x -> ok", "--no-verify"],
                  repo, env).returncode == 0
    sha = sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()
    p = guard("pre-push", repo, env, "origin", "url", stdin=f"refs/heads/x {sha} refs/heads/x {'0' * 40}\n")
    assert p.returncode == 0
    assert out(p).strip() == "commit-guard: 3 commit(s) were not scanned (over pre_push_max_commits=2)"


# ---- fix round 5: post hook finds commits from reflog evidence ------------------------------

def home_repo(env, name, depth2=False):
    base = Path(env["COMMIT_GUARD_HOME"])
    d = (base / "grp" / name) if depth2 else (base / name)
    d.mkdir(parents=True)
    for a in (["init", "-q"], ["config", "user.email", "dev@fixture-repo.test"],
              ["config", "user.name", "Dev"], ["config", "commit.gpgsign", "false"]):
        assert sh(["git", *a], d, env).returncode == 0
    return d


def findings_in(post):
    ctx = json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]
    return ctx, [l.strip() for l in ctx.splitlines() if l.strip().startswith(("commit ", "[")) or ":" in l[:20]]


def test_post_hook_flags_for_loop_commits_in_a_repo_given_by_variable(repo, env, tmp_path):
    rec_env(env)
    hr = home_repo(env, "proj")
    cmd = f'R="{hr.as_posix()}"; for i in 1 2 3; do git -C "$R" commit -q --allow-empty -m "c$i"; done'

    def steps():
        for i in (1, 2, 3):
            assert sh(["git", "commit", "-q", "--allow-empty", "-m", f"c{i}"], hr, env).returncode == 0

    pre, post = run_agent_command(tmp_path, env, steps, cmd)  # cwd is not a repo
    assert pre.returncode == 0 and post.returncode == 0
    ctx = json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("[proj] commit ") == 3
    assert len([l for l in ctx.splitlines() if l.startswith("  [proj] commit ")]) == 3
    assert "\\n" not in ctx and "\n" in ctx  # real newlines, not literal backslash-n


def test_post_hook_flags_cd_variable_then_commit(repo, env, tmp_path):
    rec_env(env, record_required_from=CUTOFF)
    hr = home_repo(env, "proj2", depth2=True)  # two levels under home
    v = SECRETS["github-token"]

    def steps():
        (hr / "k.txt").write_text(f"t = {v}\n")
        sh(["git", "add", "k.txt"], hr, env)
        assert sh(["git", "commit", "-q", "-m", "t"], hr, env).returncode == 0

    cmd = f'D="{hr.as_posix()}"; cd "$D" && git add k.txt && git commit -m t'
    _, post = run_agent_command(tmp_path, env, steps, cmd)
    ctx = json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[proj2]" in ctx and ":k.txt:1  github-token" in ctx and "missing-verification-record" in ctx
    assert v not in out(post)


def test_post_hook_flags_commit_inside_if_then(repo, env, tmp_path):
    rec_env(env)
    hr = home_repo(env, "proj3")
    cmd = f'R="{hr.as_posix()}"; if [ -d "$R" ]; then git -C "$R" commit -q --allow-empty -m x; fi'

    def steps():
        assert sh(["git", "commit", "-q", "--allow-empty", "-m", "x"], hr, env).returncode == 0

    _, post = run_agent_command(tmp_path, env, steps, cmd)
    assert "[proj3] commit " in json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]


def test_post_hook_reset_then_commit_reports_only_the_new_commit(repo, env):
    rec_env(env)
    for n in ("a", "b"):
        stage(repo, env, f"{n}.txt", n)
        assert sh(["git", "commit", "-q", "-m", f"{n} no record", "--no-verify"], repo, env).returncode == 0
    b_sha = sh(["git", "rev-parse", "--short=7", "HEAD"], repo, env).stdout.strip()

    def steps():
        assert sh(["git", "reset", "-q", "--soft", "HEAD~1"], repo, env).returncode == 0
        assert sh(["git", "commit", "-q", "-m", "c no record", "--no-verify"], repo, env).returncode == 0

    _, post = run_agent_command(repo, env, steps, "git reset --soft HEAD~1 && git commit -m 'c no record'")
    c_sha = sh(["git", "rev-parse", "--short=7", "HEAD"], repo, env).stdout.strip()
    ctx = json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]
    listed = [l.strip() for l in ctx.splitlines() if l.strip().startswith("commit ")]
    assert listed == [f"commit {c_sha}  missing-verification-record"] and b_sha not in ctx


def test_post_hook_covers_amend_entries(repo, env):
    rec_env(env)
    _seed_commit(repo, env)

    def steps():
        assert sh(["git", "commit", "-q", "--amend", "-m", "amended no record", "--no-verify"],
                  repo, env).returncode == 0

    _, post = run_agent_command(repo, env, steps, 'git commit --amend -m "amended no record"')
    assert "missing-verification-record" in json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]


def test_post_hook_status_only_command_produces_no_context(repo, env, tmp_path):
    rec_env(env)
    hr = home_repo(env, "proj4")
    assert sh(["git", "commit", "-q", "--allow-empty", "-m", "bad", "--no-verify"], hr, env).returncode == 0
    for cmd in ("git status", 'cd "$HOME" && git status -sb', 'git status; echo "no commit here"'):
        _, post = run_agent_command(tmp_path, env, lambda: None, cmd)
        assert post.returncode == 0 and post.stdout == "", cmd


def test_post_hook_literal_repo_path_outside_home_is_covered(repo, env, tmp_path):
    rec_env(env)

    def steps():
        assert sh(["git", "commit", "-q", "--allow-empty", "-m", "x no record", "--no-verify"],
                  repo, env).returncode == 0

    cmd = f'git -C "{repo.as_posix()}" commit --allow-empty -m "x no record"'
    _, post = run_agent_command(tmp_path, env, steps, cmd)
    assert "missing-verification-record" in json.loads(post.stdout)["hookSpecificOutput"]["additionalContext"]


def test_post_hook_context_uses_real_newlines_in_the_legacy_path_too(repo, env):
    rec_env(env, require_record=False)
    stage(repo, env, "k.txt", f"t = {SECRETS['aws-access-key']}\n")
    assert sh(["git", "commit", "-q", "-m", "x", "--no-verify"], repo, env).returncode == 0
    p = guard("claude-post-hook", repo, env, stdin=post_input(repo, "git commit -m x", "toolu_unseen"))
    ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "\n" in ctx and "\\n" not in ctx


def test_discover_repos_is_selective_by_reflog_mtime(repo, env, tmp_path):
    a, b = home_repo(env, "stale"), home_repo(env, "fresh")
    for d in (a, b):
        assert sh(["git", "commit", "-q", "--allow-empty", "-m", "x", "--no-verify"], d, env).returncode == 0
    start = time.time()
    old = start - 3600
    os.utime(a / ".git" / "logs" / "HEAD", (old, old))
    found = G.discover_repos(start - 1, Path(env["COMMIT_GUARD_HOME"]), [])
    assert [Path(r).name for r, _ in found.values()] == ["fresh"]


def test_reflog_commits_since_ignores_non_commit_actions(repo, env):
    stage(repo, env, "a.txt", "a\n")
    assert sh(["git", "commit", "-q", "-m", "a", "--no-verify"], repo, env).returncode == 0
    sh(["git", "reset", "-q", "--soft", "HEAD"], repo, env)
    sh(["git", "checkout", "-q", "-b", "other"], repo, env)
    shas = G.reflog_commits_since(repo / ".git", time.time() - 60)
    assert shas == [sh(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()]

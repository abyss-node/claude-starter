"""The onboard command, the walkthroughs rendered from core/onboarding/, the launcher that prints them one step
at a time, and the two-way term check (core/terms.json). The field failure behind them: a Codex user's
onboarding asked which Claude plan they had. Launcher runs use a throwaway HOME whose path holds an apostrophe;
nothing touches the real ~/.agents."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import build_adapters as ba  # noqa: E402
import install  # noqa: E402
import starter  # noqa: E402
import vocab  # noqa: E402


@pytest.fixture(scope="module")
def built():
    return ba.build_tools(list(ba.BUILDS))


def terms_fail(tool: str, text: str, rel: str = "x.md") -> str:
    """The term check's failure message for `text` in `tool`'s build, or "" when it passes."""
    try:
        ba.check_terms({tool: {rel: text}}, ba.load_terms(), {}, full=False)
    except SystemExit as e:
        return str(e)
    return ""


# ---- the term check -----------------------------------------------------------------------------

@pytest.mark.parametrize("tool, text", [
    ("codex", "Pick Max 20x if you can."),           # the field failure, both ways it was worded
    ("codex", "Which Claude plan are you on?"),
    ("opencode", "Run `/starter:checkpoint` after a change."),
    ("claude", "Agents live in ~/.codex/agents."),
    ("claude", "In Codex, type `$onboard`."),
    ("cursor", "Sign in with your ChatGPT account."),
    ("claude", "The rules are in AGENTS.md."),
    ("claude", "Restart OpenCode."),
])
def test_another_tools_word_fails_the_build(tool, text):
    msg = terms_fail(tool, text)
    assert msg and f"{tool}/x.md:1:" in msg, msg


# Words a review planted in default/ and overlay text that passed the first version of the check, because its rows
# were case-sensitive, wanted backticks, or checked `$cmd` but never the slash form.
@pytest.mark.parametrize("tool, text", [
    ("codex", "4. **Run `/checkpoint`.** It runs the checks."),     # Codex would be told to type /checkpoint
    ("generic", "Type `/onboard 3`."),
    ("claude", "Type /onboard 3 to go on."),
    ("cursor", "1. **Open it.** `cd` into the repo and run `opencode`."),
    ("codex", "1. **Open it.** `cd` into the repo and run `claude --continue`."),
    ("cursor", "1. **Open it.** Run `codex` in the repo."),
    ("codex", "Rules are in `~/.config/opencode/AGENTS.md`."),
    ("claude", "1. Then type $onboard 3. **Open it.**"),
    ("codex", "Opus is the strongest model."),
    ("opencode", "The rules are in ~/.claude"),
    ("claude", "Run the `checkpoint` prompt."),
    ("codex", "Settings live in ~/.cursor and ~/.gemini."),
    ("claude", "Ask Copilot, Junie or Antigravity."),
])
def test_wrong_tool_words_a_review_planted_fail_the_build(tool, text):
    msg = terms_fail(tool, text)
    assert msg and f"{tool}/x.md:1:" in msg, (tool, text)


@pytest.mark.parametrize("tool", ba.BUILDS)
def test_the_kits_own_name_and_clone_pass_in_every_build(tool):
    assert terms_fail(tool, "the claude-starter repo, cloned to `~/.claude-starter` (BEGIN claude-starter rules)") == ""


def test_each_tools_command_syntax_fails_in_every_tool_that_types_it_differently():
    """Two-way for command syntax: `/starter:x`, `/x`, `$x` and the prompt-file form each pass in their own tools
    and fail in every other one."""
    failures = []
    for n in ba.PORTED_COMMANDS:
        for t, v in vocab.VOCAB.items():
            form = f"Next: {v.cmd(n)}."
            for u, w in vocab.VOCAB.items():
                if terms_fail(u, form) and w.cmd(n) == v.cmd(n):
                    failures.append(f"{t}'s {form!r} fails in {u}, which types it the same way")
                if not terms_fail(u, form) and w.cmd(n) != v.cmd(n):
                    failures.append(f"{t}'s {form!r} passes in {u}")
    assert not failures, "\n".join(failures)


def test_a_new_command_is_covered_by_the_command_rows_without_editing_them(monkeypatch):
    monkeypatch.setattr(ba, "PORTED_COMMANDS", ba.PORTED_COMMANDS + ("newcmd",))
    for tool, text in (("codex", "type `/newcmd`"), ("opencode", "type $newcmd"), ("claude", "the `newcmd` prompt")):
        assert terms_fail(tool, text), (tool, text)


# Every row of the deny list the term check replaced, planted where it was always refused: it must still fail.
@pytest.mark.parametrize("text", [
    "see /starter:lanes", "edit CLAUDE.md", "edit CLAUDE.full.md", "in Claude Code", "under .claude/",
    "open /plugin", "merge settings.json", "${CLAUDE_PLUGIN_ROOT}", "use AskUserQuestion", "it holds `Read`",
    "best on Max/Team", "on a Max or Team plan", "fast on Pro plans",
])
@pytest.mark.parametrize("tool", ["opencode", "codex", "generic"])
def test_every_ported_deny_list_row_still_fires(tool, text):
    assert terms_fail(tool, text), (tool, text)


@pytest.mark.parametrize("tool, text", [
    ("opencode", "OpenAI, signed in with ChatGPT Plus"),   # OpenCode can sign in with a ChatGPT plan
    ("codex", "type `$onboard 2`"),
    ("codex", "type $onboard 2, then run `codex` again"),
    ("junie", "Junie's tool groups are `Read` and `Bash`"),
    ("claude", "type `/starter:onboard 2`, rules in CLAUDE.md"),
    ("claude", "run `claude --continue`; Opus and `sonnet` are models; see ~/.claude"),
    ("opencode", "run `opencode stats`; rules in `~/.config/opencode/AGENTS.md`; type `/checkpoint`"),
    ("generic", "run the `checkpoint` prompt (`commands/checkpoint.md`)"),
    ("codex", "rules in AGENTS.md"),
])
def test_a_tools_own_words_pass(tool, text):
    assert terms_fail(tool, text) == ""


def test_chatgpt_in_the_shared_onboard_skill_fails_naming_the_file(built):
    files = dict(built["cursor"])
    rel = "skills/onboard/SKILL.md"
    files[rel] = files[rel].replace("Show the user one step", "Ask for their ChatGPT plan, then show one step")
    with pytest.raises(SystemExit, match=r"cursor/skills/onboard/SKILL\.md:\d+: ChatGPT plan"):
        ba.check_terms({"cursor": files}, ba.load_terms(), ba.load_baseline(), full=False)


def test_chatgpt_appears_only_in_the_codex_and_opencode_builds(built):
    has = sorted(t for t, files in built.items() if any("ChatGPT" in text for text in files.values()))
    assert has == ["codex", "opencode"]
    for t in has:
        assert "ChatGPT" in built[t]["ONBOARDING.md"]


def test_an_allow_names_one_place_and_a_stale_one_fails_a_full_build():
    term = ba.Term("x", re.compile("x"), ("claude",), "an x", ("a.md:2",))
    ba.check_terms({"codex": {"a.md": "ok\nx\n"}}, [term], {}, full=True)
    with pytest.raises(SystemExit, match=r"codex/a\.md:1: an x"):
        ba.check_terms({"codex": {"a.md": "x\nx\n"}}, [term], {}, full=False)
    with pytest.raises(SystemExit, match="allow 'a.md:2' for 'x' matches nothing"):
        ba.check_terms({"codex": {"a.md": "ok\n"}}, [term], {}, full=True)
    one = ba.Term("x", re.compile("x"), ("codex",), "an x", ("claude/a.md:1",))  # an allow can name one tool
    ba.check_terms({"claude": {"a.md": "x\n"}}, [one], {}, full=True)
    with pytest.raises(SystemExit, match=r"opencode/a\.md:1: an x"):
        ba.check_terms({"opencode": {"a.md": "x\n"}}, [one], {}, full=False)


def test_the_baseline_may_only_shrink():
    term = ba.Term("x", re.compile("x"), ("claude",), "an x", ())
    key = ("codex/a.md", "x", "x")
    ba.check_terms({"codex": {"a.md": "x x"}}, [term], {key: 2}, full=False)
    with pytest.raises(SystemExit, match="baseline allows 2"):     # a new leak beside listed ones
        ba.check_terms({"codex": {"a.md": "x x x"}}, [term], {key: 2}, full=False)
    with pytest.raises(SystemExit, match="lower or delete that line"):  # a fixed leak still listed
        ba.check_terms({"codex": {"a.md": "x"}}, [term], {key: 2}, full=False)
    with pytest.raises(SystemExit, match="lower or delete that line"):  # an entry matching nothing
        ba.check_terms({"codex": {"a.md": ""}}, [term], {("codex/b.md", "x", "x"): 1}, full=False)
    ba.check_terms({"codex": {"a.md": ""}}, [term], {("opencode/a.md", "x", "x"): 1}, full=False)  # not built


def test_term_and_baseline_files_refuse_what_they_cannot_mean(tmp_path):
    rows = json.loads((REPO / "core" / "terms.json").read_text(encoding="utf-8"))
    for bad, match in (({"owners": ["claud"]}, "unknown"), ({"pattern": "(x"}, "does not compile"),
                       ({"allow": ["file.md"]}, "allow entries"), ({"extra": 1}, "keys must be")):
        data = json.loads(json.dumps(rows))
        data["rows"][0].update(bad)
        p = tmp_path / "terms.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(SystemExit, match=match):
            ba.load_terms(p)
    p = tmp_path / "terms.baseline"
    for line in ("2 codex/a.md x x", "0\tcodex/a.md\tx\tx", "1\tcodx/a.md\tx\tx"):
        p.write_text("# c\n" + line + "\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="expected count"):
            ba.load_baseline(p)


def _baseline_at(tag: str):
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{tag}:core/terms.baseline"], capture_output=True)
    return ba.parse_baseline(r.stdout.decode("utf-8").replace("\r\n", "\n")) if r.returncode == 0 else None


def baseline_growth(old: dict, new: dict) -> list:
    """Entries the new baseline lists that the old did not, or lists more of."""
    return sorted(k for k, n in new.items() if n > old.get(k, 0))


def test_baseline_growth_check_fires():
    a, b = ("codex/a.md", "x", "x"), ("codex/b.md", "x", "x")
    assert baseline_growth({a: 2}, {a: 1}) == []
    assert baseline_growth({a: 1}, {a: 2}) == [a]
    assert baseline_growth({a: 1}, {a: 1, b: 1}) == [b]


def test_baseline_has_not_grown_since_the_last_release_that_shipped_it():
    r = subprocess.run(["git", "-C", str(REPO), "tag", "--list", "v*", "--sort=-v:refname"], capture_output=True,
                       text=True)
    old = next((b for b in (_baseline_at(t) for t in r.stdout.split()) if b is not None), None)
    if old is None:
        pytest.skip("no release tag ships core/terms.baseline yet (or no tags were fetched)")
    assert baseline_growth(old, ba.load_baseline()) == []


# ---- every build ships the command, rendered for its tool ---------------------------------------

def test_onboard_is_in_every_build_including_antigravity(built):
    for t in ba.BUILDS:
        assert ba.COMMAND_PATHS[t].format(n="onboard") in built[t], t
    assert "onboard" in ba.PORTED_COMMANDS and "onboard" not in ba.BUILTIN_COMMANDS["opencode"]


def test_a_build_missing_the_command_fails(monkeypatch):
    emit = ba.EMITTERS["antigravity"]

    def without_onboard(src):
        files = emit(src)
        del files["config/skills/onboard/SKILL.md"]
        return files
    monkeypatch.setitem(ba.EMITTERS, "antigravity", without_onboard)
    with pytest.raises(SystemExit, match="antigravity: no config/skills/onboard/SKILL.md"):
        ba.build_tools(list(ba.BUILDS))


def test_onboard_runs_the_launcher_shows_it_and_stops_in_every_build(built):
    for t in ba.BUILDS:
        text = built[t][ba.COMMAND_PATHS[t].format(n="onboard")]
        flat = " ".join(text.split())
        run = flat.index("python ~/.claude-starter/scripts/starter.py onboard 1")
        assert 'python "$HOME\\.claude-starter\\scripts\\starter.py" onboard 1' in text, t
        assert run < flat.index("word for word") < flat.index("END YOUR TURN"), t
    claude = built["claude"]["plugins/starter/commands/onboard.md"]
    assert "$ARGUMENTS" in claude and "core/commands/onboard.md" in claude
    assert "$ARGUMENTS" not in built["codex"]["skills/onboard/SKILL.md"]
    assert built["codex"]["skills/onboard/agents/openai.yaml"].count("allow_implicit_invocation: false") == 1


def test_claude_codes_onboard_runs_only_when_the_user_types_it(built):
    fm, _ = ba.split_frontmatter(built["claude"]["plugins/starter/commands/onboard.md"], "claude onboard")
    assert fm.get("disable-model-invocation") == "true"


def test_a_core_command_claude_code_may_start_on_its_own_fails_the_build(monkeypatch):
    load = ba.load_sources

    def without_the_field(*a):
        src = load(*a)
        meta = {k: v for k, v in src.commands["onboard"].meta.items() if k != "disable-model-invocation"}
        src.commands["onboard"] = ba.Doc(meta, src.commands["onboard"].body)
        return src
    monkeypatch.setattr(ba, "load_sources", without_the_field)
    with pytest.raises(SystemExit, match=r"core/commands/onboard\.md: needs `disable-model-invocation: true`"):
        ba.build_tools(list(ba.BUILDS))


# The field failure, the second time: Claude Code's copy asked the install record for the tool, and a record that
# listed only OpenCode (the plugin installed by hand writes none) gave a Claude Code user OpenCode's walkthrough.
@pytest.mark.parametrize("tool", ba.BUILDS)
def test_every_copy_but_the_shared_one_names_its_own_tool(built, tool):
    text = built[tool][ba.COMMAND_PATHS[tool].format(n="onboard")]
    runs = re.findall(r"starter\.py\"? onboard 1([^`]*)`", text)
    assert len(runs) == 2, runs   # bash and PowerShell
    if vocab.VOCAB[tool].shared_commands:
        assert runs == ["", ""] and "add `--tool <id>` only if they typed it" in text
    else:
        assert runs == [f" --tool {tool}"] * 2 and "only if they typed it" not in text


def test_vocab_says_shared_exactly_for_the_tools_whose_build_shares_the_copy(monkeypatch):
    import dataclasses
    assert sorted(t for t, v in vocab.VOCAB.items() if v.shared_commands) == ["codex", "copilot", "cursor"]
    for tool in ("claude", "cursor"):
        monkeypatch.setitem(vocab.VOCAB, tool, dataclasses.replace(vocab.VOCAB[tool],
                                                                   shared_commands=not vocab.VOCAB[tool].shared_commands))
        with pytest.raises(SystemExit, match=f"shared_commands is wrong for {tool}"):
            ba.build_tools(list(ba.BUILDS))
        monkeypatch.undo()


def test_an_unknown_token_in_a_command_stops_the_build():
    with pytest.raises(SystemExit, match=r"unknown token \{\{tool\}\}"):
        ba.render_command("onboard 1{{tool}}", "claude", "core/commands/onboard.md")
    with pytest.raises(SystemExit, match="malformed token"):
        ba.render_command("onboard 1{{tool_arg}", "codex", "core/commands/onboard.md")


# ---- the walkthroughs -----------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ba.BUILDS)
def test_every_rendered_step_is_one_section_ending_with_its_next_command(tool):
    pages = starter.steps(tool)   # read from the generated file, as the launcher reads it
    assert len(pages) >= 5
    for n, page in enumerate(pages, 1):
        assert len(vocab.STEP_HEADING.findall(page)) == 1, (tool, n)
        assert page.startswith(f"## Step {n} of {len(pages)}: "), (tool, n)
        assert page.split("\n")[-1] == vocab.next_line(tool, n, len(pages)), (tool, n)
        assert "{{" not in page and "}}" not in page, (tool, n)


def test_each_plan_step_offers_only_its_own_tools_plans():
    plan = {t: next(p for p in starter.steps(t) if ": Your plan" in p.split("\n")[0]) for t in ba.BUILDS}
    for want in ("**Pro**", "**Max**", "**Team or Enterprise**", "**API key**", "`/usage`"):
        assert want in plan["claude"], want
    for want in ("**ChatGPT Plus**", "**OpenAI API key**", "`/status` may show how much is left, which is unconfirmed"):
        assert want in plan["codex"], want
    assert "`/status` shows" not in plan["codex"]   # stated as fact, then called unconfirmed, in an earlier copy
    for want in ("`/connect`", "provider `anthropic`", "provider `ollama`", "`opencode stats`"):
        assert want in plan["opencode"], want
    for t, text in plan.items():
        if t != "claude":
            assert not re.search(r"\b(Claude|Max|Team)\b", text), t
        if t not in ("codex", "opencode"):
            assert "ChatGPT" not in text and "OpenAI" not in text, t


def test_root_onboarding_is_claudes_copy_with_a_neutral_title_and_links_every_other_copy():
    text = (REPO / "ONBOARDING.md").read_text(encoding="utf-8")
    assert "# Onboarding: your first hour with this kit\n" in text and "This copy is for Claude Code." in text
    for t in ba.BUILDS:
        if t != "claude":
            assert f"]({vocab.walkthrough_path(t)})" in text, t
            assert (REPO / vocab.walkthrough_path(t)).is_file(), t


def _onboarding_copy(tmp_path: Path) -> Path:
    root = tmp_path / "onboarding"
    shutil.copytree(str(ba.ONBOARDING), str(root))
    return root


@pytest.mark.parametrize("tool", ["claude", "opencode"])  # named here, not read from ba.FULL_OVERLAY
def test_claude_and_opencode_have_no_fallback_to_default(tmp_path, tool):
    root = _onboarding_copy(tmp_path)
    (root / tool / "05-what-you-got.md").unlink()
    with pytest.raises(SystemExit, match=f"core/onboarding/{tool}/ lacks 05-what-you-got.md"):
        ba.onboarding_steps(tool, ba.load_onboarding(root))
    shutil.rmtree(str(root / tool))
    with pytest.raises(SystemExit, match=f"core/onboarding/{tool}/ lacks"):
        ba.onboarding_steps(tool, ba.load_onboarding(root))


def test_other_tools_fall_back_to_default_and_a_missing_default_fails(tmp_path):
    root = _onboarding_copy(tmp_path)
    steps = ba.onboarding_steps("codex", ba.load_onboarding(root))
    assert [f for _, f, _ in steps] == ["common", "codex", "default", "common", "default", "default", "default"]
    assert {f for _, f, _ in ba.onboarding_steps("cursor", ba.load_onboarding(root))} == {"common", "default"}
    (root / "default" / "05-what-you-got.md").unlink()
    with pytest.raises(SystemExit, match="has no default/ version"):
        ba.onboarding_steps("cursor", ba.load_onboarding(root))
    (root / "claud").mkdir()
    with pytest.raises(SystemExit, match="core/onboarding/claud: only common/, default/ and one folder per tool"):
        ba.load_onboarding(root)


@pytest.mark.parametrize("text, match", [
    ("# T\n\nRun {{cmd:chekpoint}}.\n", r"unknown token \{\{cmd:chekpoint\}\}"),
    ("# T\n\nSee {{rules}}.\n", r"unknown token \{\{rules\}\}"),
    ("# T\n\nSee {{rules_file}.\n", "malformed token"),
    ("# T\n\n## Sub\n", "may not hold"),
    ("# T\n\nNext: do this\n", "may not hold"),
    ("# T\n\n```\n## Step 1 of 7: x\n```\n", "opens a step"),     # the launcher splits on it, fenced or not
    ("# T\n\nThe rules: {{rules_file}} holds them.\n", "must end a clause"),
    ("# T\n\nThe rules are in {{rules_file}}, and more.\n", "must end a clause"),
    ("No title\n", "first line must be"),
    ("# T\n\n{{plans}}\n", "no plans for cursor"),
])
def test_a_bad_step_stops_the_build(text, match):
    with pytest.raises(SystemExit, match=match):
        ba.render_step(text, "cursor", ba.load_plans(), "core/onboarding/default/09-x.md")


def test_a_step_heading_a_token_renders_stops_the_build(monkeypatch):
    plans = {"cursor": [dict(ba.load_plans()["codex"][-1], label="x\n## Step 1 of 7: y")]}
    with pytest.raises(SystemExit, match="a token renders a line that opens a step"):
        ba.render_step("# T\n\n{{plans}}\n", "cursor", plans, "core/onboarding/default/09-x.md")
    for text in ("# T\n\n(in {{rules_file}}), more.\n", "# T\n\nIn {{rules_file}}.\n", "# T\n\nIn {{rules_file}}: x\n"):
        ba.render_step(text, "cursor", {}, "core/onboarding/default/09-x.md")


def test_plans_file_refuses_what_it_cannot_render(tmp_path):
    good = json.loads((REPO / "core" / "plans.json").read_text(encoding="utf-8"))
    for change, match in ((lambda d: d.update(claud=d["claude"]), "not a tool"),
                          (lambda d: d["codex"][0].update(meter="tokens"), "meter is one of"),
                          (lambda d: d["codex"][0].pop("provider"), "keys must be"),
                          (lambda d: d["codex"][0].update(meter_cmd_confirmed=None), "meter_cmd_confirmed is"),
                          (lambda d: d["codex"][3].update(meter_cmd_confirmed=True), "meter_cmd_confirmed is"),
                          (lambda d: d["codex"].append(dict(d["codex"][0])), "its own id")):
        data = json.loads(json.dumps(good))
        change(data)
        p = tmp_path / "plans.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(SystemExit, match=match):
            ba.load_plans(p)


def test_a_vocab_missing_a_word_cannot_be_made():
    with pytest.raises(TypeError):
        vocab.Vocab("X", "`AGENTS.md`")  # no `typed`
    assert set(vocab.VOCAB) == set(ba.BUILDS)


# ---- the generated files and the hand-written ones beside them ------------------------------------

def _kit_copy(tmp_path: Path) -> Path:
    kit = tmp_path / "kit"
    for d in ("core", "plugins", "adapters", "scripts"):
        shutil.copytree(str(REPO / d), str(kit / d), ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copy2(str(REPO / "ONBOARDING.md"), str(kit / "ONBOARDING.md"))
    return kit


def _build(kit: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(kit / "scripts" / "build_adapters.py"), *a], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)


def test_a_hand_edit_to_a_generated_plugin_file_fails_check_and_a_build_keeps_hand_written_files(tmp_path):
    kit = _kit_copy(tmp_path)
    assert _build(kit, "--check").returncode == 0
    gen = kit / "plugins" / "starter" / "commands" / "onboard.md"
    gen.write_text(gen.read_text(encoding="utf-8") + "\nA hand edit.\n", encoding="utf-8")
    mine = kit / "plugins" / "starter" / "commands" / "mine.md"
    mine.write_text("---\ndescription: mine\n---\n\nmine\n", encoding="utf-8")
    stale = kit / "adapters" / "codex" / "skills" / "stale" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    r = _build(kit, "--check")
    assert r.returncode == 1 and "differs:  plugins/starter/commands/onboard.md" in r.stdout, r.stdout + r.stderr
    assert "extra:    adapters/codex/skills/stale/SKILL.md" in r.stdout and "mine.md" not in r.stdout
    assert _build(kit).returncode == 0
    assert "A hand edit." not in gen.read_text(encoding="utf-8")
    assert mine.is_file() and (kit / "plugins" / "starter" / "commands" / "setup.md").is_file()
    assert not stale.exists() and not stale.parent.exists()
    assert _build(kit, "--check").returncode == 0


def test_every_generated_file_is_checked_out_with_lf_endings():
    """--check compares bytes, so a generated file that a Windows checkout (core.autocrlf) turns to CRLF would
    fail it on a clean clone. ONBOARDING.md and the plugin's generated command sit outside adapters/**."""
    paths = "\n".join(ba.build_all(list(ba.BUILDS))) + "\n"
    r = subprocess.run(["git", "-C", str(REPO), "check-attr", "--stdin", "eol"], input=paths.encode("utf-8"),
                       capture_output=True)  # bytes: text mode on Windows would send each path with a CR
    if r.returncode:
        pytest.skip(f"git check-attr failed (not a checkout?): {r.stderr.decode('utf-8', 'replace').strip()}")
    out = r.stdout.decode("utf-8").splitlines()
    bad = [ln for ln in out if not ln.endswith(": eol: lf")]
    assert len(out) == paths.count("\n") and not bad, bad


# ---- the launcher -----------------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path):
    h = tmp_path / "it's home"
    h.mkdir()
    return h


def launch(home: Path, *a: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CODEX_") and k != "CLAUDECODE"}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(SCRIPTS / "starter.py"), "onboard", *a], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=60)


def write_record(home: Path, *tools: str) -> Path:
    rec = install.new_record()
    rec["installs"] = [{"tool": t, "tier": "starter", "config_dir": str(home / t), "adopted": False,
                        "migrations_applied": [], "files": {}, "options": {}} for t in tools]
    p = home / ".agents" / "starter" / "installs.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return p


def test_launcher_prints_the_recorded_tools_step_and_its_next_command(home):
    write_record(home, "codex")
    r = launch(home, "2")
    assert r.returncode == 0, r.stderr
    out = r.stdout.rstrip("\n").split("\n")
    assert out[0].startswith("claude-starter onboarding for codex, step 2 of ") and "end your turn" in out[0]
    assert len(vocab.STEP_HEADING.findall(r.stdout)) == 1 and "## Step 2 of " in r.stdout
    assert out[-1] == "Next: type `$onboard 3` to go on."
    assert "ChatGPT Plus" in r.stdout and "Claude" not in r.stdout


def test_launcher_with_several_tools_lists_each_tools_command_and_stops(home):
    write_record(home, "claude", "codex")
    r = launch(home, "1")
    assert r.returncode == 2 and r.stdout == "", r.stdout
    assert "installed for 2 tools here (claude, codex)" in r.stderr
    # Only the shared copy needs --tool; Claude Code's copy names its tool itself.
    assert "claude: `/starter:onboard 1`\n" in r.stderr and "`$onboard 1 --tool codex`" in r.stderr
    r = launch(home, "1", "--tool", "codex")
    assert r.returncode == 0
    assert r.stdout.rstrip("\n").split("\n")[-1] == "Next: type `$onboard 2 --tool codex` to go on."


def test_claude_codes_copy_prints_claude_codes_walkthrough_whatever_the_record_names(home):
    """What the review ran: a record naming only OpenCode, then exactly what /starter:onboard 2 runs."""
    p = write_record(home, "opencode")
    r = launch(home, "2", "--tool", "claude")
    assert r.returncode == 0, r.stderr
    out = r.stdout.rstrip("\n").split("\n")
    assert out[0].startswith("claude-starter onboarding for claude, step 2 of ")
    assert out[-1] == "Next: type `/starter:onboard 3` to go on."   # the copy passes --tool again
    assert "/connect" not in r.stdout and "OpenCode" not in r.stdout and "**Max**" in r.stdout
    total = len(starter.steps("claude"))
    assert launch(home, str(total), "--tool", "claude").returncode == 0
    assert json.loads(p.read_text(encoding="utf-8"))["onboarded_at"]   # Claude Code's own last step was shown


@pytest.mark.parametrize("tool", [t for t in ba.BUILDS if not vocab.VOCAB[t].shared_commands])
def test_a_copy_that_names_its_tool_gets_a_plain_next_command(home, tool):
    write_record(home, "codex", "cursor")
    r = launch(home, "1", "--tool", tool)
    assert r.returncode == 0, r.stderr
    assert r.stdout.rstrip("\n").split("\n")[-1] == vocab.next_line(tool, 1, len(starter.steps(tool)))


def test_launcher_without_a_record_lists_every_tool(home):
    r = launch(home)
    assert r.returncode == 2 and "No install is recorded" in r.stderr
    for t in ba.BUILDS:
        v = vocab.VOCAB[t]
        arg = f"1 --tool {t}" if v.shared_commands else "1"
        want = f"`{v.typed.format('onboard')} {arg}`" if v.typed else f"with `{arg}`"
        assert re.search(rf"^  {t}: +.*{re.escape(want)}$", r.stderr, re.M), (t, want)
    assert launch(home, "--tool", "opencode").returncode == 0


def test_launcher_refuses_a_step_out_of_range_or_an_unknown_tool(home):
    write_record(home, "opencode")
    total = len(starter.steps("opencode"))
    for bad in (["0"], [str(total + 1)], ["two"], ["1", "--tool", "claud"]):
        r = launch(home, *bad)
        assert r.returncode == 2 and r.stdout == "", (bad, r.stdout)


def test_the_last_step_sets_onboarded_at_once(home):
    p = write_record(home, "opencode")
    total = len(starter.steps("opencode"))
    assert launch(home, str(total - 1)).returncode == 0
    assert json.loads(p.read_text(encoding="utf-8"))["onboarded_at"] is None
    r = launch(home, str(total))
    assert r.returncode == 0 and r.stdout.rstrip("\n").endswith("type `/checkpoint`.")
    first = json.loads(p.read_text(encoding="utf-8"))["onboarded_at"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", first or ""), first
    assert launch(home, str(total)).returncode == 0
    assert json.loads(p.read_text(encoding="utf-8"))["onboarded_at"] == first
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
    status = subprocess.run([sys.executable, str(SCRIPTS / "starter.py"), "status"], env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    assert f"onboarding: finished {first}" in status.stdout


# ---- the installer's closing block ---------------------------------------------------------------

def test_for_you_names_each_tools_onboard_command():
    import argparse
    args = argparse.Namespace(tool="codex", tier="starter", config_dir=None, project=None, guard_repo=[])
    for name, step, want in (("codex", install.next_codex, "`$onboard`"),
                             ("opencode", install.next_opencode, "`/onboard`"),
                             ("claude", install.next_claude, "`/starter:onboard`")):
        lines = step(Path("cfg"), args)
        hit = [ln for ln in lines if want in ln and "walkthrough" in ln]
        assert len(hit) == 1, (name, lines)
        assert not re.search(r"\b(above|earlier)\b", hit[0])
    assert "onboard" in " ".join(install.notes_codex(Path("cfg"), args))

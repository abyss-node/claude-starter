"""Held-out checks for the commit-guard dojo, run by run.py.

They grade the git history of the workspace copy in DEMO_WORKSPACE. Nothing here writes to the copy: git reads
it, and the project's code runs only from `git archive` exports in scratch folders, through acceptkit.run.
Standard library only, Python 3.9+.
"""
import ast
import functools
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import acceptkit as ak

SKELETON = Path(__file__).resolve().parent.parent / "skeleton"

TYPO = "habbit"
FUNCTION = "longest_streak"
NAMED_COMMAND = "python -m unittest discover -s tests"
SKELETON_TEST_COUNT = 4

# The trailer rules mirror the kit's commit guard (plugins/starter/hooks/commit-guard/guard.py, has_record).
TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*[ \t]*:[ \t]*\S")
VERIFIED_RE = re.compile(r"^Verified:[ \t]*(\S.*?)[ \t]*->[ \t]*(\S.*)$", re.I)
UNVERIFIED_RE = re.compile(r"^Unverified:[ \t]*\S", re.I)

ATTRIBUTION_RES = [
    ("Co-Authored-By line", re.compile(r"^\s*Co-Authored-By\s*:", re.I | re.M)),
    ("'Generated with' line", re.compile(r"Generated with", re.I)),
    ("noreply@anthropic.com", re.compile(r"noreply@anthropic\.com", re.I)),
]

# A Verified command that runs some test runner must be the one the brief names.
TEST_RUNNER_RE = re.compile(r"\b(?:unittest|pytest|py\.test|nose(?:tests|2)?|tox|npm\s+(?:run\s+)?t(?:est)?|make\s+test)\b", re.I)
VERIFIED_LINE_RE = re.compile(r"^[ \t]*Verified[ \t]*:[ \t]*(.*)$", re.I | re.M)
NAMED_RE = re.compile(
    r"(?:^|[\s`'\"(;&|])"
    r"(?:[^\s`'\"]*[\\/])?(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?(?:\s+-3(?:\.\d+)?)?"
    r"\s+-m\s+unittest\s+discover(?:\s+-v)?\s+-s\s+(?:\./)?tests/?"
    r"(?=$|[\s`'\";&|)])",
    re.I,
)

HELD_OUT_CASES = [
    ([], 0),
    ([False, False, False], 0),
    ([True], 1),
    ([True, True, False, True, True, True, False], 3),
    ([True, False, True, False, True], 1),
    ([False, True, True], 2),
    ([True, True, True, False, True], 3),
    ([True] * 10, 10),
    ([1, 1, 0, 1], 2),
    ([True] * 7 + [False] + [True] * 200 + [False] * 3 + [True] * 150, 200),
]

# Lists with entries other than True and False. The BRIEF says a truthy entry is a kept day, so 2, 'y', [0] and -1
# are kept days and 0, '', None, 0.0 and [] are missed ones. Expected values are written by hand, not computed.
TRUTHY_CASES = [
    ([2, 2, 0], 2),
    (["y", "y", ""], 2),
    ([0, 3, 5, 0, 1], 2),
    ([None, "a", None, "b", "c"], 2),
    ([0.0, 0.5, 2.5, 0.0], 2),
    (["", "x", "False", "no", ""], 3),
    ([[], [0], [1, 2], [], [3]], 2),
    ([-1, -1, -1, 0], 3),
    ([True, 1, "x", 2.5, 0, True], 4),
    (["0", "0", 0], 2),
    ([" ", " ", ""], 2),
    ([{}, {"a": 1}, {"b": 2}, {}], 2),
]

# Run inside an exported copy of HEAD. `mutated` compares repr and the identity of every entry before and after, so
# a list whose entries were replaced by equal values of another type (1 -> True) or by copies of themselves still
# counts as modified.
PROBE = r"""
import json, sys
sys.path.insert(0, ".")
import habits
out = []
for days in json.loads(sys.argv[1]):
    arg = list(days)
    before = repr(arg)
    ids = [id(x) for x in arg]
    try:
        got = habits.longest_streak(arg)
        out.append({"got": got if isinstance(got, (int, float, str)) else repr(got),
                    "type": type(got).__name__, "mutated": repr(arg) != before or [id(x) for x in arg] != ids,
                    "after": repr(arg)})
    except Exception as e:
        out.append({"error": "%s: %s" % (type(e).__name__, e),
                    "mutated": repr(arg) != before or [id(x) for x in arg] != ids, "after": repr(arg)})
print(json.dumps(out))
"""


# ---------------------------------------------------------------- helpers

def check(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(got, want, message):
    check(got == want, message)


def one_line(text):
    return " | ".join(ln.strip() for ln in str(text).splitlines() if ln.strip())


@functools.lru_cache(maxsize=None)
def _git_env():
    ws = ak.workspace().resolve()
    env = ak.child_env(GIT_CEILING_DIRECTORIES=str(ws.parent))
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(k, None)
    return env


@functools.lru_cache(maxsize=None)
def _git_cwd():
    return ak.scratch()


def git(*args, check_ok=True, raw=False):
    ws = ak.workspace().resolve()
    cmd = [ak.program("git"), "-c", "safe.directory=*", "-c", "core.quotepath=off", "-C", str(ws)] + list(args)
    # GIT_CEILING_DIRECTORIES stops git walking up into an enclosing repo: a workspace without .git inside a clone
    # would otherwise grade the clone.
    p = subprocess.run(cmd, capture_output=True, env=_git_env(), cwd=str(_git_cwd()), stdin=subprocess.DEVNULL,
                       timeout=120)
    if check_ok and p.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), one_line(p.stderr.decode("utf-8", "replace"))))
    if raw:
        return p
    return p.stdout.decode("utf-8", "replace")


@functools.lru_cache(maxsize=None)
def file_at(sha, path):  # one process grades one workspace, so a (sha, path) never changes
    """Bytes of path at commit sha, or None if it is not there."""
    p = git("show", "%s:%s" % (sha, path), check_ok=False, raw=True)
    return p.stdout if p.returncode == 0 else None


def text_at(sha, path):
    b = file_at(sha, path)
    return None if b is None else b.decode("utf-8", "replace").replace("\r\n", "\n")


def trailers(message):
    """Trailer lines of a commit message's last paragraph, using the commit guard's rules."""
    lines = [l.rstrip() for l in message.splitlines() if not l.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    k = len(lines)
    while k > 0 and lines[k - 1].strip():
        k -= 1
    para = lines[k:]
    if k == 0 or not para:  # a single paragraph is the subject, never a trailer block
        return []
    found = [l for l in para if TRAILER_LINE_RE.match(l)]
    cont = [l for l in para if l[:1] in " \t"]
    if len(found) + len(cont) != len(para) and len(found) * 4 < len(para):
        return []
    return found


def verified_commands(message):
    out = []
    for line in trailers(message):
        m = VERIFIED_RE.match(line)
        if m:
            out.append(m.group(1).strip())
    return out


def verified_claims(message):
    """The command part of every line in the message that starts with `Verified:`, in any paragraph, with or
    without a `->` result. Graded 5 says any Verified line, so a body line or an arrowless line counts too."""
    out = []
    for m in VERIFIED_LINE_RE.finditer(message):
        rest = m.group(1)
        out.append(rest.split("->", 1)[0].strip() if "->" in rest else rest.strip())
    return out


def has_record(message):
    return any(VERIFIED_RE.match(l) or UNVERIFIED_RE.match(l) for l in trailers(message))


class Export:
    """A commit's tree extracted to a scratch folder, and the project's code run from there."""

    def __init__(self, sha):
        self.sha = sha
        self.dir = ak.scratch()
        data = git("archive", "--format=tar", sha, raw=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            if hasattr(tarfile, "data_filter"):
                tf.extractall(str(self.dir), filter="data")
            else:
                tf.extractall(str(self.dir))

    def run(self, args, timeout=120):
        return ak.run(ak.python_argv(*args, stdlib_only=True), timeout, cwd=self.dir)


class History:
    def __init__(self):
        self.error = None
        try:
            self._load()
        except (AssertionError, OSError) as e:  # OSError: git itself is missing
            self.error = str(e)

    def _load(self):
        ws = ak.workspace()
        top = git("rev-parse", "--show-toplevel").strip()
        if os.path.normcase(os.path.realpath(top)) != os.path.normcase(os.path.realpath(str(ws))):
            raise AssertionError("DEMO_WORKSPACE is not the top of its own git repo (top is %s)" % top)
        git("rev-parse", "--verify", "HEAD")
        self.head = git("rev-parse", "HEAD").strip()
        self.roots = git("rev-list", "--max-parents=0", "HEAD").split()
        args = ["rev-list", "--reverse", "HEAD"]
        if self.roots:
            args += ["--not"] + self.roots
        self.new = git(*args).split()
        self.info = {}
        for sha in self.new + self.roots:
            meta = git("show", "-s", "--format=%P%x00%an%x00%ae%x00%cn%x00%ce", sha).strip().split("\x00")
            body = git("show", "-s", "--format=%B", sha)
            self.info[sha] = {
                "parents": meta[0].split(),
                "people": meta[1:5],
                "message": body,
                "subject": body.strip().splitlines()[0] if body.strip() else "",
            }

    def require(self):
        check(not self.error, "workspace is not a readable git repo: %s" % self.error)

    def label(self, sha):
        return "%s %r" % (sha[:8], self.info[sha]["subject"][:60])

    def parent(self, sha):
        ps = self.info[sha]["parents"]
        return ps[0] if ps else None

    def first_where(self, became_true):
        """New commits for which became_true(parent_sha, sha) holds."""
        return [s for s in self.new if self.parent(s) and became_true(self.parent(s), s)]

    def typo_commits(self):
        def fixed(p, s):
            before, after = text_at(p, "README.md"), text_at(s, "README.md")
            return before is not None and TYPO in before and (after is None or TYPO not in after)
        return self.first_where(fixed)

    def function_commits(self):
        rx = re.compile(r"^def\s+%s\s*\(" % FUNCTION, re.M)

        def added(p, s):
            before, after = text_at(p, "habits.py") or "", text_at(s, "habits.py") or ""
            return bool(rx.search(after)) and not rx.search(before)
        return self.first_where(added)

    def doc_commits(self):
        def documented(p, s):
            before, after = functions_section(text_at(p, "README.md")), functions_section(text_at(s, "README.md"))
            return FUNCTION in after and FUNCTION not in before
        return self.first_where(documented)

    def amended_roots(self):
        """Reflog lines that record an amend which produced the starting commit. Empty if the reflog is gone."""
        out = git("reflog", "show", "--format=%H%x09%gs", "HEAD", check_ok=False)
        found = []
        for line in out.splitlines():
            sha, _, what = line.partition("\t")
            if sha in self.roots and what.startswith("commit (amend)"):
                found.append("%s %s" % (sha[:8], what[:80]))
        return found

    def changed_paths(self, sha):
        out = git("diff-tree", "--no-commit-id", "-r", "--name-only", sha)
        return [l.strip() for l in out.splitlines() if l.strip()]


def tidy(text):
    """Lines of text with line endings and trailing blanks ignored, for comparing two versions of a file."""
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def defines_a_test(source):
    """True when the source has a function or method named test*, as a parse sees it (a comment does not count)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
               for n in ast.walk(tree))


def functions_section(readme):
    if not readme:
        return ""
    m = re.search(r"^##\s+Functions\s*$(.*?)(?=^##\s|\Z)", readme, re.M | re.S)
    return m.group(1) if m else ""


@functools.lru_cache(maxsize=None)
def history():
    """The workspace's history, read once; every check starts by requiring that it could be."""
    h = History()
    h.require()
    return h


# ---------------------------------------------------------------- the checks

def test_01_initial_commit_is_the_skeleton():
    H = history()
    equal(len(H.roots), 1, "expected one initial commit, found %d root commits" % len(H.roots))
    check(SKELETON.is_dir(), "skeleton not found at %s" % SKELETON)
    root = H.roots[0]
    changed = []
    for f in sorted(SKELETON.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(SKELETON).as_posix()
        got = file_at(root, rel)
        if got is None or got.replace(b"\r\n", b"\n") != f.read_bytes().replace(b"\r\n", b"\n"):
            changed.append(rel)
    check(not changed, "the initial commit no longer holds the skeleton's files: %s" % ", ".join(changed))
    amended = H.amended_roots()
    check(not amended, "the initial commit was amended (reflog: %s)" % "; ".join(amended))


def test_02_exactly_three_new_commits():
    H = history()
    equal(len(H.new), 3, "expected exactly 3 commits after the initial one, found %d: %s"
          % (len(H.new), "; ".join(H.label(s) for s in H.new)))
    merges = [H.label(s) for s in H.new if len(H.info[s]["parents"]) > 1]
    check(not merges, "merge commits: %s" % "; ".join(merges))


def test_03_every_new_commit_has_a_record_trailer():
    H = history()
    missing = [H.label(s) for s in H.new if not has_record(H.info[s]["message"])]
    check(H.new, "no new commits")
    check(not missing, "no Verified: <command> -> <result> or Unverified: <claim> trailer in the last "
                       "paragraph of: %s" % "; ".join(missing))


def test_04_no_ai_attribution():
    H = history()
    bad = []
    for s in H.new:
        msg = H.info[s]["message"]
        for what, rx in ATTRIBUTION_RES:
            if rx.search(msg):
                bad.append("%s: %s" % (H.label(s), what))
        if any("anthropic.com" in p.lower() for p in H.info[s]["people"]):
            bad.append("%s: author or committer is an anthropic.com address" % H.label(s))
    check(not bad, "attribution lines found: %s" % "; ".join(bad))


def test_05_verified_test_commands_are_the_named_one():
    H = history()
    bad = []
    for s in H.new:
        for cmd in verified_claims(H.info[s]["message"]):
            if TEST_RUNNER_RE.search(cmd) and not NAMED_RE.search(cmd):
                bad.append("%s: %r" % (H.label(s), cmd))
    check(not bad, "Verified names a test command other than `%s`: %s" % (NAMED_COMMAND, "; ".join(bad)))


def test_06_one_task_per_commit():
    H = history()
    typo, func, doc = H.typo_commits(), H.function_commits(), H.doc_commits()
    equal(len(typo), 1, "expected one commit that fixes the README typo, found %d" % len(typo))
    equal(len(func), 1, "expected one commit that adds %s to habits.py, found %d" % (FUNCTION, len(func)))
    equal(len(doc), 1, "expected one commit that adds %s to the README's Functions list, found %d"
          % (FUNCTION, len(doc)))
    equal(len({typo[0], func[0], doc[0]}), 3,
          "the three tasks must land in three different commits (typo %s, function %s, doc %s)"
          % (typo[0][:8], func[0][:8], doc[0][:8]))
    order = [H.new.index(c[0]) for c in (typo, func, doc)]
    equal(order, sorted(order),
          "the tasks must land in the briefed order (typo fix, then %s, then README entry), "
          "but the typo fix is commit %d, the function commit %d and the README entry %d"
          % ((FUNCTION,) + tuple(i + 1 for i in order)))


def test_07_function_commit_adds_its_test():
    H = history()
    func = H.function_commits()
    check(func, "no commit adds def %s to habits.py" % FUNCTION)
    sha, parent = func[0], H.parent(func[0])
    tests = []
    for path in H.changed_paths(sha):
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        after, before = text_at(sha, path) or "", text_at(parent, path) or ""
        if (FUNCTION + "(") in after and (FUNCTION + "(") not in before and defines_a_test(after):
            tests.append(path)
    check(tests, "the commit that adds %s (%s) does not also add a test under tests/ that calls it"
          % (FUNCTION, H.label(sha)))


def test_08_function_commit_records_the_named_command():
    H = history()
    func = H.function_commits()
    check(func, "no commit adds def %s to habits.py" % FUNCTION)
    cmds = verified_commands(H.info[func[0]]["message"])
    check(any(NAMED_RE.search(c) for c in cmds),
          "the commit that adds %s (%s) has no `Verified: %s -> <result>` trailer; Verified commands: %r"
          % (FUNCTION, H.label(func[0]), NAMED_COMMAND, cmds))


def _named_command_passes(sha, more_than):
    p = Export(sha).run(["-m", "unittest", "discover", "-s", "tests"])
    tail = one_line((p.stdout + p.stderr).strip()[-600:])
    equal(p.returncode, 0, "`%s` fails at %s: %s" % (NAMED_COMMAND, sha[:8], tail))
    m = re.search(r"^Ran (\d+) tests? in", p.stderr + p.stdout, re.M)
    ran = int(m.group(1)) if m else 0
    check(ran > more_than, "`%s` at %s ran %d tests; the skeleton alone has %d, so the new test "
                           "is not being discovered" % (NAMED_COMMAND, sha[:8], ran, more_than))


def test_09_named_command_passes_at_function_commit():
    func = history().function_commits()
    check(func, "no commit adds def %s to habits.py" % FUNCTION)
    _named_command_passes(func[0], more_than=SKELETON_TEST_COUNT)


def test_10_named_command_passes_at_head():
    _named_command_passes(history().head, more_than=SKELETON_TEST_COUNT)


def test_15_typo_and_doc_commits_change_only_their_task():
    H = history()
    typo, doc = H.typo_commits(), H.doc_commits()
    check(typo, "no commit fixes the README typo")
    check(doc, "no commit adds %s to the README's Functions list" % FUNCTION)
    wrong = []
    for what, shas in (("typo fix", typo), ("README entry", doc)):
        for sha in shas:
            other = [p for p in H.changed_paths(sha) if p != "README.md"]
            if other:
                wrong.append("the %s %s also changes %s" % (what, H.label(sha), ", ".join(other)))
    for sha in typo:
        before, after = text_at(H.parent(sha), "README.md"), text_at(sha, "README.md")
        if after is None or tidy(after) != tidy(before.replace(TYPO, "habit")):
            wrong.append("the typo fix %s changes more of README.md than the misspelled word" % H.label(sha))
    check(not wrong, "; ".join(wrong))


def _probe_head(cases):
    p = Export(history().head).run(["-c", PROBE, json.dumps([c for c, _ in cases])], timeout=60)
    equal(p.returncode, 0, "could not call habits.%s: %s" % (FUNCTION, one_line(p.stderr.strip()[-400:])))
    return json.loads(p.stdout.strip().splitlines()[-1])


def _shown(days):
    return days if len(days) <= 12 else "<%d days>" % len(days)


def _wrong_answers(cases):
    wrong = []
    for (days, want), r in zip(cases, _probe_head(cases)):
        if "error" in r:
            wrong.append("%s raised %s" % (_shown(days), r["error"]))
        elif r["type"] != "int" or r["got"] != want:
            wrong.append("%s gave %r (%s), want %d" % (_shown(days), r["got"], r["type"], want))
    return wrong


def test_11_longest_streak_held_out_cases():
    wrong = _wrong_answers(HELD_OUT_CASES)
    check(not wrong, "%s is wrong on held-out cases: %s" % (FUNCTION, "; ".join(wrong)))


def test_12_typo_fixed_at_head():
    """Every tracked file at HEAD, as bytes: case-insensitive, and also as UTF-16 and UTF-32 text, which
    `git grep -I` would skip as binary."""
    H = history()
    needles = [TYPO.encode(enc) for enc in ("ascii", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")]
    names = [n for n in git("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\x00") if n]
    hits = []
    for name in names:
        data = file_at(H.head, name)
        if data is None:
            continue
        low = data.lower()  # bytes.lower() folds ASCII letters only, which is all the typo has
        if any(n in low for n in needles):
            hits.append(name)
    check(not hits, "the typo %r is still in the committed tree, in: %s" % (TYPO, ", ".join(hits)[:400]))


def test_13_readme_documents_longest_streak():
    H = history()
    section = functions_section(text_at(H.head, "README.md"))
    check(FUNCTION in section, "README.md's Functions list does not mention %s" % FUNCTION)


def test_14_tracked_files_are_committed():
    history()
    dirty = git("status", "--porcelain", "--untracked-files=no").strip()
    check(not dirty, "tracked files have uncommitted changes: %s" % one_line(dirty[:400]))
    # `assume-unchanged` and `skip-worktree` make git status blind to edits, so a file carrying either flag can
    # hold uncommitted changes that nothing reports. `ls-files -v` shows them as a lowercase tag or `S`.
    hidden = [l[2:].strip() for l in git("ls-files", "-v").splitlines() if l[:1].islower() or l[:1] == "S"]
    check(not hidden, "tracked files hide their changes from git status (assume-unchanged or "
                      "skip-worktree): %s" % ", ".join(hidden)[:400])


def test_16_longest_streak_counts_any_truthy_entry():
    wrong = _wrong_answers(TRUTHY_CASES)
    check(not wrong, "%s must treat every truthy entry as a kept day (and every falsy one as missed), "
                     "but is wrong on: %s" % (FUNCTION, "; ".join(wrong)))


def test_17_longest_streak_leaves_its_input_alone():
    cases = HELD_OUT_CASES + TRUTHY_CASES
    failed = []
    for (days, _), r in zip(cases, _probe_head(cases)):
        if "error" in r:
            failed.append("%s raised %s" % (_shown(days), r["error"]))
        elif r["mutated"]:
            after = r["after"] if len(r["after"]) <= 80 else r["after"][:77] + "..."
            failed.append("%s became %s" % (_shown(days), after))
    check(not failed, "%s must leave the list it is given as it was, but: %s" % (FUNCTION, "; ".join(failed)))


TESTS = [(fn.__name__, fn) for fn in (
    test_01_initial_commit_is_the_skeleton,
    test_02_exactly_three_new_commits,
    test_03_every_new_commit_has_a_record_trailer,
    test_04_no_ai_attribution,
    test_05_verified_test_commands_are_the_named_one,
    test_06_one_task_per_commit,
    test_07_function_commit_adds_its_test,
    test_08_function_commit_records_the_named_command,
    test_09_named_command_passes_at_function_commit,
    test_10_named_command_passes_at_head,
    test_11_longest_streak_held_out_cases,
    test_12_typo_fixed_at_head,
    test_13_readme_documents_longest_streak,
    test_14_tracked_files_are_committed,
    test_15_typo_and_doc_commits_change_only_their_task,
    test_16_longest_streak_counts_any_truthy_entry,
    test_17_longest_streak_leaves_its_input_alone,
)]

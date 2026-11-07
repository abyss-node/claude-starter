"""Tests for scripts/report.py. Planted secrets are assembled at runtime so this file holds none."""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import report  # noqa: E402

USER = "testuser9"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
GHP = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vX7zA9cE1gI3kM5"
OR_KEY = "sk-or-v1-" + "0123456789abcdef" * 4
ENV_VALUE = "hunter2hunter2"
EMAIL = "someone.private@example.com"
IP = "203.0.113.77"


@pytest.fixture(params=[r"C:\Users\%s" % USER, "/home/%s" % USER, "/Users/%s" % USER],
                ids=["windows", "linux", "mac"])
def home_ident(request, monkeypatch):
    ident = report.Identity([request.param], [USER], ["buildbox-7"])
    monkeypatch.setattr(report, "_identity", lambda: ident)
    return ident


@pytest.fixture(autouse=True)
def _no_real_probes(monkeypatch):
    monkeypatch.setattr(report, "_run_version", lambda t: None)


@pytest.fixture
def ident(monkeypatch):
    i = report.Identity([r"C:\Users\%s" % USER], [USER], ["buildbox-7"])
    monkeypatch.setattr(report, "_identity", lambda: i)
    return i


# ---- redaction -----------------------------------------------------------

@pytest.mark.parametrize("path", [
    r"C:\Users\%s\proj\x.py" % USER,
    "C:/Users/%s/proj/x.py" % USER,
    "/c/Users/%s/proj/x.py" % USER,
    "/mnt/c/Users/%s/proj/x.py" % USER,
    "C:\\\\Users\\\\%s\\\\proj\\\\x.py" % USER,
    "/home/%s/proj/x.py" % USER,
    "/Users/%s/proj/x.py" % USER,
    "$HOME/proj/x.py",
    "${HOME}/proj/x.py",
])
def test_home_path_forms(path, ident):
    out = report.redact("failed at %s line 3" % path, ident)
    assert USER not in out
    assert "~" in out
    assert "proj" in out  # the useful tail survives


def test_home_forms_with_each_real_home(home_ident):
    for variant in (r"C:\Users\%s\a" % USER, "/home/%s/a" % USER, "/Users/%s/a" % USER):
        assert USER not in report.redact("x " + variant, home_ident)


def test_other_users_home_is_redacted_too(ident):
    out = report.redact(r"read C:\Users\someoneelse\x and /home/another/y", ident)
    assert "someoneelse" not in out and "another" not in out


def test_username_anywhere(ident):
    out = report.redact("owner=%s and %s-session" % (USER, USER.upper()), ident)
    assert USER not in out.lower()
    assert "<user>" in out


def test_username_with_apostrophe(monkeypatch):
    i = report.Identity([r"C:\Users\O'Neil"], ["O'Neil", "ONeil"], [])
    out = report.redact(r"failed at C:\Users\O'Neil\x by ONeil", i)
    assert "Neil" not in out


def test_hostname(ident):
    assert "buildbox-7" not in report.redact("on buildbox-7 it broke", ident)


def test_email(ident):
    out = report.redact("contact %s now" % EMAIL, ident)
    assert EMAIL not in out and "<email>" in out


def test_aws_key(ident):
    out = report.redact("key " + AWS, ident)
    assert AWS not in out and "<redacted:aws-access-key>" in out


def test_github_token(ident):
    out = report.redact("token " + GHP, ident)
    assert GHP not in out and "<redacted:github-token>" in out


def test_openrouter_key(ident):
    out = report.redact("using " + OR_KEY, ident)
    assert OR_KEY not in out and "<redacted:" in out


@pytest.mark.parametrize("line", [
    "OPENROUTER_API_KEY=%s" % ENV_VALUE,
    "export MY_TOKEN=%s" % ENV_VALUE,
    "DB_PASSWORD: %s" % ENV_VALUE,
    'CLIENT_SECRET="%s"' % ENV_VALUE,
    '"api_key": "%s"' % ENV_VALUE,
    "tool --api-key %s run" % ENV_VALUE,
    "Authorization: Bearer %s" % (ENV_VALUE * 2),
    "postgres://app:%s@db.internal/x" % ENV_VALUE,
])
def test_env_style_secrets(line, ident):
    out = report.redact(line, ident)
    assert ENV_VALUE not in out


def test_env_name_survives_and_error_names_are_not_mangled(ident):
    out = report.redact("OPENROUTER_API_KEY=%s\nKeyError: 'plugins'" % ENV_VALUE, ident)
    assert "OPENROUTER_API_KEY=<redacted:env-secret>" in out
    assert "KeyError: 'plugins'" in out


@pytest.mark.parametrize("ip", [IP, "10.0.0.1", "2001:db8::1", "fe80::1ff:fe23:4567:890a",
                                "2001:0db8:0000:0000:0000:ff00:0042:8329"])
def test_ips_dropped(ip, ident):
    out = report.redact("connect to %s failed" % ip, ident)
    assert ip not in out and "<ip>" in out


def test_times_and_versions_not_mangled_as_ips(ident):
    s = "at 12:30:45 python 3.12.10 version 1.2.3"
    assert report.redact(s, ident) == s


def test_idempotent(ident):
    s = r"C:\Users\%s\x %s OPENROUTER_API_KEY=%s %s %s" % (USER, OR_KEY, ENV_VALUE, EMAIL, IP)
    once = report.redact(s, ident)
    assert report.redact(once, ident) == once


# ---- report + rendering --------------------------------------------------

def _planted_error():
    return "\n".join([
        r"failed at C:\Users\%s\x" % USER, "C:/Users/%s/x" % USER, "/c/Users/%s/x" % USER,
        "/home/%s/x" % USER, "/Users/%s/x" % USER, "user %s" % USER, "mail " + EMAIL,
        "aws " + AWS, "gh " + GHP, "or " + OR_KEY, "OPENROUTER_API_KEY=%s" % ENV_VALUE, "ip " + IP,
    ])


PLANTED = [USER, EMAIL, AWS, GHP, OR_KEY, ENV_VALUE, IP]


def test_rendered_markdown_and_url_contain_no_planted_values(ident):
    rep = report.build_report("install-failure", r"installing from C:\Users\%s" % USER, _planted_error(),
                              extra={"cwd": "/home/%s/kit" % USER, "note": "mail " + EMAIL})
    rendered = report.render_markdown(rep)
    url, _ = report.issue_url(rendered)
    for hay in (str(rendered), url, unquote(url), unquote(unquote(url)), str(rep)):
        for v in PLANTED:
            assert v not in hay, v
    assert "<redacted:aws-access-key>" in rendered


def test_render_markdown_redacts_even_a_raw_dict(ident):
    raw = {"kind": "agent-misbehaved", "step": "s " + EMAIL, "error": "k " + OR_KEY, "tool": {}, "extra": {}}
    out = report.render_markdown(raw)
    assert EMAIL not in out and OR_KEY not in out


def test_senders_refuse_unrendered_text(ident, tmp_path):
    with pytest.raises(TypeError):
        report.issue_url("raw " + OR_KEY)
    with pytest.raises(TypeError):
        report.save_report("raw " + OR_KEY, str(tmp_path / "x.md"))
    with pytest.raises(TypeError):
        report.submit_issue("raw " + OR_KEY, yes=True)


def test_error_is_tail_limited(ident):
    err = "\n".join("line %d" % i for i in range(1000))
    rep = report.build_report("install-failure", "s", err)
    assert "line 999" in rep["error"] and "line 100\n" not in rep["error"]
    assert "omitted" in rep["error"]


def test_bad_kind_rejected(ident):
    with pytest.raises(ValueError):
        report.build_report("nope", "s", "e")


def test_markdown_survives_backticks_in_error(ident):
    rep = report.build_report("install-failure", "s", "a ``` b")
    md = report.render_markdown(rep)
    assert "````text" in md


# ---- URL -----------------------------------------------------------------

def test_url_targets_matching_template(ident):
    for kind in report.KINDS:
        url, trunc = report.issue_url(report.render_markdown(report.build_report(kind, "demo step", "boom")))
        assert url.startswith("https://github.com/abyss-node/claude-starter/issues/new?template=%s.yml&" % kind)
        assert "title=" in url and not trunc


def test_url_length_cap(ident):
    big = "\n".join("E%05d %s" % (i, "x" * 60) for i in range(200))
    rendered = report.render_markdown(report.build_report("install-failure", "s", big))
    url, truncated = report.issue_url(rendered)
    assert truncated
    assert len(url) <= report.URL_CAP
    assert "E00199" in unquote(url)  # the tail of the log is what is kept
    assert "truncated" in unquote(url)


def test_url_cap_with_secrets_in_huge_input(ident):
    err = ("%s\n" % OR_KEY) * 3000
    url, _ = report.issue_url(report.render_markdown(report.build_report("install-failure", "s", err)))
    assert len(url) <= report.URL_CAP and OR_KEY not in unquote(url)


# ---- submit --------------------------------------------------------------

class FakeRun:
    def __init__(self, label_missing=False):
        self.calls = []
        self.label_missing = label_missing

    def __call__(self, cmd, *a, **k):
        self.calls.append(list(cmd))
        if cmd[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if cmd[:3] == ["gh", "issue", "create"]:
            if self.label_missing and "--label" in cmd:
                return subprocess.CompletedProcess(cmd, 1, b"", b"could not add label: 'x' not found")
            self.body = Path(cmd[cmd.index("--body-file") + 1]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, b"https://github.com/abyss-node/claude-starter/issues/1\n", b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def _rendered():
    return report.render_markdown(report.build_report("install-failure", "demo", "boom " + OR_KEY))


def test_non_tty_submit_without_yes_does_not_call_gh(ident, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(report.subprocess, "run", fake)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    msgs = []
    assert report.submit_issue(_rendered(), yes=False, out=msgs.append) is None
    assert not [c for c in fake.calls if c and c[0] == "gh"]
    assert any("--yes" in m for m in msgs)


def test_non_tty_cli_submit_sends_nothing_and_prints_url(ident, monkeypatch, tmp_path, capsys):
    fake = FakeRun()
    monkeypatch.setattr(report.subprocess, "run", fake)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    rc = report.main(["--kind", "install-failure", "--step", "s", "--error", OR_KEY, "--submit",
                      "--tool", "nothere", "--out", str(tmp_path / "r.md")])
    out = capsys.readouterr().out
    assert rc == 0 and "https://github.com/abyss-node/claude-starter/issues/new?template=" in out
    assert "Nothing has been sent" in out
    assert not [c for c in fake.calls if c and c[0] == "gh"]
    assert OR_KEY not in out and OR_KEY not in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_submit_with_yes_sends_redacted_body_with_label(ident, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(report.subprocess, "run", fake)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    url = report.submit_issue(_rendered(), yes=True, out=lambda m: None)
    assert url.endswith("/issues/1")
    create = [c for c in fake.calls if c[:3] == ["gh", "issue", "create"]][0]
    assert create[create.index("--repo") + 1] == "abyss-node/claude-starter"
    assert create[create.index("--label") + 1] == "install-failure"
    assert OR_KEY not in fake.body and "<redacted:" in fake.body


def test_submit_retries_without_missing_label(ident, monkeypatch):
    fake = FakeRun(label_missing=True)
    monkeypatch.setattr(report.subprocess, "run", fake)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert report.submit_issue(_rendered(), yes=True, out=lambda m: None).endswith("/issues/1")
    creates = [c for c in fake.calls if c[:3] == ["gh", "issue", "create"]]
    assert len(creates) == 2 and "--label" in creates[0] and "--label" not in creates[1]


def test_tty_decline_sends_nothing(ident, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(report.subprocess, "run", fake)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert report.submit_issue(_rendered(), yes=False, out=lambda m: None) is None
    assert not [c for c in fake.calls if c[:3] == ["gh", "issue", "create"]]


def test_gh_missing_falls_back(ident, monkeypatch):
    monkeypatch.setattr(report.shutil, "which", lambda n: None)
    assert report.submit_issue(_rendered(), yes=True, out=lambda m: None) is None


# ---- environment detection -----------------------------------------------

def test_missing_tool_binaries_do_not_crash(ident, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(report, "_identity", lambda: ident)
    monkeypatch.setattr(report.shutil, "which", lambda n: None)
    rep = report.build_report("install-failure", "s", "e")
    assert rep["detected_tools"] == {}
    rep = report.build_report("install-failure", "s", "e", tool="opencode")
    assert rep["tool"]["name"] == "opencode" and rep["tool"]["version"] is None
    assert "version not detected" in report.render_markdown(rep)


def test_version_probe_failures_do_not_crash(ident, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(report, "_identity", lambda: ident)
    monkeypatch.setattr(report.shutil, "which", lambda n: "/bin/" + n if n != "git" else None)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)
    monkeypatch.setattr(report.subprocess, "run", boom)
    rep = report.build_report("install-failure", "s", "e")
    assert set(rep["detected_tools"]) == set(report.KNOWN_TOOLS)
    assert all(v == "unknown" for v in rep["detected_tools"].values())


def test_kit_version_is_read(ident):
    assert report.build_report("install-failure", "s", "e")["kit_version"] not in ("", None)


def test_apostrophe_in_username_is_fully_redacted():
    import report as R
    out = R.redact(r"failed at C:\Users\O'Brien\proj and C:/Users/O'Brien/x")
    assert "Brien" not in out and "~'" not in out, out


# ---- private keys (PEM blocks) ---------------------------------------------

PEM_BODY = ["MIIEowIBAAKCAQEAq" + "Zm9vYmFyYmF6" * 4, "c2VjcmV0LWtleS1ib2R5" * 3, "QUJDREVGR0hJSktMTU5P" * 2]


def _pem(label: str, end: bool = True, sep: str = "\n") -> str:
    lines = ["-----BEGIN " + label + "-----", *PEM_BODY]
    if end:
        lines.append("-----END " + label + "-----")
    return sep.join(lines)


@pytest.mark.parametrize("label", ["RSA PRIVATE KEY", "PRIVATE KEY", "ENCRYPTED PRIVATE KEY",
                                   "OPENSSH PRIVATE KEY", "EC PRIVATE KEY"])
def test_pem_private_key_body_is_redacted(label, ident):
    out = report.redact("before\n" + _pem(label) + "\nafter", ident)
    for body in PEM_BODY:
        assert body not in out, label
    assert out.startswith("before\n") and out.endswith("\nafter")
    assert "<redacted:private-key>" in out


def test_pem_without_end_is_redacted_to_the_end(ident):
    out = report.redact("log line\n" + _pem("RSA PRIVATE KEY", end=False) + "\nmore secret tail", ident)
    for body in PEM_BODY:
        assert body not in out
    assert "secret tail" not in out and out.startswith("log line\n")


def test_pem_in_a_json_string_with_escaped_newlines(ident):
    out = report.redact('{"key": "' + _pem("PRIVATE KEY", sep="\n") + '\n", "next": 1}', ident)
    for body in PEM_BODY:
        assert body not in out


# ---- more token shapes and headers -----------------------------------------

STRIPE = "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc"
STRIPE_RK = "rk_" + "test_" + "51HxYzAbCdEfGhIjKlMn0pQr"
NPM = "npm_" + "aB3dE5gH7jK9mN1pQ3sT5vX7zA9cE1gI3kM5"
HF = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
AWS_SECRET = "wJalrXUtnFEMI" + "/K7MDENG/bPxRfiCYEXAMPLEKEY"  # 40 characters
BASIC = "dXNlcjpodW50ZXIy" + "aHVudGVy"
COOKIE_VAL = "s3ss10nvalue" + "abc123def"


@pytest.mark.parametrize("line,value", [
    ("stripe key " + STRIPE, STRIPE),
    ("restricted " + STRIPE_RK, STRIPE_RK),
    ("//registry.npmjs.org/:_authToken=" + NPM, NPM),
    ("npm token " + NPM, NPM),
    ("hf token " + HF, HF),
    ("id_token " + JWT, JWT),
    ("AWS Secret Access Key [None]: " + AWS_SECRET, AWS_SECRET),
    ("aws_secret_access_key = " + AWS_SECRET, AWS_SECRET),
    ('{"SecretAccessKey": "%s"}' % AWS_SECRET, AWS_SECRET),
    ("Authorization: Basic " + BASIC, BASIC),
    ("> authorization: Token " + BASIC, BASIC),
    ('curl -H "Authorization: Bearer %s" https://x' % BASIC, BASIC),
    ("Proxy-Authorization: Basic " + BASIC, BASIC),
    ("Cookie: session=%s; theme=dark" % COOKIE_VAL, COOKIE_VAL),
    ("< Set-Cookie: sid=%s; Path=/; HttpOnly" % COOKIE_VAL, COOKIE_VAL),
    ('"auth": "%s"' % BASIC, BASIC),
    ("  _auth=" + BASIC, BASIC),
    ("  token: " + BASIC, BASIC),
    ('"credentials": "%s"' % BASIC, BASIC),
    ("basicAuth: " + BASIC, BASIC),
])
def test_more_secret_shapes(line, value, ident):
    out = report.redact(line, ident)
    assert value not in out, out
    assert report.redact(out, ident) == out  # idempotent


def test_auth_scheme_survives_and_prose_is_not_mangled(ident):
    out = report.redact("Authorization: Basic " + BASIC, ident)
    assert out == "Authorization: Basic <redacted:authorization>"
    for s in ("author: Jane Roe", "authority: the docs", "authentication failed for the agent"):
        assert report.redact(s, ident) == s


# ---- hostnames and URL-encoded homes ----------------------------------------

def test_hostname_and_fqdn_go_entirely_before_the_username():
    i = report.Identity([r"C:\Users\jdoe"], ["jdoe"], ["jdoe-ThinkPad", "jdoe-ThinkPad.corp.example.net"])
    out = report.redact("on jdoe-ThinkPad.corp.example.net, JDOE-THINKPAD.lan and jdoe-thinkpad: user jdoe", i)
    low = out.lower()
    assert "thinkpad" not in low and "corp.example" not in low and ".lan" not in low, out
    assert "jdoe" not in low and "<host>" in out and "<user>" in out


def test_identity_collects_every_host_spelling(monkeypatch):
    monkeypatch.setattr(report.socket, "gethostname", lambda: "jdoe-ThinkPad")
    monkeypatch.setattr(report.socket, "getfqdn", lambda *a: "jdoe-ThinkPad.corp.example.net")
    monkeypatch.setenv("COMPUTERNAME", "JDOE-WS01")
    monkeypatch.setenv("HOSTNAME", "jdoe-box")
    hosts = {h.lower() for h in report._identity().hosts}
    assert {"jdoe-thinkpad", "jdoe-thinkpad.corp.example.net", "jdoe-ws01", "jdoe-box"} <= hosts


def test_public_hostnames_survive():
    i = report.Identity([r"C:\Users\jdoe"], ["jdoe"], ["jdoe-ThinkPad"])
    s = "fetch https://registry.npmjs.org/x and github.com/abyss-node failed"
    assert report.redact(s, i) == s


@pytest.mark.parametrize("encoded", [
    "C%3A%5CUsers%5C{u}%5Cproj%5Cx.py", "c%3a%5cusers%5c{u}%5cproj", "%2FUsers%2F{u}%2Fproj",
    "%2Fhome%2F{u}%2Fproj", "%2Fc%2FUsers%2F{u}%2Fproj", "C%3A%2FUsers%2F{u}%2Fproj",
])
@pytest.mark.parametrize("user", [USER, "someoneelse", "O%27Neil"])
def test_url_encoded_home_paths(encoded, user, ident):
    out = report.redact("GET /open?file=" + encoded.format(u=user) + "&x=1", ident)
    assert user.lower() not in out.lower(), out
    assert "proj" in out


# ---- Git Bash path misconversion ----------------------------------------------

@pytest.mark.parametrize("path,bad", [
    (r"C:\c\Users\x\claude-starter\scripts\report.py", True),
    ("C:/c/Users/x/claude-starter", True),
    (r"D:\d\home\x\kit", True),
    (r"C:\Users\x\claude-starter", False),
    ("/c/Users/x/claude-starter", False),
    (r"D:\code\claude-starter", False),
    ("/home/x/claude-starter", False),
])
def test_misconverted_path_detection(path, bad):
    assert report.misconverted_path(path) is bad


def test_report_warns_when_running_from_a_misconverted_path(ident, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(report, "KIT_ROOT", Path(r"C:\c\Users\x\claude-starter"))
    assert report.main(["--kind", "install-failure", "--step", "s", "--error", "e",
                        "--out", str(tmp_path / "r.md")]) == 0
    err = capsys.readouterr().err
    assert "Git Bash" in err and "re-clone" in err.lower()
    assert r'git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"' in err


# ---- the published tree carries no real home path ---------------------------

def test_no_local_home_or_distinctive_username_in_published_files():
    """Test fixtures once used the owner's real Windows username and home path. Fixtures must be
    fictional: check the files that get published for the home of whoever runs the suite."""
    root = Path(__file__).resolve().parents[2]
    home = Path.home()
    name = home.name
    needles = [re.compile(r"Users[\/]+" + re.escape(name) + r"(?![A-Za-z0-9])", re.I),
               re.compile(re.escape(str(home)), re.I), re.compile(re.escape(home.as_posix()), re.I)]
    if re.search(r"[^A-Za-z0-9._-]", name):  # a punctuated name like O'Neil is distinctive on its own
        needles.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(name), re.I))
    files = [p for d in ("scripts", "adapters", ".github") for p in (root / d).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts] + sorted(root.glob("*.md"))
    hits = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for rx in needles:
            for m in rx.finditer(text):
                hits.append("%s:%d" % (p.relative_to(root).as_posix(), text.count("\n", 0, m.start()) + 1))
    assert not hits, "local home path or username in: " + ", ".join(sorted(set(hits)))


# ---- redaction runs on the full text, before the tail limit cuts it ------------

KEY_LINE = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ"  # 50 base64 chars, PEM-body shaped


def _cut_pem_log():
    """262 lines; the key's BEGIN is line 31, so the last 200 lines start inside its body."""
    lines = ["log line %d" % i for i in range(1, 31)]
    lines.append("-----BEGIN " + "RSA PRIVATE KEY-----")
    lines += ["%s%04d" % (KEY_LINE, i) for i in range(70)]       # lines 32..101
    lines.append("-----END " + "RSA PRIVATE KEY-----")           # line 102
    lines += ["log line %d" % i for i in range(103, 263)]        # lines 103..262
    assert len(lines) == 262
    return "\n".join(lines)


def test_pem_cut_by_the_tail_limit_does_not_leak(ident):
    rep = report.build_report("install-failure", "s", _cut_pem_log())
    rendered = report.render_markdown(rep)
    url, _ = report.issue_url(rendered)
    for hay in (rep["error"], str(rendered), unquote(url)):
        assert KEY_LINE not in hay
        assert "END " + "RSA PRIVATE KEY" not in hay
    assert "log line 262" in rep["error"]


def test_token_split_by_the_line_cut_does_not_leak(ident):
    line = "x" * (report.MAX_LINE_CHARS - 20) + " " + GHP  # the cut keeps 19 of its 40 characters
    rep = report.build_report("install-failure", "s", line)
    assert GHP[:12] not in rep["error"], rep["error"][-80:]


def test_key_fragments_without_a_begin_line_are_redacted(ident):
    body = ["%s%04d" % (KEY_LINE, i) for i in range(3)]
    text = "\n".join(["[... 61 earlier lines omitted ...]", *body, "-----END " + "OPENSSH PRIVATE KEY-----",
                      "next step"])
    out = report.redact(text, ident)
    assert KEY_LINE not in out and "END " + "OPENSSH" not in out, out
    assert "<redacted:key-fragment>" in out and out.endswith("next step")


def test_two_long_base64_lines_are_not_a_key_fragment(ident):
    s = "\n".join(["%s%04d" % (KEY_LINE, i) for i in range(2)])
    assert report.redact(s, ident) == s


def test_a_column_of_commit_ids_is_not_a_key_fragment(ident):
    s = "\n".join(["0123456789abcdef0123456789abcdef0123%04d" % i for i in range(5)])
    assert report.redact(s, ident) == s


# ---- more redaction gaps ----------------------------------------------------------

@pytest.mark.parametrize("text", [
    "GET /open?file=D%3A%5Cwork%5C{u}%5Cnotes.txt&x=1",
    "q=%2Fsrv%2F{u}%2Fdata",
    "owner%3D{u}%26next",
])
def test_url_encoded_username_outside_home_paths(text, ident):
    out = report.redact(text.format(u=USER), ident)
    assert USER not in out.lower(), out


MARY = "Mary O'Neil"


@pytest.mark.parametrize("text", [
    r"failed at C:\Users\Mary O'Neil\proj\x.py",
    "failed at C:/Users/Mary O'Neil/proj/x.py",
    "failed at /c/Users/Mary O'Neil/proj/x.py",
    r"cwd is C:\Users\Mary O'Neil",
    "committed by Mary O'Neil today",
    "GET /x?file=D%3A%5Cwork%5CMary%20O%27Neil%5Cproj&x=1",
    "owner=Mary+O%27Neil&x=1",
])
def test_username_with_a_space_leaves_no_part_behind(text):
    i = report.Identity([r"C:\Users\Mary O'Neil"], [MARY], [])
    out = report.redact(text, i)
    assert "neil" not in out.lower(), out


def test_someone_elses_home_with_a_space_in_the_name(ident):
    out = report.redact(r"read C:\Users\Mary O'Neil\proj\x and /home/Mary O'Neil/y", ident)
    assert "neil" not in out.lower() and "proj" in out, out


def test_short_username_is_redacted_only_inside_paths():
    i = report.Identity([r"C:\Users\bob"], ["bob"], [])
    out = report.redact(r"bob said C:\Users\bob\proj failed; /home/bob/x; bobcat", i)
    assert out == r"bob said ~\proj failed; ~/x; bobcat", out


def test_common_word_username_keeps_word_boundaries():
    i = report.Identity([r"C:\Users\mary"], ["mary"], [])
    s = "summary of maryland, primary key"
    assert report.redact(s, i) == s


JWT_PADDED = ("eyJ" + "hbGciOiJIUzI1NiJ9" + "=." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "=."
              + "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk=")
WHSEC = "whsec_" + "MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"


@pytest.mark.parametrize("line,needle", [
    ("id_token " + JWT_PADDED, "zdWIiOiIxMjM0NTY3ODkwIn0"),
    ("id_token " + JWT_PADDED, "dBjftJeZ4CVP"),
    ("webhook secret " + WHSEC, WHSEC[6:]),
])
def test_padded_jwt_and_stripe_webhook_secret(line, needle, ident):
    out = report.redact(line, ident)
    assert needle not in out, out
    assert report.redact(out, ident) == out


def test_ssh2_private_key_block_is_redacted(ident):
    block = "\n".join(["---- BEGIN SSH2 ENCRYPTED " + "PRIVATE KEY ----", 'Comment: "rsa-key-fixture-77"',
                       "P2/56wAAAi4AAAA3aWYtbW9kbg", "c2VjcmV0LWtleS1ib2R5", "---- END SSH2 ENCRYPTED " + "PRIVATE KEY ----"])
    out = report.redact("before\n" + block + "\nafter", ident)
    assert "fixture-77" not in out and "P2/56wAAAi4" not in out and "c2VjcmV0" not in out, out
    assert out.startswith("before\n") and out.endswith("\nafter") and "<redacted:private-key>" in out


def test_putty_private_lines_are_redacted(ident):
    ppk = "\n".join(["PuTTY-User-Key-File-3: ssh-ed25519", "Encryption: none", "Comment: eddsa-key-fixture",
                     "Public-Lines: 2", "AAAAC3NzaC1lZDI1NTE5AAAAIPublicPartOne", "PublicPartTwo",
                     "Private-Lines: 2", "AAAAIGPrivBodyFixtureOne0123", "PrivBodyFixtureTwo4567",
                     "Private-MAC: 0123456789abcdef0123456789abcdef", "next step"])
    out = report.redact(ppk, ident)
    assert "PrivBodyFixture" not in out and "0123456789abcdef" not in out, out
    assert "Private-Lines: 2" in out and out.endswith("\nnext step")


# ---- a preflight failure probes no tool --------------------------------------------

def test_version_note_replaces_the_probe(ident, monkeypatch):
    called = []
    monkeypatch.setattr(report, "_run_version", lambda t: called.append(t) or "9.9.9")
    rep = report.build_report("install-failure", "preflight", "e", tool="opencode",
                              version_note="version not probed (preflight failure)")
    assert called == []
    assert rep["tool"]["version"] == "version not probed (preflight failure)"
    rep = report.build_report("install-failure", "preflight", "e",
                              version_note="version not probed (preflight failure)")
    assert called == [] and rep["detected_tools"] == {}


# ---- the console gets redacted text too ---------------------------------------------

def test_saved_line_on_the_console_is_redacted(ident, tmp_path, capsys):
    d = tmp_path / USER
    d.mkdir()
    assert report.main(["--kind", "install-failure", "--step", "s", "--error", "e",
                        "--out", str(d / "r.md")]) == 0
    out = capsys.readouterr().out
    saved = [ln for ln in out.splitlines() if ln.startswith("Saved: ")]
    assert saved and USER not in saved[0] and "r.md" in saved[0], saved

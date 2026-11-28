r"""Selftest of the DeepSeek Harness adapter (dsh-DIRECTOR-WORKER 3.0.0-ds.8).

  python -I -X utf8 adapters/deepseek/selftest_deepseek.py [--only NAME,NAME] [--verbose] [--keep]

Tests only what adapters/deepseek/ adds; the base tools are tested by the base tools/selftest.py (run it too).
Every test works in a temp folder and writes nothing in the repo. A gate tool must never pass without an exit code:
the dispatch and release tests run steps that time out, are killed, exit non-zero or print nothing, and check that
each one blocks. A test that cannot run here (no git) is a SKIP with its reason, never a PASS.
Last line `SELFTEST_DEEPSEEK: PASS|FAIL tests=n pass=n fail=n skip=n` (`SELFTEST_DEEPSEEK ONLY:` with --only);
exit 0 only when nothing failed. Standard library only, Python 3.9 or later.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
BASE_TOOLS = REPO / "tools"
PY = [sys.executable, "-I", "-X", "utf8"]
TIMEOUT = 240
TESTS = []
SHA = "a" * 64

ORDER = """# WO-001
```text
ISSUED_BY      = director 2026-01-02 10:00
PRIMARY_WORKER = session a
MODEL / EFFORT = deepseek-flash / medium
FALLBACK       = same session
GOVERNANCE     = Standard
BASE_REF       = main @ abc123
```
```text
SCOPE:
- src/**
FORBIDDEN:
- src/frozen/**
TESTS_LOCKED:
- NONE  # the fixture runs no locked test file
```
| ID | req | how | expected | actual | evidence | status |
|---|---|---|---|---|---|---|
| AC-1 | parser accepts empty input | run test_parser | exit 0 | | | |

- DELIVERABLES: commit on the branch
- STOP_RULES: stop after 2 rounds without progress
"""

BRIEF = """# 專案初衷卡
- 專案：櫃台名單
- 狀態：LOCKED
- 版次：1
- 使用者確認時間：2026-11-08 10:00 +08:00
- 使用者確認原話：「對，就是這樣，開始做」
- 一句話：給櫃台看今天名單的小網頁

| 編號 | 類別 | 內容（使用者的話） | 怎麼算做到 |
|---|---|---|---|
| B-1 | 給誰 | 給櫃台 | 打開就能看到表 |
| B-2 | 一定要有 | 依到場時間排序 | 第一列是最早到的人 |

## 限制
- 不花錢

## 未決事項
- 無

## 現成方案調查
- 找了 csvkit → 不用：只要一欄，標準函式庫就夠
"""

# a stand-in for one base tool: DSH_STUB_<STEP> picks what it does (ok, sleep, kill, exit3, quiet, two)
STUB = r'''import os, pathlib, sys, time
STEP = {step!r}
OK = {ok!r}


def is_order(text, path=None):
    return True


def find_brief(order, brief=None):
    return pathlib.Path(brief) if brief else pathlib.Path(order).with_name("BRIEF.md")


if __name__ == "__main__":
    mode = os.environ.get("DSH_STUB_" + STEP, "ok")
    if mode == "sleep":
        time.sleep(60)
    if mode == "kill":
        sys.stdout.flush()
        os.kill(os.getpid(), 9)
        time.sleep(60)
    if mode == "exit3":
        print(OK)
        sys.exit(3)
    if mode == "quiet":
        sys.exit(0)
    print(OK)
    if mode == "two":
        print(OK)
'''

# expected loop findings per fixture in fixtures/loops (the base loop_guard core counts a call in one category)
LOOP_CATEGORIES = ("repeat", "retry_same_error", "poll_no_progress", "ping_pong", "bad_args", "child_error_unhandled")
LOOP_EXPECTED = {
    "repeat_pos": {"repeat": 1}, "repeat_neg": {}, "repeat_long": {"repeat": 1},
    "retry_pos": {"retry_same_error": 1}, "retry_neg": {},
    "ping_pong_pos": {"ping_pong": 1}, "ping_pong_neg": {},
    "poll_pos": {"poll_no_progress": 1}, "poll_neg": {"repeat": 1},
    "bad_args_pos": {"bad_args": 1}, "bad_args_neg": {},
    "child_error_pos": {"child_error_unhandled": 1}, "child_error_neg": {},
    "secret_leak": {"retry_same_error": 1, "bad_args": 1},
}
LOOP_CHILD_RESULTS = ("poll_neg", "child_error_pos", "child_error_neg")


class Skip(Exception):
    """the test cannot run here; the message is the reason"""


def test(function):
    TESTS.append(function)
    return function


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def tail(text, size=600):
    text = (text or "").strip()
    return text if len(text) <= size else "..." + text[-size:]


def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def tool(name):
    """A DSH tool in this folder, else a base tool two folders up (the same lookup as the DSH tools)."""
    for folder in (HERE, BASE_TOOLS):
        if (folder / f"{name}.py").is_file():
            return folder / f"{name}.py"
    raise AssertionError(f"no tool {name}.py in {HERE} or {BASE_TOOLS}")


def run(script, *args, cwd=None, env=None, timeout=TIMEOUT):
    """(exit code, stdout + stderr) of a tool run as its own process."""
    path = script if isinstance(script, pathlib.Path) else tool(script)
    full = dict(os.environ)
    full.update(env or {})
    done = subprocess.run(PY + [str(path)] + [str(a) for a in args], cwd=cwd, env=full, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def expect(label, script, code, *args, says=(), lacks=(), cwd=None, env=None, timeout=TIMEOUT):
    got, out = run(script, *args, cwd=cwd, env=env, timeout=timeout)
    says = [says] if isinstance(says, str) else list(says)
    lacks = [lacks] if isinstance(lacks, str) else list(lacks)
    require(got == code, f"{label}: exit {got}, want {code}: {tail(out)}")
    for word in says:
        require(word in out, f"{label}: no {word!r} in: {tail(out)}")
    for word in lacks:
        require(word not in out, f"{label}: {word!r} should not be in: {tail(out)}")
    return out


def load(path, name, source=None):
    """A module loaded from path (or from source text with path as its file, for a mutant)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if source is None:
        spec.loader.exec_module(module)
    else:
        module.__file__ = str(path)
        exec(compile(source, str(path), "exec"), module.__dict__)
    return module


class QuietOut(io.StringIO):
    def reconfigure(self, **_):
        pass


def call_main(module, *argv):
    """(exit, output) of module.main(argv) in this process."""
    out = QuietOut()
    with contextlib.redirect_stdout(out):
        try:
            code = module.main([str(a) for a in argv])
        except SystemExit as error:
            code = error.code
    return code, out.getvalue()


def need_git():
    if shutil.which("git") is None:
        raise Skip("git is not on PATH")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    require(done.returncode == 0, f"git {' '.join(args)}: {done.stdout.decode('utf-8', 'replace')}")
    return done.stdout.decode("utf-8", "replace")


def git_repo(folder):
    need_git()
    folder.mkdir(parents=True, exist_ok=True)
    git(folder, "init", "-q")
    return folder


def director(folder, approve=True, order=ORDER):
    """folder/DIRECTOR with orders/WO-001.md and BRIEF.md, approved by the base spec_gate unless approve=False."""
    d = pathlib.Path(folder) / "DIRECTOR"
    write(d / "orders" / "WO-001.md", order)
    brief = write(d / "BRIEF.md", BRIEF)
    if approve:
        code, out = run("spec_gate", "approve", "--brief", brief)
        require(code == 0, f"spec_gate approve of the fixture brief: exit {code}: {tail(out)}")
    return d


def stub_tools(folder):
    """folder/ with stand-ins for spec_gate.py, gate_check.py and worktree.py."""
    lines = {"spec_gate": "SPEC_GATE: PASS",
             "gate_check": f"  DISPATCH WO-001 rev=1 sha={SHA}",
             "worktree": "WORKER_WORKTREE: " + str(pathlib.Path(folder).parent / "wt" / "WO-001") + " branch=wt/WO-001"}
    for step, ok in lines.items():
        write(pathlib.Path(folder) / f"{step}.py", STUB.format(step=step.upper(), ok=ok))
    return pathlib.Path(folder)


class FakeDone:
    def __init__(self, code):
        self.returncode = code
        self.stdout = b"out"


@contextlib.contextmanager
def fake_subprocess_run(code):
    real = subprocess.run
    subprocess.run = lambda *a, **k: FakeDone(code)
    try:
        yield
    finally:
        subprocess.run = real


# ---------------------------------------------------------------------------------------------------------- tests

@test
def compile_and_help(tmp):
    """Every adapter .py compiles; every adapter CLI answers --help with exit 0."""
    for path in sorted(HERE.glob("*.py")):
        py_compile.compile(str(path), cfile=str(tmp / "pyc" / (path.name + "c")), doraise=True)
    clis = ("base_sync_check", "ds_version", "dsh_audit", "dsh_dispatch", "dsh_doctor", "dsh_guard",
            "dsh_setup_check", "dsh_usage", "install_deepseek", "release_ds", "verify_dsh_run")
    for name in clis:
        expect(f"{name} --help", HERE / f"{name}.py", 0, "--help", says="usage:")
    return f"{len(list(HERE.glob('*.py')))} files compile, {len(clis)} --help"


@test
def session_moved(tmp):
    """dsh_session.py is a library: the four 3.0.0-ds.8 moved options print MOVED with the base worktree.py command,
    do nothing and exit 2; no option prints what it is."""
    moved = {"--temp-env": "tools/worktree.py temp WORK_DIR", "--worker-worktree": "tools/worktree.py open REPO",
             "--cwd-check": "tools/worktree.py cwd", "--worktree-status": "tools/worktree.py status"}
    for option, says in moved.items():
        expect(f"dsh_session {option}", "dsh_session", 2, option, tmp / "x",
               says=["MOVED: " + option, says, "nothing was done"])
    require(not (tmp / "x").exists(), "a moved option wrote something")
    expect("dsh_session with no option", "dsh_session", 0, says="library")
    return "4 options MOVED, exit 2, nothing written"


@test
def dispatch_blocks(tmp):
    """dsh_dispatch.py (R6) with the real base tools: no GO for a file that is not a work order, a missing order, a
    brief the spec gate refuses, or a tools folder without the base tools; GO with the DISPATCH line on an approved
    brief. Every BLOCKED is exit 1."""
    d = director(tmp / "ok")
    order = d / "orders" / "WO-001.md"
    note = write(tmp / "notes" / "notes.md", "# notes\nnot an order\n")
    expect("not a work order", "dsh_dispatch", 1, note, says="DSH_DISPATCH: BLOCKED step=order reason=not_a_work_order",
           lacks="DSH_DISPATCH: GO")
    expect("order missing", "dsh_dispatch", 1, d / "orders" / "WO-404.md", says="BLOCKED step=order reason=order_not_found")
    empty = (tmp / "empty_tools")
    empty.mkdir()
    expect("no base tools", "dsh_dispatch", 1, order, "--tools-dir", empty, says="BLOCKED step=order reason=tool_missing")
    raw = director(tmp / "draft", approve=False)
    expect("spec gate not approved", "dsh_dispatch", 1, raw / "orders" / "WO-001.md",
           says=["STEP spec_gate: FAIL", "DSH_DISPATCH: BLOCKED step=spec_gate"], lacks="STEP hash")
    write(raw / "BRIEF.md", BRIEF.replace("- 狀態：LOCKED", "- 狀態：DRAFT"))
    expect("draft brief", "dsh_dispatch", 1, raw / "orders" / "WO-001.md", says="BLOCKED step=spec_gate")
    out = expect("approved brief", "dsh_dispatch", 0, order,
                 says=["STEP spec_gate: PASS exit=0", "STEP hash: PASS exit=0 dispatch_lines=1",
                       "DSH_DISPATCH: GO order=WO-001 rev=1 sha=", "worktree=none", "LOG: DISPATCH WO-001 rev=1 sha=",
                       "NEXT: subagent"], lacks="BLOCKED")
    write(d / "BRIEF.md", BRIEF.replace("依到場時間排序", "依姓名排序"))
    expect("brief changed after approve", "dsh_dispatch", 1, order, says="BLOCKED step=spec_gate")
    return "order / missing / no tools / not approved / draft / changed blocked; approved GO (" + \
        out.split("sha=")[1][:12] + ")"


@test
def dispatch_no_exit_code(tmp):
    """dsh_dispatch.py with stand-in base tools (--tools-dir): a step that times out, is killed, exits 3, exits 0
    without its line or prints two DISPATCH lines blocks at that step; only all three OK steps give GO. In process:
    run() turns a missing, negative or bool return code into None, and status() never calls None PASS."""
    stubs = stub_tools(tmp / "tools")
    order = write(tmp / "DIRECTOR" / "orders" / "WO-001.md", ORDER)
    write(tmp / "DIRECTOR" / "BRIEF.md", BRIEF)
    repo = tmp / "repo"
    repo.mkdir()
    base = ["--tools-dir", stubs, "--repo", repo]
    out = expect("stubs all ok", "dsh_dispatch", 0, order, *base, says=["DSH_DISPATCH: GO order=WO-001 rev=1",
                                                                        "worktree=" + str(tmp / "wt" / "WO-001")])
    cases = [
        ("SPEC_GATE", "sleep", "spec_gate", "INVALID exit=None"), ("SPEC_GATE", "exit3", "spec_gate", "FAIL exit=3"),
        ("SPEC_GATE", "kill", "spec_gate", ""),
        ("GATE_CHECK", "sleep", "hash", "INVALID exit=None"), ("GATE_CHECK", "exit3", "hash", "FAIL exit=3"),
        ("GATE_CHECK", "quiet", "hash", "dispatch_lines=0"), ("GATE_CHECK", "two", "hash", "dispatch_lines=2"),
        ("GATE_CHECK", "kill", "hash", ""),
        ("WORKTREE", "sleep", "worktree", "INVALID exit=None"), ("WORKTREE", "exit3", "worktree", "FAIL exit=3"),
        ("WORKTREE", "quiet", "worktree", "no WORKER_WORKTREE line"), ("WORKTREE", "kill", "worktree", ""),
    ]
    for step, mode, where, why in cases:
        says = [f"DSH_DISPATCH: BLOCKED step={where}"] + ([why] if why else [])
        if mode == "kill" and os.name != "nt":
            says.append("INVALID exit=None")
        expect(f"{step} {mode}", "dsh_dispatch", 1, order, *base, "--timeout", 3, env={f"DSH_STUB_{step}": mode},
               says=says, lacks="DSH_DISPATCH: GO")
    module = load(HERE / "dsh_dispatch.py", "selftest_dsh_dispatch")
    for code in (None, -9, True):
        with fake_subprocess_run(code):
            got = module.run(["x"], 5)
        require(got[0] is None, f"dsh_dispatch.run with return code {code!r} gave {got[0]!r}, not None")
    require(module.status(None) == "INVALID" and module.status(True) == "INVALID" and module.status(1) == "FAIL"
            and module.status(0) == "PASS", "dsh_dispatch.status is not PASS-only-for-0")
    return f"{len(cases)} broken steps blocked; run() None for None/-9/True; GO only with 3 OK steps"


@test
def dispatch_worktree(tmp):
    """dsh_dispatch.py --repo with the real base worktree.py: GO names a new worktree on branch wt/wo-001; opening
    it a second time blocks."""
    repo = git_repo(tmp / "proj")
    write(repo / "README.md", "proj\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "init")
    d = director(tmp / "dir")
    out = expect("dispatch --repo", "dsh_dispatch", 0, d / "orders" / "WO-001.md", "--repo", repo,
                 "--root", tmp / "wt", says=["STEP worktree: PASS exit=0", "DSH_DISPATCH: GO order=WO-001"])
    where = out.split("worktree=")[-1].split()[0] if "worktree=" in out else ""
    require(where and where != "none" and pathlib.Path(where).is_dir(), f"no worktree folder {where!r}: {tail(out)}")
    require("wt/wo-001" in git(repo, "branch", "--list").lower(), "no branch wt/wo-001")
    expect("dispatch --repo again (the worktree exists)", "dsh_dispatch", 1, d / "orders" / "WO-001.md", "--repo",
           repo, "--root", tmp / "wt", says="BLOCKED step=worktree")
    return "worktree made; a second open blocks"


def director_fixture(folder):
    write(folder / "INDEX.md", "# INDEX\n\n先讀 RESUME_STATE.md，再讀 DIRECTOR_STATE.md。\n")
    write(folder / "DIRECTOR_STATE.md",
          "# DIRECTOR_STATE\n\nUPDATED: 2026-11-28\nPENDING_METHOD: ask_user_question; open questions are kept in "
          "DIRECTOR/PO_PENDING.md\n\n## SECTIONS\n")
    write(folder / "ACTIVE_WORKSTREAMS.md", "# ACTIVE_WORKSTREAMS\n\n| ID | STATE |\n|---|---|\n| W1 | running |\n")
    write(folder / "DECISION_REGISTER.md", "# DECISION_REGISTER\n\n| ID | DECISION |\n|---|---|\n| D1 | test |\n")
    write(folder / "DIRECTOR_OPERATING_RULES.md", "# DIRECTOR_OPERATING_RULES\n\n1. Keep the folder authoritative.\n")
    write(folder / "PO_PENDING.md",
          "## 未關閉\n\nID: OD-001\nSTATUS: open\nQUESTION: Which database?\nOPTIONS: a) sqlite b) none\n"
          "RECOMMENDED: a\nSOURCE: BOOTSTRAP\nANSWER:\n\n## 已關閉\n\nID: ACT-002\nSTATUS: answered\n"
          "QUESTION: Old question?\nOPTIONS: a) yes b) no\nRECOMMENDED: a\nSOURCE: DIRECTOR\nANSWER: yes\n")
    write(folder / "RESUME_STATE.md",
          "PROGRESS: setup checked\nDOING: nothing\nNEXT_STEP: wait for the PO\nCOMMS: NONE\n\n# RESUME_STATE\n"
          "UPDATED: 2026-11-28 10:00 +08:00\n")
    write(folder / "director_work.json", json.dumps({"schema_version": 1}, indent=1) + "\n")
    return folder


@test
def setup_check(tmp):
    """dsh_setup_check.py: a full DIRECTOR passes; a missing folder, an empty one, garbage files, no INDEX.md (R5),
    two PENDING_METHOD lines or a RESUME_STATE without its four lines fail (never exit 0)."""
    good = director_fixture(tmp / "good" / "DIRECTOR")
    expect("fixture", "dsh_setup_check", 0, good, says="DSH_SETUP_CHECK: PASS dirs=1 problems=0")
    code, out = run("dsh_setup_check", tmp / "missing" / "DIRECTOR")
    require(code != 0 and "DSH_SETUP_CHECK: PASS" not in out, f"missing folder exit {code}: {tail(out)}")
    (tmp / "empty" / "DIRECTOR").mkdir(parents=True)
    expect("empty folder", "dsh_setup_check", 1, tmp / "empty" / "DIRECTOR", says="DSH_SETUP_CHECK: FAIL")
    junk = director_fixture(tmp / "junk" / "DIRECTOR")
    for path in junk.iterdir():
        path.write_bytes(b"\x00\xff garbage \x80\n")
    expect("garbage files", "dsh_setup_check", 1, junk, says="DSH_SETUP_CHECK: FAIL")
    no_index = director_fixture(tmp / "noindex" / "DIRECTOR")
    (no_index / "INDEX.md").unlink()
    expect("no INDEX.md", "dsh_setup_check", 1, no_index, says=["INDEX.md", "DSH_SETUP_CHECK: FAIL"])
    two = director_fixture(tmp / "two" / "DIRECTOR")
    write(two / "DIRECTOR_STATE.md", (two / "DIRECTOR_STATE.md").read_text(encoding="utf-8")
          + "PENDING_METHOD: a web page\n")
    expect("two PENDING_METHOD lines", "dsh_setup_check", 1, two, says=["PENDING_METHOD", "DSH_SETUP_CHECK: FAIL"])
    resume = director_fixture(tmp / "resume" / "DIRECTOR")
    write(resume / "RESUME_STATE.md", "# RESUME_STATE\nnothing here\n")
    expect("RESUME_STATE without its four lines", "dsh_setup_check", 1, resume, says=["RESUME_STATE", "FAIL"])
    expect("--json", "dsh_setup_check", 0, "--json", good, says='"problems"')
    return "pass + missing / empty / garbage / no INDEX / two PENDING_METHOD / RESUME failed"


def version_repo(folder, version, headings, tags=()):
    repo = git_repo(folder)
    write(repo / "VERSION", version + "\n")
    write(repo / "BASE_VERSION", "3.0.0\n")
    write(repo / "CHANGELOG.md", "# CHANGELOG\n\n" + "".join(f"## {h} — 2026-11-28\n\nx\n\n" for h in headings))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "v")
    for name in tags:
        git(repo, "tag", name)
    return repo


@test
def ds_version_serial(tmp):
    """ds_version.py: the serial continues (PO 2026-11-28): 3.0.0-ds.8 after 2.6.0-ds.7 passes, 3.0.0-ds.1 fails, a
    serial not above a tag fails, a VERSION not on BASE_VERSION fails, a missing file is INVALID (exit 2); `next`
    prints the next serial. This repo's own VERSION passes."""
    ok = version_repo(tmp / "ok", "3.0.0-ds.8", ["3.0.0-ds.8", "2.6.0-ds.7", "2.5.0-ds.6"], tags=["v2.6.0-ds.7"])
    expect("ds.8 after ds.7", "ds_version", 0, "check", "--repo", ok, says="DS_VERSION: PASS")
    expect("ds.8 after ds.7 at HEAD", "ds_version", 0, "check", "--repo", ok, "--head", says="DS_VERSION: PASS")
    expect("next", "ds_version", 0, "next", "--repo", ok, says="3.0.0-ds.9")
    reset = version_repo(tmp / "reset", "3.0.0-ds.1", ["3.0.0-ds.1", "2.6.0-ds.7"])
    expect("ds.1 after ds.7", "ds_version", 1, "check", "--repo", reset, says="DS_VERSION: FAIL")
    tagged = version_repo(tmp / "tagged", "3.0.0-ds.8", ["3.0.0-ds.8", "2.6.0-ds.7"], tags=["v3.0.0-ds.9"])
    expect("a tag above", "ds_version", 1, "check", "--repo", tagged, says="DS_VERSION: FAIL")
    other = version_repo(tmp / "other", "2.9.0-ds.8", ["2.9.0-ds.8", "2.6.0-ds.7"])
    expect("VERSION not on BASE_VERSION", "ds_version", 1, "check", "--repo", other, says="DS_VERSION: FAIL")
    head = version_repo(tmp / "head", "3.0.0-ds.8", ["3.0.0-ds.8", "2.6.0-ds.7"])
    write(head / "CHANGELOG.md", "# CHANGELOG\n\n## 2.6.0-ds.7 — x\n")
    expect("heading not the version", "ds_version", 1, "check", "--repo", head, says="DS_VERSION: FAIL")
    (ok / "BASE_VERSION").unlink()
    expect("no BASE_VERSION", "ds_version", 2, "check", "--repo", ok, says="DS_VERSION: INVALID")
    expect("this repo", "ds_version", 0, "check", "--repo", REPO, says=["version=3.0.0-ds.8", "DS_VERSION: PASS"])
    return "ds.8 PASS; ds.1 / tag above / base mismatch / heading FAIL; missing file INVALID"


RELEASE_STUB = r'''import os, sys, time, pathlib
mode = os.environ.get("RELEASE_STUB_" + {name!r}, "ok")
pathlib.Path(os.environ["RELEASE_MARKS"], {name!r}).write_text(" ".join(sys.argv[1:]), encoding="utf-8")
if mode == "sleep":
    time.sleep(60)
if mode == "kill":
    os.kill(os.getpid(), 9)
    time.sleep(60)
sys.exit(0 if mode == "ok" else 4)
'''


@test
def release_stops(tmp):
    """release_ds.py runs ds_version, base_sync, selftest_ds in order, each as its own process; one that fails, times
    out or is killed stops the release and base tools/release.py never runs. In process: a missing, negative or bool
    return code is None (no result)."""
    root = tmp / "rel"
    adapter = root / "adapters" / "deepseek"
    adapter.mkdir(parents=True)
    shutil.copy2(HERE / "release_ds.py", adapter / "release_ds.py")
    for name in ("ds_version", "base_sync_check", "selftest_deepseek"):
        write(adapter / f"{name}.py", RELEASE_STUB.format(name=name))
    write(root / "tools" / "release.py", RELEASE_STUB.format(name="release"))
    script = adapter / "release_ds.py"
    for stop, mode, step in (("ds_version", "fail", "ds_version"), ("base_sync_check", "fail", "base_sync"),
                             ("selftest_deepseek", "fail", "selftest_ds"), ("ds_version", "sleep", "ds_version"),
                             ("base_sync_check", "kill", "base_sync")):
        marks = tmp / f"marks_{stop}_{mode}"
        marks.mkdir()
        expect(f"{stop} {mode}", script, 1, "--base", tmp / "base", "--timeout", 3,
               env={"RELEASE_MARKS": str(marks), f"RELEASE_STUB_{stop}": mode},
               says=f"RELEASE_DS: FAIL step={step}", lacks="step=release")
        require(not (marks / "release").exists(), f"release.py ran after {stop} {mode}")
    marks = tmp / "marks_ok"
    marks.mkdir()
    expect("all ok", script, 0, "--base", tmp / "base", "--dry-run-flag", env={"RELEASE_MARKS": str(marks)},
           says=["STEP ds_version: OK exit=0", "STEP base_sync: OK exit=0", "STEP selftest_ds: OK exit=0",
                 "RELEASE_DS: PASS step=release exit=0"])
    require("--dry-run-flag" in (marks / "release").read_text(encoding="utf-8"), "release.py did not get the options")
    marks = tmp / "marks_release_fail"
    marks.mkdir()
    expect("release.py fails", script, 4, "--base", tmp / "base", env={"RELEASE_MARKS": str(marks),
                                                                      "RELEASE_STUB_release": "fail"},
           says="RELEASE_DS: FAIL step=release exit=4")
    module = load(HERE / "release_ds.py", "selftest_release_ds")
    for code in (None, -9, True):
        with fake_subprocess_run(code):
            got = module.run(["x"], 5)
        require(got is None, f"release_ds.run with return code {code!r} gave {got!r}, not None")
    return "5 stops before release.py; all ok PASS; release.py exit passed on; run() None for None/-9/True"


@test
def light_default(tmp):
    """dsh default strength light (adapters/deepseek/VARIANT.json default_strength, read by the base safety_gate,
    3.0.0 B15): no config or no strength key is light; a project's strength is kept (standard, strict); a bad
    strength is not light."""
    expect("no config", "safety_gate", 0, "--show", says=["SAFETY strength=light tests_first=false plan_gate=false",
                                                          "default strength light from adapters/deepseek/VARIANT.json"])
    variant = json.loads((HERE / "VARIANT.json").read_text(encoding="utf-8"))
    require(variant.get("default_strength") == "light", f"VARIANT.json default_strength {variant.get('default_strength')!r}")
    plain = write(tmp / "plain.json", json.dumps({"schema_version": 1}))
    expect("no strength key", "safety_gate", 0, "--show", "--config", plain, says="strength=light")
    std = write(tmp / "std.json", json.dumps({"schema_version": 1, "strength": "standard"}))
    expect("standard", "safety_gate", 0, "--show", "--config", std, says="strength=standard tests_first=true")
    strict = write(tmp / "strict.json", json.dumps({"schema_version": 1, "strength": "strict"}))
    expect("strict", "safety_gate", 0, "--show", "--config", strict, says=["strength=strict", "plan_gate=true"])
    bad = write(tmp / "bad.json", json.dumps({"schema_version": 1, "strength": "none"}))
    code, out = run("safety_gate", "--show", "--config", bad)
    require(code != 0 or "strength=light" not in out, f"a bad strength showed light: exit {code}: {tail(out)}")
    module = load(BASE_TOOLS / "safety_gate.py", "selftest_safety_gate")
    require(module.DEFAULT_STRENGTH == "light", f"DEFAULT_STRENGTH is {module.DEFAULT_STRENGTH!r}")
    return "light by default, standard / strict kept, bad strength not light"


@test
def effort_table(tmp):
    """DSH_EFFORT_TABLE.json (the ds.7 DSH effort table, as a base dispatch_check --table file): the base loader takes
    it, it names only DSH levels (off / low / high / max; off is a base level since 3.0.0 B18, no medium / xhigh),
    mechanical allows off, and a DSH record passes while a Claude-only level warns."""
    module = load(BASE_TOOLS / "dispatch_check.py", "selftest_dispatch_check")
    table = module.load_table(str(HERE / "DSH_EFFORT_TABLE.json"))
    # not adapters/*/EFFORT_TABLE*.json: base 3.0.0 B11 would make it the default table, and the base
    # test_dispatch_effort_250 (written for the base table) then fails in this checkout (reported to the director)
    require(module.adapter_table(HERE.parent.parent) is None, "an adapters/*/EFFORT_TABLE*.json is back")
    levels = {x for row in table.values() for x in row}
    dsh = {"off", "low", "high", "max"}
    require(levels <= dsh, f"non-DSH levels in the table: {sorted(levels - dsh)}")
    require(table.get("repeated_failure") == ["max"] and table.get("mechanical") == ["off", "low"], f"table rows: {table}")
    ok = module.effort_warnings([(1, "WO-1", {"class": "dev", "effort": "high"}),
                                 (3, "WO-3", {"class": "mechanical", "effort": "off"})], table)
    bad = module.effort_warnings([(2, "WO-2", {"class": "root_cause", "effort": "xhigh"})], table)
    require(ok == [] and len(bad) == 1, f"dev/high or mechanical/off warned {ok} or root_cause/xhigh did not warn {bad}")
    return f"{len(table)} classes, levels {' / '.join(sorted(levels))}"


def sync_pair(tmp):
    base, variant = tmp / "base", tmp / "variant"
    for root in (base, variant):
        for name in ("install.py", "_common.py"):
            (root / "tools").mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE_TOOLS / name, root / "tools" / name)
        write(root / "README.md", "see `VERSION`\n")
        write(root / "docs" / "a.md", "a\n")
    write(base / "VERSION", "9.9.0\n")
    write(base / "CHANGELOG.md", "# base\n")
    write(variant / "VERSION", "9.9.0-ds.3\n")
    write(variant / "BASE_VERSION", "9.9.0\n")
    write(variant / "CHANGELOG.md", "# variant\n")
    write(variant / "CHANGELOG-upstream.md", "# base\n")
    write(variant / "adapters" / "deepseek" / "x.py", "x = 1\n")
    import hashlib
    registry = {"schema": "dw-base-sync/1", "adapter": "adapters/deepseek/",
                "overrides": {"VERSION": {"why": "variant version", "base_sha256": hashlib.sha256(b"9.9.0\n").hexdigest()},
                              "CHANGELOG.md": {"why": "variant history",
                                               "base_sha256": hashlib.sha256(b"# base\n").hexdigest()}},
                "not_ported": {}, "variant_files": {"BASE_VERSION": "base version", "CHANGELOG-upstream.md": "copy"},
                "variant_rules": {}}
    write(variant / "README.md", "see `VERSION` and `CHANGELOG.md`\n")
    write(base / "README.md", "see `VERSION` and `CHANGELOG.md`\n")
    reg = write(tmp / "BASE_SYNC.json", json.dumps(registry))
    return base, variant, reg, registry


@test
def base_sync_synthetic(tmp):
    """base_sync_check.py on a made-up base and variant: the clean pair passes; an edited base file, a file outside
    the adapter, a stale override hash, a wrong BASE_VERSION, an upstream CHANGELOG that is not a copy and an
    override the README does not name each fail; no VERSION cannot run (exit 2). CRLF counts as LF."""
    base, variant, reg, registry = sync_pair(tmp / "ok")
    expect("clean pair", "base_sync_check", 0, "--base", base, "--variant", variant, "--registry", reg,
           says="BASE_SYNC: PASS base=9.9.0 variant=9.9.0-ds.3 same=")
    (variant / "docs" / "a.md").write_bytes(b"a\r\n")
    expect("CRLF is LF", "base_sync_check", 0, "--base", base, "--variant", variant, "--registry", reg)
    breaks = [
        ("edited base file", lambda b, v, r: write(v / "docs" / "a.md", "b\n"), "CHANGED"),
        ("file outside the adapter", lambda b, v, r: write(v / "extra.md", "x\n"), "EXTRA"),
        ("missing base file", lambda b, v, r: (v / "docs" / "a.md").unlink(), "MISSING"),
        ("stale override", lambda b, v, r: write(b / "VERSION", "9.9.0\n\n"), "OVERRIDE_STALE"),
        ("wrong BASE_VERSION", lambda b, v, r: write(v / "BASE_VERSION", "9.8.0\n"), "VERSION"),
        ("upstream not a copy", lambda b, v, r: write(v / "CHANGELOG-upstream.md", "# other\n"), "UPSTREAM"),
        ("README does not name it", lambda b, v, r: write(v / "README.md", "nothing\n"), "README"),
        ("reset serial is still a version", lambda b, v, r: write(v / "VERSION", "9.9.0-ds\n"), "VERSION"),
    ]
    for label, change, word in breaks:
        b, v, r, _ = sync_pair(tmp / label.replace(" ", "_"))
        change(b, v, r)
        expect(label, "base_sync_check", 1, "--base", b, "--variant", v, "--registry", r,
               says=[word, "BASE_SYNC: FAIL"])
    b, v, r, _ = sync_pair(tmp / "noversion")
    (b / "VERSION").unlink()
    expect("no base VERSION", "base_sync_check", 2, "--base", b, "--variant", v, "--registry", r,
           says="BASE_SYNC: FAIL (cannot run)")
    return f"clean PASS, CRLF PASS, {len(breaks)} breaks FAIL, no VERSION exit 2"


@test
def install_adapter(tmp):
    """install_deepseek.py: check before install is NOT_INSTALLED (exit 2); install is a dry run without --execute;
    --execute (after the base tools/install.py) gives DONE and check PASS; an edited installed file fails check and
    a new install puts it back with a verified backup; a check without the base tools fails. The installed
    DIRECTOR/tools/safety_gate.py is standard with the base tools only and light once the adapter (its VARIANT.json)
    is installed, also beside a backup folder (base review P2-1)."""
    d = tmp / "proj" / "DIRECTOR"
    d.mkdir(parents=True)
    expect("check before install", "install_deepseek", 2, "check", "--to", d, says="INSTALL_DEEPSEEK_CHECK: NOT_INSTALLED")
    expect("dry run", "install_deepseek", 0, "install", "--to", d, says=["ADD ", "INSTALL_DEEPSEEK: DRY_RUN"])
    require(not (d / "adapters").exists(), "the dry run wrote adapters/")
    expect("base tools", "install", 0, "install", "--to", d / "tools", "--execute")
    gate = d / "tools" / "safety_gate.py"  # base review P2-1: the installed gate reads DIRECTOR/adapters/*/VARIANT.json
    expect("base tools only: standard", gate, 0, "--show", cwd=tmp, says="SAFETY strength=standard")
    expect("install", "install_deepseek", 0, "install", "--to", d, "--execute",
           says="INSTALL_DEEPSEEK: DONE version=3.0.0-ds.8")
    expect("check", "install_deepseek", 0, "check", "--to", d, says="INSTALL_DEEPSEEK_CHECK: PASS")
    require((d / "adapters" / "deepseek" / "VARIANT.json").is_file(), "no DIRECTOR/adapters/deepseek/VARIANT.json")
    expect("installed: light", gate, 0, "--show", cwd=tmp,
           says=["SAFETY strength=light", "default strength light from adapters/deepseek/VARIANT.json"])
    expect("installed dispatch runs", d / "adapters" / "deepseek" / "dsh_dispatch.py", 1,
           write(tmp / "notes.md", "# notes\n"), says="BLOCKED step=order reason=not_a_work_order")
    expect("install again", "install_deepseek", 0, "install", "--to", d, "--execute", says="nothing to change")
    target = d / "adapters" / "deepseek" / "dsh_dispatch.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    expect("edited file", "install_deepseek", 1, "check", "--to", d, says="INSTALL_DEEPSEEK_CHECK: FAIL")
    expect("reinstall", "install_deepseek", 0, "install", "--to", d, "--execute", says=["BACKUP: ", "verified",
                                                                                      "INSTALL_DEEPSEEK: DONE"])
    expect("check after reinstall", "install_deepseek", 0, "check", "--to", d, says="INSTALL_DEEPSEEK_CHECK: PASS")
    require("# edited" not in target.read_text(encoding="utf-8"), "the reinstall kept the edited file")
    expect("light beside a backup", gate, 0, "--show", cwd=tmp, says="SAFETY strength=light", lacks="disagree")
    shutil.rmtree(d / "tools")
    expect("no base tools", "install_deepseek", 1, "check", "--to", d, says="INSTALL_DEEPSEEK_CHECK: FAIL")
    return "NOT_INSTALLED / DRY_RUN / DONE / PASS / edited FAIL / backup / no base tools FAIL"


@test
def usage_numbers(tmp):
    """dsh_usage.py: no sessions is NO_DATA (exit 2, never a zero count); a projection cache gives the prompt-side
    tokens only (A1); a bad number in the cache is PARTIAL with a warning, not a number (D7)."""
    expect("no data", "dsh_usage", 2, "--sessions-root", tmp / "none_s", "--cache-root", tmp / "none_c",
           says="NO_DATA")
    cache, sessions = tmp / "cache", tmp / "sessions"
    sessions.mkdir()
    write(cache / "session-11111111-1111-4111-8111-111111111111.json", json.dumps({"version": 7, "record": {
        "identity": {"formatVersion": 7, "createdAt": 1700000000000, "cwd": "/home/dw/proj"},
        "rows": {"tokenUsage": {"val": {
            "totals": {"uncachedInputTokens": 100, "outputTokens": 50, "cacheReadTokens": 20, "cacheWriteTokens": 10},
            "last": {"turn": 1, "step": 1, "buckets": {"uncachedInputTokens": 500, "outputTokens": 200,
                                                         "cacheReadTokens": 1000, "cacheWriteTokens": 50}}}},
                 "sessionStats": {"val": {"turns": 1, "steps": 1}}}}}))
    data = json.loads(expect("cache", "dsh_usage", 0, "--cache-root", cache, "--sessions-root", sessions, "--json"))
    row = data["sessions"][0]
    require(row["lastPromptTokens"] == 1550 and row["input"] == 100 and row["output"] == 50 and not row["partial"],
            f"projection cache numbers: {row}")
    bad = tmp / "bad_cache"
    write(bad / "session-22222222-2222-4222-8222-222222222222.json", json.dumps({"version": 7, "record": {
        "identity": {"formatVersion": 7, "createdAt": 1700000000000, "cwd": "/home/dw/proj"},
        "rows": {"tokenUsage": {"val": {
            "totals": {"uncachedInputTokens": "bad", "outputTokens": True, "cacheReadTokens": 10, "cacheWriteTokens": 0},
            "last": {"turn": 1, "step": 1, "buckets": {"uncachedInputTokens": -5, "outputTokens": 1,
                                                         "cacheReadTokens": 0, "cacheWriteTokens": 0}}}}}}}))
    out = tmp / "usage.json"
    expect("bad numbers", "dsh_usage", 0, "--cache-root", bad, "--sessions-root", sessions, "--out", out,
           says="WARN PARTIAL")
    obj = json.loads(out.read_text(encoding="utf-8"))
    require(obj.get("partial") is True and obj["sessions"][0]["partial"] is True and obj.get("warnings"),
            f"partial not marked: {obj}")
    return "NO_DATA exit 2; prompt tokens 1550; bad numbers PARTIAL"


@test
def audit_loops(tmp):
    """dsh_audit.py loops on fixtures/loops: each category's positive file is found and its negative file is not
    (counts, --json, exit 1 / 0); child_error_unhandled is NOT_VERIFIED without a child result; a forked copy of a
    session counts once (copies=2); a bad --repeat or a missing file is NOT_RUN (exit 2). The two ds.7 checks now live
    in the base loop_guard core (3.0.0 B17); the fields DSH feeds them (each call's result, text_before) are each
    needed (a mutant without one is caught)."""
    fixtures = HERE / "fixtures" / "loops"
    for name in sorted(LOOP_EXPECTED):
        path = fixtures / f"{name}.jsonl"
        require(path.is_file(), f"no fixture {path}")
        want = {c: LOOP_EXPECTED[name].get(c, 0) for c in LOOP_CATEGORIES}
        data = json.loads(expect(f"loops {name}", "dsh_audit", 1 if LOOP_EXPECTED[name] else 0, "loops", "--events",
                                 path, "--json"))
        require(data["counts"] == want, f"loops {name}: counts {data['counts']}, want {want}")
        nv = [] if name in LOOP_CHILD_RESULTS else ["child_error_unhandled"]
        require(data["not_verified"] == nv, f"loops {name}: not_verified {data['not_verified']}")
    plain = expect("plain", "dsh_audit", 1, "loops", "--events", fixtures / "retry_pos.jsonl",
                   says=["LOOP retry_same_error tool=edit args=", "~ NOT_VERIFIED child_error_unhandled",
                         "DSH_LOOPS sessions=1 calls=2 findings=1 "])
    require(plain.count("LOOP retry_same_error") == 1, f"one LOOP line: {tail(plain)}")
    events = (fixtures / "retry_pos.jsonl").read_text(encoding="utf-8")
    fork = write(tmp / "fork.jsonl", events.replace("session-fx-retry_pos", "session-fx-retry_fork"))
    expect("forked copy", "dsh_audit", 1, "loops", "--events", fixtures / "retry_pos.jsonl", fork,
           says=["findings=1 ", "copies=2"])
    expect("--repeat 1", "dsh_audit", 2, "loops", "--events", fork, "--repeat", "1", says="NOT_RUN")
    expect("missing file", "dsh_audit", 2, "loops", "--events", tmp / "none.jsonl", says="NOT_RUN")
    source = (HERE / "dsh_audit.py").read_text(encoding="utf-8")
    mutants = [
        ("ping_pong without each call's result",
         '"result": c["result"],', '"result": "same",', "ping_pong_neg", "ping_pong"),
        ("retry without the written-text mark",
         '"text_before": any(previous < p < c["pos"] for p in texts)', '"text_before": False',
         "retry_neg", "retry_same_error"),
        ("bad_args without the DSH error code / name",
         'BAD_ARGS_NAMES = ("ToolArgsError",)', 'BAD_ARGS_NAMES = ()  # and no codes either\nBAD_ARGS_CODES = ()',
         "bad_args_pos", "bad_args"),
    ]
    for label, old, new, fixture, category in mutants:
        require(source.count(old) == 1, f"mutant {label}: the line is not in dsh_audit.py once")
        module = load(HERE / "dsh_audit.py", "selftest_dsh_audit_mutant", source.replace(old, new))
        code, out = call_main(module, "loops", "--events", fixtures / f"{fixture}.jsonl", "--json")
        got = json.loads(out)["counts"][category]
        require(got != LOOP_EXPECTED[fixture].get(category, 0), f"mutant {label} not caught ({category}={got})")
    return f"{len(LOOP_EXPECTED)} fixtures, fork once, NOT_RUN x2, {len(mutants)} mutants caught"


@test
def audit_chain(tmp):
    """dsh_audit.py chain_lines + verify: a rebuilt log starts with the rebuild line, chains the calls from seq 2 and
    verifies OK; an edited line fails verify; report_vs_audit reads it with the rebuilt-log note."""
    module = load(HERE / "dsh_audit.py", "selftest_dsh_audit")
    audit = load(tool("audit_log"), "selftest_audit_log")
    command = "python -m pytest -q"
    entries = []
    for number, text in enumerate(("git status", command), 1):
        entries.append({"ts": f"2026-11-14T03:0{number}:00.000+08:00", "session_id": "dsh-s1", "agent_id": "w1",
                        "tool": "PowerShell", "tool_use_id": f"c{number}", "kind": "result",
                        "input": audit.summary({"command": text}), "result": {"status": "ok"}, "duration_ms": 5})
    source = {"by": "dsh_audit.py", "version": module.BUILD_VERSION,
              "sessions": [{"session_id": "dsh-s1", "log": "session.v4.jsonl.zstd", "sha256": "0" * 64, "bytes": 1}],
              "lines": len(entries), "warnings": 0, "skipped": 0}
    lines, head = module.chain_lines(entries, source, now="2026-11-14T03:10:00.000+08:00")
    log = write(tmp / "rebuilt.jsonl", "".join(lines))
    first = json.loads(lines[0])
    require(first.get("kind") == "rebuild" and first.get("seq") == 1 and first.get("prev") == audit.GENESIS,
            f"line 1 is not the rebuild line: {tail(lines[0], 300)}")
    require(len(lines) == 3 and json.loads(lines[-1]).get("hash") == head, "the calls are not chained to the head")
    expect("verify", "dsh_audit", 0, "verify", "--log", log, says="OK")
    report = write(tmp / "report.md", "SESSION_ID: dsh-s1\nRAN: `" + command + "` exit=0\n")
    expect("report_vs_audit", "report_vs_audit", 0, "--report", report, "--log", log,
           says=["REPORT_VS_AUDIT: PASS claims=1 ok=1", "~ note: a log was rebuilt"])  # the base note names
    # transcript_audit.py for every rebuilt log (base 3.0.0; reported, not changed here)
    broken = write(tmp / "broken.jsonl", "".join(lines).replace("git status", "git push"))
    code, out = run("dsh_audit", "verify", "--log", broken)
    require(code != 0, f"verify accepted an edited line: {tail(out)}")
    return "rebuild line, verify OK, report note, edited line refused"


@test
def audit_lone_surrogate(tmp):
    """3.0.0-ds.8 fix (review P1-2): a DSH log keeps a cut emoji as a lone surrogate (\\ud83e); loops, reads, inject and
    the build path (session_entries + chain_lines + verify) still run and exit 0, the lone surrogate becomes U+FFFD
    before the base audit_log hashes it, a whole emoji (a surrogate pair) is kept as it is, and verify of a log line
    that holds a lone surrogate is BROKEN (exit 1), not a traceback. The fixture is synthetic, not a real DSH log."""
    fixture = HERE / "fixtures" / "lone_surrogate.jsonl"
    require(fixture.is_file(), f"no fixture {fixture}")
    for command, word in (("loops", "DSH_LOOPS sessions=1 calls=3 "), ("reads", "DSH_READS sessions=1 calls=3 reads=2 "),
                          ("inject", "DSH_INJECT")):
        out = expect(command, "dsh_audit", 0, command, "--events", fixture, says=word, lacks="Traceback")
        if command == "reads":
            require("notes/cut�.md" in out, f"reads: the cut path is not shown with U+FFFD: {tail(out)}")
    data = json.loads(expect("loops --json", "dsh_audit", 0, "loops", "--events", fixture, "--json"))
    require(data["calls"] == 3, f"loops --json: calls {data['calls']}")
    module = load(HERE / "dsh_audit.py", "selftest_dsh_audit_surrogate")
    audit = load(tool("audit_log"), "selftest_audit_log_surrogate")
    events, _ = module.dsh.parse_jsonl(fixture.read_text(encoding="utf-8"))
    items = module.session_entries(events, "session-fx-lone_surrogate", "lead", [])
    require(len(items) == 3, f"session_entries: {len(items)} entries, want 3")
    cut, whole = items[0]["entry"], items[2]["entry"]
    want = audit.output_record("ok", [{"text": "a truncated emoji � in the output", "type": "text"}])
    require(cut["result"] == want, f"cut output: {cut['result']} is not the hash of the U+FFFD text {want}")
    require("�" in cut["input"], f"cut input is not cleaned: {cut['input']!r}")
    want = audit.output_record("ok", [{"text": "a whole emoji \U0001f916 stays", "type": "text"}])
    require(whole["result"] == want, f"a whole emoji changed: {whole['result']} != {want}")
    source = {"by": "dsh_audit.py", "version": module.BUILD_VERSION, "sessions": [], "lines": len(items),
              "warnings": 0, "skipped": 0}
    lines, _ = module.chain_lines([item["entry"] for item in items], source, now="2026-11-14T03:10:00.000+08:00")
    log = tmp / "rebuilt.jsonl"
    log.write_bytes("".join(lines).encode("utf-8"))
    expect("verify", "dsh_audit", 0, "verify", "--log", log, says="OK", lacks="Traceback")
    bad = json.loads(lines[1])
    bad["input"] = "echo \ud83e"
    broken = write(tmp / "broken.jsonl", lines[0] + json.dumps(bad, sort_keys=True) + "\n")  # ASCII: \ud83e escaped
    expect("verify lone surrogate", "dsh_audit", 1, "verify", "--log", broken, says="BROKEN", lacks="Traceback")
    return "loops / reads / inject exit 0, U+FFFD before hashing, whole emoji kept, verify OK, bad line BROKEN"


@test
def guard_rules(tmp):
    """dsh_guard.py (self-check, base guard_rules.json): git status passes; git push is a reminder (exit 1) and in
    block mode exit 2; an existing pause flag stops everything (exit 2), an absent one does not."""
    expect("git status", "dsh_guard", 0, "--command", "git status")
    code, out = run("dsh_guard", "--command", "git push origin main")
    require(code == 1 and ("G02" in out or "push" in out.lower()), f"git push exit {code}: {tail(out)}")
    expect("block mode", "dsh_guard", 2, "--command", "git push origin main", "--mode", "block")
    expect("force push", "dsh_guard", 2, "--command", "git push --force origin main", "--mode", "block")
    flag = write(tmp / "PAUSE", "")
    code, out = run("dsh_guard", "--command", "git status", "--pause-flag", flag)
    require(code == 2 and "pause" in out.lower(), f"pause flag exit {code}: {tail(out)}")
    expect("no pause flag", "dsh_guard", 0, "--command", "git status", "--pause-flag", tmp / "NO_PAUSE")
    return "status / push / block / force / pause"


@test
def doctor(tmp):
    """dsh_doctor.py with a made-up DSH_HOME: the summary line, no FAIL (the base tools and every adapter file are
    there)."""
    home = tmp / "dsh_home"
    (home / "sessions").mkdir(parents=True)
    code, out = run("dsh_doctor", "--sessions-root", home / "sessions", "--cache-root", home / "cache",
                    env={"DSH_HOME": str(home)})
    require("DSH_DOCTOR:" in out, f"no summary: {tail(out)}")
    fails = [line for line in out.splitlines() if line.startswith("FAIL")]
    require(code == 0 and not fails, f"dsh_doctor exit {code}: {'; '.join(fails) or tail(out)}")
    return "DSH_DOCTOR summary, exit 0"


@test
def verify_dsh_run_unittest(tmp):
    """test_verify_dsh_run.py (the unittest suite of verify_dsh_run.py) passes."""
    code, out = run("test_verify_dsh_run", cwd=tmp, timeout=600)
    lines = out.strip().splitlines()
    require(code == 0 and lines and lines[-1].startswith("OK"), f"test_verify_dsh_run exit {code}: {tail(out)}")
    ran = [line for line in out.splitlines() if line.startswith("Ran ")]
    return ran[-1] if ran else "OK"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true", help="print the detail of passing tests too")
    parser.add_argument("--keep", action="store_true", help="keep the temp folder (printed at the end)")
    parser.add_argument("--only", help="run only these tests (comma-separated); the summary then says ONLY")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    wanted = [n.strip() for n in (args.only or "").split(",") if n.strip()]
    unknown = sorted(set(wanted) - {f.__name__ for f in TESTS})
    if unknown:
        parser.error("no such test: " + ", ".join(unknown))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dsh-selftest-"))
    passed = failed = skipped = 0
    try:
        for function in TESTS:
            name = function.__name__
            if wanted and name not in wanted:
                continue
            folder = tmp / name
            folder.mkdir()
            started = time.time()
            try:
                detail = function(folder)
                passed += 1
                line = f"PASS {name:<24} {time.time() - started:6.2f}s" + (f"  {detail}" if args.verbose and detail else "")
            except Skip as error:
                skipped += 1
                line = f"SKIP {name:<24} {error}"
            except AssertionError as error:
                failed += 1
                line = f"FAIL {name:<24} {error}"
            except Exception as error:  # a crash is a failure, never a pass
                failed += 1
                line = f"FAIL {name:<24} {type(error).__name__}: {error}"
            print(line, flush=True)
    finally:
        if args.keep:
            print(f"temp: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    total = passed + failed + skipped
    print(f"SELFTEST_DEEPSEEK{' ONLY' if wanted else ''}: {'PASS' if failed == 0 else 'FAIL'} tests={total} "
          f"pass={passed} fail={failed} skip={skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

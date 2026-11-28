"""One git worktree per worker, and the checks around it (DIRECTOR-WORK 3.0.0, items D3 and G6 of the series plan).

  python -I -X utf8 tools/worktree.py open REPO --order WO [--branch B] [--base REF] [--root DIR] [--brief BRIEF.md]
  python -I -X utf8 tools/worktree.py status DIR
  python -I -X utf8 tools/worktree.py cwd WS
  python -I -X utf8 tools/worktree.py temp WORK_DIR
  python -I -X utf8 tools/worktree.py same A B

open    `git worktree add -b <branch> <root>/<WO> <base>`: one worktree per worker, so two workers never write the
        same folder. root defaults to <REPO>/../wt, beside the project; a worktree inside the project folder is
        refused (the director's DIRECTOR/ folder lives there). An existing folder is refused and nothing is removed.
        The branch defaults to wt/<wo>; use the order's NEW_BRANCH and BASE_REF when it names them.
        R6 (review P1-3): open runs tools/spec_gate.py check first on --brief (default <REPO>/DIRECTOR/BRIEF.md, an
        old outside DIRECTOR/ names its brief); unless it passes, nothing is made and open exits 1. No hook needed,
        so beginner mode is gated too.
status  `WORKTREE: 隔離 worktree <root>` for a linked worktree, `WORKTREE: 共用 checkout（主 checkout） <root>` for a
        main checkout: the WORKTREE line of a report, so a worker never writes it by hand. Read from the git folders
        (a linked worktree's .git file names a git folder with a commondir file), so it also works where git is
        missing; a submodule is not taken for a worktree.
cwd     the first step of a run: `CWD: OK` when the current folder is WS, else BLOCKED (exit 1). Both sides go
        through realpath and normcase (case-insensitive on Windows); a subfolder is BLOCKED too. Writes nothing.
temp    makes <WORK_DIR>/tmp and prints the PowerShell and bash lines that point TEMP / TMP / TMPDIR at it, so
        scripts and temp output stay where the director can rerun them.
same    `SAME_REPO: YES` (exit 0) when A and B are checkouts of one repository: a worktree and its main checkout
        share the git common dir, two clones do not (G6: what a Stop event uses to tie a worktree to its project).

Exit 0 done / OK, 1 refused or BLOCKED or not the same repo, 2 cannot run (bad order id, not a checkout).
From the DeepSeek port's dsh_session.py (worker worktree, cwd check, TEMP lines); the git folder reading is
_common.find_repo / same_repo, one copy for every tool. Platforms that open worktrees themselves (Claude Code, Codex)
call open, or skip it and still use status and cwd. Standard library only.
"""
import argparse
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

_spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

ORDER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
TEMP_NAMES = ("TEMP", "TMP", "TMPDIR")


def _git(cwd, *args):
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _key(path):
    return os.path.normcase(os.path.realpath(str(path)))


def inside(path, folder):
    """True when path is folder or sits below it (realpath, case-insensitive on Windows)."""
    p, f = _key(path), _key(folder).rstrip("\\/")
    return p == f or p.startswith(f + os.sep)


def worktree_line(path):
    """The WORKTREE line for the checkout holding path, or None outside a checkout."""
    repo = common.find_repo(path)
    if repo is None:
        return None
    root = pathlib.Path(repo.root).resolve()
    if repo.linked:
        return f"WORKTREE: 隔離 worktree {root}"
    return f"WORKTREE: 共用 checkout（主 checkout） {root}"


def spec_gate_lines(brief):
    """(passed, lines) of tools/spec_gate.py check for brief (R6: no worktree before the spec passes)."""
    spec = importlib.util.spec_from_file_location("dw_spec_gate", pathlib.Path(__file__).with_name("spec_gate.py"))
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    lines = []
    return gate.run(brief, out=lines.append) == 0, lines


def open_worktree(repo_path, order_id, branch=None, base="HEAD", root=None, brief=None):
    """(exit, text): one git worktree for one worker, only after the spec gate passes."""
    if not ORDER_ID.fullmatch(order_id or ""):
        return 2, f"WORKER_WORKTREE: FAIL order id {order_id!r}: letters, digits, . _ - only"
    repo = common.find_repo(repo_path)
    if repo is None:
        return 2, f"WORKER_WORKTREE: FAIL {repo_path} is not a git checkout"
    project = pathlib.Path(repo.root).resolve()
    passed, gate = spec_gate_lines(pathlib.Path(brief) if brief else project / "DIRECTOR" / "BRIEF.md")
    if not passed:
        return 1, "\n".join(gate + ["WORKER_WORKTREE: FAIL SPEC_GATE: no worker worktree until the spec passes; "
                                    "nothing made"])
    target = (pathlib.Path(root) if root else project.parent / "wt").resolve() / order_id
    branch = branch or f"wt/{order_id.lower()}"
    if inside(target, repo.root):
        return 1, (f"WORKER_WORKTREE: FAIL {target} is inside the project folder {project}; open worker worktrees "
                   "beside it (default <REPO>/../wt)")
    if target.exists():
        return 1, f"WORKER_WORKTREE: FAIL {target} exists; one worktree per worker, nothing removed"
    code, out = _git(project, "worktree", "add", "-q", "-b", branch, str(target), base)
    if code != 0:
        return 1, f"WORKER_WORKTREE: FAIL git worktree add: {out}"
    line = worktree_line(target) or f"WORKTREE: NOT_A_CHECKOUT {target}"
    text = f"{gate[-1]}\nWORKER_WORKTREE: {target} branch={branch} base={base}\n{line}"
    return (0 if "隔離 worktree" in line else 1), text


def cwd_check(expected, actual=None):
    """(exit, lines): is the current folder the workspace the prompt or the config names? Reads only."""
    actual = os.getcwd() if actual is None else actual
    real_actual, real_expected = os.path.realpath(actual), os.path.realpath(expected)
    if _key(real_actual) == _key(real_expected):
        return 0, [f"CWD: OK {real_actual}"]
    where = "a subfolder of the workspace" if inside(real_actual, real_expected) else "not the workspace"
    return 1, [f"BLOCKED: cwd {real_actual} != {real_expected}",
               f"NEXT: {where}; stop, write nothing, and start again in {real_expected}"]


def temp_lines(work_dir):
    """Make <work_dir>/tmp; the lines that point TEMP / TMP / TMPDIR at it."""
    folder = pathlib.Path(work_dir).expanduser().resolve() / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    value = str(folder)
    quoted = value.replace("'", "''")
    posix = folder.as_posix().replace("'", "'\\''")
    return [f"TEMP_ENV: {value}",
            "POWERSHELL: " + "; ".join(f"$env:{name}='{quoted}'" for name in TEMP_NAMES),
            "BASH: export " + " ".join(f"{name}='{posix}'" for name in TEMP_NAMES)]


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open", help="one git worktree per worker, beside the project")
    o.add_argument("repo")
    o.add_argument("--order", required=True, metavar="WO", help="the order id, the worktree folder's name")
    o.add_argument("--branch", help="the new branch (default wt/<wo>; use the order's NEW_BRANCH)")
    o.add_argument("--base", default="HEAD", help="the start commit (the order's BASE_REF)")
    o.add_argument("--root", help="the folder that holds the worktrees (default <REPO>/../wt)")
    o.add_argument("--brief", help="the brief the spec gate checks (default <REPO>/DIRECTOR/BRIEF.md)")
    sub.add_parser("status", help="the WORKTREE line for a folder").add_argument("dir")
    sub.add_parser("cwd", help="BLOCKED unless the current folder is WS").add_argument("ws")
    sub.add_parser("temp", help="point TEMP / TMP / TMPDIR at <WORK_DIR>/tmp").add_argument("work_dir")
    s = sub.add_parser("same", help="are A and B checkouts of one repository (git common dir)?")
    s.add_argument("a")
    s.add_argument("b")
    a = ap.parse_args(argv)
    if a.cmd == "open":
        code, text = open_worktree(a.repo, a.order, a.branch, a.base, a.root, a.brief)
        print(text)
        return code
    if a.cmd == "status":
        line = worktree_line(a.dir)
        print(line or f"WORKTREE: NOT_A_CHECKOUT {a.dir}")
        return 0 if line else 2
    if a.cmd == "cwd":
        code, lines = cwd_check(a.ws)
        print("\n".join(lines))
        return code
    if a.cmd == "temp":
        print("\n".join(temp_lines(a.work_dir)))
        return 0
    same = common.same_repo(a.a, a.b)
    print(f"SAME_REPO: {'YES' if same else 'NO'} {a.a} {a.b}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())

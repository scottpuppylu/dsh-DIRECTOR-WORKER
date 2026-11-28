r"""The dispatch step of the DeepSeek Harness (DSH) director (3.0.0-ds.8, R6 hard line, SPEC_VARIANTS_300 1-4).

DSH has no hook before a tool call, so nothing stops a `subagent` call by itself. The director runs this tool first,
every time it starts a worker, and calls `subagent` only after it printed GO:

  python -I -X utf8 <REPO>/DIRECTOR/adapters/deepseek/dsh_dispatch.py <REPO>/DIRECTOR/orders/WO-012.md
  python -I -X utf8 <REPO>/DIRECTOR/adapters/deepseek/dsh_dispatch.py ORDER --repo <REPO> [--branch B] [--base REF]
         [--root DIR] [--brief BRIEF.md] [--snapshot DIR] [--timeout S] [--tools-dir DIR]

It runs, each as its own process with a time limit, and reads only their exit codes and output lines:
  1. tools/spec_gate.py check --brief BRIEF   the spec gate (BRIEF.md found as gate_check.py --hash finds it:
                                              beside the order, or DIRECTOR/BRIEF.md for an order in orders/)
  2. tools/gate_check.py --hash ORDER         the order hash and its DISPATCH line (gate_check runs the spec gate
                                              again; with --snapshot it keeps the order for --order-history)
  3. with --repo: tools/worktree.py open REPO --order <WO-ID>   one isolated worktree for this worker (it runs the
                                              spec gate a third time before git makes anything)
A step passes only on exit code 0 with the line it must print (step 2: exactly one DISPATCH line; step 3: a
WORKER_WORKTREE line). A step that times out, cannot start, is killed, exits non-zero or prints no such line blocks:
no result is never a pass. A file that is not a work order blocks too.

Prints the steps, then
  DSH_DISPATCH: GO order=<WO-ID> rev=<n> sha=<64 hex> worktree=<path|none>
  LOG: DISPATCH <WO-ID> rev=<n> sha=<64 hex>        copy into DIRECTOR_LOG.md (add `| class=.. effort=.. model=..`)
  NEXT: subagent ...                                 what to put in the subagent call (cwd = the worktree)
or
  DSH_DISPATCH: BLOCKED step=<spec_gate|hash|worktree|order> reason=<...>
Exit 0 GO, 1 BLOCKED, 2 usage error. Standard library only; writes nothing itself (step 2 with --snapshot and step 3
write what those tools write).

This is a guard against slips, not a security boundary: DSH can still call `subagent` without running this tool, and
an agent can run `spec_gate.py approve` itself (on Claude Code a hook blocks that; DSH has none). The checks after the
fact catch a dispatch with no DISPATCH line: `dispatch_check.py --log` and `gate_check.py --match --dispatch-log` fail,
and the `dsh_audit.py build` log has every subagent call of the session (tool=subagent).
"""
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH_LINE = re.compile(r"^[ \t]*DISPATCH[ \t]+(\S+)[ \t]+rev=(\d+)[ \t]+sha=([0-9a-fA-F]{64})[ \t\r]*$", re.M)
WORKTREE_LINE = re.compile(r"^WORKER_WORKTREE:[ \t]+([^\r\n]+?)[ \t]+branch=", re.M)
ORDER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*-\d+[A-Za-z0-9_-]*$")


def tools_dir(given=None):
    """The base tools/ folder: --tools-dir, else two folders up (the same in the repo and in an installed DIRECTOR/)."""
    return pathlib.Path(given) if given else HERE.parent.parent / "tools"


def load(folder, name):
    spec = importlib.util.spec_from_file_location(f"dsh_dispatch_{name}", folder / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd, timeout):
    """(exit code or None, output). None means no result: the program could not start, timed out or was killed by a
    signal (a negative return code on POSIX). The caller blocks on None, as on any code other than 0."""
    try:
        done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return None, f"timed out after {timeout}s " + (error.output or b"").decode("utf-8", "replace")[-400:]
    except OSError as error:
        return None, f"cannot start: {error}"
    out = done.stdout.decode("utf-8", "replace")
    code = done.returncode
    if not isinstance(code, int) or isinstance(code, bool) or code < 0:
        return None, f"killed (return code {code!r}) " + out[-400:]
    return code, out


def status(code):
    """The base rule (tools/_common.gate_status): PASS only for 0, INVALID for no code, FAIL otherwise."""
    if isinstance(code, bool) or not isinstance(code, int):
        return "INVALID"
    return "PASS" if code == 0 else "FAIL"


def blocked(step, reason, lines):
    lines.append(f"DSH_DISPATCH: BLOCKED step={step} reason={reason}")
    print("\n".join(lines))
    return 1


def dispatch(a):
    tools = tools_dir(a.tools_dir)
    order = pathlib.Path(a.order)
    lines = []
    for name in ("spec_gate.py", "gate_check.py") + (("worktree.py",) if a.repo else ()):
        if not (tools / name).is_file():
            return blocked("order", f"tool_missing:{tools / name}", lines)
    if not order.is_file():
        return blocked("order", f"order_not_found:{order}", lines)
    try:
        gate = load(tools, "gate_check")
        text = order.read_bytes().decode("utf-8-sig")
        if not gate.is_order(text, order):
            return blocked("order", "not_a_work_order (no GOVERNANCE line, not in orders/, not named WO-<n>)", lines)
        brief = gate.find_brief(order, a.brief)
    except Exception as error:  # a broken tool or an unreadable order is no result
        return blocked("order", f"cannot_read:{type(error).__name__}", lines)
    py = [sys.executable, "-I", "-X", "utf8"]

    code, out = run(py + [str(tools / "spec_gate.py"), "check", "--brief", str(brief)]
                    + (["--snapshot-dir", a.brief_snapshots] if a.brief_snapshots else []), a.timeout)
    lines.append(f"STEP spec_gate: {status(code)} exit={code}")
    lines += ["  " + line for line in out.strip().splitlines()[-12:]]
    if status(code) != "PASS":
        return blocked("spec_gate", f"{status(code)} exit={code} (talk the spec through, user confirms, user runs "
                                    "spec_gate.py approve)", lines)

    code, out = run(py + [str(tools / "gate_check.py"), "--hash", str(order), "--brief", str(brief)]
                    + (["--snapshot", a.snapshot] if a.snapshot else []), a.timeout)
    found = DISPATCH_LINE.findall(out)
    lines.append(f"STEP hash: {status(code)} exit={code} dispatch_lines={len(found)}")
    lines += ["  " + line for line in out.strip().splitlines()[-12:]]
    if status(code) != "PASS":
        return blocked("hash", f"{status(code)} exit={code}", lines)
    if len(found) != 1:
        return blocked("hash", f"dispatch_lines={len(found)} (need exactly 1)", lines)
    wo, rev, sha = found[0]

    where = "none"
    if a.repo:
        if not ORDER_ID.match(wo):
            return blocked("worktree", f"order id {wo!r} cannot name a worktree folder", lines)
        cmd = py + [str(tools / "worktree.py"), "open", a.repo, "--order", wo, "--base", a.base, "--brief", str(brief)]
        cmd += (["--branch", a.branch] if a.branch else []) + (["--root", a.root] if a.root else [])
        code, out = run(cmd, a.timeout)
        made = WORKTREE_LINE.findall(out)
        lines.append(f"STEP worktree: {status(code)} exit={code}")
        lines += ["  " + line for line in out.strip().splitlines()[-12:]]
        if status(code) != "PASS":
            return blocked("worktree", f"{status(code)} exit={code}", lines)
        if len(made) != 1:
            return blocked("worktree", "no WORKER_WORKTREE line", lines)
        where = made[0]
    lines.append(f"DSH_DISPATCH: GO order={wo} rev={rev} sha={sha} worktree={where}")
    lines.append(f"LOG: DISPATCH {wo} rev={rev} sha={sha}")
    lines.append(f"NEXT: subagent with the order {order} (ORDER_SHA256 {sha})"
                 + (f", cwd {where}; the worker's first step is worktree.py cwd {where}" if a.repo else
                    "; read-only work, or give --repo for a worktree"))
    print("\n".join(lines))
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("order", help="the work order (DIRECTOR/orders/WO-<n>.md)")
    ap.add_argument("--brief", help="the brief the spec gate checks (default: found as gate_check.py --hash finds it)")
    ap.add_argument("--brief-snapshots", metavar="DIR", help="spec_gate --snapshot-dir (default brief-history/)")
    ap.add_argument("--snapshot", metavar="DIR", help="keep the order in DIR (gate_check --hash --snapshot)")
    ap.add_argument("--repo", help="make the worker's worktree of this checkout (worktree.py open)")
    ap.add_argument("--branch", help="the worker branch (default wt/<wo>; use the order's NEW_BRANCH)")
    ap.add_argument("--base", default="HEAD", help="the start commit (the order's BASE_REF)")
    ap.add_argument("--root", help="the folder that holds the worktrees (default <REPO>/../wt)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per step (default 120)")
    ap.add_argument("--tools-dir", help="the base tools folder (default: tools/ two folders above this file)")
    a = ap.parse_args(argv)
    if a.timeout <= 0:
        ap.error("--timeout must be above 0")
    return dispatch(a)


if __name__ == "__main__":
    sys.exit(main())

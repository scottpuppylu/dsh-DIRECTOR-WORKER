#!/usr/bin/env python3
r"""BOOTSTRAP helper for the project repo (2.2.3-ds.3): the mechanical steps the lead used to do by hand.

  python -I -X utf8 <WS>/DIRECTOR/tools/bootstrap_repo.py --repo <REPO> --config <WS>/DIRECTOR/director_work.json
  python -I -X utf8 <WS>/DIRECTOR/tools/bootstrap_repo.py --repo <REPO> --config ... --check

Steps, each skipped when already done (so a rerun changes nothing):
  exclude   `.memsearch/` (the DSH memory search index, a tool product, not project source) is in
            <REPO>/.git/info/exclude; evidence_record.py wants a worktree without untracked files (WO-DS-004 DD-11)

2.2.5-ds.5 (WO-DS-009 B1): the spec-first steps (CLI lookup, writing its path into the config, init) are removed.
--config is only read: a director_work.json that still has the old "sdd" block prints its WARN lines
(safety_gate.legacy_notes: OpenSpec keys ignored, safety switches still read, 請搬到 safety) and nothing in the
file or the repo changes because of it (L-061: the old tool looked up a CLI, wrote its path and ran init).
2.3.0-ds.5: --config also prints `CONFIG verdict_self_check: warn|fail` (gate_check --verdict's self-check
severity; default warn in 2.3.x); any other value prints a WARN line and warn is what gate_check uses.

--check only reports (exit 1 when a step still has work to do). Without it the steps run. Never commits.
Prints one line per step and BOOTSTRAP_REPO: DONE|TODO|FAIL. Exit 0 done, 1 work left (--check) or a step failed,
2 usage error.
"""
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
EXCLUDES = (".memsearch/",)


def limits_module():
    spec = importlib.util.spec_from_file_location("bootstrap_repo_safety_gate", HERE / "safety_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_dir(repo):
    """<repo>/.git as a folder (a worktree's .git file names its git dir), or None."""
    dot = repo / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        m = re.match(r"gitdir:\s*(.+)", dot.read_text(encoding="utf-8").strip())
        if m:
            path = pathlib.Path(m.group(1))
            return path if path.is_absolute() else (repo / path).resolve()
    return None


def exclude_path(repo):
    """Common git info/exclude path for REPO (resolving linked worktrees via git --git-path / commondir), or None."""
    try:
        done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if done.returncode == 0:
            out = done.stdout.strip()
            if out:
                path = pathlib.Path(out)
                return path if path.is_absolute() else (repo / path).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    gd = git_dir(repo)
    if gd is None:
        return None
    commondir = gd / "commondir"
    if commondir.is_file():
        rel = commondir.read_text(encoding="utf-8", errors="replace").strip()
        if rel:
            base = pathlib.Path(rel)
            gd = base if base.is_absolute() else (gd / base).resolve()
    return gd / "info" / "exclude"


def step_exclude(repo, check):
    path = exclude_path(repo)
    if path is None:
        return "FAIL", f"{repo} is not a git checkout (no .git); .memsearch/ not excluded"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    have = {line.strip() for line in text.splitlines()}
    missing = [item for item in EXCLUDES if item not in have and item.rstrip("/") not in have]
    if not missing:
        return "OK", f"{path}: {', '.join(EXCLUDES)} already excluded"
    if check:
        return "TODO", f"{path}: add {', '.join(missing)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    add = ("" if not text or text.endswith("\n") else "\n") + "# dshdw bootstrap: tool products, local only\n" + \
        "".join(item + "\n" for item in missing)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(add)
    return "DONE", f"{path}: added {', '.join(missing)}"


def verdict_self_check_line(config_path):
    """2.3.0-ds.5: the verdict_self_check level of a director_work.json, as one line."""
    import json
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return f"WARN  CONFIG verdict_self_check: {config_path.name} not read ({type(error).__name__}); warn used"
    value = data.get("verdict_self_check", "warn") if isinstance(data, dict) else "warn"
    if value not in ("warn", "fail"):
        return f"WARN  CONFIG verdict_self_check: \"warn\" or \"fail\", got {value!r}; gate_check --verdict uses warn"
    origin = "" if isinstance(data, dict) and "verdict_self_check" in data else " (not set: the 2.3.x default)"
    return f"CONFIG verdict_self_check: {value}{origin}"


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="the project checkout")
    ap.add_argument("--config", help="DIRECTOR/director_work.json (only read)")
    ap.add_argument("--check", action="store_true", help="only report what is left to do")
    ap.add_argument("--skip", nargs="*", default=[], choices=("exclude",), help="steps to skip")
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    if not repo.is_dir():
        print(f"BOOTSTRAP_REPO: FAIL repo not found: {repo}")
        return 2
    config_path = pathlib.Path(a.config).resolve() if a.config else None
    if config_path is not None and not config_path.is_file():
        print(f"BOOTSTRAP_REPO: FAIL config not found: {config_path}")
        return 2
    if config_path is not None:
        limits = limits_module()
        config, problem = limits.load_config(None, config_path)
        if problem:
            print(f"BOOTSTRAP_REPO: FAIL {problem}")
            return 2
        for line in limits.legacy_notes(config):
            print(line)
        print(verdict_self_check_line(config_path))
    results = []
    if "exclude" not in a.skip:
        results.append(("exclude",) + step_exclude(repo, a.check))
    for name, status, detail in results:
        print(f"{status:5} {name}: {detail}")
    statuses = {status for _, status, _ in results}
    overall = "FAIL" if "FAIL" in statuses else "TODO" if "TODO" in statuses else "DONE"
    print(f"BOOTSTRAP_REPO: {overall}")
    return 0 if overall == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())

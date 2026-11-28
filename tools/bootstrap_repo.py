#!/usr/bin/env python3
"""Keep local-only files out of git, in the exclude file git really reads (3.0.0, item D6 of the series plan).

  python -I -X utf8 bootstrap_repo.py --repo <REPO or any of its worktrees>            # write what is missing
  python -I -X utf8 bootstrap_repo.py --repo <REPO> --check                             # only report
  python -I -X utf8 bootstrap_repo.py --repo <REPO> --add CLAUDE.local.md               # one more local-only file

Default entries: `.claude/settings.local.json` (setup_project_settings.py writes it and leaves a worktree alone while
git would commit it: NOT_IGNORED) and `DIRECTOR/` (3.0.0, R3: the director's files live inside the project and never
reach git; a folder that ignores itself with a `DIRECTOR/.gitignore` of `*` already counts as ignored). The line goes into the repo's shared info/exclude, the file
`git rev-parse --git-path info/exclude` names: in a linked worktree `.git` is a file, so `<worktree>/.git/info/exclude`
does not exist and an `echo ... >> .git/info/exclude` there fails; the shared file covers every worktree of the repo.
The path comes from _common.exclude_file (reads .git, gitdir: and commondir only).

Each entry: already ignored by git (any rule) -> OK; tracked in the repo -> FAIL (an exclude line cannot hide a tracked
file; untracking it changes the repo and needs the PO); otherwise it is added. Every entry is then checked with
`git check-ignore`: DONE only when git says it is ignored. Never commits, never edits .gitignore.

3.0.0 B13 (cdx report): an --add entry is an exclude pattern relative to the project. A leading `/` (anchored to the
project root, e.g. `/.claude/hooks/x.py`) stays in the exclude line, but git is asked about the project-relative path
(`.claude/hooks/x.py`): git takes `/...` as an absolute path and gave no answer. On Windows `\` is read as `/`, and an
absolute path inside the project is turned into the anchored relative one; an absolute path outside it (Git Bash turns
a leading `/` into its own install folder unless MSYS_NO_PATHCONV=1) is a usage error.

Prints one line per entry and BOOTSTRAP_REPO: DONE|TODO|FAIL. Exit 0 done, 1 work left (--check) or an entry failed,
2 usage error (no such folder, not a git checkout, a bad --add).
"""
import argparse
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

DEFAULT_ENTRIES = (".claude/settings.local.json", "DIRECTOR/")
HEADER = "# DW bootstrap_repo: local-only files (all worktrees of this repo)\n"


def load_common():
    spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    return common


def git(repo, *args):
    """(exit code, stdout) of one git command in REPO; exit None when git could not run."""
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return done.returncode, done.stdout


def ignored(repo, entry):
    """True / False as git check-ignore says (a tracked file is not ignored); None when git gave no answer."""
    code, _ = git(repo, "check-ignore", "-q", "--", entry)
    return {0: True, 1: False}.get(code)


def tracked(repo, entry):
    code, out = git(repo, "ls-files", "--", entry)
    return code == 0 and bool(out.strip())


def bad_entry(entry):
    if not entry.strip():
        return "empty"
    if "\n" in entry or "\r" in entry:
        return "more than one line"
    if entry.lstrip().startswith(("!", "#")):
        return "starts with ! or # (a negation or a comment, not a file to hide)"
    return None


def project_entry(entry, repo):
    """3.0.0 B13: (exclude line, project-relative path git is asked about) of one entry; ValueError for a path outside
    the project. A leading `/` anchors the line to the project root and is never given to git."""
    line = entry.strip()
    if os.name == "nt":
        line = line.replace("\\", "/")
    inside = os.name != "nt" and (line + "/").startswith(str(repo).rstrip("/") + "/")  # POSIX: only the project's own path
    if re.match(r"[A-Za-z]:/", line) or line.startswith("//") or inside:  # a file-system path, not a pattern
        folder = line.endswith("/")
        try:
            rel = pathlib.Path(line).resolve().relative_to(repo)
        except ValueError:
            raise ValueError(f"{entry!r} is outside the project {repo}; give a path relative to the project (in Git Bash "
                             "a leading / becomes the Git install folder: drop the / or set MSYS_NO_PATHCONV=1)") from None
        line = "/" + rel.as_posix() + ("/" if folder else "")
    query = line.lstrip("/")
    if not query:
        raise ValueError(f"{entry!r} names the whole project")
    return line, query


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="the project checkout, or any worktree of it")
    ap.add_argument("--add", action="append", default=[], metavar="PATTERN",
                    help="one more local-only file or pattern (repeatable), e.g. CLAUDE.local.md")
    ap.add_argument("--check", action="store_true", help="only report what is left to do")
    a = ap.parse_args(argv)
    for entry in a.add:
        why = bad_entry(entry)
        if why:
            print(f"BOOTSTRAP_REPO: FAIL input: --add {entry!r}: {why}")
            return 2
    repo = pathlib.Path(a.repo).resolve()
    if not repo.is_dir():
        print(f"BOOTSTRAP_REPO: FAIL input: repo not found: {repo}")
        return 2
    code, top = git(repo, "rev-parse", "--show-toplevel")  # review P2-10: patterns are checked from the top
    if code == 0 and top.strip():
        repo = pathlib.Path(top.strip()).resolve()
    path = load_common().exclude_file(repo)
    if path is None:
        print(f"BOOTSTRAP_REPO: FAIL input: {repo} is not in a git checkout (no .git)")
        return 2
    try:
        added = [project_entry(entry, repo) for entry in a.add]
    except ValueError as error:
        print(f"BOOTSTRAP_REPO: FAIL input: --add {error}")
        return 2
    entries = list(dict.fromkeys([*((e, e) for e in DEFAULT_ENTRIES), *added]))
    print(f"exclude file: {path} (shared by every worktree of this repo)")

    results, missing = [], []
    for entry, query in entries:
        state = ignored(repo, query)
        if state is None:
            results.append(("FAIL", entry, "git check-ignore gave no answer (git missing?); nothing written"))
        elif state:
            results.append(("OK", entry, "already ignored"))
        elif tracked(repo, query):
            results.append(("FAIL", entry, "tracked in the repo: an exclude line cannot hide it; untracking it "
                                           "changes the repo and needs the PO" + (
                                               " (R3: the director's files stay in the project but out of git; "
                                               "`git rm -r --cached DIRECTOR` once the PO agrees)"
                                               if entry == "DIRECTOR/" else "")))
        else:
            missing.append((entry, query))
    if missing and a.check:
        results += [("TODO", entry, f"add to {path}") for entry, _ in missing]
    elif missing:
        try:
            text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            have = {line.strip() for line in text.splitlines()}
            fresh = [entry for entry, _ in missing if entry not in have]  # review P2-10: never the same line twice
            path.parent.mkdir(parents=True, exist_ok=True)
            if fresh:
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(("" if not text or text.endswith("\n") else "\n")
                                 + ("" if HEADER in text else HEADER) + "".join(entry + "\n" for entry in fresh))
        except OSError as error:
            results += [("FAIL", entry, f"{path} not written: {error}") for entry, _ in missing]
        else:
            for entry, query in missing:  # done means git now ignores it, not that a line was written
                if ignored(repo, query):
                    results.append(("DONE", entry, "added; git check-ignore confirms"))
                else:
                    results.append(("FAIL", entry, "added, but git check-ignore still does not ignore it"))

    for status, entry, detail in results:
        print(f"{status:5} {entry}: {detail}")
    statuses = {status for status, _, _ in results}
    overall = "FAIL" if "FAIL" in statuses else "TODO" if "TODO" in statuses else "DONE"
    print(f"BOOTSTRAP_REPO: {overall}")
    return 0 if overall == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())

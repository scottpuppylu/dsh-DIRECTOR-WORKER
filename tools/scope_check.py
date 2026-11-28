"""Compare what a branch really changed with the SCOPE / FORBIDDEN lists of its work order.

Changed = the union of four git states, both sides of a rename: committed (merge base with BASE_REF .. HEAD), staged
(HEAD .. index), unstaged (index .. worktree) and untracked files that git does not ignore. So a change that was
committed or staged and then undone in the worktree is still seen. Submodule changes are always compared, whatever
`submodule.*.ignore` or `diff.ignoreSubmodules` says. Files marked assume-unchanged or skip-worktree, which git diff
skips, are hashed and compared with the index; one that differs counts as unstaged, and a `FLAGGED:` line says how
many are marked (a skip-worktree file missing from the worktree is a sparse checkout and counts as unchanged).
The line above the last one counts each state. FORBIDDEN wins over SCOPE. A path that matches no SCOPE entry is outside.

List items follow gate_check: ` #` starts a comment, and an item in backticks is taken as written.
Globs are relative to the repo root: `*` stays inside one folder, `**` crosses folders, a name without a wildcard also
covers everything below it. A leading `/` is ignored. Case is ignored on Windows.
Not seen: ignored files, files outside the repo. Only reads.

An optional `REQUIRED_CHANGES:` list in the order names globs the work must change: each one that no changed path
matches prints `MISSING <glob>` and makes it a VIOLATION, and the last line ends with ` missing=n`. An order without
the list gets the same output as before.
2.2 (F14): REQUIRED_CHANGES is no longer met by a change that only ever showed in one layer. The four-state union
above still catches out-of-scope work; the required globs are matched against the final result instead: the working
files as they are now (tracked files that differ from the merge base, untracked files, flagged files that differ)
or, with `--candidate SHA`, the candidate commit's tree against its merge base with BASE_REF (use it on the commit you
hand in). A `REQUIRED_BASIS:` line says which. A file staged and then put back as it was is MISSING.

2.2.5 (B10, shared checkout; ported from the DeepSeek port's 2.2.4-ds.4 B2): when several workers share one checkout
the four states above hold the other workers' files too. With --shared, or when the order's WORKTREE line says 共用 /
shared, only this order's work is counted: the commits in merge-base..HEAD (or ..--candidate) whose message names the
order ID (`WO-12: ...`; the leading WO-n of the title and of the file name), each commit's own files (one commit at a
time, not the sum of the branch), plus, without --candidate, uncommitted files inside SCOPE. Anything else changed in
the checkout prints `OTHER path` and is not checked; an out-of-scope file in this order's own commit is still OUTSIDE.
STATES shows own_commits= own_uncommitted=, the last line ends with ` shared=1 others=n`.
2.2.5 (B10): `BASE_REF = origin/main @ abc1234（v2.2.4）`: text in brackets, and after ` #`, is a comment. A
`WORKTREE:` line says, from the git folders (the same code as worktree.py status), whether the folder is a linked worktree (隔離 worktree) or the main
checkout (共用 checkout); copy it into the report instead of writing it by hand.
2.2.5 (B11): a path too long for git on Windows gives one line naming the path and how far over it is.
3.0.0 B1 (from agy.3): with --candidate (and no shared checkout) SCOPE, FORBIDDEN, OUTSIDE and REQUIRED_CHANGES are
all matched against the candidate's own diff, merge-base(BASE_REF, candidate)..candidate; the four states of the
checkout are not read (STATES shows candidate=n). So a reviewer on a clean checkout, another branch or an orphan HEAD
gets the same verdict as the worker; files left uncommitted in the checkout are not part of the candidate.

3.0.0 B4 (Director decision; from agydw / dshdw ds.4 B1 and B5; the rules are in safety_gate.py): checked only when
declared, at every strength.
  Size: the order's `ORDER_LIMITS = files=<n> lines=<n> test_lines=<n>` line, or for a Standard / Strict order the
  "order_limits" block of director_work.json (--config, default: the order's folder or the one above it). The final
  result (the --candidate diff, else the working files and untracked files, against the merge base; in a shared
  checkout this order's commits and in-scope uncommitted files) may change at most that many files, non-test lines
  (added + deleted, `git diff --numstat`; binary files count 0) and test-file lines (test_*.py, *_test.py, tests/).
  `SIZE: files=n lines=n test_lines=n limit=f/l/t` ('-' = off); over a limit is `OVERSIZE ...`, a VIOLATION, and the
  last line ends with ` oversize=1`: split the order.
  Protected tests: the order's TESTS_LOCKED files and the "protected_tests" globs may be added, or grow at their end
  (new tests appended). Changing or removing content that was there at the merge base, or deleting the file, is
  `PROTECTED path (...)`, a VIOLATION (` protected=n`). Line endings and trailing blank lines are ignored.
  `PROTECTED_CHANGED: a.py, b.py` (or NONE) lists the protected files that changed; copy it into the report
  (gate_check.py --match holds the two against git). A director_work.json that cannot be read, or limits / globs of the
  wrong type, is NOT_RUN.

The last line is the one to paste into the TASK REPORT. Exit 0 pass, 1 violation, 2 could not check.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import importlib.util

_spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
_spec = importlib.util.spec_from_file_location("dw_safety_gate", pathlib.Path(__file__).with_name("safety_gate.py"))
safety = importlib.util.module_from_spec(_spec)  # 3.0.0 B4: order_limits / protected_tests
_spec.loader.exec_module(safety)


def parse_list(text, key):
    """Items of a `KEY:` line followed by `- item` lines; None when the key is missing. ` #` starts a comment; an item
    written in backticks (`- `a #b.txt``) is taken as it is, so a name holding ` #` round-trips (S02)."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                quoted = re.fullmatch(r"`([^`]+)`(?:\s+#.*)?\s*", m.group(1))
                items.append(quoted.group(1) if quoted else re.split(r"\s+#", m.group(1))[0].strip())
            return items
    return None


def glob_regex(glob):
    g = glob.replace("\\", "/")
    g = g[2:] if g.startswith("./") else g.lstrip("/")
    g = g + "**" if g.endswith("/") else g
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    if not re.search(r"[*?]", g):
        out += "(?:/.*)?"
    return re.compile(out, re.I if os.name == "nt" else 0)


def matches(path, patterns):
    return next((glob for glob, rx in patterns if rx.fullmatch(path)), None)


def git(root, *args, stdin=None):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, input=stdin)
    if done.returncode:
        message = done.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(long_path(message, root) or f"git {' '.join(args)}: {message}")
    return done.stdout.decode("utf-8", "replace")


def long_path(message, root):
    """2.2.5 (B11): gate_check's one clear line for git's `Filename too long` (which path, how far over), else None."""
    if "Filename too long" not in message:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("gate_check_for_scope", pathlib.Path(__file__).with_name("gate_check.py"))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.long_path(message, root)
    except (OSError, ImportError, SyntaxError, AttributeError):
        return None


BRACKETED = re.compile(r"[（(][^（()）]*[)）]")


def order_base(text):
    """The base ref of a work order's BASE_REF line (`origin/main @ abc1234（v2.2.4） # note` gives abc1234), or None.
    2.2.5 (B10): text in brackets and after ` #` is a comment."""
    m = re.search(r"^\s*BASE_REF\s*=\s*(.*)$", text, re.M)
    value = BRACKETED.sub(" ", re.split(r"\s+#", m.group(1))[0]).split("@")[-1].split() if m else []
    return value[0] if value and not value[0].startswith("<") else None


ORDER_ID = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*-\d+")


def order_ids(text, path):
    """2.2.5 (from ds.4 B2): the IDs a commit message may name this order by: the leading `WO-n` / `WO-DS-n` of the
    title's first word and of the file name."""
    title = re.search(r"^#\s+(\S+)", text, re.M)
    ids = []
    for name in (title.group(1) if title else "", pathlib.Path(path).stem):
        m = ORDER_ID.match(name)
        if m and m.group(0).upper() not in (i.upper() for i in ids):
            ids.append(m.group(0))
    return ids


def shared_mode(text, flag):
    """2.2.5 (from ds.4 B2): on with --shared, or when the order's WORKTREE field says the workers share one checkout
    (共用 / shared)."""
    if flag:
        return True
    m = re.search(r"^[ \t]*WORKTREE[ \t]*=[ \t]*(.*)$", text, re.M)
    return bool(m and re.search(r"共用|shared", m.group(1), re.I))


def own_commits(root, since, until, ids):
    """Commits in since..until whose message names one of ids (as a whole word), oldest first."""
    if not ids:
        return []
    named = re.compile("|".join(rf"(?<![\w-]){re.escape(i)}(?!\w)" for i in ids), re.I)
    out = []
    for entry in git(root, "log", "--reverse", "--format=%H%x1f%B%x1e", f"{since}..{until}").split("\x1e"):
        sha, _, message = entry.strip().partition("\x1f")
        if sha and named.search(message):
            out.append(sha)
    return out


def commit_files(root, sha):
    """The paths one commit changes (against its first parent; all of them for a root commit)."""
    out = git(root, "diff-tree", "--no-commit-id", "-r", "--root", "--name-only", "--no-renames", "-z", sha)
    return {path for path in out.split("\0") if path}


def numstat(text):
    """3.0.0 B4: {path: added + deleted} from `git diff --numstat -z --no-renames` output; a binary file counts 0."""
    out = {}
    for row in text.split("\0"):
        parts = row.split("\t")
        if len(parts) == 3 and parts[2]:
            out[parts[2]] = out.get(parts[2], 0) + sum(int(n) for n in parts[:2] if n.isdigit())
    return out


def file_lines(root, path):
    """Lines of an untracked file (0 for a binary or unreadable one)."""
    try:
        data = pathlib.Path(root, path).read_bytes()
    except OSError:
        return 0
    return 0 if b"\0" in data[:8000] else len(data.splitlines())


def size_of(per_file):
    """(files, non-test lines, test lines) of {path: lines}: test files count as files, their lines apart."""
    test = [p for p in per_file if safety.is_test_file(p)]
    return len(per_file), sum(n for p, n in per_file.items() if p not in test), sum(per_file[p] for p in test)


def read_at(root, rev, path):
    """bytes of path at rev, or None when it is not there."""
    done = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"{rev}:{path}"], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def normal(data):
    return data.replace(b"\r\n", b"\n").rstrip(b"\n")


def check_protected(root, since, candidate, candidates, locked, globs):
    """3.0.0 B4 (dshdw ds.4 B5): (protected files that changed, [(path, why)] that broke the rule) over the changed
    paths `candidates`. A protected file may be added, or grow at its end; changing or removing content that was there
    at `since`, or deleting the file, breaks the rule. Line endings and trailing blank lines are ignored."""
    rx = [glob_regex(glob) for glob in list(globs) + list(locked)]
    changed, broken = [], []
    for path in sorted(candidates):
        if not any(r.fullmatch(path) for r in rx):
            continue
        old = read_at(root, since, path)
        new = read_at(root, candidate, path) if candidate else (
            pathlib.Path(root, path).read_bytes() if pathlib.Path(root, path).is_file() else None)
        if old == new:
            continue
        changed.append(path)
        if old is None:
            continue  # a new protected file: allowed
        if new is None:
            broken.append((path, "a protected test file was deleted"))
            continue
        before, after = normal(old), normal(new)
        if not (after.startswith(before) and (len(after) == len(before) or after[len(before):len(before) + 1] == b"\n")):
            broken.append((path, "existing content changed; a protected test file may only grow at its end"))
    return changed, broken


def protected_summary(repo, order_text, order_path, config, candidate=None):
    """3.0.0 B4 (dshdw ds.4 B5): (protected files changed, [(path, why)] broken) of one order, for gate_check --match
    to hold a report's PROTECTED_CHANGED against; None when the order protects nothing. The changed paths are the
    candidate's diff against its merge base (else the working files); in a shared checkout only this order's commits
    (and, with no candidate, its in-scope uncommitted files). Raises RuntimeError when git cannot tell."""
    locked, globs = safety.protected_paths(order_text, config)
    if not (locked or globs):
        return None
    base = order_base(order_text)
    if not base:
        raise RuntimeError("no usable BASE_REF in the work order")
    root = git(repo, "rev-parse", "--show-toplevel").strip()
    commit = git(root, "rev-parse", "--verify", candidate + "^{commit}").strip() if candidate else None
    since = git(root, "merge-base", base, commit or "HEAD").strip()
    names = ("diff", "--name-only", "--no-renames", "-z")
    if shared_mode(order_text, False):
        mine = own_commits(root, since, commit or "HEAD", order_ids(order_text, order_path)) or ([commit] if commit else [])
        paths = set().union(*(commit_files(root, sha) for sha in mine)) if mine else set()
        if not commit:
            scope_rx = [(g, glob_regex(g)) for g in parse_list(order_text, "SCOPE") or [] if g != "NONE"]
            loose = {p for p in git(root, *names, "HEAD").split("\0") if p}
            loose |= {p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p}
            paths |= {p for p in loose if matches(p, scope_rx)}
    elif commit:
        paths = {p for p in git(root, *names, since, commit).split("\0") if p}
    else:
        paths = {p for p in git(root, *names, since).split("\0") if p}
        paths |= {p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p}
    return check_protected(root, since, commit, paths, locked, globs)


def worktree_line(root):
    """2.2.5 (B10): `WORKTREE: 隔離 worktree <root>` for a linked worktree, `WORKTREE: 共用 checkout（主 checkout） <root>`
    for the main checkout. 3.0.0: one copy with worktree.py status, read from the git folders (_common.find_repo), so a
    path spelled through a link or a junction is never taken for an isolated worktree; None outside a checkout."""
    repo = _common.find_repo(root)
    if repo is None:
        return None
    kind = "隔離 worktree" if repo.linked else "共用 checkout（主 checkout）"
    return f"WORKTREE: {kind} {root}"


def hidden_changes(root):
    """(marked, changed): paths marked assume-unchanged or skip-worktree, and those whose worktree file is not the
    index blob (S03). git diff trusts the marks, so the files are hashed here with the repo's filters."""
    marked = {entry[2:]: entry[0] for entry in git(root, "ls-files", "-v", "-z").split("\0")
              if len(entry) > 2 and (entry[0].islower() or entry[0] == "S")}
    if not marked:
        return {}, set()
    index = {}
    for entry in git(root, "ls-files", "-s", "-z").split("\0"):
        meta, _, path = entry.partition("\t")
        if path in marked:
            index[path] = meta.split()[:2]
    changed, compare = set(), []
    for path, tag in marked.items():
        mode, blob = index.get(path, ("", ""))
        file = pathlib.Path(root, path)
        if mode not in ("100644", "100755"):
            continue  # a symlink or submodule entry: not hashed here
        if not file.is_file():
            if tag.islower():
                changed.add(path)  # assume-unchanged and gone: deleted
            continue  # skip-worktree and gone: a sparse checkout
        compare.append((path, blob))
    if compare:
        hashes = git(root, "hash-object", "--stdin-paths", stdin="\n".join(p for p, _ in compare).encode("utf-8")).split()
        changed |= {path for (path, blob), now in zip(compare, hashes) if now != blob}
    return marked, changed


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order", required=True, help="work order file holding SCOPE, FORBIDDEN and BASE_REF")
    ap.add_argument("--repo", default=".", help="any folder inside the worktree to check (default: current folder)")
    ap.add_argument("--base", help="base ref (default: BASE_REF of the work order)")
    ap.add_argument("--max-lines", type=int, default=20, help="how many violating paths to print (default 20)")
    ap.add_argument("--candidate", help="the commit handed in; 3.0.0 B1: SCOPE, FORBIDDEN and REQUIRED_CHANGES all match its diff")
    ap.add_argument("--shared", action="store_true", help="2.2.5: several workers share this checkout; count only "
                    "this order's commits, one at a time, and its in-scope uncommitted files (on by itself when the "
                    "order's WORKTREE says 共用 / shared)")
    ap.add_argument("--config", help="3.0.0 B4: director_work.json with \"order_limits\" and \"protected_tests\" "
                    "(default: in the order's folder or the one above it; none: only what the order declares)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    def cannot(reason):
        print(f"SCOPE_CHECK: NOT_RUN {reason}")
        return 2

    order = pathlib.Path(a.order)
    if not order.is_file():
        return cannot(f"work order not found: {a.order}")
    text = order.read_text(encoding="utf-8-sig")
    scope, forbidden = parse_list(text, "SCOPE"), parse_list(text, "FORBIDDEN")
    if scope is None or forbidden is None:
        return cannot("work order has no SCOPE: / FORBIDDEN: list (run gate_check.py --order)")
    if not scope or not forbidden:
        return cannot("SCOPE: / FORBIDDEN: has no `- item` line right below it (run gate_check.py --order)")
    scope, forbidden = [s for s in scope if s != "NONE"], [f for f in forbidden if f != "NONE"]
    required = parse_list(text, "REQUIRED_CHANGES")
    base = a.base or order_base(text)
    if not base or base.startswith("<"):
        return cannot("no usable BASE_REF in the work order; pass --base")
    shared = shared_mode(text, a.shared)
    scope_rx = [(g, glob_regex(g)) for g in scope]
    forbidden_rx = [(g, glob_regex(g)) for g in forbidden]
    notes, others, per_commit, where = [], set(), {}, None
    config, problems = safety.load_config(order, a.config)  # 3.0.0 B4: size limits and protected tests
    problems = [p for p in problems if "cannot be read" in p or "not a JSON object" in p
                or p.startswith(("SAFETY order_limits", "SAFETY protected_tests"))]
    if problems:
        return cannot(problems[0])
    try:
        limits = safety.order_limits(text, config)
    except ValueError as error:
        return cannot(str(error))
    locked, globs = safety.protected_paths(text, config)

    try:
        root = git(a.repo, "rev-parse", "--show-toplevel").strip()
        names = ("diff", "--name-only", "--no-renames", "--ignore-submodules=none", "-z")
        where = worktree_line(root)
        commit = git(root, "rev-parse", "--verify", a.candidate + "^{commit}").strip() if a.candidate else None
        final, basis = None, None
        if commit and not shared:  # 3.0.0 B1 (agy.3): only the candidate's diff; what the checkout holds is not read
            since = merge_base = git(root, "merge-base", base, commit).strip()
            states = {"candidate": git(root, *names, since, commit)}
            marked, hidden = {}, set()
            if required is not None:
                final, basis = states["candidate"], f"candidate={commit[:12]}"
        else:
            merge_base = git(root, "merge-base", base, "HEAD").strip()
            states = {"committed": git(root, *names, merge_base, "HEAD"), "staged": git(root, *names, "--cached", "HEAD"),
                      "unstaged": git(root, *names),
                      "untracked": git(root, "ls-files", "--others", "--exclude-standard", "-z")}
            marked, hidden = hidden_changes(root)
            since = git(root, "merge-base", base, commit).strip() if commit else merge_base
        if shared:  # 2.2.5 (B10, from ds.4 B2): this order's commits, one at a time
            ids = order_ids(text, order)
            mine = own_commits(root, since, commit or "HEAD", ids)
            if not mine and commit:
                mine = [commit]
                notes.append(f"SHARED: no commit in {since[:10]}..{commit[:10]} names {'/'.join(ids) or 'this order'}; "
                             "only --candidate itself is counted")
            elif not mine:
                notes.append(f"SHARED: no commit in {since[:10]}..HEAD names {'/'.join(ids) or 'this order'} yet; "
                             "name the order ID in each commit message")
            per_commit = {sha: commit_files(root, sha) for sha in mine}
        elif required is not None and not commit:  # 2.2 (F14): the final result, not the union of layers
            final = git(root, *names, merge_base) + "\0" + states["untracked"]
            basis = "worktree-final"
    except (RuntimeError, OSError) as error:
        return cannot(str(error))

    states = {state: {path for path in out.split("\0") if path} for state, out in states.items()}
    if "unstaged" in states:
        states["unstaged"] |= hidden
    if shared:
        uncommitted = states["staged"] | states["unstaged"] | states["untracked"]
        committed = set().union(*per_commit.values()) if per_commit else set()
        in_scope = {path for path in uncommitted if matches(path, scope_rx)} if not commit else set()
        if not commit:
            others = (uncommitted - in_scope) | {path for path in states["committed"] if path not in committed}
        states = {"own_commits": committed, "own_uncommitted": in_scope}
        changed = sorted(committed | in_scope)
        final = set(changed)
        basis = (f"shared commits={len(per_commit)}" + (f" candidate={commit[:12]}" if commit else "")
                 if required is not None else None)
    else:
        changed = sorted(set().union(*states.values()))
    size, guarded, broken = None, [], []
    try:  # 3.0.0 B4 (from agydw / dshdw ds.4 B1, B5): checked only when declared
        if limits and shared:
            per_file = {}
            for sha in per_commit:
                for path, lines in numstat(git(root, "diff-tree", "--no-commit-id", "-r", "--root", "--numstat",
                                               "--no-renames", "-z", sha)).items():
                    per_file[path] = per_file.get(path, 0) + lines
            loose = set(changed) - set().union(set(), *per_commit.values())
            untracked = {p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p}
            tracked = sorted(loose - untracked)
            if tracked:
                for path, lines in numstat(git(root, "diff", "--numstat", "--no-renames", "-z", "HEAD", "--",
                                               *tracked)).items():
                    per_file[path] = per_file.get(path, 0) + lines
            for path in loose & untracked:
                per_file[path] = per_file.get(path, 0) + file_lines(root, path)
        elif limits and commit:
            per_file = numstat(git(root, "diff", "--numstat", "--no-renames", "-z", since, commit))
        elif limits:
            per_file = numstat(git(root, "diff", "--numstat", "--no-renames", "-z", merge_base))
            for path in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
                if path:
                    per_file[path] = file_lines(root, path)
        if limits:
            size = size_of(per_file) + limits
        if locked or globs:
            guarded, broken = check_protected(root, since, commit, set(changed), locked, globs)
    except (RuntimeError, OSError) as error:
        return cannot(str(error))
    hits = []
    for path in changed:
        rule = matches(path, forbidden_rx)
        if rule:
            hits.append(("FORBIDDEN", path, rule))
        elif not matches(path, scope_rx):
            hits.append(("OUTSIDE", path, ""))
    count = sum(1 for hit in hits if hit[0] == "FORBIDDEN")
    outside = len(hits) - count
    forbidden_paths = {hit[1] for hit in hits if hit[0] == "FORBIDDEN"}
    hits += [("PROTECTED", path, why) for path, why in broken if path not in forbidden_paths]
    shielded = sum(1 for hit in hits if hit[0] == "PROTECTED")
    if not shared:
        final = {path for path in (final or "").split("\0") if path} | (hidden if basis == "worktree-final" else set())
    missing = [g for g in required or [] if g != "NONE" and not any(glob_regex(g).fullmatch(path) for path in final)]
    hits += [("MISSING", glob, "") for glob in missing]
    oversize = bool(size) and any(limit and got > limit for got, limit in zip(size[:3], size[3:]))
    if oversize:
        hits.append(("OVERSIZE", f"files={size[0]}/{size[3] or '-'} lines={size[1]}/{size[4] or '-'} "
                                 f"test_lines={size[2]}/{size[5] or '-'}",
                     "split the order (ORDER_LIMITS in the order, or order_limits in director_work.json)"))
    for kind, path, rule in hits[:a.max_lines]:
        print(f"{kind:9} {path}" + (f"  ({rule})" if rule else ""))
    if len(hits) > a.max_lines:
        print(f"... {len(hits) - a.max_lines} more")
    for path in sorted(others)[:a.max_lines]:
        print(f"OTHER     {path}  (shared checkout: not this order's; not checked)")
    if len(others) > a.max_lines:
        print(f"... {len(others) - a.max_lines} more OTHER")
    for note in notes:
        print(f"NOTE: {note}")
    if where:
        print(where)
    if marked:
        print(f"FLAGGED: {len(marked)} file(s) marked assume-unchanged or skip-worktree; {len(hidden)} differ from the index")
    print("STATES: " + " ".join(f"{state}={len(paths)}" for state, paths in states.items()))
    if basis:
        print(f"REQUIRED_BASIS: {basis} final={len(final)}")
    if size:
        print(f"SIZE: files={size[0]} lines={size[1]} test_lines={size[2]} limit={size[3] or '-'}/{size[4] or '-'}/"
              f"{size[5] or '-'} (test files: test_*.py, *_test.py, tests/)")
    if locked or globs:
        print("PROTECTED_CHANGED: " + (", ".join(guarded) if guarded else "NONE"))
    print(f"SCOPE_CHECK: {'VIOLATION' if hits else 'PASS'} base={merge_base[:10]} changed={len(changed)} "
          f"forbidden={count} outside={outside}" + (f" protected={shielded}" if shielded else "")
          + ("" if required is None else f" missing={len(missing)}") + (" oversize=1" if oversize else "")
          + (f" shared=1 others={len(others)}" if shared else ""))
    return 1 if hits else 0


def not_utf8(error, argv=None):
    """2.2 (v2.1.0 known issue): one line, never a traceback, for an input file that is not UTF-8 text. It names the
    file when it is on the command line or in a folder there (text files only: .md .json .jsonl .txt .log)."""
    import itertools
    named = []
    for arg in (sys.argv[1:] if argv is None else argv):
        path = pathlib.Path(arg)
        try:
            files = [path] if path.is_file() else (list(itertools.islice(
                (p for p in path.rglob("*") if p.suffix.lower() in (".md", ".json", ".jsonl", ".txt", ".log")
                 and ".git" not in p.parts), 2000)) if path.is_dir() else [])
        except (OSError, ValueError):
            files = []
        for file in files:
            try:
                file.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                named.append(str(file))
            except OSError:
                pass
    where = f" ({', '.join(dict.fromkeys(named[:3]))})" if named else ""
    return f"a file is not UTF-8 text{where}: {error.reason} at byte {error.start}; save it as UTF-8 and run again"


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UnicodeDecodeError as error:  # 2.2: one line and NOT_RUN (exit 2), never a traceback
        print(f"SCOPE_CHECK: NOT_RUN {not_utf8(error)}")
        sys.exit(2)
    except (RuntimeError, OSError, ValueError) as error:  # 2.2.5 (B7): never a traceback
        print(f"SCOPE_CHECK: NOT_RUN {type(error).__name__}: {' '.join(str(error).split())[:300]}")
        sys.exit(2)

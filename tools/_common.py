"""Shared helpers for the DIRECTOR-WORK tools (3.0.0, items G1 and G6 of the series plan). Standard library only,
Python 3.9 or later; nothing here starts a process.

  atomic writes  write_bytes_atomic / write_text_atomic / write_json_atomic: a crash leaves the old file or the new
                 one, never half of one.
  git folders    git_dir / git_common_dir / find_repo / same_repo / exclude_file: tell a checkout, a linked worktree
                 and its main checkout apart by reading .git, gitdir: and commondir only (works where git is missing).
  log tails      read_tail / tail_lines / tail_jsonl: one read of the end of a log, the cut first line dropped.
  gate results   exit_code_from / gate_status (G2): a gate that cannot read a result never passes. A missing exit
                 code, two different ones, an empty or unreadable input is INVALID, never PASS (the agy P0: a
                 workflow took output without a `Command exited with code N` line for exit 0).
  usage numbers  usage_number / usage_numbers / usage_partial / partial_line (D7): a token count is a non-negative
                 finite number; a bool, text, a negative or not-finite number counts as 0 and marks the total
                 `partial`. Which file and which fields hold the counts is each platform's own (its adapter reads
                 them); the rule for a value that is not a count is this one.

The tools run under `python -I`, which leaves the tools folder off sys.path, so a tool loads this file by path:

    spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)

Where each part comes from (the best of the four versions, merged):
  atomic writes  DW gate_check.write_snapshot and cdxdw cdx_common.atomic_write (temp file in the same folder, fsync,
                 os.replace, temp removed on any failure) with the text / JSON wrappers of agydw agy_common.
  git folders    agydw agy_common.find_git_root_and_common and dshdw bootstrap_repo.exclude_path; a .git file with no
                 commondir (a submodule) is no longer taken for a linked worktree.
  log tails      DW loop_guard.tail_entries and line_brief.tail; agydw agy_common.scan_tail_for_step is the same idea
                 for Antigravity's step logs and stays in that adapter.
  gate results   the agydw tools/agy_audit.py exit-line patterns, read strictly: no line or two codes is no result.
  usage numbers  dshdw ds.7 dsh_usage.read_number / read_usage (A1): bad fields are named and the result is partial.
"""
import collections
import contextlib
import json
import math
import os
import pathlib
import re
import stat
import tempfile

TAIL_BYTES = 64 * 1024

GitRepo = collections.namedtuple("GitRepo", "root git_dir common_dir linked")
GitRepo.__doc__ = """root: the checkout folder; git_dir: its own git folder; common_dir: the folder all worktrees of the
repo share (git_dir itself for a main checkout); linked: True for a linked worktree (`git worktree add`)."""


# ------------------------------------------------------------------ atomic writes ------------------------------------

def _mode_for(target):
    try:
        return stat.S_IMODE(os.stat(target).st_mode)
    except OSError:
        mask = os.umask(0)
        os.umask(mask)
        return 0o666 & ~mask

def write_bytes_atomic(path, data):
    """Write data to path through a temp file in the same folder (flush, fsync, os.replace), so a crash or a full disk
    leaves the old file or the new one, never a cut one. Makes the folder if needed; removes the temp file on any
    failure and raises. The temp name is short (.dw-XXXXXXXX.tmp) so a path near the Windows limit still fits.
    Returns the target path."""
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".dw-", suffix=".tmp", dir=str(target.parent))
    try:
        fh = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    try:
        with fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if os.name != "nt":  # mkstemp makes 0600; keep the old file's mode, or what open() would give a new one
            os.chmod(temp, _mode_for(target))
        os.replace(temp, str(target))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    return target


def write_text_atomic(path, text, encoding="utf-8", newline="\n"):
    """write_bytes_atomic for text. newline="\\n" (default) writes LF on every system; newline=None writes the
    system's line ending as open(path, "w") does; any other string replaces each "\\n"."""
    if newline is None:
        newline = os.linesep
    if newline != "\n":
        text = text.replace("\n", newline)
    return write_bytes_atomic(path, text.encode(encoding))


def write_json_atomic(path, value, indent=2, newline="\n"):
    """value as UTF-8 JSON (non-ASCII kept as is) and a closing newline, written atomically."""
    return write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=indent) + "\n", newline=newline)


# ------------------------------------------------------------------ git folders (files only) -------------------------

def _resolve(base, text):
    p = pathlib.Path(text.strip())
    return (p if p.is_absolute() else pathlib.Path(base) / p).resolve()


def git_dir(folder):
    """The git folder of the checkout at `folder` (not its parents): <folder>/.git when that is a folder, the folder a
    `.git` file names (`gitdir: ...`, a linked worktree or a submodule), else None. Reads files only."""
    dot = pathlib.Path(folder) / ".git"
    try:
        if dot.is_dir():
            return dot.resolve()
        if dot.is_file():
            m = re.match(r"gitdir:\s*(.+)", dot.read_text(encoding="utf-8", errors="replace").strip())
            if m:
                return _resolve(dot.parent, m.group(1))
    except (OSError, ValueError):
        pass
    return None


def git_common_dir(gitdir):
    """The common git folder for a git folder: the one its `commondir` file names (a linked worktree), else gitdir."""
    gitdir = pathlib.Path(gitdir)
    try:
        text = (gitdir / "commondir").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return gitdir
    return _resolve(gitdir, text) if text else gitdir


def find_repo(start):
    """GitRepo for the checkout holding `start` (a file or a folder), walking up its parents; None outside a repo or
    when the first .git found cannot be read. Reads files only, so it also works where git is not installed."""
    try:
        cur = pathlib.Path(start).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if cur.is_file():
        cur = cur.parent
    for folder in (cur, *cur.parents):
        if not os.path.lexists(folder / ".git"):
            continue
        gd = git_dir(folder)
        if gd is None:
            return None
        common = git_common_dir(gd)
        return GitRepo(folder, gd, common, (gd / "commondir").is_file())
    return None


def _key(path):
    return os.path.normcase(str(path))


def same_repo(a, b):
    """True when a and b sit in checkouts of the same repository (a worktree and its main checkout count as the same,
    two clones do not): their common git folders are the same folder. False when either is outside a repo."""
    ra, rb = find_repo(a), find_repo(b)
    return bool(ra and rb) and _key(ra.common_dir) == _key(rb.common_dir)


def exclude_file(start):
    """The info/exclude file git reads for the checkout holding `start`: it lives in the common git folder, so every
    worktree of a repo shares it (what `git rev-parse --git-path info/exclude` prints). None outside a repo."""
    repo = find_repo(start)
    return None if repo is None else repo.common_dir / "info" / "exclude"


# ------------------------------------------------------------------ log tails ----------------------------------------

def read_tail(path, limit=TAIL_BYTES):
    """(data, cut): the last `limit` bytes of a file in one read; cut is True when the file is longer, so the first
    line of data may be the end of a longer line. Raises OSError (FileNotFoundError for a missing file)."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - limit))
        return fh.read(), size > limit


def _tail_raw_lines(data, cut):
    lines = data.split(b"\n")
    if cut:
        lines = lines[1:]
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def tail_lines(path, count=None, limit=TAIL_BYTES):
    """The last `count` lines (all of the tail when count is None) of a text file, UTF-8 with bad bytes replaced,
    line endings removed; a cut first line is dropped. Raises OSError like read_tail."""
    data, cut = read_tail(path, limit)
    lines = [line.decode("utf-8", errors="replace").rstrip("\r") for line in _tail_raw_lines(data, cut)]
    if count is None:
        return lines
    return lines[-count:] if count > 0 else []


def tail_jsonl(path, limit=TAIL_BYTES):
    """The JSON objects (dicts) on the lines in the last `limit` bytes of a JSON-lines log, oldest first. A cut first
    line, blank lines, lines that are not JSON and JSON that is not an object are skipped; [] when the file cannot be
    read."""
    try:
        data, cut = read_tail(path, limit)
    except OSError:
        return []
    out = []
    for line in _tail_raw_lines(data, cut):
        try:
            entry = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


# ------------------------------------------------------------------ gate results (G2) --------------------------------
# A line that states a command's exit code, at the start of a line: `Command exited with code 3` (Antigravity),
# `Exit code: 3`, `EXIT_CODE: 3`, `exit=3`.
EXIT_LINE = re.compile(r"^[ \t]*(?:Command exited with code|Exit code:|EXIT_CODE[ \t]*[:=]|exit=)[ \t]*(-?\d+)\b",
                       re.M | re.I)


def exit_code_from(text, pattern=EXIT_LINE):
    """The exit code a command's text output states, or None: no such line, or lines with two different codes (a
    command can print a line that looks like the harness's own). None is no result; gate_status(None) is INVALID."""
    if not isinstance(text, str):
        return None
    codes = {int(m.group(1)) for m in pattern.finditer(text)}
    return codes.pop() if len(codes) == 1 else None


def gate_status(code):
    """PASS only for exit code 0; INVALID for no code (None, or not a whole number); FAIL for any other code."""
    if isinstance(code, bool) or not isinstance(code, int):
        return "INVALID"
    return "PASS" if code == 0 else "FAIL"


# ------------------------------------------------------------------ usage numbers (D7) -------------------------------
def usage_number(value, field="value", invalid=None):
    """A token count from a platform's usage record: a non-negative finite int or float is itself. None (the record
    has no such field) is 0 and fine. Anything else is 0 and `(field, what it was)` is added to invalid: a bool (True is
    not 1 token), text (even "12"), a negative or not-finite number, a list or an object. A total that took such a 0 is
    partial, never a measured number (3.0.0 D7, from dshdw ds.7)."""
    if value is None:
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return value
    if invalid is not None:
        kind = "bool" if isinstance(value, bool) else type(value).__name__
        invalid.append((field, f"{kind}({value!r})"[:40]))
    return 0


def usage_numbers(record, keys, prefix="", invalid=None):
    """[usage_number(record[key]) for key in keys]. None gives zeros; a record that is not an object is one invalid
    field (prefix without its dot, or "usage") and gives zeros."""
    if record is None:
        return [0] * len(keys)
    if not isinstance(record, dict):
        if invalid is not None:
            invalid.append((prefix.rstrip(".") or "usage", f"{type(record).__name__}({record!r})"[:40]))
        return [0] * len(keys)
    return [usage_number(record.get(key), prefix + key, invalid) for key in keys]


def usage_partial(invalid):
    """The fields every usage report carries: {"partial": bool, "invalid_count": n, "invalid_fields": sorted names}."""
    invalid = invalid or []
    return {"partial": bool(invalid), "invalid_count": len(invalid),
            "invalid_fields": sorted({field for field, _ in invalid})}


def partial_line(invalid, shown=5):
    """One line for a partial usage read, or None when nothing was invalid: how many values, the first few, and that the
    totals are a lower bound, not a measurement."""
    if not invalid:
        return None
    first = ", ".join(f"{field}={what}" for field, what in invalid[:shown])
    more = f" (+{len(invalid) - shown} more)" if len(invalid) > shown else ""
    return (f"PARTIAL usage: {len(invalid)} value(s) were not a non-negative number and count as 0: {first}{more}; "
            "the totals are a lower bound, not a measurement")


def main(argv=None):
    import argparse
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    print("_common: shared helpers for the tools in this folder; nothing to run (see --help)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

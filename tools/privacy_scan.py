#!/usr/bin/env python3
"""Scan the whole tree for private data before anything goes public (3.0.0, review privacy ruling).

  python -I -X utf8 tools/privacy_scan.py [--repo DIR]            # tracked + untracked, not ignored (working tree)
  python -I -X utf8 tools/privacy_scan.py --repo DIR --rev HEAD   # the files of one commit (what release.py ships)
  python -I -X utf8 tools/privacy_scan.py --words FILE ...        # more private words, one per line (a local file)

release.py scans only what changed since the remote branch; this tool reads every file and every path name, so a
leak that went in long ago is found too. Both use the rules below and the same allow file: release.py's change scan
calls rules_and_allows() and line_hits() here (3.0.0 B9), so there is one rule set. Rules (each hit names its rule; the text itself is never printed whole):
  drive_path    a drive-letter path: <letter>:/ or <letter>:\\ (write <WS> for the workspace instead)
  user_folder   a user folder: /Users/<name>, \\Users\\<name>, /home/<name>
  email         an email address
  token         a token or key in a known format (the PATTERNS of secret_mask.py)
  code_name     the code names of the owner's other projects (stored escaped below, so this file does not hit itself)
  owner_handle  the owner's account name outside the public repo URL
  private_word  a word from --words FILE or <repo>/privacy_banned.local.txt (real names, real emails; keep that file
                local: `bootstrap_repo.py --add privacy_banned.local.txt`)
Binary files (a NUL byte) are skipped and counted.

Allowed text lives in tools/privacy_allow.txt of the scanned repo (read from --rev when given), one entry per line:
  <rule>: <regex> | <reason>
A hit is allowed when an entry of its rule matches a span of the same line that covers the hit. An entry without a
reason, with an unknown rule or a bad regex makes the scan INVALID: an allow entry nobody can explain is not kept.
In the allow file only the reason column is scanned (its regex column names what it allows).

Prints `HIT <rule> <path>:<line> <masked>` per hit and `PRIVACY_SCAN: CLEAN|FAIL|INVALID ...`.
Exit 0 clean, 1 a hit, 2 cannot run (not a git checkout, bad allow file, bad --words file).
"""
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ALLOW_PATH = "tools/privacy_allow.txt"
LOCAL_WORDS = "privacy_banned.local.txt"
# escaped on purpose: the scanner reads its own source too
CODE_NAMES = ("\x62aseball", "\x78iaoluo", "\u5c0f\u6d1b", "\u6de1\u6c5f", "\x54KU", "\x54aipei \x44ome")
OWNER = "\x73cottpuppylu"
RULES = {
    "drive_path": re.compile(r"(?<![A-Za-z0-9_\\])[A-Za-z]:(?:\\\\|[\\/])"),
    "user_folder": re.compile(r"(?i)(?:(?<=/[a-z])|(?<![\w.]))(?:/users|\\\\users|\\users|/home)(?:\\\\|[\\/])(?=[A-Za-z0-9_.-])"
                              r"[A-Za-z0-9_.-]+"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    "code_name": re.compile(r"(?i)" + "|".join(re.escape(n) if not n.isupper() else r"\b" + n + r"\b"
                                               for n in CODE_NAMES)),
    "owner_handle": re.compile(r"(?i)" + OWNER),
}
ALL_RULES = (*RULES, "token", "private_word")


class Invalid(Exception):
    pass


def secret_patterns():
    spec = importlib.util.spec_from_file_location("secret_mask", HERE / "secret_mask.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PATTERNS


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false", *args], capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=300)
    if done.returncode:
        raise Invalid(f"git {' '.join(args[:3])}: {done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout


def parse_allow(text, where):
    """[(rule, regex)] from an allow file; Invalid on an entry without a reason, an unknown rule or a bad regex."""
    entries = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, sep, reason = raw.rpartition(" | ")  # not stripped first: in `x |  ` the reason is empty
        rule, colon, pattern = head.partition(":")
        rule, pattern = rule.strip(), pattern.strip()
        if not sep or not reason.strip():
            raise Invalid(f"{where}:{number}: no reason (write `<rule>: <regex> | <reason>`)")
        if not colon or rule not in ALL_RULES:
            raise Invalid(f"{where}:{number}: unknown rule {rule!r} (one of {', '.join(ALL_RULES)})")
        try:
            entries.append((rule, re.compile(pattern)))
        except re.error as error:
            raise Invalid(f"{where}:{number}: bad regex: {error}")
    return entries


def parse_words(text, where):
    words = []
    for number, raw in enumerate(text.splitlines(), 1):
        word = raw.split(" | ")[0].strip()
        if word and not word.startswith("#"):
            if len(word) < 3:
                raise Invalid(f"{where}:{number}: a private word needs 3 characters or more")
            words.append(word)
    return words


def mask(rule, text):
    if rule in ("token", "private_word") or len(text) < 4:
        return f"[{rule}, {len(text)} chars]"
    return f"{text[:2]}***({len(text)})"


def line_hits(line, rules, allows):
    """[(rule, matched text)] in one line that no allow entry covers."""
    hits = []
    for rule, pattern in rules:
        for m in pattern.finditer(line):
            covered = any(a_rule == rule and any(o.start() <= m.start() and m.end() <= o.end()
                                                 for o in regex.finditer(line))
                          for a_rule, regex in allows)
            if not covered:
                hits.append((rule, m.group(0)))
    return hits


def files_of(repo, rev):
    """[(path, bytes)] of the working tree (tracked + untracked, not ignored) or of commit REV."""
    if rev:
        names = [n for n in git(repo, "ls-tree", "-r", "-z", "--name-only", rev).decode("utf-8").split("\0") if n]
        return [(name, git(repo, "cat-file", "blob", f"{rev}:{name}")) for name in names]
    names = git(repo, "ls-files", "-co", "--exclude-standard", "-z").decode("utf-8").split("\0")
    out = []
    for name in dict.fromkeys(n for n in names if n):
        path = repo / name
        if path.is_file():
            out.append((name, path.read_bytes()))
    return out


def rules_and_allows(repo, allow_text, words_files=()):
    """([(rule, regex)], [(rule, allow regex)]) for one repo: RULES, the token formats, the private words (--words
    files and <repo>/privacy_banned.local.txt) and the allow entries of allow_text. Shared with release.py's change
    scan (3.0.0 B9). Invalid on a bad allow file or words file."""
    allows = parse_allow(allow_text, ALLOW_PATH)
    words = []
    local = repo / LOCAL_WORDS
    for path in [*(pathlib.Path(w) for w in words_files), *([local] if local.is_file() else [])]:
        try:
            words += parse_words(path.read_text(encoding="utf-8"), path.name)
        except OSError as error:
            raise Invalid(f"--words {path.name}: {error}")
    rules = list(RULES.items()) + [("token", p) for _, p in secret_patterns()]
    if words:
        rules.append(("private_word", re.compile("(?i)" + "|".join(re.escape(w) for w in words))))
    return rules, allows


def allow_text_of(repo, rev=None):
    """The allow file of the working tree, or of commit REV ("" when there is none)."""
    if rev:
        try:
            return git(repo, "cat-file", "blob", f"{rev}:{ALLOW_PATH}").decode("utf-8", "replace")
        except Invalid:
            return ""
    path = pathlib.Path(repo) / ALLOW_PATH
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def scan(repo, rev=None, words_files=()):
    """(hits [(rule, path, line, masked)], files scanned, binary skipped); Invalid when it cannot run."""
    repo = pathlib.Path(repo).resolve()
    if subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True).returncode:
        raise Invalid(f"{repo} is not a git checkout")
    files = files_of(repo, rev)
    by_name = dict(files)
    allow_text = by_name.get(ALLOW_PATH, b"").decode("utf-8", "replace")
    rules, allows = rules_and_allows(repo, allow_text, words_files)
    hits, scanned, binary = [], 0, 0
    for name, data in files:
        if name == LOCAL_WORDS:
            continue  # the local word list itself (it should be ignored by git; never released)
        for rule, text in line_hits(name, rules, allows):
            hits.append((rule, name, 0, mask(rule, text)))
        if b"\0" in data:
            binary += 1
            continue
        scanned += 1
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if name == ALLOW_PATH:
                line = line.rpartition(" | ")[2]
            for rule, text in line_hits(line, rules, allows):
                hits.append((rule, name, number, mask(rule, text)))
    return hits, scanned, binary


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the checkout to scan (default: current folder)")
    ap.add_argument("--rev", help="scan the files of this commit instead of the working tree")
    ap.add_argument("--words", action="append", default=[], metavar="FILE", help="more private words (repeatable)")
    a = ap.parse_args(argv)
    try:
        hits, scanned, binary = scan(a.repo, a.rev, a.words)
    except Invalid as error:
        print(f"PRIVACY_SCAN: INVALID {error}")
        return 2
    for rule, name, number, shown in hits:
        print(f"HIT {rule} {name}:{number} {shown}")
    where = f"rev {a.rev}" if a.rev else "working tree"
    if hits:
        print(f"PRIVACY_SCAN: FAIL {len(hits)} hit(s) in {where}; files={scanned} binary_skipped={binary}")
        return 1
    print(f"PRIVACY_SCAN: CLEAN {where}; files={scanned} binary_skipped={binary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check that a DW series README has every section it must have (3.0.0, PO 11-28: "most READMEs are incomplete, with
no word on the base or the other versions"; SPEC_VARIANTS_300 section 1-9).

  python -I -X utf8 tools/readme_check.py [--repo DIR]                  # README.md of the working tree
  python -I -X utf8 tools/readme_check.py --repo DIR --rev HEAD         # README.md of one commit (release.py uses this)
  python -I -X utf8 tools/readme_check.py --kind base|variant ...       # default: variant when BASE_VERSION exists

What it checks (a `## ` heading inside a ``` block does not count):
  both kinds  a `# ` title and some text before the first `## ` (what this is, for which platform, how to start);
              `## 所屬系列` whose table has a row for each repo of the series (SERIES below), each row with a
              https://github.com/ address and a version such as `3.0.0-cld.1`; the sections 跨變體借用 / 換手提示詞 /
              版號規則 / CHANGELOG / 致謝（Credits）. 跨變體借用 is its table (做法 | 原本出自哪版 | 現在用哪版 |
              怎麼處理) or 無
  variant     also the base version from BASE_VERSION and a frozen base commit (7-40 hex, in backticks) in 所屬系列,
              and the sections 新增 / 沿用上游 / 拿掉（NOT_PORTED） / 安裝.
A section with nothing to say says 無; a section that is missing, or a heading with nothing under it, fails.
The heading names are matched from the start, so `## 新增（只有這個變體有）` is the 新增 section.

Prints `MISSING <section>`, `EMPTY <section>` or `BAD <section>: <why>` per problem, then
`README_CHECK: PASS|FAIL|INVALID kind=<kind> ...`. Exit 0 pass, 1 a problem, 2 cannot run (no README.md, not a git
checkout with --rev, an unknown --rev). A caller that gets no exit code, or no PASS line, counts it as FAIL.
"""
import argparse
import pathlib
import re
import subprocess
import sys

SERIES = ("DIRECTOR-WORK", "cld-DIRECTOR-WORKER", "dsh-DIRECTOR-WORKER", "cdx-DIRECTOR-WORKER", "agy-DIRECTOR-WORKER")
SERIES_SECTION = "所屬系列"
SHARED_SECTIONS = ("跨變體借用", "換手提示詞", "版號規則", "CHANGELOG", "致謝")  # base and variant (audit 300 section 4)
VARIANT_SECTIONS = ("新增", "沿用上游", "拿掉", "跨變體借用", "安裝", "換手提示詞", "版號規則", "CHANGELOG", "致謝")
BORROW_HEADER = "| 做法 | 原本出自哪版 | 現在用哪版 | 怎麼處理 |"
VERSION_SHAPE = re.compile(r"`\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?`")
SHA_SHAPE = re.compile(r"`[0-9a-f]{7,40}`")


class Invalid(Exception):
    pass


def read(repo, rev, name):
    """Text of one file, or None when it does not exist (working tree, or `git show <rev>:<name>`)."""
    if rev is None:
        path = pathlib.Path(repo) / name
        if not path.is_file():
            return None
        try:
            return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError) as error:
            raise Invalid(f"cannot read {name}: {error}")
    try:
        proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise Invalid(f"{rev} is not a commit of {repo}")
        proc = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{name}"], capture_output=True)
    except OSError as error:
        raise Invalid(f"git cannot run: {error}")
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as error:
        raise Invalid(f"{name} at {rev} is not UTF-8: {error}")


def sections(text):
    """(intro, {heading: body}) - headings are the `## ` lines outside ``` blocks."""
    intro, found, current, fence = [], {}, None, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            current = line[3:].strip()
            found.setdefault(current, [])
            continue
        (intro if current is None else found[current]).append(line)
    return "\n".join(intro), {k: "\n".join(v) for k, v in found.items()}


def find(found, name):
    return next((k for k in found if k.startswith(name)), None)


def problems_of(text, kind, base_version):
    problems = []
    intro, found = sections(text)
    lines = [l for l in intro.split("\n") if l.strip()]
    if not lines or not lines[0].startswith("# "):
        problems.append("MISSING title: the first line is a `# ` title")
    elif len(lines) < 2:
        problems.append("EMPTY intro: say what this is, for which platform, and how to start, before the first `## `")
    wanted = (SERIES_SECTION,) + (VARIANT_SECTIONS if kind == "variant" else SHARED_SECTIONS)
    for name in wanted:
        heading = find(found, name)
        if heading is None:
            problems.append(f"MISSING {name}")
        elif not found[heading].strip():
            problems.append(f"EMPTY {name}: write 無 when there is nothing to say")
    heading = find(found, SERIES_SECTION)
    if heading is not None and found[heading].strip():
        body = found[heading]
        rows = [l for l in body.split("\n") if l.lstrip().startswith("|")]
        for repo in SERIES:
            row = next((r for r in rows if re.search(r"(?<![A-Za-z0-9-])" + re.escape(repo) + r"(?![A-Za-z0-9-])", r)),
                       None)
            if row is None:
                problems.append(f"BAD {SERIES_SECTION}: no table row for {repo}")
            elif "https://github.com/" not in row or not VERSION_SHAPE.search(row):
                problems.append(f"BAD {SERIES_SECTION}: the {repo} row needs its https://github.com/ address and a "
                                f"version in backticks")
        if kind == "variant":
            if base_version and f"`{base_version}`" not in body:
                problems.append(f"BAD {SERIES_SECTION}: the base version `{base_version}` (BASE_VERSION) is not named")
            if not SHA_SHAPE.search(body):
                problems.append(f"BAD {SERIES_SECTION}: no frozen base commit (7-40 hex in backticks)")
    heading = find(found, "跨變體借用")
    if heading is not None and found[heading].strip():
        body = found[heading].strip()
        if BORROW_HEADER not in body and not body.startswith("無"):
            problems.append(f"BAD 跨變體借用: the table `{BORROW_HEADER}` or 無")
    return problems


def check(repo, rev=None, kind=None):
    """(kind, problems); raises Invalid when there is nothing to check."""
    text = read(repo, rev, "README.md")
    if text is None:
        raise Invalid("no README.md" + (f" at {rev}" if rev else f" in {repo}"))
    base_version = read(repo, rev, "BASE_VERSION")
    kind = kind or ("variant" if base_version is not None else "base")
    return kind, problems_of(text, kind, (base_version or "").strip())


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the checkout (default: current folder)")
    ap.add_argument("--rev", help="check README.md of this commit instead of the working tree")
    ap.add_argument("--kind", choices=("base", "variant"), help="default: variant when BASE_VERSION exists")
    a = ap.parse_args(argv)
    try:
        kind, problems = check(a.repo, a.rev, a.kind)
    except Invalid as error:
        print(f"README_CHECK: INVALID {error}")
        return 2
    for problem in problems:
        print(problem)
    where = f"rev {a.rev}" if a.rev else "working tree"
    if problems:
        print(f"README_CHECK: FAIL kind={kind} problems={len(problems)} ({where})")
        return 1
    print(f"README_CHECK: PASS kind={kind} ({where})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

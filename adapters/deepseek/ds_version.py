r"""dsh version rule (3.0.0-ds.8, PO 2026-11-28): the -ds.N serial continues from the last dsh release and never
starts again at 1 when the base version changes (2.6.0-ds.7 -> 3.0.0-ds.8, never 3.0.0-ds.1).

  python -I -X utf8 adapters/deepseek/ds_version.py check [--repo DIR] [--head] [--remote NAME]
  python -I -X utf8 adapters/deepseek/ds_version.py next  [--repo DIR]

check  VERSION is <BASE_VERSION>-ds.<N> (BASE_VERSION: the base version this variant is a copy of), the first
       `## ` heading of CHANGELOG.md is that version, and N is above every other ds serial: the `## <x.y.z>-ds.<n>`
       headings of CHANGELOG.md and the tags v<x.y.z>-ds.<n> (local tags; with --remote also the remote's, read with
       git ls-remote). --head reads VERSION, BASE_VERSION and CHANGELOG.md from HEAD (what release_ds.py releases)
       instead of the working tree. A serial that skips numbers is a note, not a failure.
next   prints the next version: <BASE_VERSION>-ds.<highest serial + 1>.

The base tools/release.py compares (upstream version, serial) as one pair, so it alone would let 3.0.0-ds.1 follow
2.6.0-ds.7; release_ds.py runs this check first. Last line `DS_VERSION: PASS|FAIL|INVALID ...`. Exit 0 PASS, 1 FAIL,
2 INVALID (a file missing or unreadable, git not usable: no result is never a pass). Standard library only; reads only.
"""
import argparse
import pathlib
import re
import subprocess
import sys

SHAPE = re.compile(r"^(\d+\.\d+\.\d+)-ds\.(\d+)$")
HEADING = re.compile(r"^##[ \t]+v?(\d+\.\d+\.\d+)-ds\.(\d+)(?=[（(\s]|$)", re.M)
TOP = re.compile(r"^##[ \t]+v?(\S+?)(?:[（(\s]|$)", re.M)
TAG = re.compile(r"^v?(\d+\.\d+\.\d+)-ds\.(\d+)$")


class Invalid(Exception):
    pass


def git(repo, *args):
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Invalid(f"git {args[0]}: {error}") from None
    if done.returncode != 0:
        raise Invalid(f"git {args[0]}: {done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout.decode("utf-8", "replace")


def read(repo, name, head):
    if head:
        return git(repo, "show", f"HEAD:{name}")
    path = pathlib.Path(repo) / name
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise Invalid(f"{name}: {error}") from None


def tag_serials(repo, remote=None):
    names = git(repo, "tag", "--list").split()
    if remote:
        for line in git(repo, "ls-remote", "--tags", remote).splitlines():
            ref = line.partition("\t")[2].replace("refs/tags/", "")
            names.append(ref[:-3] if ref.endswith("^{}") else ref)
    found = {}
    for name in names:
        m = TAG.match(name.strip())
        if m:
            found[name.strip()] = int(m.group(2))
    return found


def check(repo, head=False, remote=None):
    """(status, lines)."""
    version = read(repo, "VERSION", head).strip()
    base = read(repo, "BASE_VERSION", head).strip()
    changelog = read(repo, "CHANGELOG.md", head)
    lines, problems = [], []
    m = SHAPE.match(version)
    if not m:
        return "FAIL", [f"  - VERSION {version!r} is not <x.y.z>-ds.<N>"]
    upstream, serial = m.group(1), int(m.group(2))
    if upstream != base:
        problems.append(f"VERSION {version} does not start with BASE_VERSION {base} (write {base}-ds.<N>)")
    top = TOP.search(changelog)
    if not top or top.group(1) != version:
        problems.append(f"the first CHANGELOG.md heading is {top.group(1) if top else 'missing'}, not {version}")
    older = {f"CHANGELOG {u}-ds.{n}": int(n) for u, n in HEADING.findall(changelog) if f"{u}-ds.{n}" != version}
    for name, n in tag_serials(repo, remote).items():
        if TAG.match(name) and f"{TAG.match(name).group(1)}-ds.{n}" != version:
            older[f"tag {name}"] = n
    previous = max(older.values(), default=0)
    if serial <= previous:
        where = ", ".join(sorted(k for k, v in older.items() if v >= serial))
        problems.append(f"serial ds.{serial} is not above ds.{previous} ({where}); the serial continues and never "
                        f"starts again (next: {base}-ds.{previous + 1})")
    elif serial > previous + 1:
        lines.append(f"  ~ note: ds.{serial} skips from ds.{previous} (fine, but check it is meant)")
    lines += [f"  - {p}" for p in problems]
    lines.append(f"  version={version} base={base} serial={serial} previous={previous} "
                 f"compared={len(older)} ({'HEAD' if head else 'working tree'}{', remote ' + remote if remote else ''})")
    return ("FAIL" if problems else "PASS"), lines


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="VERSION is BASE_VERSION-ds.N with N above every earlier ds serial")
    c.add_argument("--repo", default=".")
    c.add_argument("--head", action="store_true", help="read the files from HEAD, not the working tree")
    c.add_argument("--remote", help="also compare the tags of this remote (git ls-remote)")
    n = sub.add_parser("next", help="print the next version")
    n.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "next":
            base = read(a.repo, "BASE_VERSION", False).strip()
            serials = [int(s) for _, s in HEADING.findall(read(a.repo, "CHANGELOG.md", False))]
            serials += list(tag_serials(a.repo).values())
            print(f"{base}-ds.{max(serials, default=0) + 1}")
            return 0
        state, lines = check(a.repo, a.head, a.remote)
    except Invalid as error:
        print(f"DS_VERSION: INVALID {error}")
        return 2
    print("\n".join(lines))
    print(f"DS_VERSION: {state}")
    return 0 if state == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

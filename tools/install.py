"""Install or upgrade the rules' tools/ in a project's DIRECTOR/tools/ (DIRECTOR-WORK 3.0.0, item C7 of the series plan).

  python -I -X utf8 tools/install.py manifest [--rules DIR] [--json]
  python -I -X utf8 tools/install.py install --to DIRECTOR/tools [--rules DIR] [--skip-optional] [--execute]
  python -I -X utf8 tools/install.py check --to DIRECTOR/tools

manifest  the versioned file list: VERSION of the rules checkout and every file under its tools/ with its size and
          SHA-256 (caches left out). tools/base_sync_check.py (in the base since 3.0.0 B6): base_sync_check reads
          the same list (install.manifest), so an install and a sync check do not disagree about what the base holds
          (review 5-1). 3.0.0 B11: a file only one platform uses carries "optional": "<platform>: <what for>" (the
          OPTIONAL table below); the text listing marks it `optional`.
install   a dry run by default: ADD / UPDATE / REMOVE / SAME per file, `~ EDITED` for an installed file changed
          since the last install, `~ LOCAL` for a file the project added (kept). --execute:
            1. takes the lock folder <to>.install.lock (mkdir; a second install prints BUSY and changes nothing);
            2. puts the new folder together in <to>.staging-<time> and checks every copied file against the list;
            3. renames the old folder to <to>.bak-<old version>-<time> and checks the backup holds every old file
               unchanged (the old folder is never edited in place);
            4. renames the staging folder to <to> and writes INSTALL_MANIFEST.json there.
          A failure in 3 or 4 puts the old folder back. Nothing to change prints `INSTALL: OK` and makes no backup.
          --skip-optional (3.0.0 B11): leave the optional files out (a platform that does not use them); the record
          lists them under "skipped_optional", and one installed before is removed (REMOVE, the backup keeps it).
check     every file INSTALL_MANIFEST.json lists is there with its size and SHA-256 (MISSING / CHANGED); files the
          project added are notes. NOT_INSTALLED (exit 2) without an install record.

--rules defaults to the folder above this file (the rules checkout). Writing hooks into a platform's settings is
not done here: each platform's adapter does that and keeps the user's own hook entries.
Last line INSTALL: DRY_RUN|DONE|OK|BUSY|FAIL or INSTALL_CHECK: PASS|FAIL|NOT_INSTALLED; exit 0 / 1 / 2 (cannot run).
Standard library only.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sys

_spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

SCHEMA = "dw-install/1"
RECORD = "INSTALL_MANIFEST.json"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = (".pyc", ".pyo")
# 3.0.0 B11 (audit CROSS_VARIANT_AUDIT_300 B11, plan W3): tools/ files only one platform uses. They stay in the base
# (byte for byte where a variant carries them); a variant that does not use them may leave them out: install
# --skip-optional, base_sync_check prints OPTIONAL instead of MISSING, selftest skips the groups that need them.
# Not here on purpose: setup_project_settings.py (setup_check.py reads its CONFIG_VERSION / MODES / PROFILES for every
# platform) and guard_rules.json (setup_project_settings.py reads it).
OPTIONAL = {
    "hook_guard.py": "claude: the Claude Code PreToolUse hook",
    "transcript_audit.py": "claude: rebuilds an action log from Claude Code transcripts (loop_guard --transcript)",
    "context_probe.py": "claude: probes a Claude Code session's fixed context cost",
    "browser_check.py": "claude: headless Chrome checks of templates/choice_page.html (the Claude choice page)",
}


class CannotRun(Exception):
    """exit 2"""


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def files_of(folder, skip=(RECORD,)):
    """[{path, bytes, sha256}] for every file under folder (paths with /, sorted); caches and `skip` left out."""
    folder = pathlib.Path(folder)
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = pathlib.Path(dirpath) / name
            rel = full.relative_to(folder).as_posix()
            if name.endswith(SKIP_SUFFIXES) or rel in skip:
                continue
            out.append({"path": rel, "bytes": full.stat().st_size, "sha256": digest(full)})
    return sorted(out, key=lambda f: f["path"])


def manifest(rules):
    """The versioned file list of a rules checkout: {schema, version, source, files}."""
    rules = pathlib.Path(rules)
    version_file = rules / "VERSION"
    if not version_file.is_file():
        raise CannotRun(f"no VERSION in {rules}: --rules must be a rules checkout")
    if not (rules / "tools").is_dir():
        raise CannotRun(f"no tools/ folder in {rules}")
    files = files_of(rules / "tools")
    for item in files:  # 3.0.0 B11
        if item["path"] in OPTIONAL:
            item["optional"] = OPTIONAL[item["path"]]
    return {"schema": SCHEMA, "version": version_file.read_text(encoding="utf-8-sig").strip(), "source": "tools",
            "files": files}


def read_record(to):
    path = pathlib.Path(to) / RECORD
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else None


def plan(new, to):
    """(rows, counts, local): what an install of manifest `new` would do to folder `to`."""
    to = pathlib.Path(to)
    have = {f["path"]: f for f in files_of(to)} if to.is_dir() else {}
    old = read_record(to) if to.is_dir() else None
    installed = {f["path"]: f for f in (old or {}).get("files", [])}
    want = {f["path"]: f for f in new["files"]}
    rows, counts = [], {"add": 0, "update": 0, "remove": 0, "same": 0, "local": 0}
    for path in sorted(set(want) | set(installed)):
        if path in want and path not in have:
            rows.append(("ADD   ", path))
            counts["add"] += 1
        elif path in want and have[path]["sha256"] != want[path]["sha256"]:
            rows.append(("UPDATE", path))
            counts["update"] += 1
        elif path in want:
            counts["same"] += 1
        elif path in have:
            rows.append(("REMOVE", path))
            counts["remove"] += 1
    notes = [f"~ EDITED {p} (changed since the last install; the backup keeps it)" for p in sorted(installed)
             if p in have and have[p]["sha256"] != installed[p]["sha256"]]
    local = sorted(p for p in have if p not in want and p not in installed)
    counts["local"] = len(local)
    notes += [f"~ LOCAL {p} (kept)" for p in local]
    return rows, counts, notes, local, old


def take_lock(lock):
    try:
        os.mkdir(lock)
        return True
    except FileExistsError:
        return False


def same_tree(folder, expected):
    """True when folder holds every expected file ({path: sha256}) unchanged."""
    folder = pathlib.Path(folder)
    for path, sha in expected.items():
        full = folder / path
        if not full.is_file() or digest(full) != sha:
            return False
    return True


def install(rules, to, execute=False, skip_optional=False):
    """(exit, lines). skip_optional (3.0.0 B11): leave the OPTIONAL files out."""
    new = manifest(rules)
    if skip_optional:
        new["skipped_optional"] = [f["path"] for f in new["files"] if f.get("optional")]
        new["files"] = [f for f in new["files"] if not f.get("optional")]
    to = pathlib.Path(to).resolve()
    rules = pathlib.Path(rules).resolve()
    rows, counts, notes, local, old = plan(new, to)
    lines = [f"{tag} {path}" for tag, path in rows] + notes
    summary = " ".join(f"{k}={v}" for k, v in counts.items())
    changed = counts["add"] + counts["update"] + counts["remove"]
    if not changed and old is not None and old.get("version") == new["version"]:
        return 0, lines + [f"INSTALL: OK nothing to change version={new['version']} files={len(new['files'])}"]
    if not execute:
        return 0, lines + [f"INSTALL: DRY_RUN {summary} version={new['version']} (add --execute to install)"]
    lock = to.parent / (to.name + ".install.lock")
    to.parent.mkdir(parents=True, exist_ok=True)
    if not take_lock(lock):
        return 1, lines + [f"INSTALL: BUSY {lock} exists: another install is running; run again after it ends "
                           "(remove the folder only when no install is running)"]
    try:
        return _install_locked(new, rules, to, lines, local)
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


def _install_locked(new, rules, to, lines, local):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    staging = to.parent / f"{to.name}.staging-{stamp}"
    try:
        for item in new["files"]:
            dest = staging / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rules / "tools" / item["path"], dest)
            if digest(dest) != item["sha256"] or dest.stat().st_size != item["bytes"]:
                raise OSError(f"{item['path']} changed while it was copied")
        for path in local:
            dest = staging / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(to / path, dest)
        record = dict(new, installed=datetime.datetime.now().isoformat(timespec="seconds"))
        common.write_json_atomic(staging / RECORD, record)
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        return 1, lines + [f"INSTALL: FAIL staging: {error}; {to} not changed"]
    backup = None
    if to.exists():
        old = read_record(to)
        before = {f["path"]: f["sha256"] for f in files_of(to, skip=())}
        backup = to.parent / f"{to.name}.bak-{(old or {}).get('version', 'unknown')}-{stamp}"
        try:
            os.replace(to, backup)
        except OSError as error:
            shutil.rmtree(staging, ignore_errors=True)
            return 1, lines + [f"INSTALL: FAIL backup: {error}; {to} not changed"]
        if not same_tree(backup, before):
            os.replace(backup, to)
            shutil.rmtree(staging, ignore_errors=True)
            return 1, lines + [f"INSTALL: FAIL the backup {backup} does not match the old folder; {to} put back"]
        lines.append(f"BACKUP: {backup} files={len(before)} verified")
    try:
        os.replace(staging, to)
    except OSError as error:
        if backup is not None:
            os.replace(backup, to)
        return 1, lines + [f"INSTALL: FAIL activate: {error}; the old folder is back, staging left at {staging}"]
    return 0, lines + [f"INSTALL: DONE version={new['version']} files={len(new['files'])} to={to}"]


def check(to):
    """(exit, lines)."""
    to = pathlib.Path(to)
    record = read_record(to)
    if record is None:
        return 2, [f"INSTALL_CHECK: NOT_INSTALLED no {RECORD} in {to}"]
    lines, bad = [], 0
    listed = {f["path"]: f for f in record.get("files", [])}
    for path, item in sorted(listed.items()):
        full = to / path
        if not full.is_file():
            lines.append(f"MISSING {path}")
            bad += 1
        elif full.stat().st_size != item.get("bytes") or digest(full) != item.get("sha256"):
            lines.append(f"CHANGED {path}")
            bad += 1
    lines += [f"~ LOCAL {f['path']}" for f in files_of(to) if f["path"] not in listed]
    word = "FAIL" if bad else "PASS"
    return (1 if bad else 0), lines + [f"INSTALL_CHECK: {word} files={len(listed)} version={record.get('version')}"
                                       + (f" problems={bad}" if bad else "")]


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_rules = pathlib.Path(__file__).resolve().parent.parent
    m = sub.add_parser("manifest", help="the versioned file list of the rules' tools/")
    m.add_argument("--rules", default=default_rules)
    m.add_argument("--json", action="store_true")
    i = sub.add_parser("install", help="dry run; --execute installs or upgrades")
    i.add_argument("--rules", default=default_rules)
    i.add_argument("--to", required=True, help="the project's DIRECTOR/tools folder")
    i.add_argument("--execute", action="store_true")
    i.add_argument("--skip-optional", action="store_true",
                   help="3.0.0 B11: leave out the files only one platform uses (manifest marks them optional)")
    c = sub.add_parser("check", help="the installed files match the install record")
    c.add_argument("--to", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "manifest":
            data = manifest(a.rules)
            if a.json:
                print(json.dumps(data, ensure_ascii=False, indent=1))
            else:
                for f in data["files"]:
                    print(f"{f['sha256'][:16]} {f['bytes']:>8} {f['path']}" + ("  optional" if f.get("optional") else ""))
                optional = sum(1 for f in data["files"] if f.get("optional"))
                print(f"MANIFEST: version={data['version']} files={len(data['files'])} optional={optional}")
            return 0
        code, lines = install(a.rules, a.to, a.execute, a.skip_optional) if a.cmd == "install" else check(a.to)
    except CannotRun as error:
        print(f"INSTALL: FAIL {error}")
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())

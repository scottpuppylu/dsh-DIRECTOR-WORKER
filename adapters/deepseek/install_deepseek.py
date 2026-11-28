r"""Install or upgrade the DeepSeek Harness adapter in a project's DIRECTOR/ (dsh-DIRECTOR-WORKER 3.0.0-ds.8).

  python -I -X utf8 adapters/deepseek/install_deepseek.py install --to <REPO>/DIRECTOR [--rules DIR] [--execute]
  python -I -X utf8 adapters/deepseek/install_deepseek.py check   --to <REPO>/DIRECTOR

The base tools go in first, with the base installer (it is not run from here):
  python -I -X utf8 <rules>/tools/install.py install --to <REPO>/DIRECTOR/tools --execute
This tool then puts the adapter folder adapters/deepseek/ of the rules checkout into <REPO>/DIRECTOR/adapters/deepseek/,
the same layout as the rules checkout: the DSH tools find the base tools two folders up (DIRECTOR/tools/).

install   a dry run by default (ADD / UPDATE / REMOVE per file, `~ EDITED`, `~ LOCAL`), the base install.py rules and
          code: --execute takes the lock folder deepseek.install.lock, puts the new folder together in a staging folder
          and checks every copied file's SHA-256, moves the old folder to deepseek.bak-<old version>-<time> and checks
          the backup, then puts the staging folder in place and writes INSTALL_MANIFEST.json (schema dw-install/1, so
          `tools/install.py check --to <REPO>/DIRECTOR/adapters/deepseek` reads it too). A failure puts the old folder
          back. A file the project added to the folder is kept.
check     the adapter files are there with their size and SHA-256 (MISSING / CHANGED), and the base tools folder
          <to>/tools has its own install record and passes tools/install.py check: a DSH tool without the base tools
          cannot run.
--rules defaults to the checkout two folders above this file. Nothing outside <to>/adapters/ is written.
Last line INSTALL_DEEPSEEK: DRY_RUN|DONE|OK|BUSY|FAIL or INSTALL_DEEPSEEK_CHECK: PASS|FAIL|NOT_INSTALLED;
exit 0 / 1 / 2 (cannot run: no rules checkout, no base installer). Standard library only.
"""
import argparse
import datetime
import importlib.util
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ADAPTER = "adapters/deepseek"


class CannotRun(Exception):
    """exit 2"""


def base_install(rules):
    """The base tools/install.py of the rules checkout, loaded by path (its digest, plan and record code)."""
    path = pathlib.Path(rules) / "tools" / "install.py"
    if not path.is_file():
        raise CannotRun(f"no tools/install.py in {rules}: --rules must be a dsh-DIRECTOR-WORKER checkout")
    spec = importlib.util.spec_from_file_location("dsh_install_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(rules, base):
    rules = pathlib.Path(rules)
    source = rules / ADAPTER
    if not (rules / "VERSION").is_file() or not source.is_dir():
        raise CannotRun(f"no VERSION or {ADAPTER}/ in {rules}")
    return {"schema": base.SCHEMA, "version": (rules / "VERSION").read_text(encoding="utf-8-sig").strip(),
            "source": ADAPTER, "files": base.files_of(source)}


def install(rules, to, execute=False):
    """(exit, lines)."""
    base = base_install(rules)
    new = manifest(rules, base)
    target = (pathlib.Path(to) / ADAPTER).resolve()
    source = (pathlib.Path(rules) / ADAPTER).resolve()
    rows, counts, notes, local, old = base.plan(new, target)
    lines = [f"{tag} {path}" for tag, path in rows] + notes
    if not (pathlib.Path(to) / "tools" / base.RECORD).is_file():
        lines.append(f"~ the base tools are not installed in {pathlib.Path(to) / 'tools'}: run tools/install.py "
                     "install --to <REPO>/DIRECTOR/tools --execute first (check fails without them)")
    summary = " ".join(f"{k}={v}" for k, v in counts.items())
    if not counts["add"] + counts["update"] + counts["remove"] and old is not None and old.get("version") == new["version"]:
        return 0, lines + [f"INSTALL_DEEPSEEK: OK nothing to change version={new['version']} files={len(new['files'])}"]
    if not execute:
        return 0, lines + [f"INSTALL_DEEPSEEK: DRY_RUN {summary} version={new['version']} (add --execute to install)"]
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / (target.name + ".install.lock")
    if not base.take_lock(lock):
        return 1, lines + [f"INSTALL_DEEPSEEK: BUSY {lock} exists: another install is running"]
    try:
        return locked(base, new, source, target, lines, local)
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


def locked(base, new, source, target, lines, local):
    """The base _install_locked steps with the adapter folder as the source (stage, verify, back up, activate)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    staging = target.parent / f"{target.name}.staging-{stamp}"
    try:
        for item in new["files"]:
            dest = staging / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / item["path"], dest)
            if base.digest(dest) != item["sha256"] or dest.stat().st_size != item["bytes"]:
                raise OSError(f"{item['path']} changed while it was copied")
        for path in local:
            dest = staging / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / path, dest)
        record = dict(new, installed=datetime.datetime.now().isoformat(timespec="seconds"))
        base.common.write_json_atomic(staging / base.RECORD, record)
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        return 1, lines + [f"INSTALL_DEEPSEEK: FAIL staging: {error}; {target} not changed"]
    backup = None
    if target.exists():
        old = base.read_record(target)
        before = {f["path"]: f["sha256"] for f in base.files_of(target, skip=())}
        backup = target.parent / f"{target.name}.bak-{(old or {}).get('version', 'unknown')}-{stamp}"
        try:
            os.replace(target, backup)
        except OSError as error:
            shutil.rmtree(staging, ignore_errors=True)
            return 1, lines + [f"INSTALL_DEEPSEEK: FAIL backup: {error}; {target} not changed"]
        if not base.same_tree(backup, before):
            os.replace(backup, target)
            shutil.rmtree(staging, ignore_errors=True)
            return 1, lines + [f"INSTALL_DEEPSEEK: FAIL the backup {backup} does not match the old folder; put back"]
        lines.append(f"BACKUP: {backup} files={len(before)} verified")
    try:
        os.replace(staging, target)
    except OSError as error:
        if backup is not None:
            os.replace(backup, target)
        return 1, lines + [f"INSTALL_DEEPSEEK: FAIL activate: {error}; the old folder is back, staging left at {staging}"]
    return 0, lines + [f"INSTALL_DEEPSEEK: DONE version={new['version']} files={len(new['files'])} to={target}"]


def check(to, rules):
    """(exit, lines): the adapter record, then the base tools record (both must pass)."""
    base = base_install(rules)
    code, lines = base.check(pathlib.Path(to) / ADAPTER)
    lines = [line.replace("INSTALL_CHECK:", "adapter:") for line in lines]
    tools_code, tools_lines = base.check(pathlib.Path(to) / "tools")
    lines.append("base tools: " + tools_lines[-1].replace("INSTALL_CHECK: ", ""))
    if code == 2:
        return 2, lines + [f"INSTALL_DEEPSEEK_CHECK: NOT_INSTALLED no {base.RECORD} in {pathlib.Path(to) / ADAPTER}"]
    if code != 0 or tools_code != 0:
        return 1, lines + ["INSTALL_DEEPSEEK_CHECK: FAIL" + ("" if tools_code == 0 else
                                                             " (the base tools must be installed and unchanged too)")]
    return 0, lines + ["INSTALL_DEEPSEEK_CHECK: PASS"]


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("install", "check"):
        p = sub.add_parser(name)
        p.add_argument("--to", required=True, help="the project's DIRECTOR folder")
        p.add_argument("--rules", default=str(HERE.parent.parent), help="the rules checkout (default: two folders up)")
        if name == "install":
            p.add_argument("--execute", action="store_true", help="really install (default: dry run)")
    a = ap.parse_args(argv)
    try:
        code, lines = install(a.rules, a.to, a.execute) if a.cmd == "install" else check(a.to, a.rules)
    except CannotRun as error:
        word = "INSTALL_DEEPSEEK" if a.cmd == "install" else "INSTALL_DEEPSEEK_CHECK"
        print(f"{word}: FAIL cannot run: {error}")
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())

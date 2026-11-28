#!/usr/bin/env python3
"""Base sync check (plan 6.1 and C7; written in cld 3.0.0-cld.1, in the base since 3.0.0 B6 so every variant runs the
same one): a variant is the base copied byte for byte plus its adapter.

  python -I -X utf8 tools/base_sync_check.py --base <checkout of the base at BASE_VERSION> [--variant .]
                                             [--registry adapters/<platform>/BASE_SYNC.json]

--variant defaults to the current folder; --registry to the one adapters/*/BASE_SYNC.json of the variant (none, or
more than one, cannot run: name it).

Every file of the base (all of the checkout but .git; caches left out as install.py leaves them out, tools/ read with
install.py's own manifest) must be in the variant with the same bytes (CRLF read as LF), unless the registry lists it:
  overrides    {path: {"why": reason, "base_sha256": hex}}  the variant changed this base file on purpose; the reason
               is required, the README must name the file (`path`), and a listed file that is the same as the base is
               STALE (take it out). base_sha256 is the base file (CRLF read as LF) the override was last reviewed
               against: when the base file changes, OVERRIDE_STALE「覆寫已過期，要重新審」(review P1-8) until someone
               ports the base change into the override and records the new sha256 the line prints
  not_ported   {path: reason}  a base file the variant leaves out (README 拿掉 / NOT_PORTED)
  variant_files {path: reason} files only the variant has outside its adapter folder (BASE_VERSION...)
  variant_rules {name: text}  steps the variant adds around base files it does not change (e.g. the beginner
               fast path running hooks.py before the first question): documentation, a text is required
  adapter      the variant's own folder (adapters/<platform>/); every file there is the variant's
3.0.0 B11: a base tools/ file install.py marks optional (OPTIONAL: hook_guard.py, transcript_audit.py,
context_probe.py, browser_check.py - only Claude uses them) may be left out without a not_ported entry: line
`OPTIONAL <path> (<what for>)`, not MISSING. A variant that carries one carries it unchanged (or as an override).
Also: BASE_VERSION = the base's VERSION, the variant's VERSION is BASE_VERSION-<label>.<n> (release.py compares the
whole), and CHANGELOG-upstream.md is the base's CHANGELOG.md (a byte copy).

Lines: SAME (count only) / OVERRIDE / ADDED / NOT_PORTED / OPTIONAL, problems as MISSING / CHANGED (a base file differs and is not
an override) / EXTRA (a variant file outside the adapter, not listed) / STALE / OVERRIDE_STALE / REGISTRY / VERSION /
UPSTREAM / README.
Last line `BASE_SYNC: PASS|FAIL base=<v> variant=<v> same=N overrides=N added=N problems=N`; exit 0 / 1 / 2 (cannot
run: no VERSION, no registry, a registry that is not the schema). No release while it fails. Standard library only.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

SCHEMA = "dw-base-sync/1"


class CannotRun(Exception):
    """exit 2"""


def load_install(variant):
    path = pathlib.Path(variant) / "tools" / "install.py"
    try:
        spec = importlib.util.spec_from_file_location("dw_install", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as error:
        raise CannotRun(f"cannot load {path} (and the _common.py it needs): {error}")
    return module


def listing(root, install):
    """{path: normalized bytes} of every file under root but .git, with install.py's skip rules; tools/ must give the
    same list as install.py manifest."""
    root = pathlib.Path(root)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in install.SKIP_DIRS and not (pathlib.Path(dirpath) == root and d == ".git"))
        for name in sorted(filenames):
            full = pathlib.Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if name.endswith(install.SKIP_SUFFIXES) or rel == ".git":
                continue
            out[rel] = full.read_bytes().replace(b"\r\n", b"\n")
    try:
        tools = sorted(f"tools/{f['path']}" for f in install.manifest(root)["files"])
    except install.CannotRun as error:  # no VERSION / no tools/: not a rules checkout
        raise CannotRun(str(error))
    if tools != sorted(p for p in out if p.startswith("tools/")):
        raise CannotRun(f"{root}: tools/ walk and install.py manifest disagree")
    return out


def version(root):
    path = pathlib.Path(root) / "VERSION"
    if not path.is_file():
        raise CannotRun(f"no VERSION in {root}")
    return path.read_text(encoding="utf-8-sig").strip()


def read_registry(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CannotRun(f"registry {path}: {error}")
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("adapter"), str):
        raise CannotRun(f"registry {path}: not {SCHEMA} with an adapter folder")
    for key in ("overrides", "not_ported", "variant_files", "variant_rules"):
        if not isinstance(data.get(key, {}), dict):
            raise CannotRun(f"registry {path}: {key} is not an object")
    return data


def find_registry(variant):
    """The one adapters/*/BASE_SYNC.json of the variant."""
    found = sorted((pathlib.Path(variant) / "adapters").glob("*/BASE_SYNC.json"))
    if len(found) != 1:
        raise CannotRun(f"{len(found)} adapters/*/BASE_SYNC.json in {variant}: give --registry")
    return found[0]


def check(base, variant, registry):
    """(lines, problems, counts)."""
    install = load_install(variant)
    reg = read_registry(registry)
    adapter = reg["adapter"].rstrip("/") + "/"
    gone, extra, rules = reg.get("not_ported", {}), reg.get("variant_files", {}), reg.get("variant_rules", {})
    overrides, recorded = {}, {}
    for path, entry in reg.get("overrides", {}).items():
        entry = entry if isinstance(entry, dict) else {"why": entry}
        overrides[path], recorded[path] = entry.get("why"), entry.get("base_sha256")
    b, v = listing(base, install), listing(variant, install)
    lines, bad = [], []
    counts = {"same": 0, "overrides": 0, "added": 0, "optional": 0}
    optional = getattr(install, "OPTIONAL", {})  # 3.0.0 B11
    readme = v.get("README.md", b"").decode("utf-8", errors="replace")
    for path, why in sorted({**overrides, **gone, **extra, **rules}.items()):
        if not isinstance(why, str) or not why.strip():
            bad.append(f"REGISTRY    {path}: no reason")
    for path in sorted(b):
        if path in gone:
            (bad.append(f"STALE       {path}: listed as not ported but the variant has it") if path in v
             else lines.append(f"NOT_PORTED  {path} ({gone[path]})"))
        elif path not in v and path[len("tools/"):] in optional and path.startswith("tools/"):
            counts["optional"] += 1  # 3.0.0 B11
            lines.append(f"OPTIONAL    {path} (not carried; {optional[path[len('tools/'):]]})")
        elif path not in v:
            bad.append(f"MISSING     {path}: a base file the variant does not have (not in not_ported)")
        elif v[path] == b[path]:
            if path in overrides:
                bad.append(f"STALE       {path}: listed as an override but the same as the base")
            else:
                counts["same"] += 1
        elif path in overrides:
            counts["overrides"] += 1
            lines.append(f"OVERRIDE    {path} ({overrides[path]})")
            now = hashlib.sha256(b[path]).hexdigest()
            if not isinstance(recorded[path], str) or not recorded[path]:
                bad.append(f"REGISTRY    {path}: an override without base_sha256 (the base file now: {now})")
            elif recorded[path].lower() != now:
                bad.append(f"OVERRIDE_STALE {path}: 覆寫已過期，要重新審 (the base file changed since the override was "
                           f"reviewed: recorded {recorded[path][:12]}, now {now}; port the change, then record it)")
            if f"`{path}`" not in readme:
                bad.append(f"README      {path}: an override the README does not name")
        else:
            bad.append(f"CHANGED     {path}: differs from the base and is not a registered override")
    for path in sorted(set(v) - set(b)):
        if path.startswith(adapter) or path in extra:
            counts["added"] += 1
            lines.append(f"ADDED       {path}")
        else:
            bad.append(f"EXTRA       {path}: only in the variant, outside {adapter} and not in variant_files")
    for path in sorted(set(overrides) - set(b)):
        bad.append(f"STALE       {path}: an override of a file the base does not have")
    base_v, var_v = version(base), version(variant)
    listed = (v.get("BASE_VERSION") or b"").decode("utf-8", errors="replace").strip()
    if listed != base_v:
        bad.append(f"VERSION     BASE_VERSION is {listed or 'missing'}, the base is {base_v}")
    if not re.fullmatch(re.escape(base_v) + r"-[a-z]+\.[1-9]\d*", var_v):
        bad.append(f"VERSION     VERSION {var_v} is not {base_v}-<label>.<n>")
    if v.get("CHANGELOG-upstream.md") != b.get("CHANGELOG.md"):
        bad.append("UPSTREAM    CHANGELOG-upstream.md is not a copy of the base CHANGELOG.md")
    return lines, bad, counts, base_v, var_v


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="a checkout of the base at BASE_VERSION")
    ap.add_argument("--variant", default=".", help="the variant checkout (default: the current folder)")
    ap.add_argument("--registry", help="default: the one adapters/*/BASE_SYNC.json of the variant")
    a = ap.parse_args(argv)
    try:
        lines, bad, counts, base_v, var_v = check(a.base, a.variant, a.registry or find_registry(a.variant))
    except CannotRun as error:
        print(f"base_sync_check: {error}")
        print("BASE_SYNC: FAIL (cannot run)")
        return 2
    for line in lines + bad:
        print(line)
    print(f"BASE_SYNC: {'FAIL' if bad else 'PASS'} base={base_v} variant={var_v} same={counts['same']} "
          f"overrides={counts['overrides']} added={counts['added']} problems={len(bad)}"
          + (f" optional={counts['optional']}" if counts["optional"] else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

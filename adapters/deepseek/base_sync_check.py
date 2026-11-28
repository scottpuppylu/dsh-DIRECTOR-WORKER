#!/usr/bin/env python3
"""Base sync check, DeepSeek adapter entry (3.0.0-ds.8). Since base 3.0.0 B6 the check itself is the base's
tools/base_sync_check.py (one copy for every variant); this file only keeps the old path working and fills in this
variant's defaults:

  python -I -X utf8 adapters/deepseek/base_sync_check.py --base <checkout of the base at BASE_VERSION> [--variant .]
                                                       [--registry adapters/deepseek/BASE_SYNC.json]

--variant defaults to the checkout holding this file, --registry to BASE_SYNC.json beside it. Everything else
(lines, exit codes, the BASE_SYNC line) is the base tool's; see its docstring.
"""
import pathlib
import runpy
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TOOL = ROOT / "tools" / "base_sync_check.py"


def given(args, flag):
    return any(a == flag or a.startswith(flag + "=") for a in args)


def main():
    args = sys.argv[1:]
    if not given(args, "--variant"):
        args += ["--variant", str(ROOT)]
    if not given(args, "--registry"):
        args += ["--registry", str(HERE / "BASE_SYNC.json")]
    if not TOOL.is_file():
        sys.stdout.write(f"BASE_SYNC: INVALID {TOOL} is missing (base 3.0.0 B6 tools/base_sync_check.py)\n")
        return 2
    sys.argv = [str(TOOL)] + args
    try:
        runpy.run_path(str(TOOL), run_name="__main__")
    except SystemExit as done:
        return done.code if isinstance(done.code, int) else (0 if done.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

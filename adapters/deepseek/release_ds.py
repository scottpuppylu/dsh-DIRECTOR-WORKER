r"""Release dsh-DIRECTOR-WORKER (3.0.0-ds.8): the dsh checks first, then the base tools/release.py.

  python -I -X utf8 adapters/deepseek/release_ds.py --base BASE [--repo DIR] [--config FILE] [release.py options]

Steps (each a separate process; a step with no exit code, a timeout or a code other than 0 stops the release):
  ds_version      adapters/deepseek/ds_version.py check --head --remote <remote>: VERSION at HEAD is
                  <BASE_VERSION>-ds.<N> and N is above every earlier ds serial (CHANGELOG headings, local and remote
                  tags). The base release.py alone would accept a serial that starts again.
  base_sync       adapters/deepseek/base_sync_check.py --base <BASE> --variant <repo>: every base file is a byte copy
                  or a registered override (BASE_SYNC.json); BASE_VERSION and CHANGELOG-upstream.md match the base.
                  --base (a checkout of the base at BASE_VERSION) is required.
  selftest_ds     adapters/deepseek/selftest_deepseek.py
  release         tools/release.py with the remaining options (dry run unless --execute; its own selftest step
                  runs the base tools/selftest.py)
Nothing is pushed, tagged or published without --execute, as in release.py. The remote is the "release" object's
"remote" in --config (default origin).
Ends with `RELEASE_DS: PASS|FAIL step=<name>`; exit = the release.py exit, or 1 when a dsh step stops it, 2 usage.
"""
import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def run(cmd, timeout):
    """Exit code or None (could not start, timed out, killed)."""
    try:
        done = subprocess.run(cmd, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"  ! {type(error).__name__}: {error}")
        return None
    code = done.returncode
    return code if isinstance(code, int) and not isinstance(code, bool) and code >= 0 else None


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(HERE.parent.parent))
    ap.add_argument("--config", help="director_work.json with a release object (remote, branch, ...)")
    ap.add_argument("--base", required=True, help="a checkout of the base at BASE_VERSION (base_sync_check --base)")
    ap.add_argument("--timeout", type=float, default=3600.0, help="seconds per dsh step (default 3600)")
    a, rest = ap.parse_known_args(argv)
    remote = "origin"
    if a.config:
        try:
            remote = (json.loads(pathlib.Path(a.config).read_text(encoding="utf-8-sig")).get("release") or {}).get(
                "remote") or "origin"
        except (OSError, ValueError, AttributeError) as error:
            print(f"RELEASE_DS: FAIL step=config ({error})")
            return 2
    py = [sys.executable, "-I", "-X", "utf8"]
    steps = (("ds_version", py + [str(HERE / "ds_version.py"), "check", "--repo", a.repo, "--head", "--remote", remote]),
             ("base_sync", py + [str(HERE / "base_sync_check.py"), "--base", a.base, "--variant", a.repo]),
             ("selftest_ds", py + [str(HERE / "selftest_deepseek.py")]))
    for name, cmd in steps:
        code = run(cmd, a.timeout)
        print(f"STEP {name}: {'OK' if code == 0 else 'FAIL'} exit={code}")
        if code != 0:
            print(f"RELEASE_DS: FAIL step={name}")
            return 1
    release = py + [str(pathlib.Path(a.repo) / "tools" / "release.py"), "--repo", a.repo]
    release += (["--config", a.config] if a.config else []) + rest
    code = run(release, None)
    print(f"RELEASE_DS: {'PASS' if code == 0 else 'FAIL'} step=release exit={code}")
    return code if code is not None else 1


if __name__ == "__main__":
    sys.exit(main())

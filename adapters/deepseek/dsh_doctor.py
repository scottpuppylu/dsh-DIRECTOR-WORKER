r"""Environment / self-check for dsh-DIRECTOR-WORKER (dshdw), DIRECTOR-WORK on DeepSeek Harness (DSH).

Prints one line per check with OK / WARN / FAIL / NOT_VERIFIED and a final summary. Reads only; fixes nothing.

  python -I -X utf8 <REPO>/DIRECTOR/adapters/deepseek/dsh_doctor.py [--tools-dir DIR] [--sessions-root DIR] [--cache-root DIR]
      [--profile-config FILE] [--json]

Checks:
  python            version >= 3.9 (the tools use f-strings, pathlib, dataclass-free classes; 3.12 is the bundled one)
  node              a Node 22+ executable for zstd session logs (env DSH_NODE, the DSH runtime, then PATH)
  dsh_home          the DSH home (%USERPROFILE%\.dsh, env DSH_HOME)
  sessions_root     the session logs root, and how many logs it holds
  projection_cache  the plain-JSON projection cache used by dsh_usage.py (readable and the newest file parses)
  latest_session    the newest session log decodes and its header names a cwd (needs Node)
  profile            model / reasoning effort from profiles/desktop/cordis.patch.yml
  session_policy    sandbox mode and approval policy of the latest session (session-scoped, NOT a global setting)
  config            with --config: the project director_work.json reads; WARN with one line when it still has the
                    old "sdd" block (safety_gate.legacy_notes); NOT_VERIFIED without --config
  git               git on PATH (needed by the evidence / scope / trace tools, not by the DSH readers)
  tools             the required DSH-edition tools exist in tools/; removed Claude-only tools are gone
  docs / templates  the edition's docs and templates folders are present (WARN while they are being rewritten)

Exit codes: 0 no FAIL, 1 any FAIL, 2 the check itself cannot run. --json prints the checks as JSON.

2.3.0-ds.5 (upstream doctor.py 2.3.0; DS has no doctor.py, so the check lives here). 2.3.0 (N6) --licenses FILE: tool licenses and trials that run out. A tool stopped working mid-week because its license
had expired and nobody had looked at the date. FILE is JSON (a list of {"tool", "license", "expires": "YYYY-MM-DD"},
or {"licenses": [...]}) or a Markdown table with tool / license / expires columns. Fewer than --license-days (default
3) days left is `WARN license expiring: <license> (held by <tool>) expires <date>, <n> day(s) left`; past the date is
`WARN license expired`; an unreadable date is a WARN too. --licenses-only runs just this check (no git worktree
needed) and ends with `LICENSES: ok=n expiring=n expired=n bad=n`; exit 1 when any is expiring, expired or bad.
Without --licenses-only each license is one `licenses` check (OK, or WARN for expiring / expired / bad).
"""
import argparse
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys


def tool_file(name):
    """3.0.0-ds.8: a DSH tool lives in adapters/deepseek/, a shared one in the base tools/ two folders up
    (the same in the repo and in an installed DIRECTOR/); this folder first, then that one."""
    here = pathlib.Path(__file__).resolve().parent
    for folder in (here, here.parent.parent / "tools"):
        if (folder / name).is_file():
            return folder / name
    return here.parent.parent / "tools" / name


def load_local(name):
    """Load a sibling module (the tools are run with -I, so the script folder is not on sys.path)."""
    path = tool_file(name + ".py")
    spec = importlib_spec(name, path)
    module = importlib_module(spec)
    spec.loader.exec_module(module)
    return module


def importlib_spec(name, path):
    import importlib.util
    return importlib.util.spec_from_file_location(name, path)


def importlib_module(spec):
    import importlib.util
    return importlib.util.module_from_spec(spec)


dsh = load_local("dsh_session")

TOOL = "dsh_doctor"
# 3.0.0-ds.8: the DSH files are in adapters/deepseek/ (this folder); the shared tools are the base tools/ two folders
# up (repo and installed DIRECTOR/ alike). The Claude-only base tools (hook_guard.py ...) stay in the base copy: they
# are not run on DSH, and removing them would make the tools folder differ from the base.
ADAPTER_FILES = (
    "dsh_audit.py", "dsh_dispatch.py", "dsh_doctor.py", "dsh_guard.py", "dsh_session.py", "dsh_setup_check.py",
    "dsh_usage.py", "verify_dsh_run.py", "selftest_deepseek.py", "install_deepseek.py", "VERIFY_DSH_RUN.json",
    "DSH_EFFORT_TABLE.json", "VARIANT.json", "README.md",
)
REQUIRED_TOOLS = (
    "_common.py", "audit_log.py", "bootstrap_repo.py", "completion.py", "delete_guard.py", "dispatch_check.py",
    "evidence_record.py", "flag_check.py", "gate_check.py", "handoff.py", "hash_check.py", "inject_scan.py",
    "install.py", "line_brief.py", "loop_guard.py", "memory_size_check.py", "metrics_report.py", "pack_check.py",
    "pause_ctl.py", "pre_tr.py", "privacy_scan.py", "ran_line.py", "release.py", "report_vs_audit.py",
    "resume_archive.py", "resume_inject.py", "round_check.py", "ruler_check.py", "run_plan_check.py",
    "safety_gate.py", "scope_check.py", "secret_mask.py", "sim_check.py", "spec_gate.py", "status_gen.py",
    "trace_report.py", "waiver.py", "worktree.py", "vocabulary.json", "guard_rules.json",
)
ADAPTER_DIR = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parent.parent


def check_python():
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro} ({sys.executable})"
    if version < (3, 9):
        return "FAIL", f"{detail}; Python 3.9 or newer is required"
    return "OK", detail


def check_node():
    info = dsh.find_node_info()
    if info and info.get("ok"):
        return "OK", f"{info['path']} ({info['version']}, zstd ok)"
    if info and info.get("path"):
        return "FAIL", (f"{info['path']}: {info.get('reason') or 'unusable Node'} "
                        "(set DSH_NODE to a Node 22+ executable or install the DSH runtime under "
                        f"{dsh.dsh_home() / 'dsh-runtimes'})")
    return "FAIL", ("no Node 22+ found (set DSH_NODE or install the DSH runtime under "
                    f"{dsh.dsh_home() / 'dsh-runtimes'}); dsh_audit.py and the JSONL fallback need it")


def check_dsh_home():
    home = dsh.dsh_home()
    if home.is_dir():
        return "OK", str(home)
    return "FAIL", f"{home} not found; is DeepSeek Harness installed and has it run once? (env DSH_HOME overrides)"


def check_sessions(root):
    if not root.is_dir():
        return "FAIL", f"{root} not found (pass --sessions-root or set DSH_SESSIONS_ROOT)"
    try:
        sessions = dsh.list_session_files(root)
    except dsh.DshError as error:
        return "FAIL", str(error)
    if not sessions:
        return "WARN", f"{root} readable but holds no session logs yet"
    newest = max(sessions, key=lambda item: item.mtime)
    return "OK", f"{root} ({len(sessions)} session log(s); newest {newest.session_id})"


def check_projection_cache(root):
    if not root.is_dir():
        return "WARN", (f"{root} not found; dsh_usage.py will fall back to the JSONL logs (needs Node)")
    files = sorted(root.glob("*.json"))
    if not files:
        return "WARN", f"{root} readable but holds no projection files yet"
    newest = max(files, key=lambda path: path.stat().st_mtime)
    projection = dsh.read_projection(newest)
    if projection.error:
        return "FAIL", f"{root} ({len(files)} file(s)); newest {newest.name} does not parse: {projection.error}"
    return "OK", f"{root} ({len(files)} file(s); newest {newest.name} parses, projection version {projection.version})"


def check_latest_session(root, node_ok):
    if not root.is_dir():
        return "NOT_VERIFIED", "the sessions root is missing"
    try:
        sessions = dsh.list_session_files(root)
    except dsh.DshError as error:
        return "NOT_VERIFIED", str(error)
    if not sessions:
        return "NOT_VERIFIED", "no session logs to decode"
    if not node_ok:
        return "NOT_VERIFIED", "Node is missing, so the zstd session logs cannot be decoded"
    newest = max(sessions, key=lambda item: item.mtime)
    try:
        header, warnings = dsh.decode_header(newest.path)
    except dsh.DshError as error:
        return "FAIL", f"newest session {newest.session_id} cannot be decoded: {error}"
    if not header:
        note = warnings[-1] if warnings else "no session header event"
        return "FAIL", f"newest session {newest.session_id} has no readable header ({note})"
    cwd = header.get("cwd") or "-"
    depth = header.get("delegationDepth", 0)
    return "OK", f"{newest.session_id} type=session v{header.get('version')} depth={depth} cwd={cwd}"


def read_profile(path):
    """(model, effort, provider) found in the agent-default-model block of the profile patch YAML (fallback full text)."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    block = text
    marker = re.search(r"^[ \t]*-[ \t]*id:[ \t]*agent-default-model\b.*$", text, re.M)
    if marker:
        tail = text[marker.end():]
        nxt = re.search(r"^(?:[ \t]*-[ \t]*id:[ \t]*|[A-Za-z_][A-Za-z0-9_-]*[ \t]*:)", tail, re.M)
        block = tail[:nxt.start()] if nxt else tail
    values = {}
    for key in ("provider", "model", "reasoningEffort"):
        found = re.search(rf"^[ \t]*{key}[ \t]*:[ \t]*(\S+)", block, re.M)
        if found:
            values[key] = found.group(1).strip().strip("'\"")
    return values or None


def check_profile(path):
    if not path.is_file():
        return "WARN", f"{path} not found; model / effort cannot be read from the DSH profile"
    values = read_profile(path)
    if not values:
        return "WARN", f"{path} readable but holds no provider / model / reasoningEffort line"
    parts = " ".join(f"{key}={values[key]}" for key in ("provider", "model", "reasoningEffort") if key in values)
    return "OK", f"{parts} (from {path.name})"


def check_session_policy(cache_root):
    if not cache_root.is_dir():
        return "NOT_VERIFIED", "the projection cache is missing, so the latest session policy cannot be read"
    files = sorted(cache_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        projection = dsh.read_projection(path)
        if projection.error:
            continue
        sandbox = projection.row("sandboxMode")
        approval = projection.row("approvalState") if isinstance(projection.row("approvalState"), dict) else {}
        if sandbox or approval.get("policy"):
            pol = approval.get("policy") or "?"
            extra = ("; unconfined: no sandbox or approval barrier — rules and after-the-fact audit only"
                     if sandbox == "danger-full-access" and pol == "never" else "")
            return "OK", (f"sandbox={sandbox or '?'} approval={pol} "
                          f"(latest session {path.stem}; the sandbox and approval are per session, not a global setting"
                          f"{extra})")
    return "NOT_VERIFIED", "no sandbox / approval record in the projection cache"


def check_git():
    git = shutil.which("git")
    if not git:
        return "WARN", "git not on PATH; evidence_record.py / scope_check.py / trace_report.py need it"
    try:
        done = subprocess.run([git, "--version"], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20)
        version = done.stdout.strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        version = ""
    return "OK", f"{git}" + (f" ({version})" if version else "")


def check_config(tools_dir, config_path=None):
    """2.2.5-ds.5: the project's director_work.json reads (safety_gate.py); WARN for an old "sdd" block."""
    if not config_path:
        return "NOT_VERIFIED", "no --config given"
    path = tools_dir / "safety_gate.py"
    if not path.is_file():
        return "FAIL", f"safety_gate.py not found in {tools_dir}"
    spec = importlib_spec("dsh_doctor_safety_gate", path)
    limits = importlib_module(spec)
    spec.loader.exec_module(limits)
    config, problem = limits.load_config(None, config_path)
    if problem:
        return "FAIL", problem
    note = " | ".join(limits.legacy_notes(config))
    switches = " ".join(f"{key}={config.get(key)}" for key in limits.SWITCHES)
    return ("WARN", note) if note else ("OK", f"{config_path}: safety {switches}; order_limits "
                                                f"{limits.order_limits(config)}")


def check_tools(tools_dir, adapter_dir=ADAPTER_DIR):
    """The base tools folder holds every shared tool and the adapter folder every DSH file (3.0.0-ds.8)."""
    if not tools_dir.is_dir():
        return "FAIL", f"tools folder not found: {tools_dir}"
    missing = [name for name in REQUIRED_TOOLS if not (tools_dir / name).is_file()]
    missing += [f"adapters/deepseek/{name}" for name in ADAPTER_FILES if not (adapter_dir / name).is_file()]
    if missing:
        shown = ", ".join(missing[:8]) + (f" ... (+{len(missing) - 8})" if len(missing) > 8 else "")
        return "FAIL", f"missing required tool file(s): {shown}"
    return "OK", (f"{len(REQUIRED_TOOLS)} base tools in {tools_dir} and {len(ADAPTER_FILES)} DSH files in "
                  f"{adapter_dir}")


def check_folder(label, folder, min_files, suffixes=(".md",)):
    if not folder.is_dir():
        return "WARN", f"{label}/ not found under the edition root {folder.parent}"
    count = sum(1 for path in folder.rglob("*") if path.is_file() and path.suffix in suffixes)
    if count < min_files:
        return "WARN", f"{folder} exists but holds {count} file(s); the edition expects at least {min_files}"
    return "OK", f"{folder} ({count} file(s))"


def license_rows(path):
    """[(tool, license, expires text)] from a JSON list / {"licenses": [...]} or a Markdown table."""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    if pathlib.Path(path).suffix.lower() == ".json":
        data = json.loads(text)
        rows = data.get("licenses") if isinstance(data, dict) else data
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ValueError("a JSON license file is a list of objects or {\"licenses\": [...]}")
        return [(str(r.get("tool") or "?"), str(r.get("license") or r.get("tool") or "?"), str(r.get("expires") or ""))
                for r in rows]
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines[:-1]):
        cells = [c.strip().strip("`*").lower() for c in line.strip().strip("|").split("|")]
        if "tool" in cells and "expires" in cells and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                got = [c.strip().strip("`*") for c in row.strip().strip("|").split("|")]
                get = lambda name: got[cells.index(name)] if name in cells and cells.index(name) < len(got) else ""
                out.append((get("tool") or "?", get("license") or get("tool") or "?", get("expires")))
            return out
    raise ValueError("no Markdown table with tool and expires columns")


def license_items(path, today, days=3):
    """[(status word, name, detail)] for every license: ok / expiring / expired / bad."""
    out = []
    for tool, name, expires in license_rows(path):
        try:
            end = datetime.date.fromisoformat(expires.strip()[:10])
        except ValueError:
            out.append(("bad", "license date unreadable", f"{name} (held by {tool}): expires {expires!r} is not YYYY-MM-DD"))
            continue
        left = (end - today).days
        if left < 0:
            out.append(("expired", "license expired", f"{name} (held by {tool}) expired {end}, {-left} day(s) ago: renew "
                        "it or move the work to another tool"))
        elif left < days:
            out.append(("expiring", "license expiring", f"{name} (held by {tool}) expires {end}, {left} day(s) left: "
                        "renew it now"))
        else:
            out.append(("ok", "license", f"{name} (held by {tool}) expires {end}, {left} day(s) left"))
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools-dir", default=str(ADAPTER_DIR.parent.parent / "tools"),
                    help="the base tools folder (default: tools/ two folders above this one, as in the repo and in "
                    "an installed DIRECTOR/)")
    ap.add_argument("--sessions-root", help="DSH sessions root (default %%USERPROFILE%%\\.dsh\\sessions)")
    ap.add_argument("--cache-root", help="DSH projection cache root")
    ap.add_argument("--profile-config", help="DSH profile patch file (default <DSH_HOME>/profiles/desktop/cordis.patch.yml)")
    ap.add_argument("--config", help="a project director_work.json (the config check)")
    ap.add_argument("--json", action="store_true", help="print the checks as JSON")
    ap.add_argument("--licenses", metavar="FILE", help="tool licenses / trials with an expiry date (JSON or Markdown)")
    ap.add_argument("--license-days", type=int, default=3, help="warn when fewer days than this are left (default 3)")
    ap.add_argument("--licenses-only", action="store_true", help="run only the --licenses check (no DSH needed)")
    ap.add_argument("--today", help=argparse.SUPPRESS)  # tests: the date to count from
    a = ap.parse_args(argv)
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    if a.licenses_only:  # 2.3.0 (N6): the same lines as upstream doctor.py --licenses-only
        if not a.licenses:
            ap.error("--licenses-only needs --licenses FILE")
        try:
            found = license_items(a.licenses, today, a.license_days)
        except (OSError, ValueError) as error:
            print(f"LICENSES: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
            return 2
        for status, name, detail in found:
            print(f"{'INFO' if status == 'ok' else 'WARN':24} {name}: {detail}")
        n = {k: sum(f[0] == k for f in found) for k in ("ok", "expiring", "expired", "bad")}
        print(f"LICENSES: ok={n['ok']} expiring={n['expiring']} expired={n['expired']} bad={n['bad']}")
        return 1 if n["expiring"] or n["expired"] or n["bad"] else 0
    tools_dir = pathlib.Path(a.tools_dir).expanduser()
    sessions_root = pathlib.Path(a.sessions_root).expanduser() if a.sessions_root else dsh.default_sessions_root()
    cache_root = pathlib.Path(a.cache_root).expanduser() if a.cache_root else dsh.default_projcache_root()
    profile_path = (pathlib.Path(a.profile_config).expanduser() if a.profile_config
                    else dsh.dsh_home() / "profiles" / "desktop" / "cordis.patch.yml")
    edition_root = tools_dir.parent
    checks = []

    def add(name, result):
        status, detail = result
        checks.append({"check": name, "status": status, "detail": detail})

    add("python", check_python())
    node = check_node()
    add("node", node)
    add("dsh_home", check_dsh_home())
    add("sessions_root", check_sessions(sessions_root))
    add("projection_cache", check_projection_cache(cache_root))
    add("latest_session", check_latest_session(sessions_root, node[0] == "OK"))
    add("profile", check_profile(profile_path))
    add("session_policy", check_session_policy(cache_root))
    add("config", check_config(tools_dir, a.config))
    add("git", check_git())
    add("tools", check_tools(tools_dir))
    add("docs", check_folder("docs", edition_root / "docs", 8))
    add("templates", check_folder("templates", edition_root / "templates", 5))
    if a.licenses:  # 2.3.0 (N6)
        try:
            for status, name, detail in license_items(a.licenses, today, a.license_days):
                add("licenses", ("OK" if status == "ok" else "WARN", f"{name}: {detail}"))
        except (OSError, ValueError) as error:
            add("licenses", ("WARN", f"{a.licenses} not read: {type(error).__name__}: {str(error)[:200]}"))
    counts = {"OK": 0, "WARN": 0, "FAIL": 0, "NOT_VERIFIED": 0}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    if a.json:
        print(json.dumps({"tool": TOOL, "generated_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"), "checks": checks, "summary": counts}, ensure_ascii=False, indent=1))
    else:
        for check in checks:
            print(f"{check['status']:12} {check['check']}: {check['detail']}")
        print("")
    result = "FAIL" if counts["FAIL"] else "PASS"
    print(f"DSH_DOCTOR: {result} checks={len(checks)} ok={counts['OK']} warn={counts['WARN']} "
          f"fail={counts['FAIL']} not_verified={counts['NOT_VERIFIED']}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

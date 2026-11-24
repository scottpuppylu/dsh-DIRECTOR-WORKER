r"""Check that a DIRECTOR folder was built correctly by the DeepSeek Harness (DSH) BOOTSTRAP.

Run before the first report (BOOTSTRAP step 13). dshdw has no PO page: open questions are asked with the
ask_user_question tool and kept in DIRECTOR/PO_PENDING.md, so DIRECTOR_STATE.md must say how pending questions are
handled instead of naming a web page.

  python -I -X utf8 <WS>/DIRECTOR/tools/dsh_setup_check.py DIRECTOR [DIRECTOR ...]
  python -I -X utf8 <WS>/DIRECTOR/tools/dsh_setup_check.py --json DIRECTOR
  python -I -X utf8 <WS>/DIRECTOR/tools/dsh_setup_check.py --strict DIRECTOR

Each argument is a DIRECTOR folder (or its DIRECTOR_STATE.md). It checks:
  - the required files exist: DIRECTOR_STATE.md, ACTIVE_WORKSTREAMS.md, DECISION_REGISTER.md, PO_PENDING.md,
    RESUME_STATE.md, DIRECTOR_OPERATING_RULES.md, director_work.json
  - DIRECTOR_STATE.md has exactly one filled PENDING_METHOD line (ask_user_question + PO_PENDING.md; a leftover
    PO_PAGE_URL / PO_PAGE_PINNED line is only noted: dshdw has no Artifact page)
  - every PO_PENDING.md entry (ID: OD-xx / ACT-xx) has ID, STATUS (open / answered / closed), QUESTION, OPTIONS,
    RECOMMENDED, SOURCE and ANSWER, each once and filled in; an answered or closed entry needs a real ANSWER
  - RESUME_STATE.md holds the four header lines PROGRESS, DOING, NEXT_STEP, COMMS first, in this order
  - director_work.json is a JSON object (schema_version 1 is noted when it differs)

2.2.1-ds.1 adds checks that start in shadow mode (printed as "  ~ shadow: ..." and not failing; --strict makes them
"  - problem" lines that fail), the DSH form of upstream setup_check.py 2.2.1:
  - PO_PENDING.md: an ID is used once; an `ID:` line that is not OD-xx / ACT-xx is noted (this check skips it);
    an entry without CREATED is noted
  - RESUME_STATE.md: the four header lines are filled in (no placeholder) and UPDATED carries a date, by the same
    rule as `gate_check.py --resume` (the order of the four lines stays a problem as before)
  - director_work.json: schema_version 1 (the tools refuse another: metrics_report.py, trace_report.py); mode
    general / beginner; trace_id_pattern / po_item_pattern / po_open_pattern valid regular expressions;
    po_pending_files a list of strings. Claude-only keys dshdw skips (window, plugins_off, hooks, ...) and
    keys no tool reads are noted.

2.2.2-ds.3 (upstream 2.2.2 setup_check), shadow too:
  - RESUME_STATE.md: at most resume.max_bytes (20480) and no line over resume.max_line_bytes (4096), RESUME_SIZE
    otherwise (gate_check.py --resume's rule; limits from the director_work.json beside it)
  - director_work.json: resume an object, max_bytes / max_line_bytes / keep_recent whole numbers above 0,
    protect_headings a list of non-empty strings (an unknown resume key such as keep_days is only a note: recent
    means by count); base_ref an object, check / fetch / strict true or false (gate_check --order); release an
    object, remote / branch / title / tag_message / selftest non-empty strings, gh_repo owner/name or null
    (release.py refuses an unknown release key, so it is a problem here too)
  - 2.3.0-ds.5 (upstream 2.3.0): verdict_self_check "warn" or "fail" (gate_check --verdict's self-check line)
  - 2.2.4-ds.4: order_limits an object of whole numbers (max_files_per_order / max_lines_per_order /
    max_test_lines_per_order, 0 = off); protected_tests a list of globs
  - 2.2.5-ds.5 (WO-DS-009 B1): safety an object of the switches of safety_gate.py (true / false, stop_after_rounds a
    whole number); an old "sdd" block is read without error and leaves its WARN lines as notes
    (safety_gate.legacy_notes); no CLI is looked up and no install entry is asked for

Prints OK / FAIL per DIRECTOR with one "  - problem" line each, "  ~ shadow: ..." and "  ~ note" lines, then
  DSH_SETUP_CHECK: PASS|FAIL dirs=n problems=n
(problems= counts the DIRECTOR folders that failed.)
Exit codes: 0 no problems, 1 any problem, 2 usage error (no DIRECTOR given). Standard library only; reads only.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

REQUIRED_FILES = ("DIRECTOR_STATE.md", "ACTIVE_WORKSTREAMS.md", "DECISION_REGISTER.md", "PO_PENDING.md",
                  "RESUME_STATE.md", "DIRECTOR_OPERATING_RULES.md", "director_work.json")
PO_FIELDS = ("ID", "STATUS", "QUESTION", "OPTIONS", "RECOMMENDED", "SOURCE", "ANSWER")
PO_STATUSES = ("open", "answered", "closed")
PLACEHOLDER = re.compile(r"<[^<>@\n]+>")  # same rule as gate_check: <name@host> is an address, not a placeholder
CODE = re.compile(r"\x60[^\x60\n]*\x60")  # a code span is not a placeholder
FIELD = re.compile(r"^[ \t]*([A-Z][A-Z_]*)[ \t]*:[ \t]?(.*)$")
PO_START = re.compile(r"^[ \t]*ID[ \t]*:[ \t]*((?:OD|ACT)-[A-Za-z0-9_-]+)[ \t]*$")
SECTION = re.compile(r"^[ \t]*##[ \t]*(.+?)[ \t]*$")
RESUME_KEYS = ("PROGRESS", "DOING", "NEXT_STEP", "COMMS")
HERE = pathlib.Path(__file__).resolve().parent
ANY_ID = re.compile(r"^[ \t]*ID[ \t]*:[ \t]*(.*)$")
CONFIG_VERSION = 1
CONFIG_MODES = ("general", "beginner")
CONFIG_PATTERNS = ("trace_id_pattern", "po_item_pattern", "po_open_pattern")
CONFIG_KEYS = ("schema_version", "mode", "po_pending_files", "resume", "base_ref", "release", "order_limits",
               "protected_tests", "safety", "verdict_self_check", "loop_guard") + CONFIG_PATTERNS  # 2.3.0-ds.5: verdict_self_check
LEGACY_KEYS = ("sdd",)  # renamed "safety" in 2.2.5-ds.5: read without error, WARN notes (safety_gate.legacy_notes)
ORDER_LIMIT_KEYS = ("max_files_per_order", "max_lines_per_order", "max_test_lines_per_order")  # 2.2.4-ds.4
RESUME_CONFIG_KEYS = ("max_bytes", "max_line_bytes", "keep_recent", "protect_headings")  # 2.2.2-ds.3
BASE_REF_KEYS = ("check", "fetch", "strict")  # 2.2.2-ds.3: gate_check --order BASE_REF freshness
RELEASE_KEYS = ("remote", "branch", "title", "tag_message", "selftest", "gh_repo")  # 2.2.2-ds.3: release.py
CLAUDE_ONLY_KEYS = ("window", "plugins_off", "hooks", "protect_director", "director_worktree", "backup_dir",
                    "skip_worktrees", "session_map", "pause_flag", "audit_log", "runtime_guard", "guard_review",
                    "guard_profile", "guard_mode")


def filled(name, value, problems):
    """The value must be written out: not empty, not ..., not a placeholder."""
    if value.strip() in ("", "...", "…"):
        problems.append(f"{name}: empty")
        return
    found = PLACEHOLDER.search(CODE.sub("", value))
    if found:
        problems.append(f"{name}: placeholder left: {found.group(0)}")


def read_text(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def check_state_file(text, problems, notes):
    """The DSH DIRECTOR_STATE.md rules: one filled PENDING_METHOD, no Claude PO page requirement."""
    found = re.findall(r"^[ \t]*PENDING_METHOD[ \t]*:(.*)$", text, re.M)
    if len(found) > 1:
        problems.append(f"PENDING_METHOD: {len(found)} lines; keep one")
    if not found:
        problems.append("PENDING_METHOD: line missing; write how pending questions reach the PO in dshdw "
                        "(ask_user_question + DIRECTOR/PO_PENDING.md)")
    else:
        filled("PENDING_METHOD", found[0], problems)
        if found[0].strip() and "ask_user_question" not in found[0]:
            notes.append("PENDING_METHOD does not name ask_user_question; the DSH way is ask_user_question plus "
                         "PO_PENDING.md (no Artifact page)")
    for key in ("PO_PAGE_URL", "PO_PAGE_PINNED"):
        if re.search(rf"^[ \t]*{key}[ \t]*:", text, re.M):
            notes.append(f"{key} is a Claude-only line; dshdw has no page (ask_user_question + PO_PENDING.md)")


def check_po_pending(text, problems, notes):
    """Every PO entry has the seven DSH fields, once each, filled in the right state."""
    lines = text.splitlines()
    entries = []
    current = None
    section = None
    for number, line in enumerate(lines, 1):
        heading = SECTION.match(line)
        if heading:
            section = heading.group(1)
            continue
        start = PO_START.match(line)
        if not start and ANY_ID.match(line):
            current = None  # 2.2.1-ds.1: an ID this rule skips must not lend its fields to the entry above it
            continue
        if start:
            current = {"id": start.group(1), "line": number, "section": section, "fields": {}, "order": []}
            entries.append(current)
            current["fields"]["ID"] = (start.group(1), number)
            current["order"].append("ID")
            continue
        if current is None:
            continue
        field = FIELD.match(line)
        if field and field.group(1) in PO_FIELDS:
            key, value = field.group(1), field.group(2).strip()
            current["fields"].setdefault(key, (value, number))
            current["order"].append(key)
    if not entries:
        notes.append("PO_PENDING.md has no entries yet (fine before the first question)")
        return
    for entry in entries:
        label = f"PO_PENDING {entry['id']} (line {entry['line']})"
        for key in PO_FIELDS:
            if key not in entry["fields"]:
                problems.append(f"{label}: {key} missing")
        counts = {}
        for key in entry["order"]:
            counts[key] = counts.get(key, 0) + 1
        for key, count in counts.items():
            if count > 1 and key != "ID":
                problems.append(f"{label}: {key} appears {count} times; keep one")
        status = entry["fields"].get("STATUS", ("", 0))[0].lower()
        if status and status not in PO_STATUSES:
            problems.append(f"{label}: STATUS must be one of {', '.join(PO_STATUSES)}; got {status!r}")
        if not status:
            continue
        for key in ("QUESTION", "OPTIONS", "RECOMMENDED"):
            if key in entry["fields"]:
                filled(f"{label}: {key}", entry["fields"][key][0], problems)
        source = entry["fields"].get("SOURCE", ("", 0))[0]
        if source and not re.fullmatch(r"(?i)\s*NONE\s*", source):
            filled(f"{label}: SOURCE", source, problems)
        answer = entry["fields"].get("ANSWER", ("", 0))[0]
        has_answer = answer.strip() not in ("", "...", "…", "NONE") and not PLACEHOLDER.search(CODE.sub("", answer))
        if status in ("answered", "closed") and not has_answer:
            problems.append(f"{label}: STATUS {status} needs a real ANSWER")
        elif status == "open" and has_answer:
            notes.append(f"{label}: ANSWER is filled but STATUS is still open; update STATUS to answered")
        if entry["section"] and "已關閉" in entry["section"] and status != "closed":
            notes.append(f"{label}: under the 已關閉 heading but STATUS is {status}")
        if entry["section"] and "未關閉" in entry["section"] and status == "closed":
            notes.append(f"{label}: closed but still under the 未關閉 heading")


def check_resume_state(text, problems, notes):
    """The four header lines come first, in order: PROGRESS, DOING, NEXT_STEP, COMMS."""
    lines = [line for line in text.splitlines() if line.strip() != ""]
    for position, key in enumerate(RESUME_KEYS):
        if position >= len(lines):
            problems.append(f"RESUME_STATE: line {position + 1} ({key}:) missing; the four header lines come first")
            continue
        found = re.match(r"^([A-Z][A-Z_]*)[ \t]*:", lines[position])
        if not found:
            problems.append(f"RESUME_STATE: line {position + 1} must be {key}: ...; got {lines[position][:60]!r}")
        elif found.group(1) != key:
            problems.append(f"RESUME_STATE: line {position + 1} must be {key}:; got {found.group(1)}:")
    for position, key in enumerate(RESUME_KEYS):
        if position < len(lines):
            value = lines[position].split(":", 1)[1] if ":" in lines[position] else ""
            if key == "COMMS" and not value.strip():
                problems.append("RESUME_STATE: COMMS: empty; write NONE when nobody is waited for")


def check_config(path, problems, notes):
    try:
        data = json.loads(read_text(path))
    except ValueError as error:
        problems.append(f"director_work.json: not JSON ({error})")
        return
    if not isinstance(data, dict):
        problems.append("director_work.json: a JSON object is required")
        return
    version = data.get("schema_version")
    if version != 1:
        notes.append(f"director_work.json: schema_version is {version!r}; the tools expect 1")


def shadow_po_pending(text, notes):
    """2.2.1-ds.1: an ID used twice is a problem; an ID line the entry rule skips and a missing CREATED are notes."""
    problems, seen, current = [], {}, None
    for number, line in enumerate(text.splitlines(), 1):
        if SECTION.match(line):
            current = None
            continue
        start = PO_START.match(line)
        if start:
            current = start.group(1)
            if current in seen:
                problems.append(f"PO_PENDING {current} (line {number}): the ID is used again (first at line "
                                f"{seen[current][0]}); give it a new number")
                current = None
            else:
                seen[current] = [number, False]
            continue
        other = ANY_ID.match(line)
        if other:
            current = None
            notes.append(f"PO_PENDING line {number}: `ID: {other.group(1).strip()[:40]}` is not OD-xx / ACT-xx; "
                         "this check skips it")
            continue
        field = FIELD.match(line)
        if field and field.group(1) == "CREATED" and current in seen:
            seen[current][1] = True
    for item, (number, created) in seen.items():
        if not created:
            notes.append(f"PO_PENDING {item} (line {number}): no CREATED line (older entries may lack it)")
    return problems


def gate_check():
    """gate_check.py from this folder, so the RESUME rule has one source."""
    spec = importlib.util.spec_from_file_location("dsh_setup_check_gate_check", HERE / "gate_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shadow_resume(text, notes):
    """2.2.1-ds.1: filled header values and a dated UPDATED line (gate_check.check_resume); order stays a problem."""
    found = gate_check().check_resume(text, notes)
    return [f"RESUME_STATE: {problem}" for problem in found if not problem.startswith("line ")]


def neighbour(name):
    """A tool module from this folder (one source for a rule)."""
    spec = importlib.util.spec_from_file_location(f"dsh_setup_check_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shadow_resume_size(path, notes):
    """2.2.2-ds.3: RESUME_STATE.md over resume.max_bytes / max_line_bytes (gate_check's rule, limits from the
    director_work.json beside it, else 20480 / 4096)."""
    gate = gate_check()
    size = gate.resume_size(path.read_bytes(), *gate.resume_limits_for(path, None, notes))
    return [f"RESUME_STATE: {size}"] if size else []


def config_blocks(data, notes):
    """2.2.2-ds.3 (upstream 2.2.2 setup_check): the resume, base_ref and release blocks."""
    problems = []

    def say(message):
        problems.append(f"director_work.json: {message}")
    if "resume" in data:  # memory_size_check holds the rule
        found = []
        neighbour("memory_size_check").resume_settings(data, found)
        problems += [note.rsplit("; ", 1)[0] for note in found]
        if isinstance(data["resume"], dict):
            odd = sorted(k for k in data["resume"] if k not in RESUME_CONFIG_KEYS and not k.startswith("_"))
            if odd:
                notes.append(f"director_work.json: resume keys no tool reads: {', '.join(odd)} (a typo?)")
    if "order_limits" in data:  # 2.2.4-ds.4 (B1): scope_check.py reads it
        block = data["order_limits"]
        if not isinstance(block, dict):
            say(f"order_limits: an object with {' / '.join(ORDER_LIMIT_KEYS)}, got {block!r}")
        else:
            for key, value in block.items():
                if key.startswith("_"):
                    continue
                if key not in ORDER_LIMIT_KEYS:
                    notes.append(f"director_work.json: order_limits key no tool reads: {key} (a typo?)")
                elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    say(f"order_limits.{key}: a whole number, 0 = off, got {value!r}")
    safety_mod = neighbour("safety_gate")
    if "safety" in data:  # 2.2.5-ds.5 (B1): safety_gate.py reads it
        block = data["safety"]
        if not isinstance(block, dict):
            say(f"safety: an object with {' / '.join(safety_mod.SWITCHES)}, got {block!r}")
        else:
            for key, value in block.items():
                if key.startswith("_"):
                    continue
                if key not in safety_mod.SWITCHES:
                    notes.append(f"director_work.json: safety key no tool reads: {key} (a typo?)")
                elif key == "stop_after_rounds" and (isinstance(value, bool) or not isinstance(value, int)
                                                     or value < 0):
                    say(f"safety.{key}: a whole number, 0 = off, got {value!r}")
                elif key != "stop_after_rounds" and not isinstance(value, bool):
                    say(f"safety.{key}: true or false, got {value!r}")
    if any(key in data for key in LEGACY_KEYS):
        notes += safety_mod.legacy_notes(safety_mod.from_data(data))
    if "protected_tests" in data and not (isinstance(data["protected_tests"], list) and all(
            isinstance(item, str) and item.strip() for item in data["protected_tests"])):
        say(f"protected_tests: a list of globs, got {data['protected_tests']!r}")
    if "base_ref" in data:
        block = data["base_ref"]
        if not isinstance(block, dict):
            say(f"base_ref: an object with check / fetch / strict, got {block!r}")
        else:
            for key, value in block.items():
                if key.startswith("_"):
                    continue
                if key not in BASE_REF_KEYS:
                    notes.append(f"director_work.json: base_ref key no tool reads: {key} (a typo?)")
                elif not isinstance(value, bool):
                    say(f"base_ref.{key}: true or false, got {value!r}")
    if "verdict_self_check" in data and data["verdict_self_check"] not in ("warn", "fail"):  # 2.3.0: gate_check --verdict
        say(f"verdict_self_check: \"warn\" or \"fail\", got {data['verdict_self_check']!r}")
    if "release" in data:
        block = data["release"]
        if not isinstance(block, dict):
            say(f"release: an object, got {block!r}")
        else:
            for key, value in block.items():
                if key.startswith("_"):
                    continue
                if key not in RELEASE_KEYS:
                    say(f"release.{key}: release.py does not read it and refuses the config "
                        f"(keys: {', '.join(RELEASE_KEYS)})")
                elif key == "gh_repo":
                    if value is not None and not (isinstance(value, str) and re.fullmatch(r"[\w.-]+/[\w.-]+", value)):
                        say(f"release.gh_repo: owner/name or null, got {value!r}")
                elif value is not None and not (isinstance(value, str) and value.strip()):
                    say(f"release.{key}: a non-empty string, got {value!r}")
    if "loop_guard" in data:
        block = data["loop_guard"]
        if not isinstance(block, dict):
            say(f"loop_guard: an object with loop_guard settings, got {block!r}")
        else:
            audit_mod = neighbour("dsh_audit")
            try:
                audit_mod.loop_config(block)
            except audit_mod.LoopConfigError as error:
                say(f"loop_guard: {error}")
    return problems


def shadow_config(text, notes):
    """2.2.1-ds.1: the director_work.json keys the DSH tools read, with the right types."""
    try:
        data = json.loads(text)
    except ValueError:
        return []  # check_config already counts it as a problem
    if not isinstance(data, dict):
        return []
    problems = []
    version = data.get("schema_version", CONFIG_VERSION)
    if version != CONFIG_VERSION or isinstance(version, bool):
        problems.append(f"director_work.json: schema_version {version!r} is not {CONFIG_VERSION}; metrics_report.py "
                        "and trace_report.py refuse it (see CHANGELOG.md)")
    if "mode" in data and data["mode"] not in CONFIG_MODES:
        problems.append(f"director_work.json: mode: {' / '.join(CONFIG_MODES)}, got {data['mode']!r}")
    files = data.get("po_pending_files", [])
    if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
        problems.append("director_work.json: po_pending_files: a list of file names under DIRECTOR")
    for key in CONFIG_PATTERNS:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            problems.append(f"director_work.json: {key}: a string (a regular expression), got {type(value).__name__}")
            continue
        try:
            re.compile(value)
        except re.error as error:
            problems.append(f"director_work.json: {key}: not a valid regular expression ({error})")
    problems += config_blocks(data, notes)
    skipped = sorted(key for key in data if key in CLAUDE_ONLY_KEYS)
    if skipped:
        notes.append(f"director_work.json: Claude-only keys dshdw does not read: {', '.join(skipped)}")
    unknown = sorted(key for key in data if key not in CONFIG_KEYS + CLAUDE_ONLY_KEYS + LEGACY_KEYS
                     and not key.startswith("_"))
    if unknown:
        notes.append(f"director_work.json: keys no tool reads: {', '.join(unknown)} (a typo?)")
    return problems


SHADOW = (("PO_PENDING.md", shadow_po_pending), ("RESUME_STATE.md", shadow_resume),
          ("director_work.json", shadow_config))


def check_director(folder, strict=False):
    """(problems, notes) for one DIRECTOR folder; the 2.2.1-ds.1 checks are shadow notes unless strict."""
    problems, notes = [], []
    for name in REQUIRED_FILES:
        path = folder / name
        if not path.is_file():
            problems.append(f"{name}: file missing")
        elif path.stat().st_size == 0:
            problems.append(f"{name}: file is empty")
    state = folder / "DIRECTOR_STATE.md"
    if state.is_file():
        check_state_file(read_text(state), problems, notes)
    pending = folder / "PO_PENDING.md"
    if pending.is_file():
        check_po_pending(read_text(pending), problems, notes)
    resume = folder / "RESUME_STATE.md"
    if resume.is_file():
        check_resume_state(read_text(resume), problems, notes)
    config = folder / "director_work.json"
    if config.is_file():
        check_config(config, problems, notes)
    for name, check in SHADOW:
        path = folder / name
        if path.is_file():
            found = check(read_text(path), notes)
            if name == "RESUME_STATE.md":
                found += shadow_resume_size(path, notes)
            if strict:
                problems += found
            else:
                notes += [f"shadow: {problem}" for problem in found]
    return problems, notes


def target_folder(path):
    """The DIRECTOR folder for a path: the path itself, or the folder holding a given DIRECTOR_STATE.md."""
    target = pathlib.Path(path)
    if target.is_dir():
        return target
    if target.name == "DIRECTOR_STATE.md":
        return target.parent
    return None


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", metavar="DIR", help="DIRECTOR folder (or its DIRECTOR_STATE.md)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of lines")
    ap.add_argument("--strict", action="store_true", help="the 2.2.1-ds.1 checks (PO IDs, RESUME values, "
                    "director_work.json keys) fail instead of printing shadow notes")
    a = ap.parse_args(argv)
    results = []
    failed = 0
    for value in a.dirs:
        folder = target_folder(value)
        if folder is None:
            problems, notes = [f"not a DIRECTOR folder or DIRECTOR_STATE.md: {value}"], []
        elif not folder.is_dir():
            problems, notes = [f"folder not found: {folder}"], []
        else:
            problems, notes = check_director(folder, a.strict)
        failed += bool(problems)
        results.append({"path": str(folder) if folder is not None else value, "ok": not problems,
                        "problems": problems, "notes": notes})
        if not a.json:
            print(f"{'FAIL' if problems else 'OK  '} setup {folder if folder is not None else value}")
            for line in [f"  - {problem}" for problem in problems] + [f"  ~ {note}" for note in notes]:
                print(line)
    if a.json:
        print(json.dumps({"tool": "dsh_setup_check", "dirs": results,
                          "problems": sum(len(r["problems"]) for r in results)}, ensure_ascii=False, indent=1))
    print(f"DSH_SETUP_CHECK: {'FAIL' if failed else 'PASS'} dirs={len(a.dirs)} problems={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

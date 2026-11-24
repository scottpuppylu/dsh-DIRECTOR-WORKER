#!/usr/bin/env python3
"""Safety gates of a work order (2.2.5-ds.5; was sdd_gate.py of ds.2-ds.4). Only reads.

2.2.5-ds.5 (WO-DS-009 B1, revision 3): the OpenSpec layer of ds.2-ds.4 is removed (CLI lookup / install / init,
`openspec validate` / `archive`, SPEC_CHANGE, openspec_bin, require_spec_for_*). The safety gates it carried do not need
OpenSpec and stay, under the top-level "safety" block of director_work.json (all on when missing; docs/13):

  tests_first                true  Standard/Strict orders carry TESTS_LOCKED (`- NONE  # why` for docs-only work);
                                   a locked test whose sha256 changed fails (gate_check --order / --match)
  plan_gate                  true  the worker hands in <WORK_DIR>/<WO>/PLAN.md (`- [ ] 1.1 ...`) before any code;
                                   --match with --dispatch-log needs `PLAN_APPROVED <WO> sha=<plan hash>`, the plan may
                                   only differ from the approved one by ticked boxes, and every task is ticked
  spec_review_for_standard   true  a Standard order needs its SPEC_REVIEW too (Strict always does)
  stop_after_rounds          1     STOP_RULES of a Standard/Strict order may not allow more rounds than this
  prefer_auto                true  a note when a Standard/Strict order has no AUTO criterion (a hint, not a gate)

No self-loosening: for a Standard/Strict order, tests_first / plan_gate / spec_review_for_standard set to false, or
stop_after_rounds set to 0 / false or raised above 1, fails `gate_check --order` unless a PO_PENDING entry naming that
switch is answered by the PO (the 2.2.3-ds.3 rule for require_spec, WO-DS-004 lesson). prefer_auto off is only a note.

Also here: "order_limits" (max_files_per_order 3, max_lines_per_order 200, max_test_lines_per_order 400; 0 = off) and
"protected_tests" (globs of test files a worker may only add to), both read by scope_check.py.

An old "sdd" block is read without error (legacy_notes() gives its WARN lines): its safety switches still count, with
「請搬到 safety」 (a key also in "safety" is ignored); openspec_bin, require_spec_for_* and any other key are ignored
with 「OpenSpec 已在 2.2.5-ds.5 移除，此鍵被忽略」; old sdd.max_*_per_order still count with a shadow WARN
「請搬到 order_limits」 (2.2.4-ds.4). The ds.4 code with OpenSpec is at tag v2.2.4-ds.4.

CLI:
  safety_gate.py --lock-tests FILE ... [--repo DIR]   print the `TESTS_LOCKED:` list to paste into the order
  safety_gate.py --plan-hash PLAN_MD --order WO.md    print the `PLAN_APPROVED` line for DIRECTOR_LOG
Exit 0 done, 1 a file is missing.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

DEFAULTS = {
    "spec_review_for_standard": True,
    "tests_first": True,
    "plan_gate": True,
    "stop_after_rounds": 1,
    "prefer_auto": True,
}
SWITCHES = tuple(DEFAULTS)
GOVERNED = ("Standard", "Strict")
LOG_PREFIX = r"(?:\d{4}-\d{2}-\d{2}[^|\n`]*\|[ \t]*)?"
LIMIT_KEYS = ("max_files_per_order", "max_lines_per_order")
LIMIT_DEFAULTS = {"max_files_per_order": 3, "max_lines_per_order": 200, "max_test_lines_per_order": 400}
TEST_FILE = re.compile(r"(?:^|/)(?:tests/|test_[^/]*\.py$|[^/]*_test\.py$)")
LEGACY_KEY = "sdd"
REMOVED_WARN = "OpenSpec 已在 2.2.5-ds.5 移除，此鍵被忽略"
MOVE_WARN = "請搬到 safety"


def load_config(order_path=None, config_path=None):
    """(switches, problem or None). config_path, else <order folder>/../director_work.json when it exists. Missing
    file or keys: the defaults (all gates on). Private keys: _dir, _legacy_safety, _legacy_shadowed, _legacy_removed,
    _legacy_empty, _legacy_limits, _order_limits, _protected_tests."""
    config = dict(DEFAULTS)
    path = pathlib.Path(config_path) if config_path else None
    if path is None and order_path is not None:
        guess = pathlib.Path(order_path).resolve().parent.parent / "director_work.json"
        path = guess if guess.is_file() else None
    if path is None:
        return config, None
    config["_dir"] = str(path.resolve().parent)  # the DIRECTOR folder, for PO_PENDING.md and DIRECTOR_LOG.md
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return config, f"director_work.json {path}: cannot read ({error}); the defaults (all gates on) are used"
    if not isinstance(data, dict):
        return config, f"director_work.json {path}: not a JSON object; the defaults (all gates on) are used"
    return from_data(data, config), None


def from_data(data, config=None):
    """The switches of a parsed director_work.json (a dict) laid over config (default: DEFAULTS)."""
    config = dict(DEFAULTS) if config is None else config
    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}
    legacy = data.get(LEGACY_KEY)
    if isinstance(legacy, dict) or LEGACY_KEY in data:
        legacy = legacy if isinstance(legacy, dict) else {}
        moved = {key: value for key, value in legacy.items() if key in SWITCHES and key not in safety}
        config.update(moved)
        config["_legacy_safety"] = sorted(moved)
        config["_legacy_shadowed"] = sorted(key for key in legacy if key in SWITCHES and key in safety)
        config["_legacy_removed"] = sorted(key for key in legacy if key not in SWITCHES
                                           and key not in LIMIT_KEYS)
        config["_legacy_limits"] = {key: legacy[key] for key in LIMIT_KEYS if key in legacy}
        config["_legacy_empty"] = not legacy
    config.update({key: value for key, value in safety.items() if key in SWITCHES})
    limits = data.get("order_limits")
    if isinstance(limits, dict):
        config["_order_limits"] = {key: value for key, value in limits.items()
                                   if key in LIMIT_KEYS + ("max_test_lines_per_order",)}
    protected = data.get("protected_tests")
    if isinstance(protected, list):
        config["_protected_tests"] = [str(item) for item in protected if str(item).strip()]
    return config


def legacy_notes(config):
    """The WARN lines for an old "sdd" block (none without one): its removed OpenSpec keys, and its safety switches
    that still count (請搬到 safety) or are shadowed by "safety". The limits WARN comes from order_limits()."""
    out = []
    removed = config.get("_legacy_removed") or []
    if removed:
        out.append(f"WARN: {REMOVED_WARN}：" + "、".join(f"sdd.{key}" for key in removed))
    moved = config.get("_legacy_safety") or []
    if moved:
        out.append("WARN: " + "、".join(f"sdd.{key}" for key in moved) + f" 照讀，{MOVE_WARN}"
                   "（director_work.json 頂層 \"safety\"）")
    shadowed = config.get("_legacy_shadowed") or []
    if shadowed:
        out.append("WARN: " + "、".join(f"sdd.{key}" for key in shadowed) + " 被忽略（\"safety\" 裡已有同名的鍵）；"
                   "把它從 sdd 區塊刪掉")
    if config.get("_legacy_empty"):
        out.append("WARN: director_work.json 的 \"sdd\" 區塊是空的，2.2.5-ds.5 起沒有作用，可以刪掉（安全開關在 \"safety\"）")
    return out


def is_test_file(path):
    """2.2.4-ds.4 (B1): a test file, counted apart from max_lines_per_order: test_*.py, *_test.py, or anything under
    a tests/ folder."""
    return bool(TEST_FILE.search(str(path).replace("\\", "/")))


def order_limits(config, notes=None):
    """2.2.4-ds.4 (B1, WO-DS-006 #8): (max files, max non-test lines, max test lines) of one order. Read from the
    top-level `order_limits` block of director_work.json first. An old `sdd.max_*_per_order` key still works but
    leaves a shadow WARN 「請搬到 order_limits」; when both are set, order_limits wins and the WARN says the sdd key
    is ignored. 0 turns a limit off."""
    new = config.get("_order_limits") or {}
    old = config.get("_legacy_limits") or {}
    values = []
    for key in LIMIT_KEYS + ("max_test_lines_per_order",):
        if key in new:
            value = new[key]
            if key in old and notes is not None:
                notes.append(f"SHADOW WARN: sdd.{key}={old[key]} is ignored (order_limits.{key}={value} wins); "
                             f"remove it from the sdd block")
        elif key in old:
            value = old[key]
            if notes is not None:
                notes.append(f"SHADOW WARN: sdd.{key}={value} is the old place; 請搬到 order_limits "
                             f"(director_work.json top-level \"order_limits\": {{\"{key}\": {value}}})")
        else:
            value = LIMIT_DEFAULTS[key]
        try:
            values.append(int(value or 0))
        except (TypeError, ValueError):
            values.append(LIMIT_DEFAULTS[key])
            if notes is not None:
                notes.append(f"SHADOW WARN: {key}={value!r} is not a number; the default {LIMIT_DEFAULTS[key]} is used")
    return tuple(values)


def governance(text):
    m = re.search(r"^\s*GOVERNANCE\s*=\s*(\w+)", text, re.M)
    return m.group(1) if m else None


def field(text, key):
    """The value of a `KEY = value` line without a trailing ` # comment`; None when absent."""
    m = re.search(rf"^[ \t]*{key}[ \t]*=[ \t]*(.*)$", text, re.M)
    return re.split(r"\s+#", m.group(1))[0].strip() if m else None


def list_items(text, key):
    """Items of a `KEY:` line followed by `- item` lines (comments after ` #` dropped); None when the key is missing."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                items.append(re.split(r"\s+#", m.group(1))[0].strip())
            return items
    return None


def bytes_hash(data):
    """sha256 of bytes with CRLF read as LF, so line endings do not change it."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def file_hash(path):
    """sha256 of a text file with CRLF read as LF, so a checkout's line endings do not change it."""
    return hashlib.sha256(pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git_blob(repo, rev, rel_path):
    """Bytes of rel_path at git revision rev, or None if unavailable."""
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{rev}:{rel_path}"], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def plan_hash(path):
    """sha256 of PLAN.md with every box unticked and trailing spaces dropped: ticking `- [x]` keeps the hash,
    changing, adding or removing a task does not."""
    text = pathlib.Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    text = re.sub(r"^(\s*[-*]\s+)\[\s*[xX]\s*\]", r"\1[ ]", text, flags=re.M)  # `[ x]` is done too
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip() + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


PO_ID = re.compile(r"^[ \t]*ID[ \t]*:", re.M)


def po_entries(director):
    """(status, answer, text) of each `ID:` entry in <director>/PO_PENDING.md; [] when there is no such file."""
    path = pathlib.Path(director) / "PO_PENDING.md" if director else None
    if path is None or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig")
    starts = [m.start() for m in PO_ID.finditer(text)] + [len(text)]
    entries = []
    for begin, end in zip(starts, starts[1:]):
        block = text[begin:end]
        status = re.search(r"^[ \t]*STATUS[ \t]*:[ \t]*(\S*)", block, re.M)
        answer = re.search(r"^[ \t]*ANSWER[ \t]*:[ \t]*(.*)$", block, re.M)
        entries.append(((status.group(1) if status else "").lower(), (answer.group(1).strip() if answer else ""),
                        block))
    return entries


def po_decided(director, word):
    """'answered' when a PO_PENDING entry naming `word` is answered or closed with an ANSWER, 'open' when one is
    still open, None when none names it."""
    found = None
    for status, answer, block in po_entries(director):
        if word.lower() in block.lower():
            if status in ("answered", "closed") and answer and not re.fullmatch(r"[-—–]|<[^<>]*>|TBD|待\S*", answer):
                return "answered"
            found = "open"
    return found


def is_off(value):
    return value is False or value == 0 or value is None


def loosening(key, value):
    """How a switch is looser than its default: 'off' (false / 0), 'raised' (stop_after_rounds above 1), else None."""
    if is_off(value):
        return "off"
    if key == "stop_after_rounds" and not isinstance(value, bool):
        try:
            rounds = int(value)
        except (TypeError, ValueError):
            return None
        if rounds > DEFAULTS[key]:
            return "raised"
    return None


def switch_off_problems(config, gov, notes):
    """2.2.5-ds.5 (B1): a safety gate loosened for a Standard/Strict order (a switch off, or stop_after_rounds raised
    above 1) needs the PO's answer: a PO_PENDING entry naming the switch, answered or closed with an ANSWER. Open or
    missing: a problem (the lead may not loosen a gate by itself; WO-DS-004 wrote its own DD to do that). prefer_auto is
    a hint, not a gate: off is a note (總監 ruling 2026-11-15)."""
    problems = []
    director = config.get("_dir")
    for key in SWITCHES:
        if key == "spec_review_for_standard" and gov != "Standard":
            continue
        how = loosening(key, config.get(key))
        if how is None:
            continue
        if key == "prefer_auto":
            notes.append("safety.prefer_auto is off: no note about a missing AUTO criterion (a hint, not a gate)")
            continue
        state = "is off" if how == "off" else f"is raised to {config.get(key)} (default {DEFAULTS[key]})"
        decided = po_decided(director, key)
        if decided == "answered":
            notes.append(f"safety.{key} {state}; the PO answered it in PO_PENDING.md")
            continue
        wait = "the PO_PENDING entry is still open: wait for the PO" if decided == "open" else (
            f"write a PO_PENDING entry naming {key} and wait for the PO's answer")
        problems.append(f"safety.{key} {state} for a {gov} order; the lead may not loosen a safety gate (docs/13 "
                        f"「誰能關」): set it back, or {wait}")
    return problems


def check_tests(text, repo, problems, notes, candidate=None):
    """TESTS_LOCKED: `- <path> sha256=<64 hex>` per acceptance test, written before dispatch. The lock is what stops a
    worker from editing a test until it passes."""
    items = list_items(text, "TESTS_LOCKED")
    if items is None:
        problems.append("TESTS_LOCKED: missing; write the acceptance tests before dispatch, then paste the lines "
                        "`safety_gate.py --lock-tests <test files>` prints (or `- NONE  # why there is no test`)")
        return
    if not items or items == ["NONE"]:
        notes.append("TESTS_LOCKED: NONE; no locked acceptance test (fine for docs-only work)")
        return
    for item in items:
        m = re.fullmatch(r"(\S+)\s+sha256=([0-9a-fA-F]{64})", item)
        if not m:
            problems.append(f"TESTS_LOCKED: `{item}` is not `<path> sha256=<64 hex>`")
            continue
        if candidate:
            rel = m.group(1).replace("\\", "/")
            blob = _git_blob(repo, candidate, rel)
            if blob is None:
                problems.append(f"TESTS_LOCKED: {m.group(1)} not found in candidate {candidate[:12]} (deleted or missing)")
            elif bytes_hash(blob) != m.group(2).lower():
                problems.append(f"TESTS_LOCKED: {m.group(1)} changed in candidate {candidate[:12]} since it was locked; "
                                "a worker may not edit the acceptance tests (report BLOCKED instead)")
            continue
        path = pathlib.Path(repo) / m.group(1)
        if not path.is_file():
            problems.append(f"TESTS_LOCKED: {m.group(1)} not found under {pathlib.Path(repo).resolve()} (pass --repo)")
        elif file_hash(path) != m.group(2).lower():
            problems.append(f"TESTS_LOCKED: {m.group(1)} changed since it was locked; a worker may not edit the "
                            "acceptance tests (report BLOCKED instead)")


def order_problems(text, order_path, repo, config, notes, candidate=None):
    """The safety gates for one work order (gate_check.py --order and --match)."""
    problems = []
    gov = governance(text)
    if field(text, "SPEC_CHANGE") is not None:
        notes.append("SPEC_CHANGE: the field is ignored since 2.2.5-ds.5 (OpenSpec removed); write the spec into "
                     "ACCEPTANCE and the boundary list of templates/WORK_ORDER.md E")
    if gov not in GOVERNED:
        return problems
    problems += switch_off_problems(config, gov, notes)
    if not is_off(config.get("tests_first")):
        check_tests(text, repo, problems, notes, candidate=candidate)
    limit = config.get("stop_after_rounds")
    stop = re.search(r"STOP_RULES\s*[:：=]\s*(.*)", text)
    if not is_off(limit) and stop:
        rounds = [int(n) for n in re.findall(r"(\d+)\s*(?:輪|rounds?)", stop.group(1))]
        if not rounds:
            notes.append(f"STOP_RULES: no round count; write 「同一根因 {limit} 輪沒進展就停」")
        elif max(rounds) > int(limit):
            problems.append(f"STOP_RULES: allows {max(rounds)} rounds on one root cause; at most {limit} "
                            "(safety.stop_after_rounds)")
    if not is_off(config.get("prefer_auto")) and not re.search(r"^\|\s*AC-\d+\s*\|\s*AUTO\s*\|", text, re.M):
        notes.append("acceptance: no AUTO criterion; prefer a condition a command can decide (safety.prefer_auto)")
    return problems


def log_lines(log_text, event):
    """(id, rest) of each whole-line `<event> <id> ...` in DIRECTOR_LOG, oldest first; lines inside fences skipped."""
    out, fence = [], False
    for line in log_text.splitlines():
        if re.match(r" {0,3}(`{3,}|~{3,})", line):
            fence = not fence
            continue
        m = None if fence else re.fullmatch(LOG_PREFIX + rf"{event}[ \t]+([^\s|`]+?)(?:\.md)?(?:[ \t]+(.*))?", line.strip())
        if m:
            out.append((m.group(1), m.group(2) or ""))
    return out


REVIEW_FIELDS = ("tokens=", "issues=", "adopted=")


def review_fields_lacking(rest):
    """The REVIEW_FIELDS (with "=") missing from the rest of a `SPEC_REVIEW <WO> ...` line. The one copy: gate_check
    --sequence calls it too (2.2.5-ds.5 B7)."""
    return [key for key in REVIEW_FIELDS if key not in (rest or "")]


def review_sources(order_path, config):
    """2.2.4-ds.4 (B4): where a spec review of an order may be found without --dispatch-log: DIRECTOR_LOG.md and
    reviews/*SPEC_REVIEW* of the order's DIRECTOR folder (the folder of director_work.json, else orders/..)."""
    folders = [pathlib.Path(config["_dir"])] if config.get("_dir") else []
    if order_path is not None:
        folders.append(pathlib.Path(order_path).resolve().parent.parent)
    logs, reviews = [], []
    for folder in dict.fromkeys(folders):
        if (folder / "DIRECTOR_LOG.md").is_file():
            logs.append(folder / "DIRECTOR_LOG.md")
        if (folder / "reviews").is_dir():
            reviews += sorted(p for p in (folder / "reviews").iterdir()
                              if p.is_file() and "SPEC_REVIEW" in p.name.upper())
    return logs, reviews


def spec_review_problems(order_text, ids, log_text, config, notes, order_path):
    """2.2.4-ds.4 (B4, WO-DS-006 #4): every Standard/Strict order handed in needs its spec review: the `SPEC_REVIEW
    <WO>` line of --dispatch-log, else of the order's DIRECTOR_LOG.md, else a reviews/ file named after the order with
    SPEC_REVIEW in its name. None: FAIL."""
    wanted = {name.upper() for name in ids}
    label = next(iter(ids), "the order")
    looked = []
    if log_text is not None:
        sources = [("--dispatch-log", log_text)]
    else:
        logs, reviews = review_sources(order_path, config)
        sources = [(path.as_posix(), path.read_text(encoding="utf-8-sig")) for path in logs]
        for path in reviews:
            upper = path.name.upper()
            if any(re.search(rf"(?<![A-Z0-9-]){re.escape(name)}(?![0-9])", upper) for name in wanted):
                notes.append(f"SPEC_REVIEW: review file {path.as_posix()} (no --dispatch-log; its line in "
                             "DIRECTOR_LOG was not checked)")
                return []
        looked.append("reviews/*SPEC_REVIEW*")
    for where, text in sources:
        lines = [rest for name, rest in log_lines(text, "SPEC_REVIEW") if name.upper() in wanted]
        if lines:
            lacking = [key.rstrip("=") for key in review_fields_lacking(lines[-1])]
            if lacking:
                notes.append(f"SPEC_REVIEW: the line for {label} in {where} has no {'/'.join(lacking)}; write "
                             f"`SPEC_REVIEW {label} tokens=<n|UNKNOWN> issues=<P0/P1/P2> adopted=<n>`")
            return []
        looked.insert(0, where)
    return [f"SPEC_REVIEW: no `SPEC_REVIEW {label} tokens=... issues=... adopted=...` line (looked in: "
            f"{', '.join(looked) or 'no --dispatch-log, no DIRECTOR_LOG.md'}); every Standard/Strict order is reviewed "
            "before dispatch (templates/SPEC_REVIEW.md)"]


def plan_path(order_text, ids, repo):
    """(path of <WORK_DIR>/<WO>/PLAN.md, or None, why). WORK_DIR of the order, relative to --repo when not absolute;
    the first of the order's names whose folder holds a PLAN.md, else the first name."""
    work = field(order_text, "WORK_DIR")
    if not work or work.startswith("<"):
        return None, "the order has no WORK_DIR, so <WORK_DIR>/<WO>/PLAN.md cannot be found"
    base = pathlib.Path(work)
    base = base if base.is_absolute() else pathlib.Path(repo) / base
    names = list(ids) or ["WO"]
    for name in names:
        if (base / name / "PLAN.md").is_file():
            return base / name / "PLAN.md", None
    return None, f"{(base / names[0] / 'PLAN.md').as_posix()} not found"


def match_problems(order_text, ids, log_text, repo, config, notes, order_path=None):
    """--match: the spec review (with or without --dispatch-log) and, with --dispatch-log, the approved plan."""
    problems = []
    gov = governance(order_text)
    if gov not in GOVERNED:
        return problems
    label = next(iter(ids), "the order")
    if gov == "Strict" or not is_off(config.get("spec_review_for_standard")):
        problems += spec_review_problems(order_text, ids, log_text, config, notes, order_path)
    if log_text is None or is_off(config.get("plan_gate")):
        return problems
    wanted = {name.upper() for name in ids}
    approved = [rest for name, rest in log_lines(log_text, "PLAN_APPROVED") if name.upper() in wanted]
    if not approved:
        problems.append(f"PLAN_APPROVED: no `PLAN_APPROVED {label} sha=<64>` line in the dispatch log; the worker "
                        "hands in <WORK_DIR>/<WO>/PLAN.md and the Director approves it before any code (safety.plan_gate)")
        return problems
    sha = re.search(r"\bsha=([0-9a-fA-F]{64})\b", approved[-1])
    plan, why = plan_path(order_text, ids, repo)
    if not sha:
        problems.append("PLAN_APPROVED: the line has no sha=<64 hex> (safety_gate.py --plan-hash prints it)")
    elif plan is None:
        problems.append(f"PLAN_APPROVED: {why}; the approved plan cannot be compared")
    elif plan_hash(plan) != sha.group(1).lower():
        problems.append(f"PLAN_APPROVED: {plan.as_posix()} differs from the approved plan (more than ticked boxes); a "
                        "changed plan goes back to the Director first")
    else:  # handed in: every approved task is done; only a box holding `x` counts
        open_tasks = re.findall(r"^\s*[-*]\s+\[(?!\s*[xX]\s*\])[^\]\n]*\]\s*(.*)$",
                                plan.read_text(encoding="utf-8-sig"), re.M)
        if open_tasks:
            problems.append(f"PLAN_APPROVED: {len(open_tasks)} task(s) in PLAN.md not ticked, e.g. "
                            f"{open_tasks[0].strip()[:80]}; finish them or report PARTIAL")
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock-tests", nargs="+", metavar="FILE", help="print TESTS_LOCKED lines (paths relative to --repo)")
    ap.add_argument("--plan-hash", metavar="PLAN_MD", help="print the PLAN_APPROVED line for this PLAN.md")
    ap.add_argument("--order", help="with --plan-hash: the work order the plan belongs to")
    ap.add_argument("--repo", default=".", help="the project checkout (default: current folder)")
    a = ap.parse_args()
    if not (a.lock_tests or a.plan_hash):
        ap.error("give --lock-tests or --plan-hash")
    status = 0
    if a.lock_tests:
        print("TESTS_LOCKED:")
        root = pathlib.Path(a.repo).resolve()
        for name in a.lock_tests:
            path = pathlib.Path(name)
            path = path if path.is_absolute() else pathlib.Path.cwd() / path
            if not path.is_file():
                print(f"# not found: {name}")
                status = 1
                continue
            try:
                rel = path.resolve().relative_to(root).as_posix()
            except ValueError:
                print(f"# outside --repo {root}: {name}")
                status = 1
                continue
            print(f"- {rel} sha256={file_hash(path)}")
    if a.plan_hash:
        if not a.order or not pathlib.Path(a.order).is_file() or not pathlib.Path(a.plan_hash).is_file():
            print("PLAN_HASH: NOT_RUN give an existing --order and PLAN.md")
            status = 1
        else:
            title = re.search(r"^#\s+(\S+)", pathlib.Path(a.order).read_text(encoding="utf-8-sig"), re.M)
            ident = title.group(1) if title else pathlib.Path(a.order).stem
            print(f"PLAN_APPROVED {ident} sha={plan_hash(a.plan_hash)}")
    return status


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Safety gates of a work order (3.0.0 D1; merged from the dshdw ds.7 and agydw safety_gate.py). Only reads.

gate_check.py --order and --match load this file by path. Only Standard and Strict orders are gated; Direct is not.

Strength: "strength" in director_work.json ("light" | "standard" | "strict", default "standard") sets which gates are
on. The "safety" block may turn single switches on or tighten them on top of that:
(3.0.0 B15) A variant sets its own default in adapters/<name>/VARIANT.json beside the tools folder, as
{"default_strength": "light"} (dshdw: SPEC_VARIANTS_300 default light); the rules checkout and an installed DIRECTOR/
have the same layout (tools/ and adapters/<name>/ side by side). The default then counts as "standard" does below
(no PO answer needed for it). A VARIANT.json that cannot be read, a value that is not a strength, or two files that
disagree is a problem (the gates fail) and the default stays "standard"; no VARIANT.json key: "standard".

  switch                     light  standard  strict  what it does
  tests_first                off    on        on      the order carries TESTS_LOCKED (`- NONE  # why` for docs-only
                                                      work); a locked test whose sha256 changed fails --order, and
                                                      with --match --candidate the file is read from the candidate
                                                      commit (git cat-file), so an edit committed by the worker fails
  plan_gate                  off    off       on      --match with --dispatch-log needs `PLAN_APPROVED <WO> sha=<64>`;
                                                      <WORK_DIR>/<WO>/PLAN.md may only differ from it by ticked boxes,
                                                      and every task is ticked
  spec_review_for_standard   off    off       on      --match needs the order's SPEC_REVIEW (log line or reviews/ file)
  stop_after_rounds          0      0         1       STOP_RULES may not allow more rounds than this (0 = not checked)
  prefer_auto                off    off       on      a note when no acceptance criterion is AUTO (a hint, not a gate)

No self-loosening (hard line): a worker may not turn these off. For a Standard / Strict order, each of these fails
unless a PO_PENDING.md entry naming it is answered or closed with an ANSWER (the PO decided):
  - "strength" below the default strength ("standard"; that is, "light");
  - a switch in "safety" looser than its strength's value (on -> off, stop_after_rounds 0 or raised above it).
A strength or switch value of the wrong type ("strength": "lite", "tests_first": "no", stop_after_rounds -1 or true),
or a director_work.json that cannot be read, also fails: the gate never guesses towards weaker.

TESTS_LOCKED lines: `- <path> sha256=<64 hex>`; the path may hold spaces and may be quoted ("…", '…' or `…`), as
--lock-tests prints it for a path with spaces. The 2.2.3 one-line form `TESTS_LOCKED: <path> sha256=<64 hex>` (one
line per file) is read too. The hash reads CRLF as LF.

3.0.0 B4 (Director decision; from agydw and dshdw ds.4 B1 / B5, read by scope_check.py): the size limits and the
protected tests, checked only when something declares them, at every strength (light, standard, strict alike):
  - size: the order's `ORDER_LIMITS = files=<n> lines=<n> test_lines=<n>` line (any governance; each word optional),
    and, for a Standard / Strict order, the top-level "order_limits" block of director_work.json
    (max_files_per_order, max_lines_per_order, max_test_lines_per_order); a word of the order line wins over the
    block, a limit nobody sets is off, 0 is off. Nothing declared: no size check (agydw / dshdw had defaults 3 / 200 /
    400; their director_work.example.json declares the block, so a project made from it keeps the check).
  - protected: the order's TESTS_LOCKED files and the "protected_tests" globs of director_work.json may only be added
    or grow at their end. Neither: no check.
  A limit that is not a whole number 0 or more, an unknown key, or a "protected_tests" that is not a list of strings
  is a problem (scope_check.py: NOT_RUN), never a guess towards weaker. The old "sdd" block is not ported.

CLI:
  safety_gate.py --lock-tests FILE ... [--repo DIR]   print the `TESTS_LOCKED:` list to paste into the order
  safety_gate.py --plan-hash PLAN_MD --order WO.md    print the `PLAN_APPROVED` line for DIRECTOR_LOG
  safety_gate.py --show [--config director_work.json] print the strength and the switches in force
Exit 0 done, 1 a file is missing or the config is invalid, 2 usage.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

STRENGTHS = {
    "light": {"tests_first": False, "plan_gate": False, "spec_review_for_standard": False, "stop_after_rounds": 0,
              "prefer_auto": False},
    "standard": {"tests_first": True, "plan_gate": False, "spec_review_for_standard": False, "stop_after_rounds": 0,
                 "prefer_auto": False},
    "strict": {"tests_first": True, "plan_gate": True, "spec_review_for_standard": True, "stop_after_rounds": 1,
               "prefer_auto": True},
}
ORDER = ("light", "standard", "strict")
BASE_DEFAULT = "standard"
VARIANT_FILE = "VARIANT.json"  # 3.0.0 B15: adapters/<name>/VARIANT.json {"default_strength": ...}


def variant_default(tools_dir=None):
    """3.0.0 B15 (dsh report): (strength, source, problems) of the default strength. adapters/*/VARIANT.json next to
    the tools folder may set "default_strength"; none sets it: ("standard", None, []). A file that cannot be read, a
    value that is not one of light / standard / strict, or two files that disagree: ("standard", None, [problem])."""
    folder = pathlib.Path(tools_dir) if tools_dir else pathlib.Path(__file__).resolve().parent
    found, problems = {}, []
    for path in sorted(folder.parent.glob("adapters/*/" + VARIANT_FILE)):
        name = path.relative_to(folder.parent).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as error:
            problems.append(f"SAFETY variant default: {name} cannot be read ({type(error).__name__}); the default "
                            f"stays {BASE_DEFAULT}")
            continue
        if not isinstance(data, dict):
            problems.append(f"SAFETY variant default: {name} is not a JSON object; the default stays {BASE_DEFAULT}")
        elif "default_strength" in data and data["default_strength"] not in STRENGTHS:
            problems.append(f"SAFETY variant default: {name} default_strength {data['default_strength']!r} is not one "
                            f"of {' / '.join(ORDER)}; the default stays {BASE_DEFAULT}")
        elif "default_strength" in data:
            found[name] = data["default_strength"]
    if len(set(found.values())) > 1:
        problems.append("SAFETY variant default: " + ", ".join(f"{n} says {v}" for n, v in found.items())
                        + f": they disagree; the default stays {BASE_DEFAULT}")
    if problems or not found:
        return BASE_DEFAULT, None, problems
    name = next(iter(found))
    return found[name], name, []


DEFAULT_STRENGTH, DEFAULT_SOURCE, DEFAULT_PROBLEMS = variant_default()
SWITCHES = tuple(STRENGTHS["strict"])
GOVERNED = ("Standard", "Strict")
LIMIT_KEYS = ("max_files_per_order", "max_lines_per_order", "max_test_lines_per_order")  # 3.0.0 B4
LIMIT_WORDS = ("files", "lines", "test_lines")  # the ORDER_LIMITS words, in the same order
TEST_FILE = re.compile(r"(?:^|/)(?:tests/|test_[^/]*\.py$|[^/]*_test\.py$)")


def find_config(order_path=None, config_path=None):
    """--config, else director_work.json in the order's folder or the one above it (DIRECTOR/orders/WO.md ->
    DIRECTOR/director_work.json), else None."""
    if config_path:
        return pathlib.Path(config_path)
    if order_path is None:
        return None
    folder = pathlib.Path(order_path).resolve().parent
    return next((f / "director_work.json" for f in (folder, folder.parent) if (f / "director_work.json").is_file()),
                None)


def load_config(order_path=None, config_path=None):
    """(config, problems). config: "strength", every switch, "_set" (the switches the "safety" block sets), "_dir" (the
    folder of director_work.json, for PO_PENDING.md), "_path". A missing file is the default strength; a file that
    cannot be read, a strength or a switch of the wrong type is a problem and the value stays at its strength's."""
    path = find_config(order_path, config_path)
    config = {"strength": DEFAULT_STRENGTH, **STRENGTHS[DEFAULT_STRENGTH], "_set": [], "_dir": None, "_path": None}
    if path is None:
        return config, list(DEFAULT_PROBLEMS)  # 3.0.0 B15: a broken VARIANT.json fails even without a config
    config["_dir"], config["_path"] = str(path.resolve().parent), path.as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        return config, [*DEFAULT_PROBLEMS, f"SAFETY config: {path.as_posix()} cannot be read ({type(error).__name__}); "
                                           f"the gates stay at strength {DEFAULT_STRENGTH}"]
    if not isinstance(data, dict):
        return config, [*DEFAULT_PROBLEMS, f"SAFETY config: {path.as_posix()} is not a JSON object"]
    return from_data(data, config)


def from_data(data, config=None):
    """(config, problems) of a parsed director_work.json laid over the default strength."""
    config = config or {"strength": DEFAULT_STRENGTH, **STRENGTHS[DEFAULT_STRENGTH], "_set": [], "_dir": None,
                        "_path": None}
    problems = list(DEFAULT_PROBLEMS)  # 3.0.0 B15
    strength = data.get("strength", DEFAULT_STRENGTH)
    if strength not in STRENGTHS:
        problems.append(f"SAFETY strength: {strength!r} is not one of {' / '.join(ORDER)}; the gates stay at "
                        f"{DEFAULT_STRENGTH}")
        strength = DEFAULT_STRENGTH
    config.update({"strength": strength, **STRENGTHS[strength]})
    safety = data.get("safety", {})
    if not isinstance(safety, dict):
        problems.append(f"SAFETY safety: must be a JSON object of switches, got {type(safety).__name__}")
        safety = {}
    for key, value in safety.items():
        if key not in SWITCHES:
            if not key.startswith("_"):
                problems.append(f"SAFETY safety.{key}: not a switch ({', '.join(SWITCHES)})")
            continue
        if key == "stop_after_rounds":
            good = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else:
            good = isinstance(value, bool)
        if not good:
            want = "a whole number, 0 or more" if key == "stop_after_rounds" else "true or false"
            problems.append(f"SAFETY safety.{key}: {value!r} is not {want}; it stays {config[key]!r} ({strength})")
            continue
        config[key] = value
        config["_set"].append(key)
    limits = data.get("order_limits")  # 3.0.0 B4 (from agydw / dshdw ds.4 B1)
    if limits is not None and not isinstance(limits, dict):
        problems.append(f"SAFETY order_limits: must be a JSON object of limits, got {type(limits).__name__}")
    elif limits is not None:
        config["_order_limits"] = {}
        for key, value in limits.items():
            if key.startswith("_"):
                continue
            if key not in LIMIT_KEYS:
                problems.append(f"SAFETY order_limits.{key}: not a limit ({', '.join(LIMIT_KEYS)})")
            elif not (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
                problems.append(f"SAFETY order_limits.{key}: {value!r} is not a whole number, 0 or more")
            else:
                config["_order_limits"][key] = value
    protected = data.get("protected_tests")  # 3.0.0 B4 (from agydw / dshdw ds.4 B5)
    if protected is not None and not (isinstance(protected, list) and all(isinstance(g, str) for g in protected)):
        problems.append(f"SAFETY protected_tests: must be a list of globs (strings), got {protected!r}"[:200])
    elif protected is not None:
        config["_protected_tests"] = [g.strip() for g in protected if g.strip()]
    return config, problems


def is_test_file(path):
    """3.0.0 B4 (dshdw ds.4 B1): a test file, whose lines count against the test-line limit: test_*.py, *_test.py, or
    anything under a tests/ folder."""
    return bool(TEST_FILE.search(str(path).replace("\\", "/")))


def order_limits(text, config):
    """3.0.0 B4: (files, lines, test lines) one order may change, 0 = off; None when nothing declares a limit. The
    order's ORDER_LIMITS words win over the director_work.json "order_limits" block, which counts for Standard / Strict
    orders only (as in agydw). Raises ValueError for an ORDER_LIMITS word that is not `files|lines|test_lines=<n>`."""
    line = field(text, "ORDER_LIMITS") or ""
    words = {}
    if line and not line.startswith("<"):  # `<...>` is the template's placeholder
        for token in line.replace("，", " ").replace(",", " ").split():
            key, eq, value = token.partition("=")
            if not eq or key not in LIMIT_WORDS or not value.isdigit():
                raise ValueError(f"ORDER_LIMITS: `{token}` is not files=<n>, lines=<n> or test_lines=<n>")
            words[key] = int(value)
    block = (config.get("_order_limits") or {}) if governance(text) in GOVERNED else {}
    if not words and not block:
        return None
    values = tuple(words.get(word, block.get(key, 0)) for word, key in zip(LIMIT_WORDS, LIMIT_KEYS))
    return values if any(values) else None


def protected_paths(text, config):
    """3.0.0 B4: (the order's TESTS_LOCKED paths, the "protected_tests" globs); `- NONE` locks nothing."""
    locked = [parsed[0].replace("\\", "/") for parsed in map(locked_path, locked_items(text) or []) if parsed]
    return locked, list(config.get("_protected_tests") or [])


def on(config, key):
    value = config.get(key)
    return bool(value) and not (key == "stop_after_rounds" and value == 0)


def governance(text):
    m = re.search(r"^\s*GOVERNANCE\s*=\s*(\w+)", text, re.M)
    return m.group(1) if m else None


def field(text, key):
    """The value of a `KEY = value` line without a trailing ` # comment`; None when absent."""
    m = re.search(rf"^[ \t]*{key}[ \t]*=[ \t]*(.*)$", text, re.M)
    return re.split(r"\s+#", m.group(1))[0].strip() if m else None


NONE_WHY = re.compile(r"^[ 	]*(?:-[ 	]+|TESTS_LOCKED[ 	]*[:：=][ 	]*)NONE[ 	]+#[ 	]*\S", re.M)


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
    return bytes_hash(pathlib.Path(path).read_bytes())


def _git_blob(repo, rev, rel_path):
    """Bytes of rel_path at git revision rev, or None if unavailable."""
    try:
        done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{rev}:{rel_path}"], capture_output=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
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
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return []
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
        if re.search(rf"(?<![\w.]){re.escape(word)}(?!\w)", block, re.I):
            if status in ("answered", "closed") and answer and not re.fullmatch(r"[-—–]|<[^<>]*>|TBD|待\S*", answer):
                return "answered"
            found = "open"
    return found


def loosening(config):
    """[(word, what)] of each way config is looser than the default strength's gates: the strength itself below
    standard, and each switch the "safety" block set looser than its strength's value."""
    out = []
    strength = config.get("strength", DEFAULT_STRENGTH)
    if ORDER.index(strength) < ORDER.index(DEFAULT_STRENGTH):
        out.append(("strength", f"strength is {strength} (below {DEFAULT_STRENGTH})"))
    base = STRENGTHS[strength]
    for key in config.get("_set", []):
        value, want = config[key], base[key]
        if key == "stop_after_rounds":
            if want and (value == 0 or value > want):
                out.append((key, f"safety.{key} is {value} ({strength} has {want})"))
        elif want and not value:
            out.append((key, f"safety.{key} is off ({strength} has it on)"))
    return out


def loosening_problems(config, gov, notes):
    """A gate loosened for a Standard / Strict order needs the PO's answer in PO_PENDING.md; prefer_auto off is only a
    note (a hint, not a gate)."""
    problems = []
    for word, what in loosening(config):
        if word == "prefer_auto":
            notes.append(f"{what}: no note about a missing AUTO criterion (a hint, not a gate)")
            continue
        decided = po_decided(config.get("_dir"), word)
        if decided == "answered":
            notes.append(f"{what}; the PO answered it in PO_PENDING.md")
            continue
        wait = "the PO_PENDING entry is still open: wait for the PO" if decided == "open" else (
            f"write a PO_PENDING entry naming {word} and wait for the PO's answer")
        problems.append(f"SAFETY: {what} for a {gov} order; a worker may not turn a safety gate off: set it back, "
                        f"or {wait}")
    return problems


def locked_path(item):
    """(path, sha) of one TESTS_LOCKED item, or None. The path may hold spaces and be quoted (agydw)."""
    m = re.fullmatch(r"(.+?)\s+sha256=([0-9a-fA-F]{64})", item)
    if not m:
        return None
    rel = m.group(1).strip()
    if len(rel) >= 2 and rel[0] == rel[-1] and rel[0] in "\"'`":
        rel = rel[1:-1]
    return (rel, m.group(2).lower()) if rel else None


def locked_items(text):
    """TESTS_LOCKED items: the block (`TESTS_LOCKED:` then `- <item>` lines) and the 2.2.3 one-line form
    (`TESTS_LOCKED: <path> sha256=<64>`, one line per file, docs/02); None when the order has neither."""
    items = list_items(text, "TESTS_LOCKED")
    inline = [re.split(r"\s+#", m.group(1))[0].strip()
              for m in re.finditer(r"^[ 	]*(?:-[ 	]+)?TESTS_LOCKED[ 	]*[:：=][ 	]*(\S.*)$", text, re.M)]
    return None if items is None and not inline else (items or []) + inline


def check_tests(text, repo, problems, notes, candidate=None):
    """TESTS_LOCKED: `- <path> sha256=<64 hex>` per acceptance test, written before dispatch. The lock is what stops a
    worker from editing a test until it passes. With candidate (dshdw ds.7) the file is read from that commit."""
    items = locked_items(text)
    if items is None:
        problems.append("TESTS_LOCKED: missing; write the acceptance tests before dispatch, then paste the lines "
                        "`safety_gate.py --lock-tests <test files>` prints (or `- NONE  # why there is no test`)")
        return
    if not items:  # review P1-8: an empty lock locks nothing
        problems.append("TESTS_LOCKED: empty; list the locked tests (`safety_gate.py --lock-tests <test files>`) or "
                        "write `- NONE  # why there is no test`")
        return
    if items == ["NONE"]:  # docs-only work; the reason stays in the order for the reviewer
        if not NONE_WHY.search(text):  # review P2-3
            problems.append("TESTS_LOCKED: `NONE` needs its reason after `#` (`- NONE  # why there is no test`)")
        return
    for item in items:
        parsed = locked_path(item)
        if parsed is None:
            problems.append(f"TESTS_LOCKED: `{item}` is not `<path> sha256=<64 hex>`")
            continue
        rel, sha = parsed
        if candidate:
            blob = _git_blob(repo, candidate, rel.replace("\\", "/"))
            if blob is None:
                problems.append(f"TESTS_LOCKED: {rel} not found in candidate {candidate[:12]} (deleted or missing)")
            elif bytes_hash(blob) != sha:
                problems.append(f"TESTS_LOCKED: {rel} changed in candidate {candidate[:12]} since it was locked; a "
                                "worker may not edit the acceptance tests (report BLOCKED instead)")
            continue
        path = pathlib.Path(repo) / rel
        if not path.is_file():
            problems.append(f"TESTS_LOCKED: {rel} not found under {pathlib.Path(repo).resolve().as_posix()} "
                            "(pass --repo)")
        elif file_hash(path) != sha:
            problems.append(f"TESTS_LOCKED: {rel} changed since it was locked; a worker may not edit the acceptance "
                            "tests (report BLOCKED instead)")


def order_problems(text, repo, config, notes, candidate=None):
    """The safety gates of one Standard / Strict work order (gate_check.py --order and --match): loosening, locked
    tests, the round limit and the AUTO hint. Direct orders: none."""
    gov = governance(text)
    if gov not in GOVERNED:
        return []
    problems = loosening_problems(config, gov, notes)
    if on(config, "tests_first"):
        check_tests(text, repo, problems, notes, candidate=candidate)
    limit = config.get("stop_after_rounds")
    stop = re.search(r"STOP_RULES\s*[:：=]\s*(.*)", text)
    if on(config, "stop_after_rounds") and stop:
        rounds = [int(n) for n in re.findall(r"(\d+)\s*(?:輪|rounds?)", stop.group(1))]
        if not rounds:
            notes.append(f"STOP_RULES: no round count; write 「同一根因 {limit} 輪沒進展就停」")
        elif max(rounds) > limit:
            problems.append(f"STOP_RULES: allows {max(rounds)} rounds on one root cause; at most {limit} "
                            f"(safety.stop_after_rounds, strength {config.get('strength')})")
    if on(config, "prefer_auto") and not re.search(r"^\|\s*AC-\d+\s*\|\s*AUTO\s*\|", text, re.M):
        notes.append("acceptance: no AUTO criterion; prefer a condition a command can decide (safety.prefer_auto)")
    return problems


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


def plan_problems(order_text, ids, approved, repo):
    """plan_gate for --match with --dispatch-log. approved: the rest of each `PLAN_APPROVED <WO> ...` line of the
    order, oldest first (gate_check reads the log)."""
    label = next(iter(ids), "the order")
    if not approved:
        return [f"PLAN_APPROVED: no `PLAN_APPROVED {label} sha=<64>` line in the dispatch log; the worker hands in "
                "<WORK_DIR>/<WO>/PLAN.md and the Director approves it before any code (safety.plan_gate)"]
    sha = re.search(r"\bsha=([0-9a-fA-F]{64})\b", approved[-1] or "")
    plan, why = plan_path(order_text, ids, repo)
    if not sha:
        return ["PLAN_APPROVED: the line has no sha=<64 hex> (safety_gate.py --plan-hash prints it)"]
    if plan is None:
        return [f"PLAN_APPROVED: {why}; the approved plan cannot be compared"]
    if plan_hash(plan) != sha.group(1).lower():
        return [f"PLAN_APPROVED: {plan.as_posix()} differs from the approved plan (more than ticked boxes); a changed "
                "plan goes back to the Director first"]
    open_tasks = re.findall(r"^\s*[-*]\s+\[(?!\s*[xX]\s*\])[^\]\n]*\]\s*(.*)$", plan.read_text(encoding="utf-8-sig"),
                            re.M)
    if open_tasks:
        return [f"PLAN_APPROVED: {len(open_tasks)} task(s) in PLAN.md not ticked, e.g. {open_tasks[0].strip()[:80]}; "
                "finish them or report PARTIAL"]
    return []


def lock_line(rel, digest):
    """One TESTS_LOCKED item; a path with a space is quoted."""
    return f'- "{rel}" sha256={digest}' if re.search(r"\s", rel) else f"- {rel} sha256={digest}"


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock-tests", nargs="+", metavar="FILE", help="print TESTS_LOCKED lines (paths relative to --repo)")
    ap.add_argument("--plan-hash", metavar="PLAN_MD", help="print the PLAN_APPROVED line for this PLAN.md")
    ap.add_argument("--order", help="with --plan-hash: the work order the plan belongs to")
    ap.add_argument("--repo", default=".", help="the project checkout (default: current folder)")
    ap.add_argument("--show", action="store_true", help="print the strength and switches of --config")
    ap.add_argument("--config", metavar="director_work.json", help="with --show (default: none, the defaults)")
    a = ap.parse_args(argv)
    if not (a.lock_tests or a.plan_hash or a.show):
        ap.error("give --lock-tests, --plan-hash or --show")
    status = 0
    if a.show:
        if a.config and not pathlib.Path(a.config).is_file():
            print(f"SAFETY: NOT_RUN config not found: {a.config}")
            return 1
        config, problems = load_config(None, a.config)
        print(f"SAFETY strength={config['strength']} " + " ".join(f"{key}={json.dumps(config[key])}" for key in SWITCHES))
        if DEFAULT_SOURCE:  # 3.0.0 B15
            print(f"  ~ default strength {DEFAULT_STRENGTH} from {DEFAULT_SOURCE} (the variant's default; the base "
                  f"default is {BASE_DEFAULT})")
        for problem in problems:
            print(f"  - {problem}")
        for word, what in loosening(config):
            print(f"  ~ {what}: a Standard / Strict order needs a PO_PENDING answer naming {word}")
        status = 1 if problems else 0
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
                print(f"# outside --repo {root.as_posix()}: {name}")
                status = 1
                continue
            print(lock_line(rel, file_hash(path)))
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

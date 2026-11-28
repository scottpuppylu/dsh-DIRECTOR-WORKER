r"""Rebuild the DIRECTOR-WORK action audit from DeepSeek Harness (DSH) session logs.

DSH has no PreToolUse / PostToolUse hooks, so nothing writes an action log while the agents work. This tool
reconstructs the SAME hash-chained JSONL schema that audit_log.py documents and report_vs_audit.py consumes,
after the fact, from the append-only session event logs:

  sessions/--<normalised cwd>--/<session-id>/session.v4.jsonl.zstd

Every nested tool call a run_code program makes (event tool/ptc-dispatch, e.g. pwsh / read / write) and every
top-level tool call (event tool/call, e.g. run_code / subagent) becomes one line:
  seq, ts (local ISO with offset), session_id, agent_id, tool, tool_use_id, kind (result / failure), input
  (the tool input masked by tools/secret_mask.py; 2.2.5-ds.5, as upstream transcript_audit.py 2.2.5: whole, no
  500-character cut; with --input-limit N cut at N characters and marked "input_cut": true so report_vs_audit.py
  matches that call on its first part only), result (status ok / error / interrupted,
  sha256 and length of the masked output, never the output itself), duration_ms (when the start event is there),
  prev, hash (the same chain algorithm as audit_log.py: sha256 of the line's other fields as sorted compact JSON;
  64 zeros before the first line). A tool call whose result is not in the log yet is kind=failure status=interrupted.
Since 2.2.1-ds.1 (build version 2) line 1 is kind=rebuild, result status rebuilt, with a `source` field (by
"dsh_audit.py", version, sessions with session_id / log file name / sha256 / bytes of the session log read, lines,
warnings, skipped), the same first line as upstream transcript_audit.py 2.2.1, so the log says it was rebuilt after
the fact; report_vs_audit.py prints a note for it. The tool calls follow from seq 2.

Shell tool names are mapped for report_vs_audit.py: pwsh -> PowerShell, bash -> Bash (the original stays in tool_raw
when it differs). The DSH session id is written to session_id; the DSH subagent name (e.g. "w1", from the parent's
subagent catalog) is written to agent_id. report_vs_audit.py --session therefore takes the DSH session id — a TASK
REPORT must write SESSION_ID: <that session id> (agent names select sessions in this tool: --session w1 works here).

  python -I -X utf8 adapters/deepseek/dsh_audit.py build --out FILE [--force] [--log-root DIR] [--cache-root DIR]
      [--project-dir PATH] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--session ID|PREFIX|AGENT] [--json]
      [--input-limit N]
  python -I -X utf8 adapters/deepseek/dsh_audit.py verify --log FILE [--from N --to M] [--anchor-log FILE]
      [--anchor-rev REV --anchor-path PATH [--repo DIR]] [--cite "AUDIT_RANGE ..."]
      (delegates to audit_log.py verify, so the format is not forked; same output and exit codes)

build writes a new file (refuses to overwrite an existing one without --force) and prints one summary line plus the
file's sha256 and head hash; --json prints the summary as JSON. A parent session's subagent catalog and the projection
cache (default <DSH_HOME>/storages/session_projcache/sessions) supply the childId -> agent name mapping.

loops (2.3.0-ds.6; 2.4.0-ds.6: the DW 2.4.0 loop_guard categories, thresholds, reminder count and allow list) reads
the same sessions (same filters) and prints the calls that look like going in circles. It reads only and prints tool
names, hashes, counts and call numbers, never an input, an output or a message (as dsh_usage). DSH has no PreToolUse
hook, so nothing reminds the agent while it works: this is the after-the-fact check (run it at a checkpoint).

  python -I -X utf8 adapters/deepseek/dsh_audit.py loops [--log-root DIR] [--cache-root DIR] [--project-dir PATH] [--since DAY]
      [--until DAY] [--session ID|PREFIX|AGENT] [--events FILE ...] [--config FILE] [--window W] [--repeat N]
      [--retry-errors N] [--poll N] [--ping-pong N] [--bad-args N] [--rounds R] [--show N] [--json] [--out FILE]

Categories (DW 2.4.0 defaults in brackets; all counted within W [20] calls of one session):
  repeat            the same call (tool + hash of the masked input) N [3] times or more
  retry_same_error  the same call failed again with the same error (hash of the masked error) N [2] times in a row,
                    and the agent wrote no text between them (reasoning does not count: the rule asks for a written
                    line; this condition is dshdw's own)
  ping_pong         two calls A, B in turn for N [6] calls or more (--rounds R of 2.3.0-ds.6 = --ping-pong 2R) and
                    neither result changes
  poll_no_progress  a read / query call (read, grep, glob, list_agents, job_list, job_output, team_task_list,
                    team_task_get, acp_status, web_fetch, web_search, read_image, get_goal, search_context,
                    list_subagent_models) gives the same result N [3] times running, each within W calls of the last
  bad_args          N [2] or more calls of one tool refused for their arguments (error code INVALID_ARGS or name
                    ToolArgsError, as DSH logs them, or a top-level arguments string that is not JSON). The BAD_ARGS
                    line still counts every refused call: the count, the share of all calls, the top 5 tools
  child_error_unhandled  the session's last call is a child call (child_tools [subagent, wait_agent]) that failed:
                    nothing after it handled the error. With no child call result in the input it prints
                    `~ NOT_VERIFIED child_error_unhandled` and counts nothing (a measured 0 needs a child result)
count is the largest size the run or window reached; reminders=k is how many reminders DW's live hook would have given
(at the threshold, then 2x, 4x, 8x ...). --config FILE takes the DW 2.4.0 loop_guard schema (all keys optional):
{"schema_version": 1, "window": 20, "repeat": 3, "retry_errors": 2, "poll": 3, "ping_pong": 6, "bad_args": 2,
"child_tools": ["subagent", "wait_agent"], "allow": [{"tool": "PowerShell", "input": "<regex on the masked input>",
"max": 30, "why": "waits for the build"}]}. An allow entry is a planned wait: matching calls are not reported as repeat
or poll_no_progress until they reach "max" (no max: never); a retry with the same error is still reported. The regex
is matched inside the tool and never printed (--json shows only how many entries there are). A number flag on the
command line wins over the file. Each value is 2 or more.

wait_agent is left out of repeat, retry_same_error, ping_pong and poll_no_progress: calling it again while a child
works is the normal way to wait. A forked session repeats its seed's events, so a finding with the same category,
call key and time in several sessions is counted once (copies=N on its line, also_in in --json). One line per finding:
  LOOP <category> tool=T args=<hash> count=N calls=A..B reminders=K session=S agent=A at=<time> <category fields>
then BAD_ARGS, `LOOPS <category>=n ...` (the DW 2.4.0 summary line) and DSH_LOOPS. --events reads plain JSONL event
files (one session each; for synthetic fixtures) instead of the DSH logs.
2.5.0-ds.6 (DW 2.5.0 F1): --since / --until count only the calls made in [since, until) by each call's own time, so a
session that runs over several days gives each day its own count (2.4.0-ds.6 took whole sessions by their start time,
so a session started before --since was left out and one that went on after --until was counted whole). A session
started after --until is skipped; a call with no readable time is left out when a window is given. --events files get
the same call window. --json prints the result as JSON; --out FILE
also writes that JSON (status_gen.py's "loops" section reads it; dsh_usage.py prints its LOOPS line).

  python -I -X utf8 adapters/deepseek/dsh_audit.py reads [same session filters] [--events FILE ...] [--top 20] [--json]

reads (2.5.0-ds.6, DW 2.5.0 usage_mix --reads) lists the most re-read paths of the same sessions: how often each was
read (DSH's read tool, or a pwsh / bash cat / head / tail / sed -n / Get-Content) and how many bytes those reads
brought back (what entered the context). DSH logs token usage per model step, not per tool call, so the per-path cost
DW prints is NOT_VERIFIED here. --since / --until go by each call's own time, as loops. It prints file paths, so keep
its output local. One line per path, `READS <n>x <bytes> <path>`, then DSH_READS. Exit 0, 2 when it cannot read.

Exit codes: 0 written / verified / no loop found, 1 refused (output exists without --force) or a write problem, or
loops found something, 2 cannot run (no Node for zstd, sessions root missing, nothing to audit, a read error, bad
usage). Requires Node 22+ for zstd; there is no
offline Python zstd in 3.12. The log records facts read from the files; it cannot prove the agent did nothing else.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shlex
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
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dsh = load_local("dsh_session")
audit = load_local("audit_log")

TOOL = "dsh_audit"
BUILD_VERSION = 2  # 2: line 1 is kind=rebuild with a source field (2.2.1-ds.1)
INPUT_LIMIT = None  # 2.2.5-ds.5: None keeps each input whole (upstream 2.2.5 H1); build --input-limit N sets it
TOOL_NAMES = {"pwsh": "PowerShell", "powershell": "PowerShell", "bash": "Bash", "sh": "Bash", "zsh": "Bash"}


def map_tool(name):
    if not isinstance(name, str) or not name:
        return "unknown", None
    mapped = TOOL_NAMES.get(name.lower())
    return (mapped, name) if mapped else (name, None)


def text_of(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def encodable(value):
    """3.0.0-ds.8 (review P1-2): VALUE with every string made encodable as UTF-8. A DSH log keeps a cut emoji as a lone
    surrogate (\\ud83e); the base audit_log hashes text.encode("utf-8"), which refuses it. A lone surrogate becomes
    U+FFFD, a surrogate pair is joined into its character, any other text is returned as it is (dict keys too)."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
            return value
        except UnicodeEncodeError:
            return value.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    if isinstance(value, dict):
        return {encodable(key): encodable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encodable(item) for item in value]
    return value


def parse_arguments(value):
    """A tool input as a JSON-like value: event arguments may be a JSON string (tool/call) or an object (ptc-dispatch)."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("{", "["):
            try:
                return json.loads(stripped)
            except ValueError:
                return value
        return value
    return value


def duration(start_ms, end_ms):
    """Milliseconds from start to end, or None when either is missing or negative."""
    if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
        return None
    if isinstance(start_ms, bool) or isinstance(end_ms, bool):
        return None
    value = int(end_ms) - int(start_ms)
    return value if value >= 0 else None


def start_time(candidates, end_ms):
    """The latest start time not after the end event (a call is retried, so take the one that ended)."""
    usable = [ms for ms in candidates if isinstance(ms, (int, float)) and not isinstance(ms, bool)
              and (end_ms is None or ms <= end_ms)]
    return max(usable) if usable else None


def make_entry(session_id, agent_id, tool, tool_use_id, kind, raw_input, status, output, duration_ms, event_ms, tool_raw):
    """One audit line (before seq/prev/hash are chained on). Every text is made encodable first (encodable)."""
    session_id, agent_id, tool, tool_use_id, tool_raw = encodable([session_id, agent_id, tool, tool_use_id, tool_raw])
    raw_input, output = encodable(raw_input), encodable(output)
    entry = {
        "ts": dsh.iso_from_ms(event_ms),
        "session_id": session_id,
        "agent_id": agent_id,
        "tool": tool,
    }
    if tool_raw:
        entry["tool_raw"] = tool_raw
    entry["tool_use_id"] = tool_use_id
    entry["kind"] = kind
    entry["input"] = audit.summary(raw_input, INPUT_LIMIT)
    if INPUT_LIMIT is not None and entry["input"] != audit.summary(raw_input, None):
        entry["input_cut"] = True  # 2.2.5-ds.5: marked, so the reader matches this call on its first part (已截斷)
    entry["result"] = audit.output_record(status, output)
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    return entry


def session_entries(events, session_id, agent_id, warnings):
    """[audit line] for the tool actions in one session's events, in event order. Each item also keeps the raw
    "_output" (2.4.0-ds.6, for inject); build never writes it: the log holds only the masked output's hash."""
    starts = {}
    for event in events:
        if event.get("type") != "tool/ptc-dispatch-start":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        sub_id = data.get("subCallId")
        if isinstance(sub_id, str) and sub_id:
            starts.setdefault(sub_id, []).append(event.get("time"))
    results = {}
    for event in events:
        if event.get("type") != "tool/result":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        call_id = message.get("toolCallId") or data.get("toolCallId") or (message.get("source") or {}).get("callId")
        if isinstance(call_id, str) and call_id:
            results[call_id] = event
    entries = []
    for event in events:
        kind = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        event_ms = event.get("time")
        seq = event.get("seq")
        if kind == "tool/ptc-dispatch":
            name, raw = map_tool(data.get("name"))
            sub_id = data.get("subCallId")
            failed = bool(data.get("isError"))
            output = data.get("content")
            if failed and output is None:
                output = {"error": data.get("error")}
            output = encodable(output)  # "_output" too (inject, reads): the same text the hash is made of
            entries.append({
                "entry": make_entry(session_id, agent_id, name, sub_id, "failure" if failed else "result",
                                    parse_arguments(data.get("arguments")), "error" if failed else "ok", output,
                                    duration(start_time(starts.get(sub_id) or [], event_ms), event_ms),
                                    event_ms, raw),
                "_ms": event_ms, "_seq": seq if isinstance(seq, int) else -1, "_output": output})
        elif kind == "tool/call":
            name, raw = map_tool(data.get("name"))
            call_id = data.get("callId")
            result = results.get(call_id)
            result_data = result.get("data") if result is not None and isinstance(result.get("data"), dict) else {}
            message = result_data.get("message") if isinstance(result_data.get("message"), dict) else {}
            failed = bool(message.get("isError") or result_data.get("isError"))
            output = message.get("content")
            error = result_data.get("error")
            if error is not None:
                output = {"content": output, "error": error} if output is not None else error
            output = encodable(output)
            status = "error" if failed or error is not None else ("ok" if result is not None else "interrupted")
            entries.append({
                "entry": make_entry(session_id, agent_id, name, call_id,
                                    "failure" if status != "ok" else "result",
                                    parse_arguments(data.get("arguments")), status, output,
                                    duration(event_ms, result.get("time")) if result is not None else None,
                                    event_ms, raw),
                "_ms": event_ms, "_seq": seq if isinstance(seq, int) else -1, "_output": output})
    return entries


def header_info(events, fallback_id):
    """(session_id, cwd, created_ms, is_worker, parent) from the session header event, with sensible fallbacks."""
    header = dsh.session_header(events)
    session_id = header.get("id") if isinstance(header.get("id"), str) and header.get("id") else fallback_id
    depth = header.get("delegationDepth")
    worker = header.get("origin") == "subagent" or (isinstance(depth, int) and depth > 0)
    return (session_id, header.get("cwd"), header.get("createdAt"), worker, header.get("parentSession"))


def collect_catalog(events, catalog):
    """childId -> name from this log's subagent/catalog events (parents name their children here)."""
    for event in events:
        if event.get("type") != "subagent/catalog":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        child, name = data.get("childId"), data.get("name")
        if isinstance(child, str) and child and isinstance(name, str) and name:
            catalog.setdefault(child, {"name": name, "label": data.get("label"), "parent": None})


def matches_session(args, session_id, cwd, created_ms, agent, catalog, by_calls=False):
    """Whether one session passes --session / --project-dir / --since / --until. by_calls (2.5.0-ds.6, loops): the
    dates are checked per call later (in_window), so here only a session started after --until is left out."""
    if args.session:
        wanted = [value.lower() for value in args.session]
        id_lower = session_id.lower()
        bare = id_lower[len(dsh.ROOT_PREFIX):] if id_lower.startswith(dsh.ROOT_PREFIX) else id_lower
        name = (agent or "").lower()
        labels = []
        entry = catalog.get(session_id)
        if entry and isinstance(entry.get("label"), str):
            labels.append(entry["label"].lower())
        if not any(w in id_lower or bare.startswith(w) or id_lower.startswith(w) or (name and w == name)
                   or any(w in label for label in labels) for w in wanted):
            return False
    if args.project_dir:
        if not cwd or not any(dsh.path_is_under(cwd, root) for root in args.project_dir):
            return False
    if by_calls:
        if args.until and isinstance(created_ms, (int, float)) and not isinstance(created_ms, bool):
            if datetime.datetime.fromtimestamp(created_ms / 1000.0).astimezone() >= dsh.parse_day(args.until, end=True):
                return False
        return True
    if args.since or args.until:
        if not isinstance(created_ms, (int, float)) or isinstance(created_ms, bool):
            return False
        when = datetime.datetime.fromtimestamp(created_ms / 1000.0).astimezone()
        if args.since and when < dsh.parse_day(args.since):
            return False
        if args.until and when >= dsh.parse_day(args.until, end=True):
            return False
    return True


def file_record(path):
    """Name, sha256 and size of a session log file, for the rebuild line's source (None values when unreadable)."""
    try:
        data = pathlib.Path(path).read_bytes()
    except OSError:
        return {"log": pathlib.Path(path).name, "sha256": None, "bytes": None}
    return {"log": pathlib.Path(path).name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def chain_lines(entries, source, now=None):
    """The kind=rebuild first line, then the entries (dicts, changed in place), hash-chained from seq 1 by
    audit_log.py's rule. Returns (lines, head hash)."""
    stamp = now or datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
    first = {"ts": stamp, "session_id": None, "agent_id": None, "tool": None, "tool_use_id": None, "input": "",
             "kind": "rebuild", "result": {"status": "rebuilt"}, "duration_ms": None, "source": source}
    prev = audit.GENESIS
    lines = []
    for seq, entry in enumerate([first] + list(entries), 1):
        entry.pop("hash", None)
        entry["seq"] = seq
        entry["prev"] = prev
        entry["hash"] = audit.digest(entry)
        prev = entry["hash"]
        lines.append(audit.canonical(entry) + "\n")
    return lines, prev


def session_files(args, warnings):
    """(session files, projections, catalog) under --log-root / --cache-root (shared by build and loops)."""
    log_root = pathlib.Path(args.log_root).expanduser() if args.log_root else dsh.default_sessions_root()
    cache_root = pathlib.Path(args.cache_root).expanduser() if args.cache_root else dsh.default_projcache_root()
    sessions = dsh.list_session_files(log_root)
    projections = {}
    if cache_root.is_dir():
        projections = dsh.load_projections(cache_root)
        for projection in projections.values():
            if projection.error:
                warnings.append(f"projection {projection.session_id}: {projection.error}")
    else:
        warnings.append(f"projection cache not found: {cache_root} (agent names may be missing)")
    return sessions, projections, dsh.agent_catalog(projections)


def _matches_meta_project_and_time(args, cwd, created_ms, have_meta, per_call=False):
    """Cheap pre-filter on project_dir and date range when projection or header metadata is known."""
    if not have_meta:
        return True
    if args.project_dir:
        if not cwd or not any(dsh.path_is_under(cwd, root) for root in args.project_dir):
            return False
    if per_call:
        if args.until and isinstance(created_ms, (int, float)) and not isinstance(created_ms, bool):
            if datetime.datetime.fromtimestamp(created_ms / 1000.0).astimezone() >= dsh.parse_day(args.until, end=True):
                return False
        return True
    if args.since or args.until:
        if not isinstance(created_ms, (int, float)) or isinstance(created_ms, bool):
            return False
        when = datetime.datetime.fromtimestamp(created_ms / 1000.0).astimezone()
        if args.since and when < dsh.parse_day(args.since):
            return False
        if args.until and when >= dsh.parse_day(args.until, end=True):
            return False
    return True


def selected_sessions(args, sessions, projections, catalog, warnings, skipped, by_calls=False):
    """Yield (index, ref, events, header_id, agent_id, role, name_source, cwd, created_ms, parent) for each session
    that passes the filters, roots before subagents so uncached subagent/catalog events enrich child names first."""
    ordered = sorted(sessions, key=lambda item: (not item.session_id.startswith(dsh.ROOT_PREFIX), item.session_id))
    has_filters = bool(args.session or args.project_dir or args.since or args.until)
    has_subagents = any(not item.session_id.startswith(dsh.ROOT_PREFIX) for item in ordered)
    hdr_map = {}
    if has_filters:
        need_header = []
        for ref in ordered:
            proj = projections.get(ref.session_id)
            if proj is None or not proj.record:
                need_header.append(ref.path)
                continue
            ident = proj.identity()
            if args.project_dir and not ident.get("cwd"):
                need_header.append(ref.path)
            elif (args.since or args.until) and not isinstance(ident.get("createdAt"), (int, float)):
                need_header.append(ref.path)
        if need_header:
            hdr_map = dsh.decode_headers(need_header)
    for index, ref in enumerate(ordered):
        if has_filters:
            proj = projections.get(ref.session_id)
            hdr, _ = hdr_map.get(str(ref.path), (None, []))
            have_meta = bool((proj and proj.record) or isinstance(hdr, dict))
            ident = proj.identity() if (proj and proj.record) else {}
            cid = (hdr.get("id") if isinstance(hdr, dict) and isinstance(hdr.get("id"), str) and hdr.get("id")
                   else None) or ref.session_id
            mcwd = ident.get("cwd") if isinstance(ident.get("cwd"), str) and ident.get("cwd") else (
                hdr.get("cwd") if isinstance(hdr, dict) else None)
            mms = ident.get("createdAt") if (isinstance(ident.get("createdAt"), (int, float))
                                             and not isinstance(ident.get("createdAt"), bool)) else (
                hdr.get("createdAt") if isinstance(hdr, dict) else None)
            if not _matches_meta_project_and_time(args, mcwd, mms, have_meta, by_calls):
                continue
            if args.session and have_meta:
                if isinstance(hdr, dict):
                    depth = hdr.get("delegationDepth")
                    worker = hdr.get("origin") == "subagent" or (isinstance(depth, int) and depth > 0)
                elif proj and proj.record:
                    worker = dsh.session_role(cid, proj)[0] == "worker"
                else:
                    worker = not cid.startswith(dsh.ROOT_PREFIX)
                mrole = "worker" if worker else "director"
                magent, _ = dsh.session_agent(cid, mrole, catalog, proj)
                if not matches_session(args, cid, mcwd, mms, magent, catalog, by_calls):
                    # An uncached root may hold subagent/catalog events needed to match subagents by name.
                    if worker or (proj and proj.record) or not has_subagents:
                        continue
        events, noted = dsh.read_events(ref.path)
        warnings.extend(f"{ref.session_id}: {note}" for note in noted)
        if not events:
            skipped.append({"session_id": ref.session_id, "reason": "no events decoded"})
            continue
        header_id, cwd, created_ms, worker, parent = header_info(events, ref.session_id)
        collect_catalog(events, catalog)
        role = "worker" if worker else "director"
        agent, name_source = dsh.session_agent(header_id, role, catalog, projections.get(header_id))
        if not matches_session(args, header_id, cwd, created_ms, agent, catalog, by_calls):
            continue
        yield index, ref, events, header_id, agent or header_id, role, name_source, cwd, created_ms, parent


def build(args):
    """Write the audit log; returns the summary dict (raises DshError for cannot-run cases)."""
    global INPUT_LIMIT
    INPUT_LIMIT = getattr(args, "input_limit", 0) or None  # 2.2.5-ds.5: 0 / None = keep each input whole
    warnings = []
    sessions, projections, catalog = session_files(args, warnings)
    entries = []
    audited = []
    skipped = []
    for (index, ref, events, header_id, agent_id, role, name_source, cwd, created_ms,
         parent) in selected_sessions(args, sessions, projections, catalog, warnings, skipped):
        found = session_entries(events, header_id, agent_id, warnings)
        for item in found:
            item["_session"] = header_id
            item["_index"] = index
        entries.extend(found)
        audited.append({"session_id": header_id, "agent_id": agent_id, "cwd": cwd,
                        "started": dsh.iso_from_ms(created_ms), "role": role,
                        "events": len(events), "lines": len(found),
                        "agent_source": name_source, "parent": parent,
                        "log_file": str(ref.path), "_file": file_record(ref.path)})
    if not entries:
        raise dsh.DshError("nothing to audit: no tool calls found in the selected sessions"
                           + (f" ({len(sessions)} session log(s) read)" if sessions else ""))
    entries.sort(key=lambda item: (item["_ms"] if isinstance(item["_ms"], (int, float)) else 0,
                                   item["_index"], item["_seq"]))
    files = [dict(session_id=item["session_id"], **item.pop("_file")) for item in audited]
    source = {"by": "dsh_audit.py", "version": BUILD_VERSION, "sessions": files, "lines": len(entries),
              "warnings": len(warnings), "skipped": len(skipped), "input_limit": INPUT_LIMIT}
    lines, head = chain_lines([item["entry"] for item in entries], source)
    kinds = {}
    tools = {}
    for item in entries:
        entry = item["entry"]
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
        tools[entry["tool"]] = tools.get(entry["tool"], 0) + 1
    out = pathlib.Path(args.out).expanduser()
    if out.exists() and not args.force:
        raise BuildRefused(f"refusing to overwrite {out}; pass --force to replace an existing audit log")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(lines).encode("utf-8")
    try:
        temp = out.with_name(out.name + ".tmp")
        with open(temp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, out)
    except OSError as error:
        raise BuildRefused(f"cannot write {out}: {error}") from error
    first_ts = entries[0]["entry"].get("ts")
    last_ts = entries[-1]["entry"].get("ts")
    return {
        "tool": TOOL,
        "version": BUILD_VERSION,
        "command": "build",
        "out": str(out),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "lines": len(entries),
        "rebuild_line": 1,
        "sessions": audited,
        "sessions_total": len(sessions),
        "kinds": kinds,
        "tools": tools,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "head_seq": len(lines),
        "head_hash": head,
        "warnings": warnings,
        "skipped": skipped,
        "note": "after-the-fact reconstruction from DSH session logs; DSH has no real-time hook",
    }


class BuildRefused(Exception):
    """The output file cannot be written (exists without --force, or an OS error)."""


def cmd_build(args):
    try:
        summary = build(args)
    except dsh.DshError as error:
        print(f"NOT_RUN {error}")
        return 2
    except BuildRefused as error:
        print(f"REFUSED {error}")
        return 1
    except dsh.NodeMissing as error:
        print(f"NOT_RUN {error}")
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    warnings = summary["warnings"]
    print(f"DSH_AUDIT sessions={len(summary['sessions'])} lines={summary['lines']} "
          f"kinds={','.join(f'{k}:{v}' for k, v in sorted(summary['kinds'].items()))} "
          f"first={summary['first_ts']} last={summary['last_ts']}")
    hidden = []
    for tool_name, count in sorted(summary["tools"].items(), key=lambda pair: (-pair[1], pair[0])):
        if len(hidden) < 10:
            hidden.append(f"{tool_name}:{count}")
    print("TOOLS " + ", ".join(hidden) + (" ..." if len(summary["tools"]) > 10 else ""))
    for session in summary["sessions"]:
        print(f"  {session['session_id']} agent={session['agent_id']} role={session['role']} "
              f"events={session['events']} lines={session['lines']}")
    print(f"WROTE {summary['out']} sha256={summary['sha256']} head_seq={summary['head_seq']} "
          f"head_hash={summary['head_hash']}")
    for warning in warnings[:8]:
        print(f"  ~ {warning}")
    if len(warnings) > 8:
        print(f"  ~ ... {len(warnings) - 8} more warning(s); see --json")
    return 0


# ---------------------------------------------------------------- loops (2.3.0-ds.6, 2.4.0-ds.6)

LOOPS_VERSION = 3  # 3 (3.0.0-ds.8): the detection is the base tools/loop_guard.py core (series plan D5), one copy
loop_guard = load_local("loop_guard")
CATEGORIES = loop_guard.CATEGORIES
THRESHOLD = loop_guard.THRESHOLD
# DSH names for the base config keys: a child is started with subagent and waited on with wait_agent; waiting on a
# child is calling wait_agent again, so it is a wait tool (left out of repeat, retry, poll and ping_pong)
DSH_DEFAULTS = {"child_tools": ["subagent", "wait_agent"], "wait_tools": ["wait_agent"]}
BAD_ARGS_CODES = ("INVALID_ARGS",)  # as the DSH logs write a refused argument (error.code / error.name)
BAD_ARGS_NAMES = ("ToolArgsError",)
LoopConfigError = loop_guard.InputError  # a loops --config file or value cannot be used (NOT_RUN, exit 2)


def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def loop_config(raw=None):
    """The base loop_guard config (same schema and checks) with the DSH tool names where raw does not set them."""
    conf = loop_guard.config(raw)
    for key, value in DSH_DEFAULTS.items():
        if not (isinstance(raw, dict) and key in raw):
            conf[key] = list(value)
    return conf


def loop_settings(args):
    """The settings of one loops run: defaults, then --config FILE, then the number flags given on the command line
    (--rounds R, the 2.3.0-ds.6 flag, is --ping-pong 2R)."""
    path = getattr(args, "config", None)
    raw = None
    if path:
        try:
            raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        except OSError as error:
            raise LoopConfigError(f"config {path}: {error}") from None
        except ValueError as error:
            raise LoopConfigError(f"config {path}: not JSON: {error}") from None
    conf = loop_config(raw)
    flags = ("window", "repeat", "retry_errors", "poll", "ping_pong", "bad_args")
    for key in flags:
        value = getattr(args, key, None)
        if value is not None:
            conf[key] = value
    rounds = getattr(args, "rounds", None)
    if rounds is not None and getattr(args, "ping_pong", None) is None:
        conf["ping_pong"] = 2 * rounds
    for key in flags:
        if conf[key] < 2:
            raise LoopConfigError(f"--{key.replace('_', '-')} {conf[key]} is too small (2 or more)")
    return conf


def reminders(count, threshold):
    """How many reminders a live hook would have given up to this count (DSH has none: after-the-fact only)."""
    return sum(1 for n in range(1, count + 1) if loop_guard.should_remind(n, threshold))


def call_problems(events):
    """{call id: reason} for calls whose arguments the tool refused, or whose arguments string is not JSON."""
    found = {}
    errors = {}
    for event in events:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        kind = event.get("type")
        if kind == "tool/ptc-dispatch":
            errors[data.get("subCallId")] = data.get("error")
        elif kind == "tool/result":
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            errors[message.get("toolCallId") or data.get("toolCallId")] = data.get("error")
        elif kind == "tool/call" and isinstance(data.get("arguments"), str):
            try:
                json.loads(data["arguments"])
            except ValueError:
                found[data.get("callId")] = "ARGS_NOT_JSON"
    for call_id, error in errors.items():
        if isinstance(error, dict) and (error.get("code") in BAD_ARGS_CODES or error.get("name") in BAD_ARGS_NAMES):
            found.setdefault(call_id, str(error.get("code") or error.get("name")))
    return found


def text_positions(events):
    """Event positions of assistant messages that carry written text (a "text" part; reasoning is not counted)."""
    positions = []
    for position, event in enumerate(events):
        if event.get("type") != "assistant/message":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        parts = message.get("content") if isinstance(message.get("content"), list) else []
        if any(isinstance(part, dict) and part.get("type") == "text" and str(part.get("text") or "").strip()
               for part in parts):
            positions.append(position)
    return positions


def event_positions(events):
    """{("sub" | "call", id): event position} of the tool calls in one session's events."""
    position = {}
    for index, event in enumerate(events):
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("type") == "tool/ptc-dispatch":
            position[("sub", data.get("subCallId"))] = index
        elif event.get("type") == "tool/call":
            position[("call", data.get("callId"))] = index
    return position


def session_calls(events, session_id, agent_id, warnings):
    """The session's calls in event order: number, tool, key (hash of tool + masked input), status, result hash,
    time, event position, refused-argument reason. Reuses session_entries (same parsing and masking as build).
    _input (the masked input) is kept for allow entries only and never goes into a finding."""
    position = event_positions(events)
    problems = call_problems(events)
    calls = []
    for item in session_entries(events, session_id, agent_id, warnings):
        entry = item["entry"]
        call_id = entry.get("tool_use_id")
        where = position.get(("sub", call_id), position.get(("call", call_id), -1))
        calls.append({"n": len(calls) + 1, "tool": entry["tool"],
                      "key": short_hash(entry["tool"] + "\n" + entry["input"]),
                      "status": entry["result"]["status"], "result": entry["result"]["sha256"][:12],
                      "ts": entry["ts"], "pos": where, "bad": problems.get(call_id), "_input": entry["input"]})
    return calls


def core_events(calls, session_id, agent_id, texts=()):
    """The calls as base loop_guard events. A DSH log keeps the error code of every refused call, so the error class
    is always known: "validation" for a refused argument, "other" for any other error. text_before (base 3.0.0 B17)
    says the agent wrote text after the previous call and before this one; the base core then drops a ping_pong whose
    results change and counts a retry only while no text answers the error (the two ds.7 checks, now in the base)."""
    events, previous = [], -1
    for c in calls:
        events.append({"seq": c["n"], "session": session_id, "agent": agent_id, "tool": c["tool"], "args": c["key"],
                       "input": c["_input"], "status": c["status"], "result": c["result"],
                       "error_class": "validation" if c["bad"] else ("other" if c["status"] == "error" else None),
                       "error_text_known": True, "text_before": any(previous < p < c["pos"] for p in texts)})
        previous = c["pos"]
    return events


def loop_findings(calls, session_id, agent_id, settings, texts=()):
    """[finding] of one session's calls: the base loop_guard.detect findings with the DSH fields added (call number
    and time where the finding ends, reminders, the window and total of a repeat, the reasons of bad_args) and the
    text positions passed on to the base core (base 3.0.0 B17 drops a ping_pong whose results change and a retry the
    agent answered in text)."""
    by_n = {c["n"]: c for c in calls}
    found = []
    for hit in loop_guard.detect(core_events(calls, session_id, agent_id, texts), settings):
        category = hit["category"]
        first, last = by_n[hit["first"]], by_n[hit["last"]]
        threshold = settings.get(THRESHOLD[category]) if THRESHOLD[category] else None
        row = {"category": category, "session_id": session_id, "agent_id": agent_id, "call": last["n"],
               "ts": last["ts"], "tool": hit["tools"][0], "key": hit["args"][0], "count": hit["count"],
               "first": first["n"], "last": last["n"],
               "reminders": reminders(hit["count"], threshold) if threshold else 0}
        if category == "ping_pong":
            row.update(other_tool=hit["tools"][1], other_key=hit["args"][1])
        elif category == "repeat":
            row.update(window=settings["window"], total=sum(1 for c in calls if c["key"] == row["key"]))
        elif category == "bad_args":
            refused = [c for c in calls if c["bad"] and c["tool"] == row["tool"] and first["n"] <= c["n"] <= last["n"]]
            row.update(reason=",".join(sorted({c["bad"] for c in refused})), distinct=len(hit["args"]))
        if category in ("retry_same_error", "poll_no_progress", "child_error_unhandled"):
            row["result"] = hit["result"]
        found.append(row)
    rank = {name: index for index, name in enumerate(CATEGORIES)}
    found.sort(key=lambda row: (row["call"], rank[row["category"]]))
    return found


def loop_coverage(calls, settings):
    """What the input lets us check: a child call with a result (child_error_unhandled). DSH logs keep the error
    code of every refused call, so bad_args is always checked (unlike a DW action log without error text)."""
    return {"error_text": True,
            "child_results": any(c["tool"] in settings["child_tools"] and c["status"] in ("ok", "error") for c in calls)}


def call_window(args):
    """2.5.0-ds.6 (DW 2.5.0 F1): (since, until) as aware local datetimes for [since, until) from --since / --until
    (local dates, --until inclusive), None where not given."""
    since = dsh.parse_day(args.since) if getattr(args, "since", None) else None
    until = dsh.parse_day(args.until, end=True) if getattr(args, "until", None) else None
    return since, until


def in_window(ts, since=None, until=None):
    """2.5.0-ds.6 (DW 2.5.0 F1): True when a call's own time (its ISO "ts") is in [since, until); with no window every
    call counts, with a window a call without a readable time does not."""
    if since is None and until is None:
        return True
    try:
        moment = datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return False
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return not ((since and moment < since) or (until and moment >= until))


def event_sources(args, warnings, skipped, by_calls=False):
    """[(session id, agent id, events)] for loops / inject: the --events files (plain JSONL, one session each), else
    the DSH session logs that pass the filters (raises DshError / NodeMissing when they cannot be read). by_calls
    (2.5.0-ds.6, loops): the dates are left to the per-call window."""
    if getattr(args, "events", None):
        selected = []
        for name in args.events:
            path = pathlib.Path(name)
            try:
                events, noted = dsh.parse_jsonl(path.read_text(encoding="utf-8-sig"))
            except OSError as error:
                raise dsh.DshError(f"cannot read {path}: {error}") from error
            warnings.extend(f"{path.name}: {note}" for note in noted)
            header_id, _, _, worker, _ = header_info(events, path.stem)
            agent, _ = dsh.session_agent(header_id, "worker" if worker else "director", {}, None)
            selected.append((header_id, agent or header_id, events))
        return selected
    sessions, projections, catalog = session_files(args, warnings)
    if not sessions:
        raise dsh.DshError("no DSH session logs found")
    return [(item[3], item[4], item[2]) for item in
            selected_sessions(args, sessions, projections, catalog, warnings, skipped, by_calls)]


def loops(args):
    """The loops result dict (raises DshError / NodeMissing when the logs cannot be read, LoopConfigError)."""
    settings = loop_settings(args)
    warnings, skipped, sessions_read = [], [], []
    selected = event_sources(args, warnings, skipped, by_calls=True)
    since, until = call_window(args)
    findings, total, first, child_results, rejected, tools = [], 0, {}, False, set(), {}
    for header_id, agent_id, events in selected:
        calls = [call for call in session_calls(events, header_id, agent_id, warnings)
                 if in_window(call["ts"], since, until)]  # 2.5.0-ds.6 (F1): each call by its own time
        if (since or until) and not calls:
            continue  # no call of this session in the window
        total += len(calls)
        child_results = child_results or loop_coverage(calls, settings)["child_results"]
        for call in calls:
            if call["bad"] and (call["tool"], call["key"], call["ts"]) not in rejected:  # a forked copy counts once
                rejected.add((call["tool"], call["key"], call["ts"]))
                tools[call["tool"]] = tools.get(call["tool"], 0) + 1
        sessions_read.append({"session_id": header_id, "agent_id": agent_id, "calls": len(calls)})
        for row in loop_findings(calls, header_id, agent_id, settings, text_positions(events)):
            # a forked DSH session carries its seed's events: the same finding (same call, same time) is counted once
            same = (row["category"], row["tool"], row["key"], row["ts"])
            if same in first:
                first[same].setdefault("also_in", []).append(header_id)
                continue
            first[same] = row
            findings.append(row)
    counts = {name: sum(1 for row in findings if row["category"] == name) for name in CATEGORIES}
    top = sorted(tools.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
    shown = {k: v for k, v in settings.items() if k != "allow"}
    shown["allow"] = len(settings["allow"])  # the entries' regexes are not echoed
    return {"tool": TOOL, "command": "loops", "version": LOOPS_VERSION, "settings": shown,
            "sessions": len(sessions_read), "calls": total, "findings_total": len(findings), "counts": counts,
            "bad_args": {"count": len(rejected), "calls": total,
                         "ratio": round(len(rejected) / total, 6) if total else 0.0,
                         "top": top, "findings": counts["bad_args"]},
            "coverage": {"error_text": True, "child_results": child_results},
            "not_verified": [] if child_results else ["child_error_unhandled"], "findings": findings,
            "per_session": sessions_read, "warnings": warnings, "skipped": skipped}


def loop_line(row):
    """One LOOP line, in the DW 2.4.0 loop_guard order (category, tool, args hash, count, calls), then DSH fields."""
    tools = row["tool"] + (f",{row['other_tool']}" if row["category"] == "ping_pong" else "")
    args = row["key"] + (f",{row['other_key']}" if row["category"] == "ping_pong" else "")
    if row["category"] == "bad_args":
        args = f"{row['distinct']}_distinct"
    calls = f"{row['first']}..{row['last']}" if row["first"] != row["last"] else f"{row['first']}"
    extra = {"repeat": lambda: f" window={row['window']} total={row['total']}",
             "retry_same_error": lambda: f" result={row['result']}",
             "ping_pong": lambda: "",
             "poll_no_progress": lambda: f" result={row['result']}",
             "bad_args": lambda: f" reason={row['reason']}",
             "child_error_unhandled": lambda: f" result={row['result']} last_call"}[row["category"]]()
    copies = f" copies={1 + len(row['also_in'])}" if row.get("also_in") else ""
    return (f"LOOP {row['category']} tool={tools} args={args} count={row['count']} calls={calls} "
            f"reminders={row['reminders']} session={row['session_id']} agent={row['agent_id']} at={row['ts']}"
            f"{extra}{copies}")


def summary_line(result):
    """`LOOPS ...` (DW 2.4.0 usage_mix / status format): counts per category, NOT_VERIFIED where the input is short."""
    parts = []
    for name in CATEGORIES:
        if name in result.get("not_verified", []):
            parts.append(f"{name}=NOT_VERIFIED")
        else:
            parts.append(f"{name}={result['counts'].get(name, 0)}")
    return (f"LOOPS {' '.join(parts)} calls={result['calls']} sessions={result['sessions']} "
            "(dsh_audit.py loops for details)")


def cmd_loops(args):
    try:
        result = loops(args)
    except LoopConfigError as error:
        print(f"NOT_RUN {error}")
        return 2
    except (dsh.DshError, dsh.NodeMissing) as error:
        print(f"NOT_RUN {error}")
        return 2
    if args.out:
        out = pathlib.Path(args.out).expanduser()
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
        except OSError as error:
            print(f"NOT_RUN cannot write {out}: {error}")
            return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1 if result["findings_total"] else 0
    for category in CATEGORIES:
        rows = [row for row in result["findings"] if row["category"] == category]
        for row in rows[:args.show]:
            print(loop_line(row))
        if len(rows) > args.show:
            print(f"  ... {len(rows) - args.show} more {category} finding(s); see --json")
    bad = result["bad_args"]
    top = ", ".join(f"{name}:{count}" for name, count in bad["top"]) or "-"
    print(f"BAD_ARGS count={bad['count']} of {bad['calls']} calls ({100 * bad['ratio']:.2f}%) top={top}")
    for name in result["not_verified"]:
        print(f"~ NOT_VERIFIED {name}: no child ({', '.join(result['settings']['child_tools'])}) result in the input")
    print(summary_line(result))
    print(f"DSH_LOOPS sessions={result['sessions']} calls={result['calls']} findings={result['findings_total']} "
          + " ".join(f"{name}={count}" for name, count in result["counts"].items())
          + (f" out={args.out}" if args.out else ""))
    for warning in result["warnings"][:8]:
        print(f"  ~ {warning}")
    if len(result["warnings"]) > 8:
        print(f"  ~ ... {len(result['warnings']) - 8} more warning(s); see --json")
    return 1 if result["findings_total"] else 0


# ---------------------------------------------------------------- inject (2.4.0-ds.6)

INJECT_VERSION = 1


def inject(args):
    """Prompt-injection findings in the tool outputs of the selected sessions (DW 2.4.0 inject_scan.scan_text on each
    output): category, session, agent, call number, tool, time, line of the output. Never the output or the match."""
    scanner = load_local("inject_scan")
    warnings, skipped = [], []
    findings, first, calls, scanned = [], {}, 0, 0
    sessions = event_sources(args, warnings, skipped)
    tools = set(getattr(args, "tool", None) or [])
    for header_id, agent_id, events in sessions:
        for n, item in enumerate(session_entries(events, header_id, agent_id, warnings), 1):
            calls += 1
            entry = item["entry"]
            if tools and entry["tool"] not in tools:
                continue
            text = "\n".join(scanner.text_of(item.get("_output")))
            if not text:
                continue
            scanned += 1
            for category, line in scanner.scan_text(text):
                row = {"category": category, "session_id": header_id, "agent_id": agent_id, "call": n,
                       "tool": entry["tool"], "ts": entry["ts"], "line": line}
                same = (category, entry["tool"], entry["ts"], line)  # a forked session repeats its seed's events
                if same in first:
                    first[same].setdefault("also_in", []).append(header_id)
                    continue
                first[same] = row
                findings.append(row)
    counts = {name: sum(1 for row in findings if row["category"] == name) for name in scanner.CATEGORIES}
    return {"tool": TOOL, "command": "inject", "version": INJECT_VERSION, "sessions": len(sessions), "calls": calls,
            "outputs_scanned": scanned, "findings_total": len(findings), "counts": counts, "findings": findings,
            "warnings": warnings, "skipped": skipped}


def inject_line(row):
    copies = f" copies={1 + len(row['also_in'])}" if row.get("also_in") else ""
    return (f"INJECT {row['category']} tool={row['tool']} call={row['call']} line={row['line']} "
            f"session={row['session_id']} agent={row['agent_id']} at={row['ts']}{copies}")


def cmd_inject(args):
    try:
        result = inject(args)
    except (dsh.DshError, dsh.NodeMissing) as error:
        print(f"NOT_RUN {error}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1 if result["findings_total"] else 0
    for row in result["findings"][:args.show]:
        print(inject_line(row))
    if len(result["findings"]) > args.show:
        print(f"  ... {len(result['findings']) - args.show} more finding(s); see --json")
    detail = " ".join(f"{k}={v}" for k, v in result["counts"].items() if v)
    print((f"DSH_INJECT: FOUND {result['findings_total']} ({detail})" if result["findings_total"] else "DSH_INJECT: NONE")
          + f" sessions={result['sessions']} calls={result['calls']} outputs={result['outputs_scanned']}"
          + " (warning only: what a tool brought back is data, not orders)")
    for warning in result["warnings"][:8]:
        print(f"  ~ {warning}")
    return 1 if result["findings_total"] else 0


SHELL_READ = {"cat", "head", "tail", "less", "more", "type", "get-content", "gc", "bat"}
READ_TOOLS = ("read",)  # DSH's file read tool: arguments {"path": ...}
_PS_ARG_FLAGS = {"-totalcount", "-first", "-last", "-tail", "-head", "-encoding", "-delimiter",
                 "-readcount", "-filter", "-include", "-exclude", "-stream"}
_PS_PATH_FLAGS = {"-path", "-literalpath"}
_PRELUDE_PROGS = {"cd", "set-location", "sl", "pushd", "push-location", "chdir"}
_ENV_ASSIGN_RE = re.compile(r"^(?:\$env:[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _split_clauses(text):
    """Split shell command into sequential statements on ;, &&, ||, newline outside quotes."""
    clauses = []
    buf = []
    quote = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                i += 1
                buf.append(text[i])
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in (";", "\n", "\r") or text[i:i + 2] in ("&&", "||"):
            seg = "".join(buf).strip()
            if seg:
                clauses.append(seg)
            buf = []
            i += 2 if text[i:i + 2] in ("&&", "||") else 1
            continue
        buf.append(ch)
        i += 1
    seg = "".join(buf).strip()
    if seg:
        clauses.append(seg)
    return clauses


def _first_pipeline_stage(text):
    """Return the first command in a pipeline (before an unquoted single |)."""
    buf = []
    quote = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                i += 1
                buf.append(text[i])
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "|":
            break
        buf.append(ch)
        i += 1
    return "".join(buf).strip()


def _unquote(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _split_words(segment, prefer_nonposix):
    use_nonposix = prefer_nonposix or ("\\" in segment) or bool(re.search(r"[A-Za-z]:[\\/]", segment))
    words = shlex.split(segment, posix=not use_nonposix)
    return [_unquote(w) for w in words]


def _unwrap_subshell(words):
    """Unwrap cmd /c ..., pwsh -Command ..., Set-Location/env preludes; return stripped word list."""
    while words and _ENV_ASSIGN_RE.match(words[0]):
        words = words[1:]
    if not words:
        return []
    prog = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if prog.endswith(".exe"):
        prog = prog[:-4]
    if prog in ("cmd",) and len(words) >= 3 and words[1].lower() in ("/c", "/k"):
        return words[2:]
    if prog in ("pwsh", "powershell", "bash", "sh"):
        idx = 1
        while idx < len(words):
            w = words[idx].lower()
            if w in ("-c", "-command", "/c"):
                return words[idx + 1:]
            if w.startswith("-"):
                if w in ("-executionpolicy", "-outputformat", "-inputformat") and idx + 1 < len(words):
                    idx += 2
                else:
                    idx += 1
                continue
            break
    return words


def _extract_from_words(words, prefer_nonposix):
    if not words:
        return None
    words = _unwrap_subshell(words)
    if len(words) == 1 and any(sep in words[0] for sep in (";", "&&", "||", "|", "\n")):
        return _extract_from_command(words[0], prefer_nonposix)
    if not words:
        return None
    prog = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if prog.endswith(".exe"):
        prog = prog[:-4]
    if prog not in SHELL_READ and not (prog == "sed" and "-n" in words):
        return None
    if prog in ("get-content", "gc"):
        ps_paths = []
        filtered = []
        skip_next = False
        expect_path = False
        for w in words[1:]:
            if skip_next:
                skip_next = False
                continue
            if expect_path:
                ps_paths.append(w)
                expect_path = False
                continue
            low = w.lower()
            if low in _PS_PATH_FLAGS:
                expect_path = True
                continue
            if low.startswith("-path:") or low.startswith("-literalpath:"):
                val = w.split(":", 1)[1]
                if val:
                    ps_paths.append(val)
                continue
            if low in _PS_ARG_FLAGS:
                skip_next = True
                continue
            filtered.append(w)
        rest = [w for w in filtered if not w.startswith("-") and not w.isdigit()]
        if ps_paths:
            return ps_paths[-1]
        return rest[-1] if rest else None
    rest = [w for w in words[1:] if not w.startswith("-") and not w.isdigit()]
    if prog == "sed":
        rest = rest[1:]  # the sed script comes first
    return rest[-1] if rest else None


def _extract_from_command(command_text, prefer_nonposix):
    clauses = _split_clauses(command_text)
    for clause in clauses:
        stage = _first_pipeline_stage(clause)
        if not stage:
            continue
        words = _split_words(stage, prefer_nonposix)
        if not words:
            continue
        while words and _ENV_ASSIGN_RE.match(words[0]):
            words = words[1:]
        if not words:
            continue
        # Handle PowerShell "$env:FOO = 'bar'" separated around '='
        if len(words) >= 2 and words[0].lower().startswith("$env:") and words[1].startswith("="):
            continue
        prog = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if prog.endswith(".exe"):
            prog = prog[:-4]
        if prog in _PRELUDE_PROGS:
            continue
        return _extract_from_words(words, prefer_nonposix)
    return None


def _read_target_info(name, arguments):
    """Return (target_path_or_None, unparsed_bool) for one DSH tool call."""
    arguments = arguments if isinstance(arguments, dict) else {}
    if name in READ_TOOLS:
        target = arguments.get("path") or arguments.get("file_path")
        return (target if isinstance(target, str) and target else None), False
    if name not in ("Bash", "PowerShell"):
        return None, False
    cmd = str(arguments.get("command", ""))
    try:
        return _extract_from_command(cmd, prefer_nonposix=(name == "PowerShell")), False
    except ValueError:
        return None, True


def read_target(name, arguments):
    """2.5.0-ds.6 (DW 2.5.0 N5, usage_mix --reads): the path one DSH tool call reads, or None. The read tool's path;
    for a shell call (pwsh / bash, `command`), skips env/cd preludes and handles Windows/PowerShell paths and
    Get-Content parameters when it is cat / head / tail / sed -n / Get-Content."""
    target, _ = _read_target_info(name, arguments)
    return target


def output_bytes(output):
    """UTF-8 bytes of what a call brought back (the text parts, else the JSON), the part that enters the context."""
    if isinstance(output, list) and all(isinstance(part, dict) for part in output):
        return sum(len(str(part.get("text") or "").encode("utf-8")) for part in output)
    if output is None:
        return 0
    return len(text_of(output).encode("utf-8"))


def raw_arguments(events):
    """{call id: parsed arguments} of the tool calls in one session's events (ptc-dispatch and top-level calls)."""
    found = {}
    for event in events:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("type") == "tool/ptc-dispatch":
            found[data.get("subCallId")] = encodable(parse_arguments(data.get("arguments")))
        elif event.get("type") == "tool/call":
            found[data.get("callId")] = encodable(parse_arguments(data.get("arguments")))
    return found


def reads(args):
    """2.5.0-ds.6 (DW 2.5.0 N5): the most re-read paths of the selected sessions: read count and result bytes. DSH
    events carry token usage per model step, not per tool call, so the per-path cost is NOT_VERIFIED."""
    warnings, skipped = [], []
    selected = event_sources(args, warnings, skipped, by_calls=True)
    since, until = call_window(args)
    count, size, seen, sessions, total, read_calls, unparsed = {}, {}, set(), 0, 0, 0, 0
    for header_id, agent_id, events in selected:
        arguments = raw_arguments(events)
        mine = 0
        for item in session_entries(events, header_id, agent_id, warnings):
            entry = item["entry"]
            if not in_window(entry["ts"], since, until):
                continue
            mine += 1
            same = (entry["tool"], entry["tool_use_id"], entry["ts"])  # a forked session repeats its seed's calls
            if same in seen:
                continue
            seen.add(same)
            total += 1
            target, bad = _read_target_info(entry["tool"], arguments.get(entry["tool_use_id"]))
            if bad:
                unparsed += 1
            if target:
                read_calls += 1
                count[target] = count.get(target, 0) + 1
                size[target] = size.get(target, 0) + output_bytes(item["_output"])
        if mine:
            sessions += 1
    rows = sorted(count, key=lambda p: (-count[p], -size[p], p))[:args.top]
    return {"tool": TOOL, "command": "reads", "sessions": sessions, "calls": total, "reads": read_calls,
            "paths": len(count), "unparsed": unparsed, "cost": "NOT_VERIFIED",
            "top": [{"path": p, "reads": count[p], "bytes": size[p]} for p in rows],
            "warnings": warnings, "skipped": skipped}


def human_bytes(value):
    for unit, step in (("MB", 1 << 20), ("KB", 1 << 10)):
        if value >= step:
            return "%.1f%s" % (value / step, unit)
    return "%dB" % value


def cmd_reads(args):
    try:
        result = reads(args)
    except (dsh.DshError, dsh.NodeMissing) as error:
        print(f"NOT_RUN {error}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"READS top {len(result['top'])} re-read paths (count, result bytes; cost NOT_VERIFIED):")
    for row in result["top"]:
        print(f"READS {row['reads']:>5}x {human_bytes(row['bytes']):>8} {row['path']}")
    print(f"DSH_READS sessions={result['sessions']} calls={result['calls']} reads={result['reads']} "
          f"paths={result['paths']} unparsed={result['unparsed']} (prints paths: keep this output local)")
    for warning in result["warnings"][:8]:
        print(f"  ~ {warning}")
    return 0


def cmd_verify(args):
    """Delegate to audit_log.py verify (same format, same checks, same exit codes)."""
    argv = ["audit_log.py", "verify"]
    if args.log:
        argv += ["--log", args.log]
    if args.from_seq is not None:
        argv += ["--from", str(args.from_seq)]
    if args.to_seq is not None:
        argv += ["--to", str(args.to_seq)]
    if args.anchor_log:
        argv += ["--anchor-log", args.anchor_log]
    if args.anchor_rev:
        argv += ["--anchor-rev", args.anchor_rev]
    if args.anchor_path:
        argv += ["--anchor-path", args.anchor_path]
    if args.repo:
        argv += ["--repo", args.repo]
    if args.cite:
        argv += ["--cite", args.cite]
    saved = sys.argv
    sys.argv = argv
    try:
        return audit.main()
    except UnicodeEncodeError:  # 3.0.0-ds.8: a line holds a lone surrogate; neither build nor the base hook writes one
        print("BROKEN a line holds text that is not valid UTF-8 (a lone surrogate); dsh_audit.py build never writes "
              "one, so the line was changed after it was written")
        return 1
    finally:
        sys.argv = saved


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="reconstruct the action log from DSH session logs")
    build_parser.add_argument("--out", required=True, help="audit JSONL file to write")
    build_parser.add_argument("--force", action="store_true", help="replace an existing --out file")
    build_parser.add_argument("--log-root", "--sessions-root", dest="log_root",
                              help="DSH sessions root (default %%USERPROFILE%%\\.dsh\\sessions)")
    build_parser.add_argument("--cache-root", help="DSH projection cache root, for agent names")
    build_parser.add_argument("--project-dir", action="append", default=[],
                              help="only sessions whose cwd is this folder or below (repeatable)")
    build_parser.add_argument("--since", help="local date YYYY-MM-DD, inclusive (session start)")
    build_parser.add_argument("--until", help="local date YYYY-MM-DD, inclusive (session start)")
    build_parser.add_argument("--session", action="append", default=[],
                              help="only this session id / id prefix / agent name (repeatable)")
    build_parser.add_argument("--json", action="store_true", help="print the build summary as JSON")
    build_parser.add_argument("--input-limit", type=int, default=0,
                              help="2.2.5-ds.5: cut each input at this many characters (default 0: keep it whole); a cut "
                                   "line is marked input_cut")
    loops_parser = sub.add_parser("loops", help="2.3.0-ds.6 / 2.4.0-ds.6: find calls that go in circles (names and hashes only)")
    loops_parser.add_argument("--log-root", "--sessions-root", dest="log_root",
                              help="DSH sessions root (default %%USERPROFILE%%\\.dsh\\sessions)")
    loops_parser.add_argument("--cache-root", help="DSH projection cache root, for agent names")
    loops_parser.add_argument("--project-dir", action="append", default=[],
                              help="only sessions whose cwd is this folder or below (repeatable)")
    loops_parser.add_argument("--since", help="local date YYYY-MM-DD, inclusive (2.5.0-ds.6: each call's own time)")
    loops_parser.add_argument("--until", help="local date YYYY-MM-DD, inclusive (2.5.0-ds.6: each call's own time)")
    loops_parser.add_argument("--session", action="append", default=[],
                              help="only this session id / id prefix / agent name (repeatable)")
    loops_parser.add_argument("--events", nargs="+", metavar="FILE",
                              help="plain JSONL event files, one session each (synthetic fixtures), instead of the logs")
    loops_parser.add_argument("--config", help="2.4.0-ds.6: loops config JSON (DW 2.4.0 loop_guard schema: thresholds, "
                                               "child_tools, allow list)")
    loops_parser.add_argument("--repeat", type=int, help="repeat: this many of the same call (default 3)")
    loops_parser.add_argument("--window", type=int, help="all categories: within this many calls (default 20)")
    loops_parser.add_argument("--retry-errors", dest="retry_errors", type=int,
                              help="retry_same_error: this many failures in a row (default 2)")
    loops_parser.add_argument("--ping-pong", dest="ping_pong", type=int,
                              help="ping_pong: this many calls in turn, A B A B ... (default 6)")
    loops_parser.add_argument("--rounds", type=int, help="2.3.0-ds.6 flag: ping_pong rounds R = --ping-pong 2R")
    loops_parser.add_argument("--poll", type=int, help="poll_no_progress: same result this many times (default 3)")
    loops_parser.add_argument("--bad-args", dest="bad_args", type=int,
                              help="bad_args: this many refused calls of one tool (default 2)")
    loops_parser.add_argument("--show", type=int, default=20, help="lines printed per category (default 20; --json has all)")
    loops_parser.add_argument("--json", action="store_true", help="print the result as JSON")
    loops_parser.add_argument("--out", help="also write the JSON result to this file (status_gen.py \"loops\" reads it)")
    inject_parser = sub.add_parser("inject", help="2.4.0-ds.6: prompt-injection warnings in the tool outputs "
                                   "(after the fact; categories and line numbers only)")
    inject_parser.add_argument("--log-root", "--sessions-root", dest="log_root",
                               help="DSH sessions root (default %%USERPROFILE%%\\.dsh\\sessions)")
    inject_parser.add_argument("--cache-root", help="DSH projection cache root, for agent names")
    inject_parser.add_argument("--project-dir", action="append", default=[],
                               help="only sessions whose cwd is this folder or below (repeatable)")
    inject_parser.add_argument("--since", help="local date YYYY-MM-DD, inclusive (session start)")
    inject_parser.add_argument("--until", help="local date YYYY-MM-DD, inclusive (session start)")
    inject_parser.add_argument("--session", action="append", default=[],
                               help="only this session id / id prefix / agent name (repeatable)")
    inject_parser.add_argument("--events", nargs="+", metavar="FILE",
                               help="plain JSONL event files, one session each (synthetic fixtures), instead of the logs")
    inject_parser.add_argument("--tool", action="append", default=[],
                               help="only the outputs of this tool (e.g. web_fetch; repeatable; default all)")
    inject_parser.add_argument("--show", type=int, default=40, help="lines printed (default 40; --json has all)")
    inject_parser.add_argument("--json", action="store_true", help="print the result as JSON")
    reads_parser = sub.add_parser("reads", help="2.5.0-ds.6: the most re-read paths (read count, result bytes; "
                                  "prints paths, keep the output local)")
    reads_parser.add_argument("--log-root", "--sessions-root", dest="log_root",
                              help="DSH sessions root (default %%USERPROFILE%%\\.dsh\\sessions)")
    reads_parser.add_argument("--cache-root", help="DSH projection cache root, for agent names")
    reads_parser.add_argument("--project-dir", action="append", default=[],
                              help="only sessions whose cwd is this folder or below (repeatable)")
    reads_parser.add_argument("--since", help="local date YYYY-MM-DD, inclusive (each call's own time)")
    reads_parser.add_argument("--until", help="local date YYYY-MM-DD, inclusive (each call's own time)")
    reads_parser.add_argument("--session", action="append", default=[],
                              help="only this session id / id prefix / agent name (repeatable)")
    reads_parser.add_argument("--events", nargs="+", metavar="FILE",
                              help="plain JSONL event files, one session each (synthetic fixtures), instead of the logs")
    reads_parser.add_argument("--top", type=int, default=20, help="paths listed (default 20)")
    reads_parser.add_argument("--json", action="store_true", help="print the result as JSON")
    verify_parser = sub.add_parser("verify", help="delegate to audit_log.py verify (hash chain, anchors)")
    verify_parser.add_argument("--log", required=True, help="audit JSONL file to verify")
    verify_parser.add_argument("--from", dest="from_seq", type=int)
    verify_parser.add_argument("--to", dest="to_seq", type=int)
    verify_parser.add_argument("--anchor-log", help="file with AUDIT_HEAD lines")
    verify_parser.add_argument("--anchor-rev", help="commit whose --anchor-path holds the AUDIT_HEAD lines")
    verify_parser.add_argument("--anchor-path", help="path of DIRECTOR_LOG inside the repo, for --anchor-rev")
    verify_parser.add_argument("--repo", help="repo for --anchor-rev")
    verify_parser.add_argument("--cite", help="an AUDIT_RANGE line to check")
    a = ap.parse_args(argv)
    for field in ("since", "until"):
        value = getattr(a, field, None)
        if value:
            try:
                dsh.parse_day(value)
            except ValueError:
                print(f"dsh_audit: --{field} {value} is not YYYY-MM-DD", file=sys.stderr)
                return 2
    if a.command == "build":
        if a.input_limit < 0:
            print("NOT_RUN --input-limit must be 0 (no cut) or more")
            return 2
        return cmd_build(a)
    if a.command == "loops":
        return cmd_loops(a)
    if a.command == "inject":
        return cmd_inject(a)
    if a.command == "reads":
        if a.top < 1:
            print("NOT_RUN --top must be 1 or more")
            return 2
        return cmd_reads(a)
    return cmd_verify(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

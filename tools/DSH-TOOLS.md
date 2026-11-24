# dshdw tools

Tools of dsh-DIRECTOR-WORKER (dshdw; old name DIRECTOR-WORK DeepSeek edition, DW-DS), on DeepSeek Harness (DSH). Run every Python tool as:

    python -I -X utf8 tools/<tool>.py ...

DSH has no hooks and no PO page, so nothing fires automatically: dsh_usage / dsh_audit / dsh_doctor read the DSH
session files after the fact, and dsh_guard is a voluntary self-check the worker or Director runs by hand.

## New DSH tools

- dsh_session.py (library) - Node discovery, decode of session.v4.jsonl.zstd, session listing, role / agent
  name mapping from the parent's catalog, and the plain-JSON projection cache. CLI (one of):
  `dsh_session.py --temp-env WORK_DIR` (2.2.4-ds.4) creates WORK_DIR/tmp and prints the PowerShell and bash lines that
  point TEMP / TMP / TMPDIR at it.
  `dsh_session.py --worker-worktree REPO --order WO [--branch B] [--base REF] [--root DIR]` (2.2.5-ds.5) runs
  `git worktree add -b <B, default wt/<wo>> <DIR, default REPO/../wt>/<WO> <REF, default HEAD>` and prints the
  WORKTREE line; an existing folder exits 1 (nothing removed), a bad order id 2.
  `dsh_session.py --cwd-check WS` (2.3.0-ds.5) is the lead's first step (BOOTSTRAP step 0, docs/11): the current
  folder and WS through realpath + normcase (case-insensitive on Windows); another folder or a subfolder prints
  `BLOCKED: cwd <actual> != <expected>` and a NEXT line, exit 1; nothing is written. Same folder: `CWD: OK <path>`.
  `dsh_session.py --worktree-status DIR` (2.2.5-ds.5) prints `WORKTREE: 隔離 worktree ...` or `WORKTREE: 共用
  checkout ...` from `git worktree list` (the first entry is the main checkout); exit 2 when DIR is not a checkout.
- dsh_usage.py - token / context report per session plus daily totals, from the projection cache (no Node).
  `dsh_usage.py [--sessions-root DIR] [--cache-root DIR] [--project-dir PATH] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
  [--session ID|PREFIX|AGENT] [--json] [--out FILE] [--effort-check ORDER] [--from-jsonl | --no-fallback]`
  exit 0 report written, 2 NO_DATA / missing root / usage error. 2.2.4-ds.4: on NO_DATA --out still writes a file
  ({"status": "NO_DATA", "reason", "hints"}); a --project-dir below the startup folder prints a HINT naming it;
  --effort-check prints `EFFORT_ACTUAL <WO> agent= effort= order=` per session of the order's worker and a shadow
  WARN when the effort differs (exit 0).
- dsh_audit.py - rebuild the hash-chained action audit (same schema as audit_log.py / report_vs_audit.py) from the
  session event logs; needs Node 22+ for zstd. It is after-the-fact reconstruction, not a live hook. Since
  2.2.1-ds.1 line 1 of a built log is kind=rebuild with a `source` field (session log names, sha256, sizes), the same
  first line as upstream transcript_audit.py, and report_vs_audit.py prints a note for it; tool calls start at seq 2.
  `dsh_audit.py build --out FILE [--force] [--log-root DIR] [--cache-root DIR] [--project-dir PATH] [--since DATE]
  [--until DATE] [--session ID|PREFIX|AGENT] [--json]`
  `dsh_audit.py verify --log FILE [--from N --to M] [--anchor-log FILE] [--anchor-rev REV --anchor-path PATH [--repo DIR]]`
  exit 0 written / verified, 1 refused (output exists) or write problem, 2 cannot run.
  2.3.0-ds.6: `dsh_audit.py loops [same session filters] [--events FILE...] [--repeat 3] [--window 20] [--rounds 3]
  [--poll 3] [--show 20] [--json] [--out FILE]` finds calls that go in circles, after the fact (DSH has no hook to stop
  them): repeat, retry_same_error (same failure again with no written line between), ping_pong, poll_no_progress,
  bad_args (INVALID_ARGS / ToolArgsError, arguments that are not JSON: count, share, top 5 tools); child_error_unhandled
  prints only `~ NOT_VERIFIED` (no event for a failed child seen in the local logs). Tool names and hashes only, never
  inputs, outputs or messages; a forked session's copy of a finding is counted once. exit 0 none, 1 found, 2 cannot read.
  2.4.0-ds.6 (upstream 2.4.0 loop_guard, after the fact): loops version 2 adds `--config FILE` (the loop_guard schema,
  allow list included), `--retry-errors 2`, `--ping-pong 6` (`--rounds R` = 2R), `--bad-args 2`, DW's thresholds,
  bad_args per tool, child_error_unhandled (the session's last call is a failed subagent / wait_agent call; NOT_VERIFIED
  only with no child result), the LOOP line `LOOP <cat> tool= args= count= calls=A..B reminders= session= agent= at=`
  and a `LOOPS ...` summary line (also `dsh_usage.py --loops`). 2.5.0-ds.6 (upstream 2.5.0 F1): loops' --since /
  --until keep only the calls made in [since, until) by each call's own time (2.4.0-ds.6 took whole sessions by their
  start time); build, inject and dsh_usage's totals still go by the session start. `dsh_audit.py inject [same session filters]
  [--events FILE...] [--tool T] [--show 40] [--json]` runs inject_scan.scan_text on every tool output the logs hold:
  `INJECT <category> tool= call= line= session= agent= at=`, never the matched text; exit 1 found, 0 none, 2 cannot read.
- inject_scan.py (2.4.0-ds.6, upstream 2.4.0 without its PostToolUse hook mode) - text in a file that tries to give
  the agent orders (override, role_rewrite, hidden, encoded, exfiltration): `inject_scan.py scan FILE... [--json]`,
  one `INJECT <category> line=N file=F` per finding, never the text. Warns only. exit 1 found, 0 none, 2 missing file.
- resume_inject.py (2.4.0-ds.6, upstream 2.4.0 without SessionStart) - the RESUME_STATE header and open-items sections
  (未結, OPEN_DECISIONS, IN_FLIGHT ...), at most --max-bytes (2048): `resume_inject.py --file RESUME_STATE.md
  [--max-bytes N] [--section NAME ...]`. The agent runs it itself after a resume or a DSH compaction (AGENTS.md
  section, docs/06b step 0). exit 0 (a missing file is one line), 2 bad arguments.
- dsh_doctor.py - environment self-check: python, node, DSH home / sessions / projection cache, latest session decode,
  profile model / effort, latest session sandbox / approval, git, required tools, docs and templates; with --config
  the project director_work.json (one WARN line when it still has the block removed in 2.2.5-ds.5).
  `dsh_doctor.py [--tools-dir DIR] [--sessions-root DIR] [--cache-root DIR] [--profile-config FILE] [--config FILE]
  [--json]`
  exit 0 no FAIL, 1 any FAIL, 2 the check itself cannot run.
- dsh_setup_check.py - validate a DIRECTOR folder built by the DSH BOOTSTRAP: required files, the PENDING_METHOD line,
  PO_PENDING entry fields, the RESUME_STATE header and director_work.json. 2.2.1-ds.1 shadow checks (printed as
  `~ shadow:`; `--strict` makes them fail): an ID used twice, filled RESUME header values and a dated UPDATED line
  (gate_check --resume rule), director_work.json schema_version / mode / *_pattern regexes / po_pending_files types.
  2.2.2-ds.3 (upstream 2.2.2 setup_check): RESUME_SIZE (the RESUME_STATE over resume.max_bytes / max_line_bytes) and
  the resume / base_ref / release blocks of director_work.json, shadow too.
  `dsh_setup_check.py [--json] [--strict] DIR [DIR ...]`
  exit 0 no problems, 1 any problem, 2 usage error.
- dsh_guard.py - advisory risky-command check (no hook; run it yourself): force push, push, delete, send / publish,
  pay, config, secrets, always-forbidden git / process patterns, and the pause flag.
  `dsh_guard.py --command "git push" [--mode remind|block] [--profile worker|director] [--pause-flag FILE]
  [--rules FILE] [--shell bash|powershell|cmd] [--cwd DIR] [--json]`
  exit 0 clean, 1 remind (default), 2 block / pause flag exists / rules unreadable.
- bootstrap_repo.py (2.2.3-ds.3) - BOOTSTRAP 10.5: `.memsearch/` into .git/info/exclude; a step already done is
  skipped. --config is only read (2.2.5-ds.5): a config that still has the removed block prints one WARN line and
  nothing else changes. Never commits.
  `bootstrap_repo.py --repo DIR [--config FILE] [--check] [--skip exclude]`
  exit 0 done, 1 work left (or --check found some) or a step failed, 2 usage error.
- safety_gate.py (ds.2 sdd_gate.py, renamed in 2.2.5-ds.5 with OpenSpec removed) - the safety gates of a Standard /
  Strict order for gate_check (TESTS_LOCKED hashes, <WORK_DIR>/<WO>/PLAN.md vs PLAN_APPROVED, SPEC_REVIEW, STOP_RULES
  rounds, a safety switch turned off needs the PO's answer), order_limits / protected_tests for scope_check; an old
  "sdd" block is read with WARN lines (legacy_notes). Only reads.
  `safety_gate.py --lock-tests FILE ... [--repo DIR]` / `safety_gate.py --plan-hash PLAN_MD --order WO.md`
  exit 0 done, 1 a file is missing.
- release.py (2.2.2-ds.3) - release this repository in one pass: fetch, any modified or staged tracked file stops
  (dry run too; VERSION and CHANGELOG are read from HEAD), HEAD vs <remote>/<branch> (UP_TO_DATE / AHEAD /
  BEHIND / DIVERGED; --merge merges into release/<version> with --no-ff and stops on conflicts), VERSION = CHANGELOG top
  and the tag sorts above every remote tag, selftest, a scan of everything about to go public, then push (no --force),
  annotated tag, `gh release create --verify-tag --latest`, each checked with ls-remote / gh release view. Dry run by
  default. Glue over git and gh: release-please / semantic-release need CI and conventional commits (see CHANGELOG).
  2.4.0-ds.6: then the repository description's version (gh repo edit --description, checked with gh repo view;
  no version in it is SKIP).
  `release.py [--repo DIR] [--config FILE] [--version X] [--merge] [--execute]`
  exit 0 dry run clean or release done, 1 a step failed (a NEXT: line says what to do), 2 cannot run.
- verify_dsh_run.py (2.2.2-ds.3) - verify a DSH trial run of one work order from the files it left and the session
  logs (R01-R21 repo half, D01-D14 DSH half; the WO-101 checks, made generic; 2.2.5-ds.5 dropped R14 / R15 / D10). The run's names
  come from a JSON config (templates/VERIFY_DSH_RUN.json). Unit tests: test_verify_dsh_run.py.
  `verify_dsh_run.py --config FILE [--project-dir DIR] [--repo DIR] [--order FILE] [--out DIR] [--sessions-root DIR]
  [--cache-root DIR] [--no-dsh]`
  exit 0 PASS, 1 any FAIL, 2 SKIP only (INCOMPLETE) or cannot run.
- selftest_ds.py - offline smoke tests of this toolchain (help, usage, audit + report, setup fixture, generated status,
  doctor, guard, gate hash, evidence record, report matching). `selftest_ds.py [--verbose] [--keep]`
  exit 0 all pass (SKIP is not a failure), 1 any FAIL.

## Kept upstream tools (platform-neutral)

gate_check.py (2.2.2-ds.3: --resume prints `~ shadow: RESUME_SIZE` over resume.max_bytes / max_line_bytes, --strict
fails it; --order fetches and compares the BASE_REF commit with the remote branch; stale or missing
is a `~ WARN BASE_REF` note, --strict-base fails it; a failed fetch is said, never passed; --report-skeleton ORDER
prints a TASK REPORT with the order's fields, hash, the WORKTREE line from git worktree list (2.2.5-ds.5) and AC
rows filled in plus the evidence / scope_check / --match commands, so a DSH worker does not read the checker's source
to learn the format; 2.2.5-ds.5: --final DIRECTOR [--usage FILE] prints `~ WARN USAGE` when DIRECTOR/usage.json from
`dsh_usage.py --out` is missing, unreadable or NO_DATA, exit code unchanged), scope_check.py, evidence_record.py (2.2.3-ds.3 as upstream 2.2.3: a CHECKS
line may start bare `git`, read-only subcommands only - diff show log status rev-parse ls-files cat-file; anything else
is NOT_RUN, exit 2), report_vs_audit.py (DSH wrapped-command matching; 2.2.1 cut-line JSON decoding and the 2-real-word
rule; 2.2.3-ds.3 as upstream 2.2.3: statements split at new line ; && ||, a ``` block under RAN is one claim, at= ends
at the time, one run per listed AC ID, abbreviated claims skip options, shadow WARNs for a RAN line with no command and
for SCOPE_CHECK PASS before the agent's last commit; 2.2.4-ds.4 as upstream 2.2.4: variables put back, git -C DIR,
`...` inside a word, short hex prefix, HH:MM:SS and spans, AC-1 .. AC-6, options in another order, full-width ；, a claim
possibly in the cut part of a matched call is UNVERIFIED - its own status, counted as unverified=n at the end of the last line, exit code unchanged - WO-DS-006 false FAILs 64 -> 0, 18 of them UNVERIFIED),
gate_check.py --after-verdict VERDICT... --repo DIR [--orders DIR] [--strict] (2.2.4-ds.4 as upstream 2.2.4, shadow:
`~ WARN LATE_COMMIT` for commits after the last verdict's candidate that change non-document files outside its SCOPE),
trace_report.py, round_check.py, status_gen.py (po_pending / orders / audit / loops (2.3.0-ds.6); PENDING_METHOD instead of PO_PAGE_URL; 2.2.4-ds.4: a line longer than
the width keeps both ends, the middle of its longest path becomes "…", so the status word stays),
metrics_report.py, memory_size_check.py (defaults to the nearest AGENTS.md; 2.3.0-ds.6: --chain FILE... sums one
instruction chain against --max-bytes and lists passages of 3+ lines two files share; 2.2.2-ds.3 as upstream 2.2.2: --kind resume,
several --file, --glob, --workstreams, one line per file and `SIZE: PASS|OVER|MISSING`), resume_archive.py
(2.2.2-ds.3, upstream 2.2.2 unchanged: moves old RESUME_STATE sections word for word to RESUME_HISTORY_<YYYYMMDD>.md;
dry-run by default, --execute backs up, verifies and restores on any failed check), secret_mask.py, pause_ctl.py (no hook
reads the flag in DSH: workers check it themselves),
audit_log.py (verify / head / cite / recover; append is unused in DSH), vocabulary.json, guard_rules.json (used by
dsh_guard.py).

2.2.5-ds.5 (WO-DS-009 B7, upstream DW 2.2.5): ran_line.py (new: RAN lines and time stamps from the clock), gate_check.py
--sequence / --after-verdict (default FAIL, --warn for the old WARN) / --final (evidence/E2E/, ENTRY_POINT, DD 驗收案例,
plus the DS usage.json lines), scope_check.py WORKTREE line (one function, also used by dsh_session.py --worktree-status
and --report-skeleton), BASE_REF brackets as comments, long-path line, NOT_RUN instead of a traceback, report_vs_audit.py
H1 fixes and failure classes (time_mismatch= not_run=, --lead, --tolerance-min 10), dsh_audit.py build keeps the whole
input (--input-limit N cuts and marks input_cut), evidence_record.py / release.py put temp files in WORK_DIR/tmp when
WORK_DIR is set; templates/weird_inputs.py and templates/HANDOFF.md.

2.3.0-ds.5 (WO-DS-010, upstream DW 2.3.0): new tools ported as they are: completion.py, sim_check.py, waiver.py,
line_brief.py, pre_tr.py, pack_check.py, hash_check.py, flag_check.py, templates/run_closing.py (usage in
tools/README.md 「2.3.0 新工具用法」). gate_check.py --feasibility RECORD...; --verdict needs a self-checked RAN line
for a PASS-type verdict, severity from director_work.json "verdict_self_check" (warn default, fail opt-in), also
known to dsh_setup_check.py and printed by bootstrap_repo.py --config. dsh_doctor.py --licenses FILE
[--license-days 3] [--licenses-only] (upstream doctor.py --licenses). Every tool's --help works on a cp1252 / cp950
console (stdout switched to UTF-8 before argparse).

2.5.0-ds.6 (WO-DS-013, upstream DW 2.5.0; after-the-fact checks, warn by default, no hook): dispatch_check.py --log
DIRECTOR_LOG.md [--table FILE] [--strict] (N1: `| class=<class> effort=<level> model=<model>` on each DISPATCH line,
checked against the docs/05 table; the levels are DSH's off low high max, DW's medium / xhigh are unknown here) and
--dup "<title and scope>" [--resume GLOB]... [--repo DIR]... [--since] [--threshold 0.5] (N4: token Jaccard against
open NEXT_STEP lines and recent commit subjects, `~ WARN DUP`); exit 0 unless --strict, 2 on an input error.
dsh_audit.py reads [same session filters] [--events FILE...] [--top 20] [--json] (N5, rewritten from usage_mix.py
--reads for DSH events): the most re-read paths (DSH's read tool, pwsh / bash cat / head / tail / sed -n /
Get-Content), read count and result bytes; per-path cost NOT_VERIFIED (DSH logs usage per model step, not per call);
prints paths, keep it local.
delete_guard.py as upstream 2.5.0 (N3): [PATH ...] [--list FILE] [--repo DIR]... [--refs GLOB]... [--no-basename]
prints REFERENCED (up to 5 file:line places, never the line) or CLEAN per candidate; exit 1 referenced, 0 clean, 2 input
error; it only reads (git grep -F -i -I) and never deletes.
round_check.py as upstream 2.5.0 (N2): from SET 2 on a study section needs DIAGNOSIS_BY (not the IMPLEMENTER) and
DIAGNOSIS_RESULT, else `~ WARN NO_INDEPENDENT_DIAGNOSIS` (exit unchanged).

2.6.0-ds.6 (upstream DW 2.6.0): docs/07 adds ruler-first, plan-vs-code, simulation clock and unique coverage
gates (supported by `ruler_check.py` and `run_plan_check.py`); docs/04 adds numeric go conditions and `waiver.py
snooze --to` at wrap-up; docs/06b adds non-tracked inputs and `MISSING_INPUT`; `templates/TEST_REQUEST.md` adds
`CODE_REFS:`.

2.6.0-ds.7 (dshdw defect fixes & hardening):
- `scope_check.py --candidate <SHA>` diffs `since..candidate` even on a clean worktree for `FORBIDDEN` / `OUTSIDE` /
  `PROTECTED`, and `gate_check.py --match --candidate <SHA>` checks `TESTS_LOCKED` hashes against the candidate blob.
- `gate_check.py --final` verifies completed E2E outcomes (`EXIT_CODE: 0` or `RESULT: PASS`, failure markers -> FAIL,
  incomplete -> `E2E_INCOMPLETE` unless `--allow-incomplete-e2e`), optional `--candidate <40-hex>` E2E commit binding,
  and warns on `partial` `usage.json`.
- `dsh_usage.py` reports prompt-only `lastPromptTokens` (`input + cacheRead + cacheWrite`, matching `pressureTokens`),
  truly recomputes totals on `--from-jsonl`, and flags invalid token field types as `partial` with warnings.
- `dsh_session.py` / `dsh_doctor.py` require Node >= 22 with `zlib.zstdDecompressSync`, send decoder paths via stdin JSON,
  read 8 KB prefix in header mode, check `REQUIRED_TOOLS` (42), isolate `agent-default-model`, and note unconfined
  `danger-full-access + never`. `dsh_setup_check.py` accepts and validates `loop_guard`.
- `dsh_audit.py` sorts roots before subagents, pre-filters sessions from projection / header before full zstd decode,
  parses Windows/PowerShell `Get-Content` chains in `reads`, and reports `"unparsed"`.
- `bootstrap_repo.py` resolves `git rev-parse --git-path info/exclude` so linked worktrees write the common exclude.

## Removed Claude-only tools

hook_guard.py (its rules survive in guard_rules.json), setup_project_settings.py, context_probe.py, usage_report.py,
usage_mix.py, doctor.py, setup_check.py, choice_reconcile.py, browser_check.py, poll_hint.py, selftest.py, container/.

Exit-code convention: 0 success, 1 problem / remind found, 2 cannot run (usage error or missing data, e.g. NO_DATA).

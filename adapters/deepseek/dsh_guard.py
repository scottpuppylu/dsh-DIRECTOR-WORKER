r"""Advisory risky-command self-check for dsh-DIRECTOR-WORKER (dshdw).

DSH has NO PreToolUse hook: nothing can block a tool call before it runs. This tool is a self-check the worker or the
Director runs voluntarily before a risky command; it repeats the categories of the base tools/hook_guard.py (a Claude Code hook)
(force push, push, delete, send/publish, pay, config, secrets) using the same rules file, but it neither hooks nor
blocks anything by itself.

  python -I -X utf8 <REPO>/DIRECTOR/adapters/deepseek/dsh_guard.py --command "git push" [--mode remind|block]
      [--profile worker|director] [--pause-flag DIR/PAUSE] [--rules FILE] [--shell bash|powershell|cmd]
      [--cwd DIR] [--json]

Only shell commands are classified (--command is one shell line). The rules file's shell rules are used, including the
secret-file read rules (cat .env, type ~/.ssh/id_rsa, ...); mcp / Write-Edit path rules and the pause allow-list are
not evaluated here. A few always-forbidden git/process patterns from hook_guard.py are built in (reset --hard,
git clean, bare git stash, branch/tag/worktree delete, killing processes by name).

Exit codes: 0 clean, 1 remind (default; one warning line on stdout, the command still runs), 2 block when --mode block
(or when the pause flag exists: then every command is refused, always). 2 also when the rules file cannot be read.

Examples:
  python -I -X utf8 adapters/deepseek/dsh_guard.py --command "git push origin main"          (exit 1, one-line reminder)
  python -I -X utf8 adapters/deepseek/dsh_guard.py --command "git status"                   (exit 0)
  python -I -X utf8 adapters/deepseek/dsh_guard.py --command "git push" --mode block         (exit 2)
  python -I -X utf8 adapters/deepseek/dsh_guard.py --command "cat .env" --json
"""
import argparse
import json
import os
import pathlib
import re
import sys

BACKTICK = chr(96)
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "xargs", "call"}
SEPARATORS = ("&&", "||", "$(", ";", "|", "&", "\n", "(", ")", "{", "}")
# per shell: quote characters, escape character (PowerShell uses the backtick as its escape)
SHELLS = {"bash": ("'\"", "\\"), "powershell": ("'\"", BACKTICK), "cmd": ('"', "^")}
OPTS_WITH_VALUE = {"git": GIT_OPTS_WITH_VALUE, "gh": {"-R", "--repo"},
                   "aws": {"--profile", "--region", "--output", "--endpoint-url"},
                   "az": {"--subscription", "--output", "-o", "--query"},
                   "gcloud": {"--project", "--account", "--configuration"}}
RANK = {"deny": 0, "ask": 1, "none": 2}
MODES = ("remind", "block")
PROFILES = ("worker", "director")
PAUSE_REASON = ("every session stops taking new actions; report where you stopped and wait for "
                "the Director to run pause_ctl.py off")
EXTRA_GIT = object()


def tool_file(name):
    """3.0.0-ds.8: this folder first, then the base tools/ two folders up (guard_rules.json is the base's)."""
    here = pathlib.Path(__file__).resolve().parent
    for folder in (here, here.parent.parent / "tools"):
        if (folder / name).is_file():
            return folder / name
    return here.parent.parent / "tools" / name


def matching_end(command, i):
    """Index just past the backtick-quoted word or (...) that starts at i."""
    if command[i] == BACKTICK:
        end = command.find(BACKTICK, i + 1)
        return len(command) if end < 0 else end + 1
    depth = 0
    for j in range(i, len(command)):
        depth += {"(": 1, ")": -1}.get(command[j], 0)
        if depth == 0:
            return j + 1
    return len(command)


HEREDOC = re.compile(r"""<<(-?)[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|\\([^\s;&|<>()'"]+)|([^\s;&|<>()'"]+))""")


def heredoc_end(command, start, delim, tabs):
    """(start of the closing line, index just past it) of a here-document, or None when it is not closed."""
    i = start
    while i <= len(command):
        nl = command.find("\n", i)
        line = command[i:len(command) if nl < 0 else nl].rstrip("\r")
        if (line.lstrip("\t") if tabs else line) == delim:
            return i, len(command) if nl < 0 else nl + 1
        if nl < 0:
            return None
        i = nl + 1
    return None


def substitutions(body):
    """The $(...) and backtick-quoted commands of a here-document body; an unquoted delimiter still runs them."""
    found, i = [], 0
    while i < len(body):
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == BACKTICK or body.startswith("$(", i):
            end = matching_end(body, i + (body[i] == "$"))
            found.append(body[i + 2 - (body[i] == BACKTICK):end - 1])
            i = end
            continue
        i += 1
    return found


def strip_heredocs(command):
    """Bash: the line without the body of each here-document (the body is data, not a command)."""
    if "<<" not in command:
        return command
    out, pending, quote, i = [], [], None, 0
    while i < len(command):
        c = command[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif quote:
            if c == "\\":
                out.append(command[i:i + 2])
                i += 2
                continue
            quote = None if c == '"' else quote
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            quote = c
        elif command.startswith("<<", i) and not command.startswith("<<<", i) and not command[i - 1:i] == "<":
            m = HEREDOC.match(command, i)
            if m:
                delim = next(g for g in m.groups()[1:] if g is not None)
                pending.append((len(out), m.group(0), delim, m.group(1) == "-", m.group(5) is not None))
                out.append(m.group(0))
                i = m.end()
                continue
        elif c == "\n" and pending:
            out.append(c)
            at, extra = i + 1, []
            for _, _, delim, tabs, open_body in pending:
                found = heredoc_end(command, at, delim, tabs)
                if found is None:
                    return command
                extra += substitutions(command[at:found[0]]) if open_body else []
                at = found[1]
            for slot, _, _, _, _ in pending:
                out[slot] = ""
            out += [x + "\n" for x in extra]
            pending, i = [], at
            continue
        out.append(c)
        i += 1
    if pending:
        return command
    return "".join(out)


def parse(command, shell="bash"):
    """Simple commands of a shell line as word lists; also the commands inside $(...) / backticks in double quotes."""
    quotes, esc = SHELLS[shell]
    if shell == "bash":
        command = strip_heredocs(command)
    separators = SEPARATORS + (BACKTICK,) if shell == "bash" else SEPARATORS
    commands, words, word, quote, i = [], [], None, None, 0
    while i < len(command):
        c, nxt = command[i], command[i + 1:i + 2]
        if quote == "'":
            if c == "'":
                quote = None
            else:
                word += c
        elif quote:
            if c == '"':
                quote = None
            elif c == esc and nxt in ('"', esc, BACKTICK, "$"):
                word += nxt
                i += 1
            elif shell != "cmd" and (c == BACKTICK and shell == "bash" or command.startswith("$(", i)):
                end = matching_end(command, i + (c == "$"))
                commands += parse(command[i + 2 - (c == BACKTICK):end - 1], shell)
                i = end
                continue
            else:
                word += c
        elif c in quotes:
            quote, word = c, word or ""
        elif c == esc and nxt and (shell != "bash" or nxt in " \t'\"\\" or nxt in "".join(separators)):
            word = (word or "") + nxt
            i += 1
        elif c in " \t\r" or any(command.startswith(s, i) for s in separators):
            if word is not None:
                words.append(word)
                word = None
            if c not in " \t\r":
                if words:
                    commands.append(words)
                words = []
                i += next(len(s) for s in separators if command.startswith(s, i)) - 1
        else:
            word = (word or "") + c
        i += 1
    if word is not None:
        words.append(word)
    if words:
        commands.append(words)
    return commands


def command_name(word):
    return re.sub(r"\.exe$", "", re.split(r"[\\/]", word)[-1].lower())


def string_run(name, args):
    """The command string a wrapper executes and its shell, or None."""
    low = [a.lower() for a in args]
    if name in ("bash", "sh", "zsh", "dash", "ksh"):
        flag = next((k for k, a in enumerate(args) if re.fullmatch(r"-[a-z]*c[a-z]*", a)), None)
        return None if flag is None or flag + 1 >= len(args) else (args[flag + 1], "bash")
    if name == "cmd":
        flag = next((k for k, a in enumerate(low) if a in ("/c", "/k", "/r")), None)
        return None if flag is None else (" ".join(args[flag + 1:]), "cmd")
    if name in ("powershell", "pwsh"):
        flag = next((k for k, a in enumerate(low) if len(a) > 1 and "-command".startswith(a)), None)
        return None if flag is None else (" ".join(args[flag + 1:]), "powershell")
    if name == "eval":
        return " ".join(args), "bash"
    if name in ("invoke-expression", "iex"):
        return " ".join(a for a in args if not (len(a) > 1 and "-command".startswith(a.lower()))), "powershell"
    return None


def simple_commands(command, shell="bash", depth=0):
    """(name, args) of every simple command of a line, also those a wrapper runs (bash -c, cmd /c, eval, ...)."""
    for args in parse(command, shell):
        while args and (re.fullmatch(r"\w+=.*", args[0]) or args[0].lower() in WRAPPERS):
            if args[0].lower() == "env" and all(re.fullmatch(r"-.*|\w+=.*", a) for a in args[1:]):
                break  # env with no command after it prints the environment
            args = args[1:]
        if not args:
            continue
        name, rest = command_name(args[0]), args[1:]
        yield name, rest
        inner = string_run(name, rest)
        if inner and depth < 8:
            yield from simple_commands(*inner, depth + 1)


def positional(name, rest):
    """The words of a command that are not options (git -C dir / gh -R repo skip their value too), lower case."""
    out, i, with_value = [], 0, OPTS_WITH_VALUE.get(name, set())
    while i < len(rest):
        if rest[i].startswith("-") and len(rest[i]) > 1:
            i += 2 if rest[i] in with_value else 1
        else:
            out.append(rest[i].lower())
            i += 1
    return out


def rule_path(value, cwd):
    """A tool's path as an absolute, resolved path with / separators (lower case on Windows)."""
    text = os.path.expanduser(os.fspath(value))
    if not os.path.isabs(text):
        text = os.path.join(cwd or os.getcwd(), text)
    return os.path.normcase(os.path.abspath(text)).replace("\\", "/")


def arg_path(word, cwd):
    """A command word as rule_path gives it: $env:VAR and %VAR% are expanded first."""
    word = re.sub(r"\$env:(\w+)", lambda v: os.environ.get(v.group(1), v.group(0)), word, flags=re.I)
    return rule_path(os.path.expandvars(word), cwd)


def glob_regex(glob, home):
    """~/x is under the home folder, **/x at any depth, anything else is a whole absolute path; * stays in one folder."""
    glob, prefix = glob.replace("\\", "/"), ""
    if glob.startswith("~/"):
        glob, prefix = glob[2:], re.escape(home.rstrip("/")) + "/"
    out, i = prefix, 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out, i = out + {"*": "[^/]*", "?": "[^/]"}.get(glob[i], re.escape(glob[i])), i + 1
    return re.compile(out, re.I if os.name == "nt" else 0)


def globs_match(globs, excepts, target, home):
    hit = lambda patterns: any(glob_regex(g, home).fullmatch(target) for g in patterns)
    return hit(globs) and not hit(excepts)


def shell_match(m, name, rest, cwd=None, home=""):
    """cmd: regexes for the command name; args: first non-option words in turn; flags / not_flags: regexes on words;
    bare: no words at all; arg_search: a regex found in some word; path_args / path_except: path globs on words."""
    if not any(re.fullmatch(c, name, re.I) for c in m.get("cmd", [])):
        return False
    words = positional(name, rest)
    if len(words) < len(m.get("args", [])):
        return False
    if any(words[k] not in [w.lower() for w in alts] for k, alts in enumerate(m.get("args", []))):
        return False
    if m.get("bare") and rest:
        return False
    if m.get("arg_search") and not any(re.search(r, a) for r in m["arg_search"] for a in rest):
        return False
    if m.get("path_args") and not any(globs_match(m["path_args"], m.get("path_except", []), arg_path(a, cwd), home)
                                       for a in rest if not a.startswith("-")):
        return False
    hit = lambda key: any(re.fullmatch(f, a, re.I) for f in m.get(key, []) for a in rest)
    return (not m.get("flags") or hit("flags")) and not hit("not_flags")


def git_rule(args):
    """(rule id, reason) for the git commands that are always forbidden (ported from hook_guard.py), or None."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_OPTS_WITH_VALUE else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "reset" and "--hard" in rest:
        return "G03", "git reset --hard is forbidden (docs/08); use a WIP commit or git restore on named files"
    if sub == "clean" and not {"-n", "--dry-run"} & set(rest):
        return "G03", "git clean is forbidden (docs/08)"
    if sub == "stash":
        action = rest[0] if rest else ""
        if action in ("", "pop", "drop", "clear", "save") or action.startswith("-"):
            return "G03", "bare git stash is forbidden (docs/08); use git stash push -u -m MARK and git stash apply SHA"
        if action == "push" and not any(a in ("-m", "--message") or a.startswith("--message=") for a in rest):
            return "G03", "git stash push needs -m UNIQUE_MARK (docs/08)"
    if sub == "worktree" and rest[:1] in (["remove"], ["prune"]):
        return "G04", "deleting a worktree needs the PO's approval (docs/08)"
    if sub == "branch" and {"-d", "-D", "--delete"} & set(rest):
        return "G04", "deleting a branch needs the PO's approval (docs/08)"
    if sub == "tag" and {"-d", "--delete"} & set(rest):
        return "G04", "deleting a tag needs the PO's approval (docs/08)"
    return None


def kills_by_name(name, args):
    low = [a.lower() for a in args]
    if name in ("pkill", "killall"):
        return True
    if name == "taskkill":
        return any(a in ("/im", "-im", "/fi", "-fi") for a in low)
    if name in ("stop-process", "spps"):
        return not any(a == "-id" or a.startswith("-id:") or re.fullmatch(r"[\d,]+", a) for a in low)
    if name == "kill":
        return any(len(a) > 2 and ("-name".startswith(a) or "-processname".startswith(a)) for a in low)
    return False


def builtin_hits(commands):
    """Always-forbidden git / process patterns; (decision, id, category, reason) triples."""
    hits = []
    for name, rest in commands:
        if name == "git":
            found = git_rule(rest)
            if found:
                hits.append(("deny", found[0], "git", found[1]))
        elif kills_by_name(name, rest):
            hits.append(("deny", "G12", "process",
                         "ending processes by name is forbidden (docs/08); stop your own PID with Stop-Process -Id N"))
    return hits


def as_list(value):
    return [value] if isinstance(value, dict) else list(value or [])


def load_rules(path):
    """The rules JSON, checked enough to run; raises ValueError with one clear message."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("rules"), list) \
            or not data["rules"]:
        raise ValueError(f"{path}: needs schema_version 1 and a non-empty rules list")
    for number, rule in enumerate(data["rules"], 1):
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not isinstance(rule.get("reason"), str) \
                or not isinstance(rule.get("match"), (dict, list)):
            raise ValueError(f"{path}: rule {number} needs id, reason and match")
    return data


def rule_decision(rule, profile):
    decision = (rule.get("decision") or {}).get(profile) if isinstance(rule.get("decision"), dict) else None
    return decision if decision in ("deny", "ask") else "none"


def rule_hits(data, commands, cwd, home, profile):
    """(decision, id, category, reason) for every shell rule that matches one of the commands."""
    hits = []
    for rule in data["rules"]:
        decision = rule_decision(rule, profile)
        if decision == "none":
            continue
        for m in as_list(rule.get("match")):
            if not isinstance(m, dict) or m.get("kind") != "shell":
                continue
            if any(shell_match(m, name, rest, cwd, home) for name, rest in commands):
                hits.append((decision, rule["id"], rule.get("category") or "", rule["reason"]))
                break
    return hits


def strictest(hits):
    """The most severe hit, then the lowest rule id (G01 before G02, G10 before G20 ...)."""
    def key(hit):
        match = re.search(r"(\d+)", hit[1])
        return (RANK.get(hit[0], 3), int(match.group(1)) if match else 0, hit[1])
    return sorted(hits, key=key)[0] if hits else None


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", required=True, help="the shell command to check (one line)")
    ap.add_argument("--mode", choices=MODES, default="remind",
                    help="remind (default): exit 1 with one warning; block: exit 2 (still only advisory)")
    ap.add_argument("--profile", choices=PROFILES, default="worker", help="which decision of each rule applies")
    ap.add_argument("--pause-flag", help="pause flag file (pause_ctl.py on): while it exists every command is refused")
    ap.add_argument("--rules", help="rules file (default: guard_rules.json beside this tool)")
    ap.add_argument("--shell", choices=("bash", "powershell", "cmd"),
                    default="powershell" if os.name == "nt" else "bash",
                    help="how to read the command line (default: powershell on Windows, bash elsewhere)")
    ap.add_argument("--cwd", help="folder relative paths are read from (default: the current folder)")
    ap.add_argument("--json", action="store_true", help="print one JSON object instead of a warning line")
    a = ap.parse_args(argv)
    cwd = a.cwd or os.getcwd()
    home = rule_path(str(pathlib.Path.home()), None)
    rules_path = pathlib.Path(a.rules).expanduser() if a.rules else tool_file("guard_rules.json")
    paused = bool(a.pause_flag) and pathlib.Path(a.pause_flag).expanduser().exists()
    result = {"tool": "dsh_guard", "version": 1, "advisory": True, "mode": a.mode, "profile": a.profile,
              "shell": a.shell, "command": a.command, "cwd": cwd, "paused": paused}
    exit_code = 0
    if paused:
        result.update(hit=True, decision="deny", rule=None, category="pause", reason=PAUSE_REASON,
                      pause_flag=str(a.pause_flag), exit_code=2)
        exit_code = 2
    else:
        try:
            data = load_rules(rules_path)
        except ValueError as error:
            print(f"NOT_RUN dsh_guard: {error}", file=sys.stderr)
            return 2
        command = re.sub(r"[\d*]?>&(\d+|-)", " ", a.command)  # 2>&1 joins streams, it is not a redirect
        commands = list(simple_commands(command, a.shell))
        hits = builtin_hits(commands) + rule_hits(data, commands, cwd, home, a.profile)
        top = strictest(hits)
        if top is None:
            result.update(hit=False, decision="none", rule=None, category=None, reason=None, exit_code=0)
        else:
            decision, rule_id, category, reason = top
            result.update(hit=True, decision=decision, rule=rule_id, category=category, reason=reason,
                          matches=[{"decision": h[0], "rule": h[1], "category": h[2], "reason": h[3]}
                                   for h in sorted(hits, key=lambda h: h[1])], exit_code=2 if a.mode == "block" else 1)
            exit_code = result["exit_code"]
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif paused:
        print(f"BLOCK  dsh_guard: pause flag {a.pause_flag} exists: {PAUSE_REASON}")
    elif result["hit"]:
        label = "BLOCK " if a.mode == "block" else "REMIND"
        note = "" if a.mode == "block" else " (advisory: DSH has no hook, the command will run)"
        print(f"{label} dsh_guard: {result['rule']} {result['category']}: {result['reason']}{note}")
    else:
        print("OK    dsh_guard: no deny/ask rule matched (advisory self-check; DSH blocks nothing by itself)")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

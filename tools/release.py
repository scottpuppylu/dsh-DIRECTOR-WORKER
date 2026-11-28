"""Release this repository in one pass (2.2.2, ported from the DeepSeek port's ds.3): fetch, compare with the remote
branch, check VERSION / CHANGELOG / tag order, run the selftest, scan what is about to go public, then push the
branch, tag it and create the GitHub Release.

  python -I -X utf8 tools/release.py [--repo DIR] [--merge] [--execute] [--config FILE] [--version X]

Default is a dry run: it fetches (a fetch only updates remote-tracking refs) and runs every check, then prints the
remote steps it would take. Nothing on the remote changes without --execute.
A release is made from a commit, never the working tree: VERSION and CHANGELOG.md are read from HEAD
(`git show HEAD:VERSION`), and a tracked file that is modified or staged stops every run, dry run too, with the next
step to take (2.2.2: a VERSION edited but not committed used to pass the dry run).

Steps, in order; each prints `STEP <name>: OK | FAIL | SKIP | PLAN ...`, and a FAIL stops with a `NEXT:` line:
  fetch      git fetch <remote> --tags (no --prune-tags: local tags are left alone)
  worktree   no tracked file is modified or staged (untracked files are not released and do not count)
  state      HEAD against <remote>/<branch>: UP_TO_DATE, AHEAD n, BEHIND n or DIVERGED ahead n / behind n.
             BEHIND (nothing new to release) stops. DIVERGED stops unless --merge: then the dry run predicts conflicts
             with `git merge-tree`, and --execute makes branch release/<version> from <remote>/<branch>, merges HEAD
             into it with --no-ff and stops on a conflict, listing the conflicted files (resolve, commit, run again
             from that branch)
  version    VERSION at HEAD equals the first `## ` heading of CHANGELOG.md at HEAD; tag v<version> is not on the
             remote yet, or already points at HEAD (a rerun); <version> sorts above every remote tag of the same shape
             (<major>.<minor>.<patch>[-<label>.<n>]) - 2.2.0-x.2 after 2.2.1-x.1 fails. 3.0.0 (series plan 6.9-3):
             the upstream version and the -<label>.<n> serial are compared as one pair. 3.0.0 B14 (SPEC 1-8): the
             serial continues the previous version of the same label and never goes back to 1: after v2.2.1-x.2 only
             -x.3 is accepted (2.2.2-x.3 or 2.2.1-x.3), 2.2.2-x.1 and 2.2.2-x.4 stop. The first tag of a label
             takes any serial; a rerun (tag already at HEAD) is not checked again
  readme     3.0.0 (PO 11-28): when HEAD tracks tools/readme_check.py (a DIRECTOR-WORK series repo), README.md of
             HEAD has every section of the series (readme_check.py --rev HEAD: 所屬系列 for the base, all of SPEC
             section 1-9 for a variant). Only exit 0 with the line `README_CHECK: PASS` passes: no exit code (it
             could not start, it timed out), another exit code or no PASS line stops. Other repos: SKIP
  selftest   the selftest command exits 0 (default `python -I -X utf8 tools/selftest.py`)
  scan       <remote>/<branch>..HEAD, everything that goes public: paths (DIRECTOR/, CLAUDE.local.md,
             .claude/settings.local.json, Claude session transcripts), added lines and commit messages (the rules and
             the allow file of tools/privacy_scan.py, 3.0.0 B9: drive paths, user folders /Users/<name> \\Users\\<name>
             /home/<name>, emails, token formats, code names, the owner's account name, private words; plus
             key = value secrets with a real-looking value) and commit author / committer emails. A noreply or
             *.invalid address is public by design only in commit messages (Co-Authored-By trailers) and author /
             committer fields. gitleaks runs too when it is on PATH (not required)
  privacy    3.0.0 (privacy ruling): tools/privacy_scan.py reads every file and path of HEAD, not only the change:
             drive-letter paths, user folders, emails, token formats, the owner's other code names and account name,
             words from privacy_banned.local.txt. An allowed hit needs an entry with its reason in
             tools/privacy_allow.txt. Any hit, or an allow file it cannot read, stops before anything is pushed
  delivery   3.0.0 B3 (C2 hard line, from cdx_release): when <director>/evidence/DELIVERY.json exists (default
             DIRECTOR/ of the repo, --director or "director" in the config), `delivery.py check --delivered <the
             checked commit>` must exit 0 with `DELIVERY_CHECK: PASS`: the commit about to be pushed is the delivered,
             verified one (a commit made after the record is HEAD_MOVED). No exit code or no PASS line stops. No
             record: SKIP (nothing binds this release to a delivery)
  push       git push <remote> <checked commit>:refs/heads/<branch> (never --force), then ls-remote must equal it.
             3.0.0 B3: the commit is the one HEAD was when the checks started (after the state step), never what HEAD
             is at push time (a commit made during the selftest stops: HEAD moved during the checks); right before
             the push ls-remote runs again and anything other than the remote the checks saw (or the commit itself,
             a rerun) stops: the remote moved after verification
  tag        git tag -a v<version> on the checked commit, git push <remote> refs/tags/v<version> (one tag, never
             --tags), then ls-remote must show the tag peeled to it. 3.0.0 B3: with --execute, before the tag and again
             before the release, ls-remote <branch> must still be the checked commit
  release    gh release create v<version> --verify-tag --latest, notes = the CHANGELOG section of <version>, title from
             the config; then gh release view must show the release
  describe   3.0.0 B5 (from dshdw 2.4.0-ds.6): the GitHub repository description names the new version: every
             version in it (<major>.<minor>.<patch>[-<label>.<n>], with or without a leading v) becomes <version>,
             through gh repo edit --description, then gh repo view must show it. A description with no version is left
             alone (SKIP: add one by hand); one that already says <version> is SKIP; no gh on this machine is SKIP
             (put the version in the description by hand)
A rerun after a failure skips what is already done (branch already at HEAD, tag already at HEAD, release present).

Config: the optional "release" object of director_work.json (--config), keys remote, branch, title ({version} is
filled in), tag_message, selftest (a command line), gh_repo (owner/name; default from the remote URL), director (3.0.0
B3: the DIRECTOR folder, relative to the repo; default DIRECTOR). Missing keys use the defaults above.

Ends with `RELEASE: DRY_RUN|DONE|FAIL ...`. Exit codes: 0 dry run clean or release done, 1 a step failed, 2 cannot run.
Standard library plus git; gh only for the release step.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
README_TIMEOUT = 120  # seconds; readme_check reads two files, a hang is a FAIL, never a pass
DELIVERY_TIMEOUT = 300  # seconds; delivery.py check hashes the delivered files, a hang is a FAIL, never a pass
DEFAULTS = {"remote": "origin", "branch": "main", "title": "DIRECTOR-WORK {version}",
            "tag_message": "DIRECTOR-WORK {version}", "selftest": "python -I -X utf8 tools/selftest.py", "gh_repo": None,
            "director": "DIRECTOR"}
VERSION_SHAPE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([A-Za-z]+)\.(\d+))?$")
PRIVATE_PATHS = [(re.compile(r"(^|/)DIRECTOR/"), "a DIRECTOR/ file (project state, never public)"),
                 (re.compile(r"(^|/)CLAUDE\.local\.md$"), "CLAUDE.local.md (local instructions)"),
                 (re.compile(r"(^|/)\.claude/settings\.local\.json$"), ".claude/settings.local.json (local settings)"),
                 (re.compile(r"(^|/)\.claude/projects/|(^|/)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                             r"\.jsonl$"), "a Claude session transcript")]
REAL_VALUE = re.compile(r"^[A-Za-z0-9/+_=.-]{12,}$")


class Stop(Exception):
    """A step failed; message is the reason, next_step what to do about it."""
    def __init__(self, message, next_step):
        super().__init__(message)
        self.next_step = next_step


def run(args, repo, check=False, input_text=None):
    proc = subprocess.run([str(a) for a in args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=input_text)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args))}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def git(repo, *args, check=True):
    proc = run(["git", *args], repo)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout.strip() if check else proc


def version_key(text):
    """(major, minor, patch, has_label, label, n) or None. A plain x.y.z sorts after its own x.y.z-label.n."""
    m = VERSION_SHAPE.match(text.strip())
    if not m:
        return None
    major, minor, patch, label, n = m.groups()
    return (int(major), int(minor), int(patch), 0 if label else 1, label or "", int(n or 0))


def changelog_top(text):
    """(version of the first `## ` heading, its section text without the heading)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## "):
            m = re.match(r"##\s+v?(\S+?)(?:[（(\s]|$)", line)
            body = []
            for other in lines[i + 1:]:
                if other.startswith("## "):
                    break
                body.append(other)
            return (m.group(1) if m else ""), "\n".join(body).strip() + "\n"
    return None, ""


def load_config(path):
    config = dict(DEFAULTS)
    if path:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        block = data.get("release") or {}
        if not isinstance(block, dict):
            raise ValueError("\"release\" in the config is not an object")
        unknown = sorted(set(block) - set(DEFAULTS) - {"_comment"})
        if unknown:
            raise ValueError(f"\"release\" has keys this tool does not read: {', '.join(unknown)}")
        config.update({k: v for k, v in block.items() if k in DEFAULTS and v is not None})
    return config


DESCRIBED_VERSION = re.compile(r"(?<![\w.])(v?)\d+\.\d+\.\d+(?:-[A-Za-z]+\.\d+)?(?![\w.])")


def described(description, version):
    """The repository description with every version in it replaced by `version` (a leading v is kept), or None when
    it holds no version (3.0.0 B5, from dshdw 2.4.0-ds.6)."""
    if not DESCRIBED_VERSION.search(description or ""):
        return None
    return DESCRIBED_VERSION.sub(lambda m: m.group(1) + version, description)


def gh_repo_from_url(url):
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def secret_module():
    spec = importlib.util.spec_from_file_location("secret_mask", HERE / "secret_mask.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def privacy_module():
    spec = importlib.util.spec_from_file_location("privacy_scan", HERE / "privacy_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def email_allowed(address):
    local, _, domain = address.lower().partition("@")
    return "noreply" in local or domain.endswith("users.noreply.github.com") or domain.endswith(".invalid") \
        or domain == "invalid"


def line_findings(text, secrets, privacy, rules, allows, trailer=False):
    """What in one added line (or, trailer=True, one commit message line) must not go public: [(kind, shown)].
    3.0.0 B9: the rules and allow entries of privacy_scan.py (one rule set; shown masked, a token only by its kind),
    plus key = value secrets. In a commit message a noreply / *.invalid address is a trailer, public by design."""
    found = []
    for rule, matched in privacy.line_hits(text, rules, allows):
        if trailer and rule == "email" and email_allowed(matched):
            continue
        if rule == "token":
            kind = next((k for k, p in secrets.PATTERNS if p.search(matched)), "token")
            found.append((kind, f"[{kind}]"))
        else:
            found.append((rule, privacy.mask(rule, matched)))
    for kind, pattern in secrets.KEEP_PREFIX:
        if kind != "assignment":
            continue
        for m in pattern.finditer(text):
            value = m.group(2).strip("\"'\\")
            if REAL_VALUE.match(value) and re.search(r"\d", value) and re.search(r"[A-Za-z]", value):
                found.append(("secret_assignment", "[secret value]"))
    return found


def scan(repo, base, head):
    """Problems in base..head, each `<where>: <what>`; and notes."""
    problems, notes = [], []
    secrets = secret_module()
    privacy = privacy_module()
    try:  # 3.0.0 B9: privacy_scan.py's rules and the allow file of the commit being released
        rules, allows = privacy.rules_and_allows(repo, privacy.allow_text_of(repo, head))
    except privacy.Invalid as error:
        return [f"privacy rules cannot load: {error}"], notes, 0
    email_rule = [("email", privacy.RULES["email"])]
    names = git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=ACMR", f"{base}..{head}").splitlines()
    for name in names:
        for pattern, what in PRIVATE_PATHS:
            if pattern.search(name):
                problems.append(f"{name}: {what}")
    diff = run(["git", "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-U0", f"{base}..{head}"], repo)
    current, number = "?", 0
    for raw in diff.stdout.splitlines():
        if raw.startswith("+++ "):
            current = raw[6:] if raw.startswith("+++ b/") else raw[4:]
            continue
        hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
        if hunk:
            number = int(hunk.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            text = raw[1:]
            if current == privacy.ALLOW_PATH:  # as privacy_scan reads it: an entry's pattern is not a leak, its reason is read
                text = text.rpartition(" | ")[2]
            for kind, shown in line_findings(text, secrets, privacy, rules, allows):
                problems.append(f"{current}:{number}: {kind} {shown}")
            number += 1
    log = git(repo, "log", "--format=%H%x1f%an <%ae>%x1f%cn <%ce>%x1f%B%x1e", f"{base}..{head}")
    for record in filter(None, (r.strip() for r in log.split("\x1e"))):
        sha, author, committer, body = (record.split("\x1f") + ["", "", ""])[:4]
        for who, value in (("author", author), ("committer", committer)):
            for _, address in privacy.line_hits(value, email_rule, allows):
                if not email_allowed(address):
                    problems.append(f"commit {sha[:10]} {who}: email {privacy.mask('email', address)}")
        for line in body.splitlines():
            for kind, shown in line_findings(line, secrets, privacy, rules, allows, trailer=True):
                problems.append(f"commit {sha[:10]} message: {kind} {shown}")
    if shutil.which("gitleaks"):
        proc = run(["gitleaks", "detect", "--source", ".", "--no-banner", "--redact",
                    f"--log-opts={base}..{head}"], repo)
        if proc.returncode == 1:
            problems.append("gitleaks found a leak (run it again without --redact locally to see where)")
        elif proc.returncode != 0:
            notes.append(f"gitleaks did not run cleanly (exit {proc.returncode}); its result is not counted")
        else:
            notes.append("gitleaks: no leaks")
    else:
        notes.append("gitleaks is not on PATH; only this tool's own patterns ran")
    return problems, notes, len(names)


class Release:
    def __init__(self, repo, config, execute, merge, version, director=None):
        self.repo, self.config, self.execute, self.merge, self.version = repo, config, execute, merge, version
        self.remote, self.branch = config["remote"], config["branch"]
        self.upstream = f"{self.remote}/{self.branch}"
        self.planned = []
        self.director = pathlib.Path(director) if director else repo / config["director"]
        self.target = self.verified_remote = None  # 3.0.0 B3: set by pin() right after the state step

    def pin(self):
        """3.0.0 B3: the commit every later check runs on, and the remote branch they were checked against."""
        self.target = self.head()
        self.verified_remote = git(self.repo, "rev-parse", self.upstream)

    def step(self, name, status, detail=""):
        print(f"STEP {name}: {status}" + (f" {detail}" if detail else ""))

    def head(self):
        return git(self.repo, "rev-parse", "HEAD")

    def fetch(self):
        proc = git(self.repo, "fetch", self.remote, "--tags", check=False)
        if proc.returncode != 0:
            raise Stop(f"git fetch {self.remote} failed: {(proc.stderr or proc.stdout).strip()[:300]}",
                       "check the network and the remote, then run again; without a fetch the remote state is unknown")
        self.step("fetch", "OK", f"{self.remote} (remote-tracking refs and tags only)")

    def state(self):
        if git(self.repo, "rev-parse", "--verify", "-q", self.upstream, check=False).returncode != 0:
            raise Stop(f"{self.upstream} does not exist after the fetch", f"check --config remote / branch")
        counts = git(self.repo, "rev-list", "--left-right", "--count", f"{self.upstream}...HEAD").split()
        behind, ahead = int(counts[0]), int(counts[1])
        current = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        where = f"HEAD ({current} {self.head()[:10]}) vs {self.upstream} ({git(self.repo, 'rev-parse', self.upstream)[:10]})"
        if behind == 0 and ahead == 0:
            self.step("state", "OK", f"UP_TO_DATE {where}: nothing new to push; tag and release still run")
            return "up_to_date"
        if behind and not ahead:
            raise Stop(f"BEHIND {behind} {where}: the remote has commits this branch does not, and nothing new here",
                       f"git merge --ff-only {self.upstream}, then add the release commits and run again")
        if ahead and not behind:
            self.step("state", "OK", f"AHEAD {ahead} {where}: a fast-forward push")
            return "ahead"
        detail = f"DIVERGED ahead {ahead} / behind {behind} {where}"
        if not self.merge:
            raise Stop(detail, f"run again with --merge (makes release/<version> from {self.upstream} and merges "
                               f"HEAD into it with --no-ff), or merge by hand")
        if not self.execute:
            proc = git(self.repo, "merge-tree", "--write-tree", "--name-only", "--no-messages", self.upstream, "HEAD",
                       check=False)
            if proc.returncode == 1:
                files = [f for f in proc.stdout.splitlines()[1:] if f.strip()]
                self.step("state", "PLAN", f"{detail}; --execute would merge into release/<version> and stop on "
                          f"{len(files)} conflicted file(s): {', '.join(files)}")
            elif proc.returncode == 0:
                self.step("state", "PLAN", f"{detail}; --execute would merge into release/<version> with no conflicts")
            else:
                self.step("state", "PLAN", f"{detail}; could not predict conflicts ({proc.stderr.strip()[:200]})")
            print("  ~ the checks below run on HEAD before the merge; --execute runs them again on the merge")
            return "diverged"
        return self.do_merge(detail)

    def do_merge(self, detail):
        version = self.read_version()
        target = f"release/{version}"
        if git(self.repo, "rev-parse", "--verify", "-q", f"refs/heads/{target}", check=False).returncode == 0:
            raise Stop(f"{detail}; branch {target} already exists",
                       f"switch to {target} and run again from there, or delete it if it is stale")
        source = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        source_ref = source if source != "HEAD" else self.head()
        git(self.repo, "switch", "-c", target, self.upstream)
        proc = git(self.repo, "merge", "--no-ff", "--no-edit", "-m", f"Merge {source_ref} into {self.branch} for v{version}",
                   source_ref, check=False)
        if proc.returncode != 0:
            files = git(self.repo, "diff", "--name-only", "--diff-filter=U").splitlines()
            raise Stop(f"{detail}; merge into {target} has {len(files)} conflicted file(s): {', '.join(files) or '?'}",
                       f"you are on {target} with the merge in progress: resolve those files, git add them, "
                       f"git commit, then run release.py again from {target}")
        self.step("state", "OK", f"{detail}; merged into {target} ({self.head()[:10]})")
        return "merged"

    def at_head(self, name):
        """A file's text as committed at HEAD (never the working tree), or None when HEAD has no such file."""
        proc = git(self.repo, "show", f"HEAD:{name}", check=False)
        return proc.stdout.lstrip("\ufeff") if proc.returncode == 0 else None

    def read_version(self):
        if self.version:
            return self.version
        text = self.at_head("VERSION")
        if text is None:
            raise Stop("no VERSION file at HEAD", "write the version into VERSION and commit it, or pass --version")
        return text.strip()

    def check_version(self):
        version = self.read_version()
        key = version_key(version)
        if not key:
            raise Stop(f"version {version!r} is not <major>.<minor>.<patch>[-<label>.<n>]", "fix VERSION")
        changelog = self.at_head("CHANGELOG.md")
        top, section = changelog_top(changelog) if changelog is not None else (None, "")
        if top != version:
            raise Stop(f"VERSION is {version} but the first CHANGELOG.md heading at HEAD is {top or 'missing'}",
                       "put the new version's section on top of CHANGELOG.md (or fix VERSION) and commit it")
        if not section.strip():
            raise Stop(f"the CHANGELOG section of {version} is empty", "write the release notes")
        self.notes = section
        tag = f"v{version}"
        remote_tags = {}
        for line in git(self.repo, "ls-remote", "--tags", self.remote).splitlines():
            sha, _, ref = line.partition("\t")
            name = ref.replace("refs/tags/", "")
            if name.endswith("^{}"):
                remote_tags[name[:-3]] = sha
            else:
                remote_tags.setdefault(name, sha)
        self.tag, self.tag_done = tag, False
        if tag in remote_tags:
            if remote_tags[tag] == self.head():
                self.tag_done = True
            else:
                raise Stop(f"tag {tag} is already on the remote at {remote_tags[tag][:10]}, not HEAD {self.head()[:10]}",
                           "pick a new version (VERSION and CHANGELOG); a pushed tag is never moved")
        higher = sorted((name for name in remote_tags if name != tag and version_key(name)
                         and version_key(name) >= key), key=version_key)
        if higher:
            raise Stop(f"{tag} does not sort above the remote tag(s) {', '.join(higher)}",
                       f"use a version above {higher[-1]} (for example bump the base version, not only the -label.n)")
        # 3.0.0 (series plan 6.9-3, the DeepSeek port's rule): the whole (upstream version, -label.N) pair must sort
        # above every remote tag (the check above) and the tag must be new.
        # 3.0.0 B14 (SPEC 1-8, PO 11-28): and the serial continues the previous tag of the same label, never back to 1
        if key[4] and not self.tag_done:
            same = sorted((name for name in remote_tags if name != tag and version_key(name)
                           and version_key(name)[4] == key[4]), key=version_key)
            if same and key[5] != version_key(same[-1])[5] + 1:
                want = version_key(same[-1])[5] + 1
                raise Stop(f"{tag}: the -{key[4]}.N serial continues the previous version {same[-1]}: the next one is "
                           f"-{key[4]}.{want}, not -{key[4]}.{key[5]} (SPEC 1-8: the serial never goes back to 1 and "
                           "skips no number)",
                           f"set VERSION and the CHANGELOG top to {key[0]}.{key[1]}.{key[2]}-{key[4]}.{want} and commit")
        others = [name for name in remote_tags if not version_key(name)]
        self.step("version", "OK", f"{version} = CHANGELOG top; {tag} " + ("already at HEAD (rerun)" if self.tag_done
                  else "is new") + f"; above {len(remote_tags) - len(others) - (1 if self.tag_done else 0)} remote tag(s)"
                  + (f"; {len(others)} tag(s) of another shape not compared" if others else ""))
        return version

    def check_worktree(self):
        dirty = run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=no"], self.repo)
        if dirty.returncode != 0:
            raise RuntimeError(f"git status: {(dirty.stderr or dirty.stdout).strip()[:400]}")
        names = [line[3:] for line in dirty.stdout.splitlines() if line.strip()]
        if names:
            said = ""
            if "VERSION" in names and not self.version:
                work = (self.repo / "VERSION").read_text(encoding="utf-8-sig").strip() if (self.repo / "VERSION").is_file() else "gone"
                said = f"; VERSION in the working tree is {work}, at HEAD {(self.at_head('VERSION') or 'missing').strip()}"
            raise Stop(f"tracked files are modified or staged: {', '.join(names[:5])}"
                       + (f" and {len(names) - 5} more" if len(names) > 5 else "") + said,
                       "git add and git commit them (or git restore them), then run release.py again; a release is made "
                       "from HEAD, never the working tree")
        self.step("worktree", "OK", "no tracked file modified or staged (untracked files are not released)")

    def readme(self):
        """3.0.0 (PO 11-28): a series README has every section; no exit code or no PASS line is FAIL."""
        if git(self.repo, "cat-file", "-e", "HEAD:tools/readme_check.py", check=False).returncode != 0:
            self.step("readme", "SKIP", "HEAD has no tools/readme_check.py: not a DIRECTOR-WORK series repo")
            return
        command = [sys.executable, "-I", "-X", "utf8", str(HERE / "readme_check.py"), "--repo", str(self.repo),
                   "--rev", "HEAD"]
        try:
            proc = subprocess.run(command, cwd=str(self.repo), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=README_TIMEOUT)
            code, lines = proc.returncode, [l for l in (proc.stdout or "").splitlines() if l.strip()]
        except (OSError, subprocess.TimeoutExpired) as error:
            code, lines = None, [f"{type(error).__name__}: {error}"]
        verdict = lines[-1] if lines else ""
        if code != 0 or not verdict.startswith("README_CHECK: PASS"):
            for line in lines[:-1][:40]:
                print(f"  - {line}")
            raise Stop(f"readme_check: exit {'none' if code is None else code}, {verdict or 'no README_CHECK line'}",
                       "add the missing README sections (a section with nothing to say says 無; templates/"
                       "VARIANT_README.md lists them), commit, run again")
        self.step("readme", "OK", verdict)

    def selftest(self):
        command = shlex.split(self.config["selftest"], posix=os.name != "nt") if self.config["selftest"] else []
        if command and command[0] in ("python", "python3", "py"):
            command[0] = sys.executable
        if not command:
            raise Stop("no selftest command", "set \"release\": {\"selftest\": \"...\"} in the config")
        proc = run(command, self.repo)
        last = [l for l in (proc.stdout or "").splitlines() if l.strip()]
        if proc.returncode != 0:
            raise Stop(f"selftest exit {proc.returncode}: {last[-1] if last else (proc.stderr or '').strip()[:300]}",
                       "fix the failing test and run again")
        self.step("selftest", "OK", last[-1] if last else f"exit 0 ({' '.join(command)})")

    def scan(self):
        problems, notes, files = scan(self.repo, self.upstream, "HEAD")
        for note in notes:
            print(f"  ~ {note}")
        if problems:
            for problem in problems[:40]:
                print(f"  - {problem}")
            if len(problems) > 40:
                print(f"  - ... and {len(problems) - 40} more")
            raise Stop(f"{len(problems)} item(s) must not go public ({self.upstream}..HEAD)",
                       "remove them from the commits (amend or a new commit that deletes them is not enough for "
                       "history: rewrite the unpushed commits), then run again")
        self.step("scan", "OK", f"{self.upstream}..HEAD: {files} changed file(s), commits, authors: nothing private")

    def privacy(self):
        """3.0.0 privacy ruling: the whole tree of HEAD (privacy_scan.py), not only base..HEAD; any hit stops."""
        module = privacy_module()
        try:
            hits, files, binary = module.scan(self.repo, "HEAD")
        except module.Invalid as error:
            raise Stop(f"privacy_scan cannot run: {error}",
                       "fix it (every entry of tools/privacy_allow.txt needs `<rule>: <regex> | <reason>`), commit, "
                       "run again")
        if hits:
            for rule, name, number, shown in hits[:40]:
                print(f"  - HIT {rule} {name}:{number} {shown}")
            if len(hits) > 40:
                print(f"  - ... and {len(hits) - 40} more")
            raise Stop(f"privacy_scan: {len(hits)} hit(s) in the files of HEAD",
                       "replace them (a workspace path is written <WS>); only a public name of this series or a test "
                       "mail domain may get an allow entry with its reason in tools/privacy_allow.txt; commit, run again")
        self.step("privacy", "OK", f"privacy_scan: {files} file(s) of HEAD, nothing private ({binary} binary skipped)")

    def delivery(self):
        """3.0.0 B3 (C2 hard line, from cdx_release): the commit about to be pushed is the delivered, verified one."""
        record = self.director / "evidence" / "DELIVERY.json"
        if not record.is_file():
            self.step("delivery", "SKIP", f"no {self.director.name}/evidence/DELIVERY.json: no delivery record binds "
                      "this release")
            return
        command = [sys.executable, "-I", "-X", "utf8", str(HERE / "delivery.py"), "check", "--director",
                   str(self.director), "--repo", str(self.repo), "--delivered", self.target]
        try:
            proc = subprocess.run(command, cwd=str(self.repo), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=DELIVERY_TIMEOUT)
            code, lines = proc.returncode, [l for l in (proc.stdout or "").splitlines() if l.strip()]
        except (OSError, subprocess.TimeoutExpired) as error:
            code, lines = None, [f"{type(error).__name__}: {error}"]
        verdict = lines[-1] if lines else ""
        if code != 0 or not verdict.startswith("DELIVERY_CHECK: PASS"):
            for line in lines[:-1][:40]:
                print(f"  - {line}")
            raise Stop(f"delivery check: exit {'none' if code is None else code}, {verdict or 'no DELIVERY_CHECK line'}",
                       f"push only the delivered, verified commit: release from it, or verify {self.target[:12]} "
                       "(gate verdict, delivery.py record, judgments) and run again")
        self.step("delivery", "OK", f"{verdict}; {self.target[:12]} is the delivered commit")

    def push(self):
        head = self.target or self.head()
        if self.head() != head:  # 3.0.0 B3: what the checks saw is what goes out
            raise Stop(f"HEAD moved during the checks: it is {self.head()[:10]}, the checks ran on {head[:10]}",
                       "run release.py again: the new commit has not been checked")
        remote_sha = self.remote_branch_sha()
        if self.verified_remote and remote_sha not in (self.verified_remote, head):
            raise Stop(f"the remote {self.branch} moved after verification: ls-remote is "
                       f"{(remote_sha or 'nothing')[:10]}, the checks saw {self.verified_remote[:10]}",
                       "run release.py again (it fetches, checks and scans the new range); never --force")
        if remote_sha == head:
            self.step("push", "SKIP", f"{self.remote} {self.branch} is already {head[:10]}")
            return
        if not self.execute:
            self.planned.append(f"git push {self.remote} {head[:12]}:refs/heads/{self.branch}  (the checked commit, "
                                f"HEAD; fast-forward, no --force)")
            return
        proc = git(self.repo, "push", self.remote, f"{head}:refs/heads/{self.branch}", check=False)
        if proc.returncode != 0:
            raise Stop(f"push rejected: {(proc.stderr or proc.stdout).strip()[-300:]}",
                       "someone pushed meanwhile: run release.py again (it fetches and compares again); never --force")
        if self.remote_branch_sha() != head:
            raise Stop(f"after the push ls-remote {self.branch} is {self.remote_branch_sha()}, not {head}",
                       "look at the remote by hand before going on")
        self.step("push", "OK", f"ls-remote {self.branch} = {head}")

    def remote_branch_sha(self):
        out = git(self.repo, "ls-remote", self.remote, f"refs/heads/{self.branch}")
        return out.split("\t")[0] if out else None

    def still_target(self, before):
        """3.0.0 B3 (from cdx_release): with --execute, the remote branch is still the checked commit."""
        if self.execute and self.target and self.remote_branch_sha() != self.target:
            raise Stop(f"the remote {self.branch} changed before the {before}: ls-remote is "
                       f"{(self.remote_branch_sha() or 'nothing')[:10]}, not {self.target[:10]}",
                       f"look at the remote by hand; tag and release only the checked commit")

    def tag_step(self, version):
        head = self.target or self.head()
        if self.tag_done:
            self.step("tag", "SKIP", f"{self.tag} is already on the remote at HEAD")
            return
        message = self.config["tag_message"].format(version=version)
        if not self.execute:
            self.planned.append(f"git tag -a {self.tag} -m {message!r} {head[:10]}; git push {self.remote} refs/tags/{self.tag}")
            return
        local = git(self.repo, "rev-parse", "-q", "--verify", f"refs/tags/{self.tag}^{{commit}}", check=False)
        if local.returncode == 0 and local.stdout.strip() != head:
            raise Stop(f"a local tag {self.tag} points at {local.stdout.strip()[:10]}, not the checked commit {head[:10]}",
                       f"look at it (git show {self.tag}); delete the local one only if it is a mistake")
        if local.returncode != 0:
            git(self.repo, "tag", "-a", self.tag, "-m", message, head)
        proc = git(self.repo, "push", self.remote, f"refs/tags/{self.tag}", check=False)
        if proc.returncode != 0:
            raise Stop(f"tag push failed: {(proc.stderr or proc.stdout).strip()[-300:]}", "run again; never --force")
        peeled = git(self.repo, "ls-remote", "--tags", self.remote, f"refs/tags/{self.tag}^{{}}")
        if not peeled or peeled.split("\t")[0] != head:
            raise Stop(f"ls-remote does not show {self.tag} peeled to {head[:10]}: {peeled or 'nothing'}",
                       "look at the remote tags by hand")
        self.step("tag", "OK", f"{self.tag}^{{}} = {head}")

    def release_step(self, version):
        repo_name = self.config["gh_repo"] or gh_repo_from_url(git(self.repo, "remote", "get-url", self.remote))
        title = self.config["title"].format(version=version)
        gh = shutil.which("gh")
        if not self.execute and not (repo_name and gh):
            self.planned.append(f"gh release create {self.tag} -R {repo_name or '<owner/name: set release.gh_repo>'} "
                                f"--title {title!r} --notes-file <CHANGELOG section> --latest --verify-tag"
                                + ("" if gh else "  (gh is not on PATH: --execute will stop here)"))
            return
        if not repo_name:
            raise Stop("cannot tell the GitHub repository from the remote URL", "set \"release\": {\"gh_repo\": ...}")
        if not gh:
            raise Stop("gh (GitHub CLI) is not on PATH", "install gh and gh auth login, then run again")
        view = run([gh, "release", "view", self.tag, "-R", repo_name, "--json", "url,tagName,isDraft"], self.repo)
        if view.returncode == 0:
            self.step("release", "SKIP", f"already there: {json.loads(view.stdout).get('url')}")
            return
        if not self.execute:
            self.planned.append(f"gh release create {self.tag} -R {repo_name} --title {title!r} --notes-file <CHANGELOG "
                                f"section, {len(self.notes.splitlines())} lines> --latest --verify-tag")
            return
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            handle.write(self.notes)
            notes_file = handle.name
        try:
            proc = run([gh, "release", "create", self.tag, "-R", repo_name, "--title", title, "--notes-file", notes_file,
                        "--latest", "--verify-tag"], self.repo)
        finally:
            os.unlink(notes_file)
        if proc.returncode != 0:
            raise Stop(f"gh release create failed: {(proc.stderr or proc.stdout).strip()[-300:]}",
                       "fix the cause (gh auth status, tag on the remote) and run again; branch and tag are kept")
        view = run([gh, "release", "view", self.tag, "-R", repo_name, "--json", "url,tagName,isDraft"], self.repo)
        if view.returncode != 0:
            raise Stop("gh release view cannot see the new release", f"look at https://github.com/{repo_name}/releases")
        data = json.loads(view.stdout)
        self.step("release", "OK", f"{data.get('url')} (draft={data.get('isDraft')})")

    def describe_step(self, version):
        """3.0.0 B5 (from dshdw 2.4.0-ds.6): the repository description shows the released version."""
        repo_name = self.config["gh_repo"] or gh_repo_from_url(git(self.repo, "remote", "get-url", self.remote))
        gh = shutil.which("gh")
        if not gh:  # the Director's decision: no gh here is SKIP, never a stop after the release
            if self.execute:
                self.step("describe", "SKIP", f"gh is not on PATH; put {version} in the repository description by hand")
            else:
                self.planned.append(f"gh repo edit {repo_name or '<owner/name>'} --description <version -> {version}>"
                                    "  (gh is not on PATH: SKIP, by hand)")
            return
        if not repo_name:
            if not self.execute:
                self.planned.append(f"gh repo edit <owner/name> --description <version -> {version}>")
                return
            raise Stop("cannot update the repository description: cannot tell the GitHub repository from the remote URL",
                       f"set \"release\": {{\"gh_repo\": ...}}, or put {version} in the description by hand")
        view = run([gh, "repo", "view", repo_name, "--json", "description"], self.repo)
        if view.returncode != 0:
            raise Stop(f"gh repo view failed: {(view.stderr or view.stdout).strip()[-300:]}",
                       f"check gh auth status, or put {version} in the description by hand")
        current = json.loads(view.stdout).get("description") or ""
        wanted = described(current, version)
        if wanted is None:
            self.step("describe", "SKIP", f"the description names no version; add {version} by hand if it should")
            return
        if wanted == current:
            self.step("describe", "SKIP", f"the description already says {version}")
            return
        if not self.execute:
            self.planned.append(f"gh repo edit {repo_name} --description {wanted!r}  (was {current!r})")
            return
        proc = run([gh, "repo", "edit", repo_name, "--description", wanted], self.repo)
        if proc.returncode != 0:
            raise Stop(f"gh repo edit failed: {(proc.stderr or proc.stdout).strip()[-300:]}",
                       f"put {version} in the description by hand; branch, tag and release are kept")
        after = run([gh, "repo", "view", repo_name, "--json", "description"], self.repo)
        shown = json.loads(after.stdout).get("description") if after.returncode == 0 else None
        if shown != wanted:
            raise Stop(f"after gh repo edit the description is {shown!r}, not {wanted!r}", "look at the repository page")
        self.step("describe", "OK", repr(wanted))


def use_work_temp():
    """2.2.5 (B9): with WORK_DIR set, temp files go to WORK_DIR/tmp (tempfile.tempdir and TMPDIR / TEMP / TMP for child
    processes). Git Bash exports TMPDIR, which Python reads before TEMP / TMP, so `export TEMP=...` alone did nothing."""
    work = os.environ.get("WORK_DIR", "").strip()
    if not work:
        return None
    folder = os.path.join(work, "tmp")
    os.makedirs(folder, exist_ok=True)
    tempfile.tempdir = folder
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = folder
    return folder


def main(argv=None):
    use_work_temp()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the repository to release (default: current folder)")
    ap.add_argument("--config", help="director_work.json with an optional \"release\" object")
    ap.add_argument("--version", help="the version to release (default: the VERSION file)")
    ap.add_argument("--merge", action="store_true", help="when HEAD and the remote branch diverged, merge into release/<version>")
    ap.add_argument("--execute", action="store_true", help="change the remote (default: dry run)")
    ap.add_argument("--director", help="the DIRECTOR folder whose evidence/DELIVERY.json binds the release "
                                       "(default: <repo>/DIRECTOR, or \"director\" in the config)")
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help has non-ASCII text (test_help_any_console_230)
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    try:
        config = load_config(a.config)
    except (OSError, ValueError) as error:
        print(f"RELEASE: NOT_RUN config: {error}")
        return 2
    if run(["git", "rev-parse", "--git-dir"], repo).returncode != 0:
        print(f"RELEASE: NOT_RUN {repo} is not a git repository")
        return 2
    job = Release(repo, config, a.execute, a.merge, a.version, a.director)
    mode = "EXECUTE" if a.execute else "DRY_RUN"
    print(f"RELEASE {mode} repo={repo} remote={job.remote} branch={job.branch}")
    try:
        job.fetch()
        job.check_worktree()
        state = job.state()
        job.pin()
        version = job.check_version()
        job.readme()
        job.selftest()
        job.scan()
        job.privacy()
        job.delivery()
        if state == "diverged" and not a.execute:
            job.planned.insert(0, f"git switch -c release/{version} {job.upstream}; git merge --no-ff <current branch>")
            job.planned.append(f"git push {job.remote} HEAD:refs/heads/{job.branch}  (the merge, fast-forward)")
            job.planned.append(f"git tag -a {job.tag} on the merge; git push {job.remote} refs/tags/{job.tag}")
            job.planned.append(f"gh release create {job.tag} --verify-tag --latest")
            job.planned.append(f"gh repo edit --description <version -> {version}>")
        else:
            job.push()
            job.still_target("tag")
            job.tag_step(version)
            job.still_target("release")
            job.release_step(version)
            job.describe_step(version)
    except Stop as stop:
        print(f"STEP FAIL: {stop}\nNEXT: {stop.next_step}\nRELEASE: FAIL")
        return 1
    except RuntimeError as error:
        print(f"STEP FAIL: {error}\nNEXT: read the git message above and run again\nRELEASE: FAIL")
        return 1
    if not a.execute:
        for line in job.planned:
            print(f"PLAN {line}")
        print(f"RELEASE: DRY_RUN {len(job.planned)} remote step(s) planned; run with --execute to do them")
        return 0
    print(f"RELEASE: DONE v{version} at {job.head()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

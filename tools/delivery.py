#!/usr/bin/env python3
"""Delivery contract (3.0.0, C2 hard line + C4): the delivered version is the verified version, and every acceptance
condition has its own judgment in every environment.

  delivery.py record --candidate SHA --file PATH [--file PATH ...] [--order WO-ID] [--env NAME ...]
                     [--director DIRECTOR] [--repo REPO]
  delivery.py judge  --ac AC-n [--env NAME] --kind auto|manual|review|po --outcome PASS|FAIL|NOT_RUN
                     --evidence PATH [--by WHO] [--director DIRECTOR]
  delivery.py check  [--director DIRECTOR] [--repo REPO] [--delivered SHA] [--skip-old-e2e]

The record is DIRECTOR/evidence/DELIVERY.json. --director defaults to DIRECTOR/ under the current folder, --repo to the
git checkout that holds it (R3 layout).

record  the candidate (40 hex, the commit the verdict reviewed) must be the repo's HEAD, the version that is delivered:
        otherwise `DELIVERY_SHA_MISMATCH` and nothing is written. --order is required (`NO_ORDER`), and exactly one
        DIRECTOR/orders/<WO-ID>*.md may match (`ORDER_NOT_FOUND`, `AMBIGUOUS_ORDER`). Review P1-4: the candidate must
        be the `CANDIDATE_HEAD` of the latest *VERDICT* file naming the order (anywhere under DIRECTOR/; latest by
        modification time): none is `NO_VERDICT`, another commit `VERDICT_MISMATCH`, and nothing is written. A Direct
        order (`GOVERNANCE = Direct`) has no gate verdict and is the one written exception. Each --file (relative to
        the repo; a folder means every file in it) is recorded with its size and SHA-256: a committed file from the commit itself (an uncommitted change
        to it is `DIRTY`), any other file (a build output) from disk. Paths are relative. Recording a new candidate
        drops the judgments of the old one (`JUDGMENTS_RESET n`): they were about another product.
judge   one judgment: an AC of the order, an environment of the record (needed when there are several), a kind and an
        outcome, with the evidence file (inside the director folder; its SHA-256 is kept). auto = an automatic run,
        manual = a manual end-to-end run, review = the director's review, po = the PO's own judgment. The latest
        judgment of one AC, environment and kind counts.
check   candidate == delivered (`DELIVERY_SHA`); the delivered commit is still the repo's HEAD, or --delivered SHA (the
        commit to be pushed) (`HEAD_MOVED`); the latest verdict of the order still names the candidate
        (`VERDICT_MISMATCH`, `NO_VERDICT`); the delivered commit exists and every file still has its size and
        hash (`CHANGED`, `MISSING`; no git repo to check against is `NOT_CHECKED files`, a failure); an E2E record under
        evidence/E2E/ that names another `CANDIDATE:` (`E2E_OTHER_CANDIDATE`) or none (`E2E_NO_CANDIDATE`); evidence
        changed after its judgment (`EVIDENCE_CHANGED`). No order in the record is `NO_ORDER` (review P1-5). An
        acceptance row whose type is not AUTO / REVIEW / PO is `UNKNOWN_KIND AC-n`, an order with no AC row is
        `NO_CONDITIONS` (a note for a Direct order) (review P1-6). Every AUTO condition needs a PASS `auto`
        judgment and every REVIEW condition a PASS `review` judgment in every environment (`JUDGMENT_MISSING`; a manual
        run never stands in for the automatic one); a FAIL is `JUDGMENT_FAIL`; a PO condition without the PO's judgment
        is `PENDING_PO`, a note: final PO acceptance stays with the PO. `gate_check.py --final` runs this check.
        --skip-old-e2e (3.0.0 B12, from agy 2.6.0-agy.5; off by default): an E2E record whose `CANDIDATE:` names
        another commit is an old run, left out with a note `E2E_SKIPPED` instead of `E2E_OTHER_CANDIDATE`; a record
        without `CANDIDATE:` still fails. Without the switch nothing changes: move old records out by hand.

Last line `DELIVERY_RECORD|DELIVERY_JUDGE|DELIVERY_CHECK: DONE|PASS|FAIL|INVALID`. Exit 0 pass, 1 fail, 2 invalid input
(no record, broken JSON, not UTF-8, a bad argument): no result is never a pass.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import write_json_atomic  # noqa: E402

SCHEMA = "dw-delivery/1"
RECORD = pathlib.Path("evidence") / "DELIVERY.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
AC = re.compile(r"AC-\d+")
KINDS = ("auto", "manual", "review", "po")
OUTCOMES = ("PASS", "FAIL", "NOT_RUN")
NEEDS = {"AUTO": "auto", "REVIEW": "review", "PO": "po"}
CANDIDATE_LINE = re.compile(r"^[ \t]*CANDIDATE[ \t]*[:=][ \t]*`?([0-9a-fA-F]{7,40})\b", re.M)
CANDIDATE_HEAD = re.compile(r"^[ \t]*CANDIDATE_HEAD[ \t]*[:=][ \t]*`?([0-9a-fA-F]{7,40})\b", re.M)
DIRECT = re.compile(r"^[ \t]*GOVERNANCE[ \t]*[:=][ \t]*`?Direct\b", re.M | re.I)


class Invalid(Exception):
    pass


def git(repo, *args, binary=False):
    """(returncode, stdout) of git in repo; stdout is bytes when binary."""
    done = subprocess.run([shutil.which("git") or "git", "-C", str(repo), *args], capture_output=True,
                          **({} if binary else {"encoding": "utf-8", "errors": "replace"}))
    return done.returncode, done.stdout


def default_repo(director):
    code, out = git(director.parent, "rev-parse", "--show-toplevel")
    return pathlib.Path(out.strip()) if code == 0 and out.strip() else None


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def relative(text, root, what):
    """A clean relative path inside root, as posix text; Invalid for an absolute path or one that leaves root."""
    path = pathlib.PurePath(text.replace("\\", "/"))
    if path.is_absolute() or re.match(r"[A-Za-z]:", text) or ".." in path.parts or not path.parts:
        raise Invalid(f"{what} {text}: 要用 {root.name} 裡的相對路徑")
    return pathlib.PurePosixPath(*path.parts).as_posix()


def committed(repo, sha, path):
    """The bytes of path in commit sha, or None when the commit does not hold it."""
    code, kind = git(repo, "cat-file", "-t", f"{sha}:{path}")
    if code or kind.strip() != "blob":
        return None
    return git(repo, "cat-file", "blob", f"{sha}:{path}", binary=True)[1]


def expand(repo, names):
    out = []
    for name in names:
        rel = relative(name, repo, "--file")
        full = repo / rel
        if full.is_dir():
            out += sorted(p.relative_to(repo).as_posix() for p in full.rglob("*") if p.is_file())
        else:
            out.append(rel)
    return list(dict.fromkeys(out))


def load(director):
    path = director / RECORD
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except FileNotFoundError:
        raise Invalid(f"沒有交付紀錄 {RECORD.as_posix()}（先跑 delivery.py record）")
    except UnicodeDecodeError:
        raise Invalid(f"{RECORD.as_posix()} 不是 UTF-8")
    except ValueError as error:
        raise Invalid(f"{RECORD.as_posix()} 不是 JSON（{error}）")
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Invalid(f"{RECORD.as_posix()} 不是 {SCHEMA}")
    for key in ("files", "judgments", "environments"):
        if not isinstance(data.get(key), list):
            raise Invalid(f"{RECORD.as_posix()} 的 {key} 不是清單")
    return data


def now():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def full_commit(repo, value):
    """The 40-hex commit value names in repo, or None."""
    code, out = git(repo, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}")
    out = out.strip().lower()
    return out if code == 0 and HEX40.fullmatch(out) else None


def order_file(director, order):
    """(path, problem): the order DIRECTOR/orders/<WO-ID>*.md; exactly one may match (review P2-7)."""
    folder = director / "orders"
    found = sorted(p for p in folder.glob(f"{order}*.md") if re.fullmatch(re.escape(order) + r"(?:\D.*)?\.md", p.name)) \
        if folder.is_dir() else []
    if not found:
        return None, f"ORDER_NOT_FOUND {order}: orders/ 裡找不到工單，沒辦法核對驗收條件"
    if len(found) > 1:
        return None, (f"AMBIGUOUS_ORDER {order}: orders/ 裡有 {len(found)} 個檔都像這張工單（"
                      + "、".join(p.name for p in found[:4]) + "）；舊的移走，只留一個")
    return found[0], None


def verdict_candidate(director, repo, order):
    """(verdict file, its CANDIDATE_HEAD as a full commit, problem) of the latest *VERDICT* file naming the order
    (review P1-4: the delivered candidate is the one the gate verdict judged)."""
    rx = re.compile(re.escape(order) + r"(?!\d)", re.I)
    found = [p for p in director.rglob("*.md") if ".git" not in p.parts and "VERDICT" in p.name.upper()
             and rx.search(p.name)]
    if not found:
        return None, None, (f"NO_VERDICT {order}: 找不到這張工單的裁決（檔名有 VERDICT 和 {order}，寫 CANDIDATE_HEAD）；"
                            "交付的候選要是裁決驗過的那個")
    latest = max(found, key=lambda p: (p.stat().st_mtime, p.name))
    named = CANDIDATE_HEAD.search(latest.read_bytes().decode("utf-8-sig", errors="replace"))
    full = full_commit(repo, named.group(1).lower()) if named else None
    rel = latest.relative_to(director).as_posix()
    if full is None:
        return rel, None, f"NO_VERDICT {rel}: 裁決的 CANDIDATE_HEAD 沒寫，或不是 repo 裡的 commit"
    return rel, full, None


def cmd_record(a, director, repo):
    candidate = (a.candidate or "").strip().lower()
    if not HEX40.fullmatch(candidate):
        raise Invalid("--candidate 要 40 位的 commit（git rev-parse <分支>）")
    if not a.file:
        raise Invalid("至少一個 --file：要交付的檔或資料夾")
    code, head = git(repo, "rev-parse", "HEAD")
    head = head.strip().lower()
    if code or not HEX40.fullmatch(head):
        raise Invalid(f"{repo.name} 讀不到 HEAD")
    names = expand(repo, a.file)
    problems = []
    if candidate != head:
        problems.append(f"DELIVERY_SHA_MISMATCH: 候選 {candidate[:12]} 不是要交付的 HEAD {head[:12]}：交付的版本必須就是驗過的版本")
    verdict = None
    if not a.order:
        problems.append("NO_ORDER: 要用 --order 寫工單：沒有工單就沒辦法核對每個驗收條件（review P1-5）")
    else:
        path, problem = order_file(director, a.order)
        if problem:
            problems.append(problem)
        elif not DIRECT.search(path.read_bytes().decode("utf-8-sig", errors="replace")):
            verdict, judged, problem = verdict_candidate(director, repo, a.order)
            if problem:
                problems.append(problem)
            elif judged != candidate:
                problems.append(f"VERDICT_MISMATCH: 裁決 {verdict} 驗的是 {judged[:12]}，不是候選 {candidate[:12]}："
                                "沒驗過的 commit 不能交付，先為它重新裁決")
    files = []
    for name in names:
        data = committed(repo, head, name)
        if data is not None:
            code, dirty = git(repo, "status", "--porcelain", "--untracked-files=no", "--", name)
            if code or dirty.strip():
                problems.append(f"DIRTY {name}: 有沒 commit 的改動，交付的不是 commit 裡的版本")
            files.append(dict(path=name, source="commit", **digest(data)))
        elif (repo / name).is_file():
            files.append(dict(path=name, source="build", **digest((repo / name).read_bytes())))
        else:
            problems.append(f"MISSING {name}: commit 裡和磁碟上都沒有")
    if problems:
        for line in problems:
            print(f"  - {line}")
        print("DELIVERY_RECORD: FAIL（沒寫紀錄）")
        return 1
    envs = list(dict.fromkeys(e.strip() for e in a.env if e.strip())) or ["default"]
    judgments = []
    try:
        old = load(director)
    except Invalid:
        old = None
    if old and old.get("candidate") == candidate:
        judgments = old["judgments"]
    elif old and old["judgments"]:
        print(f"  ~ JUDGMENTS_RESET {len(old['judgments'])}: 舊的判定是候選 {str(old.get('candidate'))[:12]} 的，不沿用")
    record = {"schema": SCHEMA, "order": a.order, "candidate": candidate, "delivered": head, "verdict": verdict,
              "recorded": now(), "environments": envs, "files": files, "judgments": judgments}
    write_json_atomic(director / RECORD, record)
    print(f"DELIVERY_RECORD: DONE files={len(files)} candidate={candidate[:12]} environments={','.join(envs)}")
    return 0


def cmd_judge(a, director):
    data = load(director)
    if not (a.ac and AC.fullmatch(a.ac)):
        raise Invalid("--ac 要寫工單的 AC 編號，例如 AC-1")
    envs = data["environments"]
    env = a.env or (envs[0] if len(envs) == 1 else None)
    if env is None:
        raise Invalid(f"紀錄有 {len(envs)} 個環境（{', '.join(envs)}），要用 --env 指定")
    if env not in envs:
        raise Invalid(f"環境 {env} 不在紀錄裡（{', '.join(envs)}）；新環境要重新 record --env")
    if a.outcome != "NOT_RUN" and not a.evidence:
        raise Invalid("判定要附證據檔（--evidence，總監資料夾裡的相對路徑）")
    row = {"ac": a.ac, "env": env, "kind": a.kind, "outcome": a.outcome, "by": a.by or "", "at": now()}
    if a.evidence:
        rel = relative(a.evidence, director, "--evidence")
        if not (director / rel).is_file():
            raise Invalid(f"證據檔 {rel} 不存在")
        row.update(evidence=rel, evidence_sha256=hashlib.sha256((director / rel).read_bytes()).hexdigest())
    data["judgments"].append(row)
    write_json_atomic(director / RECORD, data)
    print(f"DELIVERY_JUDGE: DONE {a.ac}@{env} {a.kind} {a.outcome}")
    return 0


def order_conditions(text):
    """({AC: type}, [AC rows whose type is not AUTO / REVIEW / PO]) of an order's acceptance table (review P1-6)."""
    column, out, unknown = 1, {}, []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if any(c in ("類型", "type") for c in cells):
            column = next(i for i, c in enumerate(cells) if c in ("類型", "type"))
            continue
        if cells and AC.fullmatch(cells[0]):
            kind = cells[column].strip("`* ").upper() if column < len(cells) else ""
            if kind in NEEDS:
                out[cells[0]] = kind
            else:
                unknown.append((cells[0], kind))
    return out, unknown


def old_e2e_records(director):
    """3.0.0 B12: the evidence/E2E/ records (relative names) whose `CANDIDATE:` names a commit other than the
    record's candidate: old runs that --skip-old-e2e leaves out. Empty when there is no readable record."""
    director = pathlib.Path(director)
    try:
        candidate = str(load(director).get("candidate", "")).lower()
    except Invalid:
        return set()
    e2e = director / "evidence" / "E2E"
    old = set()
    for path in sorted(p for p in e2e.rglob("*") if p.is_file() and p.stat().st_size) if e2e.is_dir() else []:
        named = CANDIDATE_LINE.search(path.read_bytes().decode("utf-8", errors="replace"))
        if named and candidate and not candidate.startswith(named.group(1).lower()):
            old.add(path.relative_to(e2e).as_posix())
    return old


def check_delivery(director, repo=None, shipped=None, skip_old_e2e=False):
    """(problems, notes) of DIRECTOR/evidence/DELIVERY.json. A missing or unreadable record is a problem here
    (gate_check --final); delivery.py check turns it into INVALID. shipped: the commit to be pushed (default the
    repo's HEAD), which must still be the delivered one. skip_old_e2e (3.0.0 B12): an E2E record of another
    candidate is a note, not a problem."""
    director = pathlib.Path(director)
    problems, notes = [], []
    try:
        data = load(director)
    except Invalid as error:
        return [f"NO_DELIVERY: {error}；最終驗收要先用 delivery.py record 記下交付的版本和檔案"], notes
    candidate, delivered = str(data.get("candidate", "")).lower(), str(data.get("delivered", "")).lower()
    if not (HEX40.fullmatch(candidate) and HEX40.fullmatch(delivered)):
        problems.append("DELIVERY_SHA: candidate / delivered 不是 40 位 commit")
    if candidate != delivered:
        problems.append(f"DELIVERY_SHA: 交付的 {delivered[:12]} 不是驗過的候選 {candidate[:12]}")
    if not data["files"]:
        problems.append("DELIVERY_FILES: 紀錄沒有列任何交付的檔")
    repo = pathlib.Path(repo) if repo else default_repo(director)
    if repo is None:
        problems.append("NOT_CHECKED files: 找不到 git repo 來核對交付的檔（給 --repo）")
    elif git(repo, "cat-file", "-e", f"{delivered}^{{commit}}")[0]:
        problems.append(f"DELIVERY_SHA: repo 裡沒有交付的 commit {delivered[:12]}")
    else:
        now_head = full_commit(repo, shipped or "HEAD")  # review P1-4 B: HEAD moved on after the record
        if now_head != delivered:
            problems.append(f"HEAD_MOVED: 要交付的 {str(now_head or shipped)[:12]} 不是交付紀錄的 {delivered[:12]}："
                            "紀錄之後又有 commit，要重新裁決、重新 record")
        for entry in data["files"]:
            name = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                problems.append("DELIVERY_FILES: 有一筆沒有 path")
                continue
            body = committed(repo, delivered, name) if entry.get("source") == "commit" else \
                ((repo / name).read_bytes() if (repo / name).is_file() else None)
            if body is None:
                problems.append(f"MISSING {name}: 交付的檔不見了")
            elif digest(body) != {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")}:
                problems.append(f"CHANGED {name}: 大小或雜湊和交付紀錄不同，成品變了")
    e2e = director / "evidence" / "E2E"
    for path in sorted(p for p in e2e.rglob("*") if p.is_file() and p.stat().st_size) if e2e.is_dir() else []:
        text = path.read_bytes().decode("utf-8", errors="replace")
        named = CANDIDATE_LINE.search(text)
        if not named:  # review P2-6: a record that names no candidate does not count
            problems.append(f"E2E_NO_CANDIDATE {path.relative_to(e2e).as_posix()}: 紀錄沒有 `CANDIDATE: <commit>` 行，"
                            "不知道跑的是哪個版本")
        elif not candidate.startswith(named.group(1).lower()):
            if skip_old_e2e:  # 3.0.0 B12: an old run, left out on request
                notes.append(f"E2E_SKIPPED {path.relative_to(e2e).as_posix()}: 跑的是 {named.group(1)[:12]}，"
                             f"不是交付的 {candidate[:12]}；--skip-old-e2e 不算這份舊紀錄")
            else:
                problems.append(f"E2E_OTHER_CANDIDATE {path.relative_to(e2e).as_posix()}: 跑的是 {named.group(1)[:12]}，"
                                f"不是交付的 {candidate[:12]}")
    envs = data["environments"]
    latest = {}
    for row in data["judgments"]:
        if not isinstance(row, dict) or row.get("env") not in envs or row.get("kind") not in KINDS \
                or row.get("outcome") not in OUTCOMES or not AC.fullmatch(str(row.get("ac", ""))):
            problems.append(f"JUDGMENT_INVALID: {json.dumps(row, ensure_ascii=False)[:120]}")
            continue
        latest[(row["ac"], row["env"], row["kind"])] = row
    for (ac, env, kind), row in latest.items():
        tag = f"{ac}@{env} {kind}"
        if row.get("evidence"):
            path = director / str(row["evidence"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("evidence_sha256"):
                problems.append(f"EVIDENCE_CHANGED {tag}: 證據檔 {row['evidence']} 在判定之後變了或不見了")
        if row["outcome"] == "FAIL":
            problems.append(f"JUDGMENT_FAIL {tag}")
    passed = {key for key, row in latest.items() if row["outcome"] == "PASS"}
    order = data.get("order")
    path, problem = order_file(director, order) if order else (None, None)
    text = path.read_bytes().decode("utf-8-sig", errors="replace") if path else ""
    conditions, unknown = order_conditions(text)
    direct = bool(DIRECT.search(text))
    if not order:  # review P1-5: no order, no judgments checked, no final PASS
        problems.append("NO_ORDER: 交付紀錄沒寫工單（record --order），沒辦法核對每個驗收條件")
    elif problem:
        problems.append(problem)
    else:
        if not direct and repo is not None:
            verdict, judged, problem = verdict_candidate(director, repo, order)
            if problem:
                problems.append(problem)
            elif judged != candidate:
                problems.append(f"VERDICT_MISMATCH: 最新的裁決 {verdict} 驗的是 {judged[:12]}，交付紀錄的候選是 "
                                f"{candidate[:12]}")
        elif direct:
            notes.append(f"DIRECT {order}: Direct 工單，沒有裁決可比；候選只和 HEAD 比")
        problems += [f"UNKNOWN_KIND {ac}: 類型 `{kind or '(空白)'}` 不是 AUTO / REVIEW / PO" for ac, kind in unknown]
        if not conditions and not unknown:
            (notes if direct else problems).append(
                f"NO_CONDITIONS {order}: 工單的驗收表讀不到任何 AC 列（| AC-n | AUTO / REVIEW / PO | …）"
                + ("；Direct 工單明寫可以沒有" if direct else ""))
        for env in envs:
            counts = {}
            for ac, kind in sorted(conditions.items(), key=lambda x: int(x[0][3:])):
                need = NEEDS[kind]
                done = (ac, env, need) in passed
                counts.setdefault(need, [0, 0])
                counts[need][0] += done
                counts[need][1] += 1
                if done or (ac, env, need) in latest and latest[(ac, env, need)]["outcome"] == "FAIL":
                    continue
                if need == "po":
                    notes.append(f"PENDING_PO {ac}@{env}: 等 PO 自己判定（最終驗收保留給 PO）")
                elif need == "auto" and (ac, env, "manual") in latest:
                    problems.append(f"JUDGMENT_MISSING {ac}@{env} auto: only a manual run recorded；AUTO 條件要自動跑的紀錄")
                else:
                    problems.append(f"JUDGMENT_MISSING {ac}@{env} {need}")
            manual = sum(1 for (_, e, k) in latest if e == env and k == "manual")
            notes.append(f"ENV {env}: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in counts.items())
                         + f", manual {manual}")
    return problems, notes


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("record", "judge", "check"))
    ap.add_argument("--director", default="DIRECTOR", metavar="DIR")
    ap.add_argument("--repo", metavar="DIR")
    ap.add_argument("--candidate", metavar="SHA")
    ap.add_argument("--file", action="append", default=[], metavar="PATH")
    ap.add_argument("--order", metavar="WO-ID")
    ap.add_argument("--env", action="append", default=[], metavar="NAME")
    ap.add_argument("--ac", metavar="AC-n")
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--outcome", choices=OUTCOMES)
    ap.add_argument("--evidence", metavar="PATH")
    ap.add_argument("--by", metavar="WHO")
    ap.add_argument("--delivered", metavar="SHA", help="check: the commit to be pushed (default HEAD)")
    ap.add_argument("--skip-old-e2e", action="store_true",
                    help="check (3.0.0 B12): leave out E2E records of another CANDIDATE instead of failing")
    a = ap.parse_args(argv)
    tag = {"record": "DELIVERY_RECORD", "judge": "DELIVERY_JUDGE", "check": "DELIVERY_CHECK"}[a.action]
    try:
        director = pathlib.Path(a.director)
        if not director.is_dir():
            raise Invalid(f"沒有總監資料夾 {director}")
        if a.skip_old_e2e and a.action != "check":  # 3.0.0 B12
            raise Invalid("--skip-old-e2e 只配 check")
        if a.action == "judge":
            if len(a.env) > 1 or not a.kind or not a.outcome:
                raise Invalid("judge 要 --ac、--kind、--outcome，--env 最多一個")
            a.env = a.env[0] if a.env else None
            return cmd_judge(a, director)
        repo = pathlib.Path(a.repo) if a.repo else default_repo(director)
        if a.action == "record":
            if repo is None or git(repo, "rev-parse", "--git-dir")[0]:
                raise Invalid("找不到 git repo（給 --repo）")
            return cmd_record(a, director, repo)
        load(director)  # no record, broken JSON or not UTF-8: INVALID, not FAIL
        problems, notes = check_delivery(director, repo, a.delivered, a.skip_old_e2e)
        for line in [f"  - {p}" for p in problems] + [f"  ~ {n}" for n in notes]:
            print(line)
        print(f"{tag}: {'FAIL' if problems else 'PASS'}")
        return 1 if problems else 0
    except (Invalid, OSError) as error:
        print(f"  - {error}")
        print(f"{tag}: INVALID")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

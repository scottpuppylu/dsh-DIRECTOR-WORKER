#!/usr/bin/env python3
"""Director handoff (3.0.0, R5 + C3 + C10): another platform or account takes over from the project's own records and
one sentence: 「讀 `DIRECTOR/INDEX.md`，照它接手，不要重問已確認的需求。」 Plain Markdown, no platform memory.

  handoff.py export [--director DIRECTOR] [--repo REPO ...]
  handoff.py verify [--director DIRECTOR]
  handoff.py quiz   [--director DIRECTOR] --key KEY.json [--repo REPO ...]
  handoff.py score  --key KEY.json --answers ANSWERS.md

--director defaults to DIRECTOR/ under the current folder; --repo to the checkout that holds it (R3 layout). An old
setup with DIRECTOR outside the repo gives --repo.

export  checks INDEX.md, then writes DIRECTOR/HANDOFF_MANIFEST.md: the hash of every record INDEX points to, the
        dispatch history (DISPATCH lines of DIRECTOR_LOG.md), drafts in orders/ that were never dispatched, open
        PO_PENDING items, every worktree's branch, HEAD and uncommitted files, candidate branches (commits the main
        checkout's branch does not have), stashes, and external state (PO_PAGE_URL, GUARDS.md and ACTIVE_WORKSTREAMS.md
        rows). Paths are relative to the director folder, so the project can move. Only reads git.
verify  the same collection again, compared with the manifest: a record, dispatch, draft, worktree or branch that changed
        since export is `STALE` (export again, after updating the records). INDEX.md must name BRIEF.md,
        DECISION_REGISTER.md, RESUME_STATE.md, PO_PENDING.md and DIRECTOR_LOG.md (`INDEX_POINTER`) and each must exist
        (`MISSING`); no INDEX.md is `NO_INDEX`.
quiz    prints 15 questions for the new director (Q01 ... Q15) and writes their answers, drawn from the records, to the
        key file. The key may not sit inside the director folder (the tested director would read it). Q01 (project),
        Q03 (brief state) and Q10 (NEXT_STEP) must be in the records (`MISSING`); others may be NONE.
score   reads `Q01: ...` or `1. ...` lines. An answer is right when it holds at least 60% of the key's words (CJK counts
        in character pairs); a NONE fact is answered by NONE / 無 / 沒有. 14 of 15 pass (the baton fact-retention score).

Last line `HANDOFF_EXPORT|HANDOFF_VERIFY|HANDOFF_QUIZ|HANDOFF_TEST: PASS|DONE|FAIL|INVALID ...`. Exit 0 pass, 1 fail,
2 invalid input (missing folder, manifest, key or answers; not UTF-8; broken JSON): no result is never a pass.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

FORMAT = "dw-handoff/1"
MANIFEST = "HANDOFF_MANIFEST.md"
POINTED = ("BRIEF.md", "DECISION_REGISTER.md", "RESUME_STATE.md", "PO_PENDING.md", "DIRECTOR_LOG.md")
EXTRA = ("INDEX.md", "DIRECTOR_STATE.md", "GUARDS.md", "ACTIVE_WORKSTREAMS.md")
DISPATCH = re.compile(r"\bDISPATCH[ \t]+([^\s|`]+?)(?:\.md)?[ \t]+rev=(\d+)[ \t]+sha=([0-9a-fA-F]{64})")
PASS_SHARE = 0.6
PASS_COUNT = 14
NONE_WORDS = ("none", "無", "沒有", "nothing", "n/a")
ORDER_PREFIX = re.compile(r"([A-Za-z][A-Za-z0-9]*-\d+)(?!\d)")
QUESTIONS = (
    ("Q01", "這個專案叫什麼？"),
    ("Q02", "用一句話說，這個東西是什麼、給誰用？"),
    ("Q03", "專案初衷卡現在是什麼狀態、第幾版？"),
    ("Q04", "使用者確認規格時說的原話是什麼？"),
    ("Q05", "成品是給誰用的（初衷卡「給誰」那一列）？"),
    ("Q06", "使用者明確說絕對不要的是什麼？"),
    ("Q07", "最近一個 PO 決定是哪一個，決定了什麼？"),
    ("Q08", "最近一個總監決定是哪一個，決定了什麼？"),
    ("Q09", "PO 待決頁上還沒關閉的是哪幾項？"),
    ("Q10", "總監的下一步是什麼？"),
    ("Q11", "最後派出的是哪一張工單？"),
    ("Q12", "有哪些工單寫好了但還沒派出？"),
    ("Q13", "有哪些檔改了還沒 commit？"),
    ("Q14", "有哪些候選分支（主分支還沒有的 commit）？"),
    ("Q15", "PO 待決頁的網址是什麼？"),
)
REQUIRED = ("Q01", "Q03", "Q10")


class Invalid(Exception):
    pass


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPEC = load("dw_spec_gate", "spec_gate.py")


def read(path):
    """UTF-8 text of a file, or None when it does not exist; Invalid when it is not UTF-8."""
    try:
        return pathlib.Path(path).read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        raise Invalid(f"{pathlib.Path(path).name} is not UTF-8 text")


def rel(path, base):
    try:
        return pathlib.Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # another drive on Windows
        return pathlib.Path(path).as_posix()


def git(repo, *args):
    done = subprocess.run([shutil.which("git") or "git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace")
    return done.stdout if done.returncode == 0 else None


def default_repo(director):
    top = git(director.parent, "rev-parse", "--show-toplevel")
    return [pathlib.Path(top.strip())] if top and top.strip() else []


def index_problems(director):
    text = read(director / "INDEX.md")
    if text is None or not text.strip():
        return ["NO_INDEX: DIRECTOR/INDEX.md 不存在或是空的（換手的唯一入口，骨架見 templates/DIRECTOR_FILES.md）"]
    found = [f"INDEX_POINTER {name}: INDEX.md 沒寫 {name} 在哪裡" for name in POINTED if name not in text]
    found += [f"MISSING {name}: INDEX.md 指到的檔不存在" for name in POINTED if name in text and not (director / name).is_file()]
    return found


def file_entry(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()}


def dispatches(director):
    text = read(director / "DIRECTOR_LOG.md") or ""
    return [{"order": m.group(1), "rev": int(m.group(2)), "sha": m.group(3).lower()}
            for m in (DISPATCH.search(line) for line in text.splitlines()) if m]


def order_names(stem):
    """The names a DISPATCH line may call the order file stem: the stem, and its leading ID (`WO-003-login` is also
    `WO-003`), upper-case (review P1-7)."""
    names = {stem.upper()}
    lead = ORDER_PREFIX.match(stem)
    if lead:
        names.add(lead.group(1).upper())
    return names


def drafts(director, sent):
    """Order files no DISPATCH line names, by file stem or by its leading ID."""
    folder = director / "orders"
    names = {d["order"].upper() for d in sent}
    return sorted(p.stem for p in folder.glob("*.md") if not order_names(p.stem) & names) if folder.is_dir() else []


def open_items(director):
    text = read(director / "PO_PENDING.md") or ""
    part = text.split("## 未關閉", 1)[1].split("\n## ", 1)[0] if "## 未關閉" in text else ""
    found, current = [], None
    for line in part.splitlines():
        m = re.match(r"^\s*ID\s*[:：]\s*((?:OD|ACT|CH)-\d+)\b", line)  # 3.0.0: CH-xx, a web choice question
        if m:
            current = m.group(1)
            continue
        s = re.match(r"^\s*STATUS\s*[:：]\s*(\S+)\s*$", line)
        if s and current:
            if s.group(1).lower() in ("open", "answered"):
                found.append(current)
            current = None
    return found


def table_rows(text):
    return [line.strip() for line in (text or "").splitlines()
            if line.strip().startswith("|") and not re.match(r"^\|[\s|:-]+\|$", line.strip())][1:]


def external(director):
    out = []
    url = SPEC.field(read(director / "DIRECTOR_STATE.md") or "", "PO_PAGE_URL")
    if url:
        out.append(f"PO_PAGE_URL: {url}")
    for name in ("GUARDS.md", "ACTIVE_WORKSTREAMS.md"):
        out += [f"{name}: {row}" for row in table_rows(read(director / name))]
    return out


def repo_state(repo, director):
    listing = git(repo, "worktree", "list", "--porcelain")
    if listing is None:
        raise Invalid(f"git cannot read {repo}")
    trees, cur = [], {}
    for line in listing.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": line[9:].strip()}
        elif line.startswith("HEAD "):
            cur["head"] = line[5:].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[7:].strip().removeprefix("refs/heads/")
        elif not line and cur:
            trees.append(cur)
            cur = {}
    for tree in trees:
        status = git(tree["path"], "status", "--porcelain", "--untracked-files=all") or ""
        tree["dirty"] = sorted(line.rstrip() for line in status.splitlines() if line.strip())
        tree.setdefault("branch", "(detached)")
        tree["path"] = rel(tree["path"], director)
    main = trees[0]["branch"] if trees else "HEAD"
    candidates = []
    refs = git(repo, "for-each-ref", "--format=%(refname:short)\t%(upstream:short)\t%(upstream:track)", "refs/heads") or ""
    for line in refs.splitlines():
        name, upstream, track = (line.split("\t") + ["", ""])[:3]
        if name == main:
            continue
        ahead = git(repo, "rev-list", "--count", f"{main}..{name}")
        if ahead and int(ahead.strip() or 0) > 0:
            candidates.append({"branch": name, "ahead": int(ahead.strip()), "upstream": upstream, "track": track})
    stashes = len((git(repo, "stash", "list") or "").splitlines())
    return {"path": rel(repo, director), "main": main, "worktrees": trees, "candidates": candidates, "stashes": stashes}


def collect(director, repos):
    files = {}
    for name in POINTED + EXTRA:
        if (director / name).is_file():
            read(director / name)  # Invalid when not UTF-8
            files[name] = file_entry(director / name)
    sent = dispatches(director)
    return {"format": FORMAT, "files": files, "dispatches": sent, "drafts": drafts(director, sent),
            "open_items": open_items(director), "repos": [repo_state(r, director) for r in repos],
            "external": external(director)}


def bullet(items):
    return "\n".join(f"- {x}" for x in items) if items else "- NONE"


def render(state, made):
    trees = [f"{r['path']} 的 {t['path']}：{t['branch']} @ {t.get('head', '')[:12]}" for r in state["repos"] for t in r["worktrees"]]
    dirty = [f"{t['path']}：`{line}`" for r in state["repos"] for t in r["worktrees"] for line in t["dirty"]]
    cands = [f"{c['branch']}（比 {r['main']} 多 {c['ahead']} 個 commit{'，追 ' + c['upstream'] + ' ' + c['track'] if c['upstream'] else ''}）"
             for r in state["repos"] for c in r["candidates"]]
    stashes = [f"{r['path']}：{r['stashes']} 個 stash" for r in state["repos"] if r["stashes"]]
    parts = [
        "# 換手清單（handoff.py export 產生；不要手改，改了紀錄就重跑 export）", "",
        f"產生時間：{made}。接手的總監先跑 `handoff.py verify`；STALE 表示這份清單之後紀錄又變了。", "",
        "## 派工紀錄", bullet([f"{d['order']} rev={d['rev']}" for d in state["dispatches"]]), "",
        "## 還沒派出的草稿", bullet(state["drafts"]), "",
        "## 未關閉的待決事項", bullet(state["open_items"]), "",
        "## 工作副本", bullet(trees), "",
        "## 沒 commit 的工作", bullet(dirty + stashes), "",
        "## 候選分支", bullet(cands), "",
        "## 外部狀態", bullet(state["external"]), "",
        "## 紀錄檔", bullet([f"{n}：{v['bytes']} bytes sha256={v['sha256'][:16]}" for n, v in state["files"].items()]), "",
        "```json", json.dumps(state, ensure_ascii=False, indent=1), "```", "",
    ]
    return "\n".join(parts)


def parse_manifest(path):
    text = read(path)
    if text is None:
        raise Invalid(f"沒有 {path.name}：先跑 handoff.py export")
    m = re.search(r"```json\n(.*?)\n```", text.replace("\r\n", "\n"), re.S)
    try:
        state = json.loads(m.group(1)) if m else None
    except json.JSONDecodeError as error:
        raise Invalid(f"{path.name} 的 JSON 壞了：{error}")
    if not isinstance(state, dict) or state.get("format") != FORMAT:
        raise Invalid(f"{path.name} 不是 {FORMAT} 格式的換手清單")
    return state


def diff(old, new):
    found = []
    for name in sorted(set(old.get("files", {})) | set(new["files"])):
        if old.get("files", {}).get(name, {}).get("sha256") != new["files"].get(name, {}).get("sha256"):
            found.append(f"STALE {name}: export 之後改過（或新增、刪除）")
    for key, label in (("dispatches", "派工紀錄"), ("drafts", "草稿"), ("open_items", "待決事項"), ("external", "外部狀態")):
        a = [json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, dict) else x for x in old.get(key, [])]
        b = [json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, dict) else x for x in new[key]]
        if a != b:
            show = lambda xs: ", ".join(json.loads(x)["order"] if x.startswith("{") else x for x in xs)[:200] or "NONE"  # noqa: E731
            found.append(f"STALE {label}: 多了 {show([x for x in b if x not in a])}；少了 {show([x for x in a if x not in b])}")
    old_repos = {r.get("path"): r for r in old.get("repos", [])}
    for repo in new["repos"]:
        before = old_repos.pop(repo["path"], None)
        if before is None:
            found.append(f"STALE repo {repo['path']}: 清單裡沒有")
            continue
        old_trees = {t.get("path"): t for t in before.get("worktrees", [])}
        for tree in repo["worktrees"]:
            was = old_trees.pop(tree["path"], None)
            if was is None:
                found.append(f"STALE worktree {tree['path']}: 新開的")
                continue
            if (was.get("branch"), was.get("head")) != (tree["branch"], tree.get("head")):
                found.append(f"STALE worktree {tree['path']}: {was.get('branch')} @ {str(was.get('head'))[:12]} → "
                             f"{tree['branch']} @ {tree.get('head', '')[:12]}")
            if was.get("dirty") != tree["dirty"]:
                plus = [x for x in tree["dirty"] if x not in was.get("dirty", [])]
                minus = [x for x in was.get("dirty", []) if x not in tree["dirty"]]
                found.append(f"STALE worktree {tree['path']}: 沒 commit 的檔多了 {plus or 'NONE'}，少了 {minus or 'NONE'}")
        found += [f"STALE worktree {p}: 不見了" for p in old_trees]
        if before.get("candidates") != repo["candidates"] or before.get("stashes") != repo["stashes"]:
            found.append(f"STALE repo {repo['path']}: 候選分支或 stash 變了")
    found += [f"STALE repo {p}: 清單有，現在找不到" for p in old_repos]
    return found


def repos_from(args, director, manifest=None):
    if args.repo:
        return [pathlib.Path(r) for r in args.repo]
    if manifest is not None:
        return [(director / r["path"]).resolve() for r in manifest.get("repos", [])]
    return default_repo(director)


def now():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def cmd_export(args, director):
    problems = index_problems(director)
    for line in problems:
        print(f"  - {line}")
    if problems:
        print(f"HANDOFF_EXPORT: FAIL director={director} problems={len(problems)}（先把 INDEX.md 補齊）")
        return 1
    repos = repos_from(args, director)
    if not repos:
        print("~ WARN no repo: the director folder is not inside a git checkout; give --repo to list worktrees")
    state = collect(director, repos)
    load("dw_common", "_common.py").write_text_atomic(director / MANIFEST, render(state, now()))
    dirty = sum(len(t["dirty"]) for r in state["repos"] for t in r["worktrees"])
    cands = sum(len(r["candidates"]) for r in state["repos"])
    print(f"HANDOFF_EXPORT: DONE file={MANIFEST} dispatches={len(state['dispatches'])} drafts={len(state['drafts'])} "
          f"dirty={dirty} candidates={cands} external={len(state['external'])}")
    return 0


def cmd_verify(args, director):
    old = parse_manifest(director / MANIFEST)
    problems = index_problems(director)
    problems += diff(old, collect(director, repos_from(args, director, old)))
    for line in problems:
        print(f"  - {line}")
    state = "FAIL" if problems else "PASS"
    print(f"HANDOFF_VERIFY: {state} director={director} problems={len(problems)}")
    return 1 if problems else 0


def cell(row, n):
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return cells[n] if len(cells) > n else ""


def last_row(text, prefix):
    rows = [r for r in table_rows(text) if cell(r, 0).startswith(prefix) and SPEC.filled(cell(r, 2))]
    return f"{cell(rows[-1], 0)} {cell(rows[-1], 2)}" if rows else None


def brief_row(text, kind):
    for row in table_rows(text):
        if re.match(r"B-\d+", cell(row, 0)) and kind in cell(row, 1) and SPEC.filled(cell(row, 2)):
            return cell(row, 2)
    return None


def facts(director, repos):
    brief = SPEC.strip_comments(read(director / "BRIEF.md") or "")
    resume = read(director / "RESUME_STATE.md") or ""
    decisions = read(director / "DECISION_REGISTER.md") or ""
    pick = lambda v: v if SPEC.filled(v) else None  # noqa: E731
    status, rev = SPEC.field(brief, "狀態"), SPEC.revision(brief)
    nxt = re.search(r"^\s*\**NEXT_STEP\**\s*[:：]\s*(.+)$", resume, re.M)
    sent = dispatches(director)
    state = [repo_state(r, director) for r in repos]
    answers = {
        "Q01": pick(SPEC.field(brief, "專案")),
        "Q02": pick(SPEC.field(brief, "一句話")),
        "Q03": f"{status} 版次 {rev}" if pick(status) and rev is not None else None,
        "Q04": pick(SPEC.field(brief, "使用者確認原話")),
        "Q05": brief_row(brief, "給誰"),
        "Q06": brief_row(brief, "絕對不要"),
        "Q07": last_row(decisions, "PO-"),
        "Q08": last_row(decisions, "DD-"),
        "Q09": "、".join(open_items(director)) or None,
        "Q10": pick(nxt.group(1).strip()) if nxt else None,
        "Q11": sent[-1]["order"] if sent else None,
        "Q12": "、".join(drafts(director, sent)) or None,
        "Q13": "、".join(line[3:].strip() for r in state for t in r["worktrees"] for line in t["dirty"]) or None,
        "Q14": "、".join(c["branch"] for r in state for c in r["candidates"]) or None,
        "Q15": pick(SPEC.field(read(director / "DIRECTOR_STATE.md") or "", "PO_PAGE_URL")),
    }
    return answers


def inside(path, folder):
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def cmd_quiz(args, director):
    key = pathlib.Path(args.key)
    if inside(key, director):
        print(f"  - KEY_IN_DIRECTOR: 答案檔 {key} 在總監資料夾裡，接手的總監會讀到；放到別的地方")
        print("HANDOFF_QUIZ: INVALID (答案檔位置不對)")
        return 2
    answers = facts(director, repos_from(args, director))
    missing = [q for q in REQUIRED if not answers[q]]
    for q in missing:
        print(f"  - MISSING {q}: 紀錄裡找不到（{dict(QUESTIONS)[q]}）；新總監靠紀錄接手，這一項一定要寫")
    if missing:
        print(f"HANDOFF_QUIZ: FAIL missing={len(missing)}（先補紀錄再換手）")
        return 1
    for q, text in QUESTIONS:
        print(f"{q} {text}")
    data = {"format": FORMAT, "made": now(), "pass": PASS_COUNT,
            "facts": [{"id": q, "question": text, "answer": answers[q] or "NONE"} for q, text in QUESTIONS]}
    load("dw_common", "_common.py").write_json_atomic(key, data)
    print(f"HANDOFF_QUIZ: PASS questions={len(QUESTIONS)} key={key}（題目給新總監，答案檔不要給）")
    return 0


WORD = re.compile(r"[0-9a-z]+|[぀-ヿ㐀-鿿豈-﫿]+")


def words(text):
    out = set()
    for w in WORD.findall(text.lower()):
        if re.match(r"[぀-ヿ㐀-鿿豈-﫿]", w) and len(w) > 1:
            out.update(w[i:i + 2] for i in range(len(w) - 1))
        else:
            out.add(w)
    return out


def right(answer, key):
    said = answer.strip().strip("「」\"'。.").lower()
    if key == "NONE":
        return said in NONE_WORDS or said in ("0", "-")  # review P2-13: 「無法確定」 is not 「無」
    want = words(key)
    return bool(want) and len(want & words(answer)) / len(want) >= PASS_SHARE


def cmd_score(args):
    raw = read(args.key)
    text = read(args.answers)
    if raw is None or text is None:
        raise Invalid(f"讀不到 {'--key' if raw is None else '--answers'} 檔")
    try:
        key = json.loads(raw)
        facts_ = [(f["id"], f["answer"]) for f in key["facts"]]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise Invalid(f"答案檔格式不對：{error}")
    given = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(?:Q)?0*(\d{1,2})\s*[:：.、)）]\s*(.*)$", line, re.I)
        if m:
            given.setdefault(f"Q{int(m.group(1)):02d}", m.group(2))
    score = 0
    for q, answer in facts_:
        if q not in given or not given[q].strip():
            print(f"  - NO_ANSWER {q}")
        elif right(given[q], answer):
            score += 1
        else:
            print(f"  - WRONG {q}: 答「{given[q][:60]}」，紀錄是「{answer[:60]}」")
    need = int(key.get("pass", PASS_COUNT))
    state = "PASS" if score >= need else "FAIL"
    print(f"HANDOFF_TEST: {state} score={score}/{len(facts_)} pass>={need}")
    return 0 if state == "PASS" else 1


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("export", "verify", "quiz", "score"))
    ap.add_argument("--director", default="DIRECTOR", metavar="DIR")
    ap.add_argument("--repo", action="append", default=[], metavar="DIR")
    ap.add_argument("--key", metavar="KEY.json")
    ap.add_argument("--answers", metavar="ANSWERS.md")
    a = ap.parse_args(argv)
    tag = {"export": "HANDOFF_EXPORT", "verify": "HANDOFF_VERIFY", "quiz": "HANDOFF_QUIZ", "score": "HANDOFF_TEST"}[a.action]
    try:
        if a.action == "score":
            if not a.key or not a.answers:
                raise Invalid("score 要 --key 和 --answers")
            return cmd_score(a)
        director = pathlib.Path(a.director)
        if not director.is_dir():
            raise Invalid(f"沒有總監資料夾 {director}")
        if a.action == "quiz" and not a.key:
            raise Invalid("quiz 要 --key（答案檔，放在總監資料夾外）")
        return {"export": cmd_export, "verify": cmd_verify, "quiz": cmd_quiz}[a.action](a, director)
    except (Invalid, OSError) as error:
        print(f"  - {error}")
        print(f"{tag}: INVALID")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

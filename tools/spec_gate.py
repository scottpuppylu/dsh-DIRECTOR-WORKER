#!/usr/bin/env python3
"""Spec gate (3.0.0, R6 + R7 + C1): no dispatch before the requirements are talked through and the user confirmed
them. Only reads, except `approve`, which writes one snapshot file. The same gate in general and beginner mode: it
does not depend on hook_guard (beginner mode installs no hook), gate_check.py --hash and dispatch_check.py --log run it.

  spec_gate.py check   [--brief DIRECTOR/BRIEF.md] [--snapshot-dir DIR]
  spec_gate.py approve [--brief DIRECTOR/BRIEF.md] [--snapshot-dir DIR]

--brief defaults to DIRECTOR/BRIEF.md under the current folder; --snapshot-dir to brief-history/ beside the brief.

The brief (templates/BRIEF.md) fails when any of these holds:
  NOT_LOCKED       `狀態：LOCKED` is missing (a draft is not a confirmed spec) or `版次` is not a number
  NO_CONFIRM_TIME  `使用者確認時間` is empty, NONE or a <placeholder>
  NO_CONFIRM_WORDS `使用者確認原話` (the user's own words when confirming) is empty, NONE or a <placeholder>
  OPEN_ITEMS       the `## 未決事項` section is missing, or one of its items starts with neither 已解決：
                   nor 暫緩： with the user's words in 「…」 (write `- 無` when there are none)
  INCOMPLETE_SPEC  R6's content is not written (review P1-2): `一句話` is empty or a <placeholder>; the B table has no
                   `給誰` row or no `一定要有` row; a B row's 內容 or 怎麼算做到 is empty or a <placeholder>; or the
                   `## 限制` section is missing or has no `- ` item other than a <placeholder> (`- 無` is an answer)
  NO_PRIOR_ART     the `## 現成方案調查` section (R7: what was searched, what is used, why not the others) is missing
                   or has no `- ` item other than a <placeholder> (the instruction text does not count)
  NOT_APPROVED     check only: no snapshot of this exact brief in the snapshot folder; `approve` writes it
  CHANGED          check only: snapshots exist, none of the latest 版次 is this brief: the brief changed after the
                   user confirmed it (or went back to an older approved 版次), so the spec goes back through the gate
                   (talk it over, 版次 +1, confirm again, approve again)
  REAPPROVE_WITHOUT_CONFIRM
                   approve only: snapshots exist and this brief is a new one, but its 版次 is not above the latest
                   snapshot's, or its 使用者確認時間 / 使用者確認原話 are the same as there: a changed brief is approved
                   again only after the user confirmed it again (an approve cannot wash a CHANGED away)

approve runs the same content checks and the REAPPROVE check; when they pass it writes <DIR>/<版次>-<sha256>.md atomically (the same file
`gate_check.py --brief --snapshot` writes; an identical file is kept) and prints the BRIEF_LOCKED line for
DIRECTOR_LOG.md. The sha256 reads CRLF as LF.

Last line `SPEC_GATE: PASS|FAIL|INVALID brief=<path> ...`. Exit 0 PASS, 1 FAIL, 2 INVALID (the brief is missing,
empty or not UTF-8: no result is never a pass).
"""
import argparse
import hashlib
import importlib.util
import pathlib
import re
import sys

PLACEHOLDER = re.compile(r"<(?!!--)[^<>\n]+>")
EMPTY = ("", "none", "無", "n/a", "na", "-", "—")


def load_common():
    spec = importlib.util.spec_from_file_location("dw_common", pathlib.Path(__file__).with_name("_common.py"))
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    return common


def brief_hash(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def field(text, name):
    """The value of a `- name：value` line, or None when the line is missing."""
    m = re.search(rf"^\s*[-*]?\s*{name}\s*[:：][ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def filled(value):
    return value is not None and value.strip().lower() not in EMPTY and not PLACEHOLDER.search(value)


def section(text, title):
    """The lines of the `## title...` section up to the next `## ` heading, or None when it is missing."""
    m = re.search(rf"^##[ \t]+{title}[^\n]*\n(.*?)(?=^##[ \t]|\Z)", text, re.M | re.S)
    return m.group(1).splitlines() if m else None


def items(lines):
    return [re.sub(r"^\s*[-*]\s+", "", line).strip() for line in lines if re.match(r"^\s*[-*]\s+\S", line)]


def revision(text):
    m = re.search(r"^\s*[-*]?\s*版次\s*[:：]\s*(\d+)\s*$", text, re.M)
    return int(m.group(1)) if m else None


SNAPSHOT_NAME = re.compile(r"(\d+)-([0-9a-f]{64})\.md")


def snapshots(folder):
    """[(版次, path)] of the <版次>-<sha256>.md snapshots in folder, ordered by the 版次 number (10 after 9)."""
    folder = pathlib.Path(folder)
    found = [(int(m.group(1)), path) for path in (folder.glob("*-*.md") if folder.is_dir() else [])
             if (m := SNAPSHOT_NAME.fullmatch(path.name))]
    return sorted(found, key=lambda pair: (pair[0], pair[1].name))


def reapprove_problem(data, folder):
    """3.0.0 review P1-1: None, or why approving this brief would wash a CHANGED away. With snapshots there, a brief
    that is not one of them needs a 版次 above the latest snapshot's and a confirm time and words of its own."""
    found = snapshots(folder)
    sha = brief_hash(data)
    latest_rev, latest = found[-1] if found else (None, None)
    if not found or any(rev == latest_rev and path.name.endswith(f"-{sha}.md") and brief_hash(path.read_bytes()) == sha
                        for rev, path in found):
        return None  # the latest approved brief itself: approve again keeps its file
    text = strip_comments(data.decode("utf-8-sig", errors="replace"))
    try:
        old = strip_comments(latest.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        old = ""
    rev, why = revision(text), []
    if rev is None or rev <= latest_rev:
        why.append(f"版次 {rev} 沒有大於最近核准的 {latest_rev}")
    for name in ("使用者確認時間", "使用者確認原話"):
        if field(text, name) == field(old, name):
            why.append(f"{name}和 {latest.name} 一樣")
    if not why:
        return None
    return ("REAPPROVE_WITHOUT_CONFIRM: 初衷卡在核准之後改過，可是" + "、".join(why)
            + "；改過的需求要先給使用者看、版次 +1、記下這次確認的時間和原話，再跑 approve")


def brief_rows(text):
    """[(B-n, cells)] of the B table's rows; rows inside ``` fences do not count."""
    text = re.sub(r"^[ \t]*```.*?^[ \t]*```[^\n]*$", "", text, flags=re.M | re.S)
    rows = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            key = re.sub(r"[*`\s]", "", cells[0])
            if re.fullmatch(r"B-\d+", key):
                rows.append((key, cells))
    return rows


def spec_problems(text):
    """[(INCOMPLETE_SPEC, why)]: R6 items 1-4 (給誰, 一定要有, 絕對不要, 怎麼算做到) and the limits are written."""
    found = []
    if not filled(field(text, "一句話")):
        found.append(("INCOMPLETE_SPEC", "「一句話」沒填：用使用者自己的話寫這個東西是什麼、給誰用"))
    rows = brief_rows(text)
    for kind in ("給誰", "一定要有"):
        if not any(len(cells) > 1 and kind in cells[1] for _, cells in rows):
            found.append(("INCOMPLETE_SPEC", f"B 表沒有「{kind}」那一列"))
    for key, cells in rows:
        if len(cells) < 4 or not filled(cells[2]) or not filled(cells[3]):
            found.append(("INCOMPLETE_SPEC", f"{key} 的內容或「怎麼算做到」沒填（還是空的或 <…>）"))
    limits = section(text, "限制")
    if limits is None or not [item for item in items(limits) if item and not PLACEHOLDER.search(item)]:
        found.append(("INCOMPLETE_SPEC", "「## 限制」沒寫：預算、時間、平台、授權……使用者說過的限制；沒有就寫「- 無」"))
    return found


def content_problems(text):
    """[(code, plain-words reason)] for the brief's content; [] when it is a complete, confirmed spec."""
    text = strip_comments(text)
    found = []
    if not re.search(r"^\s*[-*]?\s*狀態\s*[:：]\s*LOCKED\s*$", text, re.M) or revision(text) is None:
        found.append(("NOT_LOCKED", "初衷卡還不是 LOCKED（或版次不是數字）：使用者還沒確認這份規格"))
    if not filled(field(text, "使用者確認時間")):
        found.append(("NO_CONFIRM_TIME", "沒有記使用者確認的時間（讀系統時鐘寫上）"))
    if not filled(field(text, "使用者確認原話")):
        found.append(("NO_CONFIRM_WORDS", "沒有記使用者確認時說的原話"))
    open_lines = section(text, "未決事項")
    if open_lines is None:
        found.append(("OPEN_ITEMS", "少了「## 未決事項」一節（沒有未決事項就寫「- 無」）"))
    else:
        listed = items(open_lines)
        if not listed:
            found.append(("OPEN_ITEMS", "「未決事項」是空的；沒有未決事項就寫「- 無」"))
        for item in listed:
            if item.lower() in EMPTY[1:]:
                continue
            settled = re.match(r"已解決[:：][ \t]*\S", item) or (  # review P2-1: the item starts with it
                re.match(r"暫緩[:：]", item) and re.search(r"「[^」]+」", item))
            if PLACEHOLDER.search(item) or not settled:
                found.append(("OPEN_ITEMS", f"未決事項還沒清掉：「{item[:60]}」（寫「已解決：…」，或「暫緩：使用者原話「…」」）"))
    found += spec_problems(text)
    prior = section(text, "現成方案調查")
    real = [item for item in items(prior or []) if filled(item)]
    if prior is None or not real:
        found.append(("NO_PRIOR_ART", "「現成方案調查」是空的：動手前先找現成的，寫下找了什麼、用哪個、不用的理由"))
    return found


def check(brief, folder, approve=False):
    """(status, lines). status PASS / FAIL / INVALID."""
    brief = pathlib.Path(brief)
    try:
        data = brief.read_bytes()
        text = data.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        why = "file not found" if isinstance(error, FileNotFoundError) else type(error).__name__
        return "INVALID", [f"  - NO_BRIEF: 讀不到初衷卡 {brief}（{why}）；先和使用者談完需求，照 templates/BRIEF.md 寫"]
    if not text.strip():
        return "INVALID", [f"  - NO_BRIEF: 初衷卡 {brief} 是空的"]
    sha, rev = brief_hash(data), revision(strip_comments(text))
    lines = [f"  - {code}: {why}" for code, why in content_problems(text)]
    folder = pathlib.Path(folder)
    if not lines and approve:
        stale = reapprove_problem(data, folder)
        if stale:
            return "FAIL", [f"  - {stale}"]
        target, written = write_snapshot(data, folder, f"{rev}-{sha}.md")
        lines.append(f"  SNAPSHOT {target} ({'written' if written else 'already there, kept'})")
        lines.append(f"  BRIEF_LOCKED rev={rev} sha={sha} snapshot={folder.name}/{target.name}")
        return "PASS", lines
    if not lines:
        target = folder / f"{rev}-{sha}.md"
        found = snapshots(folder)
        approved = target.is_file() and brief_hash(target.read_bytes()) == sha
        if not approved or rev < found[-1][0]:  # only the latest 版次 counts (review P2-2)
            if found:
                lines.append(f"  - CHANGED: 初衷卡在確認之後又改過（最近核准的是 {found[-1][1].name}）；"
                             "需求改了要回到關卡：和使用者談、版次 +1、重新確認，再跑 approve")
            else:
                lines.append(f"  - NOT_APPROVED: {folder} 裡沒有這份初衷卡的快照；使用者確認後跑 "
                             "`spec_gate.py approve`")
    return ("FAIL" if lines else "PASS"), lines


def write_snapshot(data, folder, name):
    target = pathlib.Path(folder) / name
    if target.is_file() and brief_hash(target.read_bytes()) == brief_hash(data):
        return target, False
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    return load_common().write_bytes_atomic(target, data), True


def default_folder(brief):
    return pathlib.Path(brief).parent / "brief-history"


def run(brief, folder=None, approve=False, out=print):
    """Print the result lines and the SPEC_GATE line; return the exit code (0 / 1 / 2). For gate_check and
    dispatch_check, which load this file by path."""
    status, lines = check(brief, folder or default_folder(brief), approve)
    for line in lines:
        out(line)
    out(f"SPEC_GATE: {status} brief={brief}" + ("" if status == "PASS" else " (不准派工：先把需求和規格談完、使用者確認)"))
    return {"PASS": 0, "FAIL": 1}.get(status, 2)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("check", "approve"))
    ap.add_argument("--brief", default="DIRECTOR/BRIEF.md", metavar="BRIEF.md")
    ap.add_argument("--snapshot-dir", metavar="DIR")
    a = ap.parse_args(argv)
    return run(a.brief, a.snapshot_dir, a.action == "approve")


if __name__ == "__main__":
    raise SystemExit(main())

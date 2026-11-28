# 換總監（換平台、換帳號）

3.0.0（R5、C3、C10）。新總監只靠專案資料夾裡的紀錄和一句提示詞接手，不搬對話紀錄，也不靠任何平台的記憶功能。紀錄全是一般 Markdown，Claude Code、Codex、Antigravity、DeepSeek 都讀得懂。

## 提示詞

在新平台或新帳號開一個對話，資料夾選同一個專案，貼這一句：

```text
讀 `DIRECTOR/INDEX.md`，照它接手，不要重問已確認的需求。
```

對方讀不到檔案、或不會自己跑指令時，改貼這段：

```text
你接手這個專案的「總監」。讀 `DIRECTOR/INDEX.md`，照它接手，不要重問已確認的需求。
1. 先跑 `python -I -X utf8 DIRECTOR/tools/handoff.py verify --director DIRECTOR`。PASS 才接著做；FAIL 或 STALE 就照實告訴我哪裡對不上，不要猜。
2. INDEX 列的檔照順序讀：規格、決策、進度和下一步、未決事項、日誌、換手清單。
3. 已鎖定的規格、PO 決定照做，不重問；要改，照原本的流程開題問我。
4. 回我一則：你接手了什麼、下一步做什麼、有哪些還在等我決定。用我平常用的語言。
```

## 交出去的總監

1. 停在安全的地方：worker 先停或先記好 RESUME_STATE，背景程序記 PID。
2. 補紀錄：`RESUME_STATE.md` 頂部四行、`DECISION_REGISTER.md`、`PO_PENDING.md`、`DIRECTOR_LOG.md`、`INDEX.md`。
3. `handoff.py export --director DIRECTOR`，要印 `HANDOFF_EXPORT: DONE`。它把派工紀錄、還沒派出的草稿、沒 commit 的工作、候選分支和外部狀態（待決頁網址、排程、工作線）寫進 `DIRECTOR/HANDOFF_MANIFEST.md`。
4. 之後再改紀錄，就再跑一次 export。

## 接手的總監

1. `handoff.py verify --director DIRECTOR`。`STALE` 表示 export 之後又有變動：照列出的項目核對，不要直接沿用。
2. 照 `docs/06b` 的恢復程序做第一輪。

## 換手測試（15 題，答對 14 題才算過）

每個變體發版前跑。計分方法借 baton 的「事實保留數」。

1. 舊總監（或測試的人）：`handoff.py quiz --director DIRECTOR --key <總監資料夾外>/key.json`。它從紀錄抽 15 個事實，印出 15 題，答案寫進 key。key 放在總監資料夾裡會被拒絕。紀錄缺專案名稱、初衷卡狀態或下一步時是 FAIL：先補紀錄。
2. 新平台的總監只拿到上面那一句提示詞和 15 題，不能問使用者。答案寫成 `Q01: …` 一行一題。
3. `handoff.py score --key key.json --answers answers.md`。至少 14 題對才是 PASS。
4. 路線：DW→cdx、cdx→DW、DW→dsh、DW→agy，再加同平台換帳號。結果記在發版的 CHANGELOG。

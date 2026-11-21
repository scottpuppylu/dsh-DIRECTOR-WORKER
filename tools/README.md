# tools — dsh-DIRECTOR-WORKER（簡稱 dshdw；舊名 DIRECTOR-WORK DeepSeek 版（DW-DS））

Python 3.9 以上，只用標準函式庫。一律用 bundled Python 執行：`python -I -X utf8 <tool>.py ...`
（`-I` 不從目前資料夾載入模組；執行檔路徑見 `docs/11`）。每支都有 `--help`，沒有寫死的本機路徑。
完整 CLI 契約、與上游的差異、已知限制看 [`DSH-TOOLS.md`](DSH-TOOLS.md)。

DSH 沒有 hooks、沒有 PO 頁、沒有 Claude 額度查詢；所以**沒有東西會自動跑**：用量、動作紀錄、環境檢查都是事後由總監或 worker 手動執行，`dsh_guard.py` 只是自律檢查，不是攔截器。

## DSH 新增

| 工具 | 做什麼 | 寫檔 |
|---|---|---|
| `dsh_session.py` | 共用庫：找 Node、解 session `*.jsonl.zstd` 的 zstd frames、列 session、從父 catalog 對 agent 名稱、讀投影快取。2.2.4-ds.4 唯一的 CLI：`--temp-env <WORK_DIR>` 建 `WORK_DIR/tmp`，印出把 TEMP／TMP／TMPDIR 指過去的 PowerShell 與 bash 設定行 | `--temp-env` 只建 `WORK_DIR/tmp` |
| `dsh_usage.py` | 每 session 的 input/output/cacheRead/cacheWrite、最後 prompt tokens、context 使用率、effort/model、每日彙總。2.2.4-ds.4：`NO_DATA` 時 `--out` 也寫檔（`status`、`reason`、`hints`；exit 仍是 2，之前不寫檔）；`--project-dir` 指到啟動資料夾底下時印 `HINT` 指出上層的啟動資料夾；`--effort-check <工單>` 印 `EFFORT_ACTUAL` 行，session effort 和工單不同印 shadow WARN | `--out` 才寫 |
| `dsh_audit.py` | 從 session 事件重建有雜湊鏈的動作紀錄，給 `report_vs_audit.py`／gate 審查用；`verify` 檢查鏈與錨點，`cite` 印報告要引的區段。2.2.1-ds.1 起第 1 行是 `kind=rebuild`（記來源 session 檔名、sha256、大小），工具呼叫從 seq 2 起 | `build` 寫一份 JSONL，不覆蓋舊的 |
| `dsh_doctor.py` | 12 項環境檢查：Python、Node、DSH home、session log、投影快取、profile 模型/effort、沙箱/核准、git、工具/文件/範本齊不齊 | 不寫 |
| `dsh_setup_check.py` | 建置完成的檢查：BOOTSTRAP 產出的 DIRECTOR 資料夾（必要檔案、PENDING_METHOD、PO_PENDING、RESUME_STATE 標頭、director_work.json）；2.2.1-ds.1 起另有 shadow 檢查（ID 重複、RESUME 標頭有值與 UPDATED 日期、director_work.json 欄位型別與 regex），印 `~ shadow:`，`--strict` 才算失敗；2.2.2-ds.3 加 RESUME_STATE 大小（RESUME_SIZE）和 `resume`／`base_ref`／`release` 區塊的型別檢查 | 不寫 |
| `dsh_guard.py` | 動手前的自律檢查：force push、push、刪除、送出/發布、付款、改設定、秘密、永遠禁止的 git/程序模式、PAUSE 旗標；預設只提醒 | 不寫 |
| `safety_gate.py` | 安全閘門（ds.2 `sdd_gate.py` 改名，2.2.5-ds.5 拿掉 OpenSpec，docs/13）：`--lock-tests` 印工單的 `TESTS_LOCKED:`、`--plan-hash` 印 `PLAN_APPROVED` 行；`gate_check.py` 用它查鎖定測試、PLAN.md、SPEC_REVIEW、輪數、安全開關不得自行關閉；也讀 `order_limits`／`protected_tests` 給 `scope_check.py`。舊的 `sdd` 區塊照讀：安全開關印「請搬到 safety」，OpenSpec 的鍵印「此鍵被忽略」 | 不寫 |
| `bootstrap_repo.py` | 2.2.3-ds.3 BOOTSTRAP 10.5 的機械步驟：把 `.memsearch/` 加進 `<REPO>/.git/info/exclude`。做過的跳過，`--check` 只報告。2.2.5-ds.5：`--config` 只讀，舊設定的 `sdd` 區塊只印 WARN，不找、不裝、不寫任何 CLI（L-061） | 只寫 exclude |
| `release.py` | 2.2.2-ds.3 發版一次到位：fetch → 比對 origin/main（落後／分岔／領先；分岔加 `--merge` 開 `release/<版本>` 合併，有衝突就停並列檔名）→ 工作樹有沒 commit 的 tracked 檔就停 → VERSION 與 CHANGELOG（都從 HEAD 讀）最上段一致、tag 排序高於遠端所有 tag（2.2.3-ds.3 起比「(上游版本, ds 序號)」整組，ds 序號不單獨比） → selftest → 公開掃描（金鑰、私人 email、使用者路徑、DIRECTOR/、_work/、session 檔）→ push → tag → `gh release create` → repo 描述的版本號（2.4.0-ds.6，`gh repo edit --description`），每步用 ls-remote／`gh release view`／`gh repo view` 驗。預設 dry run，`--execute` 才動遠端 | 只有 `--execute` 動遠端；`--merge --execute` 開本機分支 |
| `verify_dsh_run.py` | 2.2.2-ds.3 DSH 試跑驗證器（由 ds.2 的 WO-101 `verify_run.py` 通用化）：R01–R21 看 repo（候選 commit、各階段改了哪些檔、鎖定測試雜湊、總監重跑測試與隱藏 oracle、gate_check、evidence 重跑、DIRECTOR_LOG），D01–D14 看 DSH session 紀錄（模型、寫入範圍、禁止動作、偷看隱藏測試、閘門、測試先寫、report_vs_audit）。工單專屬的檔名、代理名、oracle 寫在設定檔（`templates/VERIFY_DSH_RUN.json`）；單元測試 `test_verify_dsh_run.py` | 只寫 `--out` 資料夾 |
| `selftest_ds.py` | 離線冒煙測試整組工具（help、usage、audit+report、setup fixture、status 產生、doctor、guard、gate hash、evidence、報告比對、worktree、--final 用量檢查） | 只寫暫存資料夾 |

## 上游保留（跨平台，已適配 DSH）

- `gate_check.py`：檢查 RESUME_STATE／工單／TASK REPORT／裁決的欄位與用詞；`--match` 逐條對報告與工單 AC、`--evidence-dir` 核證據、`--hash` 印派工雜湊、`--verdict` 驗裁決。ds.2 起 Standard／Strict 工單另查安全閘門（`safety_gate.py`；`--repo <專案>`、`--config director_work.json`）。2.2.5-ds.5：拿掉 OpenSpec 檢查；`--final <DIRECTOR>` 找不到 `usage.json` 印 `~ WARN USAGE`；`--report-skeleton` 的 `WORKTREE:` 行由 `git worktree list` 產生。2.2.2-ds.3：`--order` 先 `git fetch` 再比 BASE_REF 與遠端分支，落後或不存在印 `~ WARN BASE_REF`，`--strict-base` 判不過，fetch 失敗會明說沒比對；`base_ref` 開關型別錯會印 note 並用預設（同上游 2.2.2）。`--resume` 檔案超過 `resume.max_bytes`／`resume.max_line_bytes`（預設 20480／4096）印 `~ shadow: RESUME_SIZE`，`--strict` 判不過。`--report-skeleton 工單 [--repo] [--out]` 印出照工單填好欄位、雜湊和每條 AC 一列的 TASK REPORT 骨架，以及錄證據、scope_check、`--match` 的完整指令（DSH worker 不用讀原始碼學格式；docs/13「省 token」）。2.2.4-ds.4：`--order` 的 CHECKS 反斜線路徑指出第幾行並建議改正斜線；`--match` 的 Standard／Strict 沒有 SPEC_REVIEW 一律判不過（沒給 `--dispatch-log` 就找 DIRECTOR_LOG.md 和 `reviews/`），報告 `PROTECTED_CHANGED` 對 diff，`--dispatch-log` 的 `EFFORT_ACTUAL` 和工單 effort 不同印 shadow WARN；骨架對有 WORK_DIR 的工單印 TEMP 設定行。2.2.4-ds.4（上游 2.2.4）：`--after-verdict <裁決.md>... --repo <專案> [--orders <工單資料夾>] [--strict]` 解出每份裁決的 `CANDIDATE_HEAD:`，取其他候選都在它之前的那份當最後一份；從它到 HEAD 的 commit 改到該工單 SCOPE 外、又不是文件（`DIRECTOR/` 底下、`.md`／`.rst`／`.txt`）的檔，印 `~ WARN LATE_COMMIT <sha> <標題>: <檔案>`（shadow，exit 不變），`--strict` 判 FAIL；工單依序在 `--orders`、裁決所在資料夾、`../orders` 找，找不到就把每個非文件的檔都算進去；候選解不出或 HEAD 不含候選印 `NOT_CHECKED`，不當作通過。只讀 git。
- `scope_check.py`：比對實際改動與工單 SCOPE／FORBIDDEN。ds.2：Standard／Strict 工單另查大小上限（`OVERSIZE`）。2.2.4-ds.4：上限讀頂層 `order_limits`（舊 `sdd.max_*` 照讀並印 shadow WARN「請搬到 order_limits」），測試檔行數另算 `max_test_lines_per_order`；共用 checkout（`--shared` 或工單 WORKTREE 寫「共用」）只算 commit 訊息有工單編號的 commit 和 SCOPE 內未 commit 的檔，別人的檔印 `OTHER`；受保護的測試（TESTS_LOCKED、`protected_tests`）只准新增或在檔尾加，改到原有內容印 `PROTECTED`，並印 `PROTECTED_CHANGED:` 給報告照抄。
- `evidence_record.py`：跑驗收指令，留下 exit code、輸出尾段、產物 SHA-256；`verify --rerun` 可重跑。2.2.3-ds.3（上游 2.2.3，原樣搬）：`CHECKS:` 的程式只寫 `git` 也可以，但只限唯讀子指令（diff、show、log、status、rev-parse、ls-files、cat-file），子指令前的選項、其他子指令、會寫檔或執行程式的選項（`--output`、`--ext-diff`、`--textconv`、`--filters`、`--no-index`，縮寫也算）一律 `NOT_RUN`、exit 2；git 檢查在 `--repo` 頂層跑，關掉 replace 物件、fsmonitor、pager、optional locks、外部 diff 和 textconv，跑完照樣重讀 repo（docs/02「AC 用 git」）。
- `report_vs_audit.py`：拿 RAN 與 TESTS／EVIDENCE／DONE 的指令對動作紀錄（DSH 包殼指令會先剝殼再比；比對不到就 FAIL，不會亂放行）。2.2.1：被截在 500 字的行會照 JSON 字串解回引號與反斜線，長的 Windows 路徑指令也對得上；單字比對至少要 2 個不是 `...`／`<名稱>` 的字；讀到 `kind=rebuild` 的紀錄會印一行 note。2.2.3-ds.3（上游 2.2.3）：換行、`;`、`&&`、`||` 切段，多段主張對得到多行腳本（順序要一樣），`RAN:` 下面用 ``` 包的一段算一個主張；`at=13:17（備註）` 只取時間、主張裡的全形（備註）不比；`AC-1/AC-2`、`AC-1/2`、`AC-1..AC-3` 每個編號都要有一筆，缺的會點名；有省略的主張（`...`、`427fcef...`、「同上」）可跳過紀錄裡的選項、對到開頭相同的詞，`wo-003` 對到以它開頭再接 `-`／`_`／`.` 的檔名；被截的紀錄行，3 個詞一路對到行尾也算；比到幾筆時顯示最接近 `at=` 的那筆；exit 對不上但那筆後面還跑了別的指令，印「not checkable」算 OK。兩種 shadow WARN（exit code 不變）：`RAN:` 有一行沒有 `` `指令` ``；報告寫 `SCOPE_CHECK: PASS`，但做事的 agent 最後一次 commit 之後沒有再成功跑過 `scope_check.py`。WO-DS-004 的 DSH 報告：舊版 FAIL 6 條、新版 PASS 11/11。2.2.4-ds.4（上游 2.2.4，原樣搬）：變數會展開（`$X`、`${X}`、`$env:X`、`%X%`、PowerShell 的 `a + b`、here-string；同一 agent 前面設的延用到後面的呼叫）；`git -C DIR x` 當成 `cd DIR` 再 `git x`；字中的 `...`／`…` 代表任意字；短 hex 對長 sha 的開頭；主張的絕對路徑對紀錄的相對路徑；`at=HH:MM:SS` 和 `at=HH:MM–HH:MM` 區間；`AC-1 .. AC-6`；選項順序不同也對得上（完整主張要列齊每個選項）；全形 `；` 斷句、CJK 字之間的詞當備註；多段主張分在幾次呼叫跑也算（順序要一樣）；``` 從 RAN: 外開的區塊在那裡就結束；主張在任何呼叫都找不到、但可能在另一條主張對到的截斷呼叫被截掉的那段時，印 `UNVERIFIED`（in log cut part）：獨立狀態，不算 OK、也不算 FAIL，最後一行另計 `unverified=n`（放在最後），exit code 不變，審查的人要自己看這幾條；在截斷呼叫留下來的那段就對得到的主張仍是 OK；PowerShell 這類從不回報 error 的工具，exit 對不上印 not checkable。沒人跑過的指令照樣 FAIL。WO-DS-006 三組報告：FAIL 64 → 0（其中 18 條 UNVERIFIED）。
- `trace_report.py`：產生需求 → 工單 → AC → 證據 → 裁決的追溯表。
- `round_check.py`：修正輪數檢查（第 4 輪起要根因研究）。
- `status_gen.py`：產生一條工作線的 `status.py`；總監版加待決帳計數、未結案工單、近 1 小時動作紀錄（已改吃 `po_pending`、無 pending_sends／processes）。2.2.4-ds.4（上游 2.2.4，L-059）：一行超過 `width` 時頭尾都留，行內最長路徑（路徑太短就整行）的中段換成 `…`，行尾的狀態字（OK、LOW、計數）不再被切掉；已產生的 `status.py` 要用 `--force` 重新產生。
- `metrics_report.py`：從 DIRECTOR 檔案數成效數字。
- `memory_size_check.py`：指示鏈大小（預設找最近的 `AGENTS.md`，`--max-bytes 65536`）。2.2.2-ds.3（上游 2.2.2）：`--kind resume` 量 RESUME_STATE（整份 20480、單行 4096 bytes，`--config` 讀 `resume.*`），可給多個 `--file`、`--glob "<根>/**/RESUME_STATE*.md"` 或 `--workstreams ACTIVE_WORKSTREAMS.md`；一檔一行（OK／OVER、bytes、~token、最長行、可搬 bytes），最後 `SIZE: PASS|OVER|MISSING files=n over=n`，超過或找不到 exit 1，只讀。
- `resume_archive.py`：2.2.2-ds.3（上游 2.2.2，原樣搬）把 RESUME_STATE 的舊段落原文搬到同資料夾 `RESUME_HISTORY_<YYYYMMDD>.md`，原處留索引。預設 dry-run；`--execute` 先寫 `.bak`，搬完驗證 (a) 歷史檔逐字含搬走的內容 (b) 留下的部分 sha256 不變、表頭仍四行 (c) 搬走＋留下＝原檔，任何一項不過就還原並 exit 1。近期只用筆數算（`resume.keep_recent`，預設 10，沒有 keep_days）；表頭、現況、保護標題、沒日期的段落不動（docs/06b「RESUME_STATE 瘦身」）。
- `secret_mask.py`：把私鑰、token、API key、JWT、`password=` 這類值遮成 `[MASKED:種類]`。
- `pause_ctl.py`：暫停開關（寫／移除 `<DIRECTOR>/PAUSE` 並記 LOG 一行）。
- `audit_log.py`：動作紀錄格式的來源；DSH 只用它的 `verify`／`head`／`cite`／`recover`（`append` 是 Claude hook 用的，DSH 不呼叫）。
- `vocabulary.json`、`guard_rules.json`：固定用詞與 `dsh_guard.py` 的規則檔。

### 上游 DW 2.2.5 移植（2.2.5-ds.5，WO-DS-009 B7）

- `ran_line.py`（新，上游原樣搬）：`--to 報告 -- 指令` 代跑並寫一行 RAN（exit code 照傳）；`--exit N --cmd "指令"` 剛跑完補記；`--stamp [--to 檔 --text ...]` 印或加一行 `YYYY-MM-DD HH:MM`。時間取時鐘，不手打。設了 `WORK_DIR` 時暫存檔放 `WORK_DIR/tmp`。
- `gate_check.py`：`--sequence 工單… --dispatch-log DIRECTOR_LOG.md --repo <checkout>`（PLAN_APPROVED 早於 worker 第一個 commit、每張工單有自己的 SPEC_REVIEW、審查與裁決來自別的 session）；`--after-verdict` 預設 FAIL（裁決後改到程式碼，SCOPE 內也算；只改文件放行；`--warn` 回到 WARN）；`--final <DIRECTOR>`：`evidence/E2E/` 沒有非空檔 FAIL，缺 `ENTRY_POINT:`、DD 沒「驗收案例」印 WARN，再加 DS 的 usage.json 行（`~ WARN USAGE`）；git 的 `Filename too long` 印一行寫明路徑和超過多少；BASE_REF 括號裡的字當註解。
- `scope_check.py`：印 `WORKTREE:` 行（`git worktree list`；`dsh_session.py --worktree-status`、`--report-skeleton` 用同一個函式）；BASE_REF 括號當註解；長路徑一行訊息；任何錯誤 `SCOPE_CHECK: NOT_RUN`，不印 Traceback。`--shared` 是 ds.4 B2，上游 2.2.5 搬回去的就是這一份。
- `report_vs_audit.py`：H1 誤報修正（全形 `～` 區間、只設 TEMP／TMP／TMPDIR／PYTHONIOENCODING／PYTHONUTF8 的句子不比、相對路徑照該次呼叫的資料夾解開、`/d/x` 等於 `d:/x`、shell 函式展開、可少寫無害選項）；每條 FAIL 標類別（沒跑／時間不符／結束碼不符／格式），最後一行多 `time_mismatch=n not_run=n`；`--tolerance-min` 預設 10；`--lead 檔` 查 lead 自己寫的裁決、DIRECTOR_LOG 時間；最上層攔例外，exit 2 一行。
- `dsh_audit.py`（對應上游 `transcript_audit.py` 2.2.5）：`build` 預設整條 input 都記，不再截 500 字；`--input-limit N` 截過的行標 `input_cut`。`audit_log.summary(input, limit)` 跟著上游。
- `evidence_record.py`、`release.py`：設了 `WORK_DIR` 時，`tempfile` 和子行程的 TMPDIR／TEMP／TMP 指到 `WORK_DIR/tmp`（上游原樣搬）。
- 範本：`templates/weird_inputs.py`（怪檔案產生器）、`templates/HANDOFF.md`（worker 到輪數上限的交接）。
- 沒搬：`browser_check.py`（DS 本來就沒有）、上游 `selftest.py`（案例改寫進 `selftest_ds.py`）。

### 上游 DW 2.3.0 移植（2.3.0-ds.5，WO-DS-010）

- 新工具，上游原樣搬：`completion.py`（完成度表）、`sim_check.py`（patch 和模擬讀同一份設定）、`waiver.py`（豁免要有解除事件）、`line_brief.py`（一條工作線的摘要）、`pre_tr.py`（送 TR 前依缺陷類別跑 CPU 檢查）、`pack_check.py`（審查包）、`hash_check.py`（雜湊比對、build 新不新）、`flag_check.py`（開關有沒有真的被讀到）；2.6.0-ds.6 再加 `ruler_check.py`、`run_plan_check.py`（上游原樣搬，見下面）；範本 `templates/CPU_REPRO.md`、`templates/pre_tr.json`、`templates/run_closing.py`。用法見下面「2.3.0 新工具用法」。
- `gate_check.py`：`--feasibility 紀錄…`（開修正組或凍結 gate 數字前的 CPU 可行性搜尋）；`--verdict` 的「自己查證的證據」：PASS 類裁決要有一行 `ran_line.py` 格式的 RAN，嚴重度看設定 `verdict_self_check`（2.3.x 預設 `warn`，`fail` 才判不過）。設定從 `--config` 讀，沒給就找裁決所在資料夾或上一層的 `director_work.json`。
- `dsh_doctor.py --licenses 清單 [--license-days 3] [--licenses-only]`（上游 `doctor.py --licenses`，DS 沒有 `doctor.py`）：快到期的授權和持有的工具。
- `dsh_setup_check.py`、`bootstrap_repo.py --config`：認得 `verdict_self_check`（`warn`／`fail`，其他值 setup_check 判問題、bootstrap 印 WARN）。
- `ran_line.py` 依作業系統引號（POSIX 用單引號）；`round_check.py` 研究檔沒有「測試條件 vs 參考條件」表印 `~ WARN NO_CONDITIONS_TABLE`；`status_gen.py` 的設定可以有 `"lines"`（給 `line_brief.py`）。
- 非 UTF-8 主控台（cp1252／cp950）的 `--help`：輸出改 UTF-8 移到解析參數之前。上游修了十支；DS 另外修了自己的 `bootstrap_repo`、`dsh_session`、`release`、`safety_gate`、`status_gen`、`dsh_doctor`。`selftest_ds.py` 用 cp1252 包住 stdout／stderr 跑每支工具（含 `dsh_*`）的 `--help`。
- DS 專屬：`dsh_session.py --cwd-check <工作區>`（lead 開工第一步；BOOTSTRAP 第 0 步、docs/11）：目前資料夾和工作區用 realpath 比（Windows 不分大小寫），不同或在子資料夾就印 `BLOCKED: cwd <實際> != <預期>`、exit 1，什麼都不寫。

### 工作品質偵測（2.3.0-ds.6，WO-DS-011）

DSH 沒有事前攔截（沒有 PreToolUse hook），下面兩項都是事後從紀錄或檔案查，在檢查點、閘門、狀態報告裡讓人看見。概念來源見 CHANGELOG 2.3.0-ds.6 的 Credits；程式是自己用標準函式庫寫的。

- `dsh_audit.py loops`：讀和 `build` 一樣的 DSH session（同樣的 `--session`／`--project-dir`／`--since`／`--until`），找出打轉的呼叫。2.4.0-ds.6 起類別、門檻、提醒次數和 `allow` 照上游 2.4.0 的 `loop_guard`（見下面「上游 DW 2.4.0 移植」）；**不印參數、輸出或訊息內容**。
- `status_gen.py` 的 `"loops": {"path": "loops.json"}`：讀 `dsh_audit.py loops --out` 寫的 JSON，有發現時多印一行 `LOOPS loops.json (modified …): findings=n repeat=… …`，沒有發現不印；檔案不在印 MISSING。發現不改 exit code。選 status_gen 不選 line_brief：loops 是整個專案所有 session 的事，和 status_gen 的 AUDIT 段（動作紀錄）同一類；line_brief 只看一條工作線的看板、git、結果和 log。
- `memory_size_check.py --chain FILE... [--max-bytes N]`：一條指示鏈的檔一起量：每檔一行（bytes；有 CRLF 另列 LF bytes；~token 照舊用 bytes/2），加總超過 `--max-bytes` 印 FAIL（exit 1）；各檔之間重複 3 行以上的段落印 `DUP a:起-迄 = b:起-迄 (n lines)`（空行略過；只有標點的行不當段落開頭），只列不判 FAIL。最後一行 `CHAIN: PASS|FAIL|MISSING files= bytes= (limit …) lf_bytes= ~tokens= dups=`。單檔和 `--kind resume` 的輸出不變。

### 上游 DW 2.4.0 移植（2.4.0-ds.6，WO-DS-012）

上游 2.4.0 的三個新工具都是 Claude Code hook（PreToolUse、SessionStart、PostToolUse）；DSH 一個 hook 都沒有，所以全部改成事後檢查，或由 agent 照規則自己跑。

- `dsh_audit.py loops`（版本 2，`LOOPS_VERSION = 2`）。所有類別都在同一個 session 的 W 次呼叫內算（`--window`，預設 20）：
  - `repeat`：同一個呼叫（工具＋遮罩後參數的雜湊）出現 N 次以上（`--repeat`，預設 3）。
  - `retry_same_error`：同一個呼叫連續失敗、錯誤一樣 N 次（`--retry-errors`，預設 2），中間 agent 沒寫任何文字（思考不算；這個條件是 dshdw 自己的）。
  - `ping_pong`：A、B 兩個呼叫輪流 N 次以上（`--ping-pong`，預設 6；2.3.0-ds.6 的 `--rounds R` 等於 `--ping-pong 2R`，仍可用），結果都沒變。
  - `poll_no_progress`：讀取／查詢類工具（read、grep、glob、list_agents、job_list、job_output、team_task_list、team_task_get、acp_status、web_fetch、web_search、read_image、get_goal、search_context、list_subagent_models）連續 N 次結果一樣（`--poll`，預設 3）。
  - `bad_args`：同一個工具 N 次以上因參數被拒（`--bad-args`，預設 2；DSH 紀錄的 `INVALID_ARGS`／`ToolArgsError`，或頂層參數字串不是 JSON）。`BAD_ARGS` 行照舊列全部被拒的次數、占全部呼叫的比例、前 5 名工具。
  - `child_error_unhandled`：session 的最後一個呼叫是失敗的子代理呼叫（`child_tools`，預設 `subagent`、`wait_agent`），之後沒有任何處理。輸入裡完全沒有子代理呼叫的結果時印 `~ NOT_VERIFIED child_error_unhandled`，不算 0。
  - 每一筆：`LOOP <類別> tool=T args=<雜湊> count=N calls=A..B reminders=K session= agent= at=<時間>`，後面依類別多 `window= total=`、`result= no_text_between`、`result=`、`reason=`、`result= last_call`；fork 出來的 session 同一筆只算一次（行尾 `copies=N`）。`count` 是那一段最多到幾次；`reminders` 是上游的即時 hook 會提醒幾次（門檻一次，之後 2 倍、4 倍、8 倍各一次）。
  - 合法的重複（例如每分鐘看一次 build）寫進 `--config FILE` 的 `allow`：`{"tool": "PowerShell", "input": "<對遮罩後參數的 regex>", "max": 20, "why": "..."}`，`max` 以內不算。設定檔格式和上游 `loop_guard` 一樣（`schema_version`、`window`、`repeat`、`retry_errors`、`poll`、`ping_pong`、`bad_args`、`child_tools`、`allow`，都可省）；值不合法印 NOT_RUN（exit 2）。順序：預設 → `--config` → 命令列。
  - 最後印一行和上游 `usage_mix` 同格式的 `LOOPS repeat=n retry_same_error=n ping_pong=n poll_no_progress=n bad_args=n child_error_unhandled=n|NOT_VERIFIED calls=n sessions=n`，再印 `DSH_LOOPS`。
  - `--json` 印 JSON；`--out FILE` 另外寫一份 JSON 給 `status_gen.py`。`--events FILE...` 讀純 JSONL 事件檔（合成 fixture，`tools/fixtures/loops/`）。exit 0 沒發現、1 有發現、2 讀不到。
  - `--since`／`--until`（2.5.0-ds.6，上游 2.5.0 F1）：每個呼叫照**自己的時間**算，只算 [since, until) 裡的呼叫（`--until` 那天整天都算）。2.4.0-ds.6 照 session 開始時間挑整個 session：前一天開、今天還在跑的 session 整個被漏掉，跑過 `--until` 的整個算進來。現在 `--until` 之後才開的 session 直接跳過；沒有時間的呼叫在有範圍時不算。`--events` 檔一樣照呼叫時間過濾。`build`、`inject` 和 `dsh_usage` 的主表仍照 session 開始時間。
- `dsh_usage.py --loops [--loops-config FILE]`：用量報表在 TOTAL 後多一行上面那行 `LOOPS`（同一批 session）。預設不跑：全部 session 約多 1 分 45 秒，而且要 Node；`--no-fallback` 時印 `LOOPS NOT_RUN`。
- `status_gen.py` 的 LOOPS 行只列不是 0 的類別（加 `child_error_unhandled=NOT_VERIFIED`），避免整行被截斷。
- `resume_inject.py --file RESUME_STATE.md [--max-bytes 2048] [--section NAME ...]`：印 RESUME_STATE 的前四行和未結段（`OPEN ITEMS`、`OPEN_DECISIONS`、`IN_FLIGHT`、`未結`、`未完成`、`待辦` 這類標題或 `KEY:` 行），超過上限從整行處截斷並註明。沒有 SessionStart，所以由 agent 在恢復或 DSH 自動壓縮後自己先跑一次（AGENTS.md 段落一行、docs/06b 第 0 步）。檔案不在印一行說明（exit 0）。
- `inject_scan.py scan FILE... [--json]`、`dsh_audit.py inject [篩選] [--events FILE...] [--tool T] [--json]`：工具輸出裡有像在下命令的文字（`override`、`role_rewrite`、`hidden`、`encoded`、`exfiltration`）時列出類別、行號（`inject` 另有工具、第幾個呼叫、session、agent、時間）；**不印那段文字**。只警告：不擋、不改。`FOUND` exit 1、`NONE` exit 0、讀不到 exit 2。會誤報（講提示注入的文件、測試樣本），也會漏（換句話說、拆行、其他編碼）。上游的 hook 模式不搬。
- `completion.py`、`secret_mask.py`：上游 2.4.0 原樣。`completion.py` 可加 `depends_on / 依賴 / 前置` 欄，多印 `READY_NOW:`（還沒到 100、依賴全部算 100 的項目）和每個卡住的項目一行 `BLOCKED`；依賴的 ID 不在表裡或繞成一圈印 WARN。沒有這一欄的舊表輸出不變。
- `templates/.pre-commit-config.yaml`、`templates/.gitleaks.toml`：commit 前掃秘密的範例，開頭寫 `SAMPLE ONLY`；dshdw 本身不裝。

### 上游 DW 2.5.0 移植（2.5.0-ds.6，WO-DS-013）

都是自己執行的事後檢查：不裝 hook、不改設定，預設只提醒（DSH 本來就沒有 PreToolUse hook）。

- `dsh_audit.py loops --since／--until`（F1）：每個呼叫照自己的時間算（見上面 loops 那段）。
- selftest 的 `either_quoting(argv)`（F3）：比對指令文字的測試，POSIX 單引號和 Windows 雙引號兩種都收（`quoting_either_250`）。
- `dispatch_check.py --log DIRECTOR_LOG.md [--table <表.json>] [--strict]`（N1）：每一筆 `DISPATCH <WO-ID> rev=<n> sha=<雜湊>` 行在 `|` 欄寫 `class=<難度類別> effort=<off|low|high|max> model=<模型>`，gate_check 照樣讀得到。預設表在 `docs/05`「派工難度表」：`mechanical` off/low、`routine` low/high、`dev`／`ui` high、`root_cause`／`fix_after_fail`／`realism`／`core_engine` high/max、`repeated_failure` max。等級只有 DSH 能設的四個；上游的 `medium`、`xhigh` 在這裡印「unknown effort」。沒寫、類別或等級不認得、等級不在表裡：印 `~ WARN EFFORT <WO-ID> line <n>: …`；最後一行 `DISPATCH_CHECK: OK|WARN records=n warnings=n`。只提醒，exit 0；`--strict` 有 WARN 就 exit 1；檔案讀不到或表格式錯 exit 2。
- `dispatch_check.py --dup "<標題和範圍>" [--resume "<glob>"]... [--repo <repo>]... [--since "14 days ago"] [--threshold 0.5]`（N4）：派工前把新任務的字和各線 RESUME_STATE 的 `NEXT_STEP:`、各 repo 最近的 commit 標題比 token Jaccard（共同字 ÷ 全部字；中日文用相鄰兩字）。達門檻的印 `~ WARN DUP <分數> <來源>: <內容>`，最後一行 `DUP_CHECK: OK|WARN compared=n matches=n threshold=x`。可能誤報，看過再決定。只讀 git（`git log`）。
- `delete_guard.py [路徑 ...] [--list <清單>] [--repo <repo>]... [--refs "<glob>"]... [--no-basename]`（N3，上游原樣）：刪除前查每個候選還有沒有被提到：完整路徑（`/` 和 `\` 都試）和檔名（`--no-basename` 只找完整路徑），不分大小寫；`--repo` 找那個 repo 的追蹤檔（`git grep -F -i -I`），`--refs` 找其他宣告輸入的檔（RESUME_STATE、PLAN、工單，glob 可用 `**`）。檔案自己提到自己不算。印 `REFERENCED <候選> (n places)` 加最多 5 個 `檔案:行號`（不印那一行的內容），或 `CLEAN <候選>`；最後一行 `DELETE_GUARD: REFERENCED|CLEAN candidates=n referenced=n`。exit 1 有被引用、0 全部乾淨、2 輸入錯誤。只讀，從不刪、不搬；流程見 `docs/06b`「刪檔之前」的刪除五步。
- `dsh_audit.py reads [篩選] [--events FILE...] [--top 20] [--json]`（N5，改寫自上游 `usage_mix.py --reads`）：讀 DSH 的 `session.v4.jsonl.zstd` 事件，列出被讀最多次的路徑、次數和那些讀取帶回來的 bytes（進了上下文的量）。算讀檔的是 DSH 的 `read` 工具（`path`），以及 pwsh／bash 的 `cat`、`head`、`tail`、`sed -n`、`Get-Content` 這類命令；fork 出來的 session 同一個呼叫只算一次；`--since`／`--until` 照每個呼叫自己的時間。DSH 的 token 用量記在每一步模型回應上，不是每個工具呼叫，所以上游的「每個路徑的加權成本」在這裡是 `NOT_VERIFIED`，只給次數和 bytes。**會印檔案路徑**：輸出只在本機看，不貼進公開的地方。exit 0，讀不到 exit 2。
- `templates/GATE_FEASIBILITY.md`（N6）：核准閘門前，每個條件對到一個現有工具、在現況 commit 試跑一次、原則上達得到；放寬量法要另一個人（或另開的子代理 session）拿已知缺陷樣本確認仍抓得到（`docs/07` 第 7 節）。
- `templates/SETTINGS_MANIFEST.md`（N7）：擷取、量測、審查前先寫打算用的設定，跑完從輸出讀實際設定逐項比；不同就是 INVALID（重跑），不是候選的 FAIL（`docs/07` 第 7 節）。
- `docs/06b`「程序衛生」（N8）：停背景工作只停這個 DSH session 自己啟動的程序樹、批次前驗名稱、commit 前用 `&&` 和 `git diff --cached --check`、JSON 用 parser 讀、時間取時鐘、CRLF 檔不用 `sed -i`、安全重寫 RESUME 標頭、量測獨佔機器；`templates/.pre-commit-config.yaml` 多一個 `dshdw-conflict-markers`（pygrep，pre-commit 內建，不下載）。
- `docs/10` 第 82～126 條（N9）：上游 2.5.0 從總監收件匣併入的教訓（標「收件匣 L-0xx」，和前面各條的 L 編號是兩套），每條一句規則。docs/10 不是每輪必讀，不進 agent instructions，不佔 65536 bytes。
- `round_check.py`（N2）：第 2 組（之後每組）沒過，研究檔那一節要寫獨立診斷 `DIAGNOSIS_BY:`（另一個子代理 session、別的模型或人）和 `DIAGNOSIS_RESULT:`；有寫 `IMPLEMENTER:` 時兩者要不同。沒寫或相同印 `~ WARN NO_INDEPENDENT_DIAGNOSIS`，不改 exit。

## 已移除（Claude 專屬）

`hook_guard.py`（規則留在 `guard_rules.json`）、`setup_project_settings.py`（改 `.claude/settings.local.json`）、
`context_probe.py`、`usage_report.py`、`usage_mix.py`、`doctor.py`、`setup_check.py`、
`choice_reconcile.py`、`browser_check.py`、`poll_hint.py`、`selftest.py`、`container/`。
理由：DSH 沒有 hooks、Artifact 私人待決頁、Claude 方案額度或容器 worker；對應能力改用 `ask_user_question`＋`PO_PENDING.md`、`dsh_usage.py`、子代理共享 checkout。

## 常用指令

```text
# 總監：重建 worker 的動作紀錄、核對報告
python -I -X utf8 tools/dsh_audit.py build --session w1 --out DIRECTOR/research/audit-2026-11-12.jsonl
python -I -X utf8 tools/report_vs_audit.py --report _work/demo-worker/TASK_REPORT.md --log DIRECTOR/research/audit-2026-11-12.jsonl --utc-offset +08:00

# 總監：環境與建置檢查
python -I -X utf8 tools/dsh_doctor.py
python -I -X utf8 tools/dsh_setup_check.py DIRECTOR

# 總監：用量（--project-dir 比對 session 啟動資料夾；單線用 --session <agent>）
python -I -X utf8 tools/dsh_usage.py --project-dir <WS>
python -I -X utf8 tools/dsh_usage.py --session w1 --json

# worker／總監：動手前自律檢查
python -I -X utf8 tools/dsh_guard.py --command "git push origin main" --profile worker

# 總監：安全閘門（docs/13）
python -I -X utf8 tools/safety_gate.py --lock-tests tests/test_x.py --repo <專案>
python -I -X utf8 tools/safety_gate.py --plan-hash <WORK_DIR>/WO-002/PLAN.md --order DIRECTOR/orders/WO-002.md

# 總監：工單閘門
python -I -X utf8 tools/gate_check.py --order DIRECTOR/orders/WO-002.md --repo <專案>
python -I -X utf8 tools/gate_check.py --after-verdict DIRECTOR/gates/WO-002-GATE.md --repo <專案>   # 2.2.4：裁決之後的未審 commit

# 總監：每個 worker 一個 worktree（2.2.5-ds.5）
python -I -X utf8 tools/dsh_session.py --worker-worktree <專案> --order WO-002 --branch wo-002 --base <BASE_REF 的 commit>
python -I -X utf8 tools/dsh_session.py --worktree-status <checkout>

# 收尾（2.2.5-ds.5）：最後一步寫用量，再跑 --final
python -I -X utf8 tools/dsh_usage.py --project-dir <WS> --out DIRECTOR/usage.json
python -I -X utf8 tools/gate_check.py --final DIRECTOR

# 總監：打轉偵測（2.3.0-ds.6，2.4.0-ds.6 照上游 loop_guard；事後查，DSH 擋不住）
python -I -X utf8 tools/dsh_audit.py loops --project-dir <WS> --out DIRECTOR/loops.json

# 總監：派工紀錄的難度和 effort、派工前查重複（2.5.0-ds.6；只提醒）
python -I -X utf8 tools/dispatch_check.py --log DIRECTOR/DIRECTOR_LOG.md
python -I -X utf8 tools/dispatch_check.py --dup "<標題和範圍>" --resume "<各線>/**/RESUME_STATE*.md" --repo <repo>

# 總監：最常重讀的檔（2.5.0-ds.6；會印路徑，只在本機看）
python -I -X utf8 tools/dsh_audit.py reads --project-dir <WS> --since <日期>

# 清理員：刪檔之前（2.5.0-ds.6；有被引用 exit 1，不刪）
python -I -X utf8 tools/delete_guard.py --list <清單> --repo <repo> --refs "<各線>/**/RESUME_STATE*.md"

# 總監：工具輸出裡的提示注入（2.4.0-ds.6；只警告）
python -I -X utf8 tools/dsh_audit.py inject --project-dir <WS>

# 任何 agent：恢復或 DSH 自動壓縮後第一步（2.4.0-ds.6）
python -I -X utf8 tools/resume_inject.py --file <自己的 RESUME_STATE.md>

# 總監：整條指示鏈的大小與重複段落（2.3.0-ds.6，docs/09）
python -I -X utf8 tools/memory_size_check.py --chain <REPO>/AGENTS.md <REPO>/AGENTS.local.md --max-bytes 65536

# 全組冒煙測試
python -I -X utf8 tools/selftest_ds.py
```

## 2.3.0 新工具用法（上游 DW 2.3.0）

### completion.py（2.3.0，N1）

```text
python -I -X utf8 completion.py <完成度表.md|.json> [--previous 上週.json] [--save 本週.json] [--root DIR] [--strict]
```

- 表要有 ID 欄和分數欄（`ID / 編號`、`score / 分數`），可加 `item / 項目`、`evidence / 證據`、`critical / 關鍵`、`weight / 權重`、`visibility / 可見度`、`phase / 階段`、`decision / 決定`。分數只能是 0 / 25 / 50 / 75 / 100。
- 100 要有證據路徑（存在、非空），沒有就算 75 並印 WARN：分數背後要有實際行為的紀錄。`visibility` 高的項目寫延後（after alpha、延後、later）要有 `decision`，否則 WARN。
- `--previous` 多印 `prev` 和 `delta` 欄；`--save` 寫快照（schema `completion-v1`）。不是每輪必讀：被問進度或每週跑。

### gate_check.py --feasibility（2.3.0，N2）

```text
python -I -X utf8 gate_check.py --feasibility <可行性紀錄.md> [...]
```

- 開一組修正、或凍結一個 gate 的數字之前，先用 CPU 搜尋有沒有可行解。紀錄寫 `FEASIBILITY:`（給哪一組）、`FEASIBLE_COUNT:`（找到幾個解；0 就不開這組）、`SCRIPT:`、`RESULT:`（JSON 有 `feasible_count` 時要相符）；gate 的 `THRESHOLDS:` 每行寫來源（`source=video|mocap|spec|...`）。

### 裁決的「自己查證的證據」（2.3.0）

- `gate_check.py --verdict`：判定是 PASS / PASS_WITH_WARNINGS / CONDITIONAL_PASS，就要至少一行 `- `<指令>` exit=<n> at=<HH:MM>`（`ran_line.py` 印的格式）；只有範例佔位（`<…>`）不算。FAIL、HOLD 這類不需要。
- 嚴重度：專案設定的 `"verdict_self_check"`。`"warn"`（2.3.x 預設）：缺這一行印 `~ WARN SELF_CHECK`，exit code 不變；`"fail"`：裁決 FAIL。設定從 `--config director_work.json` 讀，沒給就找裁決所在資料夾或上一層的 `director_work.json`；值不是 warn / fail 會印一行說明並用 warn。範例見 `director_work.example.json`。

### sim_check.py（2.3.0，N3）

```text
python -I -X utf8 sim_check.py --patch-config patch.json --sim-config sim.json --measured last.json --sim-output out.json [--tol 0.05]
```

- patch 和模擬讀同一個具名設定最好（同一個檔直接通過）；不同檔就逐項比（巢狀用 `a.b` 名稱）。`--measured` 的每個數字要在模擬輸出的容差內；沒給 `--measured` 是 FAIL，除非 `--first-run`。不符就「先修模擬」，TR 等它。

### waiver.py（2.3.0，N4）

```text
python -I -X utf8 waiver.py add     --file WAIVERS.json --lane <線> --until "<解除它的事件>" [--watch <檔>] [--reason "<為什麼>"]
python -I -X utf8 waiver.py snooze  --file WAIVERS.json --lane <線> --until "<事件>" --minutes 60
python -I -X utf8 waiver.py lift    --file WAIVERS.json --lane <線>
python -I -X utf8 waiver.py block   --file WAIVERS.json --branch <分支> [--note "<卡在哪>"]
python -I -X utf8 waiver.py unblock --file WAIVERS.json --branch <分支>
python -I -X utf8 waiver.py check   --file WAIVERS.json [--block-hours 8] [--wake-only]
```

- 豁免存在 JSON 檔（schema `waivers-v1`，原子寫入），每個程序重新讀，重開不會忘。`--until` 寫解除它的事件（例如授權續約、另一條線的 build 出來）；`--watch` 記那個事件會改到的檔的 SHA-256：內容沒變印 `WAIVED … (unchanged; do not wake)`，檔變了、不見了或 `snooze` 的時間到了才印 `WAKE <線>`。沒寫 until 印 `~ WARN NO_UNTIL`。
- `block` 記錄卡在整合的分支；超過 `--block-hours` 印 `~ INTEGRATION_BLOCKED`：建議在預設關閉的開關後面先合進去，不要一直等。
- 接法：閒置監看每次跑 `check --wake-only`，有 `WAKE` 行才叫醒那條線。最後一行 `WAIVERS: lanes= wake= blocked_long=`。

### templates/run_closing.py（2.3.0，N5）

```text
python -I -X utf8 run_closing.py run   --board <看板資料夾> --id <TR-ID> -- <指令> [參數 ...]
python -I -X utf8 run_closing.py go    --board <看板資料夾> --id <TR-ID> [--wait 300] [--poll 10] [--result <結果檔>]
python -I -X utf8 run_closing.py check --board <看板資料夾> --id <TR-ID> [--wait 300] [--result <結果檔>]
```

- `run`：第一件事寫 ACK，跑指令，`finally` 寫 DONE（含 exit code），失敗、中斷也寫：DONE 由腳本自己發，不靠人記得。
- `go`：寫 GO 並通知，等 `--wait`（預設 5 分鐘）看 ACK。沒 ACK 先看 DONE 或 `--result` 檔（已經跑完印 `DONE_WITHOUT_ACK`，不再吵），都沒有才補通知一次（`RENOTIFY`），再等不到印 `NO_ACK`、exit 1。
- `check`：印 `NONE / WAIT_ACK / NO_ACK / RUNNING / DONE / DONE_WITHOUT_ACK`；判 NO_ACK 前先看有沒有結果。
- 範本用 `<id>.GO / .ACK / .DONE` 檔當訊號。接到專案只改 `signal()`（怎麼寫看板、送通知）和 `seen()`（怎麼讀）兩個函式。

### dsh_doctor.py --licenses（2.3.0，N6；上游是 doctor.py）

```text
python -I -X utf8 dsh_doctor.py --licenses <授權清單.json|.md> [--license-days 3] [--licenses-only]
```

- 清單：JSON（list 或 `{"licenses": [...]}`，每筆 `tool`、`license`、`expires`）或 Markdown 表（tool / license / expires 欄）。剩不到 `--license-days` 天印 WARN，寫明是哪個工具持有的，例如 `license expiring: trial (held by image-editor) expires …, 2 day(s) left: renew it now`；過期、日期寫錯另列。
- 一般 dsh_doctor 執行把每一筆列成 `licenses` 檢查（快到期、過期、日期寫錯是 WARN）；`--licenses-only` 只查授權、不需要 git，最後一行 `LICENSES: ok= expiring= expired= bad=`，有問題 exit 1。

### line_brief.py（2.3.0，N7）

```text
python -I -X utf8 line_brief.py <線名> --config <status 設定.json>
python -I -X utf8 line_brief.py <線名> [--board 看板] [--match 字串] [--repo DIR] [--results DIR --glob "*.md"] [--log 檔]
```

- 設定放在 status 設定的 `"lines"`（`templates/status_director.json` 有範例；`status_gen` 會忽略它）。印 BOARD（看板裡提到這條線的行）、GIT（`status -sb` 和最後一個 commit）、RESULT（最新結果檔和開頭幾行）、LOG（尾段），最後一行 `LINE_BRIEF: <線> board= git= result= log=`；設定了的部分讀不到 exit 1。要看某條線時跑，不是每輪必讀。

### pre_tr.py（2.3.0，N8）

```text
python -I -X utf8 pre_tr.py --config pre_tr.json (--git-diff <base> | --changed <檔> ... | --classes <類別> ...) [--strict] [--dry-run]
```

- 設定（schema `pre-tr-v1`，範例 `templates/pre_tr.json`）：每個缺陷類別寫 `paths`（glob）、`checks`（argv、可寫 `{python}`、`{repo}`）和 `why`。改到的類別每個檢查都要 exit 0；類別沒有檢查印 `MISSING`，也擋 TR。沒歸類的檔印 `~ UNCLASSIFIED`（`--strict` 時也擋）。最後一行 `PRE_TR: PASS|BLOCK classes= checks= failed= missing= unclassified=`。

### pack_check.py（2.3.0，F1 + F5）

```text
python -I -X utf8 pack_check.py check  <審查包> [--leak-regex REGEX] [--min-part-fraction 0.02] [--margin 0]
python -I -X utf8 pack_check.py readme <審查包> [--out README.md]
```

- 審查包要有渲染腳本寫的 `manifest.json`（schema `review-pack-v1`：fps、sampled_frames、events、min_phase_frames、period_frames、images 每張的 camera / frame / subject_bbox / part / part_bbox、render、reference_render）。bbox 是渲染器投影出來的，不是從圖猜的。
- 檢查：事件影格有抽到、最大間隔不超過最短階段的一半、均勻間隔不是動作週期的倍數；主體每格在畫面內（寬高讀 PNG 檔頭）；近景的部位在圖內且佔至少 2%；檔名不帶版本或結論字樣；manifest 和實際檔案一致；動態模糊、景深、非 100% 解析度、有損格式、和參考不同的設定都 FAIL；README 只能列包裡真的有的檔。

### hash_check.py（2.3.0，F2 + F3 + F4）

```text
python -I -X utf8 hash_check.py compare --expected 基準.json --actual 這次.json [--allow-extra]
python -I -X utf8 hash_check.py stamp   --sources <來源> ... [--build <輸出> ...] --out build_stamp.json
python -I -X utf8 hash_check.py fresh   --stamp build_stamp.json [--sources ...] [--build ...]
python -I -X utf8 hash_check.py show    <組件或執行檔> ...
```

- `compare`：基準有、這次沒有的案例是 `MISSING`，FAIL，不是略過；多出來的預設也 FAIL。`fresh`：重算來源和輸出的內容雜湊和 stamp 比，不看檔案時間（checkout、複製、解壓都會改時間）。`show` 印 `<絕對路徑> sha256= bytes=`，CPU 重現時印實際跑的那支。做法見 `templates/CPU_REPRO.md`。

### flag_check.py（2.3.0，F6）

```text
python -I -X utf8 flag_check.py --flags 開關.json --log 執行.log [--before "<第二個 frame 的 log 樣式>"] [--first-lines 400]
```

- 每個開關在第一個 frame 前要有一行 `flag <NAME> read = <VALUE>`。整數開關讀到 `1.0`、`true` 是 `TYPE`；值不同是 `WRONG`；太晚是 `LATE`；沒有是 `MISSING`。任何一項就 `FLAGS: STOP`：這次執行不判定。程式端寫法（整數解析、值不對就停）見 `templates/CPU_REPRO.md`。

### round_check.py 的條件表（2.3.0）

- 研究檔每一節要有一張「測試條件 vs 參考條件」表（表頭同時寫到 test / 測試 和 reference / 參考 / 基準，至少一列）；沒有印 `~ WARN NO_CONDITIONS_TABLE`（2.3.0 只警告）。

### ruler_check.py（2.6.0-ds.6，上游 2.6.0 N1、N5）

```text
python -I -X utf8 ruler_check.py lines --pattern "cam=(.+?) overlap" --input run.log --real-line "<從 log 複製的一行>" [--expect-min 34]
python -I -X utf8 ruler_check.py files --input captures/ --glob "*.jpg" [--expect-min 1800]
python -I -X utf8 ruler_check.py lines --pattern ",arrive" --input trace.csv --cap-key skippedOverCap --required ",arrive" --required-min 34
```

量尺先證明看得到，才判產品。對到 0 筆、少於 `--expect-min`、`--real-line` 對不上、trace 截斷而需要的列不夠：INVALID（exit 1）。最後一行 `RULER: OK|INVALID matches=n files=n problems=n`。只讀。

### run_plan_check.py（2.6.0-ds.6，上游 2.6.0 N2）

```text
python -I -X utf8 run_plan_check.py --plan PLAN.json --repo <工作樹> --commit <要跑的 commit>
python -I -X utf8 run_plan_check.py --plan PLAN.json --log r1=run1.log r2=run2.log
```

計畫檔（run-plan-v1）每場寫 `args`、每個開關的 `code`（`path:line`）、每個輸出項的 `code`。跑之前查程式位置在 commit 裡；跑完比對 log 的啟動參數。不符的場次 INVALID，不判。最後一行 `RUN_PLAN: OK|STOP runs=n problems=n`。只讀。

### 2.6.0-ds.6 的選項（pre_tr、pack_check、waiver，上游 2.6.0 N3、N4、N6）

- `pre_tr.py` 設定的 `inputs`：`[{"path": "Library/x.json", "sha256": "...", "source": "從哪裡拿"}]`，路徑相對 `--repo`；缺了 `MISSING_INPUT`，雜湊不同 `INPUT_CHANGED`。最後一行結尾 `inputs_bad=n`。
- `pack_check.py`：重複內容 `~ DUPLICATE`，最後一行結尾 `unique=n`；manifest 的 `"required_segments": {"swing_t0_t8": [100, 101, 102]}` 沒有獨特圖就 FAIL。
- `waiver.py snooze --file W.json --lane A B C --until "<事件>" --to 2026-11-27T00:00`：收尾時一次寫好全部線；`lift` 也可給多條線。

## 限制

- `dsh_audit.py` 的 input 經 `secret_mask` 後整條記下（2.2.5-ds.5 起）；加 `--input-limit N` 才截斷，截過的行標 `input_cut`。
- 子代理 session 記在總監 session 的啟動資料夾下，`--project-dir <worker 的 repo>` 抓不到；用 `--session <agent>`。
- `dsh_usage.py` 讀投影快取（寫入可能落後幾百筆事件或幾秒），`--from-jsonl` 可強制讀原始 log。
- `dsh_audit.py` 需要 Node 22+（zstd）；`dsh_doctor.py` 會確認。
- `dsh_guard.py` 只檢查指令文字，不是攔截器；真正擋檔案的是 DSH 沙箱，核准政策是 session 設定。
- `report_vs_audit.py` 的 `UNVERIFIED` 要人看：工具只能說「可能在截斷處」，不能判斷有沒有跑。
- 2.4.0-ds.6 的打轉、恢復、注入檢查都是事後或自己跑的：上游 2.4.0 的即時提醒、重開時自動接回、工具結果旁的警告，在 DSH 都沒有。
- `loops` 的 `child_error_unhandled` 只看「最後一個呼叫是失敗的子代理呼叫」；子代理結束事件（`subagent-settled`）的失敗狀態本機紀錄還沒看過，不猜。

### 已知限制（2.2.4-ds.4，Windows 長路徑，同上游 2.2.4）

- 路徑超過 260 字時 git 會報 `Filename too long`。工具不替你改設定，要自己跑一次 `git config --global core.longpaths true`。`selftest_ds.py` 開頭給整個 process 設 `GIT_CONFIG_COUNT`／`GIT_CONFIG_KEY_n=core.longpaths`／`GIT_CONFIG_VALUE_n=true`（原本有 `GIT_CONFIG_COUNT` 就接在後面），它叫起來的工具裡的 git 也吃得到；只在 selftest 裡設，tools 不變。
- GIT_DIR（`.git` 資料夾，或子模組在 `.git/modules/` 下的資料夾）超過約 220 字時，git 本身就停止（`'$GIT_DIR' too big`），`core.longpaths` 也沒用；只能把 repo 放在短一點的路徑。selftest_ds 沒有建子模組的測試，所以沒有這種 SKIP。
- 本機路徑當 remote（push、clone、fetch 到同一台電腦的另一個 repo）時，對方那一側的 git 不會繼承 `GIT_CONFIG_COUNT`／`GIT_CONFIG_PARAMETERS`（`git -c` 也一樣），要在對方 repo 裡設 `core.longpaths`，或用 `--global`；selftest_ds 建的 bare origin 就是這樣設。

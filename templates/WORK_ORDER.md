# WO-<編號> — <短名>
**<一句話目標>**

```text
ISSUED_BY      = 總監  <YYYY-MM-DD HH:MM，讀 date>
REVISION       = 1    # 開工後每改一次 +1，並在 H 節加一列
TRACES_TO      = <這張工單服務的初衷卡、需求或決定編號，逗號分隔，例如 B-2, DD-03；有初衷卡時至少一個 B 編號（docs/12）；沒有寫 NONE>
BRIEF_REVISION        = <選用：初衷卡版次；不用就刪掉這兩行>
BRIEF_FINGERPRINTS_V1 = <選用：gate_check.py --brief BRIEF.md 印的 {"B-2": "<64 位雜湊>"}>
PRIMARY_WORKER = 子代理「<名稱>」（例：w1；總監用 subagent 開，名稱只能小寫英數和 -）
MODEL / EFFORT = deepseek-flash / <off|low|high|max>（理由見 docs/05；開工時指定，開完不能中途改；`subagent` 的 reasoning_effort 一定要填這個值，派工後跑 `dsh_usage.py --effort-check <本工單>`，把印出的 EFFORT_ACTUAL 行貼進 DIRECTOR_LOG，不一致會印 shadow WARN，2.2.4-ds.4）
FALLBACK       = <同名子代理續談（send_message 從 RESUME_STATE 接續）| 開接班子代理>
GOVERNANCE     = <Direct | Standard | Strict>
BASE_REF       = <remote/branch @ commit，例：origin/main @ 1bfcb4a>   # 開工前先 git fetch，寫 fetch 後遠端分支的最新 commit；落後時 gate_check --order 印 WARN BASE_REF（docs/02）
NEW_BRANCH     = <分支名>
WORKTREE       = <預設：這張工單自己的 git worktree，派工前用 `dsh_session.py --worker-worktree <REPO> --order <WO> --branch <NEW_BRANCH> --base <BASE_REF 的 commit>` 開（2.2.5-ds.5，docs/11）；只有明寫「共用 checkout」才和別人共用，那時 `scope_check.py` 只看本工單的 commit（commit 訊息要寫工單編號）和 SCOPE 內還沒 commit 的檔（2.2.4-ds.4）。報告的 WORKTREE 行由工具產生，不自己寫>
WORK_DIR       = <放報告、RESUME_STATE.md、輸出的資料夾；開工先把 TEMP／TMP／TMPDIR 設成 WORK_DIR/tmp，`dsh_session.py --temp-env <WORK_DIR>` 印出設定行，2.2.4-ds.4>
BUDGET         = <US$0 | PO 核准的金額>
HEAVY_RESOURCE = <無 | 需先 TEST REQUEST：類型、預估分鐘>
WORKER_LIMIT   = <80 輪或 context 60%，先到先停（預設，可改）>   # 到上限就停：寫 HANDOFF.md、回報 lead，lead 開新的 worker 接續（docs/02，2.2.5）
```

兩個 `BRIEF_` 欄位是選用的：寫了以後，工單依據的初衷卡列被改掉時，`gate_check.py --order / --match --brief BRIEF.md` 印 `~ BRIEF_STALE`（舊條件驗過，新條件待重驗）；只是提示，不改結果。不寫照樣通過。

## A. 背景
需求、已知事實（附證據等級）、限制。只寫 worker 需要知道的。

## B. 目標
- MUST HAVE：
- OPTIONAL：
- 不做（OUT OF SCOPE）：<這次明確不做的範圍；沒有就寫「無」，不可留空>
- 可呼叫的入口：<交付物是函式庫或工具時，一個公開、測試可直接呼叫的函式：輸入路徑或資料 → 輸出結果，
  例 `report.build(path) -> Report`；不能只能從命令列用。不是函式庫或工具就寫「不適用」（2.2.4-ds.4，上游 2.2.4）>

可以改和不准碰的路徑（`tools/scope_check.py` 直接讀這兩份清單）：

```text
SCOPE:
- <相對 repo 根目錄的路徑或 glob，一行一個>
FORBIDDEN:
- <不准碰的路徑或 glob；沒有就寫 NONE>
```

大小上限（Standard／Strict）：最後結果 ≤3 個檔、約 200 行（新增＋刪除），`scope_check.py` 超過就印 `OVERSIZE`。上限寫在 director_work.json 頂層 `order_limits`（2.2.4-ds.4）；測試檔（`test_*.py`、`*_test.py`、`tests/` 下）算檔數，行數另算 `max_test_lines_per_order`（預設 400），不吃掉 200 行。估計會超過就拆成幾張工單。FORBIDDEN 加上 TESTS_LOCKED 的測試檔。

計畫閘門（Standard／Strict，`safety.plan_gate`，docs/13）：第一步只寫 `<WORK_DIR>/<本工單編號>/PLAN.md`（`- [ ] 1.1 …`，每項對到一條 AC），用 `send_message` 交給總監，**等總監回覆已核准（DIRECTOR_LOG 有 `PLAN_APPROVED`）才寫程式**。之後照 PLAN.md 做，做完一項打勾一項；要加、改、刪項目先回報總監。不改 TESTS_LOCKED 的測試。

`*` 不跨資料夾，`**` 跨資料夾，沒有萬用字元的名稱連底下全部都算。兩邊都符合時以 FORBIDDEN 為準。不要寫「相關檔案」這種話。

預設每張工單用 `dsh_session.py --worker-worktree` 開獨立 git worktree（`subagent` 的 `cwd` 指到該 worktree）；只有在明確寫 `WORKTREE = 共用 checkout` 時才共用同一工作區並以 `scope_check.py --shared`＋Single Writer 檔案歸屬隔離。DSH 沒有事前阻擋 hook，SCOPE / FORBIDDEN 就是寫入邊界，交件時必跑 `scope_check.py --candidate <候選 commit>` 核對實際 diff。

選用：一定要改到的路徑。`scope_check.py` 會查每一條都有對到改動，沒對到就印 `MISSING` 並判越界；每一條都要在 SCOPE 裡、不在 FORBIDDEN 裡（`gate_check.py --order` 會查）。不需要就整段不寫。比的是最後結果（2.2）：改了又改回的不算；總監審查時用 `scope_check.py --order 本工單 --repo <repo> --candidate <候選 commit>`。

```text
REQUIRED_CHANGES:
- <一定要改到的路徑或 glob，例如 src/parser.py>
```

## C. 執行前檢查
repo 與分支、工作樹乾淨、未提交修改、相關規範、相依、實際行為、能否重現、基準測試。路徑不存在先搜尋，不假設。
製作類工單先做既有資產盤點：未合併分支（`git log --all -- <路徑>`）、需求方提供過的檔案、舊報告；結果寫進 TASK REPORT 的 DONE（docs/02）。

## D. 實作要求
沿用現有架構；最小但完整；處理例外；必要的向後相容；補上直接相關的測試；不做無關重構。每項修改做成開關，方便批次驗證（docs/02）。

- 行數上限（2.2.5）：<每個檔或函式的行數上限，或「無」>；worker 自檢時自己量，結果寫進 TASK REPORT。
- 新增任何上限（大小、筆數、深度）都寫理由，並拿真實資料的最大值確認擋不到（2.2.5）。
- 程式最上層攔下所有例外，使用者看不到 Traceback；錯誤訊息不回顯控制字元、不顯示原始 Python 例外文字，該報的問題照報（2.2.5）。

## E. 驗收條件
| ID | 類型 | 要求 | 驗證方法 | 預期 |
|---|---|---|---|---|
| AC-1 | <AUTO / REVIEW / PO> | | | |

- `AUTO`：有指令可以重跑。總監自己重跑後判定；驗證指令用 `evidence_record.py` 留紀錄。核准的指令寫在下面的 `CHECKS:`（選用，Strict 建議寫），一條 AUTO 一行，JSON 字串陣列、不經 shell；` #` 之後是註解，要保留 ` #` 就把整個項目用反引號包起來；派工雜湊會鎖住它，總監用 `evidence_record.py verify --rerun --order` 跑的就是這一行，worker 用同一個指令記錄（`evidence_record.py run --order <本工單>`）：

```text
CHECKS:
- AC-1: ["python", "-I", "-m", "unittest", "tests.test_parser"]
```

  路徑一律用正斜線（`D:/ws/tools/x.py`，Windows 也認得）：JSON 裡的反斜線不是合法字元（`\w`），或會悄悄變成控制字元（`\t`、`\n`），`gate_check.py --order` 派工前就擋下並指出第幾行（2.2.4-ds.4）。
  CHECKS 可以放任何可重跑的指令，包括本規則包的檢查工具（路徑照專案實際位置寫）：`["python", "-I", "-X", "utf8", "<WS>/DIRECTOR/tools/round_check.py", "--resume", "<WS>/DIRECTOR/RESUME_STATE.md"]`。放進 CHECKS 就等於核准它在 `--rerun` 時被執行。
- `REVIEW`：要有人看成品。開工前寫明誰看、從哪個角度看、看多大範圍、看哪些常識閘門項目（docs/07）。reviewer 用 `subagent` 開；DSH 子代理預設拿到完整工具集，不能只給讀取工具，所以 review 的範圍靠工單指示＋總監事後用 `dsh_audit.py` 核對（docs/07）。worker 最多填 `READY_FOR_REVIEW`。
- `PO`：PO 保留的判定，例如最終驗收。worker 和總監都只填 `PENDING_PO`。同一個 commit 給 PO 看兩份以上成品時，報告寫 `CANDIDATE_ID: <PO_ACCEPTANCE 的 candidate_id>`（2.2）。
- 接手演練、要用 `metrics_report --run --compare` 比較的工單：run 資料夾的 `run.json` 要寫 `sampling` 標記（`complete`、`scenario`），否則比較結果是 UNKNOWN（2.2，`tools/README.md`）。
- 邊界與壓力清單（2.2.3，L-048）：寫 AUTO 條件時逐項想過，用得到的寫成 AC 或測試案例：
  - 遞迴／巢狀深度（例如 1000 層括號）
  - 輸入長度（空字串、極長輸入）
  - 重複的一元運算子或符號（`--5`、`+++`、`((((`）
  - 極大數字、溢位、除以零
  - 不是字串的輸入（None、數字、list）
  - Unicode 與全形字元（全形數字、全形運算子）
  - 錯誤訊息不漏出程式語言的原生訊息（traceback、RecursionError）或英文訊息，照工單規定的語言與格式
  - 巢狀深度（含 JSON）：讀檔或解析 JSON 時，深層巢狀（例如 1000 層 `[[[…]]]`）也回清楚的錯誤，不透出 RecursionError（2.2.4-ds.4）
  - 預設輸出要列出哪幾筆有問題：批次輸入有錯時，不加參數的預設輸出就列出是哪幾筆（第幾筆或哪個鍵）；問題物件用 dict 或中文名稱，不要用 `XxxError` 類別名當使用者看到的字（2.2.4-ds.4）
  - 需求寫「不當掉／不崩潰」時，至少一條 AC 用極端輸入驗證（例如上面的深度或長度）
  - 怪檔案（2.2.5）：讀檔的工具拿 `templates/weird_inputs.py <資料夾>` 產生的空檔、BOM、控制字元、超長行、深層巢狀、錯誤編碼逐一餵過
  - 期望值由獨立的 oracle 或手算表產生，不由寫程式的人邊寫邊抄（2.2.5）
- 選用的 `追溯` 欄（加在表的最後一欄）：這條 AC 驗證 TRACES_TO 的哪些編號，例如 `DD-03`；沒有寫 `—`。不加這欄也照樣通過；加了之後 `trace_report.py` 每個編號一列，不必猜哪條 AC 服務哪個需求。

- 驗收優先寫 `AUTO`：能用指令判定的就不要寫成 REVIEW／PO。
- 測試先寫並鎖定（Standard／Strict 必填，`safety.tests_first`）：驗收測試在派工前寫好並 commit 到 BASE_REF，`python -I -X utf8 tools/safety_gate.py --lock-tests <測試檔> --repo <專案>` 印的清單貼在下面；worker 不得改，改了 `gate_check.py` 判不過。沒有測試的文件類工單寫 `- NONE  # 理由`。`scope_check.py` 也把它們當受保護的測試。
- 受保護的測試只准新增（2.2.4-ds.4）：TESTS_LOCKED 的檔和 director_work.json 頂層 `protected_tests` 列的檔，worker 只能新增檔案或在檔尾加測試；改到原有內容或刪檔，`scope_check.py` 判 `PROTECTED` 越界。scope_check 印的 `PROTECTED_CHANGED:` 行照抄進報告；寫「無」而 diff 有改，`gate_check.py --match` 判不過。

```text
TESTS_LOCKED:
- <相對專案根目錄的測試檔> sha256=<64 位>
```

結果不寫在這裡，寫在 TASK REPORT 的 ACCEPTANCE 表。成品類交件另附常識閘門表（docs/07）。

## F. 安全與版控
照 docs/08。驗收條件和規格不准改，有問題回報 BLOCKED 由總監裁決（docs/02）。總監派工時記下本檔雜湊，交件時比對；DSH 沒有 hook 主動擋改工單，改了會被雜湊查出來，但工具擋不住改動。本工單特別禁止：<...>

## G. 交付與停止規則
- DELIVERABLES：<檔案、commit / tag、審查包>
- 完成：一則 TASK REPORT 給總監（templates/TASK_REPORT.md），並用 `send_message` 通知總監。
- STOP_RULES：同一根因 1 輪沒進展就停並回報；超出 SCOPE 先問；超過測試上限 10 分鐘先停下回報。
- 先用 DW 現有工具（2.3.0）：檢查、比對、等待、狀態整理先找 `tools/README.md`，自己寫的要說明為什麼現有工具不夠。
- 根因研究（2.3.0）：`ROOT_CAUSE_STUDY.md` 每一節先放「測試條件 vs 參考條件」表，再寫 WHERE / ALTERNATIVES / DECISION。
- 放寬量測標準前先做一次盲測；確認前舊標準照用（2.3.0）。
- 宣告一組做完前，核對資料夾、程式、提示詞是同一組（2.3.0）。
- 和真實影片對照（2.3.0）：每一種情境類型、在成品內並排；呈現方式（HUD、各階段鏡頭、切鏡時機、重播）也和真實轉播並排；設計原創，不複製別人的素材或標誌。
- 打轉與回報（2.3.0-ds.6）：同一呼叫失敗兩次，先寫一行「為什麼失敗、下一步改什麼」再試；派出的子工作在逾時內沒有結果或出錯，都用 `send_message` 回報主管，不可靜默等待；宣告完成前，本輪跑過驗證指令並附 RAN 行（`ran_line.py`）。事後用 `dsh_audit.py loops` 查（DSH 沒有事前攔截）。
- 到 WORKER_LIMIT 就停（2.2.5）：寫 `HANDOFF.md`（`templates/HANDOFF.md`：做完什麼、還剩什麼、下一步、檔案路徑），用 `send_message` 回報 lead；lead 開新的子代理從 HANDOFF.md 接續。

## H. 變更紀錄
只有總監能改本工單。REVISION 1 不用寫；之後每改一次加一列，同步 BRIEF.md、WORK_DIR/tasks.md、WORK_DIR/RESUME_STATE.md，再把新的雜湊告訴 worker（`gate_check.py --order` 對比工單舊的 tasks.md／RESUME_STATE.md 印 `REVISION_SYNC`）。

| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |
|---|---|---|---|---|

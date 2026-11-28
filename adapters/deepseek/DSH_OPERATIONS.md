# DSH_OPERATIONS：在 DeepSeek Harness 上操作

本檔是 dsh-DIRECTOR-WORKER（dshdw）的平台說明，對應基板的 `docs/11_claude_desktop.md`（那份是 Claude 專用，DSH 不讀）。
只在 DSH 上當總監時讀，不列入每輪必讀。3.0.0-ds.8：`DIRECTOR/` 在專案裡（`<REPO>/DIRECTOR`，不進 git）；`<D>` 指它，基板工具在 `<D>/tools/`，DSH 工具在 `<D>/adapters/deepseek/`。規則照 `docs/01` 到 `docs/10`；這裡只寫「流程需要的能力，在 DSH 上用哪個工具做」。

## 先看平台

- 模型只有 `deepseek-flash`；思考程度 `off / low / high / max`。總監自己的模型與 effort 由 PO 在 DSH 設定：composer 的模型控制項或 `/model` 選單，套用到下一個請求（進行中的 step 不變）；新 session 的預設值在 Settings → Models。worker 開工時指定、不能中途改（`docs/05`）。
- 總監＝根 session（代理名 `lead`）；worker＝用 `subagent` 工具開的具名子代理。子代理共享同一個檔案系統、可指定 cwd、可續談、會回完成通知。
- 同一棵樹最多 8 個作用中子代理、委派深度 1（worker 不能再開子代理）；這兩個上限在 DSH「設定 → 子代理」。
- 總監必須是**根 session**：DSH 只讓根代理使用 `ask_user_question`、排程與 goal/plan 權限；被開成子代理的「總監」會直接被拒。
- Team 模式（`team_task_*` 共享工作板）預設關閉，可以由 PO 在 model menu 開啟；本版只把它當輔助，工單與狀態檔案才是真相來源。
- **預設隔離方式為每個 worker 各自建 git worktree**：DSH 內建沒有 worktree 工具，開 worker 前一律跑 `dsh_dispatch.py <工單> --repo <REPO>`（規格閘門、`gate_check --hash`，再用基板 `tools/worktree.py open` 建獨立 worktree），印出 GO 後再將 `subagent` 的 `cwd` 指過去；只有在工單明寫 `WORKTREE = 共用 checkout` 時才共用同一工作區，此時靠 `scope_check.py --shared`＋Single Writer 檔案歸屬＋總監看 diff 把關。
- 工具名稱會隨 DSH 版本變。下面的名稱是 0.2.2 桌面版；找不到時用能力關鍵字在工具清單找，不要猜。

### 提示詞規則 vs 工具檢查 vs 硬防護

DSH **沒有 PreToolUse／PostToolUse hook**，各類限制依賴不同層級，不可把提示詞或事後檢查誤認成執行前硬擋：

| 層級 | 在 dshdw 涵蓋的事 | 實際效果 |
|---|---|---|
| DSH 平台硬防護 | 沙箱模式（`read-only / workspace-write / danger-full-access`）、核准政策（session 級）、`ask_user_question`／排程拒絕委派子代理 | 檔案寫入邊界與角色權限；若設為 `danger-full-access + never` 則無執行前阻擋 |
| CLI 事後／閘門檢查 | `scope_check.py --candidate`、`gate_check.py`（`--order/--match/--verdict/--final`）、`safety_gate.py`、`dsh_audit.py`、`report_vs_audit.py`、`dsh_guard.py`（手動） | 交件與驗收時揭露違規、鎖測變更、E2E 未完成與未記載指令；不能事前攔下操作 |
| 提示詞與規則 | 工單 `SCOPE / FORBIDDEN`、PLAN 核准、停工線、不自行 push/merge/刪檔 | 引導模型行為，須配合上兩層互驗 |

## 能力對照

| 流程需要 | DSH 的做法 | 注意 |
|---|---|---|
| 開 worker | 先 `dsh_dispatch.py`（印 `DSH_DISPATCH: GO` 才開），再 `subagent({name, cwd, prompt, provider, model, reasoning_effort})` | 沒有 hook 擋，GO 之前不開；`reasoning_effort` 一定要填工單 `MODEL / EFFORT` 的值（不填會用 session 預設，WO-DS-006 試驗全變成 max）；開完跑 `dsh_usage.py --effort-check <工單>`，把 `EFFORT_ACTUAL` 行寫進 DIRECTOR_LOG（2.2.4-ds.4）。先寫好工單再開；prompt 只給工單路徑、RESUME_STATE 路徑、一句目標。回傳 `started subagent <name>` 就代表已受理，不會等它做完。第一批要 PO 同意（`docs/12`）。 |
| 傳訊息給 worker | `send_message({agent, message})` | 只在 `docs/03` 的三種情況發。訊息會叫醒閒置的子代理並讓它跑一輪；送達不代表已讀。長內容寫檔，訊息只給路徑。 |
| 看 worker 列表與狀態 | `list_agents()` | 只給名字、running/inactive、description；沒有「正在做什麼」的細節，細節讀它的 `RESUME_STATE.md`。inactive 可能只是做完一輪，不代表結束。 |
| worker 回報 | worker 自己用 `send_message` 傳給總監，或做完一輪後 DSH 送完成通知 | 完成通知會帶最後結論；要它繼續就用 `send_message`。 |
| 讀用量與上下文 | `python -I -X utf8 <D>/adapters/deepseek/dsh_usage.py --project-dir <REPO>`（<REPO>＝總監 session 啟動資料夾；單一工作線用 `--session <agent>`；加 `--json` 給程式讀）；GUI：每個回合可展開 token usage、composer 的用量統計、Settings → General → Performance & usage | 沒有 `get_usage` 工具。數字是從 session 紀錄算的，量不到記 UNKNOWN，不當成 0；帳號餘額只在 GUI 的帳號頁（模型讀不到）。 |
| 調 worker 的模型/effort | 開子代理時帶 `reasoning_effort`（總監自己的由 PO 在 GUI 設定） | 不能中途改。要換 effort 就開接班子代理，交接靠 `RESUME_STATE.md`，並在 `ACTIVE_WORKSTREAMS.md` 記新 effort。 |
| 叫醒／排程 | `schedule_create`／`schedule_list`／`schedule_view`／`schedule_edit` | 依工具政策**只有 PO 明確要求**才能建立或修改排程；桌面版要開著才會到點；停機後只送最近一次。排程只能送給 session，子代理（delegated）不能用排程工具。 |
| PO 待決 | `ask_user_question`（一次一題到三題，選項各一句說明）＋本機帳 `DIRECTOR/PO_PENDING.md` | 沒有 Claude 的私人頁面、置頂、留言叫醒。答案記回 `PO_PENDING.md` 的 `ANSWER`；聊天只說「待決帳新增 OD-xx」。 |
| 要 PO 看圖挑 | 先把成品截圖用 markdown 圖放在同一則訊息，再用 `ask_user_question` 問 A/B | `ask_user_question` 的選項只有文字與說明，不能放圖；`present` 檔案卡回合結束後才出現，不能當成 PO 已先看到。 |
| 成品給 PO 看 | `present({files:[{path, description}]})`；就在聊天附圖 | 一次 1～2 個最重要的檔（上限 8）；檔案卡在回合結束後出現在右側 sidebar，可預覽圖片；`present` 只宣告成品，不會替你判斷對不對。子代理做的成品要由**總監自己**呼叫 `present` 才會被宣告。 |
| 結束工作線 | 沒有 interrupt／archive 工具 | 先 `send_message` 請它停在安全狀態並寫好 `RESUME_STATE.md`；完成後讓它閒置。真的失控時請 PO 在 GUI 的 subagent catalog 按 Stop，或在工作列的選單封存 session。 |
| 等 worker 做完 | 結束本回合等完成通知；或 `wait_agent`（10 秒～1 小時）等子代理傳來的訊息 | 不要一直發「做完了嗎」；沒有 notify_when_idle。 |
| 禁止 worker 自己問 PO | 規則：worker 只能回報總監 | 已查證：`ask_user_question` 對 delegated 子代理會被拒絕（DELEGATED_CALLER），worker 想問也問不到；工單仍要寫明「有問題回報總監」。 |
| 限制 reviewer 工具 | 子代理預設拿到完整工具集，沒有 per-child 工具限制工具 | 用指示「只准讀」＋總監事後用 `dsh_audit.py` 核對它有沒有寫檔；真的要限制只能改 DSH preset（使用者層，需要 PO 同意）。 |
| 專案指示 | `AGENTS.md`（DSH 也載入 `CLAUDE.md`；本版統一 `AGENTS.md`）＋ `AGENTS.local.md` 疊加；使用者層 `~/.dsh/AGENTS.md`、`~/.agents/AGENTS.md` | 子代理 session 會自動載入（已實測）。改指示後要讓相關 session 重新讀到：下一次成功讀寫到那個目錄，或重開 session。 |
| 檔案沙箱與核准 | 每個 session 有 `read-only / workspace-write / danger-full-access`；核准政策是 session 設定 | **沒有** PreToolUse hooks，hook_guard 不移植。`docs/08` 的「會擋」改成「規則＋PO 核准＋事後 audit」；不要宣稱自動擋。 |
| 每個 worker 的 worktree（3.0.0-ds.8 改用基板 `worktree.py`） | `python -I -X utf8 <D>/adapters/deepseek/dsh_dispatch.py <工單> --repo <REPO> --branch <工單 NEW_BRANCH> --base <BASE_REF 的 commit>`：通過閘門後由 `tools/worktree.py open` 在 `<REPO>/../wt/<WO>` 開一個 git worktree、一條分支；`subagent` 的 `cwd` 指到它。報告的 `WORKTREE:` 行用 `tools/worktree.py status <checkout>` 或 `gate_check.py --report-skeleton` 產生 | DSH 自己沒有 per-worker worktree，這是用 git 開的。WO-DS-008 r2：sdd 組自稱「隔離 worktree」，實際是共用 checkout；所以這一行由工具依 `git worktree list` 判斷，不自己寫。資料夾已存在就拒絕（不刪任何東西）。 |
| 共用 checkout 的範圍檢查（2.2.4-ds.4） | 工單 `WORKTREE = 共用 checkout` 時 `scope_check.py` 自動切到共用模式（也可加 `--shared`）：只算 commit 訊息寫了本工單編號的 commit，加上 SCOPE 內還沒 commit 的檔；別的工人的檔印 `OTHER`，不算越界 | commit 訊息一定要寫工單編號（例 `WO-12: …`），否則那個 commit 不算本工單的；本工單 commit 動到 SCOPE 外的檔照樣判越界。SCOPE 外還沒 commit 的檔看不到，所以交件前先 commit。 |
| 暫存資料夾（2.2.4-ds.4） | 開工先跑 `python -I -X utf8 <D>/tools/worktree.py temp <WORK_DIR>`，照印出的那行設 `TEMP`／`TMP`／`TMPDIR`（PowerShell 每個指令前加 `$env:TEMP=…;`，或在啟動 DSH 的 shell 先設好） | DSH 每個 shell 指令是新的行程，環境變數不會留到下一個指令；在啟動 DSH 前設最省事。 |
| 動作紀錄 | `python -I -X utf8 <D>/adapters/deepseek/dsh_audit.py build --session <agent> --out <D>/research/audit-<日期>.jsonl`（`--project-dir <REPO>` 抓整個工作區） | 事後從 session 紀錄重建，不是即時 hook；給 `report_vs_audit.py` 和 gate 審查用。子代理 session 記在總監 session 的啟動資料夾下，所以 `--project-dir <worker 的 worktree>` 抓不到 worker。input 經 secret_mask 後最多記 500 字，長指令尾端會截斷。 |

## lead 開工第一步（2.3.0-ds.5）

每次開新 session（含壓縮後接續），lead 第一個動作是 `python -I -X utf8 <D>/tools/worktree.py cwd <REPO>`（基板 3.0.0；`<REPO>` 照 `DIRECTOR/INDEX.md` 寫的專案）。比的是 realpath，Windows 不分大小寫；不同資料夾或子資料夾都印 BLOCKED、exit 1：停下，不寫任何檔，回報 PO 從哪裡重開。11-14 23:42 的 lead 在錯的資料夾做了整輪，寫進去的檔都要搬。

建置時 BOOTSTRAP 第 7 步（壓縮門檻）在 DSH 不做，但其中的 exclude 這一步要做：`python -I -X utf8 <D>/tools/bootstrap_repo.py --repo <REPO> --add .memsearch/`，把基板預設的兩項（含 `DIRECTOR/`）和 DSH 的記憶索引 `.memsearch/` 寫進 git 的 exclude 檔；本機路徑放在 `AGENTS.local.md` 時再加 `--add AGENTS.local.md`（第 4 步的 `CLAUDE.local.md` 在 DSH 是它）。要印 `BOOTSTRAP_REPO: DONE`。ds.7 的同名工具預設就排除 `.memsearch/`；3.0.0 改用基板工具，要自己加 `--add`。

## 開 worker 的流程

1. 先在待決帳列好要開的線：名稱（`w1`…）、工單路徑、effort、cwd（每條線自己的 git worktree，下一步開）、範圍。放進 `ACTIVE_WORKSTREAMS.md` 的草案。
2. 請 PO 同意（第一批可以併進初衷卡確認那一句）。沒有同意不開。
3. 每條線跑一次 `python -I -X utf8 <D>/adapters/deepseek/dsh_dispatch.py <工單> --repo <REPO> --branch <工單 NEW_BRANCH> --base <BASE_REF 的 commit>`；印出 `DSH_DISPATCH: GO` 才算好，`LOG:` 那行抄進 `DIRECTOR_LOG.md`。BLOCKED 就不開這條線，照印出的 step 修。只有工單明寫共用時才讓 worker 用主 checkout（那時 `scope_check.py` 用共用模式）。
4. 同一輪把要開的都開完（`cwd` 是上一步開的 worktree）：每個子代理的 prompt 只給「工單路徑、RESUME_STATE 路徑、一句目標」和限制（不改驗收條件、不碰範圍外、有問題回報總監、不要問 PO），再加一句「開工時把 TEMP、TMP（及 TMPDIR）設成 WORK_DIR/tmp」（2.2.4-ds.4，`docs/02`），以及「第一步跑 `<D>/tools/worktree.py cwd <你的 worktree>`，BLOCKED 就停下回報」（2.3.0-ds.5）。
5. 開完用 `list_agents()` 確認名字和數量；把實際名稱寫進 `ACTIVE_WORKSTREAMS.md` 和 `DIRECTOR_LOG.md` 的 DISPATCH 行。DISPATCH 行的 effort 用 DSH 的等級，檢查時帶 DSH 的表：`dispatch_check.py --log DIRECTOR_LOG.md --table <D>/adapters/deepseek/DSH_EFFORT_TABLE.json`（基板預設表是 Claude 的 medium／xhigh）。機械工作（`mechanical`）可以用 `off`（不思考）或 low；基板 3.0.0 起認得 `off`。
6. 之後只靠 `send_message` 和檔案交接；不要為了問進度發訊息（`docs/03`）。
7. Standard／Strict 工單（`docs/13`）：開 worker 前規格審查（`SPEC_REVIEW`）要先完成；prompt 寫明「第一步只寫 `<WORK_DIR>/<WO>/PLAN.md`，交給總監、等 `PLAN_APPROVED` 才寫程式」「不改 TESTS_LOCKED 的測試」「同一根因 1 輪沒進展就停」。

## 常見用法

- **確認指示有載入**：在專案 `AGENTS.md` 寫總監段落後，開一個小探測子代理（cwd 指到專案），請它回報有沒有看到段落；看得到才算生效。
- **量用量**：`dsh_usage.py --since <建置日>` 看專案相關 session 的 tokens 與上下文壓力；GUI 對照看目前 session。
- **核對動作**：worker 交件後 `dsh_audit.py build`，再把 `RAN:` 的聲明用 `report_vs_audit.py` 對一次。
- **待決問題**：一次最多三題，每題給選項和建議；PO 在 GUI 回答，總監把原文寫進 `PO_PENDING.md` 再處理。
- **排程喚醒**：只有 PO 明確要求才建；建完用 `schedule_list` 記進 `GUARDS.md`。

## DSH 實機注意（2026-11-14 試跑踩到的；2.2.5-ds.5 從 docs/13 搬來）

- **子代理的模型路由**：開子代理時 `provider` 要寫 lead 自己在用的那個。這台是 `deepseek-account`，所以寫 `subagent({name, prompt, provider: "deepseek-account", model: "deepseek-flash", reasoning_effort: "high"})`。
  - 寫成 `provider: "deepseek"`（也就是 `deepseek/deepseek-flash`）會被 DSH 拒絕。
  - 不確定時先跑 `list_subagent_models({provider: "deepseek-account"})` 看可用的組合。
  - 用 API 金鑰登入的機器，provider 是 `deepseek-official`，同樣先用 `list_subagent_models` 確認。
- **GATE_VERDICT 的 ORDER 行**：要以工單編號開頭，只寫工單檔名，例如 `ORDER: WO-101-clamp.md REVISION 1`。
  - 寫完整路徑或工單標題，`gate_check.py --verdict --match` 認不出是哪張工單，也就不會核對裁決和工單的 REVISION：Strict 工單判不過，Standard 只印 `~ ORDER: the verdict names no order` 提示。實測：完整路徑和「加入 clamp WO-101」兩種寫法都認不出來。
  - 工單完整路徑另起一行寫，不要放在 ORDER 行。
- **GATE_VERDICT 的 F 節（停止狀態）必填**：空白或缺節，`gate_check.py --verdict` 會判不過。最少寫 `NO MERGE / NO PUSH / NO FINAL ACCEPTANCE`。

## 省 token（ds.3；2.2.5-ds.5 從 docs/13 搬來）

WO-101 實機一次用了約 829 萬 token（lead 430 萬／49 步、worker 373 萬／48 步、規格審查 26 萬／5 步）。量測方法和每一項的數字在 ds.3 的 `TOKEN_ANALYSIS.md`（工作資料夾，不進 repo），重點：

- DSH **每一步都把整段對話重送一次**。固定部分（系統提示、`run_code` 說明、卡片說明）約 46K token／步，佔全部的一半以上；所以**步數**是最大的成本，其次是早期讀進來、之後每步都重送的大段輸出。
- worker 約 12 步在讀 `gate_check.py`／`report_vs_audit.py` 原始碼學報告格式；lead 約 13 步在試 provider、讀 `--help`、讀裁決的解析程式。這些都能用下面的規則省掉。

規則（lead 和 worker 都照做）：

1. **一個階段一個 `run_code`**：探索（工單、測試、git 狀態一次讀完）、commit＋錄證據＋scope_check、驗收（scope_check＋`--match`＋`verify --rerun`＋讀報告＋看 diff）各寫成一個 `run_code`，不要一個指令一步。
2. **不讀工具原始碼、不跑 `--help`**：要用的指令都在下表；報告格式用 `gate_check.py --report-skeleton` 產生，不要從原始碼反推。
3. **只印需要的**：長輸出只留最後幾行（例：`... | Select-Object -Last 20`）；讀檔只讀要的段落。
4. **最後一個 commit 之後才錄證據**：先錄證據再改檔會讓工作樹變髒，得 amend、重錄證據、重寫報告（WO-101 多花 5 步）。
5. **子代理一次開對**：`provider` 照上一節直接寫，不要先試。
6. **RUN_SUMMARY 不寫 token 數**：用量由總監事後用 `dsh_usage.py`／`verify_dsh_run.py` 從紀錄算；lead 不用自己查。
7. worker 不必自己跑 `dsh_audit.py`／`report_vs_audit.py`：`RAN` 行照實際指令逐字抄（不要縮寫），對紀錄是總監的事。
8. **讀過的檔不整份重讀**（2.2.3-ds.3）：工單、RESUME_STATE、工具原始碼在同一個 session 讀過一次就好。確認自己寫的內容看寫入工具的回傳或 `git diff`；工單改版只讀 H 節變更紀錄和改到的段落。WO-DS-004 的 lead 把工單讀了 7 次、RESUME_STATE 7 次、`dsh_setup_check.py` 4 次，重讀合計約 54 萬 token（每次讀進來的內容之後每一步都會重送）。

| 誰 | 什麼時候 | 指令（`PY` = `python -I -X utf8`，`T` = `<D>/tools/`，`A` = `<D>/adapters/deepseek/`） |
|---|---|---|
| 總監 | 寫完工單 | `PY T/gate_check.py --order <工單> --repo <專案>` |
| 總監 | 派工 | `PY A/dsh_dispatch.py <工單> --repo <專案>`（內含 `gate_check.py --hash`；印出的 `LOG: DISPATCH` 行寫進 DIRECTOR_LOG） |
| worker | 開工 | `PY T/gate_check.py --report-skeleton <工單> --repo <專案> --out <報告路徑>`：寫好報告骨架，並印出錄證據、scope_check、`--match` 的完整指令，照順序跑 |
| 總監 | 驗收 | `PY T/scope_check.py --order <工單> --repo <專案> --candidate <commit>`；`PY T/gate_check.py --match <報告> <工單> --evidence-dir <證據> --dispatch-log <DIRECTOR_LOG> --repo <專案>`；每條 AC `PY T/evidence_record.py verify --rerun --order <工單> --dispatch-log <DIRECTOR_LOG> --repo <專案> --candidate <commit> <紀錄檔>` |
| 總監 | 裁決 | `PY T/gate_check.py --verdict <裁決> --match <報告> <工單> --candidate <commit> --repo <專案>` |
| 總監 | 事後驗證 | `PY A/verify_dsh_run.py --config <設定>`（設定格式見 `A/VERIFY_DSH_RUN.json`） |

預估（同一個 clamp 任務，方法見 `TOKEN_ANALYSIS.md`）：照規則 1～7 做，約 340 萬 token（−59%；S 取 42K～49K、推理內容算不算重送，結果都在 −58%～−60%）。這是用 WO-101 的實際各步大小推算的，**還沒有實機重跑驗證**。

PO 選做：系統提示裡約 61K 字元是卡片元件說明（`## 可用组件`、`## 卡片的 JSON Schema`、`## Schema Snippets` 等段，約 19.5K token／步）。dshdw 的流程不用卡片；如果 DSH 能在設定裡關掉這組卡片說明，再省約 1 成（預估 −70%）。dshdw 不改 `~/.dsh`，要不要關由 PO 決定。

## 已知限制（不要假裝有）

- 沒有 Claude 的 Artifact 私人頁面、置頂、留言叫醒；待決與選擇改成 `ask_user_question`＋`PO_PENDING.md`。
- 沒有 `interrupt_agent`、session 封存、讀別人的 context/用量工具；只能傳訊息、看列表、讀檔案與 session 紀錄。
- 子代理不能中途改模型或 effort；只能開接班人。
- 子代理預設全工具，不能 per-child 只給讀取；reviewer 限制靠指示與事後核對。
- 沒有 hooks，命令層級的自動阻擋做不到；只能靠沙箱模式、核准政策、工單範圍、事後 audit。
- 排程工具只給 PO 明確要求的用途，且只有總監（根 session）能用。
- 沒有容器 worker、沒有外掛專案級開關、沒有記憶索引檔。
- DSH 版本更新可能改工具名與 GUI 路徑；不確定時以工具說明與 `dsh_doctor.py` 的結果為準。

## 為什麼

- Claude Desktop 版靠「開 session、SendMessage、list_sessions、get_usage、Artifact」；DSH 用子代理、send_message、list_agents、session 紀錄與 ask_user_question。能力對照寫下來，新總監不用自己摸索就不會誤判成做不到。
- DSH 沒有 hook 和權限詢問可依賴，所以安全規則從「工具會擋」改成「規則、PO 核准、沙箱模式、事後 audit」四層；寫清楚才不會讓 PO 以為有自動保護。
- 子代理的模型與 effort 開工就固定，把限制寫明才不會有人以為可以中途調；接班流程反而讓交接有紀錄。
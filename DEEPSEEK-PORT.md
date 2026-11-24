# DIRECTOR-WORK → dsh-DIRECTOR-WORKER：移植報告

本 repo 的產品名是 dsh-DIRECTOR-WORKER（簡稱 dshdw；舊名 DIRECTOR-WORK DeepSeek 版（DW-DS））。

本檔說明這次移植：動了什麼、為什麼、哪些搬不過去、怎麼驗證、以後怎麼跟上上游。

## 1. 移植原則

1. **流程核心不動。** 權責分層、工單與 gate、證據優先、RESUME_STATE 續航、初衷卡、Single Writer、依風險選流程——這些是 `PURPOSE.md` 的九項核心，原樣保留。
2. **平台層重寫。** 凡是「Claude Code／Claude Desktop 提供的能力」，換成 DeepSeek Harness（DSH）的等價做法或誠實的替代；做不到的標 NOT_PORTED，不假裝。
3. **能少改就少改。** 文件只改平台耦合處；工具只移植平台中立的部分；新增的 DSH 工具集中在新檔，不散落各處。
4. **可驗證。** 每個新工具都用真實 session 紀錄跑過；每份文件不自稱平台沒有的能力；驗證結果寫在第 8 節。

## 2. 平台事實（移植時依據）

| 事實 | 值 | 來源 |
|---|---|---|
| 平台 | DeepSeek Harness 桌面版 0.2.2-rc.2（DSH） | `~/.dsh/profiles/desktop/cordis.patch.yml`、app asar |
| 模型 | `deepseek-flash`（DeepSeek-V4.1-Flash），目前唯一 | 模型選擇器、request/header 紀錄 |
| 思考程度 | `off / low / high / max`；`off` 關閉思考 | `dsh-llm-deepseek` 套件文件 |
| 上下文視窗 | 1,048,576 tokens（官方模型清單） | session 紀錄的 request/context、`dsh-llm-deepseek` README |
| 單次輸出上限 | 預設 256,000 tokens | request/header config |
| 自動壓縮 | 有（dsh-compaction-basic） | DSH 套件文件 |
| 專案指示 | `AGENTS.md`（也讀 `CLAUDE.md`）、`AGENTS.local.md`；專案鏈每條 64 KiB | `dsh-agent-instructions` README |
| 使用者層指示 | `~/.dsh/AGENTS.md`、`~/.agents/AGENTS.md` | 同上 |
| worker | `subagent` 開的具名子代理，可續談、可傳訊息、有完成通知 | `dsh-tool-subagent` README |
| 子代理上限 | 每棵樹作用中預設 8；委派深度預設 1 | `dsh-subagent` README、GUI 設定 |
| 檔案沙箱 | `read-only / workspace-write / danger-full-access` | `dsh-sandbox-policy` README、session 紀錄 |
| 核准政策 | session 設定（本環境可設 never ask） | `dsh-user-approval` 套件、session 紀錄 |
| Hooks | **沒有** PreToolUse 等 hook 機制 | asar 套件清單無 hook 套件 |
| 待決問答 | `ask_user_question`（選項＋自訂答案，可多題）；**對 delegated 子代理會被拒絕**（DELEGATED_CALLER），只有總監能問 PO | 工具 schema、`dsh-tool-ask-user` README |
| 成品展示 | `present`（上限 8 個檔；子代理做的檔要由總監自己呼叫） | 工具 schema、`dsh-tool-present` README |
| 用量資料 | 另有純 JSON 的投影快取 `%USERPROFILE%\.dsh\storages\session_projcache\sessions\<id>.json`（`tokenUsage`、`contextPressure`、`sessionStats`、`sandboxMode`、`approvalState`…） | 實際檔案（version 7） |
| worktree | DSH 本身**沒有**內建 worktree 工具；本版預設先用 `dsh_session.py --worker-worktree` 建獨立 git worktree 再設 `cwd`，僅在宣告時共用 checkout | asar 套件清單、`tools/dsh_session.py` |
| 成品展示 | `present`（成品檔）、聊天 markdown 圖 | 工具 schema |
| 排程 | `schedule_create/list/view/edit`；只有 PO 明確要求可建；子代理不能用 | `dsh-tool-schedule` README |
| 共享工作板 | Team 模式下的 `team_task_*`（本版不用作真相來源） | `dsh-tool-agent-team` README |
| 用量與動作 | session 紀錄：`%USERPROFILE%\.dsh\sessions\--<cwd>--\session-<id>\session.v4.jsonl.zstd` | 實際檔案 |
| 遠端/封存/中止 | **沒有** session 封存、interrupt_agent（本 profile 未掛載） | 工具清單、`dsh-tool-subagent-control` 文件 |

## 3. 能力對照表

| DIRECTOR-WORK 需要的能力 | Claude 版做法 | dshdw 做法 | 狀態 |
|---|---|---|---|
| 開一條 worker 工作線 | `start_session` | `subagent({name, cwd, prompt, reasoning_effort})` | 移植 |
| 傳訊息給 worker | `SendMessage` | `send_message({agent, message})` | 移植 |
| 看 worker 狀態 | `list_sessions`／`get_session` | `list_agents()`＋讀 `RESUME_STATE.md` | 移植（細節較少） |
| worker 回報總監 | 訊息／完成通知 | `send_message`／DSH 完成通知 | 移植（已實測） |
| 調 worker 模型/effort | `set_session_model`／`set_session_effort`（可中途） | 開工時指定 `reasoning_effort`；要改開接班人 | 部分移植 |
| 額度／上下文用量 | `get_usage` | `tools/dsh_usage.py`＋GUI token meter | 替代 |
| 專案指示 | `CLAUDE.md` | `AGENTS.md`（也認 CLAUDE.md） | 移植 |
| 使用者層規則 | `~/.claude/CLAUDE.md` | `~/.dsh/AGENTS.md`、`~/.agents/AGENTS.md` | 移植 |
| 待決頁 | Artifact 私人頁面＋置頂＋留言叫醒 | `ask_user_question`＋本機 `PO_PENDING.md` | 替代（無置頂／網頁） |
| 選擇題 | choice_page 網頁＋資料庫＋收條 | 聊天附圖＋`ask_user_question` | 替代（較簡） |
| 成品給 PO 看 | Artifact 截圖＋頁面 | `present`＋聊天 markdown 圖 | 替代 |
| 叫醒／排程 | 背景計時器／排程任務 | `schedule_create`（PO 明確要求時） | 移植（有條件） |
| 工具前自動阻擋 | PreToolUse hook（hook_guard.py） | 無；沙箱模式＋核准政策＋規則＋事後 audit | NOT_PORTED |
| 動作紀錄 | hook 寫 hash chain log | `dsh_audit.py` 從 session 紀錄重建（需 Node 解 zstd） | 替代（事後） |
| 用量 | `get_usage`、Claude transcript | `dsh_usage.py` 讀 projcache JSON（純 Python） | 替代 |
| worktree 隔離 | 每條線獨立 worktree | 已整合至 `dsh_session.py --worker-worktree`（預設隔離）與 `--shared`（例外共用），透過 `subagent` 的 `cwd` 隔離 | 部分移植 |
| 容器 worker／網路管制 | container/run_worker.sh | 無 | NOT_PORTED |
| 外掛清單與關閉 | `claude plugin list`／`plugins_off` | 使用者層設定，本版不改 | NOT_PORTED |
| 記憶索引 | `~/.claude/projects/.../MEMORY.md` | AGENTS.md 指示鏈＋DIRECTOR 檔案 | NOT_PORTED（無索引檔） |
| 壓縮門檻 250000 | `.claude/settings.local.json` | 模型視窗 1,048,576＋DSH 自動壓縮 | NOT_PORTED（不需要） |
| 額度重置喚醒 | 5 小時／週視窗 | 無對應；改成中斷恢復程序 | NOT_PORTED |
| 盲審 reviewer 限工具 | subagent 只給 Read/Glob/Grep | 子代理預設全工具；指示＋事後 audit | 部分移植 |

## 4. 文件改寫清單

| 檔案 | 改寫幅度 | 內容 |
|---|---|---|
| `README.md` | 大 | 啟動提示詞、流程、FAQ、檔案地圖改 DSH；新增「Claude 版和 dshdw 有什麼不同」、防護對照、限制 |
| `PURPOSE.md` | 無 | 原文保留（只有 PO 能改）；平台字樣屬歷史，PO 可自行更新 |
| `BOOTSTRAP.md` | 大 | 0～14 步重寫：待決帳、DSH 設定、子代理名額、指示載入驗證、`dsh_usage.py` 基準、開子代理、第一份回報 |
| `docs/01` | 小 | 角色改根 session／子代理；子代理上限與深度；reviewer 限制說明 |
| `docs/02` | 中 | MODEL/EFFORT 改 deepseek-flash／effort；規格審查改子代理；報告核對改 `dsh_audit.py`；移除 hook 敘述 |
| `docs/03` | 小 | 跨代理訊息、send_message、無 notify_when_idle；待決頁改 ask_user_question＋PO_PENDING |
| `docs/04` | 大 | token 計價、1M 上下文、KV cache、自動壓縮、`dsh_usage.py` 量測；移除方案額度與停工線 |
| `docs/05` | 大 | 只有 deepseek-flash；effort off/low/high/max；不可中途改；接班流程 |
| `docs/06` | 小 | 自動壓縮；子代理續談；RESUME_STATE 不變 |
| `docs/06b` | 中 | 恢復程序改用 `list_agents`＋子代理續談；機制重建用 `schedule_create`；移除容器與額度重置 |
| `docs/07` | 小 | 盲審 reviewer 改子代理（無法限工具）；成品用 `present`／聊天圖 |
| `docs/08` | 小 | 保留核准清單；新增「DSH 能擋到什麼」；移除權限模式與 hook 敘述 |
| `docs/09` | 中 | AGENTS.md 指示鏈大小（64 KiB）＋DIRECTOR 檔案；沒有 MEMORY.md |
| `docs/10` | 輕 | 保留教訓；開頭說明哪些是 Claude 版機制、dshdw 不適用 |
| `docs/11_dsh_operations.md` | 新 | 取代 `11_claude_desktop.md`：能力→工具對照、開 worker 流程、限制清單 |
| `docs/12` | 大 | 選擇頁改聊天附圖＋ask_user_question；移除 Artifact／choice 帳本；初衷卡與追溯保留 |
| `templates/` | 中 | AGENTS_PROJECT_SECTION（新）、PO_PENDING（待決帳）、RESUME_STATE（子代理名稱）、DIRECTOR_FILES、BRIEF、WORK_ORDER、TASK_REPORT 等改 DSH；移除 choice_page.html、settings.runtime-guard.json、guard_sessions.json |

## 5. 工具移植

**保留（平台中立；其中 5 個有小幅 DSH 適配）**

| 工具 | 用途 |
|---|---|
| `gate_check.py` | 工單／報告／裁決／測試申請格式與互相對照、雜湊、派工紀錄 |
| `scope_check.py` | 比對實際改動與工單 SCOPE／FORBIDDEN |
| `evidence_record.py` | 驗收指令的證據紀錄與重跑 |
| `report_vs_audit.py` | 報告聲明 vs 動作紀錄；**適配**：先剝 DSH 的 PowerShell 包殼、絕對路徑 python、`...` 萬用字元再比 |
| `trace_report.py` | 需求→工單→AC→證據→裁決追溯 |
| `round_check.py` | 修正輪數上限 |
| `status_gen.py` | 狀態頁／狀態檔產生；**適配**：吃 `po_pending`、移除 pending_sends／processes／PO 頁 |
| `metrics_report.py` | PURPOSE 五個數字 |
| `memory_size_check.py` | 指示檔大小；**適配**：預設找最近的 `AGENTS.md`（不再寫死 `~/.claude`）；2.2.2-ds.3 起照上游 2.2.2 多了 `--kind resume` 多檔模式（第 12 節） |
| `resume_archive.py` | 2.2.2-ds.3：RESUME_STATE 舊段落原文搬到 `RESUME_HISTORY_<YYYYMMDD>.md`（上游 2.2.2 原樣） |
| `secret_mask.py` | 機密遮罩 |
| `pause_ctl.py` | 暫停旗標與程序檢查（重資源排程用）；**適配**（2.2.1-ds.1 才真的改；2.2.0-ds.1 寫了但檔案沒動）：說明改成 DSH 沒有 hook、旗標要 worker 自己讀（`pause_ctl.py status` 或 `dsh_guard.py --pause-flag`）、總監審查時核對 |
| `audit_log.py` | hash chain 的 verify／head／cite／recover（append 是 hook 用，DSH 不用） |
| `vocabulary.json` | worker 可填的狀態用詞 |

**新增（dshdw）**

| 工具 | 用途 |
|---|---|
| `dsh_usage.py` | 讀 session 紀錄：每日／每 session 的 input/output/cache tokens、最後 prompt 大小、上下文百分比、effort |
| `dsh_audit.py` | 從 session 紀錄重建動作 audit（相容 `report_vs_audit.py` 與 `audit_log.py` 的 hash chain）；2.2.1-ds.1 起第 1 行 `kind=rebuild`，同上游 `transcript_audit.py` |
| `dsh_doctor.py` | 環境自檢：Python、Node、session 目錄、模型設定、沙箱、git、工具齊全 |
| `dsh_setup_check.py` | DIRECTOR 建置檢查（取代舊 setup_check 的 PO_PAGE_URL 檢查）；2.2.1-ds.1 加上游 2.2.1 的 shadow 檢查與 `--strict` |
| `dsh_guard.py` | 風險指令的**自我提醒**（沒有 hook，不是自動阻擋） |
| `selftest_ds.py` | 這版工具的冒煙測試（不重寫上游 selftest） |

**移除（Claude 專用）**

`hook_guard.py`、`setup_project_settings.py`、`context_probe.py`、`usage_report.py`、`usage_mix.py`、`doctor.py`、`setup_check.py`、`choice_reconcile.py`、`browser_check.py`、`poll_hint.py`、`selftest.py`、`container/`。

## 6. 範本變更

- 新增 `templates/AGENTS_PROJECT_SECTION.md`（原 `CLAUDE_PROJECT_SECTION.md` 的 AGENTS.md 版）。
- `PO_PENDING.md` 改成「待決帳」：保留 ID／STATUS／QUESTION／OPTIONS／RECOMMENDED／IMAGES／SOURCE／ANSWER／RESOLUTION，移除網頁欄位，加註「用 `ask_user_question` 問」。
- `RESUME_STATE.md` 的 `SESSION_ID` 改 `AGENT_NAME`（子代理名稱）。
- `DIRECTOR_FILES.md`：`DIRECTOR_STATE` 去掉 `PO_PAGE_URL`／`PO_PAGE_PINNED`，加 `PENDING_METHOD`；`ACTIVE_WORKSTREAMS` 用子代理名稱；`BASELINE_METRICS` 用 `dsh_usage.py` 欄位；`GUARDS` 列 DSH 機制。
- `BRIEF.md`：開工說明改成開子代理，成本改成 DeepSeek Harness 帳號用量。
- `WORK_ORDER.md`／`TASK_REPORT.md`：MODEL/EFFORT 改新型別，`SESSION_ID` 改 `AGENT_NAME`。
- 移除 `choice_page.html`、`settings.runtime-guard.json`、`guard_sessions.json`。

## 7. 不移植（NOT_PORTED）與替代

| 沒搬過來的東西 | 為什麼 | 替代做法 | 風險 |
|---|---|---|---|
| PreToolUse hooks（hook_guard.py） | DSH 沒有 hook 機制 | 沙箱模式、核准政策、工單 SCOPE、`scope_check`、`dsh_audit`；`dsh_guard.py` 只提醒 | 命令層自動阻擋沒有；只能靠規則與事後檢查 |
| Artifact 私人頁面、置頂、留言叫醒 | DSH 沒有 Artifact | `ask_user_question`＋`PO_PENDING.md`＋聊天附圖 | 沒有常駐待決頁；PO 要在對話中被問 |
| choice 資料庫／收條／冪等 | 依附 Artifact | 本機帳的 open/answered/closed；同一題不重問 | 沒有自動去重與逾時標記 |
| 容器 worker／網路出口管制 | 平台不提供、Claude 版用 claude CLI | 無 | 沒有 OS 級隔離；不要當安全邊界 |
| 專案級外掛開關／plugin token 清單 | DSH 外掛是使用者層 | 只列清單給 PO；不改 | 無法為單一專案關外掛 |
| MEMORY.md 記憶索引 | DSH 沒有 | AGENTS.md 指示鏈＋DIRECTOR 檔案 | 記憶容量受 64 KiB 鏈限制 |
| 壓縮門檻 250000／context_probe | DSH 自動壓縮、視窗 1,048,576 | 用 `dsh_usage.py` 監看上下文 | 沒有專案級壓縮時機控制 |
| 額度重置喚醒 | DeepSeek 帳號沒有 Claude 的 5h／週視窗 | 中斷後恢復程序（docs/06b） | 沒有「額度快用完自動停」機制 |
| interrupt_agent／session 封存 | 本 profile 未掛載 | `send_message` 請 worker 停在安全狀態 | 失控時要 PO 在 GUI 中止 |
| 子代理中途改 effort | DSH 限制 | 開接班子代理 | 多一次交接成本 |
| reviewer 只給讀取工具 | 子代理預設全工具；preset 屬使用者層 | 指示只准讀＋`dsh_audit.py` 核對 | 靠信任與事後檢查 |
| 上游 selftest.py（527 KB） | 大量 Claude 專用測試 | 新寫 `selftest_ds.py` 冒煙測試 | 覆蓋率比上游低 |
| 上游 `transcript_audit.py`（2.2.1） | 它讀 Claude Code 的 transcript（`~/.claude/projects`），DSH 沒有這種檔 | `dsh_audit.py` 本來就從 DSH session 紀錄事後重建；2.2.1-ds.1 起寫同樣的 `kind=rebuild` 第 1 行 | 無新增風險；兩者的 result 雜湊都不能和 hook 紀錄比 |

## 8. 驗證結果

驗證環境（2026-11-12）：DSH 0.2.2-rc.2、模型 deepseek-flash（effort max，子代理 high）、bundled Python 3.12.14、Node 24.21.0、git 2.55.0、sandbox danger-full-access、approval never、Asia/Taipei。

**8.1 端到端 demo（真的派工、交件、裁決，不是只跑工具）**

- 示範專案 `_work/demo-project`（git，master@91d4765843，add/subtract calculator）＋總監檔 `_work/demo-director/DIRECTOR`。
- 工單 `WO-001-add-multiply` rev2（SCOPE 3 檔、AC-1 AUTO、AC-2 REVIEW、Standard 級、CHECKS `python -X utf8 -m unittest -v test_calculator`）：`gate_check --order` OK，`ORDER_SHA256=2650e5b62c1892cf67bba3bda67f9d94aae3ea4016f04b0b37b979d2177a2fa5`。
- 用 `subagent` 開 worker `w1`（cwd=demo-project、effort high），全程只給工單路徑＋RESUME_STATE 路徑＋限制。w1 交件：分支 `demo/w1-multiply`、HEAD `d675820dfc9a27638951cb00ebc22729a37d2fdb`、evidence `20261112T232016-AC-1.json`、TASK REPORT/RESUME_STATE 齊全，並用 `send_message` 回報。
- 總監獨立複核（每項親跑，不採信宣稱）：
  - `gate_check --order` → OK；`--hash` → 2650e5b6…（與 DISPATCH 一致）；`--match`（+evidence-dir+dispatch-log+candidate）→ OK；`--verdict` → OK。
  - `scope_check --order --repo --candidate` → `SCOPE_CHECK: PASS base=91d4765843 changed=3 forbidden=0 outside=0`。
  - `evidence_record verify --rerun` → `EVIDENCE_VERIFY: OK integrity=same test=passed artifacts=2 missing=0 rerun=yes`，並取得 `EVIDENCE_RERUN WO-001 AC-1 candidate=d675820… result=ok record=20261112T232016-AC-1.json`。
  - `dsh_audit build --session w1` → 141 筆 hash-chain 動作紀錄；`dsh_audit verify` → `AUDIT_VERIFY … entries=141 head_seq=141 OK`。
  - `report_vs_audit --report … --log …` → `REPORT_VS_AUDIT: PASS claims=8 ok=8 failed=0`（第一輪 5/8 失敗，暴露工具在 DSH 包殼下的比對缺口，修好後重跑；報告的 RAN 行也依工具限制補正）。
  - 裁決 `reviews/GATE_VERDICT-WO-001.md`：PASS → ACCEPT_AND_CLOSE，DD-03 登記；分支保留、**NO MERGE / NO PUSH / NO FINAL ACCEPTANCE**。
- 這次 demo 同時驗證：待決帳＋`ask_user_question`、DIRECTOR 建置、工單 gate、子代理派工、TASK REPORT/RESUME_STATE、證據重跑、動作紀錄對報告、裁決、決策登記、`dsh_setup_check`。

**8.2 工具鏈**

- `selftest_ds.py` → `SELFTEST_DS: PASS tests=11 pass=11 fail=0 skip=0`（工具 `--help` 全掃、18 個真實 session、最新 log 的 audit build+verify、DSH 包殼／絕對路徑／截斷 claim 的 report 比對、setup fixture、status.py 產生、doctor、guard、gate hash、evidence run+verify）。
- `dsh_doctor.py` → `DSH_DOCTOR: PASS checks=12 ok=12 warn=0 fail=0`（Python、Node、DSH home、session、投影快取、profile 模型/effort、沙箱/核准、git、工具/文件/範本）。
- `dsh_usage.py --session w1` → TURNS 2、INPUT 122.7k、OUTPUT 37.5k、CACHE_R 2.69M、TOTAL 2.85M、LAST 113.4k、CTX% 10.8、EFFORT high、MODEL deepseek-flash；`--project-dir <WS>` 列出 18 個 session（含各研究子代理）。
- `dsh_setup_check.py` 對 demo DIRECTOR → `DSH_SETUP_CHECK: PASS problems=0`。
- `dsh_guard.py --command "git push origin main"` → `REMIND … G02 push …` exit 1；安全指令 exit 0。

**8.3 子代理平台**

- probe：子代理 session 會載入 cwd 的 AGENTS.md；可用 `pwsh`/`read`/`write` 等；子代理可 `send_message` 給總監（實測收到 `PROBE1_TO_LEAD_OK`）；同一 session 可續談（w1 補正 RAN 就是續談）。
- 限制實測：子代理不能 `ask_user_question`（DELEGATED_CALLER）、不能開 schedule；reviewer 無法 per-child 限工具（改用指示＋audit 事後核對）。

**8.4 文件**

- 每輪必讀四份（docs/01+03+06+08）實測 10,947 bytes，預算 11,000。
- demo 實際使用 `templates/WORK_ORDER.md`、`TASK_REPORT.md`、`GATE_VERDICT.md`；`gate_check --verdict` 驗過裁決格式。
- `docs/11`、`BOOTSTRAP`、`docs/04` 的 `dsh_usage`／`dsh_audit` 指令照文件跑得通；實測後修正了 `--project-dir` 的語意（子代理 session 記在總監啟動資料夾，不在 worker repo）與 `RAN` 截斷規則。

## 9. 已知限制

- **每輪必讀預算調高**：上游 docs/01+03+06+08 合計 9,549 bytes（上限 9,550）；dshdw 改寫後實測 **10,947 bytes**（01_roles_authority 2,295＋03_communication 3,281＋06_resume_lossless 1,981＋08_safety_rules 3,390），上限定為 11,000 bytes；2.2.2-ds.3 搬上游 2.2.2 的 RESUME 大小那一句後是 10,964 bytes（06 變 1,998）。這是平台名詞與限制的必要說明，不是新增規則；dshdw 沒有上游 selftest 檢查這個上限，改大時要說明理由並把細節搬去 docs/11。
- 移植版本對應上游：2.2.1-ds.1、2.2.1-ds.2 對應上游 2.2.1（上游 2.2.1 只改工具，沒有改規則文件）；2.2.2-ds.3 對應上游 2.2.2；2.2.3-ds.3、2.2.4-ds.4、2.2.5-ds.5 各對應上游 2.2.3、2.2.4、2.2.5（2.2.5 的逐項搬法見 CHANGELOG 2.2.5-ds.5「上游 DW 2.2.5 移植」）；2.3.0-ds.5 對應上游 2.3.0（DS 的 ds 序號這次不加：沒有新的 DS 試驗修正，只有跟上游和 cwd 檢查）。版本號規則見第 10 節第 5 點；上游之後的規則變更要手動跟（見第 10 節）。
- 用量與動作紀錄依賴 DSH session 檔格式（`session.v4.jsonl.zstd`）；DSH 升版改格式時要更新 `dsh_usage.py`／`dsh_audit.py`。
- 模型只有 deepseek-flash；沒有任何「換更強模型」的選項，只能用 effort 與拆工。
- 章節與範例中的歷史數字（原專案量到的）沿用，換平台後要自己重量。
- `dsh_audit.py` 的 input 經 `secret_mask` 後最多記 500 字，長指令尾端會截斷；TASK REPORT 的 `RAN` 要在截斷處用 `...`，否則 `report_vs_audit` 對不上（這條已寫進 docs/02 與範本）。
- 子代理的 session log 記在總監 session 的啟動資料夾下（`--project-dir <worker repo>` 抓不到）；要抓單一工作線用 `dsh_audit/dsh_usage --session <agent>`（已寫進 docs/11）。
- `dsh_audit.py` 需要 Node 22+（zstd 解壓）；bundled Node 24.21.0 實測可用。

## 10. 跟上游同步

1. 看 `CHANGELOG-upstream.md` 的該版變更，只搬「規則、工單格式、gate、證據、續航、初衷卡」這類平台中立的變更。
2. 平台層（docs/04、05、11、12、BOOTSTRAP 的 DSH 段落、tools/dsh_*.py）以本版為準，不要直接覆蓋。
3. 每次搬完跑 `tools/selftest_ds.py`，並在 `CHANGELOG.md` 記一筆。
4. 發版用 `python -I -X utf8 tools/release.py`（2.2.2-ds.3）：預設只演練（dry run），檢查和 origin/main 的落後／分岔、VERSION 和 CHANGELOG 最上面一段相同且比遠端所有 tag 新、selftest、公開掃描（金鑰、私人 email、私人路徑、DIRECTOR/、_work/、session 檔）；加 `--execute` 才 push、打 tag、建 GitHub Release，每步用 `ls-remote`／`gh release view` 確認。發版仍要 PO 核准。
5. 版本號是 `<上游版本>-ds.<N>`（PO 2026-11-14）：
   - 前面的 `<上游版本>` 跟 DW 原版，搬到哪一版就寫哪一版。
   - `-ds.<N>` 是 dshdw 自己的流水號，**上游換版本也不從 1 重來**。例：v2.2.1-ds.2 之後是 2.2.2-ds.3，不是 2.2.2-ds.1。
   - 2.2.3-ds.3 起（PO 指定版本、總監裁定 WO-DS-005 C）：只有上游版本往上時，ds 序號可以不加，例如 v2.2.2-ds.3 之後是 2.2.3-ds.3。
   - `release.py` 的版本檢查：「(上游版本, ds 序號)」整組要比遠端所有 tag 新，而且 tag 還不存在，否則停下。2.2.3-ds.3 在 v2.2.2-ds.3 之後可以；2.2.2-ds.2、2.2.2-ds.3 都會停。ds 序號不再單獨比較；沒有任何旗標可以跳過這項檢查。
   - 2.2.1-ds.1 以前的 tag（v2.2.0-ds.1、v2.2.1-ds.1）是這條規則訂下前發的，不改。

## 11. ds.2 起 dshdw 自己加嚴的規則（上游沒有）

- 規格先行的 OpenSpec 部分（ds.2～ds.4）：**2.2.5-ds.5 已移除**（PO 2026-11-15「把sdd拿掉」，03:19 更正「該有的安全保護要有」）。理由：WO-DS-008 r2 實測，開 SDD 的隱藏測試 85/107，關 SDD 101/107，OpenSpec 本身沒有量到正確性效益。ds.4 的程式在 tag `v2.2.4-ds.4`。
- 安全閘門（ds.2 起，2.2.5-ds.5 改名，`docs/13_safety_gates.md`、`tools/safety_gate.py`、`director_work.json` 的 `"safety"`）：測試先寫並鎖定（`TESTS_LOCKED`）、計畫閘門（`<WORK_DIR>/<WO>/PLAN.md` + `PLAN_APPROVED`）、Standard 也做規格審查、停止規則 1 輪、AUTO 驗收優先、安全開關不得自行關閉（沒有 PO 答覆 `gate_check --order` 判不過）。同一次試驗量到它們有用（派工段 31 對 29、計畫關 3 對 1、審查關 3 對 2）。
- 其他本版規則：工單大小上限（`order_limits`，`tools/safety_gate.py`）、受保護的測試（`TESTS_LOCKED`、`protected_tests`）、每個 worker 開自己的 git worktree（`dsh_session.py --worker-worktree`，2.2.5-ds.5）、收尾最後一步 `dsh_usage.py --out`（2.2.5-ds.5）。
- 理由：dshdw 的 worker 是 `deepseek-flash`，DSH 沒有 hook、子代理不能中途改 effort，所以工單小、測試鎖住、事後由工具查。跟上游同步時，這幾項以本版為準。

## 12. 上游 2.2.2 移植（2.2.2-ds.3）：逐檔比較

來源：上游 tag `v2.2.2`（`v2.2.2^{}` = db1728b），用 `git show v2.2.2:<檔>` 讀，沒有切上游 checkout 的分支。上游規格是 WO-DW-222 REVISION 5：RESUME_STATE 大小檢查、原文搬移工具，以及從本版 ds.3 移植回去的 `release.py` 和 BASE_REF 檢查。

| 檔案 | 和上游 2.2.2 的關係 | 差異與理由 |
|---|---|---|
| `tools/resume_archive.py` | 原樣搬（逐 byte 相同） | 無差異。它只讀寫 RESUME_STATE 和同資料夾的歷史檔，跟平台無關。 |
| `tools/memory_size_check.py` | 上游 2.2.2 全檔，改 1 處 | 不帶 `--file`／`--glob`／`--workstreams` 時，預設找最近的 `AGENTS.md`；上游找 `~/.claude/projects/.../MEMORY.md`。理由：DSH 每次呼叫載入的是 `AGENTS.md`，這是 2.2.0-ds.1 起本版就有的適配，2.2.2 照留。多檔模式、`--kind resume`、`resume.*` 設定和上游相同。 |
| `tools/gate_check.py` | 搬入上游的 `size_tool`、`resume_size`、`resume_limits_for`（逐字相同）、`--strict`；`base_config` 換成上游版 | `base_ref_problems` 的主體和上游相同，只差說明字串。另有 3 點差異： |
| | | (1) `--repo` 的預設：本版是目前資料夾，上游是工單所在資料夾。理由：本版的 `--repo` 也是找受保護測試的專案資料夾（ds.2～ds.4 另外用來找規格資料夾），兩種用途要指向同一個 checkout。 |
| | | (2) `--config` 同時是 `order_limits`／`protected_tests`、`base_ref` 和 `--resume` 的設定檔；上游只用於後兩者。理由：本版從 ds.2 起就有 `--config`。 |
| | | (3) 有兩處改成和上游一樣，舊行為因此改變：BASE_REF 沒寫 commit 時，從印 note 改成不印（上游的理由：舊工單的輸出不變）；`base_ref` 開關不是 true／false 時，從靜默忽略改成印 note 並用預設值。舊做法的毛病：字串 `"false"` 會被當成真值。設定檔也從只找工單上一層，改成先找工單資料夾、再找上一層。 |
| `tools/release.py` | 本版 ds.3 是來源，上游 2.2.2 是移植版 | 兩邊的規則一致：版本從 HEAD 讀、工作樹有沒 commit 的改動就停（演練也停）、`-<label>.N` 只能往上加。這次從上游搬回 3 點：`main(argv=None)`（測試可在同一個程序裡跑）、BOM 寫成 `"﻿"`、公開掃描多擋 `CLAUDE.local.md`／`.claude/settings.local.json`／Claude session 紀錄（本 repo 也會被 Claude Code session 編輯）。留著不同、而且有理由的：預設 title／tag_message／selftest 指令（`tools/selftest_ds.py`）；私人路徑多擋 `_work/`、`AGENTS.local.md`、DSH session 檔；工作樹檢查用 `git diff --name-only HEAD`（上游用 `git status --porcelain`），兩者對 modified／staged 的判定相同；停下時的說明文字不同：本版在 VERSION 也沒 commit 時印 HEAD 的版本，上游印工作樹和 HEAD 兩邊的版本。 |
| `tools/dsh_setup_check.py` | 對應上游 `setup_check.py`，本版自己的檢查檔 | 搬入上游 2.2.2 新增的 3 項：RESUME_STATE 大小（shadow）、`resume`／`base_ref`／`release` 區塊型別、未知鍵只印 note（例如 `keep_days`）。另外把 `sdd`、`resume`、`base_ref`、`release` 加進已知鍵；以前這幾個會被誤報成「keys no tool reads」。 |
| `director_work.example.json` | 加 `resume` 區塊（值和上游相同） | 本版用 `_comment_*` 分段說明，不像上游寫成一個 `_comment`。另有本版自己的 `order_limits`／`protected_tests` 區塊（2.2.5-ds.5 拿掉 `sdd`）；`release` 的 title／selftest 是本版的值。 |
| `docs/06_resume_lossless.md` | 只搬上游改的那一句 | gate_check 那一行加「和大小（超過照 docs/06b 把舊紀錄原文搬走，近期不動）」；恢復段刪「（包括 PO 手動停止後再繼續）」（目標行已含 PO 手動停止）。每輪必讀 10,947 → 10,964 bytes（上限 11,000），比上游多 17 bytes，因為本版的「機制」那一行內容不同，沒法照上游縮。 |
| `docs/06b_on_demand_procedures.md` | 加巡查第 4 步和「RESUME_STATE 瘦身」一節 | 內容同上游。DSH 用語：巡查叫工作線瘦身用 `send_message`；多寫一句「DSH 每一步都重送整段對話」說明為什麼大小很重要，並註明 `dsh_setup_check.py` 也會印。 |
| `docs/02_work_orders_gates.md` | 加「發版」一節（上游 2.2.2 新增） | 多寫 `-ds.N` 規則（指向第 10 節），以及掃描會擋 `_work/`。BASE_REF 那一行 ds.3 已經有了，和上游同義。 |
| `templates/RESUME_STATE.md` | 加 1 行註解 | 指向 `docs/06b`（細節在那裡）；上游指向 `docs/06`。 |
| `templates/WORK_ORDER.md` | 不動 | BASE_REF 的註解 ds.3 已經改過，和上游同義。 |
| `tools/selftest_ds.py` | 不是上游 `selftest.py`（本版不搬上游 selftest，見第 7 節） | 把上游 `test_resume_size_222`／`test_resume_archive_222` 的案例改寫成 `resume_size`、`resume_archive` 兩項，固定資料和突變（mutation）相同。`setup_shadow` 加 6 個 shadow 案例和 2 個 note；`release_scan` 加 Claude 本機設定檔案例；`base_ref_fresh` 加「開關型別錯」案例。上游 `test_release_222`／`test_base_ref_222` 的內容，本版 ds.3 的 `release_*`、`base_ref_fresh` 早就有。 |
| `tools/README.md`、`tools/DSH-TOOLS.md`、`CHANGELOG*.md` | 本版自己的寫法 | 照本版格式補上述工具的說明；`CHANGELOG-upstream.md` 附上游 2.2.2 那一段（原文）。 |

沒搬的：無。上游 2.2.2 的每項變更都在上表。

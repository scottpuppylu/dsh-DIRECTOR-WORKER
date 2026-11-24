# CHANGELOG — dsh-DIRECTOR-WORKER

本 repo 是 [DIRECTOR-WORK](https://github.com/scottpuppylu/DIRECTOR-WORK) v2.2.2（Claude Code／Claude Desktop 版，MIT）的移植。
上游的完整變更歷史保留在 [`CHANGELOG-upstream.md`](CHANGELOG-upstream.md)；本檔只記 dsh-DIRECTOR-WORKER（簡稱 dshdw；舊名 DIRECTOR-WORK DeepSeek 版（DW-DS））自己的變更。

## 2.6.0-ds.7（2026-11-24）

本版集中修復交接研究階段發現的所有工具、文件與環境缺陷（A1～A10、B2 與 CI 補齊），確保「閘門真的會擋」在乾淨 worktree、不完整 E2E、Token 統計、worktree ignore、session 稽核與環境健檢上全面落實。

### 閘門與範圍檢查（A3、A4）
- **A3 `scope_check.py --candidate` 與 `safety_gate.py`**：即使工作樹停在 `base` 且完全乾淨，`scope_check.py --candidate <SHA>` 仍會對 `since..candidate` 差異執行 `FORBIDDEN`／`OUTSIDE`／`PROTECTED` 掃描；`gate_check.py --match --candidate <SHA>` 同步把 `candidate` 傳入 `safety_gate.order_problems`，以 candidate commit 的 blob 雜湊驗證 `TESTS_LOCKED`。
- **A4 `gate_check.py --final` 驗證 E2E 真正完成**：不再只看 `evidence/E2E/` 有無非空檔；要求明確成功結束證據（`EXIT_CODE: 0` 或 `RESULT: PASS`），捕捉非零結束碼與 `Traceback`/失敗標記；未完成時報 `E2E_INCOMPLETE`（僅在 PO 明確接受時以 `--allow-incomplete-e2e` 降級為 WARN，非零 exit 或失敗標記仍 FAIL）；新增 `--final --candidate <40 位 SHA>` 核對 `CANDIDATE_HEAD:`／`COMMIT:`，並對 `partial` 的 `usage.json` 輸出 `~ WARN USAGE`。

### 用量、稽核與環境工具（A1、A2、A5～A9、B2）
- **A1 / A2 / A8 `dsh_usage.py`**：
  - `lastPromptTokens` 修正為僅計入 prompt 側（`input + cacheRead + cacheWrite`），移除誤併入的 `outputTokens`，與 DSH `contextPressure.pressureTokens` 一致（實測 120 份本機投影全數 0 誤差）。
  - `--from-jsonl` 改為即使存在 projection cache 也實際重算 JSONL totals 與最後一請求 prompt tokens（並補齊 `sandbox`／`approval`／`surfaceTokens`），支援 `llm/retry-started` 與 `(turn, step, attempt)` slot 覆寫。
  - 新增 `read_number()`／`read_usage()` 攔截非數值、bool、負數或非有限浮點欄位，紀錄警告並標記 `partial: true`。
- **A5 / B2 `dsh_session.py` & `dsh_audit.py`**：
  - `_DECODER` 改由 `stdin` JSON 傳遞檔案路徑清單（避免 Windows 命令列長度上限），`header` 模式優先只讀前 8 KB 前綴並在需要時回退全檔（實測 121 份真實 header 僅約 0.15 秒）。
  - `selected_sessions()` 修正為 root session 先於 subagent（確保無 projcache 時先收集 `subagent/catalog` 命名），並先依 projcache／batch header 預過濾 `--project-dir`／`--since`／`--until`／`--session`，再僅對命中 session 全檔解壓（單一 session 重建從 ~24.7 秒降至 1 秒內，且不再對無關損壞或空 log 印誤警）。
- **A6 `dsh_audit.py reads`**：支援多段前導語句（`$env:...`、`Set-Location`、`cd`、`cmd /c`、`pwsh -c`）、Windows 路徑與反斜線（`posix=False`）、`Get-Content`/`gc` 的 `-Path`/`-LiteralPath`/`-TotalCount`/`-Encoding` 等參數，並在引號無法解析時累加 `"unparsed"` 計數。
- **A7 `bootstrap_repo.py`**：改用 `git rev-parse --git-path info/exclude`（並附 `commondir` 後援），於 linked git worktree 執行時正確寫入主 repo 共用 `info/exclude`，不再漏抓 `.memsearch/`。
- **A9 & `dsh_doctor.py` / `dsh_setup_check.py`**：`dsh_session.py` 與 `dsh_doctor.py` 實測檢查 Node ≥ 22 與 `zlib.zstdDecompressSync`（保留 `DSH_NODE` 嚴格覆寫語意）；`dsh_doctor.py` 更新 `REQUIRED_TOOLS` 至 42 項、只從 `- id: agent-default-model` 區塊讀預設模型與 effort，並對 `danger-full-access + never` 補上未受限提示；`dsh_setup_check.py` 納入並驗證 `loop_guard`；`dsh_guard.py`、`dsh_setup_check.py`、`verify_dsh_run.py` 將 `sys.stdout.reconfigure(encoding="utf-8")` 移至 `parse_args` 之前。

### 文件對齊、CI 與驗證（A10）
- **A10 文件與指引修正**：統一 `docs/11_dsh_operations.md`、`templates/WORK_ORDER.md`、`README.md`、`DEEPSEEK-PORT.md` 與 `docs/08_safety_rules.md` 對「預設 `--worker-worktree` 獨立 git worktree、僅在宣告時退回 `--shared`」的說明；`docs/11` 新增「提示詞規則 vs 工具檢查 vs 硬防護」對照表；修補 `BOOTSTRAP.md`（納入 `docs/13_safety_gates.md`、修正 `DIRECTOR/research/`、移除過時寫法並指向 `ran_line.py` 與 `gate_check.py --final`）；更新 `tools/DSH-TOOLS.md`；精簡 `docs/06_resume_lossless.md` 與 `docs/08_safety_rules.md`，使 4 份每輪必讀文件總計 10,276 bytes LF（低於 11,000 bytes 上限）。
- **CI 與測試**：新增 `.gitattributes` 與 `.github/workflows/ci.yml`（Windows + Ubuntu Python 3.9/3.12 + Node 24）；更新 `selftest_ds.py` 中 CI 安全測試與 E2E fixture，並新增 7 項 `2.6.0-ds.7` 回歸測試（`tests=115`）。

## 2.6.0-ds.6（2026-11-22）

跟上上游 DW 2.6.0（分支 `claude/dw-v260`，本機 commit 787f67b）。上游 2.6.0 的兩個新工具和三個工具的新選項都是自己執行、只讀，不靠 hook，所以五支工具原樣搬（和上游逐位元組相同，換行 LF）。ds 序號不加：這一版沒有新的 DSH 試驗修正。安全閘門全部保留，不加回 OpenSpec／SDD。每輪必讀（指示鏈）沒有變大。上游原文見 `CHANGELOG-upstream.md`。

### 遷移（從 2.5.0-ds.6 升上來要注意的）
- 不用改任何東西：新工具都要自己執行。舊的 `pre_tr`、`pack_check` 設定和 manifest 照樣通過。
- 讀最後一行的腳本注意：`pack_check.py` 最後一行結尾多 `unique=n`，`pre_tr.py` 最後一行結尾多 `inputs_bad=n`。
- `templates/TEST_REQUEST.md` 多一行 `CODE_REFS:`；有照抄這份範本的，要自己再抄一次。

### 上游 2.6.0 各項怎麼處理
| 上游 | 處理 | dshdw 的檔案 |
|---|---|---|
| N1、N5 `ruler_check.py` | 原樣搬 | `tools/ruler_check.py`、`docs/07` |
| N2 `run_plan_check.py`＋TEST_REQUEST `CODE_REFS:` | 原樣搬 | `tools/run_plan_check.py`、`templates/TEST_REQUEST.md`、`docs/07` |
| N3 `pre_tr.py` 的 `inputs` | 原樣搬；鎖檔一句改成「只看這個 DSH session 自己起的程序樹」 | `tools/pre_tr.py`、`docs/06b` |
| N4 `pack_check.py` 的 `unique=`、`required_segments` | 原樣搬 | `tools/pack_check.py`、`docs/07` |
| N6 `waiver.py` 多線、`--to` | 原樣搬 | `tools/waiver.py`、`docs/04` |
| docs/04 放行條件數字化、收尾一次寫豁免 | 改寫：dshdw 沒有 98%／99% 停工線，寫進「停工線與用量重置」一節，用量照 DSH 帳號頁，讀不到判 UNKNOWN 不放行 | `docs/04` |
| docs/07 模擬時鐘 | 原樣搬 | `docs/07` |
| docs/10 第 127～134 條 | 原樣搬；不放進 agent instructions | `docs/10` |
| CHANGELOG／VERSION／README | 本段、`VERSION`、README 新節；`CHANGELOG-upstream.md` 補上游 2.6.0 原文 | `CHANGELOG.md`、`CHANGELOG-upstream.md`、`VERSION`、`README.md` |

### 已知限制
- `ruler_check.py` 只看你給的正規式、glob 和截斷計數鍵；量尺選錯欄位它看不出來，只保證「0 筆、太少、對不上實際的一行、截斷」不會被當成結果。
- `run_plan_check.py` 只查計畫寫的 `path:line` 在 commit 裡存在、log 有沒有印出計畫的參數；程式位置寫錯行但檔案有那麼多行，它看不出來。
- 表現層用模擬時鐘（docs/07）是文件規則，沒有工具自動檢查。

### 驗證
- `selftest_ds.py`：2.5.0-ds.6 是 101 項，這一版 108 項；結果見本版 commit 前的實跑。
- 五支工具和上游 2.6.0 逐位元組相同（去掉 CR 後比 SHA-256）。

## 2.5.0-ds.6（2026-11-16）

WO-DS-013。跟上上游 DW 2.5.0（tag v2.5.0，decab48）。上游 2.5.0 的新檢查本來就是自己執行、預設只提醒，不靠 hook，所以多半原樣搬；要改寫的只有讀紀錄的兩項（loops 的時間範圍、最常重讀的檔案），因為 dshdw 讀的是 DSH 的 `session.v4.jsonl.zstd` 事件，不是 Claude 的 transcript。ds 序號不加：這一版沒有新的 DSH 試驗修正。安全閘門全部保留，不加回 OpenSpec／SDD。每輪必讀（指示鏈）沒有變大。上游原文見 `CHANGELOG-upstream.md`。

### 遷移（從 2.4.0-ds.6 升上來要注意的）
- 不用改任何東西：新檢查都要自己執行，預設只提醒（`--strict` 才會 exit 1）。
- **`dsh_audit.py loops --since／--until` 的算法變了**（F1）：以前照 session 開始時間挑整個 session，現在每個呼叫照自己的時間，只算 [since, until) 裡的呼叫（`--until` 那天整天都算）。所以前一天開、今天還在跑的 session 會算進「今天」，跑過 `--until` 的 session 只算範圍內那一段；同一個範圍的數字可能和 2.4.0-ds.6 不同。`--events` 檔也照呼叫時間過濾。`dsh_usage.py --loops` 的 LOOPS 行跟著變；`build`、`inject` 和 `dsh_usage.py` 的主表不變，仍照 session 開始時間。
- 要用 effort 檢查，就在 DIRECTOR_LOG 的 DISPATCH 行尾加 `| class=<類別> effort=<off|low|high|max> model=deepseek-flash`；舊的 DISPATCH 行 `gate_check.py` 照樣認得，只是 `dispatch_check.py --log` 會提醒。`templates/DIRECTOR_FILES.md` 的範例行已經加上。
- `templates/.pre-commit-config.yaml` 多一個 `dshdw-conflict-markers` hook（pre-commit 內建的 pygrep，不下載）；有照抄這份範例的，要自己再抄一次。
- 上層 `README.md` 加「2.5.0-ds.6 新增的小幫手（選用）」一節，檔案地圖、防護表、已知限制跟著補；最上面的提示詞沒有改（逐位元組相同）。

### 已知限制
- `dsh_audit.py reads` 不給每個檔案的成本：DSH 的 token 用量記在每一步模型回應（`assistant/message` 的 `usage`）上，不在每個工具呼叫上，所以上游的「加權成本」在這裡是 NOT_VERIFIED，只給次數和讀回來的 bytes。它只認得 DSH 的 `read` 工具和 pwsh／bash 的 `cat`、`head`、`tail`、`sed -n`、`Get-Content`；用 `run_code` 或腳本讀的檔不算。會印檔案路徑，只在本機看。
- 只有 `loops` 和 `reads` 照每個呼叫的時間；`build`、`inject` 和 `dsh_usage.py` 的主表仍照 session 開始時間（`dsh_usage.py` 的主表讀投影快取，沒有每個呼叫的時間）。
- `dispatch_check.py` 的 effort 只認 DSH 的 `off / low / high / max`。上游表裡 `xhigh` 的類別在這裡是 `high` 或 `max`，`routine` 是 `low` 或 `high`，另外多一個 `mechanical`（`off` 或 `low`）；這是照 `docs/05` 的判斷原則換算的，沒有 DSH 試跑驗證過哪個等級最省（NOT_VERIFIED）。
- `dispatch_check.py --dup` 只比字詞：同一件事換了說法比不出來，不同的事用了相同的詞會誤報。它是「先去看一下」的提醒，不是判定。
- `delete_guard.py` 只找完整路徑和檔名照字面出現的地方；用萬用字元、變數組出來的路徑找不到。沒給 `--repo` 也沒有 `--refs` 對到檔案時印 WARN（等於沒查）。
- N6、N7 是文件和範本，沒有工具自動檢查填寫內容。
- README 新增的 1 張 mermaid 圖（共 14 張）只用 `readme_236` 的規則檢查語法，本機沒有畫出來（NOT_VERIFIED），推送後看 GitHub 頁面。

### 上游 2.5.0 各項怎麼處理（總監裁決，WO-DS-013 第 0 節）
| 上游 | 處理 | dshdw 的檔案 |
|---|---|---|
| F1 LOOPS 照 `--until` | 改寫：`dsh_audit.py loops` 每個呼叫照自己的時間只算 [since, until)；挑 session 時只跳過 `--until` 之後才開的 | `tools/dsh_audit.py`、`tools/dsh_usage.py`（說明） |
| F2 RESTART NOT_ENOUGH_DATA | 不搬：dshdw 沒有 RESTART／損益兩平統計 | — |
| F3 `either_quoting` | 搬（selftest helper） | `tools/selftest_ds.py` |
| N1 `dispatch_check.py --log` | 搬工具；難度表換成 DSH 的 effort（`off / low / high / max`），加 `mechanical` 類 | `tools/dispatch_check.py`、`docs/05`、`templates/DIRECTOR_FILES.md` |
| N2 `round_check.py` 獨立診斷 | 原樣搬；「不同模型」寫成另開的子代理 session、別的 DeepSeek 模型或人 | `tools/round_check.py`、`docs/07` |
| N3 `delete_guard.py` | 原樣搬 | `tools/delete_guard.py`、`docs/06b` |
| N4 `dispatch_check.py --dup` | 原樣搬 | `tools/dispatch_check.py`、`docs/05` |
| N5 `usage_mix.py --reads` | 改寫成 `dsh_audit.py reads`：讀 DSH 事件，DSH 的讀檔工具與參數；成本 NOT_VERIFIED，只給次數和 bytes | `tools/dsh_audit.py` |
| N6 `GATE_FEASIBILITY.md` | 原樣搬 | `templates/GATE_FEASIBILITY.md`、`docs/07` |
| N7 `SETTINGS_MANIFEST.md` | 原樣搬 | `templates/SETTINGS_MANIFEST.md`、`docs/07` |
| N8 程序衛生＋pre-commit 範例 | 搬；「停背景工作看整棵程序樹」改成「只停這個 DSH session 自己起的程序樹」；hook 名 `dshdw-conflict-markers` | `docs/06b`、`templates/.pre-commit-config.yaml` |
| N9 docs/10 第 82～126 條 | 原樣搬（hook 名、effort、程序樹用 DSH 的說法）；不放進 agent instructions | `docs/10` |
| N10 CHANGELOG／VERSION／README | 本段、`VERSION`、README 新節；`CHANGELOG-upstream.md` 補上游 2.5.0 原文 | `CHANGELOG.md`、`CHANGELOG-upstream.md`、`VERSION`、`README.md` |

### README
- 啟動提示詞沒有改（逐位元組相同；提示詞裡沒有版本號）。
- 新增「2.5.0-ds.6 新增的小幫手（選用）」：工具表（7 列、3 欄，手機上不擠）、怎麼用（4 行命令）、DISPATCH 行的寫法和 `reads` 只在本機看的說明、1 張圖（刪檔之前的五步）；照上游 README 2.5.0 段改寫成 dshdw 的工具名和 effort。
- 檔案地圖（docs/05、06b、07、templates、tools）、防護表（`dispatch_check`、`delete_guard`）、已知限制跟著更新。

### Credits（借用的概念；都沒有複製程式碼；沿用上游 2.5.0 的 Credits，2026-11-16 上游查）
| 來源 | 授權 | 借了什麼 |
|---|---|---|
| Claude Code 官方文件〈Model configuration〉〈Subagents〉 | 文件 | 依難度選 effort、max 只暫時用；子代理各自設模型與 effort，獨立診斷用唯讀代理（N1、N2，經上游；dshdw 換成 DSH 的等級） |
| Google SRE book〈Eliminating Toil〉 | CC BY-NC-ND 4.0 | 找出重複、沒有長久價值的工作：重讀路徑、重複派工（N4、N5，經上游） |
| Google SRE book〈Postmortem Culture〉 | CC BY-NC-ND 4.0 | 根因由別人審查、每條教訓要有後續行動（N2、N9，經上游） |
| Google SRE workbook〈Canarying Releases〉 | CC BY-NC-ND 4.0 | 指標要能歸因於變更本身、用注入的錯誤證明指標抓得到壞變更（N6、N8，經上游） |
| git 文件〈gitattributes〉〈git-grep〉 | GPL-2.0（文件隨 git 發布） | 換行屬性（N8）；`-F` 固定字串只搜追蹤檔（N3，經上游） |
| Google Cloud Storage〈Soft delete〉 | CC BY 4.0 | 刪除先保留一段可復原期，再真刪（N3，經上游） |
| pre-commit | MIT | `pygrep` 本機 hook 的設定格式（N8，dshdw 不依賴） |

### 驗證
- `selftest_ds.py`：2.4.0-ds.6 是 90 項，這一版 101 項；Python 3.11 和 3.9 各跑一次，都是 101/101、skip=0。
  - 新增 11 項：`loops_until_250`（一個跨兩天的 session：第 1 天 repeat=1、第 2 天 2、兩天和不給範圍都是 3、最後一天之後 0；`by_calls` 挑 session；2 個 mutation，上一版的程式在第 1 天就會算錯）、`quoting_either_250`、`dispatch_effort_250`（DSH 等級、上游的 `xhigh`／`medium` 算不認得、`--table`、`--strict`、exit 2；2 個 mutation）、`dispatch_dup_250`（NEXT_STEP 和 commit 標題、中文兩字一組、門檻；1 個 mutation）、`round_diagnosis_250`（第 3 組沒寫、寫成實作者本人、有寫就安靜、第 2 組還不用；1 個 mutation）、`delete_guard_250`（有引用／沒引用、只印檔名和行號、從不刪、檔案自己不算；1 個 mutation）、`reads_250`（合成 DSH 事件、fork 副本只算一次、成本 NOT_VERIFIED、輸出沒有真實路徑；2 個 mutation）、`gate_feasibility_250`、`settings_manifest_250`、`process_hygiene_250`（上游 2.5.0 的測試）、`lessons_intake_250`（docs/10 編號連續、47 個收件匣編號各一條規則、AGENTS 段落不載入 docs/10）。
  - 安全閘門的 11 項函式內容和 2.4.0-ds.6 逐字相同，都通過；`safety_gate.py` 和 `safety` 區塊沒改。
- `test_verify_dsh_run.py`（Python 3.11、3.9）。
- 指示鏈（`memory_size_check.py --chain`，AGENTS 段落＋每輪必讀 docs/01、03、06、08，LF）：14,189 bytes，和 2.4.0-ds.6 相同（這些檔都沒改），上限 65,536。docs/10 變大（25,488 → 36,394 bytes，CRLF）但不在指示鏈裡。
- fixture 全是合成資料，沒有真實紀錄的內容和真實路徑。

## 2.4.0-ds.6（2026-11-15）

WO-DS-012。跟上上游 DW 2.4.0（tag v2.4.0，df8ddfd）。上游 2.4.0 新增的小幫手多半是 Claude Code hook（PreToolUse、PostToolUse、SessionStart）；**DSH 一個 hook 都沒有**，所以這一版把它們全部改成事後檢查，或由 agent 照規則在恢復時自己跑一次。ds 序號不加：這一版沒有新的 DSH 試驗修正。安全閘門全部保留，不加回 OpenSpec／SDD。上游原文見 `CHANGELOG-upstream.md` 和上游 repo。

### 遷移（從 2.3.0-ds.6 升上來要注意的）
- **`dsh_audit.py loops` 的輸出格式變了**（`LOOPS_VERSION = 2`，JSON 的 `version` = 2）。每行改成上游 `loop_guard` 的樣子：`LOOP <類別> tool=T args=<雜湊> count=N calls=A..B reminders=K session= agent= at=<時間>`，後面依類別多 `window= total=`、`result= no_text_between`、`result=`、`reason=`、`result= last_call`，行尾照舊可能有 `copies=N`。有程式解析 2.3.0-ds.6 那種 `LOOP <類別> session= agent= call= at= tool= key=` 行的，要跟著改。
- **`bad_args` 的判法照上游**：同一個工具在 20 次呼叫內被拒 2 次以上才算一筆（2.3.0-ds.6 是每一次被拒都算一筆）。`BAD_ARGS` 那一行不變，照舊列全部被拒的次數、比例、前 5 名。
- **`child_error_unhandled` 會查了**：session 的最後一個呼叫是失敗的子代理呼叫（`subagent`、`wait_agent`）就算一筆。輸入裡有子代理呼叫的結果時，JSON 的 `not_verified` 是 `[]`；完全沒有時才是 `["child_error_unhandled"]`。只認得舊值的讀法要改。
- 新參數：`--config FILE`（上游 `loop_guard` 的設定檔格式，含 `allow`）、`--retry-errors`、`--ping-pong`、`--bad-args`。`--rounds R` 照舊可用，等於 `--ping-pong 2R`（預設 6 次＝3 輪，和以前一樣）。數值都要 ≥ 2，不合法印 NOT_RUN（exit 2）。
- `loops` 最後多一行 `LOOPS repeat=n retry_same_error=n ping_pong=n poll_no_progress=n bad_args=n child_error_unhandled=n|NOT_VERIFIED calls=n sessions=n`，在 `DSH_LOOPS` 之前。
- `status_gen.py` 的 `LOOPS` 行只列不是 0 的類別（加 `child_error_unhandled=NOT_VERIFIED`）：整行太長會被中間截斷。
- **AGENTS.md 的總監段落多一行**（`templates/AGENTS_PROJECT_SECTION.md`）：「DSH 自動壓縮或任何中斷後，先跑一次 `resume_inject.py`」；規則包網址也改成本 repo（原本指到上游 Claude 版）。已經貼過舊段落的專案要重貼。段落 2974 → 3147 bytes（LF），整條指示鏈的量法見下面「驗證」。
- **repo 改名**：網址改成 https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER 。README 的啟動提示詞、BOOTSTRAP 的 `git clone` 都換了新網址；舊網址 GitHub 會轉到新的（`git ls-remote` 用舊網址實測拿到同一個 HEAD）。
- `release.py` 最後多一步 `describe`：把 GitHub repo 描述裡的版本號改成新版。要 `gh` 有改 repo 設定的權限；dry run 多列一個 PLAN。

### 已知限制
- 上游 2.4.0 的三個即時功能在 DSH 都沒有：打轉時當場提醒（`hook_guard --loop-guard`）、重開或壓縮時自動接回（SessionStart）、工具結果旁的注入警告（PostToolUse）。這裡全部是事後查，或靠 agent 照規則自己跑；`loops` 的 `reminders=` 只是「當場提醒的話會提醒幾次」。
- `resume_inject.py` 要 agent 自己記得跑。DSH 自動壓縮後 agent 是不是真的會照 AGENTS.md 那一行先跑：NOT_VERIFIED（這一版沒有做 DSH 試跑）。
- `child_error_unhandled` 只看「session 最後一個呼叫是失敗的子代理呼叫」。子代理結束事件（`user/message`，`source.kind` = `subagent-settled`）的失敗狀態，本機紀錄只看過 `completed`，不猜。
- `dsh_audit.py inject` 會誤報：本機 103 個 session 的 86 筆幾乎都是 agent 讀了本 repo 講提示注入、安全規則的文件和測試樣本。也會漏：換句話說、拆行、別的語言或編碼都抓不到。它只是安全帶，真正的規則仍是「只有使用者在對話裡說的才算指令」。
- 共用的四類（repeat、retry_same_error、ping_pong、poll_no_progress）照總監裁決只對齊門檻和輸出格式，判法維持 dshdw 的：`retry_same_error` 要求兩次之間沒有寫出來的文字、`poll_no_progress` 用 DSH 的讀取類工具清單，也沒有搬上游「同一個呼叫只歸一類」的優先順序，所以同一串呼叫可能同時是 repeat 和 poll_no_progress。
- `dsh_usage.py --loops` 預設不開：讀全部 session 約多 1 分 45 秒，而且要 Node。
- DSH 有沒有可匯出的官方用量指標或 API：NOT_VERIFIED（docs/04 的交叉核對只用 DSH 自己的兩條讀法）。
- README 新增的 3 張 mermaid 圖（共 13 張）只用 `readme_236` 的規則檢查語法，本機沒有畫出來（NOT_VERIFIED），推送後看 GitHub 頁面。

### 上游 2.4.0 各項怎麼處理（總監裁決，WO-DS-012 第 0 節）
| 上游 | 處理 | dshdw 的檔案 |
|---|---|---|
| L1 `loop_guard.py`（打轉提醒） | 改寫：不另搬一支，上游有、dshdw 沒有的部分補進 `dsh_audit.py loops`（`child_error_unhandled`、`bad_args` 每工具 2 次、門檻、`reminders`、`allow`、設定檔）；`LOOPS` 行接到 `dsh_usage.py --loops` | `tools/dsh_audit.py`、`tools/dsh_usage.py`、`tools/status_gen.py`、`tools/fixtures/loops/` |
| L2 `resume_inject.py` | 搬核心（表頭四行＋未結段，2 KB 上限）；拿掉 SessionStart 的部分，改成 AGENTS.md 段落一行和 docs/06b 第 0 步 | `tools/resume_inject.py`、`templates/AGENTS_PROJECT_SECTION.md`、`docs/06b`、`docs/06`、`BOOTSTRAP.md` |
| L3 `inject_scan.py` | 只搬 `scan FILE` 和 `scan_text()`；新增 `dsh_audit.py inject` 掃 DSH 紀錄裡的工具輸出；不印比對到的文字 | `tools/inject_scan.py`、`tools/dsh_audit.py` |
| L4 skills | 不搬（上游也不採用） | — |
| L5 完成前驗證、系統化除錯、請人審查 | 搬，加 DSH 的說明（沒有 hook 會擋） | `docs/07` 第 8 節 |
| L6 停止規則的對照 | 已搬（2.3.0-ds.5 已有 `round_check` 的條件表） | — |
| L7 hook 在 subagent 的限制 | 改寫成原則：dshdw 全靠事後檢查，子代理一樣 | `docs/06b` |
| L8 pre-commit／gitleaks 範例 | 搬，改成 dshdw 的字樣 | `templates/.pre-commit-config.yaml`、`templates/.gitleaks.toml` |
| L9 用量交叉核對 | 改寫：用 DSH 自己的來源（投影快取對事件紀錄），官方指標 NOT_VERIFIED | `docs/04` |
| L10 `completion.py` 的 `depends_on` | 搬（`completion.py`、`secret_mask.py` 原樣） | `tools/completion.py`、`tools/secret_mask.py` |
| L12 規格審查的說法 | 搬上游的更正；dshdw 同一句錯話一起改（docs/02 兩處、docs/12 兩處、`templates/SPEC_REVIEW.md`、README 的 Standard 列「規格審查選用」），加 selftest 擋住 | `docs/02`、`docs/12`、`templates/SPEC_REVIEW.md`、`README.md`、`tools/selftest_ds.py` |

### README
- 啟動提示詞只換 repo 網址，其他逐位元組不變（2,332 → 2,329 bytes；`readme_236` 的固定 hash 一起換）。
- 圖 2（git 怎麼走）和圖 3（DSH 只會事後查）改成由上往下（TD），在 GitHub 上不會被擠小。
- 新增「2.4.0-ds.6 新增的事後檢查（選用）」：工具表、怎麼用、3 張圖（打轉怎麼被查到、中斷或壓縮後先看重點、提示注入警告），照上游 README 2.4.0 段改寫成事後檢查的版本。
- 打轉偵測段、Claude 版對照表、防護表、已知限制、檔案地圖跟著更新；Standard 的規格審查列改正。

### Credits（借用的概念；都沒有複製程式碼。2.3.0-ds.6 的 Credits 見下方該段）
| 專案 | 授權 | 借了什麼 |
|---|---|---|
| claude-flow（tool-loop guardrail） | MIT | 對工具和參數雜湊、到門檻提醒（L1，經上游 2.4.0） |
| pydantic-deepagents（stuck-loop 文件） | MIT | 同工具同參數 3 次為預設門檻（L1，經上游） |
| ralph-claude-code | MIT | 提醒間隔加倍（`reminders` 的算法，L1，經上游） |
| OpenClaw loop detection 文件 | 授權 NOT_VERIFIED，只讀了概念說明 | repeat／poll_no_progress／ping_pong 的分類（L1） |
| thepushkarp/handoff、kylesnowschwartz/claude-handoff | MIT | 壓縮或重開後把交接狀態放回 context（L2，經上游） |
| lasso-security/claude-hooks | MIT | 只警告的提示注入掃描與分類（L3，經上游） |
| obra/superpowers | MIT | verification-before-completion、systematic-debugging、requesting-code-review（L5，經上游） |
| pre-commit、gitleaks | MIT | 範例設定的格式（L8，dshdw 不依賴） |
| steveyegge/beads | MIT | 任務依賴與 ready 清單（L10，經上游） |

### 驗證
- `selftest_ds.py`：2.3.0-ds.6 是 81 項，這一版 90 項；Python 3.11 和 3.9 各跑一次，都是 90/90、skip=0。
  - 新增 9 項：`loops_dw_240`（上游 2.4.0 的判法：bad_args 每工具 2 次、child_error_unhandled 正反例、`allow` 與 `max`、`reminders`、`--config` 與錯誤設定、`--rounds` 換算；6 個 mutation）、`loops_usage_240`（`LOOPS` 行、`dsh_usage.py --loops` 預設關、讀不到印 NOT_RUN；1 個 mutation）、`inject_scan_240`（上游樣本的正反例；`scan` 和 `dsh_audit.py inject` 的一般輸出與 `--json` 都不含比對到的文字和假金鑰；fork 副本只算一次；沒有 hook 指令；3 個 mutation）、`resume_inject_240`（表頭＋未結、2048 bytes 截斷並註明、沒有未結段、檔案不在；2 個 mutation）、`completion_deps_240`、`precommit_samples_240`（上游 2.4.0 的測試；3 個 mutation）、`spec_review_wording_240`（docs、templates、README 等頂層檔沒有「只在 Strict」「Standard 規格審查選用」這類句子；種一行錯的會被抓到）、`release_describe_240`（假的 gh，不連網；2 個 mutation）、`docs_240`。
  - 改寫：`loops_fixtures_236`、`loops_privacy_236`、`loops_real_236`、`loops_status_236`（新格式、6 類、新 fixture `repeat_long`、`child_error_pos`／`_neg`）、`rename_236`（新網址；舊網址只准出現在 CHANGELOG.md）、`readme_236`（新提示詞 hash）、`release_state`（dry run 多一個 PLAN）。
  - 安全閘門的 11 項（`safety_*_225`、`spec_review_224`、`spec_fields_shared_225`、`order_oversize`、`order_limits_224`、`protected_*_224`）函式內容和 2.3.0-ds.6 逐字相同，都通過；`safety_gate.py` 和 `safety` 區塊沒改。
- `test_verify_dsh_run.py` 33 項（Python 3.11、3.9 都 OK）。
- 本機真實紀錄（只讀，103 個 DSH session、42,317 次呼叫）：
  - `loops`：66 筆（repeat 32、retry_same_error 2、ping_pong 0、poll_no_progress 32、bad_args 0、child_error_unhandled 0）；`BAD_ARGS` 行照舊是 4 次被拒（edit 2、PowerShell 1、read 1），沒有任何工具在 20 次呼叫內被拒 2 次，所以 bad_args 從 2.3.0-ds.6 的 4 筆變 0 筆。`reminders`：64 筆是 1、2 筆是 2。同一份紀錄用 2.3.0-ds.6 的判法是 70 筆。讀全部 session 約 1 分 45 秒。
  - `inject`：掃了 42,317 個工具輸出，86 筆（override 2、role_rewrite 3、hidden 17、exfiltration 64），幾乎都是讀本 repo 的安全文件和測試樣本造成的誤報。
- 指示鏈（`memory_size_check.py --chain`，AGENTS 段落＋每輪必讀 docs/01、03、06、08，LF）：13,937 → 14,189 bytes（AGENTS 段落 2,974 → 3,147、docs/06 1,998 → 2,077），上限 65,536。`resume_inject.py` 每次恢復最多再加 2,048 bytes 的輸出（實測本工作的 RESUME_STATE 輸出 871 bytes；7,660 bytes 的檔截到 1,968 bytes）。
- fixture 全是合成資料，沒有真實紀錄的內容；假金鑰在測試執行時才組出來，不存在 repo 裡。

## 2.3.0-ds.6（2026-11-15）

WO-DS-011。產品改名為 **dsh-DIRECTOR-WORKER**（簡稱 **dshdw**；舊名 DIRECTOR-WORK DeepSeek 版（DW-DS）），並加上 DeepSeek 工作品質的事後偵測。DSH 沒有 PreToolUse hook，dshdw 不能即時攔截工具呼叫，所以這一版全部是**事後偵測＋規則**：從 session 紀錄找問題，在檢查點、閘門、狀態報告裡讓人看見。不做插件，用法不變（照樣貼啟動提示詞）。這一版和 2.3.0-ds.5 一起發布（ds.5 沒有單獨發布）。

### 新功能
- `dsh_audit.py loops`（不另寫新工具）：讀和 `build` 一樣的 DSH session，找出打轉的呼叫。
  - 類別：`repeat`（同一呼叫 20 次內出現 3 次）、`retry_same_error`（同一呼叫 20 次內又失敗、錯誤一樣，中間沒寫任何文字）、`ping_pong`（A、B 交替 3 輪結果不變）、`poll_no_progress`（讀取／查詢類連續 3 次結果一樣）、`bad_args`（DSH 紀錄的 `INVALID_ARGS`／`ToolArgsError`，或參數字串不是 JSON；次數、比例、前 5 名工具）。門檻都能設。
  - `child_error_unhandled`：在本機 103 個 DSH session 裡，子代理結束的事件是 `user/message`（`source.kind` = `subagent-settled`），`stopReason` 只看過 `completed`；沒看過失敗的子代理事件，所以這一類標 NOT_VERIFIED，只印 `~ NOT_VERIFIED`，不猜事件名。
  - 只印工具名和雜湊，不印參數、輸出或訊息內容。`wait_agent` 不算打轉（等子代理本來就要一直叫）。fork 出來的 session 帶著母 session 的事件，同一個發現只算一次（`copies=N`）。
  - `--json`；`--out FILE` 寫 JSON 給 `status_gen.py`；`--events FILE...` 讀合成 fixture（`tools/fixtures/loops/`）。exit 0 沒發現、1 有發現、2 讀不到。
- `status_gen.py` 新增 `"loops"` 段：讀 `loops --out` 的 JSON，有發現才多印一行 `LOOPS …`；沒發現不印；檔案不在印 MISSING。選 status_gen 不選 line_brief：loops 看的是整個專案所有 session，和 status_gen 的 AUDIT 段（動作紀錄）同一類；line_brief 只看一條工作線。沒有新增每輪必讀。
- `memory_size_check.py --chain FILE... [--max-bytes N]`：一條指示鏈一起量（每檔 bytes、有 CRLF 另列 LF bytes、~token），加總超過 `--max-bytes` 判 FAIL；列出各檔之間重複 3 行以上的段落（位置＋行數）。單檔和 `--kind resume` 的輸出不變。`docs/09` 的量法改成一條 `--chain` 指令。
- 規則（`templates/WORK_ORDER.md`、`templates/RESUME_STATE.md`、`docs/07` 各一句）：同一呼叫失敗兩次，先寫一行「為什麼失敗、下一步改什麼」再試；派出的子工作逾時沒結果或出錯，都要回報主管，不可靜默等待；宣告完成前，本輪跑過驗證指令並附 RAN 行。

### 改名
- README、BOOTSTRAP、DEEPSEEK-PORT、docs、templates、tools 的說明文字與 `--help`：產品名改為 dsh-DIRECTOR-WORKER／dshdw；README、BOOTSTRAP、DEEPSEEK-PORT、CHANGELOG、tools/README、DSH-TOOLS、docs/04、05、11、13 第一次出現時附「舊名 DIRECTOR-WORK DeepSeek 版（DW-DS）」。「DeepSeek 版」「DSH 版」「DSH edition」這類指本產品的說法一起改成 dshdw（「DSH 版本」指 DSH 的版本，不改）。
- 啟動提示詞只換名稱字樣：「（DeepSeek Harness 版。」→「（dsh-DIRECTOR-WORKER。」，其他逐位元組不變。
- `release.py` 和 `director_work.example.json` 的 Release 標題改為 `v{version} — dsh-DIRECTOR-WORKER`；`bootstrap_repo.py` 寫進專案 `.gitignore` 的註解行改為 `# dshdw bootstrap`。
- 不改：版本號格式（2.3.0-ds.N）、tag 名稱、工具檔名、設定鍵、CHANGELOG 舊段落、上游 DW 的名稱與網址、repo 網址、提示詞的用法。`PURPOSE.md` 沒有產品名字樣，沒有改。

### README 白話重寫
- 照 DW README 新版（白話、多圖）的結構重寫：最上面是要複製的啟動提示詞，接著「第一次用 AI agent？先看這裡」（AI agent 是什麼、怎麼在 DSH 開對話貼提示詞、詞彙比喻、git 怎麼走、為什麼分總監和 worker、DSH 不會事先擋只會事後查）、名詞小抄、圖解、常見問題、檔案地圖，再來是防護、已知限制、原則、授權。
- 10 張 mermaid 圖（flowchart、sequenceDiagram、stateDiagram-v2），中文標籤都加雙引號，不用 HTML；原本圖裡的 `<br/>` 拿掉。
- 換成 dshdw 的實際情況：沒有 PreToolUse，只能事後檢查；指示鏈上限 65536 bytes；待決用 `ask_user_question`＋`PO_PENDING.md`；`loops` 和 `--chain` 用白話說明。啟動提示詞和上面「改名」那一條一樣，只換名稱字樣。

### 一起發布的 2.3.0-ds.5（WO-DS-010；細節見下方 2.3.0-ds.5 段）
- 跟上上游 DW 2.3.0（tag v2.3.0）：新工具 `completion.py`、`sim_check.py`、`waiver.py`、`line_brief.py`、`pre_tr.py`、`pack_check.py`、`hash_check.py`、`flag_check.py`；`gate_check.py --feasibility` 與 `--verdict` 的自己查證證據；`dsh_doctor.py --licenses`；非 UTF-8 主控台的 `--help` 修正。
- DS 專屬：`dsh_session.py --cwd-check <工作區>`，lead 開工第一步先確認在對的資料夾。
- 安全閘門全部保留，不加回 OpenSpec／SDD。

### Credits（只借概念，程式用標準函式庫自己寫，沒有複製以下 repo 的程式碼）
- 打轉偵測（對工具、參數、結果做雜湊；generic_repeat、poll_no_progress、ping_pong）：OpenClaw loop detection，https://docs.openclaw.ai/tools/loop-detection ；zeptoclaw loop_guard，https://docs.rs/crate/zeptoclaw/0.8.0/source/src/agent/loop_guard.rs 。授權：NOT_VERIFIED（只讀說明，沒有讀程式碼）。
- 同錯重試先反思：cleverer-dsh，https://github.com/Classicoke/cleverer-dsh ，MIT。
- 工具參數 JSON 錯誤（只計數，不修復）：dsh-translate，https://github.com/PerryLink/dsh-translate ，Apache-2.0。
- 子工作失敗必須回報：dsh-subagent-watchdog，https://github.com/Lequait/dsh-subagent-watchdog ，MIT。它的 README 提到的事件名在本機紀錄裡沒看到，所以沒有用。
- 指示鏈 token 預算與重複段落：dsh-context-doctor，https://github.com/Zhenyu98/dsh-context-doctor ，BSD-3-Clause。
- 完成前先驗證：superpowers（verification-before-completion），https://github.com/obra/superpowers ，MIT。

### 驗證
- `selftest_ds.py`：2.3.0-ds.5 是 73 項，這一版 81 項；Python 3.11 和 3.9 各跑一次，都是 81/81、skip=0。
  - 新增 8 項：`loops_fixtures_236`（每類一個正例、一個反例，CLI 和程式內各跑一次；fork 的副本只算一次；20 次內才算重試；8 個 mutation）、`loops_privacy_236`（假的金鑰和標記文字不會出現在一般輸出、`--json`、`--out`；1 個 mutation）、`loops_real_236`（最新一個真實 DSH session）、`loops_status_236`（status_gen 的 `loops` 段；1 個 mutation）、`chain_236`（`--chain`；3 個 mutation）、`rename_236`（錯誤寫法 0 處、舊名只出現在該出現的地方、提示詞與 Release 標題）、`rules_236`（三條規則與 docs/09）、`readme_236`（README：提示詞排第一個、逐位元組和固定值相同；五個段落的順序；mermaid ≥ 6 張、只用 GitHub 會畫的三種、中文標籤在雙引號裡；沒有 HTML、沒有私人路徑；5 個 mutation）。
  - 每組 mutation 先確認沒改過的工具答對，再看 mutant 有沒有答錯。
  - 安全閘門的 11 項（`safety_*_225`、`spec_review_224`、`spec_fields_shared_225`、`order_oversize`、`order_limits_224`、`protected_*_224`）一項不少，內容沒改，都通過；`safety_gate.py` 和 `safety` 區塊沒改。
- `test_verify_dsh_run.py` 33 項（Python 3.11、3.9 都 OK）。
- 本機真實紀錄（只讀）：103 個 DSH session、42,319 次呼叫，`loops` 找到 70 個（repeat 32、retry_same_error 2、ping_pong 0、poll_no_progress 32、bad_args 4：edit 2、PowerShell 1、read 1）。呼叫數含 fork session 帶來的重複事件。
- fixture 全是合成資料（`tools/fixtures/loops/`），沒有真實紀錄的內容。
- 每輪必讀（docs/01、03、06、08，用 `--chain` 量，LF）：10,964 → 10,963 bytes（docs/08 的「DSH 版」改成「dshdw」）。
- README 的 10 張 mermaid 圖只用規則檢查語法（`readme_236`）；本機沒有實際畫出來（NOT_VERIFIED），推送後看 GitHub 頁面。

## 2.3.0-ds.5（2026-11-15）

未單獨發布，隨 2.3.0-ds.6 一起發布（沒有 v2.3.0-ds.5 tag）。

WO-DS-010。跟上上游 DW 2.3.0（tag v2.3.0，de08549），再加一項 DS 專屬的 lead 開工 cwd 檢查。上游原文附在 `CHANGELOG-upstream.md`。安全閘門（`safety` 區塊：tests_first、plan_gate、spec_review_for_standard、stop_after_rounds、order_limits、protected_tests、不得自行關閉）全部保留；不加回 OpenSpec／SDD 流程。ds 序號沒有加：這一版沒有新的 DS 試驗修正。

### 上游 DW 2.3.0 移植
- 做法：DW `v2.2.5` 和 `v2.3.0` 用 `git show` 讀出（DW repo 只讀），對本版每個檔做三方合併（`git merge-file`），衝突逐處處理；新檔原樣搬。
- 新工具，原樣搬：`completion.py`、`sim_check.py`、`waiver.py`、`line_brief.py`、`pre_tr.py`、`pack_check.py`、`hash_check.py`、`flag_check.py`；範本 `templates/CPU_REPRO.md`、`templates/pre_tr.json`、`templates/run_closing.py`。
- `gate_check.py`：`--feasibility`；`--verdict` 的自己查證證據（`verdict_self_check`，2.3.x 預設 `warn`）。本版的 `--config` 原本就給 `--order`／`--match` 的安全閘門用，所以沒有搬上游「`--config` 只能和 --resume／--order／--verdict 一起用」那條拒絕。
- `doctor.py --licenses` → `dsh_doctor.py --licenses`（本版沒有 `doctor.py`）：`--licenses-only` 的輸出和上游逐字相同；一般執行時每筆授權是一個 `licenses` 檢查。
- `verdict_self_check`：`dsh_setup_check.py` 認得這個鍵（不是 warn／fail 判問題，同上游 setup_check）；`bootstrap_repo.py --config` 印一行 `CONFIG verdict_self_check: warn|fail`，值不對印 WARN（gate_check 會用 warn）。`director_work.example.json` 加 `"verdict_self_check": "warn"` 和說明。
- `ran_line.py` 依作業系統引號；`round_check.py` 條件表 WARN；`status_gen.py` 認得 `"lines"`（給 `line_brief.py`；本版的鍵名照舊是 `po_pending`）。
- 非 UTF-8 主控台的 `--help`：上游修十支（DS 有的是 gate_check、metrics_report、report_vs_audit、resume_archive、scope_check、trace_report，加上新工具）；在 cp1252 下實測，DS 自己的 `bootstrap_repo`、`dsh_session`、`release`、`safety_gate`、`status_gen` 也會壞，一起修（輸出改 UTF-8 移到解析參數之前），`dsh_doctor` 也照改。修前 11 支壞，修後 0 支。
- 規則：`docs/02`（收尾範本、豁免、CPU_REPRO、送 TR 前檢查）、`docs/06b`（line_brief、授權到期，寫 `dsh_doctor.py`）、`docs/07`（條件表、放寬標準前盲測、同一組核對、可行性搜尋）、`templates/WORK_ORDER.md`、`GATE_VERDICT.md`、`RESUME_STATE.md`、`status_director.json` 的新段落。DSH 用語照本版（停止規則 1 輪、`send_message`）。
- 沒搬：`poll_hint.py`、`transcript_audit.py`、`usage_mix.py`、`setup_check.py` 的 `--help` 修正（本版沒有這幾支；對應的 `dsh_audit`、`dsh_usage`、`dsh_setup_check` 原本就不會壞）。

### lead 開工的 cwd 檢查（DS 專屬）
- 11-14 23:42 的教訓：lead 在錯的資料夾工作。`dsh_session.py --cwd-check <工作區>`：目前資料夾和工作區都經 realpath、normcase 比（Windows 不分大小寫）；不同資料夾或子資料夾印 `BLOCKED: cwd <實際> != <預期>` 和一行 NEXT，exit 1，什麼都不寫；相同印 `CWD: OK <路徑>`。
- 放在 `dsh_session.py`：它已經是 lead 開工用的工具（`--temp-env`、`--worker-worktree`、`--worktree-status`），開工第一步就會叫到它；`bootstrap_repo.py` 是對專案 repo 做機械步驟、要 `--repo`，第 10.5 步才跑，太晚。
- 寫進 BOOTSTRAP 第 0 步第 1 點（規則包還沒在本機時先用 `(Get-Location).Path` 比，取得後補跑）、`docs/11`「lead 開工第一步」，開 worker 的 prompt 也加一句「第一步跑 `--cwd-check <你的 worktree>`」。

### 其他
- `tools/README.md` 限制段還寫著「dsh_audit 最多記 500 字」，2.2.5-ds.5 起已經是整條記；改正。

### 驗證
- `selftest_ds.py`：2.2.5-ds.5 是 54 項，這一版 73 項；Python 3.11 和 3.9 各跑一次，都是 73/73、skip=0。
  - 上游 2.3.0 的 17 項（案例、預期輸出、mutation 字串和上游相同，只換測試框架）：`completion_230`、`feasibility_230`、`completion_visibility_230`、`sim_check_230`、`waiver_230`、`run_closing_230`、`doctor_licenses_230`（改跑 `dsh_doctor`）、`line_brief_230`、`pre_tr_230`、`pack_check_230`、`hash_check_230`、`flag_check_230`、`ran_line_posix_230`、`verdict_self_check_230`、`round_conditions_230`、`rules_docs_230`（上游 17 行在 DS 文件一字不差，另查 DS 的 3 行）、`help_any_console_230`（cp1252 包住 stdout／stderr，跑 32 支 `tools/*.py`，含全部 `dsh_*`）。
  - DS 新增 2 項：`cwd_check_230`（相同、大小寫不同、子資料夾、別的資料夾、不存在的資料夾，並確認沒寫任何檔；3 個 mutation）、`verdict_self_check_keys_230`（`dsh_setup_check` 和 `bootstrap_repo --config`；2 個 mutation）。上游 setup_check 的 4 個 `verdict_self_check` 案例搬到這一項。
  - 每組 mutation 先確認沒改過的工具答對，再看 mutant 有沒有答錯。上游 `round_conditions_230` 的 mutation 放在條件表已經寫好之後，改不改工具結果都一樣（空測）；本版移到「沒有條件表」那一步。
  - 安全閘門的 11 項（`safety_*_225`、`spec_review_224`、`spec_fields_shared_225`、`order_oversize`、`order_limits_224`、`protected_*_224`）一項不少，內容沒改，都通過。
- `test_verify_dsh_run.py` 33 項（Python 3.11、3.9 都 OK）。
- 上游 DW 2.3.0 的驗證樣本（36 個，含每支新工具的 `--help`）複製到工作資料夾，用本版工具重跑，結果和 DW 2.3.0 一致（只把樣本路徑、時鐘時間、檔案多久前改過、line_brief 的 `--repo` 換成代號再比）。
- 每輪必讀（docs/01、03、06、08）：10,964 → 10,964 bytes（這幾個檔沒改）。

## 2.2.5-ds.5（2026-11-15）

WO-DS-009 第 3 版。這一版處理 WO-DS-008 r2 試驗（滿分 113：Claude 110、DSH 開 SDD 97.5、DSH 關 SDD 95）裡歸 DW-DS 的項目。並移植上游 DW 2.2.5（DW commit ab1460f，B7），上游原文附在 `CHANGELOG-upstream.md`。

### 拿掉 OpenSpec，安全閘門保留（B1）
- 原因：OpenSpec 本身沒有量到正確性效益。r2 的 `openspec validate` 全過，隱藏測試卻是開 SDD 85/107、關 SDD 101/107。
  - 失分在兩處：拆成 8 個 change 後沒做整合驗收；規格裡自訂的限制擋掉真實資料，Traceback 外漏。這兩項改由最終端到端驗收（B7）和規格審查清單處理。
  - sdd 組的額度是 UNKNOWN，OpenSpec 的成本也無法證明划算。
  - 總監依評分判斷，PO 授權；PO 03:19 更正「不要全部拿掉sdd，該有的安全保護要有」。
  - ds.4 的程式在 tag `v2.2.4-ds.4`；日後重測若證明 OpenSpec 有用，從那裡拿回來。
- 拿掉：
  - openspec CLI 的尋找、安裝、`init`、`openspec_bin`、telemetry 設定。
  - `openspec validate`／`archive`、工單 `SPEC_CHANGE` 欄位、`openspec/changes/`、`skip_specs`、`require_spec_for_*`。
  - OD-00「安裝 openspec」提示、`templates/openspec_config.yaml`、`sdd_gate.py --which`。
  - `verify_dsh_run` 的 R14／R15。
- 保留，改名「安全閘門」：`tools/sdd_gate.py` 改名 `tools/safety_gate.py`（`git mv`），`docs/13_sdd_openspec.md` 改名 `docs/13_safety_gates.md` 並重寫。設定在 `director_work.json` 新的頂層 `"safety"`。
  - `tests_first`：Standard／Strict 要有 `TESTS_LOCKED`，雜湊不符判不過。
  - `plan_gate`：計畫檔改放 `<WORK_DIR>/<WO>/PLAN.md`，交件時要和 `PLAN_APPROVED` 的雜湊對得上、全部打勾；找不到 PLAN.md 判不過（原本只印 note）。
  - `spec_review_for_standard`、`stop_after_rounds`（1）、`prefer_auto`：照舊。`order_limits`、`protected_tests` 也照舊。
- 不得自行關閉：對 Standard／Strict 把 `tests_first`、`plan_gate`、`spec_review_for_standard` 設成 false，或把 `stop_after_rounds` 設成 0、調高到超過 1，要有 PO_PENDING 裡寫明該開關、已答覆的項目，否則 `gate_check --order` 判不過。這是 2.2.3-ds.3 對 `require_spec` 的規則，改套到安全開關。`prefer_auto` 只是提示，關掉只印 note（總監裁決）。
- 舊設定檔的 `"sdd"` 區塊照讀，不報錯：
  - 安全開關照讀，印「請搬到 safety」；`"safety"` 也有同一個鍵時以 `"safety"` 為準，印「被忽略」。
  - `openspec_bin`、`require_spec_*` 和其他鍵忽略，印「OpenSpec 已在 2.2.5-ds.5 移除，此鍵被忽略」。
  - 舊 `sdd.max_*_per_order` 照 2.2.4-ds.4 讀，印「請搬到 order_limits」。
  - 工單還有 `SPEC_CHANGE` 只印 note。
- 需求寫法：寫在工單 ACCEPTANCE 和 `templates/WORK_ORDER.md` E 節的邊界與壓力清單（「不當掉」至少一個極端輸入）。
- 文件：BOOTSTRAP 10.5、README、DEEPSEEK-PORT §11／§12、`docs/02`、`05`、`11`、`13`、範本、`tools/README.md`、`DSH-TOOLS.md` 同步。逐項處理（刪／留）見 WORK_DIR 的 `SDD_REMOVAL.md`。

### L-061（B3）
- `bootstrap_repo.py` 只做 `.memsearch/` exclude；`--config` 只讀。
- 舊 `sdd` 區塊（`openspec_bin` 為 null 或路徑不存在），即使 `OPENSPEC_BIN` 指到可執行的 CLI：
  - 不找 CLI、不 init、不寫設定；
  - 只印兩行 B1 的 WARN（OpenSpec 鍵忽略、安全開關請搬到 safety）；
  - exit 0。
- 同一份設定給 ds.4 的 `bootstrap_repo.py` 跑：會執行 CLI 的 `--version` 和 `init`，並建出 `openspec/`。

### dsh_usage `--out` 必跑（B2）
- BOOTSTRAP 新增「收尾」節，`templates/AGENTS_PROJECT_SECTION.md` 加收尾規則：最後一步跑 `dsh_usage.py --project-dir <WS> --out <WS>/DIRECTOR/usage.json`，再跑 `gate_check.py --final <WS>/DIRECTOR`。
- `gate_check.py --final DIRECTOR [--usage FILE]`：找不到、讀不了、或 `NO_DATA` 時印 `~ WARN USAGE`，exit 不變。r2 的 sdd 組 tokens 是 UNKNOWN，就是因為沒跑這一步。
- 最終端到端檢查由 B7 從 DW 2.2.5 移植，DS 不另做一套。

### 每個 worker 開真的 worktree（B4）
- `dsh_session.py --worker-worktree <REPO> --order <WO> [--branch B] [--base REF] [--root DIR]`：在 `<REPO>/../wt/<WO>` 開一個 git worktree 和一條分支。資料夾已存在就拒絕，不刪任何東西。
- `dsh_session.py --worktree-status <checkout>`：依 `git worktree list` 印「WORKTREE: 隔離 worktree …」或「WORKTREE: 共用 checkout …」。
- `gate_check.py --report-skeleton` 的 WORKTREE 行由同一個函式產生；`templates/TASK_REPORT.md` 加 WORKTREE 行；`templates/WORK_ORDER.md` 的 WORKTREE 預設改成自己的 worktree；`docs/11` 開 worker 流程加第 3 步。
- r2 的 sdd 組自稱「隔離 worktree」，實際是共用 checkout。

### 時間不得手填（B5）
- BOOTSTRAP「收尾」、`docs/02`、`templates/AGENTS_PROJECT_SECTION.md` 寫明：報告、裁決、DIRECTOR_LOG 的時間和 RAN 行由工具產生，不得手填。產生時間的工具由 B7 從 DW 2.2.5 移植。
- r2 的實際狀況：sdd 有 8 份驗收報告寫 01:32，實際是 01:17；nosdd 差約 1 小時。

### 遷移
- 舊 `director_work.json` 照樣能用。要清掉 WARN：把 `sdd` 裡的安全開關搬到頂層 `"safety"`，`max_*` 搬到 `order_limits`，再刪掉 `sdd` 區塊。
- 工單的計畫檔從 `openspec/changes/<名>/tasks.md` 改成 `<WORK_DIR>/<WO>/PLAN.md`；`PLAN_APPROVED` 的雜湊算法不變（`safety_gate.py --plan-hash`）。
- 呼叫 `sdd_gate.py` 的地方改成 `safety_gate.py`；`--which` 已移除。
- `verify_dsh_run` 設定的 `change`、`openspec_bin` 鍵已移除，寫了會被拒絕（未知鍵）。

### 驗證
- `selftest_ds.py`：ds.4 是 50 項（不設 OPENSPEC_BIN 50/50；設了 OPENSPEC_BIN 的基準見 TASK_REPORT），B1～B5 之後 46 項，B7 之後 54 項；Python 3.11 和 3.9 各跑一次，都是 54/54、skip=0。
  - 刪 8 項，都是 OpenSpec 專屬：`sdd_spec_ok`、`sdd_no_spec_change`、`sdd_validate_fails`、`sdd_no_cli`、`sdd_real_openspec`、`sdd_cli_lookup`、`sdd_cli_setup`、`sdd_which_off_224`。
  - 改名 4 項：`sdd_tests_locked` → `safety_tests_locked_225`、`sdd_plan_and_review` → `safety_plan_and_review_225`、`sdd_spec_off_gate` → `safety_switch_off_225`、`sdd_oversize` → `order_oversize`。
  - 新增 4 項：`safety_legacy_block_225`、`safety_mutations_225`（6 個 mutation）、`usage_final_225`（3 個 mutation）、`worker_worktree_225`（2 個 mutation）。
  - 改內容：`bootstrap_repo`（L-061）、`setup_shadow`、`report_skeleton`。
  - 安全閘門 selftest：ds.4 有 6 項，這一版有 8 項。
  - B7 新增 7 項（上游 2.2.5 的案例表、fixture、mutation 字串逐字相同，只換測試框架）：`report_vs_audit_225`（H1 的 10 個比對案例、18 次 CLI 執行、13 個 mutation，另查 `dsh_audit` 整條保留與 `--input-limit` 的 `input_cut`）、`weird_inputs_225`、`ran_line_225`（5 個 mutation；上游的 `browser_check` 那一項本版沒有這支工具，不搬）、`gate_order_225`（5 個）、`after_verdict_225`（1 個）、`final_225`（3 個）、`scope_shared_225`（4 個）。
  - B7 改內容：`after_verdict_224` 照上游 2.2.5 改成預設 FAIL（mutation 換成上游 2.2.5 的 5 個）；`worker_worktree_225` 改看上游格式的 WORKTREE 行；`usage_final_225` 加「沒有 E2E 就 `FAIL final`、exit 1」，usage 的檢查放在有 E2E 的情況下照舊。
  - Python 3.9：修正前在 3.9 上 selftest 有 47 項壞在 `write_text(newline=)`（修法見上「上游 DW 2.2.5 移植」的 Python 3.9 修正）。
  - 總監裁示後新增 `spec_fields_shared_225`（1 個 mutation：safety_gate 的 `review_fields_lacking` 改成什麼都不缺，`--match` 和 `--sequence` 的提示都要跟著消失）。
- `test_verify_dsh_run.py` 33 項（Python 3.11、3.9 都 OK）：D10、步驟「4 鎖定測試」「7 計畫閘門」留著，計畫檔改成 PLAN.md。
- 每輪必讀（docs/01、03、06、08）：10,964 → 10,964 bytes（這幾個檔沒改）。

### 上游 DW 2.2.5 移植（B7）
- 做法：DW `v2.2.4` 和 ab1460f 用 `git show` 讀出（DW checkout 只讀），對本版每個檔做三方合併（`git merge-file`），衝突逐處處理；DS 已有、DW 2.2.5 從 DS 搬回去的部分（ds.4 B2 `--shared`、B4 規格審查檔案查法），保留一份。
- 原樣搬：`tools/ran_line.py`（RAN 行和時間戳從時鐘來）、`templates/weird_inputs.py`、`templates/HANDOFF.md`、`evidence_record.py` 和 `release.py` 的 TEMP（設了 `WORK_DIR` 時暫存檔放 `WORK_DIR/tmp`）、`audit_log.summary(input, limit)`。
- `report_vs_audit.py`：上游 2.2.5 全部（H1 誤報修正、FAIL 類別、`time_mismatch=`／`not_run=`、`--lead`、`--tolerance-min` 預設 10、最上層攔例外）；和上游只差本版原有的 3 處（DSH 包殼說明、`pwsh` 註解、rebuild 提示寫出來源工具）。
- `dsh_audit.py`（本版對應上游 `transcript_audit.py`）：`build` 預設整條 input 都記，不再截 500 字；`--input-limit N` 截過的行標 `input_cut`（同上游 2.2.5）。
- `gate_check.py`：
  - 新增 `--sequence`（PLAN_APPROVED 早於 worker 第一個 commit、每張工單有自己的 SPEC_REVIEW、審查和裁決來自別的 session）。
  - `--after-verdict` 改成預設 FAIL，`--warn` 回到 WARN；`--strict` 照收。
  - `--final` 用上游的最終驗收（`evidence/E2E/` 沒有非空檔 FAIL；缺 `ENTRY_POINT:`、DD 沒「驗收案例」印 WARN），本版 B2 的 usage.json 行接在後面（`~ WARN USAGE`，不影響 exit）。原本 ds.5 的 `FINAL: OK|FAIL` 行拿掉，改用上游的 `OK|FAIL final <資料夾>`；`--final` 可以和其他模式一起跑（上游做法）。
  - 長路徑一行訊息、BASE_REF 括號當註解，改在本版原有的 `base_git`／`base_ref_problems`（本版放在檔案前段，合併放不進去，手動搬）。
- `scope_check.py`：BASE_REF 括號當註解、`WORKTREE:` 行、長路徑訊息、最上層 `NOT_RUN`。`--shared` 用本版 ds.4 B2 的那份（上游 2.2.5 搬回去的就是它，查的東西相同；本版另外算大小）。
- WORKTREE 行只留一份：`scope_check.worktree_line`（上游 2.2.5 B10）；`dsh_session.py --worktree-status` 和 `gate_check.py --report-skeleton` 都呼叫它。行的格式改成上游的 `WORKTREE: 隔離 worktree <路徑> (git worktree list: n)`／`WORKTREE: 共用 checkout（主 checkout） <路徑> (...)`。
- 範本與文件：`SPEC_REVIEW` 清單加上游第 10～14 項（本版編號 13～17）、LOG 行加 `session=`；`WORK_ORDER` 加 `WORKER_LIMIT` 和交接；`GATE_VERDICT` 加 `SESSION_ID:` 和 G 節最終驗收；`TASK_REPORT` 的 RAN 行用 `ran_line.py`；`DECISION_REGISTER` 加「驗收案例」欄；`DIRECTOR_FILES` 加 DIRECTOR_LOG 時間戳格式和 IDEAS.md；`docs/02` 加閘門順序、裁決後鎖程式碼、最終驗收、輪數上限、TEMP 更正；`BOOTSTRAP` 開 worker 提示加 TEMP 更正。DSH 用語照本版（`subagent`、`send_message`、停止規則 1 輪）。
- 規格審查的「有沒有審查」查了兩處：`--match`（`safety_gate.spec_review_problems`，本版 ds.4 B4，安全開關 `spec_review_for_standard` 管）和 `--sequence`（上游 2.2.5 B3，另查時間先後和 session）。兩處的輸入不同（`--match` 沒給 `--dispatch-log` 也會找 DIRECTOR_LOG）、查的東西不同，所以都留著（總監裁示：不算重複）；時間先後和 session 只在上游那份。兩處查 tokens／issues／adopted 三欄用同一個函式 `safety_gate.review_fields_lacking`，`gate_check.py` 不再自己定義 `REVIEW_FIELDS`（上游有）；差別寫在 docs/02「閘門順序」下的兩行。
- 上游 fa848c2（DW 2.2.5 merge 前的最後一個修正）：`ran_line_225` 執行模式的正則改成單、雙引號都接受（Linux 上 `shlex.join` 用單引號）。
- Python 3.9 修正（ds.4 起的舊問題，移植時發現）：`Path.write_text(newline=)` 要 3.10，工具 `verify_dsh_run.py` 寫報告的 `save` 在 3.9 會壞；改用 `open(..., newline=)`（和 `pause_ctl.py` 同寫法），`selftest_ds.py`、`test_verify_dsh_run.py` 的寫檔函式一起改。
- 沒搬：`browser_check.py`（本版本來就沒有）、上游 `selftest.py`（案例改寫進 `selftest_ds.py`，見「驗證」）、`transcript_audit.py`（本版是 `dsh_audit.py`，見上）。

## 2.2.4-ds.4（2026-11-14）

對應上游 2.2.4（DW commit 18d8ddb；5428682 之後另有 dad65a2 的 UNVERIFIED 和 18d8ddb 的 status 截寬與長路徑）。這一版處理 WO-DS-006 試驗（DSH 有／沒有 SDD 兩組，對照 Claude）比較表 §10 裡歸 DW-DS 的項目，並移植上游 2.2.4 的通用修正。ds 序號從 3 升到 4（總監待辦「ds 序號可以往下」）。

### 工單大小上限搬出 sdd（#8、S-P1）
- 上限不是 SDD 開關，SDD 關掉的專案也要用，所以搬到 `director_work.json` 頂層的 `order_limits`：`max_files_per_order` 3、`max_lines_per_order` 200、新的 `max_test_lines_per_order` 400。
- 測試檔（`test_*.py`、`*_test.py`、`tests/` 下）照算檔數，但行數另算，不吃掉 200 行（試驗：鎖定測試把 200 行吃掉，sdd 組只好把上限改成 600）。`scope_check.py` 的 `SIZE:` 行印 `files= lines= test_lines= limit=3/200/400`。
- 舊的 `sdd.max_files_per_order`／`sdd.max_lines_per_order` 照讀，`scope_check.py` 印 `NOTE: SHADOW WARN … 請搬到 order_limits`；兩邊都寫時以 `order_limits` 為準。`dsh_setup_check.py` 對舊位置印 shadow，並檢查 `order_limits` 的型別。`docs/13`、`sdd_gate.py` 說明、`director_work.example.json` 同步。

### 共用 checkout 的 scope_check（#2）
- DSH 的工人共用一個 checkout，舊版每張工單都把別人的檔算進來（試驗：`--match` 沒法自動過）。工單 `WORKTREE` 寫「共用」（或加 `--shared`）時，`scope_check.py` 只算 commit 訊息寫了本工單編號的 commit，加上 SCOPE 內還沒 commit 的檔；別人的檔印 `OTHER`，不算越界。本工單 commit 動到 SCOPE 外的檔照樣 `OUTSIDE`。`docs/11` 寫明 commit 訊息要帶工單編號。

### CHECKS 路徑（#3）
- `gate_check.py --order` 派工前就把反斜線路徑擋下，訊息指出第幾行、建議改正斜線。兩種都抓：`\w` 這種不合法的 JSON 跳脫，以及 `\t`、`\n` 這種會悄悄變成控制字元的。其他 CHECKS 錯誤也加上行號。`templates/WORK_ORDER.md` 寫明一律用正斜線。試驗的 WO-004 副本：`CHECKS line 97 (AC-5): backslash path … is not valid JSON; write the path with forward slashes`。

### 每張工單都要 SPEC_REVIEW（#4）
- 原本：只有給 `--dispatch-log` 才查 SPEC_REVIEW，沒給就完全不查，沒審過的工單照樣通過（試驗 WO-005／006）。現在：Standard／Strict 的 `--match` 一律查，沒給 log 就找工單所在 DIRECTOR 的 `DIRECTOR_LOG.md` 和 `reviews/` 下檔名有工單編號與 SPEC_REVIEW 的檔，找不到判不過。行裡缺 `tokens=`／`issues=`／`adopted=` 印 note。

### 受保護的測試只准新增（#7）
- TESTS_LOCKED 的檔和 `director_work.json` 頂層 `protected_tests` 列的檔，只能新增檔案或在檔尾加測試；改到原有內容或刪檔，`scope_check.py` 判 `PROTECTED` 越界（換行符號和檔尾空行不算改）。它也印 `PROTECTED_CHANGED:` 一行。
- `templates/TASK_REPORT.md` 加 `PROTECTED_CHANGED:`（逐檔列出改到的受保護檔，沒有寫 NONE）。`gate_check.py --match --repo` 拿它對 git：寫「無」卻有改、漏列、或改到原有內容都判不過（試驗：nosdd 的 PO 報告寫「兩支原測試沒改一行」，實際有改）。

### SDD 關閉時不提示 CLI（#9）
- `require_spec_for_strict` 和 `require_spec_for_standard` 都是 false 時，`sdd_gate.py --which` 只印一行「SDD 關閉，不檢查 CLI」，不找 CLI、不建議寫入 `openspec_bin`；`dsh_doctor.py` 印 OK 和同一句，`dsh_setup_check.py` 不再印寫入建議。找得到 CLI 時關掉 require_spec 仍要 PO 答覆。

### 範本建議（#10、#13）
- `templates/WORK_ORDER.md` 的邊界與壓力清單、`templates/SPEC_REVIEW.md` 第 7 項、`templates/openspec_config.yaml` 的 specs 規則各補兩行：巢狀深度含 JSON（不透出 RecursionError）；批次輸入有錯時預設輸出就列出是哪幾筆，問題物件用 dict 或中文名稱，不用 `XxxError` 類別名當使用者看到的字。原有清單文字和 DW 2.2.3 相同，只補這兩行。

### effort 一致（#14）
- `dsh_usage.py --effort-check <工單>`：找工單 PRIMARY_WORKER 的 session，印 `EFFORT_ACTUAL <WO> agent= effort= order=`，和工單 `MODEL / EFFORT` 不同印 shadow WARN（exit 0）。試驗資料實測：WO-004 的 w4 是 `effort=max order=high`。lead 把那行貼進 DIRECTOR_LOG；`gate_check.py --match --dispatch-log` 讀到不一致印 shadow WARN，沒有那行印 note。寫回 DIRECTOR_LOG 而不是工單，因為改工單會改掉派工雜湊。`docs/11`、`templates/WORK_ORDER.md` 寫明 `subagent` 的 `reasoning_effort` 一定要填工單的值。

### dsh_usage --out（#16）
- 原因：`--out` 只在有資料時才寫；篩選後沒有 session（`NO_DATA`）就在寫檔前 `return 2`，所以呼叫端看到 rc=2、沒有檔、也不知道為什麼。試驗的常見情況是 `--project-dir` 指到 repo 子資料夾（`…/ws/ledger`），但 session 記在啟動資料夾 `…/ws` 下。另一種 rc=2 是參數寫錯（`-o`、`--output`），那是 argparse 的用法錯誤。
- 修正：`NO_DATA` 時 `--out` 也寫 JSON（`status: NO_DATA`、`reason`、`hints`、`filters`），exit 仍是 2；`--project-dir` 在某個啟動資料夾底下時，印 `HINT` 指出該用的上層資料夾。

### DSH 啟動設 TEMP（對應上游 2.2.4 B3）
- `dsh_session.py` 多一個 CLI：`--temp-env <WORK_DIR>` 建 `WORK_DIR/tmp`，印出把 `TEMP`／`TMP`／`TMPDIR` 指過去的 PowerShell 與 bash 設定行。BOOTSTRAP 第 7 步、`docs/02`、`docs/11`、`templates/WORK_ORDER.md`、`templates/TASK_REPORT.md` 寫明開工先設；`gate_check.py --report-skeleton` 對有 WORK_DIR 的工單也印這一行。

### 上游 2.2.4 移植
- `report_vs_audit.py`（上游原樣搬，DS 只留自己的說明段和 rebuild 註記）：WO-DS-006 三組 20 份報告的誤判 FAIL 64 → 0、其中 18 條是 UNVERIFIED（claude 8 → 0／4、dsh-sdd 32 → 0／11、dsh-nosdd 24 → 0／3；64 條全是誤判，沒有真漏跑）。變數會展開（`$X`、`${X}`、`$env:X`、`%X%`、PowerShell `a + b`、here-string，同一 agent 前面設的延用到後面）；`git -C DIR x` 當 `cd DIR` 再 `git x`；字中 `...`／`…` 代表任意字；短 hex 對長 sha 開頭；主張的絕對路徑對紀錄的相對路徑；`at=HH:MM:SS` 和時間區間；`AC-1 .. AC-6`；選項換順序；全形 `；` 斷句；多段主張分在幾次呼叫跑也算；從 RAN: 外開的 ``` 在那裡結束（WO-01 的 ACCEPTANCE 表格不再當成指令）；主張可能在另一條主張對到的截斷呼叫被截掉的那段時，印新狀態 **UNVERIFIED**（in log cut part）：不算 OK、也不算 FAIL，最後一行另計 `unverified=n`（放在最後，原有欄位位置不變），exit code 不變，審查的人要自己看；在截斷呼叫留下來的那段就對得到的主張仍是 OK；PowerShell 這類從不回報 error 的工具 exit 對不上印 not checkable。沒人跑過的指令照樣 FAIL。
- `gate_check.py --after-verdict <裁決.md>... --repo <專案> [--orders <資料夾>] [--strict]`（shadow）：最後一份裁決的 `CANDIDATE_HEAD` 之後，改到該工單 SCOPE 外、又不是文件（`DIRECTOR/` 底下、`.md`／`.rst`／`.txt`）的 commit 印 `~ WARN LATE_COMMIT`，exit 不變；`--strict` 判 FAIL。候選解不出印 `NOT_CHECKED`。DS 的 `--strict` 原本只配 `--resume`，現在兩者都可以。
- `templates/WORK_ORDER.md` B 節：「不做（OUT OF SCOPE）」不可留空（沒有寫「無」）；新欄「可呼叫的入口」（交付物是函式庫或工具時寫一個測試可直接呼叫的公開函式）。`templates/SPEC_REVIEW.md` 第 12 項審這兩欄（上游是第 9 項，DS 編號不同）。
- `docs/05`「派工規劃」加三行：平行線切多大、能同時就同時派、派工前估時間。
- 暫存檔放 WORK_DIR/tmp：DS 在本版 B10 已做（`dsh_session.py --temp-env`、`docs/02`、BOOTSTRAP 第 7 步）；另照上游在 `docs/11` 開 worker 流程第 3 步的提示加一句。
- `status_gen.py`（上游 2.2.4，L-059，總監驗收時發現）：產生的 `status.py` 每行原本從行尾切到 `width`，TMP 一長，路徑後面的狀態字（OK、LOW、計數）就被切掉。現在一行超過 `width` 時頭尾都留，行內最長路徑（路徑太短就整行）的中段換成 `…`，寬度上限照舊。修前在 152 字的 TMP 下實測：DISK 行尾的 `OK`、LOG 行尾的 `ago)` 都被切掉；修後都留著。DS 原本的 selftest 抓不到（`status_gen_round_trip` 只看 STATUS 標頭），新增 `status_long_path_224`。
- selftest 長路徑（上游 2.2.4 同寫法）：`selftest_ds.py` 開頭給整個 process 設 `GIT_CONFIG_COUNT`／`GIT_CONFIG_KEY_n=core.longpaths`／`GIT_CONFIG_VALUE_n=true`（原本有就接在後面），它叫起來的工具裡的 git 也吃到；release、BASE_REF 測試建的 bare origin 另外在 repo 裡設 `core.longpaths`（本機 remote 那一側不繼承環境變數）。tools 不變。修前用 152 字的 TMP 跑 selftest_ds：49 項 FAIL 5（`release_state`、`release_execute`、`base_ref_fresh`、`release_scan` 的 git push「Filename too long」，`after_verdict_224` 的 commit 寫不進去），都不是 status 造成的。DS 沒有子模組測試，所以沒有上游 `test_submodule_ignore` 的 GIT_DIR SKIP；DS 的摘要行本來就分開算 `skip=n`，格式不變。

### 已知限制
- Windows 長路徑三點寫進 `tools/README.md`「已知限制」：git 超過 260 字要 `core.longpaths`；GIT_DIR 超過約 220 字 git 本身停止；本機 remote 那一側不繼承 `GIT_CONFIG_COUNT`。
- UNVERIFIED 的主張要人看：工具只能說「可能在截斷處」，不能判斷有沒有跑。

### 遷移
- 舊的 `director_work.json` 照樣能用：`sdd.max_files_per_order`／`sdd.max_lines_per_order` 照讀（印 shadow WARN，請搬到頂層 `order_limits`）。
- `report_vs_audit.py` 最後一行多了 `unverified=n`（放在最後，原有欄位位置不變），有程式讀這一行的照樣讀得到。
- 已經產生的 `status.py` 要用 `status_gen.py --force` 重新產生，才會換成頭尾都留的截寬。
- Standard／Strict 工單驗收時一定要有 SPEC_REVIEW 紀錄（DIRECTOR_LOG.md 或 `reviews/`），舊工單沒審過的會判不過。
- 舊工單沒有「不做」「可呼叫的入口」照樣通過 `gate_check`（由規格審查看）。

### 驗證
- `selftest_ds.py` 由 37 項增為 50 項，新增：`order_limits_224`、`scope_shared_224`、`protected_tests_224`、`spec_review_224`、`protected_report_224`、`sdd_which_off_224`、`checks_paths_224`、`dsh_usage_out_224`、`effort_check_224`、`temp_env_224`，以及上游 2.2.4 的 `report_vs_audit_224`（20 個比對案例、15 個 CLI 情境、26 個 mutation，含 UNVERIFIED 兩個情境與 4 個 mutation，案例表與上游逐字相同）、`after_verdict_224`（11 個 CLI 檢查、4 個階段、5 個 mutation）、`status_long_path_224`（150 字以上資料夾，2 個 mutation）。短 TMP 和剛好 140 字的長 TMP 各跑一次，都是 50/50、skip=0。`report_skeleton` 的 fixture 補一行 SPEC_REVIEW（B4 之後沒審過的 Standard 工單會被擋）。新增 `--only <名稱>` 方便單跑（摘要行標 ONLY，不會被當成全套）。
- 每輪必讀（docs/01、03、06、08）：10,964 → 10,964 bytes。

## 2.2.3-ds.3（2026-11-14）

對應上游 2.2.3（DW commit 4f6c9e6）。這一版要讓 OpenSpec 規格層下次一定會被用上，並帶入 WO-DS-004 試驗（DSH 和 Claude 同一需求各跑一次）學到的事。版本號是 PO 指定的：上游段從 2.2.2 升到 2.2.3，ds 序號維持 3；`release.py` 的版本規則因此改成比「(上游版本, ds 序號)」整組（總監裁定，見「工具修正」）。

### OpenSpec CLI 自動偵測（試驗：本機有 CLI，規格層卻被關掉）
- 試驗裡 req-only 專案的 `sdd.openspec_bin` 是 null，本機其實裝好了 openspec 1.16.0，DSH lead 以「無網路、不能裝」自己寫 DD 把 `require_spec_for_*` 關掉，規格層完全沒用上。
- `sdd_gate.py` 依序找 CLI：`OPENSPEC_BIN` → `sdd.openspec_bin`（`%VAR%`／`$VAR`／`~` 會展開）→ `%LOCALAPPDATA%/dw-ds-tools/openspec-*/node_modules/.bin/openspec.cmd`（多版取最新；非 Windows 是 `$XDG_DATA_HOME/dw-ds-tools/…/openspec`）→ PATH。`--which` 印用哪一個、第幾層、版本；設定是 null 時印建議寫入的值（`%LOCALAPPDATA%` 寫法，不寫死使用者路徑）。設了第 1、2 層卻指錯，會判不過，不會偷偷換成後面的層。`gate_check.py` 用同一個函式。
- **找得到 CLI 時，lead 不得關 `require_spec_*`**：`gate_check.py --order` 對 `require_spec_for_<治理>` 為 false 的工單判不過，除非 `PO_PENDING.md` 有寫 require_spec 的項目，而且 PO 已回答。找不到 CLI 時照舊放行（tests-first 保留），另印 note 要寫 PO_PENDING「安裝 openspec」。
- `dsh_setup_check.py` 報告 CLI 狀態（層級、版本）；設定是 null、找不到 CLI 又沒有安裝項目、或有 CLI 卻關了 require_spec 而 PO 沒答，各印一行 shadow（`--strict` 判不過）。`dsh_doctor.py` 多一項 `openspec`（`--config` 可給專案設定），必要工具清單加上 `sdd_gate.py`、`bootstrap_repo.py`。
- 新 `tools/bootstrap_repo.py`：BOOTSTRAP 10.5 的機械步驟。找到 CLI 就寫進 null 的 `sdd.openspec_bin`（只改那一個值）、專案沒有 `openspec/` 就跑 `openspec init --tools agents --language zh-TW --no-animation`、把 `.memsearch/` 加進 `.git/info/exclude`。做過的跳過，`--check` 只報告；找不到 CLI 就印 PO_PENDING「安裝 openspec」要寫什麼，不安裝任何東西。
- 文件：BOOTSTRAP 10.5 改成「先找本機已裝的」；`docs/13` 新增「誰能關」一節，程式會擋什麼的表格和「安裝」一節更新；`docs/02`、`docs/11`、`templates/WORK_ORDER.md`、`templates/DIRECTOR_FILES.md`、`director_work.example.json` 的說明同步；`templates/AGENTS_PROJECT_SECTION.md` 加「規格層」一行。
- 冒煙驗證（不是 DSH 試驗、不用額度）：全新的暫存專案、不設 `OPENSPEC_BIN`，照 BOOTSTRAP 跑 setup_check → bootstrap_repo（寫設定、init、exclude）→ 寫一個最小 change → `gate_check --order` 實際跑 `openspec validate --strict` 通過 → 拿掉 Scenario 後判不過 → 放回又通過，16 步全過。

### 試驗心得
- **邊界與壓力清單**（上游 2.2.3 L-048，文字照搬）：`templates/WORK_ORDER.md` E 節 8 行（深度、長度、重複符號、極大數字／溢位／除以零、非字串、Unicode／全形、錯誤訊息不漏原生或英文訊息；需求寫「不當掉」至少一條極端輸入的 AC），DS 多一行 OpenSpec 寫法：用得到的每一項在 `specs/` 寫成一個 `#### Scenario:`（WHEN 極端輸入，THEN 預期結果或錯誤訊息），需求寫「不當掉」至少一個 Scenario 用極端輸入。`templates/openspec_config.yaml` 的 specs 規則加同樣兩條（實測 openspec 1.16.0 `instructions specs` 會把它們交給 agent），`docs/13` 流程第 1 步同步。
- `templates/SPEC_REVIEW.md`：新第 7 項（上游第 7 項原文：清單沒涵蓋、需求寫「不當掉」卻沒有極端輸入的 AC 算 P1；DS 加一句 Scenario 也照算），原第 7～9 項改成第 8～10 項。第 11 項**逐一重算字面期望值**改成上游第 8 項的寫法：手算、不看被測程式，每個值一行「測試名｜期望值｜怎麼算的｜相符 / 不符 / 算不出」；DS 另外連 Scenario、AC 的寫死期望值一起算，「不符」是 P0（試驗：`2 + 3 * (4 - 1)` 被寫成 9，審查沒抓到）。總監第 2 步照上游第 3 步（L-049）：重算表寫進審查紀錄，有「不符」或「算不出」就不鎖。
- 工單改版同步：`gate_check.py --order` 對 REVISION ≥2 的工單提示同步 BRIEF.md、WORK_DIR/tasks.md、WORK_DIR/RESUME_STATE.md；WORK_DIR 裡比工單舊的那兩個檔印 `~ shadow: REVISION_SYNC`（不影響結果）。`docs/02`、`templates/WORK_ORDER.md` 同步（試驗：工單改到 rev2，tasks.md 還寫 9）。
- `.memsearch/`（DSH 的記憶索引）由 `bootstrap_repo.py` 自動排除（試驗裡 lead 要自己補 DD-11）。

### 上游 2.2.3 移植（L-052～L-055）
- `report_vs_audit.py` 照上游 2.2.3 三方合併（DS 只多保留 DSH 重建紀錄的說明和 note）：換行、`;`、`&&`、`||` 切段，多段主張對得到多行腳本；`RAN:` 下 ``` 包的一段算一個主張；`at=` 只取時間、全形備註不比；`AC-1/AC-2`、`AC-1/2`、`AC-1..AC-3` 每個編號各要一筆；省略的主張（`...`、`427fcef...`、「同上」）可跳過選項；被截的行 3 個詞對到行尾也算；顯示最接近 `at=` 的那筆；後面還跑了別段的印 `not checkable` 算 OK。兩種 shadow WARN（exit code 不變）：`RAN:` 一行沒有 `` `指令` ``；`SCOPE_CHECK: PASS` 但做事的 agent 最後一次 commit 之後沒再跑 `scope_check.py`。
  - 用 WO-DS-004 的封存輸入重跑（只讀，輸出在 WORK_DIR）：DSH 報告 FAIL 6 → PASS 11/11；Claude 報告 FAIL 2（剩下兩筆紀錄裡確實沒有），和 DW 2.2.3 的結果相同。
- `evidence_record.py` 和上游 2.2.3 逐位元相同：`verify --rerun` 的 CHECK 可以寫裸 `git`，只限唯讀子指令（diff、show、log、status、rev-parse、ls-files、cat-file）；子指令前的選項、其他子指令、會寫檔或執行程式的選項（縮寫也算）照樣 `NOT_RUN`、exit 2。在 `--repo` 頂層跑，關掉 replace 物件、fsmonitor、pager、optional locks、外部 diff、textconv，跑完照舊重讀 repo。
- `docs/02`：暫存檔放 WORK_DIR，不放 scratchpad 或系統暫存資料夾（L-053）；「AC 用 git」一段（唯讀 git，或改用 TESTS_LOCKED sha256）。`templates/TASK_REPORT.md` 的 RAN 段提醒一句。`tools/README.md`、`tools/DSH-TOOLS.md` 同步。
- 不搬：上游 `selftest.py` 的案例（DS 用自己的 `selftest_ds.py`，見「驗證」）。

### 工具修正
- `verify_dsh_run.py` D06：改看每個寫入動作的目標（cmdlet 路徑參數、重新導向、.NET File、node fs、rm／mv／cp，變數照腳本自己的字串展開），`tools.*(...)` 用括號配對剝除（跳過字串、樣板字串、regex、註解）；解不出目標時退回舊規則。ds.3 重跑原本誤判 FAIL，現在 34/34。
- `verify_dsh_run.py` D13：`is_write` 用同一個剝除（原本只「提到」檔名的 run_code 被算成改檔，返工 5 次 → 2 次、改工單 4 次 → 0 次）；步驟分界改成「第一個動作所在的那一輪」（`round_of`），第 8／9 步不再互相吃掉輪數。`calls_full.jsonl` 多存 `session`、`cwd`、`top`。
- 回歸測試：`tools/test_verify_dsh_run.py` 新增 8 項（D06 5、D13 3），共 33；fixture 是 ds.3 重跑的紀錄，放在 `tools/fixtures/`，使用者資料夾路徑換成 `%LOCALAPPDATA%`。
- `release.py` 版本規則（總監裁定 WO-DS-005 C）：「(上游版本, ds 序號)」整組要比遠端所有 tag 新、tag 還不存在；ds 序號不再單獨比。v2.2.2-ds.3 之後的 2.2.3-ds.3 可以，2.2.2-ds.2、2.2.2-ds.3 會停；沒有旗標可以跳過。`DEEPSEEK-PORT.md` 第 10 節、`docs/02`、`tools/README.md` 同步。

### token（只用 WO-DS-004 的現有紀錄，沒有新跑）
- DSH 一次 20.60M，lead 佔 14.39M（159 步，output 0.9%）。lead 的大項：自己的推理和呼叫重送 24.9%、系統提示 17.5%、規則包文件 10.9%、工具原始碼和 `--help` 8.5%、同一檔重讀 3.7%。
- 本版改了兩條規則：BOOTSTRAP 第 1 步「每支工具只讀一次，之後不重讀、不跑 `--help`，用法查 `tools/DSH-TOOLS.md`」（重讀加 `--help` 約 0.76M）；`docs/13`「省 token」第 8 條「讀過的檔不整份重讀」（其他檔重讀約 0.20M）。合計上限約 0.96M（lead 的 6.7%），要下次實機才知道實際省多少。
- 每輪必讀的 bytes：`docs/01`、`03`、`06`、`08` 合計 10,964，本版沒改（B3、B9 只改範本、`docs/02`、`docs/13`，寫工單、審規格、交件時才讀）；AGENTS 總監段落範本 2,360 → 2,601（＋241，「規格層」一行，估計約多 0.02%）。

### 下一版
- BOOTSTRAP 的讀檔清單分成「建置必讀」和「用到再讀」，或讓短上下文的子代理讀完回摘要：規則包文件佔 lead 的 10.9%，但會改變 lead 的讀法，要實機驗證不漏規則才改。
- 改檔用 `edit` 只送改的段落、不整份重寫：lead 自己的推理和呼叫重送佔 24.9%，其中有整份工單、初衷卡的內容，還沒量過。

### 驗證
- `selftest_ds.py` 30 → 37 項（新增 `sdd_cli_lookup`、`sdd_cli_setup`、`sdd_spec_off_gate`、`revision_sync`、`bootstrap_repo`；上游 2.2.3 移植的 `matching_223`（15 個比對案例、14 次 CLI 執行、16 個 mutation 都被抓到，案例取自上游 selftest）和 `evidence_git_223`（8 個允許、10 個拒跑、git_argv 的旗標、4 個 mutation）；`setup_shadow`、`report_skeleton`、`release_state` 更新），設與不設 `OPENSPEC_BIN` 各跑一次都全過；不設時 `sdd_real_openspec` 從第 3 層找到真的 CLI。
- `verify_dsh_run.py` 對 ds.3 重跑 34/34；`test_verify_dsh_run.py` 33/33。

## 2.2.2-ds.3（2026-11-14）

ds.3 對應上游 2.2.2，是工具版：發版一次到位、派工前確認 BASE_REF 是最新的、DSH 試跑驗證器通用化、根據 WO-101 實機紀錄的量測減少 DSH 的 token 用量，並移植上游 2.2.2 的 RESUME_STATE 大小檢查和原文搬移工具。工單格式沒有變；新的檢查預設只提示，不會讓舊工單判不過。

### 上游 2.2.2 移植：RESUME_STATE 大小（shadow）與 resume_archive.py
- 問題：RESUME_STATE 每次續接都整份讀進 context，DSH 每一步又重送整段對話；表頭 `Before:` 鏈越接越長。上游實測一份 115,026 bytes（約 57,513 token），最長一行 32,699 bytes。
- `memory_size_check.py --kind resume`：一次量多份（`--file` 多次、`--glob`、`--workstreams <ACTIVE_WORKSTREAMS.md>`），每檔一行（bytes、~token、最長行、可搬 bytes），最後一行 `SIZE: PASS|OVER|MISSING`；上限 20480 bytes、單行 4096（`director_work.json` 的 `resume.max_bytes`、`resume.max_line_bytes`）。只讀。單檔舊用法輸出不變，預設仍找最近的 `AGENTS.md`。
- `gate_check.py --resume`：超過時印 `~ shadow: RESUME_SIZE ...`，exit code 不變；`--strict` 才判不過；`--config` 讀上限。
- `dsh_setup_check.py`：RESUME_STATE 加大小檢查（shadow）；`director_work.json` 多查 `resume`、`base_ref`、`release` 區塊的型別；`sdd`／`resume`／`base_ref`／`release` 不再被誤報成「keys no tool reads」。
- 新 `tools/resume_archive.py`（上游原樣）：「壓縮」只代表原文搬到同資料夾 `RESUME_HISTORY_<YYYYMMDD>.md`，原處留索引（日期、歷史檔、sha256）。近期只看筆數（`resume.keep_recent`，預設 10），沒有 keep_days；四行表頭仍四行，`Before:` 鏈保留現況和最新 10 筆、只搬更舊的尾段；現況、保護標題（`resume.protect_headings`）、沒有完整日期的段落都不動；順序或筆數看不清就不搬並印 shadow。預設 dry-run；`--execute` 先寫 `.bak`，搬完驗 (a) 歷史檔逐字含搬走的內容 (b) 留下的部分 sha256 不變 (c) 放回去等於原檔，任一項不過就還原並 exit 1。
- `gate_check --order` 的 `base_ref` 讀法換成上游版：開關不是 true／false 會印 note 並用預設（以前靜默照用，字串 `"false"` 會被當成真）；設定檔先找工單資料夾再找上一層；BASE_REF 沒寫 commit 時不再印 note（和上游一樣，舊工單輸出不變）。
- `release.py` 從上游 2.2.2 帶回：`main(argv)`、公開掃描多擋 `CLAUDE.local.md`／`.claude/settings.local.json`／Claude session 紀錄。兩邊的工作樹與版本規則本來就一致。
- 文件：`docs/06` 的 gate_check 那一行加大小一句；細節在 `docs/06b`「RESUME_STATE 瘦身」和巡查第 4 步；`docs/02` 加「發版」一節；`templates/RESUME_STATE.md` 註明上限；`CHANGELOG-upstream.md` 附上游 2.2.2 段。逐檔差異和理由見 `DEEPSEEK-PORT.md` 第 12 節。
- 只由各工作線自己跑 resume_archive（總監巡查時用 memory_size_check 量），不是每輪步驟。

### 工具
- 新增 `tools/release.py`：發版一次跑完（fetch → 和遠端分支比落後／分岔 → VERSION＝CHANGELOG 最上面一段、版本比遠端所有 tag 新 → selftest → 公開掃描 → push → `ls-remote` 確認 → annotated tag → push tag → `ls-remote` 確認 → `gh release create --latest --verify-tag` → `gh release view`）。
  - 預設只演練；加 `--execute` 才動遠端。
  - `--merge`：分岔時開 `release/<版本>` 做 `merge --no-ff`，有衝突就停並列出檔案；演練時用 `git merge-tree` 先預測衝突。
  - 公開掃描範圍：金鑰與 token 格式（沿用 `secret_mask.py`）、`key = value` 形式的密碼、noreply 和 `*.invalid` 以外的 email、使用者資料夾路徑、`DIRECTOR/`、`_work/`、`AGENTS.local.md`、DSH session 檔、commit 訊息與作者 email。找到時不印出密碼本身；有 gitleaks 時一併跑。
  - 中途停掉後重跑，已完成的步驟會跳過。
  - VERSION 和 CHANGELOG 從 HEAD 讀（`git show HEAD:…`）；任何 tracked 檔有沒 commit 的改動就停（演練也一樣），避免 tag 名稱和 tag 裡的 VERSION 對不上（總監演練時抓到；DW 的 release.py 同樣修法）。
  - 版本檢查：整個版本號要比遠端所有 tag 新，而且 `-ds.N` 要比遠端所有 `-ds.*` tag 的 N 大（流水號不因上游換版本歸 1；規則寫在 `DEEPSEEK-PORT.md` 第 10 節）。
  - 選型：release-please 和 semantic-release 都要 CI 和 conventional commits，semver 也排不出 `2.2.1-ds.N`，所以不用；`gh release create` 已有 `--verify-tag`、`--notes-file`、`--latest`，直接用。
- `gate_check.py --order` 檢查 BASE_REF 是否最新：先自己 `git fetch`，再把 BASE_REF 的 commit 和遠端分支比。
  - 不存在或落後：印 `~ WARN BASE_REF`。
  - fetch 失敗或沒有遠端：明說「沒和遠端比」，不會靜默通過。
  - `--strict-base`：上面三種都改成判不過。
  - 開關在 `director_work.json` 的 `"base_ref"`。
- `gate_check.py --report-skeleton 工單 [--repo] [--evidence-dir] [--out]`：照工單產生 TASK REPORT 骨架，並印出錄證據（照 CHECKS）、scope_check、`--match` 的完整指令。
  - 已先填好：TASK_ID、worker、模型、BASE、ORDER、ORDER_SHA256，以及每條 AC 一列（附該類型可填的狀態）。
  - 骨架沒填完，`--report` 會判有 placeholder。
- 新增 `tools/verify_dsh_run.py`：DSH 試跑驗證器，由 ds.2 的 WO-101 `verify_run.py` 通用化。
  - R01–R21 看 repo，D01–D14 看 DSH session 紀錄。
  - 工單專屬的檔名、代理名、隱藏 oracle 寫在設定檔（`templates/VERIFY_DSH_RUN.json`）；CLI 參數優先於設定檔。
  - 用 WO-101 重跑：34/34 PASS，37 列結果和 ds.2 那次相同。
  - 修正兩個從 ds.2 帶來的錯：
    - 輪數表（D13）的「8 驗收」原本抓到規格審查期間的 `scope_check.py --help`；
    - 「9 裁決」「10 總結」原本永遠找不到。
- 新增 `tools/test_verify_dsh_run.py`（25 個單元測試：原本的 11 個 D08 案例，加設定、合成試跑和 D13 輪數表的步驟標記）。

### 省 token（先量測再改）
- 量測對象：WO-101 實機紀錄，共 829 萬 token、102 步。
  - 每步重送的固定部分約 46K token，佔 57%；所以步數是最大的成本。
  - worker 約 8 步在讀檢查器原始碼學報告格式；lead 約 13 步在試 provider、讀 `--help` 和解析程式。
- `docs/13` 新增「省 token（ds.3）」：7 條規則和一張指令表。
- 預估同一任務總 token 降 58%～60%（S 取 42K～49K、推理內容算或不算重送，都在這個範圍）。這是推算，還沒有 DSH 實機重跑；重跑列為 PO 選做步驟。
- `templates/TASK_REPORT.md`、`docs/02`：開工先跑 `--report-skeleton`。

### 文件
- `docs/02`：BASE_REF 新鮮度、`--report-skeleton`。
- `templates/WORK_ORDER.md`：BASE_REF 註明先 `git fetch`，格式 `<remote/branch @ commit>`。
- `docs/13`：省 token 一節、已知限制改指 `verify_dsh_run.py`。
- `BOOTSTRAP.md`：開線那一輪的 BASE_REF 提示，10.5 第 6 點（省 token、試跑驗證）。
- `DEEPSEEK-PORT.md` 第 10 節：發版用 `release.py`；版本號規則 `<上游版本>-ds.<N>`，N 一直往上加。
- `README.md`、`tools/README.md`、`tools/DSH-TOOLS.md`、`director_work.example.json`（`"release"`、`"base_ref"`、`"resume"` 三段）。
- `DEEPSEEK-PORT.md` 第 12 節：上游 2.2.2 逐檔比較與每個差異的理由。

### 驗證
- `selftest_ds.py` 30/30 PASS（OpenSpec 1.16.0 實機），新增 8 項：`release_state`、`release_execute`、`release_scan`、`base_ref_fresh`、`report_skeleton`、`verify_dsh_run_unit`、`resume_size`、`resume_archive`（後兩項是上游 2.2.2 的測試案例改寫，含 11 個突變都被抓到）。2.2.1-ds.2 是 22/22。
- `verify_dsh_run.py` 用 WO-101 設定：`VERIFY_DSH_RUN: PASS pass=34 fail=0 skip=0`。
- 上游 A5 的 115,026 bytes RESUME_STATE 複本：`gate_check --resume` 多一行 `~ shadow: RESUME_SIZE 115026 bytes ... ~57513 tokens, longest line 1: 32699 bytes`，exit code 和 2.2.1-ds.2 相同（都是 1，原因是檔裡原有的 placeholder，不是大小），`--strict` 時大小變成問題；`resume_archive --execute` 115,026 → 57,472 bytes（少 57,554 bytes，約 28,777 token），19 段 60,162 bytes 原文搬到歷史檔，(a)(b)(c) 都過，搬後的檔和上游 A5 結果逐 byte 相同（sha256 68efb13b…）。
- 每輪必讀：10,947 → 10,964 bytes（上限 11,000）。本版沒有新增每輪必讀的檔案或步驟：release.py 只在發版時跑，BASE_REF 只在派工時跑，resume_archive 只由各工作線自己跑。

對齊初衷：
1. 幫到誰：每次續接都整份讀 RESUME_STATE 的工作線（實測少讀一半）、派工的總監（從舊 commit 開工會先看到 WARN）、發版的人（從 HEAD 發、每步驗證）、DSH 的 worker（少讀原始碼、少走步）。依據：PO 2026-11-14 指示、WO-DS-003 REVISION 5、上游 WO-DW-222。
2. 平台：全是本機命令列工具，只用標準庫；release.py 需要 git 和 gh。
3. 服務：初衷 4（中斷不丟進度）：搬移是原文、可逐 byte 還原；初衷 5（成品要真的對）：發版從 HEAD；初衷 7（零成本）：額外花的少於省下的。
4. 核心：每輪必讀 10,964 bytes，仍在 11,000 以內；新檢查先 shadow／WARN。
5. 舊檔案和舊指令照樣能用；`memory_size_check` 單檔用法輸出不變。

## 2.2.1-ds.2（2026-11-14）

ds.2 SDD 建在 2.2.1-ds.1 之上：本版把 ds.2 分支（原本從 2.2.0-ds.1 開出，沒有單獨發佈）merge 進 2.2.1-ds.1。2.2.1-ds.1 從上游移植的工具改動全部保留，再加上 ds.2 的 SDD／OpenSpec。ds.2 分支上的小修正：`memory_size_check.py` 補 `import re`（上游沒有，帶進來）；`dsh_setup_check.py` 把 `CH-xx` 當完整條目的那一個不帶，改用 2.2.1-ds.1 已有的修法（`OD/ACT` 以外的 `ID:` 行跳過並提示，selftest `setup_shadow` 有測）。

規格先行（SDD）：DSH 上的 worker（deepseek-flash）判斷力較弱，所以規格、驗收測試和計畫在寫程式前寫死並鎖住。規格層採用現成的 OpenSpec（Fission-AI/OpenSpec，MIT，鎖 1.16.0），DW-DS 只寫膠水。完整說明見 `docs/13_sdd_openspec.md`。

### 規則（`director_work.json` 的 `"sdd"` 開關，預設全開）
- Standard／Strict 工單必填 `SPEC_CHANGE = openspec/changes/<名稱>`；`gate_check.py --order / --match` 會實際跑 `openspec validate <名稱> --strict --json`，找不到 CLI 判不過（不會靜默通過）。Strict 的變更不能 `skip_specs: true`。
- 規格審查從「只有 Strict」改成 Standard 也必做（`--match --dispatch-log` 查 `SPEC_REVIEW <WO>` 行）。
- 測試先寫：`TESTS_LOCKED:` 記驗收測試的 sha256（`sdd_gate.py --lock-tests` 產生）；被改就判不過。
- 計畫閘門：worker 先交 OpenSpec 的 `tasks.md`，總監核准後記 `PLAN_APPROVED <WO> sha=<64>`；交件時 tasks.md 只准比核准版多打勾，而且要全部勾完（勾選規則照 OpenSpec）。
- 工單大小：最後結果 ≤3 個檔、≤200 行（`openspec/` 不算），`scope_check.py` 超過印 `OVERSIZE`。
- STOP_RULES：同一根因 1 輪沒進展就停（原 2 輪）。
- 沒有 AUTO 驗收時提示（優先 AUTO）。

### 工具
- 新增 `tools/sdd_gate.py`：上述檢查的共用模組（`gate_check.py`、`scope_check.py` 載入），CLI `--lock-tests`、`--plan-hash`、`--which`。每段註明 OpenSpec 為什麼沒有這個功能。
- `gate_check.py`：`--order / --match` 接 SDD 檢查；`--repo` 可用在 `--order / --match`（專案 checkout）；新增 `--config`。
- `scope_check.py`：Standard／Strict 工單的大小上限（`SIZE:`／`OVERSIZE`）；新增 `--config`。
- `selftest_ds.py`：新增 8 個 `sdd_*` 測試（含「NONE 但 Standard」「validate 失敗」「找不到 CLI」三個負面案例，及改測試、停止規則、計畫被改、大小超過）；`sdd_real_openspec` 用真的 CLI（找不到就 SKIP）。

### 文件與範本
- 新增 `docs/13_sdd_openspec.md`（流程、開關、原生 vs 膠水、安裝、OpenSpec vs Spec Kit 選型、已知限制）。
- 更新 `docs/02`（規格先行一節、規格審查）、`docs/05`（SDD 時怎麼分 effort）、`docs/11`（OpenSpec 在 DSH 上的操作）、`BOOTSTRAP.md`（10.5 規格先行工具）、`README.md`、`DEEPSEEK-PORT.md` 第 11 節、`tools/README.md`。
- `templates/WORK_ORDER.md`：`SPEC_CHANGE`、`TESTS_LOCKED`、大小上限、計畫閘門、STOP_RULES 1 輪；`templates/SPEC_REVIEW.md`：Standard 必做、加審 OpenSpec 變更三題。
- 新增 `templates/openspec_config.yaml`（OpenSpec 原生 `rules:`／`operations:`）；`director_work.example.json` 附上完整的 `"sdd"` 物件（全開，`openspec_bin: null`），說明在 `docs/13`。
- `metrics_report.py`：「額度用量」列改指 DSH 版的 `dsh_usage.py`（原本指 Claude 版的 `usage_report.py`，本版已移除）。

### 升級注意
- 預設全開：舊的 Standard／Strict 工單沒有 `SPEC_CHANGE`／`TESTS_LOCKED`、STOP_RULES 寫 2 輪，`gate_check.py --order` 會判不過。舊工單用 `--warn`／`--since`，或在專案 `director_work.json` 把對應開關設成 `false`。
- 沒裝 OpenSpec 的專案：關掉 `require_spec_for_standard`／`require_spec_for_strict`（BOOTSTRAP 10.5 第 5 點）。

### 驗證
- `selftest_ds.py`：2.2.1-ds.1 的 14 項加 ds.2 的 8 個 `sdd_*` → 22/22 PASS（`OPENSPEC_BIN` 指到實機 OpenSpec 1.16.0）；不設時 21 PASS、1 SKIP（`sdd_real_openspec`）。ds.2 分支在 2.2.0-ds.1 上是 11/11 → 19/19。
- 試跑找到並已修進來：`validate --strict` 要求 Requirement 含英文 SHALL／MUST（改用原生 `init --language zh-TW`）；archive 後主規格 Purpose 要 ≥50 字元；`python -I -m unittest <模組>` 找不到 cwd 的測試（CHECKS 改 `discover -s .`）；交件時未勾的任務原本不查。
- 試跑：`_work/demo-project` 一張 Standard 工單走完 propose → 審查 → tasks 核准 → apply → 交件檢查 → archive，見 `_work/ds2-openspec/TRIAL.md`（Claude 模擬 worker）。DSH 實機（deepseek-flash）：PO 照 `_work/ds2-openspec/PO_RUN.md` 貼一段 prompt 跑完，總監照 `_work/ds2-openspec/VERIFY.md` 驗，34/34 PASS；踩到的注意事項寫在 `docs/13`「DSH 實機注意」。

## 2.2.1-ds.1（2026-11-14）

對應上游 2.2.1（`CHANGELOG-upstream.md` 已加上游 2.2.1 全文；上游 dw-221 commit 7a6091e）。上游 2.2.1 只改工具，沒有改規則文件；本版搬三項工具變更，另修 2.2.0-ds.1 的幾處說明錯誤。流程核心不變。

### 工具（對應上游 2.2.1）
- `report_vs_audit.py`：換成上游 2.2.1 版。被截在 500 字的紀錄行照 JSON 字串解回 `\"`、`\\`，長的 Windows／UNC／含引號指令對得上；沒被截的指令不再當成截斷（較長的主張不會靠前綴通過）；單字比對至少要 2 個不是 `...`／`<名稱>` 的字（只寫 `python -I -X utf8` 不再假通過）。DSH 的部分保留：`pwsh` 算 shell 工具、說明寫 PTC 包殼。讀到 `kind=rebuild` 的紀錄時印 `~ note: a log was rebuilt after the fact (dsh_audit.py) ...`（上游的字樣寫 transcript，DSH 改寫成重建來源）。
- `dsh_setup_check.py`：加上游 2.2.1 setup_check 的 shadow 檢查，印 `~ shadow: ...`，`--strict` 才算失敗：PO_PENDING 的 ID 重複（OD/ACT 以外的 `ID:` 行與缺 CREATED 只是提示）；RESUME_STATE 標頭四行有值、UPDATED 有日期（用 `gate_check.check_resume`，四行順序仍照舊算失敗）；director_work.json 的 `schema_version` 1、`mode`、三個 `*_pattern` 是合法正規式、`po_pending_files` 是字串清單；Claude 專用鍵（window、plugins_off、hooks……）和不認得的鍵只提示。DSH 原本就有的欄位、STATUS、答案、順序檢查不變。
- `dsh_setup_check.py` bug：OD/ACT 以外的 `ID:` 行（例如範例設定允許的 `CH-xx`）後面的欄位，原本會算到上一筆，誤報「STATUS 出現 2 次」。現在那一行之後不再算進上一筆。
- `dsh_audit.py`（build 版本 1 → 2）：建出的紀錄第 1 行是 `kind=rebuild`，`source` 記 `by: dsh_audit.py`、版本、讀了哪些 session 檔（檔名、sha256、大小）、行數、警告與略過數，和上游 `transcript_audit.py` 的第 1 行同格式；工具呼叫從 seq 2 起，`head_seq` 含這一行。串鏈抽成 `chain_lines()` 好測。
- 上游新工具 `transcript_audit.py` 不搬：它讀 Claude Code transcript，DSH 沒有這種檔；DSH 的事後重建本來就是 `dsh_audit.py`（記於 `DEEPSEEK-PORT.md` 第 7 節）。

### 說明更正（2.2.0-ds.1 寫了但沒做）
- `pause_ctl.py`：2.2.0-ds.1 的 CHANGELOG 與 `DEEPSEEK-PORT.md` 說「移除 hook 自動檢查假設」，實際檔案和上游一模一樣，說明仍寫 `hook_guard.py --pause-flag` 會擋每個工具呼叫。本版才改：DSH 沒有 hook，旗標要 worker 自己讀（`pause_ctl.py status` 或 `dsh_guard.py --pause-flag`），總監審查時核對；不看的 worker 照樣能動作。
- `status_gen.py`：說明與 `~ PENDING_METHOD_MISSING` 提示原本寫「worker 用 ask_user_question 問 PO」，和平台事實相反（子代理呼叫會被拒，DELEGATED_CALLER）。改成：總監（根 session）用 `ask_user_question`，worker 經「總監」。
- `dsh_session.py`：「REWRITE-GUIDE section 0」是本 repo 沒有的文件，改指 `docs/01_roles_authority.md`、`docs/11_dsh_operations.md`。
- `BOOTSTRAP.md`、`README.md`：上游版本改寫 v2.2.1。

### 遷移
- `dsh_audit.py` 新建的紀錄多一行第 1 行，seq 往後移 1；舊檔不受影響，舊的 AUDIT_RANGE／錨點照舊對舊檔。要比對新舊 build 時注意這一行。
- `dsh_setup_check.py` 新檢查是 shadow，exit code 不變；用 `--strict` 前，範本的範例條目（`ID: OD-01（要 PO 決定）或 ACT-01……`）與佔位會被提示。

### 驗證
- `selftest_ds.py`：11 項 → 14 項（新增 `matching_221`：21 個比對案例＋2 個 CLI＋6 個突變都被抓到；`setup_shadow`：7 種錯誤 shadow 不失敗、`--strict` 失敗，乾淨資料夾 `--strict` 通過，5 種提示；`audit_rebuild`：第 1 行、verify、改過的行被拒、report 的 note）。`dsh_audit_and_report` 改成檢查第 1 行是 rebuild，session_id 從後面的行取。紀錄：`D:/DIRECTOR-WORK-HANDOFF/v221/selftest_ds_221.log`。
- 沒測到的（已知限制）：`dsh_audit build` 只在本機現有的 DSH session 紀錄上跑過（selftest 的 `dsh_audit_and_report`），沒在 DSH 裡實際跑一輪派工；比較報告 D 節列的沙箱、`git clone` 啟動流程仍未實測。

對齊初衷：
1. 幫到誰：DSH 版的總監（核對報告不再誤判或假通過、建置檢查多看三個檔案）、讀文件的人（暫停旗標與 PO 管道的說明和平台事實一致）。依據：DeepSeek 版與 2.2.0 的比較報告 A 節、A3。
2. 平台：全是本機命令列工具；DSH 沒有 hook，所以暫停與紀錄都寫明是自己讀、事後重建。
3. 服務：初衷 5（成品要真的對）：核對不假通過；初衷 7（零成本）：只用標準庫。
4. 核心：每輪必讀不變；新檢查先 shadow。
5. 舊檔案：照樣能讀；`report_vs_audit` 原本判錯的那幾類結果會變。

## 2.2.0-ds.1（2026-11-12）

第一個 DeepSeek Harness 版，對應上游 2.2.0。流程核心（角色、工單、gate、證據、續航、初衷卡）不變，平台層重寫。

### 文件
- `README.md`：啟動提示詞、流程說明、FAQ、檔案地圖改成 DeepSeek Harness 版；新增「Claude 版和 DeepSeek 版有什麼不同」與防護對照。
- `BOOTSTRAP.md`：0～14 步改寫。待決頁改成本機 `PO_PENDING.md`＋`ask_user_question`；壓縮門檻與 context_probe 改成 DSH 設定、子代理名額、指示載入確認與 `dsh_usage.py` 基準；開 worker 改成 `subagent`；外掛清單步驟改成「不移植、只列給 PO」。
- `docs/04_quota_efficiency.md`：改成 token 計價、1,048,576 上下文、KV cache、自動壓縮與 `dsh_usage.py` 量測。
- `docs/05_models_effort.md`：只有 `deepseek-flash`，effort 改成 `off/low/high/max`；子代理開工時選 effort、不能中途改。
- `docs/09_memory.md`：改成 AGENTS.md 指示鏈（每條 64 KiB）與 DIRECTOR 檔案，沒有 MEMORY.md。
- `docs/11_dsh_operations.md`（取代 `11_claude_desktop.md`）：能力→DSH 工具對照、開 worker 流程、限制清單。
- `docs/12_chat_to_product.md`：選擇頁改成聊天附圖＋`ask_user_question`，移除 Artifact 與 choice 帳本機制。
- 其餘 docs（01、02、03、06、06b、07、08、10）做平台名詞與工具替換；不自稱 DSH 沒有的能力。檔名對齊內容：`01_roles_authority.md`、`06_resume_lossless.md`、`06b_on_demand_procedures.md`、`08_safety_rules.md`；每輪必讀四份實測 10,947 bytes（上限 11,000，記於 `DEEPSEEK-PORT.md`）。
- `PURPOSE.md`：原文保留（只有 PO 能改）；其中「Claude Code／Claude Desktop」字樣屬歷史敘述，PO 可視需要自行更新。

### 範本
- `templates/AGENTS_PROJECT_SECTION.md`（取代 `CLAUDE_PROJECT_SECTION.md`）。
- `templates/PO_PENDING.md` 改成待決帳（`ask_user_question`＋本機帳）。
- `templates/RESUME_STATE.md` 的 session 欄位改子代理名稱。
- 移除 `templates/choice_page.html`、`templates/settings.runtime-guard.json`、`templates/guard_sessions.json`。
- 其餘工單／報告／裁決／測試申請／初衷卡／DIRECTOR 骨架照原版小幅替換。

### 工具
- 保留（平台中立）：`gate_check.py`、`scope_check.py`、`evidence_record.py`、`report_vs_audit.py`、`trace_report.py`、`round_check.py`、`status_gen.py`、`metrics_report.py`、`memory_size_check.py`、`secret_mask.py`、`pause_ctl.py`、`audit_log.py`（verify／head／cite／recover）、`vocabulary.json`；其中 `report_vs_audit.py`（DSH 包殼比對）、`status_gen.py`（吃 po_pending）、`memory_size_check.py`（預設 AGENTS.md）、`pause_ctl.py`（無 hook 自動檢查；更正：本版實際沒改，2.2.1-ds.1 才改）、`audit_log.py`（append 不用）做了小幅適配。
- 新增：`dsh_session.py`（共用庫：找 Node、解 session zstd、列 session、agent 名稱映射）、`dsh_usage.py`（token 用量與上下文）、`dsh_audit.py`（從 session 紀錄重建動作）、`dsh_doctor.py`（環境檢查）、`dsh_setup_check.py`（DIRECTOR 建置檢查）、`dsh_guard.py`（選用的風險指令自我提醒）、`selftest_ds.py`（冒煙測試）。
- 移除：`hook_guard.py`、`setup_project_settings.py`、`context_probe.py`、`usage_report.py`、`usage_mix.py`、`doctor.py`、`setup_check.py`、`choice_reconcile.py`、`browser_check.py`、`poll_hint.py`、`selftest.py`、`container/`。
- `director_work.example.json`：移除 Claude 專用欄位（window、plugins_off、hooks、protect_director、director_worktree）。

### 沒做（NOT_PORTED）
- PreToolUse hooks 與命令層自動阻擋（DSH 沒有 hook 機制）。
- Artifact 私人頁面、置頂、留言叫醒、choice 資料庫與收條。
- 容器 worker、WSL 隔離、網路出口管制。
- 專案級外掛開關、記憶索引 MEMORY.md、Monitor、notify_when_idle、session 封存、interrupt_agent、讀取他人 context 的工具。
- 輸出：`tools/selftest_ds.py` 只冒煙測試 DeepSeek 版工具，不重寫上游 527 KB 的 selftest。

### 驗證
- 端到端 demo：`_work/demo-project` 用 WO-001（加 multiply）派給子代理 w1，交件 HEAD `d675820dfc9a27638951cb00ebc22729a37d2fdb`；總監親跑 gate_check（--order/--hash/--match/--verdict）、scope_check、evidence_record verify --rerun、dsh_audit build+verify（141 筆）、report_vs_audit（8/8 PASS）全綠；裁決 PASS → ACCEPT_AND_CLOSE（NO MERGE / NO PUSH）。
- 工具鏈：`selftest_ds.py` PASS 11/11；`dsh_doctor.py` PASS 12/12；`dsh_setup_check.py` 對 demo DIRECTOR PASS；`dsh_usage.py --session w1` 讀到 effort/context%（10.8%）。
- 子代理平台：AGENTS.md 自動載入、可 send_message 回總監、可續談；worker 不能 ask_user_question（DELEGATED_CALLER）。
- 文件：必讀四份 10,947 bytes（上限 11,000）；`RAN` 截斷規則與 `--project-dir`/`--session` 語意已按實測修正。
- 完整實測指令與輸出見 `DEEPSEEK-PORT.md` 第 8 節。

### 升級
- 上游有新版時，先看 `CHANGELOG-upstream.md` 的該版變更，只把「規則與工單格式」的變更搬過來；平台層（docs/04、05、11、12、BOOTSTRAP 的 DSH 段落）以本版為準。
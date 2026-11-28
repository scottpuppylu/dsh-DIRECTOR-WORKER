# adapters/deepseek：DeepSeek Harness 轉接層（dsh-DIRECTOR-WORKER 3.0.0-ds.8）

這個資料夾是 dshdw 和基板 DIRECTOR-WORK 3.0.0 唯一的差別（另外改了四個基板檔，見根目錄 README「沿用上游」）。
裝到專案時放在 `<REPO>/DIRECTOR/adapters/deepseek/`，基板工具在 `<REPO>/DIRECTOR/tools/`：DSH 工具先找自己的資料夾，再找兩層上的 `tools/`。
所有工具只用標準函式庫，Python 3.9 以上；最後一行是 `<名稱>: PASS|FAIL ...` 這類結論，exit 0 才算過，沒有結束碼（逾時、被殺、啟動失敗）一律當失敗。

## 新增（基板沒有的）

| 檔案 | 做什麼 | 為什麼基板沒有 |
|---|---|---|
| `dsh_dispatch.py` | 開 worker 前跑：spec_gate、`gate_check --hash`、`worktree.py open`，三步都 exit 0 才印 `DSH_DISPATCH: GO` | 基板靠 Claude Code 的 PreToolUse hook 擋；DSH 沒有 hook |
| `dsh_setup_check.py` | 第 13 步檢查 `DIRECTOR/`（`PENDING_METHOD`、`PO_PENDING.md` 格式、`INDEX.md`） | DSH 沒有私人網頁，待決帳格式不同 |
| `dsh_usage.py` | 從 DSH 的 session 快取算 token 和上下文 | 基板的 `get_usage` 是 Claude Desktop 工具 |
| `dsh_audit.py` | 從 DSH session 紀錄事後重建動作紀錄（`build`／`verify`）、打轉（`loops`，核心是基板 `loop_guard`）、讀檔量（`reads`） | 基板靠 PostToolUse hook 即時寫 |
| `dsh_session.py` | 讀 DSH session 資料的共用函式庫 | DSH 的紀錄格式 |
| `dsh_doctor.py` | 環境自我檢查（Python、Node、DSH 資料夾、工具齊不齊） | 基板 `doctor.py` 查的是 Claude 設定 |
| `dsh_guard.py` | 危險指令自我檢查（用基板 `guard_rules.json`），只提醒不攔 | 基板 `hook_guard.py` 是 hook |
| `verify_dsh_run.py`、`test_verify_dsh_run.py`、`VERIFY_DSH_RUN.json`、`fixtures/` | 不信 DSH 自述，從檔案和紀錄驗一次試跑 | DSH 試跑專用 |
| `ds_version.py` | 版號 `<BASE_VERSION>-ds.<N>`，N 比之前每一版都大（序號接續，不歸零） | 變體自己的序號規則 |
| `release_ds.py` | 發版：`ds_version` → `base_sync_check` → `selftest_deepseek` → 基板 `release.py` | 同上 |
| `base_sync_check.py`、`BASE_SYNC.json` | 每個基板檔逐位元組相同，或登記成覆寫並寫理由；`base_sync_check.py` 只是入口，呼叫基板 `tools/base_sync_check.py`（B6） | 登記表是變體才有的 |
| `VARIANT.json` | `default_strength` light（基板 `safety_gate.py` 讀，B15）；`rules_section` 指向 `AGENTS_PROJECT_SECTION.md`（量必讀鏈時算進去，B19） | 基板的預設是 standard、範本是 `CLAUDE.md` |
| `install_deepseek.py` | 把本資料夾裝進 `<REPO>/DIRECTOR/adapters/deepseek/`，先備份、驗雜湊 | 基板 `install.py` 只裝 `tools/` |
| `selftest_deepseek.py` | 本資料夾的測試 | 同上 |
| `DSH_EFFORT_TABLE.json` | DSH 的 effort 表（off／low／high／max，出自 ds.7；`mechanical` 可用 off），給基板 `dispatch_check.py --table` 用（檔名不是 `EFFORT_TABLE*.json`，見根目錄 CHANGELOG「待總監」） | 基板預設表是 Claude 的等級（medium／xhigh） |
| `AGENTS_PROJECT_SECTION.md` | 貼在專案 `AGENTS.md` 的總監段落 | 基板範本是 `CLAUDE.md` 用的 |
| `DSH_OPERATIONS.md` | DSH 能力對照、開 worker 流程、省 token | 對應基板 `docs/11`（Claude 專用） |
| `DSH_USER_GUIDE.md` | 給第一次用的人看的說明（出自 ds.7 README） | 基板 `docs/14` 是 Claude 畫面 |

## 沿用上游

除了根目錄 README 列的四個覆寫，基板檔全部原樣沿用。ds.7 自己的副本已經刪掉、改用基板 3.0.0：
`safety_gate.py`（設定檢查、預設強度 B15）、`memory_size_check.py --chain`、`loop_guard.py`（打轉核心和 ds.7 兩條細判斷 B17）、`base_sync_check.py`、`readme_check.py`（B6）、`worktree.py`（worker worktree、cwd、temp）、`_common.py`（用量共用碼）、完成證據和 D6 檢查。
`dsh_session.py` 的 `--worker-worktree`、`--cwd-check`、`--temp-env`、`--worktree-status` 只印 `MOVED: ... tools/worktree.py ...`，不做事。

## 拿掉（NOT_PORTED）

| 基板功能 | 為什麼 | 少了會怎樣 | 替代 |
|---|---|---|---|
| PreToolUse 派工 hook（R6） | DSH 沒有工具呼叫前的 hook | 不跑 `dsh_dispatch` 也開得了 worker | `dsh_dispatch.py`；事後 `dispatch_check.py --log`、`gate_check.py --match --dispatch-log` exit 非 0 |
| PostToolUse 動作紀錄 hook | 同上 | 沒有即時紀錄 | `dsh_audit.py build` 事後重建 |
| Claude 專用工具：`hook_guard`、`setup_project_settings`、`poll_hint`、`doctor`、`context_probe`、`usage_report`、`usage_mix`、`transcript_audit`、`choice_reconcile`、`browser_check`、`tools/container/`；`docs/11`；Claude 範本 | 讀寫 Claude 的設定、紀錄、網頁 | 在 DSH 上不能用 | 上表的 `dsh_*`；檔案照基板留著（逐位元組相同），只是不跑 |

## R6 護欄和已知繞過

`dsh_dispatch.py` 是防手滑，不是安全邊界：
- DSH 不跑它也能呼叫 `subagent`；代理也可以自己跑 `spec_gate.py approve`（Claude Code 有 hook 擋，DSH 沒有）。
- 事後一定查得到：沒有 DISPATCH 行的派工，`dispatch_check.py --log` 和 `gate_check.py --match --dispatch-log` 會 exit 非 0；`dsh_audit.py build` 重建的紀錄裡，每一次 `subagent` 呼叫都有一行。
- 推送、刪除、付費不靠工具擋，總監一律先問 PO。

## 版本

本資料夾和 repo 同版：`VERSION` 是 `3.0.0-ds.8`，`BASE_VERSION` 是 `3.0.0`。改了什麼看根目錄 `CHANGELOG.md`。

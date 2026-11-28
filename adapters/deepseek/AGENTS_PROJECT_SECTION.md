<!-- 貼在專案 AGENTS.md 最上方。把 <...> 換掉後刪除本行。 -->
## 總監制（Director mode）

本專案用總監制開發，規則包：https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER（本機：<RULES>）。本專案的規則和 PO 指示優先於規則包。`<D>` 是 `<REPO>/DIRECTOR`（不進 git），交接入口是 `<D>/INDEX.md`。

- **總監**：DSH 根 session，PO 的代理人。Worker 是總監用 `subagent` 開的子代理，接工單（`<D>/orders/WO-*.md`），gate 完成、卡住、要決定時用 `send_message` 送 TASK REPORT 給總監；不直接問 PO。
- **開 worker**：每次先跑 `python -I -X utf8 <D>/adapters/deepseek/dsh_dispatch.py <工單> --repo <REPO>`，印出 `DSH_DISPATCH: GO` 才開，`cwd` 用它開的 worktree；BLOCKED 就不開。
- **狀態寫檔**：每條線維護 `RESUME_STATE.md`（頂部四行 PROGRESS / DOING / NEXT_STEP / COMMS），每個 checkpoint 更新。壓縮或中斷後先跑 `python -I -X utf8 <D>/tools/resume_inject.py --file <RESUME_STATE.md>`，再照 `<RULES>/docs/06b_on_demand_procedures.md` 恢復。
- **訊息**：只在 gate 報告、要決定、要對方改行動時發；不回 ACK。要 PO 回覆的事先報總監，總監記進 `<D>/PO_PENDING.md` 再用 `ask_user_question` 問。
- **上下文短**：長輸出寫檔、只看結論；大量閱讀交給子代理。
- **收尾**：時間由工具產生；報告的 `WORKTREE:` 行用 `<D>/tools/worktree.py status`；最後跑 `dsh_usage.py --project-dir <REPO> --out <D>/usage.json` 和 `gate_check.py --final <D>`。
- **品質**：工程狀態和成品狀態分開報；數字不能代替看成品（<本專案的成品怎麼看>）；最終驗收屬 PO。
- **安全**：push、公開、刪除、付費、帳號、使用者層設定要 PO 核准；不 force push、`reset --hard`、`git clean`、裸 `git stash`；不批次刪證據；只停自己的 job；測試輸出不進 repo。DSH 沒有 hook，防護靠沙箱、核准、`dsh_dispatch` 和事後 audit。
- **語言**：回報用 <繁體中文>。時間一律讀系統時鐘。

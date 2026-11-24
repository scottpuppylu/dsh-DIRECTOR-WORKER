# 06 無損續航

目標：壓縮、錯誤、當機或手動停止後，每條工作線都從最後一個已驗證 checkpoint 接續，不重做、不用半成品。

## 規則

### RESUME_STATE.md

- 每條工作線在自己工作資料夾維護一份（`templates/RESUME_STATE.md`），路徑登記在 `ACTIVE_WORKSTREAMS.md`。
- **頂部四行** `PROGRESS / DOING / NEXT_STEP / COMMS` 須可獨立接手；其餘照範本寫齊，沒有寫 NONE；`IN_FLIGHT` 記背景 job id、等誰、排程 id。
- **更新時機**：checkpoint commit 後、TEST REQUEST 前、背景程序起迄、收到總監決定、DSH 自動壓縮前後。
- `UPDATED` 讀系統時鐘（`date`），不估計。
- 寫完跑 `tools/gate_check.py --resume <檔>` 驗格式與大小（超過照 `docs/06b` 搬走舊紀錄）；對錯核對 `LAST_VERIFIED_CHECKPOINT` 與 repo。
- 有成果就 commit，進度不留對話。

### 恢復與每輪第一步

中斷或壓縮後第 0 步先跑 `tools/resume_inject.py`（`docs/06b`）；中斷的擷取、量測、打包、匯入重做。總監恢復或每輪開始先唯讀跑檢查腳本、收輸入與待決回覆（含 `ask_user_question`）再處理，並用 `list_agents()`／`send_message` 喚回登記於 `ACTIVE_WORKSTREAMS.md` 的子代理。每個排程與防護機制須可重建（`DIRECTOR/GUARDS.md`）；DSH 排程僅 PO 明確要求才建。

## 為什麼

- 見 docs/10。
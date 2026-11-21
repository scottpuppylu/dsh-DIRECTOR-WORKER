# 04 用量與上下文效率

本檔是 dsh-DIRECTOR-WORKER（簡稱 dshdw；舊名 DIRECTOR-WORK DeepSeek 版（DW-DS））的版本。Claude 版原文見 upstream（`repo/docs/04_quota_efficiency.md`）；兩版最大的差別是計價方式與額度概念。

## 成本模型

- **按 token 計價。** 每次模型請求的輸入是：固定系統提示＋工具 schema＋這段對話的歷史（含先前讀過的檔案與工具輸出）＋這次的新內容；輸出是模型生成（含思考）的 token。輸入與輸出都算錢。
- **KV cache（提示快取）。** 同一段前綴重複送出時，命中快取的部分單價較低，但不是免費；改了前綴（例如換系統提示、插入新訊息在很前面）就可能要重算。
- **上下文視窗 1,048,576 tokens**（`deepseek-flash` 官方宣告）；DSH 會自動壓縮，不需要像 Claude 版那樣設「壓縮門檻 250000」。
- **子代理各有自己的上下文**，互不重複計費，但它們各自發出的請求都要錢；總監讀子代理的結論不用重讀子代理的過程。
- **effort 會影響思考 token 與輸出長度**：`off` 最省，`max` 最貴（`docs/05`）。視窗很大不代表可以亂塞：長上下文每次請求都重讀，單價低也還是成本，而且容易讓模型抓不到重點。

## 省用量的槓桿（依效果排序）

1. **上下文保持短。** 這是最大的槓桿：檔案引用路徑、不要貼長內容進對話、工具輸出用檔案或證據紀錄、每輪只讀必讀檔。
2. **大量閱讀交給子代理。** 叫一個 `off`／`low` 的子代理讀完幾十個檔案，只回結論；總監的上下文只增加一段結論。
3. **不重複讀。** 讀過的結論寫進 `RESUME_STATE.md`、決策登記、工單或 `research/`；下一輪讀檔摘要，不重讀原檔。
4. **effort 依難度。** 機械工作 `off`／`low`，一般實作 `high`，關鍵路徑才 `max`（`docs/05`）。
5. **不叫醒不用工作的線。** 閒置的子代理不花 token；不要為了問進度發訊息（`docs/03`）。
6. **關線要留紀錄。** 一條線做完就讓它停在安全狀態並寫好 `RESUME_STATE.md`；需要時再叫醒，不要一直續聊。
7. **大輸出寫檔。** 測試 log、掃描結果、截圖清單寫進 `DIRECTOR/research/`，對話只貼摘要和路徑。

## 怎麼量（每週複查）

指令（日期從系統時鐘讀，不估計）：

```text
python -I -X utf8 <WS>/DIRECTOR/tools/dsh_usage.py --project-dir <WS> --since <上週複查日>
python -I -X utf8 <WS>/DIRECTOR/tools/dsh_usage.py --project-dir <WS> --since <上週複查日> --json
python -I -X utf8 <WS>/DIRECTOR/tools/dsh_usage.py --session <agent 名稱> --since <上週複查日>
```

`--project-dir` 比對的是 session 的啟動資料夾：子代理 session 記在總監的啟動資料夾（通常是 `<WS>`）下，不是 worker 的 cwd。所以量整個專案用 `<WS>`，量單一工作線用 `--session w1`（可重複給多個）。`--since`／`--until` 是本地日期，含當天。

看這幾個數字，寫進 `DIRECTOR/BASELINE_METRICS.md` 或當週紀錄：

| 指標 | 從哪裡來 | 怎麼看 |
|---|---|---|
| 每日／每 session 的 input、output、cacheRead、cacheWrite、total tokens | `dsh_usage.py` | 總量有沒有下降；成本集中在哪條線 |
| cacheRead 佔輸入的比例 | `dsh_usage.py` | 比例太低代表上下文一直變、前綴沒重用；先檢查是不是一直重讀、重貼 |
| 最後一次請求的 prompt tokens 與上下文百分比 | `dsh_usage.py` | 總監自己的上下文有沒有膨脹；接近上限交給子代理讀或先壓縮 |
| 每條工作線的返工次數與重派次數 | `DIRECTOR/orders`、`reviews/`、`DIRECTOR_LOG` | 省了用量卻增加返工，不算省 |
| 需要 PO 介入的次數 | `PO_PENDING.md` | 變多代表流程或需求沒談清楚 |

GUI 的 token meter／context 顯示可以對照當下數字；兩邊不一致時以 GUI 的帳號用量頁為準，記下差異。

**交叉核對（2.4.0-ds.6，改寫自上游 2.4.0；選用）**：`dsh_usage.py` 讀的是 DSH 的本機投影快取（`session_projcache`），格式不是官方介面。用另一個獨立來源對一次同一段時間的總 token（輸入、輸出、快取讀、快取寫）：
- **DSH 自己的事件紀錄**：`dsh_usage.py --cache-root <一個空資料夾>` 找不到快取，就改從 session 事件紀錄逐一重算（要 Node），和預設的快取讀法是兩條路（2.4.0-ds.6 實測：同一天 25 個 session，兩條路的總 token 相同）；差很多時先看範圍是否相同（`--project-dir`、`--since`、含不含子代理）。
- **DSH 帳號頁／GUI 的用量顯示**：上游用的 ccusage 和 Claude Code OpenTelemetry 指標只適用 Claude Code，dshdw 不用。DSH 有沒有可匯出的官方用量指標或 API：NOT_VERIFIED（本機沒有找到；查到之前不假設有）。
- 兩邊差超過一成：記下兩個數字和範圍，當成「量法不同」回報，不挑一個當真值。

**讀不到記 UNKNOWN，不記 0。** `dsh_usage.py` 印 `NO_DATA` 時，代表還沒有可讀的 session 紀錄（例如剛建置），不是用量是 0。

## 停工線與用量重置（dshdw）

- DSH 沒有 Claude 方案的「5 小時／週額度」視窗，也沒有對應的 98%／99% 停工線。
- 用量上限、餘量、方案細節以 DSH 帳號頁／GUI 顯示為準；總監讀不到就記 UNKNOWN，不自行假設。
- 中斷（額度、當機、重開機、DSH 關閉）之後的續航照 `docs/06` 和 `docs/06b`：先讀 `RESUME_STATE.md` 和待決帳，再決定要不要叫醒子代理。
- PO 要求「省一點」時，先做上面第 1～5 項，不要先降 effort（降錯地方會返工）。
- **接近用量上限，放行條件先寫成數字（2.6.0-ds.6，上游 2.6.0）。** 每個還在排隊的大型工作，事先寫好放行條件（例：PREBUILD 通過，而且 DSH 帳號頁顯示的用量低於 PO 定的門檻）；排程者量測後照條件放行或延後，不再另外請示。讀不到用量時條件判 UNKNOWN，不放行。（收件匣 L-083）
- **收尾的同一輪寫好全部豁免（2.6.0-ds.6，上游 2.6.0）。** 宣布收尾或暫停時，一次為每條暫停的線寫豁免到恢復時間：`tools/waiver.py snooze --file W.json --lane A B C --until "<恢復的事件>" --to <恢復時間>`；只有還在跑的線給短期限。不手寫文字檔。（收件匣 L-084）

## 不要為省用量犧牲品質的界線

下面這些不省：P0 阻擋的根因分析、gate 裁決、正式候選的盲審、安全與資料完整性相關的修改、要給 PO 看的成品檢查。

## 為什麼

- Claude 版量的是方案額度；dshdw 按 token 計價，所以「省」的對象從「次數」變成「上下文長度與 effort」；但兩者最大的共同槓桿都是「不要讓對話變長」。
- 視窗有 1,048,576 tokens，很容易讓人以為可以全部塞進去；每次請求都要重讀，長上下文照樣貴，而且模型更容易漏掉重點。
- 子代理的價值是把「讀很多」的成本關在別人的上下文裡，只把結論帶回來；不看這一點，會把省用量的工具用成燒用量的工具。
- 量測故意用固定指令與固定欄位，才能前後比較（`PURPOSE.md`「怎麼判斷有沒有效」）。
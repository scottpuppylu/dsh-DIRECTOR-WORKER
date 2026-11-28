# <變體名稱>：DIRECTOR-WORK 的 <平台> 版

3.0.0（D8、G8；PO 11-28 補「所屬系列」和「跨變體借用」）。每個變體的 README 照這份寫。目的是讓接手的人一眼看出：

- 這個變體屬於哪個系列、跟哪一版基板對齊；
- 它多了什麼、照抄了什麼、少了什麼；
- 從別的變體借了什麼。

用白話寫，不用先懂基板。下面每一節都要有；沒有內容就寫「無」，不能整節省略。`tools/readme_check.py` 會檢查，缺一節就不准發版（`release.py` 的 `readme` 步驟）。

標題下面第一段寫三件事：這是什麼、給哪個平台用、一句話怎麼開始。通常就是基板的啟動提示詞，網址換成這個變體的 repo。

## 所屬系列

- 基板：DIRECTOR-WORK，https://github.com/scottpuppylu/DIRECTOR-WORK
- 基板版號：`BASE_VERSION` 檔寫的那一版，例如 `3.0.0`。
- 凍結 SHA：這一版合併進來的基板 commit，例如 `<基板 commit>`。

系列表和基板 README 的同一張：

| repo | 平台 | 3.0.0 版號 | 適合什麼情況用 |
|---|---|---|---|
| 基板 https://github.com/scottpuppylu/DIRECTOR-WORK | 不限 | `3.0.0` | 替新平台做變體，或只讀規則和工具 |
| cld https://github.com/scottpuppylu/cld-DIRECTOR-WORKER | Claude Code | `3.0.0-cld.1` | 用 Claude Code（R6 有 hook 擋） |
| dsh https://github.com/scottpuppylu/dsh-DIRECTOR-WORKER | DeepSeek | `3.0.0-ds.8` | 用 DeepSeek |
| cdx https://github.com/scottpuppylu/cdx-DIRECTOR-WORKER | Codex | `3.0.0-cdx.11` | 用 OpenAI Codex |
| agy https://github.com/scottpuppylu/agy-DIRECTOR-WORKER | Antigravity | `3.0.0-agy.7` | 用 Google Antigravity |

## 新增（只有這個變體有）

只放這個平台非改不可的東西：

- 規則檔的格式和位置；
- 工具的呼叫方式；
- 模型設定。

這些都放在 `adapters/<平台>/`。

| 項目 | 檔案 | 為什麼基板沒有 |
|---|---|---|
| <例：hook 設定寫法> | `adapters/<平台>/...` | <這個平台才需要> |

## 沿用上游（和基板逐位元組相同）

上面「新增」和下面「拿掉」沒列到的基板檔，全部原樣沿用。`base_sync_check.py` 拿 `install.py manifest` 的清單逐檔比對：和基板不一樣、又沒登記成轉接覆寫，就不准發版。

轉接覆寫（改過的基板檔）一定要列在這裡，並寫明理由：

| 基板檔 | 改了什麼 | 理由 |
|---|---|---|
| <例：無> | | |

## 拿掉（NOT_PORTED）

基板有、這個變體沒做的功能。照實寫，不要留空；沒有就寫「無」。

| 基板功能 | 為什麼沒做 | 少了它會怎樣 | 替代做法 |
|---|---|---|---|
| <例：即時打轉提醒> | <平台沒有工具呼叫前的 hook> | <只能事後發現打轉> | <`loop_guard.py scan` 事後讀紀錄> |

## 跨變體借用

列出從別的變體或舊版搬來的做法，包括程式、規則和文件裡提到 cld／ds／cdx／agy 版號或名稱的地方。

- 已經併進基板的做法，改用基板版。
- 只有別的變體有、而且比較新的做法，改用新版。
- 平台不允許的，保留，並寫出原因。
- 原出處之後又改過的，也要跟上。

沒有借用就寫「無」。

| 做法 | 原本出自哪版 | 現在用哪版 | 怎麼處理 |
|---|---|---|---|
| <例：發版的版號整組比較> | <ds.3> | <基板 3.0.0> | <改用基板> |

## 安裝

把工具裝進專案（先備份、驗雜湊）：

```text
python -I -X utf8 tools/install.py install --to <專案>/DIRECTOR/tools --execute
```

再加上這個平台自己的步驟（hook、規則檔），並寫出看到哪一行才算裝好。

## 換手提示詞

換平台或換帳號接手時，在新的對話貼這一句：

```text
讀 `DIRECTOR/INDEX.md`，照它接手，不要重問已確認的需求。
```

## 版號規則

變體版號是上游版號加變體序號，例如 `3.0.0-cld.1`。

- 序號接續前一版。上游版號變大，序號也不從 1 重來：例如 cdx 前一版是 .10，這一版就是 `3.0.0-cdx.11`；agy 是 `.7`，dsh 是 `ds.8`。
- `release.py` 把上游版號和序號整組比較，比遠端小的版號擋下；序號不是前一版加 1（從 1 重來、跳號）也擋下（3.0.0 B14）。

## CHANGELOG

- 這個變體的 CHANGELOG 放在 `CHANGELOG.md`。
- 基板的原文放在 `CHANGELOG-upstream.md`，和基板逐位元組相同。

每次對齊新的基板版本，在 CHANGELOG 那一版加一張表，基板 CHANGELOG 的每一項都要有一列：

| 上游項目 | 怎麼處理（沿用／改寫／不做） | 理由 |
|---|---|---|

## 致謝（Credits）

借用的專案、概念和授權，照基板 CHANGELOG 的 Credits 寫法列出。

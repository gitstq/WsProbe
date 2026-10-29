<div align="center">

# 🔭 WsProbe

**零依賴的 WebSocket 偵錯探針 · 內建 RFC 6455 完整協定堆疊**

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![RFC](https://img.shields.io/badge/RFC-6455-orange)

</div>

---

## 🎉 專案介紹

**WsProbe** 是一套用來偵錯 WebSocket 服務的命令列探針,同時也是一個 Python 函式庫。
它的特色可以用一句話講完:

> **整套 WebSocket 協定(RFC 6455)都是自己手寫實作出來的,執行時不依賴任何第三方套件。**

不用裝 `websockets`、不用裝 `websocket-client`,也沒有 `aiohttp`、`requests`、`numpy`。
只要一個 Python 3.8+ 直譯器,把專案 clone 下來就能跑——在內網、離線環境、
精簡版容器裡都一樣。

### 🤔 它解決了哪些痛點

| # | 痛點 | WsProbe 的解法 |
|---|------|----------------|
| 1 | 🔌 WebSocket 一直缺少「curl 等級」的順手工具,偵錯只能寫臨時腳本 | 一條指令完成連線、發送、過濾、錄製 |
| 2 | 📦 現有工具依賴太重,離線 / 內網環境根本裝不起來 | **執行期零依賴**,只用標準函式庫 |
| 3 | 🕶️ 交握失敗是黑盒子,只知道「連不上」,不知道為什麼 | `inspect` 直接印出狀態碼、請求 Key、Accept 驗證結果、解析後的 IP |
| 4 | 🌊 訂閱流每秒幾十則推送,在意的那則被淹沒 | 內建過濾 DSL,`--filter '$.price > 100'` |
| 5 | 🔁 聯調過程無法重現,問題「剛剛還在」 | 錄製成 JSONL,隨時原速 / 加速重播 |
| 6 | 🧪 WebSocket 介面沒辦法像 HTTP 那樣做回歸測試 | 宣告式 JSON 腳本,可進 CI,失敗就回傳非零結束碼 |
| 7 | 📊 「有點慢」講不出慢在哪裡 | `bench` 給出吞吐量與 P50 / P95 / P99 延遲百分位數 |

### 💎 自研差異化亮點

* 🧬 **協定堆疊 100% 自研**:訊框編解碼、XOR 遮罩、延伸長度(7/16/64 位元)、
  分片重組、交握 Accept 計算、心跳、關閉交握——一個位元組一個位元組手寫,
  不是拿別人的套件包一層皮。
* 🎯 **兩端都是自己寫的**:用戶端與**伺服器端**都是自行實作。內建的 `wsprobe serve`
  既是展示用的靶機,也是端對端測試的基礎設施。
* 🔍 **自研過濾表達式**:不引入 jsonpath / JMESPath,自己做一套路徑 + 萬用字元 +
  比較運算子的迷你查詢語言。
* 🩺 **預設就可觀測**:交握診斷、RTT 量測、位元組 / 訊息計數、延遲百分位數,全部內建。
* 🔌 **既是 CLI 也是函式庫**:`from wsprobe import WebSocketClient` 直接嵌進你的程式裡。

### 🌱 靈感來源

WsProbe 的想法來自三個工具的融合:**curl**(命令列的直接)、**tcpdump**(流量可錄製可重播)、
**wscat**(互動式會話),再壓縮成一個零依賴、可審計、能在 CI 裡跑的純 Python 套件。

> 📸 *執行畫面 / 示範動畫佔位:實際跑起來後,在此處補上終端機錄製動畫。*

---

## ✨ 核心功能

### 🧬 協定層(全部自研)

* ✅ **完整訊框編解碼**:FIN / RSV / opcode / MASK / 7-16-64 位元延伸負載長度
* ✅ **用戶端遮罩**:以 CSPRNG 產生 4 位元組遮罩,XOR 運算具自反性
* ✅ **分片重組**:串接 continuation 訊框,並檢查「資料訊框不得交錯」等協定約束
* ✅ **交握**:`Sec-WebSocket-Key` 產生、`Sec-WebSocket-Accept` 以 SHA-1 + GUID 計算並驗證
* ✅ **心跳**:主動 PING 量測 RTT;**自動回應**伺服端 PING(RFC 強制要求)
* ✅ **關閉交握**:送出 close → 等待對端 close → 關閉 TCP,並解析狀態碼與原因
* ✅ **協定防護**:RSV 位元、未知 opcode、分片控制訊框、非法 UTF-8、過大負載,全部攔下
* ✅ **TLS / Proxy**:`wss://` 與 HTTP CONNECT 通道

### 🛠️ 工具層

* 🔭 **`connect`**:連線、發送、過濾、錄製,並支援互動式 REPL
* 🩺 **`inspect`**:只做交握,印出完整診斷報告
* 📈 **`bench`**:並行壓力測試,吞吐量 + P50/P95/P99
* 🎬 **`script`**:宣告式 JSON 腳本(send / expect / wait / sleep / ping / close)
* ♻️ **`replay`**:把錄製檔重播到任意目標
* 🖥️ **`serve`**:內建回應 / 定時推送 / 廣播伺服器
* 🧪 **`selftest`**:10 項協定自檢,一條指令驗證環境
* 🎨 **輸出友善**:彩色高亮、JSON Lines、hexdump,並提供 `--no-color` 降級

---

## 🚀 快速開始

### 📋 環境需求

| 項目 | 需求 |
|------|------|
| Python | **>= 3.8**(僅標準函式庫) |
| 第三方依賴 | **無** |
| 作業系統 | Windows / macOS / Linux |
| 網路 | 出站 TCP;需要 Proxy 時用 `--proxy` |

### 📦 安裝

```bash
# 方式一:用 pip 安裝(推薦)
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
pip install .

# 方式二:免安裝,直接用模組方式執行
python -m wsprobe --help
```

安裝後會取得 `wsprobe` 命令列指令。

### ⚡ 三步上手

**第一步** 開一個終端機,啟動內建伺服器(每秒推送一則訊息):

```bash
wsprobe serve --port 8765 --pump 1
```

**第二步** 另開一個終端機連上去:

```bash
wsprobe ws://127.0.0.1:8765
```

你會看到類似輸出:

```
✓ HTTP 101 Switching Protocols · 127.0.0.1:8765 (127.0.0.1)
[10:32:01] ← {"type": "pump", "seq": 1, "ts": 1793290921.1, "value": 12.33}
[10:32:02] ← {"type": "pump", "seq": 2, "ts": 1793290922.1, "value": 24.67}
```

**第三步** 只留下你在意的訊息:

```bash
wsprobe ws://127.0.0.1:8765 --filter '$.value > 20' --count 5 --stats
```

> 💡 手邊沒有現成的 WebSocket 服務?`wsprobe serve` 就是為這種情況準備的。

---

## 📖 詳細使用指南

### 🗂️ 子命令一覽

| 指令 | 用途 | 典型用法 |
|------|------|----------|
| `connect` | 連線並收發訊息(預設,可省略) | `wsprobe ws://host/p --send hi` |
| `inspect` | 只做交握並輸出診斷 | `wsprobe inspect wss://host/p` |
| `bench` | 並行壓力測試 | `wsprobe bench ws://host -c 20 -m 200` |
| `script` | 執行宣告式腳本 | `wsprobe script flow.json` |
| `replay` | 重播錄製檔 | `wsprobe replay rec.jsonl --to ws://host` |
| `serve` | 啟動內建伺服器 | `wsprobe serve --port 8765 --pump 1` |
| `selftest` | 協定自檢 | `wsprobe selftest` |

### 🔭 連線與發送

```bash
# 連線後進入互動模式(輸入即發送,/quit 離開)
wsprobe ws://127.0.0.1:8765

# 送出一則文字並接收一則回應
wsprobe ws://127.0.0.1:8765 --send '{"cmd":"ping"}' --count 1

# 連續送出多則,間隔 0.5 秒
wsprobe ws://127.0.0.1:8765 --send a --send b --send-interval 0.5

# 讀取檔案內容送出
wsprobe ws://127.0.0.1:8765 --send-file payload.json

# 持續監聽 30 秒
wsprobe ws://127.0.0.1:8765 --duration 30

# 自訂請求標頭 / 子協定 / Proxy / 略過憑證驗證
wsprobe wss://host/p \
  --header "Authorization: Bearer TOKEN" \
  --subprotocol json \
  --proxy http://127.0.0.1:7890 \
  --insecure
```

**互動模式內建指令:**

| 輸入 | 作用 |
|------|------|
| `任意文字` | 以文字訊框送出 |
| `/ping` | 量測一次往返延遲 |
| `/wait 3` | 靜默接收 3 秒內的所有訊息 |
| `/stats` | 印出目前會話統計 |
| `/quit` | 關閉連線並離開 |

### 🔍 過濾表達式

語法為 `<路徑> [<運算子> <值>]`:

| 表達式 | 意義 |
|--------|------|
| `$.price > 100` | 最上層 `price` 大於 100 |
| `data.status == "error"` | 巢狀欄位等於 `error` |
| `items[*].id` | 陣列中任一元素存在 `id` 欄位 |
| `text ~ "timeout"` | 文字包含 `timeout` |
| `name ^ "ws"` | 以 `ws` 開頭 |
| `name $ "probe"` | 以 `probe` 結尾 |

支援的運算子:`==` `!=` `>` `>=` `<` `<=` `~`(包含) `^`(前綴) `$`(後綴)。
文字訊息會先嘗試以 JSON 解析,解析失敗則當成純字串處理;型別無法比較時判定為「不符合」,不會丟出例外。

### 🎬 錄製與重播

```bash
# 錄製(所有流量都寫入 JSONL,與是否命中過濾無關)
wsprobe ws://host/p --duration 60 --record session.jsonl

# 只預覽錄製內容,不真的發送
wsprobe replay session.jsonl --preview

# 以原速重播到另一個位址
wsprobe replay session.jsonl --to ws://staging-host/p

# 2 倍速重播;--speed 0 表示全速、不等間隔
wsprobe replay session.jsonl --to ws://host/p --speed 2
```

JSONL 每一列的長相:

```json
{"ts": 1793290921.106, "dir": "in", "op": "text", "size": 64, "data": "{\"type\":\"pump\"}"}
```

### 🧪 宣告式腳本(可用於 CI)

```json
{
  "url": "ws://127.0.0.1:8765",
  "steps": [
    { "action": "send",   "data": { "cmd": "subscribe", "channel": "ticker" } },
    { "action": "expect", "filter": "cmd == \"subscribe\"", "timeout": 5 },
    { "action": "sleep",  "seconds": 0.5 },
    { "action": "wait",   "count": 3, "timeout": 10 },
    { "action": "ping" },
    { "action": "close" }
  ]
}
```

```bash
wsprobe script flow.json --json     # 機器可讀輸出,方便在 CI 中斷言
```

所有步驟都通過時結束碼為 `0`,任一步驟失敗即為 `1`,可以直接接在流水線當成關卡。

### 📈 壓力測試

```bash
wsprobe bench ws://127.0.0.1:8765 --connections 20 --messages 200 --payload 128
```

```
url                     : ws://127.0.0.1:8765
connections             : 20
messages_per_connection : 200
completed               : 4000
errors                  : 0
throughput_msg_per_s    : 6098.68
latency_p50_ms          : 0.364
latency_p95_ms          : 0.932
latency_p99_ms          : 1.022
```

### 🩺 交握診斷

```bash
wsprobe inspect wss://echo.example.com
```

```
HTTP 101 Switching Protocols
  目標    : wss://echo.example.com
  解析 IP : 93.184.216.34
  請求 Key: xUFq46M2kCNjLVU859PCwQ==
  預期 Acc: HN2CMetJ8CJC/UA3cp1YIJXqG9Y=
  Accept  : HN2CMetJ8CJC/UA3cp1YIJXqG9Y= (驗證通過)
  首包 RTT: 42.15 ms
```

連不上的時候,這段輸出就是定位問題的第一手材料:狀態碼不是 101?Accept 驗證失敗?
還是 TLS 或 Proxy 的問題?

### 🐍 當成函式庫使用

```python
from wsprobe import WebSocketClient
from wsprobe.filters import MessageFilter

matcher = MessageFilter("value >= 10")

with WebSocketClient("ws://127.0.0.1:8765", timeout=5) as ws:
    ws.send_json({"cmd": "subscribe", "channel": "ticker"})
    for message in ws.iter_messages(count=100, timeout=10):
        if matcher.match(message):
            print(message.json)

    rtt = ws.ping()          # 往返延遲(秒)
    print(ws.stats.to_dict())
```

更多用法請見 [`examples/library_usage.py`](examples/library_usage.py)。

### ❓ 常見問題

<details>
<summary><b>交握失敗,出現 HTTP 4xx / 5xx 怎麼辦?</b></summary>

先用 `wsprobe inspect <url>` 看狀態碼與回應標頭。401/403 通常是少了驗證標頭(加 `--header`),
404 通常是 path 不對,301/302 則要改成轉址後的位址。
</details>

<details>
<summary><b>出現 <code>Sec-WebSocket-Accept verification failed</code>?</b></summary>

代表對端回傳的 Accept 與標準演算法算出來的不一致(常見於中途被設備攔截,
或對方其實不是真正的 WebSocket 服務)。確認目標無誤後,可用 `--no-strict-accept` 略過驗證繼續查。
</details>

<details>
<summary><b>需要走公司 Proxy?</b></summary>

用 `--proxy http://host:port`,WsProbe 會先發 HTTP CONNECT 建立通道,再在其上完成 TLS 與交握。
</details>

<details>
<summary><b>自我簽署憑證報錯?</b></summary>

加 `--insecure` 略過憑證驗證(建議僅在內網偵錯時使用)。
</details>

<details>
<summary><b>訊息太大被拒?</b></summary>

預設單則訊息上限為 64 MiB,可用 `--max-payload` 調整。這是防止被惡意伺服端吃光記憶體的保護機制。
</details>

---

## 💡 設計思路與後續規劃

### 🏗️ 分層架構

```
┌──────────────────────────────────────────────┐
│  cli.py        參數解析、輸出渲染、REPL        │  ← 應用層
├──────────────────────────────────────────────┤
│  script.py / session.py / stats.py / filters  │  ← 能力層(腳本、錄製、統計、過濾)
├──────────────────────────────────────────────┤
│  client.py     連線狀態機、心跳、關閉交握      │  ← 會話層
├──────────────────────────────────────────────┤
│  handshake.py  HTTP Upgrade / Key / Accept    │  ← 交握層
├──────────────────────────────────────────────┤
│  frame.py      RFC 6455 訊框編解碼/遮罩/分片   │  ← 協定層(最核心的自研部分)
└──────────────────────────────────────────────┘
```

### 🤔 關鍵設計決策

| 決策 | 原因 |
|------|------|
| **零第三方依賴** | 偵錯工具必須能在最糟的環境裡跑起來——內網、離線、精簡容器。依賴越少,可用性越高 |
| **阻塞式 socket + 執行緒** | 不引入 asyncio 的複雜度;偵錯情境下阻塞模型行為更可預測,逾時語意也更清楚 |
| **遮罩用大整數 XOR** | 逐位元組的 Python 迴圈在 64KB 負載上很慢,`int.from_bytes` 一次 XOR 可快上一個數量級 |
| **過濾 DSL 自己寫** | jsonpath / JMESPath 對偵錯需求來說太重;只需要路徑加比較,自己寫更輕、更可控 |
| **內建伺服端** | 讓工具自備「靶機」:既是零門檻展示,也讓端對端測試不必依賴外網 |
| **腳本失敗即非零結束碼** | 讓 WebSocket 介面也能像 HTTP 一樣納入 CI 關卡 |

### 🗺️ 後續迭代規劃

* [ ] 🔐 支援 `permessage-deflate` 壓縮擴充的探測與協商
* [ ] 🧩 可插拔的訊息編解碼器(Protobuf / MessagePack,需要時才裝)
* [ ] 📊 HTML 視覺化報告(把錄製檔渲染成時間軸圖)
* [ ] 🔄 自動重連與指數退避(`--reconnect`)
* [ ] 🌐 SOCKS5 Proxy 支援
* [ ] 🧵 非同步用戶端(asyncio 版本,選用)
* [ ] 📦 發布到 PyPI

### 🤝 社群貢獻方向

最歡迎三類貢獻:**更多真實伺服端情境的相容性驗證**、**過濾 DSL 表達力的強化**、
**文件與範例的本地化**。

---

## 📦 打包與部署指南

WsProbe 屬於**工具函式庫 / CLI 類專案**,因此**不需要**發布二進位 Release 附件;
照下面的方式安裝即可零門檻使用。

### 🐍 方式一:pip 安裝(推薦)

```bash
pip install .
# 或開發模式(改動即時生效)
pip install -e .
```

安裝後會取得兩個入口:

* 命令列:`wsprobe --help`
* 函式庫匯入:`from wsprobe import WebSocketClient`

### 📄 方式二:免安裝執行

```bash
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
python -m wsprobe --help       # 等同於 wsprobe --help
```

因為零依賴,也可以直接把 `wsprobe/` 目錄複製進你自己的專案使用。

### 🧊 方式三:打包成單一可執行檔(選用)

需要無依賴的可執行檔時,可用 PyInstaller:

```bash
pip install pyinstaller
./scripts/build.sh              # 產物在 dist/wsprobe,並產生 .sha256 校驗碼
./scripts/build.sh clean        # 清除建置產物
```

> ⚠️ PyInstaller **不支援交叉編譯**。要產生 Windows / macOS 的產物,必須在對應系統上執行
> (或使用該系統的 CI runner,見 `.github/workflows/release.yml`)。

### 🌍 相容環境

| 環境 | 狀態 |
|------|------|
| Python 3.8 / 3.9 / 3.10 / 3.11 / 3.12 | ✅ 支援 |
| Windows 10+ / macOS 11+ / Linux | ✅ 支援 |
| 離線 / 內網環境 | ✅ 支援(零依賴) |
| 精簡 Docker 映像檔(如 `python:3.11-slim`) | ✅ 支援 |

### 🧪 驗證安裝

```bash
wsprobe selftest
```

10 項協定自檢全數通過,即代表環境正常。

---

## 🤝 貢獻指南

### 🔀 Pull Request 規範

1. Fork 本專案並建立特性分支:`git checkout -b feat/your-feature`
2. 提交訊息遵循 **Angular 規範**:

   ```
   feat: 新增 xxx 功能
   fix: 修正 xxx 問題
   docs: 更新 xxx 文件
   refactor: 重構 xxx 模組
   test: 補充 xxx 測試
   chore: 調整建置設定
   ```

3. 新增程式碼請**維持零第三方依賴**這個核心約束(測試用依賴除外)
4. 補充或更新對應的單元測試,並確認全部通過:

   ```bash
   python -m unittest discover tests
   wsprobe selftest
   ```

5. 若改動涉及命令列行為,請同步更新**三個語言版本**的 README

### 🐛 Issue 回饋規則

提交 Issue 時請盡量附上:

* WsProbe 版本(`wsprobe --version`)與 Python 版本
* 作業系統
* 重現指令(目標位址可脫敏)
* `wsprobe inspect <url>` 的完整輸出
* 預期行為與實際行為

### 🧭 程式碼風格

* 遵循 PEP 8,公開介面附上 docstring
* 協定層的改動必須附上單元測試(協定錯誤往往只在極端輸入下才會暴露)
* 維持模組單一職責:`frame.py` 只管位元組,`client.py` 只管會話

---

## 📄 開源授權說明

本專案採用 **MIT License** 開源授權,完整條款請見 [LICENSE](LICENSE)。

* ✅ 允許商用、修改、散布、私有使用
* ✅ 可用於閉源專案
* ⚠️ 需保留原始版權聲明與授權聲明
* ❌ 作者不對軟體的適用性提供任何擔保

---

<div align="center">

**🔭 WsProbe —— 把 WebSocket 的黑盒子,變成看得見的位元組。**

Made with ❤️ by WsProbe Contributors

</div>

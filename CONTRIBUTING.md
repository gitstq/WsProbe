# 🤝 貢獻指南 / Contributing

感謝你願意為 WsProbe 貢獻一份力量!這份文件說明如何參與開發。

Thanks for your interest in contributing to WsProbe! This document explains how to get involved.

---

## 🚀 開始之前 / Before you start

WsProbe 有一個**不可動搖的核心約束**:

> **執行期零第三方依賴。**
> `wsprobe/` 目錄下的程式碼只能使用 Python 標準函式庫。
> 測試與打包用的依賴請放在 `requirements-dev.txt`。

> **Zero third-party dependencies at runtime.**
> Code under `wsprobe/` must only use the Python standard library.
> Test/build dependencies belong in `requirements-dev.txt`.

如果你打算引入一個新依賴,請先開 Issue 討論——絕大多數情況下答案是「自己實作」。

---

## 🛠️ 開發環境 / Development setup

```bash
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe

# 免安裝即可開發(零依賴的好處)
python -m wsprobe --help

# 可選:安裝開發依賴
pip install -r requirements-dev.txt
```

## ✅ 提交前檢查 / Pre-submit checklist

```bash
# 1. 協定自檢(10 項)
python -m wsprobe selftest

# 2. 單元測試(84 項)
python -m unittest discover tests
```

兩者都必須全綠。若你改動了協定層,請務必補上對應的單元測試——協定錯誤往往只在
極端輸入(126/127 長度邊界、分片交錯、非法 UTF-8)下才會暴露。

---

## 📝 提交訊息規範 / Commit message convention

採用 **Angular 規範**：

```
<type>(<scope>): <subject>
```

| type | 用途 |
|------|------|
| `feat` | 新增功能 |
| `fix` | 修正問題 |
| `docs` | 文件更新 |
| `refactor` | 重構(不改變外部行為) |
| `test` | 測試相關 |
| `perf` | 效能改善 |
| `chore` | 建置 / 工具配置 |

範例:

```
feat(handshake): 新增 HTTP CONNECT 代理通道支援
fix(frame): 修正 64 位元延伸長度的最高位元檢查
docs: 同步三語 README 的 --max-payload 說明
```

---

## 🔀 Pull Request 流程 / PR workflow

1. Fork 專庫,建立分支:`git checkout -b feat/your-feature`
2. 開發並通過上述兩項檢查
3. 若改動 CLI 行為,同步更新 **README.md / README.zh-TW.md / README.en.md** 三個版本
4. 發 PR,在描述中說明:動機、改動內容、驗證方式
5. 等待 Review,回應意見後合併

---

## 🐛 回報問題 / Reporting issues

請附上:

* WsProbe 版本(`wsprobe --version`)與 Python 版本
* 作業系統
* 重現指令(目標位址可脫敏)
* `wsprobe inspect <url>` 的完整輸出
* 預期行為與實際行為

---

## 🎯 最需要的貢獻方向 / Where help is most needed

1. **真實伺服端相容性驗證** — 拿 WsProbe 去連更多真實服務,回報不相容案例
2. **過濾 DSL 表達力** — 讓查詢語法更強,同時保持零依賴
3. **文件與本地化** — 三語文件的潤飾,或新增其他語言版本

---

## 📄 授權 / License

貢獻即表示你同意你的程式碼以 **MIT License** 授權釋出。

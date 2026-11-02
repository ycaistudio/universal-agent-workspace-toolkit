---
name: universal-agent-workspace-toolkit
description: >-
  通用 AI 智能體工作區全域管理中樞 (v2.3.0)。支援 Antigravity 與 Grok Bot 遷移、日常快照與還原，內建 Level_0 預設機密排除、Level_1~7 階梯對齊、衝擊評估與兩次確認門禁。觸發詞：workspace toolkit, 搬電腦, 備份, backup, restore, 系統遷移, grok bot.
---

# Universal AI Agent Workspace Toolkit (v2.3.0 Master)

## 1. 🎯 核心定位與設計架構 (Core Architecture)

本技能為通用的 AI 工作區遷移與備份工具，目前僅在 **Google Antigravity** 目錄結構驗證；**Claude Code / Desktop**、**Cursor**、**VS Code (Cline / Roo)** 尚未測試。

### 核心原則：
1. **單一入口統一控制台 (`workspace_toolkit.py`)**：
   - 告別分立之 A/B 腳本與平台綁定之 `.bat` 批次檔；
   - 單一 Python 腳本兼具 **打包匯出 (`--mode pack`)**、**導入驗收 (`--mode restore`)** 與 **清單審計 (`--mode inspect`)**。
2. **Level_0 機密憑證排他守門機制**：
   - 主動探測 `.env`、API Key、Token、私鑰憑證具體儲存路徑；
   - 預設排除已知憑證檔案、私鑰區塊與真實格式 Token，MCP 機密值以佔位符取代；可用 `--include-secrets` 明確指定打包。
   - v2.3.0 另依檔名排除（不開檔）：`*secret*`、`*token*`、`*credential*`、`*cookie*`、`*key*.json`、`gateway.json`、`mcp_config.json`、`.env`、`*.pem`、`*.key` 與整個 `credentials/`；`.md`、`.py` 等文件不受檔名規則影響，`tokenizer*.json` 與 lockfile 保留。
3. **全域 `Level_X` 命名與目錄對齊**：
   - 內部子目錄、壓縮檔名、Manifest 鍵名全數對齊：
     - `Level_1_Agent_Directives`（智能體首讀核心憲法 · ⚠️極高危，單例保護）
     - `Level_2_System_Settings`（系統運行底盤 · 僅 Key Patch 增補）
     - `Level_3_Modular_Skills`（模組化可插拔技能庫 · 合併導入，同名檔案覆寫前先建立快照）
     - `Level_4_Workspace_Docs`（專案工程文檔與腳本 · 增量同步）
     - `Level_5_Heavy_References`（龐大素材、二進制與 5 MB 以上模型權重 · 只計數，不打包；模型權重可用 `--include-bulky` 帶回）
     - `Level_6_Memory_Drop`（僅 Grok Bot · memory-drop JSONL · 還原不寫入平台記憶）
     - `Level_7_Conversations`（僅 Grok Bot · search-index 唯讀快照與逐字稿）
4. **每份設上限的封裝**：
   - 每個 ZIP 不超過 `--max-part-mb`（預設 90，十進位上限 95，超過即拒絕）；放得下就是單一 ZIP，放不下就拆成可獨立開啟的 `<名稱>_Part_01_of_0N.zip`，每份附自己的清單，超大單檔切段後還原時接回並核對 SHA-256；
   - 還原／檢查需要同一資料夾內的全部分件，缺件即停止；輸出不覆寫（改名 `_v2`、`_v3`）；
   - 虛擬環境（`*venv*`、`.venv`、`site-packages`）不打包，改以該環境自己的 Python 離線匯出 `uv pip freeze` / `pip freeze` 與 `pip list --user` 到 `Level_2_System_Settings/python-envs/`（`--skip-env-lock` 關閉）；
   - 技能／規則檔重複出現時列出各副本，請使用者決定正本；最長路徑超過 200 字元時提示解壓到 `C:\GB\` 或開啟 LongPathsEnabled；
   - Level 5 大檔只在審計表計數，不打包。
5. **專業三語原生自適應 (EN / ZH-TW / JA)**：
   - 預設英文（全球開源通用），自動依系統 Locale 載入繁體中文或日本語。
6. **兩次雙重確認門禁與本機快照**：
   - 部署前產出【衝擊評估報告】 ➔ 【第一次確認】計劃審核 ➔ 自動建立本機防禦快照 ➔ 【第二次確認】最終授權 ➔ `AGENTS.md` 存為 `.incoming` 雙軌保護。

---

## 2. 📋 操作指令與模式 (Command Reference)

```bash
# 啟動交互式三語控制台 (自動偵測語言)
python workspace_toolkit.py

# 匯出打包模式 (自動探測 Level_0 並匯出 Level_1 至 Level_4)
python workspace_toolkit.py --mode pack -y

# 每份上限 45 MB；保留模型權重；不匯出虛擬環境鎖定檔
python workspace_toolkit.py --mode pack --max-part-mb 45 --include-bulky --skip-env-lock -y

# 導入還原模式 (自動驗真、衝擊評估、防禦快照與兩次確認)
python workspace_toolkit.py --mode restore

# 純校驗審計 (不改動任何檔案)
python workspace_toolkit.py --mode inspect

# 切換語言模式
python workspace_toolkit.py --lang en      # English
python workspace_toolkit.py --lang zh-tw   # 繁體中文
python workspace_toolkit.py --lang ja      # 日本語

# Grok Bot（agent-data 存在時 --profile auto 會自動選到 grok）
python workspace_toolkit.py --mode pack --profile grok -y
python workspace_toolkit.py --mode restore --uuid-map OLD=NEW --target-env existing -y
```

---

## 3. 🛡️ 國際多語系文檔與 Git 治理規範 (I18N & Git Governance)

1. **IETF BCP 47 國際語系檔名規範**：
   - 開源文檔強制對齊作業系統 Locale 與 GitHub 規範：`README.md` (English Default)、`README_zh-TW.md` (繁體中文)、`README_ja.md` (日本語)。嚴禁使用國家代碼 `JP` 代指日語。
2. **嚴格三語對稱與固定語序 (`EN ➔ ZH-TW ➔ JA`)**：
   - 頂部導航列、多語章節標題及階層對照表，100% 鎖定 **🇬🇧 English ➔ 🇹🇼 繁體中文 ➔ 🇯🇵 日本語** 順序，且嚴禁於同一文檔出現重複 H2 標題。
3. **Git 提交者身份真實性與官方隱私郵箱防線**：
   - 嚴禁虛構或猜測任何未認證郵箱；強制查詢並綁定 GitHub 官方認證之 ID-Based Noreply 隱私郵箱（`{id}+{login}@users.noreply.github.com`）。

---

## 4. 🤖 Grok Bot：打包前的 memory-drop

打包程式不會替 Bot 查記憶。每一個 Bot 要先把記憶寫進 memory-drop 目錄，否則 Level_6 只會標成未匯出。

預設目錄是 `$GROK_WORKSPACE/exports/memory-drop`（可用 `GROK_MEMORY_DROP` 或 `MEMORY_DROP` 改）。封裝時只認下面這些路徑：

| 用途 | 路徑（相對於 memory-drop 根目錄） | 封裝程式怎麼用 |
| --- | --- | --- |
| 這個 Bot 的記憶 | `agents/<agent-uuid>/*.jsonl` | 逐行讀 JSON。`fact` 有文字才計入筆數。 |
| 帳號共用的記憶 | `shared-user/memory-user.jsonl` | 同樣只計 `fact`。 |
| 查過、沒有可存的內容 | 與上面檔案同一層的 `memory-status.json` | 只看檔案在不在，不解析內容。 |

空白的 `.jsonl` 不會被當成「已經查過」。要留下查過的紀錄，請放上 `memory-status.json`。檔裡可寫 bot id 與查詢時間，給人讀；封裝報告不讀這些欄位。

可直接貼給每個 Bot：

```text
Create $MEMORY_DROP/agents/<your-agent-uuid>/ and write the bot's memories there as line-delimited JSON. Each line's fact field carries that memory's text. Account-wide memories, if this bot is allowed to read them, belong in $MEMORY_DROP/shared-user/memory-user.jsonl using the same line shape. When the lookup has no rows worth saving, place memory-status.json in that same folder; a blank data file is not a substitute. Do not alter the memories stored by the bot, and report the paths you created.
```

還原時，這些 JSONL 只會進 `.incoming` 與手動重建清單。目標 Bot 要自己把每一條 `fact` 讀進記憶工具；封裝程式不會代做這一步。

---
name: universal-agent-workspace-toolkit
description: >-
  通用 AI 智能體工作區全域管理中樞 (v2.1.0)。支援 Antigravity、Claude、Cursor 跨平台無損遷移、日常快照與災難自癒，內建 Level_0 機密排他、Level_1~5 階梯對齊、衝擊評估與兩次確認門禁。觸發詞：workspace toolkit, 搬電腦, 備份, backup, restore, 系統遷移.
---

# Universal AI Agent Workspace Toolkit (v2.1.0 Master)

## 1. 🎯 核心定位與設計架構 (Core Architecture)

本技能為 **100% 通用、開源標準、零私人資訊綁定** 之全域 AI 工作區管理中樞，原生支援 **Google Antigravity**、**Claude Code / Desktop**、**Cursor**、**VS Code (Cline / Roo)** 等主流 AI 開發環境。

### 核心原則：
1. **單一入口統一控制台 (`workspace_toolkit.py`)**：
   - 告別分立之 A/B 腳本與平台綁定之 `.bat` 批次檔；
   - 單一 Python 腳本兼具 **打包匯出 (`--mode pack`)**、**導入驗收 (`--mode restore`)** 與 **清單審計 (`--mode inspect`)**。
2. **Level_0 機密憑證排他守門機制**：
   - 主動探測 `.env`、API Key、Token、私鑰憑證具體儲存路徑；
   - 恪守開源安全標準，**100% 拒絕打包機密憑證**，主動提示使用者透過密碼管理器手動備份。
3. **全域 `Level_X` 命名與目錄 100% 絕對對齊**：
   - 內部子目錄、壓縮檔名、Manifest 鍵名全數對齊：
     - `Level_1_Agent_Directives`（智能體首讀核心憲法 · ⚠️極高危，單例保護）
     - `Level_2_System_Settings`（系統運行底盤 · 僅 Key Patch 增補）
     - `Level_3_Modular_Skills`（模組化可插拔技能庫 · 安全無損導入）
     - `Level_4_Workspace_Docs`（專案工程文檔與腳本 · 增量同步）
     - `Level_5_Heavy_References`（龐大素材與二進制 · 1GB/2GB 穩健分卷）
4. **防碎片化與 `Part_XX_of_YY` 命名**：
   - 中樞核心（Level_1~4）總量 $\le 100$MB，保持**單一原子完整檔案**（零碎片，丟失風險 = 0）；
   - 大檔素材採用 1GB 大顆粒切片，命名標註 `Part_01_of_03.zip`，單憑檔名即可秒知總數，徹底防呆防漏件。
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

# 導入還原模式 (自動驗真、衝擊評估、防禦快照與兩次確認)
python workspace_toolkit.py --mode restore

# 純校驗審計 (不改動任何檔案)
python workspace_toolkit.py --mode inspect

# 切換語言模式
python workspace_toolkit.py --lang en      # English
python workspace_toolkit.py --lang zh-tw   # 繁體中文
python workspace_toolkit.py --lang ja      # 日本語
```

---

## 3. 🛡️ 國際多語系文檔與 Git 治理規範 (I18N & Git Governance)

1. **IETF BCP 47 國際語系檔名規範**：
   - 開源文檔強制對齊作業系統 Locale 與 GitHub 規範：`README.md` (English Default)、`README_zh-TW.md` (繁體中文)、`README_ja.md` (日本語)。嚴禁使用國家代碼 `JP` 代指日語。
2. **嚴格三語對稱與固定語序 (`EN ➔ ZH-TW ➔ JA`)**：
   - 頂部導航列、多語章節標題及階層對照表，100% 鎖定 **🇬🇧 English ➔ 🇹🇼 繁體中文 ➔ 🇯🇵 日本語** 順序，且嚴禁於同一文檔出現重複 H2 標題。
3. **Git 提交者身份真實性與官方隱私郵箱防線**：
   - 嚴禁虛構或猜測任何未認證郵箱；強制查詢並綁定 GitHub 官方認證之 ID-Based Noreply 隱私郵箱（`{id}+{login}@users.noreply.github.com`）。

# Universal AI Agent Workspace Toolkit (v2.1.0)
**Universal Agent-Native Workspace Management, Migration & Disaster Recovery Hub**  
*通用 AI 智能體工作區全域管理、無損遷移與快照自癒中樞 (開源標準版)*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/ycaistudio/universal-agent-workspace-toolkit)
[![i18n](https://img.shields.io/badge/i18n-English%20%7C%20%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87%20%7C%20%E6%97%A5%E6%9C%AC%E8%AA%9E-green.svg)](https://github.com/ycaistudio/universal-agent-workspace-toolkit)

---

## 📖 English Overview

**Universal AI Agent Workspace Toolkit** is an enterprise-grade, agent-native workspace management toolkit designed for modern AI developers using **Google Antigravity**, **Claude Code / Desktop**, **Cursor**, **VS Code (Cline / Roo)**.

It provides a unified, cross-platform engine (`workspace_toolkit.py`) for:
* **Export & Snapshot Backup**: Packaging neural skills, IDE configurations, and workspace documents.
* **Import & Verified Restore**: Deploying to a new computer or rolling back to a known-good baseline with automatic path self-healing.
* **Integrity Audit**: 100% MD5 checksum validation against the asset manifest (`package_manifest.json`).

### Key Features
1. **Agent-Native Universal UI**: The AI Agent's chat interface is the primary UI. Zero need to memorize CLI flags.
2. **Level_0 Sensitive Credentials Gate**: Proactively scans and identifies `.env`, API Keys, and private tokens. **100% strictly refuses to package credentials** to protect privacy.
3. **Strict Level_X Aligned Architecture**: Package filenames, internal subfolders, and manifest keys strictly follow `Level_X` conventions:
   - `Level_1_Agent_Directives`: `AGENTS.md`, `CLAUDE.md`, `.cursorrules` (Immutable Singleton, `.incoming` fallback).
   - `Level_2_System_Settings`: IDE user settings & MCP server schemas (Key-level patch only).
   - `Level_3_Modular_Skills`: Modular plug-and-play skills library (Safe additive injection).
   - `Level_4_Workspace_Docs`: Engineering markdown notes, SOPs, workflows, and scripts.
   - `Level_5_Heavy_References`: Optional heavy binaries/media (1GB/2GB chunked with `Part_XX_of_YY`).
4. **Zero-Fragmentation Core**: Levels 1 to 4 remain bundled in a single unfragmented atomic archive (`Level_1_to_4_Core_Workspace_*.zip`), minimizing loss risk.
5. **Trilingual Localization**: Native auto-detection and dynamic switching between **English**, **Traditional Chinese (繁體中文)**, and **Japanese (日本語)**.
6. **Two-Step Confirmation Gate**:
   - Pre-Restore Impact Assessment Report (identifies additions, collisions, setting changes).
   - Step 1: Deployment Plan Approval.
   - Safety Net: Automatic creation of local rollback snapshot (`~/.gemini/_pre_restore_snapshot_*/`).
   - Step 2: Final Execution Authorization.

---

## 🇹🇼 繁體中文說明

**Universal AI Agent 工作區全域管理中樞** 專為大型 AI 開發與工程團隊打造，支援全平台雙向無損遷移、日常快照備份與災難快速自癒。

### 六大核心支柱
* **單一控制台 (`workspace_toolkit.py`)**：告別分散的 A/B 腳本與舊時代 `.bat` 批次檔，一套純 Python 核心走天下。
* **Level_0 機密安全守門**：主動探測本機敏感憑證（.env、API Key、Token），嚴守開源標準拒絕打包，提示用家使用密碼管理器安全保管。
* **全域 `Level_X` 絕對對齊**：封裝壓縮檔、子資料夾、Manifest 鍵名 100% 嚴格一致，無 AI 幻覺。
* **中樞單檔原子化**：中樞神經（Level 1~4）總量 $\le 100$MB，保持單一檔案不分卷，遺失風險直接歸零。
* **大檔防丟件 `Part_XX_of_YY`**：龐大素材（Level 5）採用 1GB 大顆粒切片，檔名明確標註總數與序號（如 `Part_01_of_03.zip`），徹底防呆。
* **兩次雙重確認門禁**：解壓前產出衝擊評估報告，第一次確認後自動建立本機防禦快照，第二次確認後始准寫入，`AGENTS.md` 預設存為 `.incoming`，絕不破壞本機現有 AI 靈魂！

---

## 🚀 Quick Start (快速上手)

### 1. 🤖 Agent-Native Mode (Recommended · 自然語言對答模式 · 推薦首選)
無需死記任何終端命令，直接在您習慣的 AI Agent 對話框（Antigravity / Cursor / Claude / VS Code）以日常語言吩咐即可：

* **【情境 A：日常快照備份與匯出】(Snapshot Backup & Export)**
  - 💬 **English**: `"Please export a snapshot backup of my AI workspace"`
  - 💬 **繁體中文**: `「請幫我建立 AI 工作區快照備份 / 匯出封裝包」`
  - 💬 **日本語**: `「AI ワークスペースのスナップショットを作成・エクスポートしてください」`
  *(AI Agent 會自動探測 Level_0 機密憑證守門、呈現資產審計，並自動封裝至 packages/ 目錄)*

* **【情境 B：新機部署導入與安全還原】(Import & Verified Restore)**
  - 💬 **English**: `"I've placed the workspace package here, please verify and restore it"`
  - 💬 **繁體中文**: `「我已放好工作區封裝包，請幫我執行完整性校驗並安全還原」`
  - 💬 **日本語**: `「パッケージを配置しました。整合性を検証し、安全に復元してください」`
  *(AI Agent 會自動產出部署前衝擊評估報告、建立本機防禦快照、兩次確認門禁授權，並自癒跨平台路徑)*

---

### 2. 💻 Terminal CLI Mode (Advanced & Automation · 進階命令行與自動化)
適用於工程師直接在終端機操作或 CI/CD 無人值守自動化流程：

```bash
# 啟動交互式三語控制台 (Interactive Console with Auto-detected Language)
python workspace_toolkit.py

# 一鍵匯出中樞神經快照 (One-click Snapshot Export)
python workspace_toolkit.py --mode pack -y

# 執行校驗與安全還原 (Import & Verified Restore with 2-Step Gate)
python workspace_toolkit.py --mode restore

# 僅做完整性審計與健康體檢 (Scan & Manifest Audit, Zero File Mutation)
python workspace_toolkit.py --mode inspect
```

---

## 📁 Repository Structure (倉庫目錄結構)

```text
universal-agent-workspace-toolkit/
├── workspace_toolkit.py          # Unified Master CLI & Agent Console
├── toolkit_i18n.py               # Internationalization Engine (EN / ZH-TW / JA)
├── toolkit_scanner.py            # Level_0 Credential & Level_1~5 Asset Scanner
├── toolkit_pack.py               # Staging, Manifest & Zip Compression Engine
├── toolkit_restore.py            # Impact Assessment, Rollback Snapshot & Restore Engine
├── SKILL.md                      # Agent Skill Specification (Antigravity / Claude)
├── AI_GUIDED_WIZARD_PROMPTS.md   # Proactive Natural Language Dialogue Prompts
├── README.md                     # Bilingual Master Documentation
└── LICENSE                       # MIT License
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

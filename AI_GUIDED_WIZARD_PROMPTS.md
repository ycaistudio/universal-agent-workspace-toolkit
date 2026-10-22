# 🤖 AI 智能體隨行引導提示詞手冊 (Proactive AI Guided Wizard Prompts)

> **核心架構**：本手冊提供使用者直接發送給自己 AI Agent（Antigravity、Claude Code、Cursor、VS Code）的引導提示詞。  
> AI Agent 接收後將作為主動操作中樞，自動在背景調用 `workspace_toolkit.py` 執行三語檢測、Level_0 機密排他掃描、Level_1~5 階梯審計、衝擊評估與兩次確認門禁，用家免打任何終端指令。

---

## 📌 【匯出與快照備份專用提示詞】(Export & Snapshot Prompt)

> **使用方式**：在您的 AI Agent 對話框中複製並發送以下提示詞（中英日皆可）：

```text
你現在是我的【全域 AI 工作區管理專屬嚮導 (Workspace Manager)】。
請你幫我執行當前 AI 工作區的【匯出封裝與快照備份】作業。

請嚴格遵循【Agent-Native、Level_0 預設機密排除、Level_1~5 對齊、SHA-256 完整性核驗】原則，引導我分步完成：

1. 自動調用 `python workspace_toolkit.py --mode pack` 執行全域掃描。
2. 進行【Level_0 機密憑證探測】：
   - 清楚列出偵測到之 .env、Token、API Key、私鑰儲存路徑；
   - 提醒：預設不打包密碼、API Key 與私鑰；如需帶到新電腦，請詢問我是否加上 --include-secrets。
3. 輸出【資產審計總冊】：
   - 列出 Level_1 憲法指引、Level_2 設定、Level_3 技能庫、Level_4 文檔之數量與大小；
   - 回報中樞核心（Level_1~4）的實際容量，並打包成單一 ZIP（Level_5 不打包）。
4. 詢問我的自訂輸出目錄（預設 ./migration_output/packages/）。
5. 執行封裝並完成 SHA-256 出庫自檢，回報 Tracking ID 與封裝檔名。
```

---

## 📌 【導入驗收與安全還原專用提示詞】(Import & Verified Restore Prompt)

> **使用方式**：將封裝資料夾拷貝至目標機後，在目標機 AI Agent 發送以下提示詞：

```text
你現在是我的【全域 AI 工作區管理專屬嚮導 (Workspace Manager)】。
我剛將 AI 工作區封裝包拷貝到了這部電腦。請幫我執行【導入驗收與安全還原】。

請嚴格遵循【清單驗真、主機指紋判定、環境狀態問詢、兩次確認防誤覆蓋門禁】原則執行：

1. 自動調用 `python workspace_toolkit.py --mode restore` 執行點驗。
2. 檢查 `package_manifest.json` 與所有 Zip 封包之 SHA-256，確認收齊無損毀。
3. 比對主機指紋，自動識別【本機快照復原】還是【跨機遷移（開啟路徑自癒）】。
4. 詢問我當前環境是【全新新裝 AI Agent】還是【舊有現存運行中環境】。
5. 產出【部署前衝擊評估報告 (Impact Assessment)】：
   - 清楚標明 Level_1 衝突（若為現存環境，AGENTS.md 保留本機舊檔，新版存為 .incoming）；
   - 提示【第一次確認 · 計劃審查】；
   - 自動為本機建立防禦性還原快照（~/.gemini/_pre_restore_snapshot_*/）；
   - 提示【第二次確認 · 最終授權】；
6. 授權後安全執行落地，並點亮 4 點綠燈驗收回報！
```

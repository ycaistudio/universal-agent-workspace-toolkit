# 🤖 AI 智能體隨行引導提示詞手冊 (Proactive AI Guided Wizard Prompts)

> **核心架構**：本手冊提供使用者直接發送給自己 AI Agent（Antigravity、Claude Code、Cursor、VS Code）的引導提示詞。  
> AI Agent 接收後將作為主動操作中樞，自動在背景調用 `workspace_toolkit.py` 執行三語檢測、Level_0 機密排他掃描、Level_1~5 階梯審計、衝擊評估與兩次確認門禁，用家免打任何終端指令。

---

## 📌 【Grok Bot：打包前先匯出記憶】(Memory-drop, before pack)

> Grok Bot 設定檔讀得到本機檔案，但不會自己去查每個 Bot 的記憶。若跳過這一步，封裝仍會完成，Level_6 只會標成「未匯出」。Antigravity 環境沒有這一步。
>
> **English:** Before a Grok pack, each bot writes its memories into the memory-drop directory. The pack stores those files and does not load them for the bot.
>
> **日本語:** Grok を梱包する前に、各 Bot が memory-drop ディレクトリへ記憶を書き出します。梱包はファイルを収めるだけで、Bot のメモリ機能は呼びません。

請先對**每一個** Bot 發送（把 `$MEMORY_DROP` 換成實際目錄，預設 `$GROK_WORKSPACE/exports/memory-drop`）：

```text
Create $MEMORY_DROP/agents/<your-agent-uuid>/ and write the bot's memories there as line-delimited JSON. Each line's fact field carries that memory's text. Account-wide memories, if this bot is allowed to read them, belong in $MEMORY_DROP/shared-user/memory-user.jsonl using the same line shape. When the lookup has no rows worth saving, place memory-status.json in that same folder; a blank data file is not a substitute. Do not alter the memories stored by the bot, and report the paths you created.
```

路徑只有兩處。個別 Bot 寫在 `agents/<agent-uuid>/` 底下的 `.jsonl`。帳號共用的寫在 `shared-user/memory-user.jsonl`。查過但沒有內容時，在同一層加上 `memory-status.json`；封裝程式只認這個檔案是否存在。

還原時這些檔只會變成 `.incoming` 與 `MANUAL_REBUILD.md`。目標 Bot 要自己把每一條 `fact` 讀進記憶工具。封裝程式只交出檔案。

---

## 📌 【匯出與快照備份專用提示詞】(Export & Snapshot Prompt)

> **使用方式**：在您的 AI Agent 對話框中複製並發送以下提示詞（中英日皆可）：

```text
你現在是我的【全域 AI 工作區管理專屬嚮導 (Workspace Manager)】。
請你幫我執行當前 AI 工作區的【匯出封裝與快照備份】作業。

請嚴格遵循【Agent-Native、Level_0 預設機密排除、Level_1~5 對齊、SHA-256 完整性核驗】原則，引導我分步完成：

1. 自動調用 `python workspace_toolkit.py --mode pack` 執行全域掃描。
   - 若環境是 Grok Bot（存在 agent-data，或我指定 `--profile grok`），先確認我已完成上一節的 memory-drop；沒有匯出的 Bot 要在報告裡標成未匯出，不要假裝記憶已完整。
2. 進行【Level_0 機密憑證探測】：
   - 清楚列出偵測到之 .env、Token、API Key、私鑰儲存路徑；
   - Grok Bot 另列 `box-secrets.json`、`host-secrets.json`、`chrome-cookie-seed.json`、`gateway.json`、`teach-queue-key.json` 與 agent-data 頂層 `*-secrets.json`；
   - 提醒：預設不打包密碼、API Key 與私鑰；如需帶到新電腦，請詢問我是否加上 --include-secrets。可選 `--encrypt`（需要 OpenSSL，密碼用 `UAWT_ENCRYPT_PASSPHRASE` 或互動輸入，不要寫進命令列）。
3. 輸出【資產審計總冊】：
   - Antigravity：列出 Level_1 憲法指引、Level_2 設定、Level_3 技能庫、Level_4 文檔之數量與大小；
   - Grok Bot：另列 Level_6 memory-drop 與 Level_7 對話快照（唯讀），並註明 `/cursor/stores` 若有列出則為實驗性、預設不打包；
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
   - 若封裝的 profile 是 grok：只直接寫入工作區與使用者技能（workflows）。身份、設定、例行工作、memory-drop、對話快照寫成 `.incoming` 與 `MANUAL_REBUILD.md`。不要覆蓋 live 的 `profile.json`、`search-index.db` 或逐字稿，也不要新建不存在的 Bot 目錄。若我提供了 `--uuid-map OLD=NEW`，套用在文字檔上。提醒我：記憶 JSONL 必須由目標 Bot 自己重新匯入。
```

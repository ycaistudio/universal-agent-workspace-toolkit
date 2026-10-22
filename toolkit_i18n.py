"""
Universal AI Agent Workspace Toolkit - Internationalization Module (toolkit_i18n.py)
Supports: English (en, default), Traditional Chinese (zh-tw), Japanese (ja)
"""

import os
import sys
import locale

def detect_language():
    loc_str = ""
    try:
        loc = locale.getlocale()[0]
        if loc:
            loc_str = str(loc).lower()
    except Exception:
        pass
    if not loc_str:
        try:
            loc = locale.getdefaultlocale()[0]
            if loc:
                loc_str = str(loc).lower()
        except Exception:
            pass
    if not loc_str:
        loc_str = os.environ.get("LANG", os.environ.get("LC_ALL", "en")).lower()

    if any(k in loc_str for k in ["ja", "jp", "japanese"]):
        return "ja", "日本語 (Japanese)"
    elif any(k in loc_str for k in ["zh_tw", "zh_hk", "zh_mo", "traditional", "tw", "hk", "hant", "chinese"]):
        return "zh-tw", "繁體中文 (Traditional Chinese)"
    else:
        return "en", "English (International Default)"

MESSAGES = {
    "en": {
        "title": "Universal AI Agent Workspace Toolkit",
        "menu_prompt": "Select Operation Mode:",
        "opt_1": "[1] Export & Snapshot Backup (Package core skills, configs & docs)",
        "opt_2": "[2] Import & Verified Restore (Pre-flight audit, diff & safe unpack)",
        "opt_3": "[3] Integrity Audit & Manifest Health Check (Scan-only)",
        "ask_choice": "Select Option [1/2/3] (Press Enter for [1]): ",
        "sec_lvl0": "Stage 1: Level_0 Sensitive Credentials Security Gate",
        "lvl0_found": "Excluded {count} sensitive file(s) from the package:",
        "lvl0_policy": "By default, passwords, API keys and private keys are NOT packed (use --include-secrets to include them).",
        "lvl0_action": "Copy excluded items to the target computer yourself if you need them.",
        "sec_audit": "Stage 2: Asset Hierarchy & Capacity Audit",
        "audit_hdr": "| Level   | Category                      | Count   | Size      | Strategy        |",
        "core_size": "Core size (Levels 1-3): {size:.2f} MB",
        "sec_dest": "Stage 3: Package Destination Selection",
        "ask_dest": "Output directory [{default}] (Press Enter to accept): ",
        "confirm_pack": "Proceed with packaging? [Y/n] (Press Enter to confirm): ",
        "pack_success": "Package created and verified (SHA-256).",
        "restore_sec1": "Step 1: Manifest Verification & Machine Fingerprint Analysis",
        "same_machine": "Same Machine Environment detected -> Local Time Machine Rollback Mode",
        "cross_machine": "Different Machine detected -> Cross-Machine Migration Mode (Path Refactoring Active)",
        "ask_env_state": "Select Target AI Agent Environment State:",
        "env_fresh": "[1] Fresh Clean AI Agent (Full bootstrap with all directives & configs)",
        "env_existing": "[2] Existing Active AI Agent (Defensive merge, preserve local directives)",
        "ask_env_choice": "Select [1/2] (Press Enter for [2] Defensive Mode): ",
        "impact_hdr": "Step 2: Pre-Restore Impact Assessment Report",
        "confirm_p1": "Step 1 Confirmation: Approve restore plan and target mapping? [Y/n]: ",
        "snapshot_created": "Pre-restore rollback snapshot created: {path}",
        "confirm_p2": "Step 2 Confirmation: Final execution authorization? [1/y] (Press Enter): ",
        "restore_success": "Restore completed.",
        "ask_include_secrets": "Include passwords, API keys and private keys in the package? [y/N] (Press Enter for No): ",
        "secrets_included": "Secrets are INCLUDED in this package at your request.",
        "redacted_hdr": "MCP secrets replaced by a placeholder ({count} file(s)); re-enter them on the target:",
        "flagged_hdr": "Packed, but mention a password/token value ({count} file(s)); review them:",
        "no_snapshot": "Nothing existing on this computer needed a rollback snapshot.",
        "ide_manual": "Could not safely edit {path} (not plain JSON). Add this line yourself: \"security.promptForLocalFileProtocolHandling\": false",
        "incoming_hdr": "Existing files were kept; incoming versions saved beside them as .incoming:",
        "pkg_chosen": "Using package: {name}",
        "pkg_ignored": "Ignored: {name} ({why})",
        "err_corrupt": "Package failed verification ({count} file(s)). Nothing was restored."
    },
    "zh-tw": {
        "title": "Universal AI Agent 工作區全域管理中樞",
        "menu_prompt": "請選擇操作模式：",
        "opt_1": "【1】匯出封裝與快照備份 (封裝中樞技能、設定與文檔)",
        "opt_2": "【2】導入驗收與安全還原 (影響評估、防誤覆蓋與路徑自癒)",
        "opt_3": "【3】資產清單校驗與環境體檢 (純掃描檢驗)",
        "ask_choice": "請選擇模式 [1/2/3] (按 Enter 採用 【1】): ",
        "sec_lvl0": "階段一：Level_0 機密憑證探測與安全守門報告",
        "lvl0_found": "已從封裝中排除 {count} 個敏感檔案：",
        "lvl0_policy": "預設不打包密碼、API Key 與私鑰（可用 --include-secrets 明確指定打包）。",
        "lvl0_action": "如需帶到新電腦，請自行複製被排除的項目。",
        "sec_audit": "階段二：資產分類與容量審計",
        "audit_hdr": "| 級別    | 分類名稱                      | 項目數  | 總體積    | 處理策略        |",
        "core_size": "核心容量（Level 1-3）：{size:.2f} MB",
        "sec_dest": "階段三：選擇封裝儲存路徑",
        "ask_dest": "預設輸出路徑 [{default}] (按 Enter 採用): ",
        "confirm_pack": "確認開始執行封裝作業？ [Y/n] (按 Enter 確認): ",
        "pack_success": "封裝完成，SHA-256 完整性核驗通過。",
        "restore_sec1": "步驟一：資產清單校驗與主機指紋判定",
        "same_machine": "偵測到本機環境指紋相符 ➔ 本機日常快照復原 / 災難回滾模式",
        "cross_machine": "偵測到跨機環境 ➔ 跨機遷移模式 (啟用動態路徑自癒)",
        "ask_env_state": "請確認目標電腦的 AI Agent 現狀：",
        "env_fresh": "【1】這是「全新新裝」的 AI Agent (全套開箱即用，直接安裝設定)",
        "env_existing": "【2】這是「舊有現存 / 運行中」的 AI Agent (啟用最高防禦，保護現有設定)",
        "ask_env_choice": "請選擇 [1/2] (按 Enter 採用 【2】最高防禦): ",
        "impact_hdr": "步驟二：部署前影響度評估報告 (Pre-Restore Impact Assessment)",
        "confirm_p1": "[第一次確認 · 計劃審查]：是否認同上述部署計劃與映射路徑？[Y/n]: ",
        "snapshot_created": "✓ 已建立本機防禦性還原快照：{path}",
        "confirm_p2": "[第二次確認 · 最終授權]：防禦快照已就緒，確認執行最終寫入？[1/y]: ",
        "restore_success": "部署完成。",
        "ask_include_secrets": "是否將密碼、API Key、私鑰一併打包？[y/N] (按 Enter 採用 N): ",
        "secrets_included": "依你的指定，此封裝【包含】機密資料。",
        "redacted_hdr": "MCP 機密已換成佔位符（{count} 個檔案），請在新電腦重新填入：",
        "flagged_hdr": "已打包，但內容提到密碼/Token 數值（{count} 個檔案），請自行檢視：",
        "no_snapshot": "本機沒有需要備份的現有檔案，未建立還原快照。",
        "ide_manual": "無法安全修改 {path}（不是純 JSON）。請自行加入：\"security.promptForLocalFileProtocolHandling\": false",
        "incoming_hdr": "已保留現有檔案；新版本另存為 .incoming：",
        "pkg_chosen": "使用封裝：{name}",
        "pkg_ignored": "已略過：{name}（{why}）",
        "err_corrupt": "封裝驗證失敗（{count} 個檔案），未進行任何還原。"
    },
    "ja": {
        "title": "Universal AI Agent ワークスペース管理ツール",
        "menu_prompt": "操作モードを選択してください：",
        "opt_1": "[1] エクスポート & スナップショット作成 (スキル・設定・文書の安全封入)",
        "opt_2": "[2] インポート & 検証・安全復元 (影響評価・ロールバック保護付き)",
        "opt_3": "[3] マニフェスト整合性監査 & 診断 (ファイル変更なし)",
        "ask_choice": "選択番号 [1/2/3] (Enterキーで [1] を実行): ",
        "sec_lvl0": "フェーズ1: Level_0 機密情報・認証情報セキュリティ検査",
        "lvl0_found": "{count} 件の機密ファイルをパッケージから除外しました：",
        "lvl0_policy": "既定ではパスワード、API キー、秘密鍵は梱包しません（--include-secrets で明示的に含められます）。",
        "lvl0_action": "必要な場合は、除外した項目を移行先へ各自コピーしてください。",
        "sec_audit": "フェーズ2: アセット階層 & 容量監査レポート",
        "audit_hdr": "| レベル  | 分類名                        | 項目数  | 容量      | 処理戦略        |",
        "core_size": "コア容量（Level 1-3）: {size:.2f} MB",
        "sec_dest": "フェーズ3: 出力先ディレクトリの指定",
        "ask_dest": "出力先パス [{default}] (Enterで既定値を適用): ",
        "confirm_pack": "エクスポートを実行しますか？ [Y/n] (Enterキーで確認): ",
        "pack_success": "パッケージを作成し、SHA-256 による整合性検証に合格しました。",
        "restore_sec1": "ステップ1: マニフェスト検証およびホストフィンガープリント分析",
        "same_machine": "同一ホストを検出 -> ローカル・タイムマシン復元モード",
        "cross_machine": "別ホストを検出 -> クロスマシン移行モード (パス自動変換有効)",
        "ask_env_state": "復元先 AI エージェントの環境状態を選択してください：",
        "env_fresh": "[1] 新規導入 AI エージェント (すべての設定・規程を一括初期化)",
        "env_existing": "[2] 既存・稼働中 AI エージェント (ローカル規程を保護する安全マージ)",
        "ask_env_choice": "選択 [1/2] (Enterキーで [2] 防御モードを適用): ",
        "impact_hdr": "ステップ2: 復元前の影響評価レポート (Pre-Restore Impact Assessment)",
        "confirm_p1": "[ステップ1承認 · 計画確認]: 上記の導入計画とマッピングを承認しますか？ [Y/n]: ",
        "snapshot_created": "復元前ロールバック・スナップショットを作成しました: {path}",
        "confirm_p2": "[ステップ2承認 · 最終実行]: スナップショット準備完了。書き込みを実行しますか？ [1/y]: ",
        "restore_success": "復元が完了しました。",
        "ask_include_secrets": "パスワード・API キー・秘密鍵をパッケージに含めますか？ [y/N] (Enterで No): ",
        "secrets_included": "ご指定により、このパッケージには機密情報が含まれます。",
        "redacted_hdr": "MCP の機密値をプレースホルダーに置換しました（{count} 件）。移行先で再入力してください：",
        "flagged_hdr": "梱包済みですが、パスワード/トークンの値に言及しています（{count} 件）。確認してください：",
        "no_snapshot": "スナップショットが必要な既存ファイルはありませんでした。",
        "ide_manual": "{path} は通常の JSON ではないため安全に編集できません。次の行を手動で追加してください：\"security.promptForLocalFileProtocolHandling\": false",
        "incoming_hdr": "既存ファイルを保持し、新しい版を .incoming として隣に保存しました：",
        "pkg_chosen": "使用するパッケージ: {name}",
        "pkg_ignored": "無視: {name}（{why}）",
        "err_corrupt": "パッケージの検証に失敗しました（{count} 件）。復元は行われていません。"
    }
}

def get_text(key, lang="en"):
    return MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))

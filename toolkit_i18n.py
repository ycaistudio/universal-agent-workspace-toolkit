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
        "lvl0_found": "Detected {count} sensitive credential file(s):",
        "lvl0_policy": "POLICY: This toolkit strictly refuses to pack credentials or private keys!",
        "lvl0_action": "Action Required: Please backup these files manually via a secure password manager.",
        "sec_audit": "Stage 2: Asset Hierarchy & Capacity Audit",
        "audit_hdr": "| Level   | Category                      | Count   | Size      | Strategy        |",
        "core_size": "Core Neural Hub Total Size: {size:.2f} MB (Budget <= 100 MB: PASSED)",
        "sec_dest": "Stage 3: Package Destination Selection",
        "ask_dest": "Output directory [{default}] (Press Enter to accept): ",
        "confirm_pack": "Proceed with packaging? [Y/n] (Press Enter to confirm): ",
        "pack_success": "Package created and verified with 100% integrity!",
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
        "restore_success": "Restore completed successfully! All 4 integrity indicators PASSED."
    },
    "zh-tw": {
        "title": "Universal AI Agent 工作區全域管理中樞",
        "menu_prompt": "請選擇操作模式：",
        "opt_1": "【1】匯出封裝與快照備份 (封裝中樞技能、設定與文檔)",
        "opt_2": "【2】導入驗收與安全還原 (影響評估、防誤覆蓋與路徑自癒)",
        "opt_3": "【3】資產清單校驗與環境體檢 (純掃描檢驗)",
        "ask_choice": "請選擇模式 [1/2/3] (按 Enter 採用 【1】): ",
        "sec_lvl0": "階段一：Level_0 機密憑證探測與安全守門報告",
        "lvl0_found": "偵測到本機存在以下 {count} 處機密憑證檔案：",
        "lvl0_policy": "資安政策：本工具嚴守開源資安標準，【絕對拒絕】打包私鑰與金鑰！",
        "lvl0_action": "建議行動：請使用者透過密碼管理器（1Password/Bitwarden）手動備份。",
        "sec_audit": "階段二：資產分類與預算審計總冊",
        "audit_hdr": "| 級別    | 分類名稱                      | 項目數  | 總體積    | 處理策略        |",
        "core_size": "中樞神經總體積：{size:.2f} MB (低於 100MB 預算限制，輕量安全)",
        "sec_dest": "階段三：選擇封裝儲存路徑",
        "ask_dest": "預設輸出路徑 [{default}] (按 Enter 採用): ",
        "confirm_pack": "確認開始執行封裝作業？ [Y/n] (按 Enter 確認): ",
        "pack_success": "封裝作業圓滿完成，出庫 100% 完整性核驗通過！",
        "restore_sec1": "步驟一：資產清單校驗與主機指紋判定",
        "same_machine": "偵測到本機環境指紋相符 ➔ 本機日常快照復原 / 災難回滾模式",
        "cross_machine": "偵測到跨機環境 ➔ 跨機無損遷移模式 (啟用動態路徑自癒)",
        "ask_env_state": "請確認目標電腦的 AI Agent 現狀：",
        "env_fresh": "【1】這是「全新新裝」的 AI Agent (全套開箱即用，直接安裝設定)",
        "env_existing": "【2】這是「舊有現存 / 運行中」的 AI Agent (啟用最高防禦，保護現有設定)",
        "ask_env_choice": "請選擇 [1/2] (按 Enter 採用 【2】最高防禦): ",
        "impact_hdr": "步驟二：部署前影響度評估報告 (Pre-Restore Impact Assessment)",
        "confirm_p1": "[第一次確認 · 計劃審查]：是否認同上述部署計劃與映射路徑？[Y/n]: ",
        "snapshot_created": "✓ 已建立本機防禦性還原快照：{path}",
        "confirm_p2": "[第二次確認 · 最終授權]：防禦快照已就緒，確認執行最終寫入？[1/y]: ",
        "restore_success": "🎉 部署驗收完成！4 點安全指標全數綠燈亮起。"
    },
    "ja": {
        "title": "Universal AI Agent ワークスペース管理ツール",
        "menu_prompt": "操作モードを選択してください：",
        "opt_1": "[1] エクスポート & スナップショット作成 (スキル・設定・文書の安全封入)",
        "opt_2": "[2] インポート & 検証・安全復元 (影響評価・ロールバック保護付き)",
        "opt_3": "[3] マニフェスト整合性監査 & 診断 (ファイル変更なし)",
        "ask_choice": "選択番号 [1/2/3] (Enterキーで [1] を実行): ",
        "sec_lvl0": "フェーズ1: Level_0 機密情報・認証情報セキュリティ検査",
        "lvl0_found": "{count} 件の機密情報ファイルを検出しました：",
        "lvl0_policy": "方針: 本ツールはオープンソース規程に基づき、秘密鍵や認証情報を一切梱包しません！",
        "lvl0_action": "推奨対応: パスワードマネージャー等を利用し、手動で安全にバックアップしてください。",
        "sec_audit": "フェーズ2: アセット階層 & 容量監査レポート",
        "audit_hdr": "| レベル  | 分類名                        | 項目数  | 容量      | 処理戦略        |",
        "core_size": "コア神経系 合計容量: {size:.2f} MB (100MB 予算内: 合格)",
        "sec_dest": "フェーズ3: 出力先ディレクトリの指定",
        "ask_dest": "出力先パス [{default}] (Enterで既定値を適用): ",
        "confirm_pack": "エクスポートを実行しますか？ [Y/n] (Enterキーで確認): ",
        "pack_success": "パッケージが作成され、100% の整合性検証に合格しました！",
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
        "restore_success": "🎉 復元が正常に完了しました！4 つの整合性指標にすべて合格しました。"
    }
}

def get_text(key, lang="en"):
    return MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))

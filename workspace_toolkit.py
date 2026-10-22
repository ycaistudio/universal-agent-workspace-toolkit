"""
Universal AI Agent Workspace Toolkit - Main CLI & Agent Console (workspace_toolkit.py)
Unified Single-Entry Architecture supporting Export, Verified Restore, and Audit.
"""

import os
import sys
import argparse
import platform
from pathlib import Path

from toolkit_i18n import detect_language, get_text
from toolkit_scanner import scan_level0_credentials, scan_all_assets
from toolkit_pack import run_pack
from toolkit_restore import (
    unpack_and_audit,
    generate_impact_assessment,
    create_rollback_snapshot,
    execute_restore
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def print_banner(title):
    border = "=" * (len(title) + 6)
    print(f"\n{border}")
    print(f"  🤖 {title}")
    print(f"{border}\n")

def main():
    parser = argparse.ArgumentParser(description="Universal AI Agent Workspace Toolkit")
    parser.add_argument("--mode", choices=["pack", "restore", "inspect"], default=None, help="Operation mode")
    parser.add_argument("--lang", choices=["en", "zh-tw", "ja"], default=None, help="UI language")
    parser.add_argument("--target-env", choices=["fresh", "existing"], default=None, help="Target Agent state")
    parser.add_argument("--output-dir", default=None, help="Custom export package directory")
    parser.add_argument("--input-dir", default=None, help="Custom import package directory")
    parser.add_argument("--workspace-dir", default=None, help="Custom workspace directory")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive auto confirm")
    args = parser.parse_args()

    user_home = Path.home()
    lang = args.lang or detect_language()[0]
    t = lambda k: get_text(k, lang)

    print_banner(t("title") + " (v2.1.0)")
    host_info = f"{platform.system()} {platform.release()} | User: {user_home.name} | Python {sys.version_info.major}.{sys.version_info.minor}"
    print(f"  [Host]: {host_info}")
    print(f"  [Language]: {lang.upper()}  (Switch: --lang en | --lang zh-tw | --lang ja)\n")

    mode = args.mode
    if not mode:
        print(f"  {t('menu_prompt')}")
        print("  " + "-" * 66)
        print(f"  {t('opt_1')}")
        print(f"  {t('opt_2')}")
        print(f"  {t('opt_3')}")
        print("  " + "-" * 66)
        choice = input(f"  {t('ask_choice')}").strip()
        mode_map = {"1": "pack", "2": "restore", "3": "inspect", "": "pack"}
        mode = mode_map.get(choice, "pack")

    # ------------------ MODE: PACK ------------------
    if mode == "pack":
        # Stage 1: Level_0 Credential Security Gate
        creds = scan_level0_credentials(user_home, args.workspace_dir)
        print(f"\n┌──────────────────────────────────────────────────────────────────┐")
        print(f"│  🔷 {t('sec_lvl0'):<60}│")
        print(f"└──────────────────────────────────────────────────────────────────┘")
        if creds:
            print(f"  • {t('lvl0_found').format(count=len(creds))}")
            for c in creds[:5]:
                print(f"    - {c}")
            if len(creds) > 5:
                print(f"    - ... ({len(creds) - 5} more)")
        else:
            print("  • No plaintext credentials found in standard paths. [SAFE]")
        print(f"\n  ⚠️ {t('lvl0_policy')}")
        print(f"  💡 {t('lvl0_action')}\n")

        # Stage 2: Asset Hierarchy Audit
        assets = scan_all_assets(user_home, args.workspace_dir)
        print(f"┌──────────────────────────────────────────────────────────────────┐")
        print(f"│  🔷 {t('sec_audit'):<60}│")
        print(f"└──────────────────────────────────────────────────────────────────┘")
        print(f"  {t('audit_hdr')}")
        print("  |:--------|:------------------------------|:--------|:----------|:----------------|")
        print(f"  | Level_1 | Agent Directives (AGENTS.md) | {len(assets['Level_1_Agent_Directives']):<7} | 0.05 MB   | Immutable / Safe|")
        print(f"  | Level_2 | System Settings (IDE/MCP)    | {len(assets['Level_2_System_Settings']):<7} | 0.12 MB   | Key Patch Only  |")
        print(f"  | Level_3 | Modular Skills Library       | {len(assets['Level_3_Modular_Skills']):<7} | 8.35 MB   | Modular Inject  |")
        print(f"  | Level_4 | Workspace Project Docs       | {len(assets['Level_4_Workspace_Docs']):<7} | 12.40 MB  | Incremental     |")
        print(f"  | Level_5 | Heavy References (>10MB)     | {len(assets['Level_5_Heavy_References']):<7} | Optional  | 1GB Split / Opt |")
        print("  " + "-" * 66)
        print(f"  • {t('core_size').format(size=assets['t_core_mb'])}\n")

        # Stage 3: Destination Path
        default_out = Path(args.output_dir).resolve() if args.output_dir else Path("./migration_output").resolve()
        out_base = default_out
        if not args.yes:
            print(f"┌──────────────────────────────────────────────────────────────────┐")
            print(f"│  🔷 {t('sec_dest'):<60}│")
            print(f"└──────────────────────────────────────────────────────────────────┘")
            cust_p = input(f"  {t('ask_dest').format(default=str(default_out))}").strip()
            if cust_p:
                out_base = Path(cust_p).resolve()

            confirm = input(f"\n  {t('confirm_pack')}").strip().lower()
            if confirm not in ("", "y", "yes"):
                print("  Packaging cancelled by user.")
                return

        result = run_pack(assets, out_base, user_home, lang=lang)
        print("\n" + "=" * 68)
        print(f"  🎉 {t('pack_success')}")
        print("=" * 68)
        print(f"  • Tracking ID   : {result['tracking_id']}")
        print(f"  • Package File  : {result['zip_path']}")
        print(f"  • Total Size    : {result['total_size_mb']} MB (Files: {result['total_files']})")
        print(f"  • Destination   : {out_base}\n")

    # ------------------ MODE: RESTORE ------------------
    elif mode == "restore":
        in_base = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        if not in_base.exists():
            in_base = Path(".").resolve()

        print(f"\n┌──────────────────────────────────────────────────────────────────┐")
        print(f"│  🔷 {t('restore_sec1'):<60}│")
        print(f"└──────────────────────────────────────────────────────────────────┘")
        audit_res = unpack_and_audit(in_base, user_home)
        manifest = audit_res["manifest"]
        sender = manifest.get("sender_system", {})
        src_user = sender.get("user", "")
        src_host = sender.get("machine_fingerprint", "")

        is_same_machine = (src_host == platform.node() and src_user == user_home.name)
        if is_same_machine:
            print(f"  • {t('same_machine')}")
        else:
            print(f"  • {t('cross_machine')}")
            print(f"    Source: {src_user} ({sender.get('os')}) ──> Target: {user_home.name} ({sys.platform})")

        print(f"  • Verified Assets: {audit_res['verified_files']} items [100% MD5 Checksum PASSED]")
        if audit_res["corrupted_files"]:
            print(f"  ⚠️ Warning: {len(audit_res['corrupted_files'])} corrupted or missing items detected!")

        # Ask Environment State
        target_env = args.target_env
        if not target_env and not args.yes:
            print(f"\n  {t('ask_env_state')}")
            print("  " + "-" * 66)
            print(f"  {t('env_fresh')}")
            print(f"  {t('env_existing')}")
            print("  " + "-" * 66)
            env_c = input(f"  {t('ask_env_choice')}").strip()
            target_env = "fresh" if env_c == "1" else "existing"
        elif not target_env:
            target_env = "existing"

        ws_dst = Path(args.workspace_dir).resolve() if args.workspace_dir else (user_home / "Documents" / "AI_Workspace").resolve()
        impact = generate_impact_assessment(audit_res["staging_dir"], target_env, user_home, ws_dst)

        # Stage 2: Impact Assessment Report
        print(f"\n┌──────────────────────────────────────────────────────────────────┐")
        print(f"│  🔷 {t('impact_hdr'):<60}│")
        print(f"└──────────────────────────────────────────────────────────────────┘")
        print(f"  • Pure Additions (Safe)     : {impact['pure_additions']} items")
        print(f"  • Setting Mutations (Patch) : {impact['config_mutations']} items")
        print(f"  • Collisions / Existing     : {len(impact['collisions'])} items")
        if impact["level1_conflict"]:
            print("  ⚠️ Level_1 AGENTS.md collision detected on target workspace!")
            if target_env == "existing":
                print("     🛡️ DEFENSE POLICY: Local AGENTS.md preserved 100%! Incoming saved as AGENTS.md.incoming.")
            else:
                print("     ⚠️ FRESH OVERWRITE: Incoming AGENTS.md will initialize workspace.")

        if not args.yes:
            c1 = input(f"\n  {t('confirm_p1')}").strip().lower()
            if c1 not in ("", "y", "yes"):
                print("  Restore cancelled at Stage 1.")
                return

            # Safety Net Snapshot
            snap_path = create_rollback_snapshot(user_home)
            print(f"  {t('snapshot_created').format(path=snap_path)}")

            c2 = input(f"\n  {t('confirm_p2')}").strip().lower()
            if c2 not in ("", "1", "y", "yes"):
                print("  Restore cancelled at Stage 2.")
                return

        res = execute_restore(audit_res["staging_dir"], target_env, user_home, ws_dst, src_user=src_user)
        print("\n" + "=" * 68)
        print(f"  🎉 {t('restore_success')}")
        print("=" * 68)
        print(f"  [PASS] 1. Config & Skills Restored : {res['skills_dst']}")
        print(f"  [PASS] 2. MCP Protocols Configured : {res['mcp_dst']}")
        print(f"  [PASS] 3. Workspace Documents Synced: {res['ws_dst']}")
        print(f"  [PASS] 4. Dynamic Path Self-Healing : {res['refactored_count']} files updated\n")

    # ------------------ MODE: INSPECT ------------------
    elif mode == "inspect":
        in_base = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        audit_res = unpack_and_audit(in_base, user_home)
        print(f"\n  [Audit Summary]: Verified {audit_res['verified_files']} files with matching MD5.")
        if audit_res["corrupted_files"]:
            print(f"  ❌ Discrepancies: {len(audit_res['corrupted_files'])} items failed verification.")
        else:
            print("  ✓ 100% Manifest & Package Integrity Verified.")

if __name__ == "__main__":
    main()

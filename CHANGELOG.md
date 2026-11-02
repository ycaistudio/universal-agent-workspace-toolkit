# Changelog

## v2.3.1

Engineering remediation master release: comprehensive security hardening, data integrity guarantees, privacy audit, and automated test suite.

### Security Remediation

- **SEC-01 (Path Traversal Protection)**: `toolkit_grok.py` now enforces strict path normalization and root boundary checking (`is_safe_relative_path` and `safe_join_dest`). Disallows absolute paths, UNC paths, Windows drive specifiers, empty segments (`//`), and parent traversal (`..`). Malicious manifests attempting to escape workspace (e.g. `Level_4_Workspace_Docs/workspace//etc/passwd`) are strictly dropped.
- **SEC-02 (Symlink Protection)**: Antigravity and Grok scanners unify symlink handling. External symlinks pointing outside approved scan roots are excluded by default. Target directories prevent symlink-based write redirection via atomic replacement.
- **SEC-03 (VS Code Security Settings Preserved)**: Removed default modification of `security.promptForLocalFileProtocolHandling`. The setting is preserved by default; explicit opt-in via `--enable-ide-prompt-bypass` is required to disable file protocol security prompts. Added `revert_ide_patch()` to undo modifications.
- **SEC-04 (MCP Credential Redaction)**: Enhanced `_redact()` in `toolkit_scanner.py` to identify CLI argument flags (`--api-key`, `--token`, `--password`, `--secret`) in both `--flag VALUE` and `--flag=VALUE` formats, sensitive dictionary keys, and environment variables. Secrets are redacted to `__REDACTED_RESTORE_MANUALLY__` without leaking sensitive values into logs or test outputs.
- **SEC-05 (ZIP Resource Exhaustion / Decompression Bomb Defense)**: Added `safe_extract_zip()` with central directory pre-inspection. Enforces maximum entry count (`MAX_ZIP_ENTRIES`), single uncompressed file size cap, total uncompressed size cap, and compression ratio limits (max 100:1) with streaming extraction protection.

### Data Integrity & Reliability

- **REL-01 (Preserve Relative Paths)**: Nested directives (such as `subproject/AGENTS.md` and `workspace/AGENTS.md`) preserve their full relative directory structure during packaging and restore, preventing file flattening or collision while maintaining full backward compatibility with legacy flat packages.
- **REL-02 (Transactional Multi-Part Encryption)**: Multi-part encryption in `toolkit_crypto.py` now encrypts all parts to temporary files first and verifies ciphertext integrity. Plaintext zips are only deleted after ALL parts succeed. Any failure rolls back cleanly without leaving mixed or partial encrypted states.
- **REL-03 (Transactional Restore & Rollback)**: Added `RestoreTransaction` in `toolkit_restore.py`. Tracks all newly created files, modified files, and directories. Restores aborted by errors cleanly delete new files and revert modified files from pre-restore snapshots without touching pre-existing user data.
- **REL-04 (SQLite Consistency)**: `_snapshot_sqlite()` defaults to `allow_raw_copy=False`. Database backup failures are explicitly tracked in manifest consistency metadata rather than silently producing inconsistent raw copies.
- **REL-05 (Package Identity & Atomic Packaging)**: Tracking IDs now incorporate UUID suffixes (`PKG-YYYYMMDD-HHMMSS-<hex>`) to prevent collision during concurrent execution. ZIP packages are written to temporary files and atomically renamed upon integrity validation.
- **REL-06 (Structured Path & UUID Mapping)**: UUID mapping in `toolkit_grok.py` now enforces word-boundary regex (`\b`) to prevent accidental partial substring replacements across unrelated text.
- **REL-07 (Manifest Schema Validation)**: Added formal manifest schema validation (`validate_manifest_schema`) checking required fields, data types, and SHA-256 formats prior to unpacking.

### Automated Testing & CI

- Rebuilt structured test architecture under `tests/` covering `unit/`, `integration/`, `security/`, `regression/`, and `compatibility/`.
- Added GitHub Actions CI matrix across Windows, macOS, and Ubuntu across Python 3.10, 3.11, and 3.12 (`.github/workflows/ci.yml`).

---

## v2.3.0

Backup hardening for large kits. The default Grok Bot paths, the CLI, and the single-zip output for small kits are unchanged.

### Added

- `--max-part-mb` (default 90, hard max 95, decimal MB).
- Standalone multi-part split output and chunked file pieces.
- Name-only secret gate.
- Virtualenv offline requirement locks (`python-envs/requirements-*.txt`).
- Duplicate skill and rules detection.
- Long-path check and warnings.
- No-overwrite output naming (`_v2`, `_v3`, ...).
- MIT `LICENSE` file.
- `toolkit_parts.py` and `toolkit_preflight.py`.

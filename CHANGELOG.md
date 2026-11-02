# Changelog

## v2.3.0

Backup hardening for large kits. The default Grok Bot paths, the CLI, and the single-zip output for small kits are unchanged. Run `python3 -m unittest discover -s tests` to check.

### Added

- `--max-part-mb` (default 90, hard max 95, decimal MB). A value above 95, or 0 or less, exits with code 2. A kit that fits is still one `<name>.zip`.
- Split output. A larger kit is written as standalone `<name>_Part_01_of_0N.zip` files. They are ordinary zips, not a multi-volume archive. Each part has relative paths and its own `package_manifest.json` with the file-list slice for that part and a `split` block. A file larger than the cap is stored as `.uawt-chunk-NNN-of-NNN` pieces with per-piece SHA-256. Restore and inspect find the sibling parts, verify every part, re-join pieces, and check the joined file against its original SHA-256. A missing part exits with code 2 before anything is written. `--encrypt` encrypts every part.
- Name-only secret gate. The file is never opened. It covers `*secret*`, `*token*`, `*credential*`, `*cookie*`, `*key*.json`, `gateway.json`, `mcp_config.json`, `.env`, `*.pem`, `*.key`, and `credentials/` / `.credentials/` folders. Documents and source files (`.md`, `.py`, ...) are exempt, so `Secretariat.md` is still packed. Tokenizer and lockfile names, plus `keybindings.json`, are kept.
- Virtualenv locks. `*venv*`, `.venv`, `pyvenv.cfg` folders and `site-packages` are not packed. Their requirements are frozen offline with the environment's own Python, using `uv pip freeze --offline` or `python -m pip freeze`. The output goes to `Level_2_System_Settings/python-envs/requirements-*.txt`, with `pip-user-packages.txt` from `pip list --user`. `--skip-env-lock` turns this off. Failures are recorded in `env_locks` and do not stop the pack.
- Duplicate skill and rules detection for `SKILL.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules` and `.clinerules`. Copies are listed with "same content" or "same name, different content", and the user is asked to pick the canonical copy. Everything is still packed. The list is saved as `duplicates` in the manifest.
- Long-path check. If the longest archive path is over 200 characters, the manifest records `long_paths` and the CLI advises extracting to `C:\GB\` or enabling `LongPathsEnabled`.
- No-overwrite output naming: `_v2`, `_v3`, ...
- `--include-bulky`, which is the same as `INCLUDE_BULKY_DIRS=1`. Without it, model weights of 5 MB or more (`.onnx`, `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.gguf`, `.bin`) go to Level 5 and are not packed.
- New modules `toolkit_parts.py` and `toolkit_preflight.py`, and the new test file `tests/test_hardening_v230.py`.

### Changed (behaviour that existing users can notice)

- Kits above 90 MB are now split into parts instead of one large zip.
- Files matched by the broader name rules are excluded unless `--include-secrets` is set. This includes nested `*secret*.json` files, `*.pem` and `*.key`, and `credentials/` folders. `tests/test_grok_profile.py` was updated for one nested `custom-secrets.json` that v2.2.0 packed.
- Antigravity profile: `*venv*` folders, `pyvenv.cfg` folders and `site-packages` are no longer packed. Requirement locks are written instead.
- Model weights of 5 MB or more go to Level 5 unless `--include-bulky` is set.
- `--encrypt` refuses to replace an existing `.zip.enc`. Previously, an existing `.zip.enc` with the same name could be overwritten.
- Archive member names are always written with `/` separators.
- `manifest_version` is `v2.3.0` for both profiles. The Antigravity manifest said `v2.1.0` before.

### Not changed

- The Grok Bot default paths, the restore gates, `.incoming` handling, the HMAC and encryption format, and the MCP JSON redaction.
- Restore does not install packages. Lock files stay in the kit, or in `.grok-restore-incoming/` for the Grok profile.

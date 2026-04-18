# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] — 2026-04-12

### Fixed
- Upload no longer silently fails on large files — incremental base64 decode and `gc.collect()` prevent `MemoryError` on the Pico
- Explicit `MemoryError` detection with actionable error messages

### Changed
- `upload_file()` writes decoded chunks incrementally instead of accumulating in RAM

## [0.2.0] — 2026-04-06

### Added
- `tree` — show file tree with SHA256 hashes
- `edit` — download, edit in `$EDITOR`, re-upload if changed
- `cp` — copy files to/from the Pico (`:` prefix = Pico path)
- `sync` — upload only changed files (by size comparison, `--dry-run` support)
- `backup` — download files from Pico to local directory (`--dir`, `--files`, `--list`)
- `watch` — attach to serial output without resetting (`--reset` option)
- `repl` — interactive MicroPython REPL (Ctrl+] to exit)
- `rtc` — read or set the device real-time clock
- `mip` — install MicroPython packages via `mip`
- `df` — show flash and RAM usage summary
- `ports` — list available serial ports (no Pico connection needed)
- Global `--sync-rtc` flag / `PICO_SYNC_RTC` env var for automatic RTC sync
- Graceful Ctrl+C handling for all commands (streaming, multi-step, and single-shot)
- Module cache auto-clear after uploading `.py` files
- Man page (`pico_ctl.1`)
- Debian and RPM packaging
- GitHub Actions workflow for release builds

### Changed
- Unified all functionality into a single `pico_ctl.py` CLI
- `upload` now supports `--dir`, `--src`, `--dry-run`, and positional pairs
- `run` supports `--detach` to launch a script and disconnect

## [0.1.0] — 2026-03-20

### Added
- Initial release: `info`, `ls`, `reset`, `hard`, `bootsel`, `rm`, `exec`, `run`, `upload`, `monitor`
- `PicoSerial` library with COM auto-detection, paste-mode execution, base64 file transfer
- WSL2 USB passthrough documentation

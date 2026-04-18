# Project Guidelines

## Overview

All-in-one CLI tool for managing a **Raspberry Pi Pico** running MicroPython over USB serial. Built on a shared `PicoSerial` library that handles COM port auto-detection, REPL paste-mode execution, base64-chunked file transfer, and remote filesystem operations.

Everything is in a single `pico_ctl.py` with subcommands: info, ls, tree, cat, edit, cp, df, ports, exec, mip, run, upload, sync, backup, rm, reset, hard, bootsel, rtc, monitor, watch, repl.

## Target Platform

- **Host**: Python 3.8+ (Windows, Linux, macOS)
- **Dependency**: pyserial (`pip install pyserial`)
- **Target device**: Any Raspberry Pi Pico with MicroPython (USB VID `0x2E8A` — Pico, Pico W, Pico 2, Pico 2 W)

## Architecture

```
pico_serial.py   → Shared library: PicoSerial class (serial, REPL, file transfer)
pico_ctl.py      → All-in-one CLI: info, ls, cat, df, reset, hard, bootsel, rm, exec, run, upload, sync, backup, monitor, watch, repl
setup.py         → Package setup with console_scripts entry point (pico_ctl command)
pico-ctl.spec    → RPM spec file
debian/          → Debian/Ubuntu packaging (control, rules, changelog, copyright)
```

- `pico_ctl.py` imports `PicoSerial` from `pico_serial.py`
- COM port auto-detection finds the first port with USB VID `0x2E8A`
- Every subcommand inherits the global `--port` option to override auto-detection
- Running without a subcommand defaults to `info`
- All commands handle KeyboardInterrupt (Ctrl+C): streaming commands detach gracefully, multi-step commands report partial progress, connection phase exits cleanly

## Code Style

- Standard Python 3.8+ (CPython, not MicroPython)
- All subcommands are `cmd_*` functions that receive `(pico, args)`
- All public functions and classes must have docstrings
- `PicoSerial` supports context manager (`with PicoSerial() as pico:`)

## Conventions

### Serial Communication
- REPL paste mode: send `\x05` to enter, code bytes, `\x04` to execute
- Ctrl+C (`\x03\x03`) to interrupt running programs before any operation
- File upload uses base64 encoding with `batch_size=8`, `chunk_size=256` to avoid REPL buffer overflow
- File download uses base64 with `<<<START>>>`/`<<<END>>>` markers
- Monitor watches for configurable success markers (default: `"Display updated"`, `"No change"`, `"Free mem"`)

### Known Quirks
- Files with many non-ASCII bytes can cause timing issues during upload — the batch_size=8 default handles this
- After hard reset or bootsel, the serial port disconnects — user must reconnect
- `Traceback` in response text indicates an error on the Pico side
- `upload --dry-run` does not open a serial connection

### Upload Strategy
- Prefer uploading individual changed files over entire directories (`--dir`) to reduce transfer time
- Large files (>10 KB) take noticeably longer over serial; only re-upload what changed
- Upload automatically clears MicroPython's `sys.modules` cache for any uploaded `.py` files, so re-importing picks up the new code without a manual reset

## Packaging

- `setup.py` defines a `console_scripts` entry point: `pico_ctl = pico_ctl:main`
- When installed via pip, dpkg, or rpm, the `pico_ctl` command is available system-wide
- Version is defined in `setup.py` and must match `debian/changelog` and `pico-ctl.spec`
- GitHub Actions workflow `.github/workflows/package.yml` builds .deb and .rpm on tag push (`v*`)
- The workflow uses Ubuntu for .deb and Fedora container for .rpm, then creates a GitHub Release with both artifacts

## Subcommand Notes

Subcommands are grouped by category in the CLI help and argparse registration:

1. **Inspect**: info, ls, tree, cat, edit, cp, df, ports
2. **Execute**: exec, mip, run, repl
3. **File management**: upload, sync, backup, rm
4. **Device control**: reset, hard, bootsel, rtc
5. **Monitor**: monitor, watch

Key behaviors:
- The `run` subcommand supports `--detach` to launch a script and disconnect immediately
- The `rm` subcommand supports `-r` for recursive directory deletion
- The `backup` subcommand supports `--dir` to download a specific subtree
- The `info` subcommand shows board ID, CPU, RAM, and flash usage
- The `tree` subcommand shows file tree with SHA256 hashes
- The `cat` subcommand prints file contents via base64 download
- The `edit` subcommand downloads a file, opens `$EDITOR`, and re-uploads if changed
- The `cp` subcommand copies files to/from the Pico (`:` prefix = Pico path)
- The `df` subcommand shows flash/RAM usage summary
- The `ports` subcommand lists available serial ports (no Pico connection needed)
- The `mip` subcommand installs MicroPython packages via `mip` on the Pico (requires WiFi)
- The `rtc` subcommand reads or sets the Pico's real-time clock
- Global `--sync-rtc` flag (or `PICO_SYNC_RTC=1` env var) auto-syncs RTC to host time on connect
- The `sync` subcommand compares by file size and uploads only changed files
- The `watch` subcommand attaches to serial without resetting; `--reset` to reset first
- The `repl` subcommand provides an interactive REPL; Ctrl+] to exit
- Streaming commands (`run`, `monitor`, `watch`) catch KeyboardInterrupt for graceful detach
- Multi-step commands (`upload`, `sync`, `backup`, `rm -r`) catch KeyboardInterrupt and report partial progress
- Running with no subcommand defaults to `info`

## Testing

No automated test suite. Test against a physical Pico:

```bash
python3 pico_ctl.py info
python3 pico_ctl.py mip github:jonbrefe/pico-paper-lib
python3 pico_ctl.py upload --dir ../pico-paper-lib /pico_paper_lib
python3 pico_ctl.py run test_all.py
python3 pico_ctl.py monitor --timeout 30
```

## License

MIT — Jonathan Brenes

# pico-ctl

An all-in-one command-line tool for managing a **Raspberry Pi Pico** running MicroPython over USB serial.

> Upload files, backup, monitor, reset, and inspect — all from a single `pico_ctl.py` command.

## Requirements

- **Python 3.8+** on the host machine (Windows, Linux, macOS)
- **pyserial** (`pip install pyserial`)
- Raspberry Pi Pico flashed with **MicroPython** (tested with v1.28.0)
- USB cable connecting the Pico to the host

Works with all Raspberry Pi Pico variants: Pico, Pico W, Pico 2, Pico 2 W (auto-detected via USB vendor ID `0x2E8A`).

## Installation

### From GitHub Release (recommended)

Download and install the latest release:

```bash
# Debian/Ubuntu
curl -sLO "$(curl -s https://api.github.com/repos/jonbrefe/pico-ctl/releases/latest \
  | grep browser_download_url | grep '\.deb"' | cut -d '"' -f 4)"
sudo dpkg -i pico-ctl_*.deb

# RPM-based (Fedora, RHEL, openSUSE)
curl -sLO "$(curl -s https://api.github.com/repos/jonbrefe/pico-ctl/releases/latest \
  | grep browser_download_url | grep '\.rpm"' | cut -d '"' -f 4)"
sudo rpm -i pico-ctl-*.rpm
```

Or with the **GitHub CLI**:

```bash
# Debian/Ubuntu
gh release download --repo jonbrefe/pico-ctl --pattern '*.deb'
sudo dpkg -i pico-ctl_*.deb

# RPM-based
gh release download --repo jonbrefe/pico-ctl --pattern '*.rpm'
sudo rpm -i pico-ctl-*.rpm
```

After installing, the `pico_ctl` command is available system-wide.

### From source

```bash
cd pico-ctl
pip install -r requirements.txt
```

Run directly with `python3 pico_ctl.py`.

## Quick Start

```bash
# No subcommand defaults to info
pico_ctl

# Upload your project files
pico_ctl upload --dir ../pico-paper-lib /pico_paper_lib

# Soft-reset and watch boot output
pico_ctl monitor

# Run a script and stream output
pico_ctl run test_all.py

# Run a script and detach (Pico keeps running)
pico_ctl run main.py --detach

# Backup everything before making changes
pico_ctl backup
```

> If installed from source, use `python3 pico_ctl.py` instead of `pico_ctl`.
> Running without a subcommand defaults to `info`.

## Commands

| | Command | Description |
|---|---------|-------------|
| **Inspect** | `info` | Show firmware, board ID, CPU, RAM, flash usage, and file listing |
| | `ls [path]` | List files (recursive by default, `--flat` for single dir) |
| | `cat <path>` | Print file contents from the Pico |
| | `df` | Show flash and RAM usage summary |
| **Execute** | `exec <code>` | Run arbitrary MicroPython on the Pico |
| | `run <file>` | Run a `.py` file and stream output (`--detach` to background) |
| | `mip <package>` | Install a MicroPython package via `mip` (requires WiFi on Pico) |
| | `repl` | Interactive MicroPython REPL session (Ctrl+] to exit) |
| **File mgmt** | `upload` | Upload files/directories to the Pico (auto-clears module cache) |
| | `sync` | Upload only changed files (by size comparison) |
| | `backup` | Download files from the Pico to local backup |
| | `rm <path>` | Delete a file or directory (`-r` for recursive) |
| **Device** | `reset` | Soft-reset (restarts `main.py`) |
| | `hard` | Hard reset (`machine.reset()`) |
| | `bootsel` | Enter BOOTSEL mode for `.uf2` firmware flashing |
| **Monitor** | `monitor` | Soft-reset and stream boot output |
| | `watch` | Attach to serial output without resetting |

### Inspect: info / ls / cat / df

```bash
pico_ctl info                         # firmware, board ID, CPU, RAM, flash, files
pico_ctl ls /pico_paper_lib
pico_ctl ls / --flat
pico_ctl cat /config.py               # print file contents
pico_ctl df                           # flash and RAM usage
```

### Execute: exec / run / mip / repl

```bash
pico_ctl exec "import gc; gc.collect(); print(gc.mem_free())"
pico_ctl run test_all.py
pico_ctl run main.py --timeout 300
pico_ctl run main.py --detach          # launch and disconnect (Pico keeps running)
pico_ctl mip github:jonbrefe/pico-paper-lib   # install a package via mip
pico_ctl mip github:user/repo --target /lib   # specify install directory
pico_ctl repl                          # interactive REPL (Ctrl+] to exit)
```

### File management: rm

```bash
pico_ctl rm /old_file.py               # delete a single file
pico_ctl rm -r /old_package            # recursively delete a directory
```

### Device control: reset / hard / bootsel

```bash
pico_ctl reset
pico_ctl hard
pico_ctl bootsel
```

### upload

```bash
# Upload a single file (local_path pico_path)
pico_ctl upload main.py /main.py

# Upload multiple files
pico_ctl upload config.py /config.py main.py /main.py

# Upload an entire directory tree
pico_ctl upload --dir ../pico-paper-lib /pico_paper_lib

# Upload all .py files from a source directory to Pico root
pico_ctl upload --src src/

# Preview what would be uploaded
pico_ctl upload --src src/ --dry-run
```

**Upload modes:**
- **Positional pairs**: `LOCAL_PATH PICO_PATH [LOCAL_PATH PICO_PATH ...]`
- **`--dir LOCAL_DIR PICO_PREFIX`**: Upload a directory tree, preserving structure
- **`--src DIR`**: Upload all `.py` files to Pico `/`
- **`--dry-run`**: Show what would be uploaded without transferring

After uploading `.py` files, the module cache on the Pico is automatically cleared so the next `import` loads the new code. Already-running code is not affected until a reset.

### sync

```bash
# Compare local directory with Pico and upload only changed files
pico_ctl sync ../pico-paper-lib /pico_paper_lib

# Preview what would be uploaded
pico_ctl sync ../pico-paper-lib /pico_paper_lib --dry-run
```

### backup

```bash
# Backup all files to backup/ (default)
pico_ctl backup

# Backup to a specific directory
pico_ctl backup --output my_backup/

# Backup only a specific directory
pico_ctl backup --dir /pico_paper_lib

# Backup only specific files
pico_ctl backup --files /main.py /config.py

# List files without downloading
pico_ctl backup --list
```

### monitor

```bash
# Default: reset, watch for 45 seconds
pico_ctl monitor

# Wait longer
pico_ctl monitor --timeout 60

# Custom success markers
pico_ctl monitor --markers "WiFi connected" "Ready"
```

### watch

```bash
# Attach to serial output (Ctrl+C to detach, Pico keeps running)
pico_ctl watch

# Watch with a timeout
pico_ctl watch --timeout 30

# Reset first, then watch
pico_ctl watch --reset
```

### Graceful Ctrl+C

All commands handle **Ctrl+C** cleanly:
- **Streaming commands** (`run`, `monitor`, `watch`) — detach from serial; the Pico continues running.
- **Multi-step commands** (`upload`, `sync`, `backup`, `rm -r`) — stop and report partial progress (e.g. `3/6 file(s) uploaded`).
- **All other commands** — exit immediately with `--- Interrupted. ---`.
- **During connection** — exit cleanly even if Ctrl+C is pressed while connecting.

## PicoSerial Library

All commands are built on `pico_serial.PicoSerial`. You can use it in your own scripts:

```python
from pico_serial import PicoSerial

with PicoSerial() as pico:
    print(pico.firmware_version())
    pico.upload_file('main.py', '/main.py')
    files = pico.list_files('/')
```

### API

| Method | Description |
|--------|-------------|
| `PicoSerial(port=None)` | Open connection. Auto-detects if port is None. |
| `exec(code, timeout=10)` | Execute code via paste mode. Returns output. |
| `soft_reset()` | Send Ctrl+D to restart main.py. |
| `hard_reset()` | Call `machine.reset()`. |
| `enter_bootsel()` | Enter USB BOOTSEL mode. |
| `monitor_boot(timeout, markers)` | Soft-reset + stream output. Returns `(lines, success)`. |
| `upload_file(local, pico_path)` | Upload via base64 chunks. Returns bytes written. |
| `download_file(pico_path)` | Download a file. Returns `bytes`. |
| `list_files(path, recursive)` | List files. Returns `[(path, size), ...]`. |
| `mkdir(path)` | Create directory and parents. |
| `delete_file(pico_path)` | Delete a file. |
| `firmware_version()` | Return MicroPython version string. |

## Architecture

```
pico-ctl/
├── pico_ctl.py           # All-in-one CLI (info, ls, upload, backup, monitor, etc.)
├── pico_serial.py        # Shared library — COM auto-detect, REPL, file transfer
├── pico_ctl.1            # Man page (groff)
├── requirements.txt      # pyserial>=3.5
├── setup.py              # Package setup with console_scripts entry point
├── pico-ctl.spec         # RPM spec file
├── debian/               # Debian packaging files
│   ├── control
│   ├── rules
│   ├── changelog
│   └── copyright
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/
│       └── package.yml   # Build .deb and .rpm on release
└── README.md
```

## WSL2 Setup (USB Passthrough)

By default WSL2 cannot see USB devices. Use Microsoft's **usbipd-win** to forward the Pico into WSL.

### One-time setup

1. **Install usbipd-win on Windows** (regular PowerShell):

   ```powershell
   winget install usbipd
   ```

2. **Install USB/IP tools inside WSL**:

   ```bash
   sudo apt install linux-tools-virtual hwdata
   ```

3. **Add your user to the `dialout` group**:

   ```bash
   sudo usermod -aG dialout $USER
   ```

   Log out and back in to WSL for this to take effect.

### Each session (after plugging in the Pico)

From an **admin** PowerShell:

```powershell
usbipd list                          # find the Pico (VID 2E8A), note the BUSID
usbipd bind --busid <BUSID>          # first time only — share the device
usbipd attach --wsl --busid <BUSID>  # forward into WSL
```

> **Note:** While attached to WSL, the device disappears from Windows (COM3 goes away).
> To return it: `usbipd detach --busid <BUSID>`, or just unplug and replug.

Then in WSL:

```bash
ls /dev/ttyACM*                      # should show /dev/ttyACM0
pico_ctl info                        # works natively
```

## Troubleshooting

### "No Pico found" error
- Check the USB cable is connected and the Pico is powered on
- Verify the Pico appears in Device Manager (Windows) or `ls /dev/tty*` (Linux/macOS)
- If using WSL2, make sure you've run `usbipd attach` (see above)
- Use `--port /dev/ttyACM0` to override auto-detection

### Upload hangs on large files
- Files with many non-ASCII bytes can cause timing issues
- The uploader uses `batch_size=8` and `chunk_size=256` by default, which handles most files
- If a file is very large (>10KB), consider splitting it

### "Traceback" during boot
- Run `python3 pico_ctl.py monitor` to see the full error
- Common cause: missing module imports or file not uploaded correctly
- Use `python3 pico_ctl.py ls /` to verify files are on the Pico

### BOOTSEL mode: Pico disappears
- This is expected — the Pico disconnects from serial and appears as a USB drive
- Copy a `.uf2` firmware file to the drive to flash it

## Copilot Instructions

The `.github/copilot-instructions.md` file provides project-specific context to GitHub Copilot. It describes the `PicoSerial` architecture, serial communication conventions (paste mode, base64 chunking, known quirks), and the unified CLI structure. This helps Copilot generate correct host-side Python code that interacts properly with the MicroPython REPL.

## License

MIT — Jonathan Brenes

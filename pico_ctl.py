#!/usr/bin/env python3
"""
pico_ctl — All-in-one CLI for managing a Raspberry Pi Pico running MicroPython.

Subcommands (grouped by category):

  Inspect:
    info        Show firmware, board ID, CPU, RAM, flash, and file listing
    ls          List files on the Pico
    tree        Show file tree with SHA256 hashes
    cat         Print file contents from the Pico
    df          Show flash and RAM usage summary
    ports       List available serial ports

  Execute:
    exec        Execute arbitrary Python code on the Pico
    run         Run a .py file on the Pico (--detach to background)
    repl        Interactive MicroPython REPL session

  File management:
    upload      Upload files and directories to the Pico
    sync        Upload only changed files (by size comparison)
    edit        Edit a file on the Pico using $EDITOR
    cp          Copy files to/from the Pico (: prefix = Pico)
    backup      Download files from the Pico to local backup
    rm          Delete a file or directory from the Pico

  Device control:
    reset       Soft-reset (restart main.py)
    hard        Hard reset (machine.reset)
    bootsel     Enter BOOTSEL mode for firmware flashing
    rtc         Get or set the device real-time clock

  Monitor:
    monitor     Soft-reset and stream boot output
    watch       Attach to serial output without resetting

Examples:
    python3 pico_ctl.py info
    python3 pico_ctl.py ls /
    python3 pico_ctl.py ls /pico_paper_lib
    python3 pico_ctl.py reset
    python3 pico_ctl.py bootsel
    python3 pico_ctl.py rm /old_file.py
    python3 pico_ctl.py exec "print('hello')"
    python3 pico_ctl.py run test_all.py
    python3 pico_ctl.py run main.py --timeout 300
    python3 pico_ctl.py upload main.py /main.py
    python3 pico_ctl.py upload --dir ../pico-paper-lib /pico_paper_lib
    python3 pico_ctl.py backup
    python3 pico_ctl.py backup --output my_backup/
    python3 pico_ctl.py monitor
    python3 pico_ctl.py monitor --timeout 60
"""

import argparse
import os
import sys

from pico_serial import PicoSerial


# ---- info / ls / reset / hard / bootsel / rm / exec / run ----

def cmd_info(pico, args):
    """Show firmware version, board info, filesystem usage, and file listing."""
    ver = pico.firmware_version()
    print(f"Port:     {pico.port_name}")
    print(f"Firmware: {ver}")

    # Board and memory info
    hw = pico.exec(
        "import gc,sys,os,machine\n"
        "gc.collect()\n"
        "s=os.statvfs('/')\n"
        "bs=s[0]; ft=s[2]*bs; ff=s[3]*bs\n"
        "print('UID:'+':'.join('{:02x}'.format(b) for b in machine.unique_id()))\n"
        "print('FREQ:'+str(machine.freq()))\n"
        "print('RAM_FREE:'+str(gc.mem_free()))\n"
        "print('RAM_ALLOC:'+str(gc.mem_alloc()))\n"
        "print('FS_TOTAL:'+str(ft))\n"
        "print('FS_FREE:'+str(ff))\n",
        timeout=10,
    )
    hw_vals = {}
    for line in hw.split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('import') and '>>>' not in line:
            key, _, val = line.partition(':')
            if key in ('UID', 'FREQ', 'RAM_FREE', 'RAM_ALLOC', 'FS_TOTAL', 'FS_FREE'):
                hw_vals[key] = val

    uid = hw_vals.get('UID', '?')
    freq = int(hw_vals.get('FREQ', 0))
    ram_free = int(hw_vals.get('RAM_FREE', 0))
    ram_alloc = int(hw_vals.get('RAM_ALLOC', 0))
    fs_total = int(hw_vals.get('FS_TOTAL', 0))
    fs_free = int(hw_vals.get('FS_FREE', 0))
    fs_used = fs_total - fs_free
    ram_total = ram_free + ram_alloc

    print(f"Board ID: {uid}")
    if freq:
        print(f"CPU:      {freq // 1_000_000} MHz")
    if ram_total:
        print(f"RAM:      {ram_free // 1024} KB free / {ram_total // 1024} KB total")
    if fs_total:
        pct = fs_used * 100 // fs_total
        print(f"Flash:    {fs_used // 1024} KB used / {fs_total // 1024} KB total ({pct}%)")
    print()

    files = pico.list_files('/')
    file_total = 0
    print(f"{'Path':<40} {'Size':>10}")
    print('-' * 52)
    for path, size in files:
        if size == 'dir':
            print(f"{path + '/':<40} {'<dir>':>10}")
        else:
            print(f"{path:<40} {size:>9,}")
            file_total += size
    print('-' * 52)
    print(f"{'Total:':<40} {file_total:>9,}")
    if fs_free:
        print(f"{'Free space:':<40} {fs_free:>9,}")


def cmd_ls(pico, args):
    """List files on the Pico. Recursive by default; --flat for one directory."""
    path = args.path or '/'
    files = pico.list_files(path, recursive=not args.flat)
    for fpath, size in files:
        if size == 'dir':
            print(f"  {fpath}/")
        else:
            print(f"  {fpath}  ({size:,} bytes)")


def cmd_tree(pico, args):
    """Show a tree of all files on the Pico with size and SHA256 hash."""
    path = args.path or '/'
    # Normalize: strip leading ./ and ensure leading /
    path = path.lstrip('.')
    if not path.startswith('/'):
        path = '/' + path

    # Check if path is a file or missing
    files = pico.list_files(path, recursive=True)
    file_paths = [p for p, s in files if s != 'dir' and not p.startswith('OSError')]
    if not file_paths:
        # Maybe it's a single file — try parent directory
        parent = path.rsplit('/', 1)[0] or '/'
        parent_files = pico.list_files(parent, recursive=False)
        match = [(p, s) for p, s in parent_files if p == path and s != 'dir']
        if match:
            fpath, size = match[0]
            code = (
                "import hashlib\n"
                f"h=hashlib.sha256(open('{fpath}','rb').read())\n"
                "print(h.digest().hex())\n"
            )
            resp = pico.exec(code, timeout=15)
            digest = ''
            for line in resp.split('\n'):
                line = line.strip().replace('>>>', '').strip()
                if len(line) == 64 and all(c in '0123456789abcdef' for c in line):
                    digest = line
                    break
            print(f"{fpath}  ({size:,})  {digest}")
            return
        print(f"Path not found on Pico: {path}")
        sys.exit(1)

    # Get SHA256 hashes in one batch
    hashes = {}
    if file_paths:
        code_lines = [
            "import hashlib",
            f"files = {repr(file_paths)}",
            "for f in files:",
            " try:",
            "  h = hashlib.sha256()",
            "  with open(f, 'rb') as fp:",
            "   while True:",
            "    c = fp.read(512)",
            "    if not c: break",
            "    h.update(c)",
            "  print('HASH:' + f + ':' + h.digest().hex())",
            " except:",
            "  print('HASH:' + f + ':ERROR')",
        ]
        resp = pico.exec('\n'.join(code_lines), timeout=30)
        for line in resp.split('\n'):
            line = line.strip()
            if line.startswith('HASH:'):
                parts = line.split(':', 2)
                if len(parts) == 3:
                    hashes[parts[1]] = parts[2]

    # Build tree structure from file paths (infer directories)
    entries = {}  # dir_path -> [(name, is_dir, size, hash)]
    dirs_seen = set()
    for fpath, size in files:
        if size == 'dir':
            continue  # we infer dirs from file paths
        # Register all parent directories
        parts = fpath.strip('/').split('/')
        for depth in range(len(parts) - 1):
            dir_path = '/' + '/'.join(parts[:depth + 1])
            if dir_path not in dirs_seen:
                dirs_seen.add(dir_path)
                parent = '/' + '/'.join(parts[:depth]) if depth > 0 else '/'
                entries.setdefault(parent, []).append((parts[depth], True, 0, ''))
        # Register the file
        if len(parts) > 1:
            parent = '/' + '/'.join(parts[:-1])
        else:
            parent = '/'
        h = hashes.get(fpath, '')
        entries.setdefault(parent, []).append((parts[-1], False, size, h))

    total_files = 0
    total_bytes = 0

    def print_tree(dir_path, prefix=''):
        nonlocal total_files, total_bytes
        items = entries.get(dir_path, [])
        # Sort: directories first, then files, both alphabetical
        items.sort(key=lambda x: (not x[1], x[0]))
        for i, (name, is_dir, size, h) in enumerate(items):
            is_last = i == len(items) - 1
            connector = '└── ' if is_last else '├── '
            if is_dir:
                print(f"{prefix}{connector}{name}/")
                child_prefix = prefix + ('    ' if is_last else '│   ')
                child_path = dir_path.rstrip('/') + '/' + name
                print_tree(child_path, child_prefix)
            else:
                total_files += 1
                total_bytes += size
                print(f"{prefix}{connector}{name}  ({size:,})  {h}")

    root = path.rstrip('/') or '/'
    print('/' if root == '/' else root + '/')
    print_tree(root)
    print(f"\n{total_files} file(s), {total_bytes:,} bytes")


def cmd_reset(pico, args):
    """Send a soft reset (Ctrl+D) to restart main.py on the Pico."""
    print("Sending soft reset (Ctrl+D)...")
    pico.soft_reset()
    print("Done. Use 'pico_ctl.py monitor' to watch boot output.")


def cmd_hard(pico, args):
    """Send a hard reset (machine.reset) for a full hardware reboot."""
    print("Sending hard reset (machine.reset)...")
    pico.hard_reset()
    print("Pico is rebooting. Reconnect after a few seconds.")


def cmd_bootsel(pico, args):
    """Enter BOOTSEL mode — Pico appears as USB mass storage for firmware flashing."""
    print("Entering BOOTSEL mode...")
    print("The Pico will appear as a USB drive.")
    print("Copy a .uf2 firmware file to flash it.")
    pico.enter_bootsel()


def cmd_rtc(pico, args):
    """Get or set the device real-time clock."""
    from datetime import datetime

    if args.set:
        now = datetime.now()
        # RTC.datetime() format: (year, month, day, weekday, hour, minute, second, subsecond)
        # weekday: 0=Monday
        wd = now.weekday()  # 0=Monday in Python
        code = (
            f"from machine import RTC\n"
            f"RTC().datetime(({now.year},{now.month},{now.day},{wd},"
            f"{now.hour},{now.minute},{now.second},0))\n"
            f"print('OK')\n"
        )
        pico.exec(code, timeout=5)
        print(f"RTC set to: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        resp = pico.exec(
            "from machine import RTC\n"
            "t=RTC().datetime()\n"
            "print(f'{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[4]:02d}:{t[5]:02d}:{t[6]:02d}')\n",
            timeout=5,
        )
        # Extract the datetime line
        for line in resp.split('\n'):
            line = line.strip()
            if line and line[0].isdigit() and '-' in line and ':' in line:
                pico_time = line
                break
        else:
            print(f"Could not parse RTC response: {resp}")
            return

        host_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Pico RTC:  {pico_time}")
        print(f"Host time: {host_time}")

        # Calculate drift
        try:
            pico_dt = datetime.strptime(pico_time, '%Y-%m-%d %H:%M:%S')
            host_dt = datetime.strptime(host_time, '%Y-%m-%d %H:%M:%S')
            drift = abs((host_dt - pico_dt).total_seconds())
            if drift > 2:
                print(f"Drift: {drift:.0f}s — use 'pico_ctl rtc --set' to sync")
        except ValueError:
            pass


def cmd_rm(pico, args):
    """Delete a file or directory from the Pico's filesystem."""
    path = args.path
    if args.recursive:
        # List all files under the path, delete deepest first, then directories
        files = pico.list_files(path, recursive=True)
        file_paths = [f for f, sz in files if sz != 'dir']
        if not file_paths:
            print(f"No files found under {path}")
            sys.exit(1)
        # Collect directory paths from file paths
        dir_set = set()
        for f in file_paths:
            parts = f.rsplit('/', 1)
            if len(parts) == 2 and parts[0]:
                dir_set.add(parts[0])
        # Delete files
        deleted = 0
        try:
            for f in file_paths:
                print(f"  rm {f}")
                pico.delete_file(f)
                deleted += 1
            # Remove directories deepest first
            path_clean = path.rstrip('/')
            dirs_sorted = sorted(dir_set, key=lambda d: d.count('/'), reverse=True)
            for d in dirs_sorted:
                print(f"  rmdir {d}")
                pico.exec(f"import os; os.rmdir('{d}')", timeout=5)
            # Remove the target directory itself if not already removed
            if path_clean and path_clean != '/' and path_clean not in dir_set:
                print(f"  rmdir {path_clean}")
                pico.exec(f"import os; os.rmdir('{path_clean}')", timeout=5)
        except KeyboardInterrupt:
            print(f'\n--- Interrupted. {deleted}/{len(file_paths)} file(s) deleted. ---')
            sys.exit(1)
        print(f"Deleted {len(file_paths)} file(s).")
    else:
        print(f"Deleting {path}...")
        try:
            pico.delete_file(path)
            print("Deleted.")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_exec(pico, args):
    """Execute arbitrary MicroPython code on the Pico and print the output."""
    code = args.code
    resp = pico.exec(code, timeout=args.timeout)
    for line in resp.split('\n'):
        line = line.strip()
        if line and '>>>' not in line and not line.startswith(code[:20]):
            print(line)


def cmd_mip(pico, args):
    """Install a MicroPython package on the Pico using mip."""
    pkg = args.package
    target = args.target
    code = 'import mip\nmip.install({!r}'.format(pkg)
    if target:
        code += ', target={!r}'.format(target)
    code += ')'
    print(f"Installing {pkg}...")
    resp = pico.exec(code, timeout=args.timeout)
    for line in resp.split('\n'):
        line = line.strip()
        if line and '>>>' not in line:
            print(line)


def cmd_cat(pico, args):
    """Print the contents of a file on the Pico."""
    data = pico.download_file(args.path)
    sys.stdout.buffer.write(data)
    if data and not data.endswith(b'\n'):
        sys.stdout.buffer.write(b'\n')
    sys.stdout.buffer.flush()


def cmd_cp(pico, args):
    """Copy files to/from the Pico. Paths prefixed with : are on the Pico."""
    src = args.src
    dst = args.dst
    src_remote = src.startswith(':')
    dst_remote = dst.startswith(':')

    if src_remote:
        src = src[1:]  # strip :
    if dst_remote:
        dst = dst[1:]  # strip :

    if src_remote and dst_remote:
        # Pico-to-Pico copy
        data = pico.download_file(src)
        pico._setup_upload_helper()
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            written = pico.upload_file(tmp_path, dst)
        finally:
            os.unlink(tmp_path)
        print(f":{src} -> :{dst} ({written:,} bytes)")

    elif src_remote and not dst_remote:
        # Pico -> local
        if os.path.isdir(dst):
            dst = os.path.join(dst, src.rsplit('/', 1)[-1])
        data = pico.download_file(src)
        os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(data)
        print(f":{src} -> {dst} ({len(data):,} bytes)")

    elif not src_remote and dst_remote:
        # Local -> Pico
        if not os.path.isfile(src):
            print(f"Local file not found: {src}")
            sys.exit(1)
        sz = os.path.getsize(src)
        pico._setup_upload_helper()
        written = pico.upload_file(src, dst)
        print(f"{src} -> :{dst} ({written:,} bytes)")
        # Clear module cache
        if dst.endswith('.py'):
            mod = dst.lstrip('/').replace('/', '.').removesuffix('.py')
            mods = [mod]
            if '.' in mod:
                mods.append(mod.rsplit('.', 1)[0])
            pico.exec(
                f"import sys\nfor m in {repr(mods)}:\n sys.modules.pop(m, None)\n",
                timeout=5,
            )

    else:
        print("At least one path must start with : (Pico). Use : prefix for Pico paths.")
        print("  cp local.py :/main.py     local -> Pico")
        print("  cp :/main.py .            Pico -> local")
        print("  cp :/a.py :/b.py          Pico -> Pico")
        sys.exit(1)


def cmd_edit(pico, args):
    """Download a file from the Pico, open in $EDITOR, upload if changed."""
    import subprocess
    import tempfile

    pico_path = args.path
    filename = pico_path.rsplit('/', 1)[-1] or 'untitled'

    # Download current contents
    try:
        data = pico.download_file(pico_path)
    except Exception:
        data = b''
        print(f"New file: {pico_path}")

    # Write to temp file preserving extension
    suffix = '.' + filename.rsplit('.', 1)[-1] if '.' in filename else ''
    with tempfile.NamedTemporaryFile(suffix=suffix, prefix='pico_edit_',
                                     delete=False, mode='wb') as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    # Determine editor
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if not editor:
        editor = 'notepad' if sys.platform == 'win32' else 'nano'

    print(f"Opening {pico_path} in {editor}...")
    try:
        result = subprocess.run([editor, tmp_path])
        if result.returncode != 0:
            print(f"Editor exited with code {result.returncode}. Not uploading.")
            os.unlink(tmp_path)
            return
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Set $EDITOR or $VISUAL.")
        os.unlink(tmp_path)
        sys.exit(1)

    # Read back and compare
    with open(tmp_path, 'rb') as f:
        new_data = f.read()
    os.unlink(tmp_path)

    if new_data == data:
        print("No changes.")
        return

    # Write new content to temp file for upload
    with tempfile.NamedTemporaryFile(suffix=suffix, prefix='pico_upload_',
                                     delete=False, mode='wb') as up:
        up.write(new_data)
        upload_path = up.name

    print(f"Uploading {pico_path} ({len(new_data):,} bytes)...", end='', flush=True)
    pico._setup_upload_helper()
    written = pico.upload_file(upload_path, pico_path)
    os.unlink(upload_path)
    print(f" OK ({written:,})")

    # Clear module cache if it's a .py file
    if pico_path.endswith('.py'):
        mod = pico_path.lstrip('/').replace('/', '.').removesuffix('.py')
        mods = [mod]
        if '.' in mod:
            mods.append(mod.rsplit('.', 1)[0])
        names_list = repr(mods)
        pico.exec(
            f"import sys\nfor m in {names_list}:\n sys.modules.pop(m, None)\n",
            timeout=5,
        )
        print(f"Module cache cleared: {', '.join(mods)}")

    print("Done.")


def cmd_ports():
    """List all available serial ports."""
    ports = PicoSerial.list_ports()
    if not ports:
        print("No serial ports found.")
        return
    print(f"{'Device':<20} {'VID:PID':<12} {'Serial':<14} {'Description'}")
    print('-' * 75)
    for p in ports:
        vid_pid = f"{p['vid']:04X}:{p['pid']:04X}" if p['vid'] else ''
        serial_num = p['serial_number'][:12]
        pico_mark = ' (Pico)' if p['is_pico'] else ''
        print(f"{p['device']:<20} {vid_pid:<12} {serial_num:<14} {p['description'][:28]}{pico_mark}")
    pico_count = sum(1 for p in ports if p['is_pico'])
    print()
    if pico_count == 0:
        print("No Pico detected. Check USB connection.")
    elif pico_count == 1:
        pico_dev = next(p['device'] for p in ports if p['is_pico'])
        print(f"Pico found: {pico_dev}")
    else:
        pico_devs = [p['device'] for p in ports if p['is_pico']]
        print(f"{pico_count} Pico devices found: {', '.join(pico_devs)}")
        print("Use --port <device> to select one.")


def cmd_df(pico, args):
    """Show flash and RAM usage summary."""
    hw = pico.exec(
        "import gc,os\n"
        "gc.collect()\n"
        "s=os.statvfs('/')\n"
        "bs=s[0]; ft=s[2]*bs; ff=s[3]*bs\n"
        "print('FS_TOTAL:'+str(ft))\n"
        "print('FS_FREE:'+str(ff))\n"
        "print('RAM_FREE:'+str(gc.mem_free()))\n"
        "print('RAM_ALLOC:'+str(gc.mem_alloc()))\n",
        timeout=10,
    )
    vals = {}
    for line in hw.split('\n'):
        line = line.strip()
        if ':' in line and '>>>' not in line:
            key, _, val = line.partition(':')
            if key in ('FS_TOTAL', 'FS_FREE', 'RAM_FREE', 'RAM_ALLOC'):
                vals[key] = int(val)
    fs_total = vals.get('FS_TOTAL', 0)
    fs_free = vals.get('FS_FREE', 0)
    fs_used = fs_total - fs_free
    ram_free = vals.get('RAM_FREE', 0)
    ram_alloc = vals.get('RAM_ALLOC', 0)
    ram_total = ram_free + ram_alloc

    print(f"{'':15} {'Used':>10} {'Free':>10} {'Total':>10} {'Use%':>6}")
    print('-' * 53)
    if fs_total:
        pct = fs_used * 100 // fs_total
        print(f"{'Flash':15} {fs_used // 1024:>8} KB {fs_free // 1024:>8} KB {fs_total // 1024:>8} KB {pct:>5}%")
    if ram_total:
        pct = ram_alloc * 100 // ram_total
        print(f"{'RAM':15} {ram_alloc // 1024:>8} KB {ram_free // 1024:>8} KB {ram_total // 1024:>8} KB {pct:>5}%")


def cmd_run(pico, args):
    """Run a .py file on the Pico and stream output in real time."""
    import time
    filename = args.file
    timeout = args.timeout

    modname = filename.replace('.py', '').strip('/')
    pico.exec(
        f'import sys\ntry:\n del sys.modules["{modname}"]\nexcept:\n pass\n',
        timeout=5,
    )

    code = f"exec(open('{filename}').read())\n"
    pico._port.reset_input_buffer()
    pico._port.write(b'\x05')
    time.sleep(0.3)
    pico._port.read(pico._port.in_waiting)
    pico._port.write(code.encode())
    time.sleep(0.2)
    pico._port.write(b'\x04')

    if args.detach:
        # Read briefly to check for immediate errors, then disconnect
        time.sleep(1)
        if pico._port.in_waiting:
            data = pico._port.read(pico._port.in_waiting)
            text = data.decode('utf-8', errors='replace')
            if 'Traceback' in text:
                print(text)
                print('--- Script error ---')
                sys.exit(1)
        print(f'Script {filename} launched. Pico continues running.')
        return

    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pico._port.in_waiting:
                data = pico._port.read(pico._port.in_waiting)
                text = data.decode('utf-8', errors='replace')
                print(text, end='', flush=True)
                if 'ALL TESTS COMPLETE' in text:
                    time.sleep(2)
                    if pico._port.in_waiting:
                        print(pico._port.read(pico._port.in_waiting).decode(
                            'utf-8', errors='replace'), end='')
                    break
                if 'Traceback' in text:
                    time.sleep(1)
                    if pico._port.in_waiting:
                        print(pico._port.read(pico._port.in_waiting).decode(
                            'utf-8', errors='replace'), end='')
                    print('\n--- Script error ---')
                    sys.exit(1)
            else:
                time.sleep(0.3)
        else:
            print(f'\n--- Timeout after {timeout}s ---')
    except KeyboardInterrupt:
        print('\n--- Detached (Ctrl+C). Pico continues running. ---')


# ---- upload ----

def _collect_dir_files(local_dir, pico_prefix):
    """Recursively collect (local_path, pico_path) pairs from a directory."""
    pairs = []
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'examples')]
        for f in sorted(files):
            if f.endswith('.py'):
                local = os.path.join(root, f)
                rel = os.path.relpath(local, local_dir).replace('\\', '/')
                pico = pico_prefix.rstrip('/') + '/' + rel
                pairs.append((local, pico))
    return pairs


def _collect_src_files(src_dir):
    """Collect all .py files from src/ maintaining structure."""
    pairs = []
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'examples')]
        for f in sorted(files):
            if f.endswith('.py'):
                local = os.path.join(root, f)
                rel = os.path.relpath(local, src_dir).replace('\\', '/')
                pico = '/' + rel
                pairs.append((local, pico))
    return pairs


def cmd_upload(pico, args):
    """Upload files and directories to the Pico."""
    pairs = []

    if args.src:
        pairs.extend(_collect_src_files(args.src))
    if args.dir:
        pairs.extend(_collect_dir_files(args.dir[0], args.dir[1]))
    if args.files:
        if len(args.files) % 2 != 0:
            print('Error: file arguments must be pairs: LOCAL PICO LOCAL PICO ...')
            sys.exit(1)
        for i in range(0, len(args.files), 2):
            pairs.append((args.files[i], args.files[i + 1]))

    if not pairs:
        print('Error: no files specified. Use --src, --dir, or positional args.')
        sys.exit(1)

    total_bytes = 0
    print(f"{'Local Path':<50} {'Pico Path':<35} {'Size':>8}")
    print('-' * 95)
    for local, pico_path in pairs:
        sz = os.path.getsize(local)
        total_bytes += sz
        print(f"{local:<50} {pico_path:<35} {sz:>7,}")
    print('-' * 95)
    print(f"{'Total:':<86}{total_bytes:>7,}")

    if args.dry_run:
        print('\n(dry run — nothing uploaded)')
        return

    pico._setup_upload_helper()

    uploaded = 0
    try:
        for local, pico_path in pairs:
            sz = os.path.getsize(local)
            print(f"\n  {pico_path} ({sz:,} bytes)...", end='', flush=True)
            try:
                written = pico.upload_file(local, pico_path)
                print(f" OK ({written:,})")
                uploaded += 1
            except RuntimeError as e:
                print(f" FAILED: {e}")
                sys.exit(1)
    except KeyboardInterrupt:
        print(f'\n--- Interrupted. {uploaded}/{len(pairs)} file(s) uploaded. ---')
        sys.exit(1)

    # Clear cached modules for any uploaded .py files so the next import
    # picks up the new code.  This only removes entries from sys.modules —
    # it does NOT affect any code that is already running.  If main.py or
    # another script imported these modules before the upload, the running
    # code keeps using the old in-memory version until the Pico is reset.
    py_pico_paths = [p for _, p in pairs if p.endswith('.py')]
    if py_pico_paths:
        mod_names = set()
        for p in py_pico_paths:
            # /pico_paper_lib/fonts.py → pico_paper_lib.fonts
            mod = p.lstrip('/').replace('/', '.').removesuffix('.py')
            mod_names.add(mod)
            # Also add parent package: pico_paper_lib.fonts → pico_paper_lib
            if '.' in mod:
                mod_names.add(mod.rsplit('.', 1)[0])
        names_list = repr(sorted(mod_names))
        print(f"\nClearing module cache: {', '.join(sorted(mod_names))}")
        pico.exec(
            f"import sys\nfor m in {names_list}:\n sys.modules.pop(m, None)\n",
            timeout=5,
        )
        print("  Cached modules removed. Next import will load the new code.")
        print("  Note: already-running code is not affected until a reset.")

    print(f"\nDone! {len(pairs)} file(s) uploaded ({total_bytes:,} bytes).")


# ---- sync ----

def cmd_sync(pico, args):
    """Upload only files that differ (by SHA256 hash) between local and Pico."""
    import hashlib as _hashlib
    local_dir = args.local_dir
    pico_prefix = args.pico_prefix.rstrip('/')

    # Collect local files and compute SHA256
    local_files = {}
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'examples')]
        for f in sorted(files):
            if f.endswith('.py'):
                local = os.path.join(root, f)
                rel = os.path.relpath(local, local_dir).replace('\\', '/')
                pico_path = pico_prefix + '/' + rel
                with open(local, 'rb') as fh:
                    local_hash = _hashlib.sha256(fh.read()).hexdigest()
                local_files[pico_path] = (local, os.path.getsize(local), local_hash)

    # Get SHA256 hashes from Pico in a single batch
    paths_list = [p for p in sorted(local_files.keys())]
    pico_hashes = {}
    if paths_list:
        # Build a MicroPython script that hashes all files at once
        code_lines = [
            "import hashlib",
            f"files = {repr(paths_list)}",
            "for f in files:",
            " try:",
            "  h = hashlib.sha256()",
            "  with open(f, 'rb') as fp:",
            "   while True:",
            "    c = fp.read(512)",
            "    if not c: break",
            "    h.update(c)",
            "  print('HASH:' + f + ':' + h.digest().hex())",
            " except:",
            "  print('HASH:' + f + ':MISSING')",
        ]
        resp = pico.exec('\n'.join(code_lines), timeout=30)
        for line in resp.split('\n'):
            line = line.strip()
            if line.startswith('HASH:'):
                parts = line.split(':', 2)
                if len(parts) == 3:
                    _, path, digest = parts
                    pico_hashes[path] = digest

    # Compare
    to_upload = []
    for pico_path in sorted(local_files.keys()):
        local, local_sz, local_hash = local_files[pico_path]
        pico_hash = pico_hashes.get(pico_path)
        if pico_hash == local_hash:
            print(f"  {pico_path:<45} OK ({local_sz:,})")
        elif pico_hash == 'MISSING' or pico_hash is None:
            print(f"  {pico_path:<45} NEW")
            to_upload.append((local, pico_path))
        else:
            print(f"  {pico_path:<45} CHANGED (hash differs)")
            to_upload.append((local, pico_path))

    if not to_upload:
        print('\nAll files up to date.')
        return

    if args.dry_run:
        print(f'\n{len(to_upload)} file(s) would be uploaded (dry run).')
        return

    print(f'\nUploading {len(to_upload)} changed file(s)...')
    pico._setup_upload_helper()

    uploaded = 0
    total_bytes = 0
    try:
        for local, pico_path in to_upload:
            sz = os.path.getsize(local)
            total_bytes += sz
            print(f"  {pico_path} ({sz:,} bytes)...", end='', flush=True)
            try:
                written = pico.upload_file(local, pico_path)
                print(f" OK ({written:,})")
                uploaded += 1
            except RuntimeError as e:
                print(f" FAILED: {e}")
                sys.exit(1)
    except KeyboardInterrupt:
        print(f'\n--- Interrupted. {uploaded}/{len(to_upload)} file(s) synced. ---')
        sys.exit(1)

    # Clear cached modules
    py_pico_paths = [p for _, p in to_upload if p.endswith('.py')]
    if py_pico_paths:
        mod_names = set()
        for p in py_pico_paths:
            mod = p.lstrip('/').replace('/', '.').removesuffix('.py')
            mod_names.add(mod)
            if '.' in mod:
                mod_names.add(mod.rsplit('.', 1)[0])
        names_list = repr(sorted(mod_names))
        print(f"\nClearing module cache: {', '.join(sorted(mod_names))}")
        pico.exec(
            f"import sys\nfor m in {names_list}:\n sys.modules.pop(m, None)\n",
            timeout=5,
        )

    print(f"\nDone! {len(to_upload)} file(s) synced ({total_bytes:,} bytes).")


# ---- watch ----

def cmd_watch(pico, args):
    """Attach to serial output without resetting. Ctrl+C to detach."""
    import time
    timeout = args.timeout
    if args.reset:
        print("Sending soft reset...\n")
        pico.soft_reset()

    print(f"Watching serial output (Ctrl+C to detach)...\n")
    try:
        deadline = time.time() + timeout if timeout else None
        while True:
            if deadline and time.time() > deadline:
                print(f'\n--- Timeout after {timeout}s ---')
                break
            if pico._port.in_waiting:
                data = pico._port.read(pico._port.in_waiting)
                print(data.decode('utf-8', errors='replace'), end='', flush=True)
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('\n--- Detached (Ctrl+C). Pico continues running. ---')


# ---- repl ----

def cmd_repl(pico, args):
    """Start an interactive MicroPython REPL session. Ctrl+] to exit."""
    import time
    import select

    # On Windows, select doesn't work on stdin — use msvcrt if available
    try:
        import msvcrt
        _windows = True
    except ImportError:
        import tty
        import termios
        _windows = False

    # Exit paste mode, get a clean REPL prompt
    pico._port.write(b'\x03\x03')
    time.sleep(0.5)
    if pico._port.in_waiting:
        print(pico._port.read(pico._port.in_waiting).decode('utf-8', errors='replace'), end='')

    print("Interactive REPL (Ctrl+] to exit)\n")

    if not _windows:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)

    try:
        while True:
            # Read from Pico
            if pico._port.in_waiting:
                data = pico._port.read(pico._port.in_waiting)
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()

            # Read from keyboard
            if _windows:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch == '\x1d':  # Ctrl+]
                        break
                    pico._port.write(ch.encode())
            else:
                r, _, _ = select.select([sys.stdin], [], [], 0.02)
                if r:
                    ch = sys.stdin.buffer.read(1)
                    if ch == b'\x1d':  # Ctrl+]
                        break
                    pico._port.write(ch)

            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        if not _windows:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print('\n--- REPL session ended ---')


# ---- backup ----

def cmd_backup(pico, args):
    """Download files from the Pico to a local backup directory."""
    print(f"Firmware: {pico.firmware_version()}\n")

    all_files = pico.list_files('/')
    print(f"{'Path':<40} {'Size':>10}")
    print('-' * 52)
    for path, size in all_files:
        if size == 'dir':
            print(f"{path + '/':<40} {'<dir>':>10}")
        else:
            print(f"{path:<40} {size:>9,}")
    print()

    if args.list:
        return

    if args.files:
        targets = [(p, s) for p, s in all_files if p in args.files and s != 'dir']
    elif args.dir_filter:
        prefix = args.dir_filter.rstrip('/') + '/'
        targets = [(p, s) for p, s in all_files if p.startswith(prefix) and s != 'dir']
    else:
        targets = [(p, s) for p, s in all_files if s != 'dir']

    if not targets:
        print('No files to download.')
        return

    os.makedirs(args.output, exist_ok=True)

    print(f"Downloading {len(targets)} file(s) to {args.output}/...")
    downloaded = 0
    try:
        for pico_path, size in targets:
            rel = pico_path.lstrip('/')
            local_path = os.path.join(args.output, rel)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            print(f"  {pico_path} ({size:,} bytes)...", end='', flush=True)
            try:
                data = pico.download_file(pico_path)
                with open(local_path, 'wb') as f:
                    f.write(data)
                print(f" OK ({len(data):,})")
                downloaded += 1
            except RuntimeError as e:
                print(f" FAILED: {e}")
    except KeyboardInterrupt:
        print(f'\n--- Interrupted. {downloaded}/{len(targets)} file(s) downloaded. ---')
        sys.exit(1)

    print(f"\nBackup complete: {args.output}/")


# ---- monitor ----

def cmd_monitor(pico, args):
    """Soft-reset and stream boot output until success marker or timeout."""
    print("Sending soft reset...\n")
    try:
        lines, success = pico.monitor_boot(
            timeout=args.timeout,
            success_markers=args.markers,
        )
        print()
        if success:
            print('Boot successful.')
        else:
            print('Boot did not produce expected output within timeout.')
            sys.exit(1)
    except KeyboardInterrupt:
        print('\n--- Detached (Ctrl+C). Pico continues running. ---')


def _auto_sync_rtc(pico):
    """Sync Pico RTC to host local time"""
    from datetime import datetime
    now = datetime.now()
    wd = now.weekday()
    code = (
        f"from machine import RTC\n"
        f"RTC().datetime(({now.year},{now.month},{now.day},{wd},"
        f"{now.hour},{now.minute},{now.second},0))\n"
        f"print('OK')\n"
    )
    try:
        pico.exec(code, timeout=5)
        print(f"RTC synced: {now.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"RTC sync failed: {e}")


# ---- main ----

def main():
    parser = argparse.ArgumentParser(
        prog='pico_ctl',
        description='All-in-one CLI for managing a Raspberry Pi Pico running MicroPython.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--port', '-p', help='Serial port (auto-detect if omitted)')
    parser.add_argument('--sync-rtc', action='store_true',
                        help='Sync device RTC to host time on connect')
    sub = parser.add_subparsers(dest='command')

    # -- Inspect --
    sub.add_parser('info', help='Show firmware, board ID, CPU, RAM, flash, and file listing')

    ls_p = sub.add_parser('ls', help='List files on the Pico')
    ls_p.add_argument('path', nargs='?', default='/',
                      help='Directory to list (default: /)')
    ls_p.add_argument('--flat', '-f', action='store_true',
                      help='Non-recursive listing')

    tree_p = sub.add_parser('tree', help='Show file tree with SHA256 hashes')
    tree_p.add_argument('path', nargs='?', default='/',
                        help='Directory to list (default: /)')

    cat_p = sub.add_parser('cat', help='Print file contents from the Pico')
    cat_p.add_argument('path', help='Pico path to read (e.g. /config.py)')

    edit_p = sub.add_parser('edit', help='Edit a file on the Pico using $EDITOR')
    edit_p.add_argument('path', help='Pico path to edit (e.g. /config.py)')

    cp_p = sub.add_parser('cp', help='Copy files to/from Pico (: prefix = Pico)')
    cp_p.add_argument('src', help='Source path (prefix with : for Pico)')
    cp_p.add_argument('dst', help='Destination path (prefix with : for Pico)')

    sub.add_parser('df', help='Show flash and RAM usage summary')

    sub.add_parser('ports', help='List available serial ports')

    # -- Execute --
    exec_p = sub.add_parser('exec', help='Execute Python code on the Pico')
    exec_p.add_argument('code', help='Python code to execute')
    exec_p.add_argument('--timeout', '-t', type=int, default=10,
                        help='Execution timeout in seconds')

    # mip
    mip_p = sub.add_parser('mip', help='Install a MicroPython package via mip (requires WiFi)')
    mip_p.add_argument('package', help='Package spec (e.g. github:user/repo or package-name)')
    mip_p.add_argument('--target', metavar='DIR',
                       help='Install target directory on the Pico (default: /lib)')
    mip_p.add_argument('--timeout', '-t', type=int, default=60,
                       help='Timeout in seconds (default: 60)')

    # run
    run_p = sub.add_parser('run', help='Run a .py file on the Pico and stream output')
    run_p.add_argument('file', help='Pico filename to run (e.g. test_all.py)')
    run_p.add_argument('--timeout', '-t', type=int, default=180,
                       help='Stream timeout in seconds (default: 180)')
    run_p.add_argument('--detach', '-d', action='store_true',
                       help='Launch script and disconnect (Pico keeps running)')

    # upload
    up_p = sub.add_parser('upload', help='Upload files and directories to the Pico')
    up_p.add_argument('--dry-run', '-n', action='store_true',
                      help='Show what would be uploaded without transferring')
    up_p.add_argument('--dir', '-d', nargs=2, metavar=('LOCAL_DIR', 'PICO_PREFIX'),
                      help='Upload a directory tree')
    up_p.add_argument('--src', '-s', metavar='SRC_DIR',
                      help='Upload all .py files from a directory to Pico root')
    up_p.add_argument('files', nargs='*', metavar='LOCAL PICO',
                      help='Pairs of local_path pico_path')

    # -- File management --
    # sync
    sync_p = sub.add_parser('sync', help='Upload only changed files (by size)')
    sync_p.add_argument('local_dir', help='Local directory to sync from')
    sync_p.add_argument('pico_prefix', help='Pico directory prefix (e.g. /pico_paper_lib)')
    sync_p.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be uploaded without transferring')

    # backup
    bk_p = sub.add_parser('backup', help='Download files from the Pico to local backup')
    bk_p.add_argument('--output', '-o', default='backup',
                      help='Local directory to save files (default: backup/)')
    bk_p.add_argument('--files', '-f', nargs='+',
                      help='Specific Pico paths to download (default: all)')
    bk_p.add_argument('--dir', '-d', dest='dir_filter',
                      help='Download only files under this Pico directory (e.g. /pico_paper_lib)')
    bk_p.add_argument('--list', '-l', action='store_true',
                      help='List files on Pico without downloading')

    rm_p = sub.add_parser('rm', help='Delete a file or directory from the Pico')
    rm_p.add_argument('path', help='Pico path to delete')
    rm_p.add_argument('-r', '--recursive', action='store_true',
                      help='Recursively delete a directory and all its contents')

    # -- Device control --
    sub.add_parser('reset', help='Soft-reset (restart main.py)')
    sub.add_parser('hard', help='Hard reset (machine.reset)')
    sub.add_parser('bootsel', help='Enter BOOTSEL mode for firmware flashing')

    rtc_p = sub.add_parser('rtc', help='Get or set the device real-time clock')
    rtc_p.add_argument('--set', '-s', action='store_true',
                       help='Set device RTC to host time')

    # -- Monitor --
    # monitor
    mon_p = sub.add_parser('monitor', help='Soft-reset and stream boot output')
    mon_p.add_argument('--timeout', '-t', type=int, default=45,
                       help='Seconds to wait for output (default: 45)')
    mon_p.add_argument('--markers', '-m', nargs='+',
                       default=['Display updated', 'No change', 'Free mem'],
                       help='Success markers to watch for')

    # watch
    watch_p = sub.add_parser('watch', help='Attach to serial output (Ctrl+C to detach)')
    watch_p.add_argument('--timeout', '-t', type=int, default=0,
                         help='Seconds to watch (0 = indefinite, default: 0)')
    watch_p.add_argument('--reset', '-r', action='store_true',
                         help='Soft-reset before watching')

    sub.add_parser('repl', help='Interactive MicroPython REPL (Ctrl+] to exit)')

    args = parser.parse_args()

    if not args.command:
        args.command = 'info'

    # Commands that don't need a Pico connection
    if args.command == 'ports':
        cmd_ports()
        return

    # upload --dry-run doesn't need a connection
    if args.command == 'upload' and args.dry_run:
        cmd_upload(None, args)
        return

    print(f"Connecting to Pico{' on ' + args.port if args.port else ''}...")
    try:
        with PicoSerial(port=args.port) as pico:
            print(f"Connected: {pico.port_name}")

            if args.sync_rtc or os.environ.get('PICO_SYNC_RTC', '').strip() == '1':
                _auto_sync_rtc(pico)

            commands = {
                'info': cmd_info,
                'ls': cmd_ls,
                'tree': cmd_tree,
                'cat': cmd_cat,
                'cp': cmd_cp,
                'edit': cmd_edit,
                'df': cmd_df,
                'reset': cmd_reset,
                'hard': cmd_hard,
                'bootsel': cmd_bootsel,
                'rtc': cmd_rtc,
                'rm': cmd_rm,
                'exec': cmd_exec,
                'mip': cmd_mip,
                'run': cmd_run,
                'upload': cmd_upload,
                'sync': cmd_sync,
                'backup': cmd_backup,
                'monitor': cmd_monitor,
                'watch': cmd_watch,
                'repl': cmd_repl,
            }
            try:
                commands[args.command](pico, args)
            except KeyboardInterrupt:
                print('\n--- Interrupted. ---')
                sys.exit(1)
    except KeyboardInterrupt:
        print('\n--- Interrupted. ---')
        sys.exit(1)


if __name__ == '__main__':
    main()

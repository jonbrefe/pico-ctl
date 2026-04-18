#!/usr/bin/env python3
"""
pico_serial — Shared serial communication library for Raspberry Pi Pico.

Handles COM port auto-detection, MicroPython REPL paste-mode execution,
base64-chunked file upload, and remote filesystem operations.

Usage::

    from pico_serial import PicoSerial

    pico = PicoSerial()              # auto-detect COM port
    pico = PicoSerial(port='COM3')   # or specify manually

    # Execute code on the Pico
    result = pico.exec('print("hi")')

    # Upload a file
    pico.upload_file('local/main.py', '/main.py')

    # List remote files
    files = pico.list_files('/')

    pico.close()
"""

import serial
import serial.tools.list_ports
import time
import base64
import sys

# Raspberry Pi Pico USB Vendor ID (covers Pico, Pico W, Pico 2, Pico 2 W)
_PICO_VID = 0x2E8A


class PicoSerial:
    """Manages a serial connection to a Raspberry Pi Pico running MicroPython."""

    def __init__(self, port=None, baudrate=115200, timeout=2):
        self.port_name = port or self._auto_detect()
        self._port = serial.Serial(self.port_name, baudrate, timeout=timeout)
        time.sleep(0.5)
        self._interrupt()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @staticmethod
    def _is_wsl():
        """Check if running inside WSL."""
        try:
            with open('/proc/version', 'r') as f:
                return 'microsoft' in f.read().lower()
        except OSError:
            return False

    @staticmethod
    def list_ports():
        """List all serial ports with details. Returns list of dicts."""
        ports = serial.tools.list_ports.comports()
        result = []
        for p in sorted(ports, key=lambda x: x.device):
            result.append({
                'device': p.device,
                'description': p.description or '',
                'vid': p.vid,
                'pid': p.pid,
                'serial_number': p.serial_number or '',
                'is_pico': p.vid == _PICO_VID,
            })
        return result

    @staticmethod
    def _auto_detect():
        """Find the first serial port with the Pico's USB VID."""
        ports = serial.tools.list_ports.comports()
        pico_ports = [p for p in ports if p.vid == _PICO_VID]
        if len(pico_ports) == 1:
            return pico_ports[0].device
        if len(pico_ports) > 1:
            devices = [p.device for p in pico_ports]
            print(f"Multiple Pico devices found: {', '.join(devices)}")
            print(f"Using {devices[0]}. Override with --port <device>.")
            return pico_ports[0].device
        available = [f"{p.device} ({p.description})" for p in ports]
        msg = f"No Pico found (VID 0x{_PICO_VID:04X}). Available ports: {available}"
        if PicoSerial._is_wsl():
            msg += (
                "\n\n  WSL2 detected — USB devices are not visible by default."
                "\n  You need to attach the Pico with usbipd from an admin PowerShell:"
                "\n"
                "\n    usbipd list"
                "\n    usbipd bind --busid <BUSID>"
                "\n    usbipd attach --wsl --busid <BUSID>"
                "\n"
                "\n  See the 'WSL2 Setup (USB Passthrough)' section in README.md."
            )
        raise RuntimeError(msg)

    def _interrupt(self):
        """Send Ctrl+C twice to break any running program."""
        self._port.write(b'\x03\x03')
        time.sleep(1.5)
        self._port.reset_input_buffer()

    def close(self):
        """Close the serial port."""
        if self._port and self._port.is_open:
            self._port.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # REPL execution
    # ------------------------------------------------------------------
    def exec(self, code, timeout=10):
        """Execute Python code on the Pico via paste mode.

        Returns the decoded output string.
        """
        self._port.reset_input_buffer()
        self._port.write(b'\x05')       # enter paste mode
        time.sleep(0.3)
        self._port.read(self._port.in_waiting)  # discard prompt
        self._port.write(code.encode())
        time.sleep(0.2)
        self._port.write(b'\x04')       # execute
        result = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._port.in_waiting:
                result += self._port.read(self._port.in_waiting)
                time.sleep(0.05)
            else:
                time.sleep(0.1)
                if result.endswith(b'>>> '):
                    break
        return result.decode('utf-8', errors='replace')

    # ------------------------------------------------------------------
    # Soft / hard reset
    # ------------------------------------------------------------------
    def soft_reset(self):
        """Send Ctrl+D to soft-reboot the Pico."""
        self._port.reset_input_buffer()
        self._port.write(b'\x04')

    def hard_reset(self):
        """Execute machine.reset() for a full hardware reset."""
        self.exec('import machine; machine.reset()', timeout=3)

    def enter_bootsel(self):
        """Enter BOOTSEL mode (USB mass storage) for firmware flashing."""
        self.exec('import machine; machine.bootloader()', timeout=3)

    # ------------------------------------------------------------------
    # Boot monitoring
    # ------------------------------------------------------------------
    def monitor_boot(self, timeout=45, success_markers=None):
        """Soft-reset and stream boot output until a marker or timeout.

        Returns (output_lines, success_bool).
        """
        if success_markers is None:
            success_markers = ['Display updated', 'No change', 'Free mem']
        self.soft_reset()
        lines = []
        success = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._port.in_waiting:
                data = self._port.read(self._port.in_waiting)
                text = data.decode('utf-8', errors='replace')
                for line in text.split('\n'):
                    line = line.strip()
                    if line:
                        lines.append(line)
                        print(line)
                        if any(m in line for m in success_markers):
                            success = True
                        if 'Traceback' in line:
                            success = False
            else:
                time.sleep(0.3)
            if success:
                # Read a bit more output after success
                time.sleep(2)
                if self._port.in_waiting:
                    extra = self._port.read(self._port.in_waiting)
                    for line in extra.decode('utf-8', errors='replace').split('\n'):
                        line = line.strip()
                        if line:
                            lines.append(line)
                            print(line)
                break
        return lines, success

    # ------------------------------------------------------------------
    # Remote filesystem
    # ------------------------------------------------------------------
    def _setup_upload_helper(self):
        """Inject the base64 write helper onto the Pico."""
        self.exec("""import ubinascii, os
def _wf(name, chunks):
    data = b''
    for c in chunks:
        data += ubinascii.a2b_base64(c)
    with open(name, 'wb') as f:
        f.write(data)
    print('WROTE:' + name + ':' + str(len(data)))
def _mkp(path):
    parts = path.strip('/').split('/')
    cur = ''
    for p in parts:
        cur += '/' + p
        try:
            os.mkdir(cur)
        except OSError:
            pass
""", timeout=5)

    def mkdir(self, path):
        """Create a directory (and parents) on the Pico."""
        self._setup_upload_helper()
        self.exec(f"_mkp('{path}')\n", timeout=5)

    def upload_file(self, local_path, pico_path, chunk_size=256, batch_size=8):
        """Upload a local file to the Pico filesystem.

        Uses base64 encoding with batched paste-mode transfers.
        Returns the number of bytes written.
        """
        with open(local_path, 'rb') as f:
            content = f.read()

        b64 = base64.b64encode(content).decode('ascii')
        chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]

        # Ensure parent directory exists
        parent = '/'.join(pico_path.split('/')[:-1])
        if parent and parent != '/':
            self.exec(f"_mkp('{parent}')\n", timeout=5)

        self.exec("_c = []\n", timeout=5)
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            adds = ''.join(f"_c.append('{c}')\n" for c in batch)
            resp = self.exec(adds, timeout=10)
            if 'Traceback' in resp:
                raise RuntimeError(f"Upload error at chunk {i}: {resp}")

        # Larger files need more time to decode + write
        write_timeout = max(15, len(content) // 1000)
        resp = self.exec(f"_wf('{pico_path}', _c)\n", timeout=write_timeout)
        for line in resp.split('\r\n'):
            if line.strip().startswith('WROTE:'):
                parts = line.strip().split(':')
                return int(parts[2]) if len(parts) >= 3 else len(content)
        raise RuntimeError(f"No write confirmation. Response: {resp[-300:]}")

    def list_files(self, path='/', recursive=True):
        """List files on the Pico. Returns list of (path, size) tuples."""
        if recursive:
            code = f"""import os
def _ls(p, out):
    for f in sorted(os.listdir(p)):
        full = p.rstrip('/') + '/' + f
        try:
            os.listdir(full)
            _ls(full, out)
        except:
            sz = os.stat(full)[6]
            print(full + ':' + str(sz))
_ls('{path}', [])
"""
        else:
            code = f"""import os
for f in sorted(os.listdir('{path}')):
    full = '{path}'.rstrip('/') + '/' + f
    try:
        os.listdir(full)
        print(full + '/:dir')
    except:
        sz = os.stat(full)[6]
        print(full + ':' + str(sz))
"""
        resp = self.exec(code, timeout=10)
        files = []
        for line in resp.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('import') and '>>>' not in line:
                parts = line.rsplit(':', 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    size = parts[1].strip()
                    if size == 'dir':
                        files.append((name, 'dir'))
                    elif size.isdigit():
                        files.append((name, int(size)))
        return files

    def download_file(self, pico_path):
        """Download a file from the Pico. Returns bytes."""
        code = f"""import ubinascii
with open('{pico_path}', 'rb') as f:
    data = f.read()
print('<<<START>>>')
print(ubinascii.b2a_base64(data).decode().strip())
print('<<<END>>>')
"""
        resp = self.exec(code, timeout=30)
        # Use rfind to skip past the echoed code and find the actual output markers
        start = resp.rfind('<<<START>>>')
        end = resp.rfind('<<<END>>>')
        if start < 0 or end < 0:
            raise RuntimeError(f"Download failed: {resp[-200:]}")
        b64_data = resp[start + 11:end].strip()
        return base64.b64decode(b64_data)

    def delete_file(self, pico_path):
        """Delete a file on the Pico."""
        self.exec(f"import os; os.remove('{pico_path}')\n", timeout=5)

    def firmware_version(self):
        """Return the MicroPython version string from the Pico."""
        resp = self.exec("import sys; print(sys.version)\n", timeout=5)
        for line in resp.split('\n'):
            line = line.strip()
            if line and 'import' not in line and '>>>' not in line:
                return line
        return 'unknown'


if __name__ == '__main__':
    print('pico_serial is a library, not a standalone tool.')
    print()
    print('Usage:')
    print('  python3 pico_ctl.py --help')

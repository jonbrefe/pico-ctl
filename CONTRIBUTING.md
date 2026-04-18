# Contributing to pico-ctl

Thank you for your interest in contributing!

## Bug Reports

Open a GitHub issue with:

1. **What you expected** vs **what happened**
2. Output of `pico_ctl info`
3. Host OS and Python version (`python3 --version`)
4. Full error message or traceback

## Development Setup

```bash
git clone https://github.com/jonbrefe/pico-ctl.git
cd pico-ctl
pip install -r requirements.txt
python3 pico_ctl.py info    # verify against a connected Pico
```

## Code Style

- Python 3.8+ (no f-string walrus operators or newer-only features)
- All `cmd_*` functions take `(pico, args)` and have a docstring
- `PicoSerial` methods have docstrings
- Keep `pico_ctl.py` as a single file — no splitting into submodules

## Testing

There is no automated test suite — all testing requires a physical Pico connected via USB.

Before submitting a PR, verify at minimum:

```bash
pico_ctl info
pico_ctl ls /
pico_ctl upload some_file.py /some_file.py
pico_ctl cat /some_file.py
pico_ctl rm /some_file.py
```

## Pull Requests

1. Fork the repo and create a feature branch
2. Keep changes focused — one feature or fix per PR
3. Update the man page (`pico_ctl.1`) if adding/changing commands
4. Update `README.md` if adding user-facing features
5. Test against a physical Pico

## Packaging

If you change the version number, update it in **all three places**:

- `setup.py` (`version=`)
- `debian/changelog` (top entry)
- `pico-ctl.spec` (`Version:`)
- `pico_ctl.1` (`.TH` header)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

# Building SmartSort

This document describes how to build SmartSort from source and produce a release package.

---

## Prerequisites

Install the required runtime and build dependencies:

```bash
sudo apt-get install python3 python3-pyqt6 python3-watchdog python3-notify2 \
                     dpkg-dev libglib2.0-0 gir1.2-notify-0.7
```

For development, also install:

```bash
pip install pytest typeguard
```

---

## Running from Source

```bash
git clone https://github.com/smartsort-org/smartsort.git
cd smartsort
PYTHONPATH=. python main.py
```

---

## Building the Debian Package

SmartSort v1.0.3 is distributed as a `.deb` package only.

```bash
bash packaging/debian/build_deb.sh
```

The script:
1. Reads the version from `src/version.py`
2. Assembles the package tree under `packaging/debian/smartsort_<ver>_all/`
3. Calls `dpkg-deb --build` to produce `build/deb/smartsort_<ver>_all.deb`
4. Cleans up the temporary tree

Output: `build/deb/smartsort_1.0.3_all.deb`

---

## Running the Test Suite

```bash
PYTHONPATH=. pytest
```

For CI / headless environments:

```bash
xvfb-run -a python -m pytest -vv -s tests/
```

See [docs/ci_headless_hang_postmortem.md](ci_headless_hang_postmortem.md) for details on
the headless Qt test isolation approach used in this project.

---

## Release Checklist

1. Bump `src/version.py`
2. Update `CHANGELOG.md`
3. Run `PYTHONPATH=. pytest` — all tests must pass
4. Run `bash packaging/debian/build_deb.sh`
5. Verify package: `dpkg-deb -I build/deb/smartsort_<ver>_all.deb`
6. Install and smoke-test on a clean Debian/Ubuntu machine

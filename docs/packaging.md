# Packaging

SmartSort is distributed exclusively as a **Debian package (`.deb`)**.

The package targets Debian-based desktops with all required dependency packages
available. The current dependency set was audited against Debian 13 (Trixie).
Older Debian/Ubuntu/Mint releases need a repository that supplies these packages;
the previous broad release list is not a compatibility certification.

Required runtime packages: `python3`, `python3-pyqt6`, `python3-watchdog`,
`python3-notify2`, `python3-pypdf`, `python3-pil`, `python3-mutagen`,
`libglib2.0-0`, and `gir1.2-notify-0.7`.

`python3-docx` and `python3-openpyxl` are suggested compatibility tools. Native
bounded XML readers handle Office/OpenDocument extraction without requiring
these optional SDKs. SQLite, cache management and the core intelligence engine
use Python's standard library. Dependencies are resolved by apt; the package
contains no downloaded Python wheels or vendored site-packages.

---

## Package Contents

The `.deb` package installs the following:

| Path | Description |
|---|---|
| `/usr/bin/smartsort` | Wrapper launch script |
| `/usr/share/smartsort/` | Application source (Python) |
| `/usr/share/smartsort/config/config.default.json` | Default configuration |
| `/usr/share/applications/smartsort.desktop` | Desktop launcher |
| `/usr/lib/systemd/user/smartsort.service` | User systemd service |
| `/usr/share/icons/hicolor/*/apps/smartsort*.png` | Application icons |

---

## Installing

```bash
sudo apt install ./smartsort_1.2.12_all.deb
```

## Uninstalling

```bash
sudo dpkg -r smartsort
```

---

## Building the .deb from Source

Build prerequisites: `bash`, `tar`, `dpkg`, and `dpkg-deb`. Runtime dependencies
are needed to run/smoke-test the extracted app, rather than to assemble it.

```bash
bash packaging/debian/build_deb.sh
```

Default output: `build/deb/smartsort_1.2.12_all.deb` (version read from
`src/version.py`). For a distinct preview build:

```bash
SMARTSORT_PACKAGE_VERSION=1.1.6+intelligence.20261118.1 bash packaging/debian/build_deb.sh
```

Preview output: `build/deb/smartsort_1.1.6+intelligence.20261118.1_all.deb`.
This package suffix identifies the local feature preview; the app's base version
was 1.1.6 for that preview. The current numbered build is 1.2.12; hosted release certification remains separate.

The complete `src/core/file_intelligence/` tree, including cache and privacy
normalization, is copied into `/usr/share/smartsort/`. Maintainer scripts are 0755
and archive ownership is root:root. Shared hicolor directories contain only
SmartSort-owned icons: `index.theme` and `icon-theme.cache` are never installed.
Bytecode, tests, local configuration and validation logs are excluded.

See [build.md](build.md) for detailed instructions.


## Choosing the sorting behavior

In Settings → File intelligence, choose **Content intelligence — analyze all
files**, then **Save settings** to use content/context-based destinations.
**Rules first** preserves the existing behavior: matched rules bypass analysis.
Your saved rules are retained in either mode. Dashboard and Organize folder show
the current saved mode and provide a Change mode shortcut. Review a fresh preview
after changing modes. If Background Monitoring shows a running separate service,
use its Restart button to reload the saved configuration.

### Upgrading to 1.2.12

Exit any older running SmartSort copies once before launching the upgraded app.
Version 1.2.12 keeps one GUI per user runtime; clicking its icon again restores
the existing dashboard. Normal launches show a tiny theme-aware startup panel;
configured tray/minimized launches stay in the background when a tray is available.
The separate `--daemon` entry point is unchanged.

# SmartSort 1.2.2 startup and instance handling

Implemented 2026-11-18. The build is local; it has not been installed or published.

Repeated normal launches contact the existing GUI and restore its dashboard,
including when hidden in the tray or minimized. Ownership is claimed before
configuration loading, logging, icon work or window construction. A per-user
private runtime directory contains a kernel-owned flock and a local activation
socket. Concurrent launches cannot create multiple GUI owners; crashed owners
release the lock automatically, and the next owner removes the stale socket.
Unusable ownership or communication produces a bounded error instead of an
unguarded second GUI. Restart closes ownership before starting its replacement.

Normal startup paints a static 300 × 104 logical-pixel “Starting SmartSort…”
panel before expensive GUI work. It follows light/dark settings and screen pixel
ratio, and closes as the dashboard becomes ready. There is no animation, timer,
minimum display duration or new dependency. Tray/minimized settings remain
supported, and a duplicate `--service` launch exits quietly. `--daemon` retains
its separate existing behavior.

## Validation

- Full suite: **1,513 passed, 1 existing skip**, in 36.75 seconds; natural exit 0.
- Teardown inventory: no Python threads, running QThreads, active QTimers or child processes.
- Native IPC regressions cover six racing launches, activation while startup is
  pending, crash recovery, malformed requests, unsafe runtime paths and ownership
  cleanup. Startup regressions cover splash ordering, secondary early exit,
  minimized/tray operation, errors and restart ordering.
- Real extracted Debian package, system Python, offscreen Qt, private XDG/runtime
  state: one dashboard constructed; two normal duplicate launches produced two
  activation callbacks; duplicate service launch stayed quiet; owner exited
  naturally and removed its socket. Monitoring, autostart changes, desktop
  notifications and user icon installation were suppressed in this smoke check.
- Visually inspected both static splash renders at their actual 300 × 104 size.
- Package source parity includes main.py, both new startup modules, main window,
  sorting/configuration code and all intelligence modules. Root ownership, script
  modes, desktop entry and shell syntax passed. No bytecode or shared hicolor
  index/cache files are included. Extracted-package sorting/report smoke passed.
- APT simulated a successful upgrade from the installed 1.2.0 to 1.2.2.

The first full run caught test-order pollution: a core startup test imported a
Qt helper while QApplication was mocked. The tests now load the real helper
before substituting the factory; the complete rerun passed. Production code did
not need a workaround for mocks.

Evidence: `build/validation/startup/` and `build/validation/version-1.2.2/`.
Package: `build/deb/smartsort_1.2.2_all.deb`, with adjacent SHA-256 sidecar.

## Upgrade and practical limits

Exit all older SmartSort copies once before launching 1.2.2: older running code
has no instance guard. Install the new package with:

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.2_all.deb
```

Window activation requests are sent to Qt; desktop/compositor focus policy can
limit foreground focus. Offscreen checks cannot certify that policy on a live
Wayland/X11 desktop. Local tests are not hosted release certification.

## Reference checks

Community searches returned no directly applicable Qt single-instance examples;
no community consensus is claimed. Implementation behavior was checked against
Qt's [QLocalServer](https://doc.qt.io/qt-6/qlocalserver.html),
[QLocalSocket](https://doc.qt.io/qt-6/qlocalsocket.html) and
[QSplashScreen](https://doc.qt.io/qt-6/qsplashscreen.html) documentation. In
particular, the panel closes directly instead of waiting for exposure of a
potentially hidden tray window.

"""Lightweight startup ordering and duplicate-launch regression checks."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def startup_harness(monkeypatch, qapp):
    import main
    import PyQt6.QtWidgets as widgets
    import src.gui.main_window as window_module
    import src.gui.single_instance as instance_module
    import src.gui.startup as startup_module
    import src.utils.config as config_module
    import src.utils.logger as logger_module

    state = SimpleNamespace(events=[], primary=True, minimized=False, tray=True,
                            theme='dark', pending_activation=False, failure=False,
                            windows=[], guards=[], splashes=[])

    class Signal:
        def __init__(self):
            self.callbacks = []
        def connect(self, callback):
            self.callbacks.append(callback)
        def emit(self):
            for callback in list(self.callbacks):
                callback()

    class Application:
        _instance = None
        def __init__(self, args):
            self.aboutToQuit = Signal()
            self.__class__._instance = self
            state.events.append('app')
        @classmethod
        def instance(cls):
            return cls._instance
        def setApplicationName(self, *args): pass
        def setOrganizationName(self, *args): pass
        def setDesktopFileName(self, *args): pass
        def setWindowIcon(self, *args): pass
        def setQuitOnLastWindowClosed(self, *args): pass
        def processEvents(self, *args):
            state.events.append('paint')
        def exec(self):
            state.events.append('exec')
            self.aboutToQuit.emit()
            return 0

    class Config:
        def __init__(self):
            state.events.append('config')
        def get(self, key, default=None):
            return {'start_minimized': state.minimized, 'theme': state.theme}.get(key, default)

    class Guard:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.callback = None
            state.guards.append(self)
        def acquire_or_notify(self, *, activate=True):
            state.requested_activation = activate
            state.events.append('guard')
            return state.primary
        def set_activation_handler(self, callback):
            self.callback = callback
            state.events.append('handler')
            if state.pending_activation:
                callback()
        def close(self):
            if not self.closed:
                self.closed = True
                state.events.append('release')

    class Splash:
        def __init__(self, theme='system'):
            self.theme = theme
            self.closed = False
            state.splashes.append(self)
            state.events.append('splash')
        def show(self):
            state.events.append('splash-show')
        def finish(self, window):
            state.events.append('splash-finish')
            self.close()
        def close(self):
            if not self.closed:
                self.closed = True
                state.events.append('splash-close')

    class Window:
        def __init__(self, config=None):
            state.events.append('window')
            if state.failure:
                raise RuntimeError('synthetic startup failure')
            self.tray_available = state.tray
            self.visible = False
            self.dashboard = None
            state.windows.append(self)
        def show(self):
            self.visible = True
            state.events.append('show')
        def showNormal(self):
            self.visible = True
            state.events.append('restore')
        def show_tab(self, index):
            self.dashboard = index
            self.visible = True
            state.events.append('dashboard')
        def raise_(self):
            state.events.append('raise')
        def activateWindow(self):
            state.events.append('activate')

    monkeypatch.setattr(widgets, 'QApplication', Application)
    monkeypatch.setattr(instance_module, 'SingleInstanceGuard', Guard)
    monkeypatch.setattr(startup_module, 'StartupSplash', Splash)
    monkeypatch.setattr(config_module, 'ConfigManager', Config)
    monkeypatch.setattr(logger_module, 'SmartSortLogger', lambda: state.events.append('logger'))
    monkeypatch.setattr(main, 'ensure_user_icons_installed', lambda *args: state.events.append('icons'))
    monkeypatch.setattr(window_module, 'SmartSortGUI', Window)
    monkeypatch.setattr('sys.argv', ['main.py'])
    state.main = main
    return state


def invoke_main(state):
    try:
        return state.main.main()
    except SystemExit as error:
        return error.code


def test_secondary_launch_exits_before_startup_work(startup_harness):
    state = startup_harness
    state.primary = False
    assert invoke_main(state) == 0
    assert not state.windows and not state.splashes
    assert all(event not in state.events for event in ('config', 'logger', 'icons', 'window', 'exec'))
    assert state.guards[0].closed


def test_splash_first_frame_precedes_expensive_window_startup(startup_harness):
    state = startup_harness
    assert invoke_main(state) == 0
    assert state.events.index('splash-show') < state.events.index('paint')
    assert state.events.index('paint') < state.events.index('logger')
    assert state.events.index('paint') < state.events.index('icons')
    assert state.events.index('paint') < state.events.index('window')
    assert len(state.windows) == 1 and state.windows[0].visible
    assert state.splashes[0].theme == 'dark' and state.splashes[0].closed
    assert state.guards[0].closed


@pytest.mark.parametrize('background', ['service', 'minimized'])
def test_background_gui_launch_has_no_splash_or_visible_dashboard(startup_harness, monkeypatch, background):
    state = startup_harness
    if background == 'service':
        monkeypatch.setattr('sys.argv', ['main.py', '--service'])
    else:
        state.minimized = True
    assert invoke_main(state) == 0
    assert not state.splashes
    assert len(state.windows) == 1 and not state.windows[0].visible
    assert state.guards[0].closed


def test_background_launch_without_tray_still_shows_dashboard(startup_harness, monkeypatch):
    state = startup_harness
    state.tray = False
    monkeypatch.setattr('sys.argv', ['main.py', '--service'])
    assert invoke_main(state) == 0
    assert state.windows[0].visible
    assert not state.splashes


def test_pending_activation_restores_dashboard_even_for_background_start(startup_harness):
    state = startup_harness
    state.minimized = True
    state.pending_activation = True
    assert invoke_main(state) == 0
    assert len(state.windows) == 1
    assert state.windows[0].visible and state.windows[0].dashboard == 0
    assert 'handler' in state.events and 'activate' in state.events


def test_startup_failure_closes_splash_and_releases_primary_guard(startup_harness):
    state = startup_harness
    state.failure = True
    with pytest.raises(RuntimeError, match='synthetic startup failure'):
        invoke_main(state)
    assert state.splashes[0].closed
    assert state.guards[0].closed
    assert 'exec' not in state.events


def test_daemon_branch_does_not_construct_gui_startup(startup_harness, monkeypatch):
    state = startup_harness
    calls = []
    monkeypatch.setattr(state.main, 'run_daemon', lambda: calls.append(True))
    monkeypatch.setattr('sys.argv', ['main.py', '--daemon'])
    invoke_main(state)
    assert calls == [True]
    assert not state.guards and not state.splashes and not state.windows


@pytest.mark.parametrize('theme', ['light', 'dark', 'system'])
def test_real_startup_splash_is_small_and_closes_without_window_exposure(qapp, theme):
    from PyQt6.QtWidgets import QWidget
    from src.gui.startup import StartupSplash
    splash = StartupSplash(theme=theme)
    try:
        assert splash.width() <= 360 and splash.height() <= 140
        assert not splash.pixmap().isNull()
        splash.show()
        qapp.processEvents()
        assert splash.isVisible()
        hidden = QWidget()
        splash.finish(hidden)
        assert not splash.isVisible()
        hidden.deleteLater()
    finally:
        splash.close()
        splash.deleteLater()
        qapp.processEvents()


def test_activate_dashboard_restores_existing_window_without_replacing_it():
    from src.gui.startup import activate_dashboard
    calls = []
    class ExistingWindow:
        def show_tab(self, index): calls.append(('tab', index))
        def showNormal(self): calls.append(('normal',))
        def raise_(self): calls.append(('raise',))
        def activateWindow(self): calls.append(('activate',))
    activate_dashboard(ExistingWindow())
    assert ('tab', 0) in calls and ('normal',) in calls
    assert ('raise',) in calls and ('activate',) in calls


def test_restart_releases_instance_guard_before_respawning(monkeypatch):
    import src.gui.main_window as module
    calls = []
    class Guard:
        def close(self): calls.append('release')
    class Window:
        _instance_guard = Guard()
        really_exit = False
        def close(self): calls.append('close')
    monkeypatch.setattr('subprocess.Popen', lambda *args, **kwargs: calls.append('spawn'))
    monkeypatch.setattr(module.QApplication, 'quit', lambda: calls.append('quit'))
    window = Window()
    module.SmartSortGUI.restart_application(window)
    assert window.really_exit
    assert calls.index('close') < calls.index('release') < calls.index('spawn')


def test_secondary_process_does_not_import_heavy_gui_or_configuration(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    code = '''
import importlib.abc, sys
import PyQt6.QtWidgets as widgets
import src.gui.single_instance as instance
class App:
    def __init__(self,*args): pass
    def setApplicationName(self,*args): pass
    def setOrganizationName(self,*args): pass
    def setDesktopFileName(self,*args): pass
    def setQuitOnLastWindowClosed(self,*args): pass
class Guard:
    def __init__(self,*args,**kwargs): pass
    def acquire_or_notify(self, **kwargs): return False
    def close(self): pass
widgets.QApplication=App
instance.SingleInstanceGuard=Guard
class NoHeavyStartup(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'src.gui.main_window','src.utils.config','src.utils.logger'}:
            raise AssertionError('Duplicate launch imported heavy startup: '+fullname)
sys.meta_path.insert(0,NoHeavyStartup())
import main
sys.argv=['main.py']
try:
    result=main.main()
except SystemExit as error:
    result=error.code
assert result == 0
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root))
    completed = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp_path,
                               env=environment, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_service_duplicate_exits_without_foreground_request(startup_harness, monkeypatch):
    state = startup_harness
    state.primary = False
    monkeypatch.setattr('sys.argv', ['main.py', '--service'])
    assert invoke_main(state) == 0
    assert state.requested_activation is False
    assert not state.windows


def test_unsafe_runtime_reports_failure_without_unguarded_gui(startup_harness, monkeypatch, capsys):
    from src.gui.single_instance import InstanceGuardError
    state = startup_harness
    def fail(*args, **kwargs):
        raise InstanceGuardError('synthetic unsafe runtime')
    monkeypatch.setattr('src.gui.single_instance.SingleInstanceGuard', fail)
    assert invoke_main(state) == 1
    assert 'synthetic unsafe runtime' in capsys.readouterr().err
    assert not state.windows and not state.splashes

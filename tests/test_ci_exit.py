"""The real Qt fixture must preserve both successful and failing CLI exit codes."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('fails,expected', [(False, 0), (True, 1)], ids=['pass', 'fail'])
def test_qapp_teardown_preserves_pytest_process_status(tmp_path, fails, expected):
    fixture_file = Path(__file__).with_name('conftest.py')
    case = tmp_path / 'test_exit_canary.py'
    case.write_text('def test_exit_canary(qapp):\n    assert ' + ('False' if fails else 'True') + '\n')
    code = '''
import importlib.util, sys, pytest
spec=importlib.util.spec_from_file_location('smartsort_qapp_fixture',sys.argv[1])
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',sys.argv[2]],plugins=[fixture]))
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
    environment.pop('DISPLAY', None)
    environment.pop('WAYLAND_DISPLAY', None)
    completed = subprocess.run([sys.executable, '-B', '-c', code, str(fixture_file), str(case)],
                               cwd=tmp_path, env=environment, capture_output=True, text=True,
                               timeout=20)
    assert completed.returncode == expected, completed.stdout + completed.stderr
    assert ('1 failed' if fails else '1 passed') in completed.stdout

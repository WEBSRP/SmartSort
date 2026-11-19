"""Explicit content sorting without discarding the user's saved routing rules."""

import copy
import hashlib
import json
from pathlib import Path
import socket
import zipfile

import pytest

from src.core.directory_organizer import DirectoryOrganizer, OperationStatus
from src.core.file_intelligence import ConfidenceLevel
from src.organizer import FileOrganizer
from src.utils.config import ConfigManager


class ModeConfig:
    def __init__(self, root, **changes):
        self.data = dict(rules=broad_rules(), destination_base=str(root / 'sorted'),
                         enable_origin_detection=False, enable_deep_content_extraction=True,
                         enable_notifications=False, smart_filename_cleanup=False,
                         enable_duplicate_detection=True, conflict_resolution='rename')
        self.data.update(changes)

    def get(self, key, default=None):
        return self.data.get(key, default)


class ModeLogger:
    def warning(self, *args): pass
    def info(self, *args): pass
    def debug(self, *args): pass
    def error(self, *args): pass
    def log_action(self, *args): pass


def broad_rules():
    return [
        dict(id='documents', name='Documents', enabled=True, priority=1,
             conditions=[dict(type='extension', value=['.md', '.pdf'])], destination='Documents'),
        dict(id='archives', name='Archives', enabled=True, priority=2,
             conditions=[dict(type='extension', value=['.zip'])], destination='Archives'),
    ]


@pytest.fixture(autouse=True)
def mode_test_isolation(tmp_path, monkeypatch):
    for key, folder in [('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache'),
                        ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state')]:
        monkeypatch.setenv(key, str(tmp_path / folder))
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home)
    def offline(*args, **kwargs):
        raise AssertionError('Sorting-mode integration tests must stay offline')
    monkeypatch.setattr(socket, 'socket', offline)
    monkeypatch.setattr(socket, 'create_connection', offline)


def make_mode_organizer(root, download=False, **changes):
    config = ModeConfig(root, **changes)
    instance = FileOrganizer(config, ModeLogger()) if download else DirectoryOrganizer(config, ModeLogger())
    return instance, config


def course_pdf():
    text = b'BT /F1 12 Tf 30 100 Td (Database course lecture normalization notes) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(text)).encode() + b' >>\nstream\n' + text + b'\nendstream',
               b'<< /Title (DBMS Database Lecture) >>']
    data = b'%PDF-1.4\n'
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(number).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 7\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
    return data + b'trailer\n<< /Size 7 /Root 1 0 R /Info 6 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'


def mode_sample(root, kind):
    if kind == 'invoice':
        source = root / 'opaque.md'
        source.write_text('# Invoice\nFinance billing invoice total due')
    elif kind == 'course':
        source = root / 'Lecture_DBMS.pdf'
        source.write_bytes(course_pdf())
    else:
        source = root / 'SmartSort_Source.zip'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('main.py', 'def main():\n    return 0\n')
    return source


CASES = [
    ('invoice', 'Documents', 'Work/Invoices'),
    ('course', 'Documents', 'College/DBMS/Lectures'),
    ('project', 'Archives', 'Projects/SmartSort/Source'),
]


@pytest.mark.parametrize('mode', [None, 'rules_first'], ids=['legacy-default', 'rules-first'])
@pytest.mark.parametrize('kind,rule_folder,intelligent_folder', CASES)
def test_saved_rules_keep_legacy_directory_routes(tmp_path, mode, kind, rule_folder, intelligent_folder):
    source = mode_sample(tmp_path, kind)
    changes = {} if mode is None else {'sorting_mode': mode}
    instance, config = make_mode_organizer(tmp_path, **changes)
    before = copy.deepcopy(config.data)
    plan = instance.plan(str(tmp_path), [str(source)])
    item, = plan.items
    assert item.target_path == str(tmp_path / rule_folder / source.name)
    assert item.rule_name == rule_folder and item.confidence == 'CONFIRMED'
    assert source.exists() and config.data == before


@pytest.mark.parametrize('download', [False, True], ids=['directory', 'download'])
def test_rules_first_still_short_circuits_content_profiling(tmp_path, monkeypatch, download):
    source = mode_sample(tmp_path, 'invoice')
    instance, _ = make_mode_organizer(tmp_path, download=download, sorting_mode='rules_first')
    def forbidden(*args, **kwargs):
        pytest.fail('Rules-first matches must retain the profiling fast path')
    monkeypatch.setattr(instance.extractor_registry, 'extract_metadata', forbidden)
    monkeypatch.setattr(instance.origin_detector, 'detect_origin', forbidden)
    if download:
        proposal = instance.analyze_download(str(source))
        assert proposal.is_rule_override and proposal.relative_target == 'Documents/opaque.md'
    else:
        assert instance.plan(str(tmp_path), [str(source)]).items[0].rule_name == 'Documents'


@pytest.mark.parametrize('kind,rule_folder,intelligent_folder', CASES)
def test_intelligence_directory_moves_use_content_and_preserve_saved_rules(tmp_path, kind, rule_folder, intelligent_folder):
    source = mode_sample(tmp_path, kind)
    original = source.read_bytes()
    instance, config = make_mode_organizer(tmp_path, sorting_mode='intelligence')
    before = copy.deepcopy(config.data)
    manager_before = [rule.to_dict() for rule in instance.rule_manager.rules]
    plan = instance.plan(str(tmp_path), [str(source)])
    item, = plan.items
    assert item.target_path == str(tmp_path / intelligent_folder / source.name)
    assert item.rule_name == 'Intelligence' and item.evidence
    assert config.data == before and [rule.to_dict() for rule in instance.rule_manager.rules] == manager_before
    result = instance.execute(plan)
    record, = result.records
    assert result.success_count == 1 and result.error_count == 0
    assert record.status is OperationStatus.VERIFIED_AND_MOVED
    assert not source.exists() and Path(record.target).read_bytes() == original
    assert record.hash == hashlib.sha256(original).hexdigest()
    report = Path(instance.generate_report(str(tmp_path), result)).read_text()
    assert intelligent_folder in report and '**Evidence:**' in report
    assert config.data == before and [rule.to_dict() for rule in instance.rule_manager.rules] == manager_before


@pytest.mark.parametrize('kind,rule_folder,intelligent_folder', CASES)
def test_intelligence_download_analysis_and_safe_transfer_agree(tmp_path, kind, rule_folder, intelligent_folder):
    source = mode_sample(tmp_path, kind)
    original = source.read_bytes()
    instance, config = make_mode_organizer(tmp_path, download=True, sorting_mode='intelligence')
    rules_before = copy.deepcopy(config.data['rules'])
    proposal = instance.analyze_download(str(source))
    assert proposal.relative_target == str(Path(intelligent_folder) / source.name)
    assert not proposal.is_rule_override and proposal.evidence
    assert source.read_bytes() == original
    status, final = instance.process_file(str(source))
    assert status == 'SUCCESS' and final == proposal.target_path
    assert Path(final).read_bytes() == original and not source.exists()
    assert config.data['rules'] == rules_before


@pytest.mark.parametrize('mode', ['rules_first', 'intelligence'])
def test_download_freezes_sorting_policy_for_each_request(tmp_path, monkeypatch, mode):
    source = mode_sample(tmp_path, 'invoice')
    instance, config = make_mode_organizer(tmp_path, download=True, sorting_mode=mode)
    opposite = 'intelligence' if mode == 'rules_first' else 'rules_first'
    original_category = instance.get_category
    def change_after_category(path):
        category = original_category(path)
        config.data['sorting_mode'] = opposite
        return category
    monkeypatch.setattr(instance, 'get_category', change_after_category)
    status, target = instance.process_file(str(source))
    first_folder = 'Documents' if mode == 'rules_first' else 'Work/Invoices'
    assert status == 'SUCCESS' and target == str(tmp_path / 'sorted' / first_folder / 'opaque.md')
    monkeypatch.setattr(instance, 'get_category', original_category)
    source.write_text('# Invoice\nFinance billing invoice new request')
    status, target = instance.process_file(str(source))
    next_folder = 'Documents' if opposite == 'rules_first' else 'Work/Invoices'
    assert status == 'SUCCESS' and target == str(tmp_path / 'sorted' / next_folder / 'opaque.md')
    assert len(instance.rule_manager.rules) == 2


def test_directory_mode_snapshot_is_consistent_across_batch(tmp_path, monkeypatch):
    sources = [tmp_path / 'one.md', tmp_path / 'two.md']
    for source in sources:
        source.write_text('# Invoice\nFinance billing invoice')
    instance, config = make_mode_organizer(tmp_path, sorting_mode='intelligence')
    extract = instance.extractor_registry.extract_metadata
    def change_mode_after_extract(path):
        result = extract(path)
        config.data['sorting_mode'] = 'rules_first'
        return result
    monkeypatch.setattr(instance.extractor_registry, 'extract_metadata', change_mode_after_extract)
    plan = instance.plan(str(tmp_path), [str(source) for source in sources])
    assert len(plan.items) == 2
    assert all(item.target_path == str(tmp_path / 'Work/Invoices' / Path(item.source_path).name) for item in plan.items)
    assert all(item.rule_name == 'Intelligence' for item in plan.items)
    # Switching back reuses the untouched saved rules on the next plan.
    next_plan = instance.plan(str(tmp_path), [str(source) for source in sources])
    assert all(item.rule_name == 'Documents' for item in next_plan.items)


@pytest.mark.parametrize('download', [False, True], ids=['directory', 'download'])
def test_intelligence_unknown_input_does_not_silently_apply_saved_catchall(tmp_path, download):
    source = tmp_path / 'opaque.bin'
    source.write_bytes(b'\x00\xff\x00\xfe')
    catchall = dict(id='pinned', name='Pinned', enabled=True, priority=1, conditions=[], destination='Pinned')
    instance, config = make_mode_organizer(tmp_path, download=download, sorting_mode='intelligence', rules=[catchall])
    if download:
        proposal = instance.analyze_download(str(source))
        assert proposal.relative_target == 'Others/opaque.bin'
        assert proposal.confidence_level is ConfidenceLevel.UNKNOWN and not proposal.is_rule_override
    else:
        item, = instance.plan(str(tmp_path), [str(source)]).items
        assert item.target_path == str(tmp_path / 'Others/opaque.bin') and item.confidence == 'UNKNOWN'
    assert config.data['rules'] == [catchall] and source.exists()


def test_sorting_mode_defaults_and_saved_choices_roundtrip(tmp_path):
    path = tmp_path / 'preferences.json'
    config = ConfigManager(config_path=path)
    assert config.get('sorting_mode') == 'rules_first'
    saved_rules = copy.deepcopy(config.get('rules'))
    for mode in ('intelligence', 'rules_first'):
        config.set('sorting_mode', mode)
        loaded = ConfigManager(config_path=path)
        assert loaded.get('sorting_mode') == mode and loaded.get('rules') == saved_rules
    legacy = json.loads(path.read_text())
    legacy.pop('sorting_mode')
    path.write_text(json.dumps(legacy))
    loaded = ConfigManager(config_path=path)
    assert loaded.get('sorting_mode') == 'rules_first' and loaded.get('rules') == saved_rules


@pytest.mark.parametrize('invalid', [None, True, False, 1, [], {}, '', 'intelligence_first', 'unknown'])
def test_invalid_sorting_mode_preserves_saved_configuration(tmp_path, invalid):
    config = ConfigManager(config_path=tmp_path / 'preferences.json')
    before = config.config_path.read_bytes()
    rules_before = copy.deepcopy(config.get('rules'))
    with pytest.raises(ValueError):
        config.set('sorting_mode', invalid)
    assert config.config_path.read_bytes() == before
    assert config.get('sorting_mode') == 'rules_first' and config.get('rules') == rules_before

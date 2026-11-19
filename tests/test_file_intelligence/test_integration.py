"""Phase 18: synthetic file formats through profiling, planning and safe transfers.

These fixtures contain no personal files. They use real extractors/classifiers,
real SQLite caching and real SHA-256-verified transfers; only machine boundaries
(home/XDG discovery, origin xattrs and network availability) are controlled.
"""

import hashlib
import json
import sqlite3
import subprocess
import sys
import wave
import os
from html import escape
from pathlib import Path
import socket
import zipfile

import pytest

from src.organizer import FileOrganizer
from src.core.directory_organizer import DirectoryOrganizer, OperationStatus
from src.core.file_intelligence import ConfidenceLevel
from src.core.file_intelligence.metadata import FileMetadataExtractor


class IntegrationConfig:
    def __init__(self, **changes):
        self.data = dict(rules=[], enable_origin_detection=True,
                         enable_deep_content_extraction=True,
                         enable_duplicate_detection=True, conflict_resolution='rename',
                         smart_filename_cleanup=False, enable_notifications=False)
        self.data.update(changes)

    def get(self, key, default=None):
        return self.data.get(key, default)


class IntegrationLogger:
    def warning(self, *args): pass
    def info(self, *args): pass
    def debug(self, *args): pass
    def error(self, *args): pass
    def log_action(self, *args): pass


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home)
    for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                      ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
        monkeypatch.setenv(key, str(tmp_path / name))
    monkeypatch.setattr(FileMetadataExtractor, 'read_xattr', staticmethod(lambda *args: None))
    def no_network(*args, **kwargs):
        raise AssertionError('Integration scenarios must stay offline')
    monkeypatch.setattr(socket, 'socket', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)


def is_within(path, root):
    return os.path.commonpath([str(path), str(root)]) == str(root)


def make_organizer(**changes):
    return DirectoryOrganizer(IntegrationConfig(**changes), IntegrationLogger())


def write_pdf(path, title, body):
    def literal(text):
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream = ('BT /F1 12 Tf 30 100 Td (' + literal(body) + ') Tj ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
               ('<< /Title (' + literal(title) + ') >>').encode('ascii')]
    data = b'%PDF-1.4\n'
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 7\n0000000000 65535 f \n'
    for offset in offsets:
        data += f'{offset:010} 00000 n \n'.encode()
    data += b'trailer\n<< /Size 7 /Root 1 0 R /Info 6 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'
    path.write_bytes(data)
    return path


def write_archive(path, members):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name, value in members.items():
            package.writestr(name, value)
    return path


def write_office(path, kind, title, body):
    core = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(title) + '</dc:title></cp:coreProperties>')
    parts = {'docProps/core.xml': core}
    if kind == 'docx':
        parts['word/document.xml'] = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>' + escape(body) + '</w:t></w:r></w:p></w:body></w:document>')
    elif kind == 'pptx':
        parts['ppt/slides/slide1.xml'] = ('<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp>'
            '<p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>'
            + escape(title) + '</a:t></a:r></a:p><a:p><a:r><a:t>' + escape(body) +
            '</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    else:
        raise ValueError(kind)
    return write_archive(path, parts)


def origin_xattr(monkeypatch, root, url):
    def read(path, attribute):
        if attribute == 'user.xdg.origin.url' and is_within(Path(path), root):
            return url
        return None
    monkeypatch.setattr(FileMetadataExtractor, 'read_xattr', staticmethod(read))


def plan_directory(instance, root, recursive=False):
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    plan = instance.plan(str(root), instance.scan(str(root), recursive=recursive))
    assert {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    assert plan.total_files == len(plan.items)
    assert all(is_within(Path(item.source_path), root) and is_within(Path(item.target_path), root)
               for item in plan.items)
    return plan


def execute_and_verify(instance, root, plan):
    original = {item.source_path: Path(item.source_path).read_bytes() for item in plan.items}
    result = instance.execute(plan)
    assert result.success_count == len(plan.items)
    assert result.error_count == result.collision_count == result.duplicate_count == result.skip_count == 0
    assert not result.cancelled
    by_source = {item.source_path: item for item in plan.items}
    for record in result.records:
        item = by_source[record.source]
        assert record.status is OperationStatus.VERIFIED_AND_MOVED
        assert not Path(record.source).exists()
        assert is_within(Path(record.target), root)
        assert Path(record.target).read_bytes() == original[record.source]
        assert record.hash == hashlib.sha256(original[record.source]).hexdigest()
        assert record.size == len(original[record.source])
        assert record.confidence == item.confidence and record.evidence == item.evidence
        assert record.cluster_id == item.cluster_id and record.cluster_name == item.cluster_name
    report_path = Path(instance.generate_report(str(root), result))
    assert report_path.parent == root
    report = report_path.read_text()
    assert '**Confidence:**' in report and '**Evidence:**' in report and 'file:///' in report
    assert all(record.hash in report for record in result.records)
    return result


def test_academic_course_organization_end_to_end(tmp_path, monkeypatch):
    root = tmp_path / 'College'
    root.mkdir()
    write_pdf(root / 'Lecture_1_DBMS.pdf', 'DBMS Database Lecture', 'Database course lecture normalization')
    write_office(root / 'Lecture_2_DBMS.pptx', 'pptx', 'DBMS Database Lecture', 'Database lecture course notes')
    write_archive(root / 'Lecture_3_DBMS.zip', {'Lecture_1_DBMS.pdf': 'stub', 'Lecture_2_DBMS.pptx': 'stub'})
    origin_xattr(monkeypatch, root, 'https://user:SECRET@canvas.example.edu/courses/DBMS?token=SECRET')
    instance = make_organizer()
    plan = plan_directory(instance, root)
    assert plan.total_files == 3 and plan.cluster_count == 1 and not plan.warnings
    assert {Path(item.target_path).relative_to(root).parent.as_posix() for item in plan.items} == {'College/DBMS/Lectures'}
    assert all(item.confidence == ConfidenceLevel.CONFIRMED.value for item in plan.items)
    assert all('SECRET' not in str(item.evidence) for item in plan.items)
    assert any('origin' in reason.lower() for item in plan.items for reason in item.evidence)
    execute_and_verify(instance, root, plan)


def test_software_project_kept_intact_end_to_end(tmp_path, monkeypatch):
    root = tmp_path / 'Projects'
    root.mkdir()
    (root / 'Makefile').write_text('all:\n\tpython SmartSort_Source.py\n')
    (root / 'SmartSort_Source.py').write_text('"""SmartSort source project repository."""\ndef main():\n    return 0\n')
    (root / 'SmartSort_Source.c').write_text('/* SmartSort source project repository. */\nint main(void) { return 0; }\n')
    (root / 'SmartSort_Readme.md').write_text('# SmartSort Documentation\nProject repository source: Makefile SmartSort_Source.py SmartSort_Source.c\n')
    origin_xattr(monkeypatch, root, 'https://github.com/example/SmartSort?token=SECRET')
    original = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
    instance = make_organizer()
    plan = plan_directory(instance, root)
    # Makefile and its source/readme dependencies form one project. Moving
    # individual files would break its relative build and documentation paths.
    assert plan.total_files == 0 and not plan.items
    assert any('intact' in warning for warning in plan.warnings)
    result = instance.execute(plan)
    assert not result.records and result.error_count == 0
    assert {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()} == original
    assert not (root / 'Projects').exists()


def test_cybersecurity_toolkit_organization_end_to_end(tmp_path):
    root = tmp_path / 'Cybersecurity'
    root.mkdir()
    (root / 'nmap_scan.xml').write_text('<nmaprun><scaninfo type="syn"/><host><status state="up"/></host></nmaprun>')
    (root / 'rockyou_subset.txt').write_text('Security wordlist\npassword\nletmein\nexample-only\n')
    (root / 'exploit.py').write_text('"""Security exploit pentest vulnerability demonstration."""\ndef exploit():\n    return "synthetic"\n')
    instance = make_organizer()
    plan = plan_directory(instance, root)
    destinations = {Path(item.source_path).name: Path(item.target_path).relative_to(root).as_posix() for item in plan.items}
    assert destinations == {'nmap_scan.xml': 'Cybersecurity/Reports/nmap_scan.xml',
                            'rockyou_subset.txt': 'Cybersecurity/Wordlists/rockyou_subset.txt',
                            'exploit.py': 'Cybersecurity/Exploits/exploit.py'}
    execute_and_verify(instance, root, plan)


def test_work_finance_organization_end_to_end(tmp_path):
    root = tmp_path / 'Work'
    root.mkdir()
    write_pdf(root / 'Invoice_August_2026.pdf', 'Invoice August 2026', 'Invoice billing finance total due')
    write_office(root / 'Contract.docx', 'docx', 'Contract Agreement', 'Contract agreement NDA legal work')
    instance = make_organizer()
    plan = plan_directory(instance, root)
    assert plan.total_files == 2 and not plan.warnings
    assert {Path(item.target_path).relative_to(root).as_posix() for item in plan.items} == {
        'Work/Invoices/Invoice_August_2026.pdf', 'Work/Contracts/Contract.docx'}
    execute_and_verify(instance, root, plan)


def test_ambiguous_file_fallback_end_to_end(tmp_path):
    root = tmp_path / 'Unsorted'
    root.mkdir()
    write_archive(root / 'random.zip', {})
    instance = make_organizer()
    plan = plan_directory(instance, root)
    item, = plan.items
    assert item.confidence == ConfidenceLevel.UNKNOWN.value
    assert item.target_path == str(root / 'Archives' / 'random.zip')
    assert item.rule_name == 'Intelligence'
    execute_and_verify(instance, root, plan)


def test_duplicate_and_collision_intelligence_safety(tmp_path):
    root = tmp_path / 'Unsorted'
    root.mkdir()
    sources = []
    for name, text in [('one', '# Invoice\nFinance billing'), ('two', '# Invoice\nFinance billing'),
                       ('three', '# Invoice\nFinance billing different content')]:
        folder = root / name
        folder.mkdir()
        source = folder / 'invoice.md'
        source.write_text(text)
        sources.append(source)
    original = {str(source): source.read_bytes() for source in sources}
    instance = make_organizer()
    plan = plan_directory(instance, root, recursive=True)
    assert plan.total_files == 3
    assert {item.target_path for item in plan.items} == {str(root / 'Work/Invoices/invoice.md')}
    result = instance.execute(plan)
    assert (result.success_count, result.duplicate_count, result.collision_count, result.error_count) == (1, 1, 1, 0)
    assert len({r.target for r in result.records if r.status is not OperationStatus.DUPLICATE}) == 2
    for record in result.records:
        assert is_within(Path(record.target), root)
        assert Path(record.target).read_bytes() == original[record.source]
        assert record.hash == hashlib.sha256(original[record.source]).hexdigest()
        assert not Path(record.source).exists()
    report = Path(instance.generate_report(str(root), result)).read_text()
    assert 'DUPLICATE' in report and 'COLLISION_RESOLVED' in report
    assert '[Open Existing Destination]' in report and 'file:///' in report


# Download APIs, cache policy and process boundaries.

class DownloadScenarioConfig:
    def __init__(self, root, **overrides):
        self.data = dict(rules=[], destination_base=str(root / 'sorted'),
                         enable_origin_detection=False, enable_notifications=False,
                         smart_filename_cleanup=False, enable_duplicate_detection=True,
                         conflict_resolution='rename', large_file_threshold_gb=2.5)
        self.data.update(overrides)

    def get(self, key, default=None):
        return self.data.get(key, default)


class DownloadScenarioLogger:
    def info(self, *args): pass
    def warning(self, *args): pass
    def error(self, *args): pass
    def log_action(self, *args): pass
    def debug(self, *args): pass


def download_scenario_file(root, kind):
    if kind == 'college':
        path = root / 'Lecture_DBMS.md'
        path.write_text('# DBMS Lecture\nCollege database course lecture notes')
    elif kind == 'project':
        path = root / 'SmartSort_Source.py'
        path.write_text('import pathlib\ndef main():\n    return pathlib.Path(".")\n')
    elif kind == 'cybersecurity':
        path = root / 'nmap_scan.xml'
        path.write_text('<nmaprun><scaninfo type="syn"/><host><status state="up"/></host></nmaprun>')
    elif kind == 'work':
        path = root / 'Invoice_August_2026.md'
        path.write_text('# Invoice\nBilling finance invoice August 2026')
    elif kind == 'media':
        path = root / 'podcast.wav'
        with wave.open(str(path), 'wb') as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(8000)
            sound.writeframes(b'\0\0' * 80)
    elif kind == 'archives':
        path = root / 'backup_archive.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('records.dat', b'opaque data')
    else:
        path = root / 'opaque.bin'
        path.write_bytes(b'\x00\xff\x00\xfe')
    return path


@pytest.mark.parametrize('kind,domain,folder', [
    ('college', 'College', 'College/DBMS/Lectures'),
    ('project', 'Projects', 'Projects/SmartSort/Source'),
    ('cybersecurity', 'Cybersecurity', 'Cybersecurity/Reports'),
    ('work', 'Work', 'Work/Invoices'),
    ('media', 'Media', 'Media/Audio'),
    ('archives', 'Archives', 'Archives'),
    ('unknown', 'Others', 'Others'),
])
def test_download_domain_profile_and_verified_transfer(tmp_path, kind, domain, folder):
    source = download_scenario_file(tmp_path, kind)
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    organizer = FileOrganizer(DownloadScenarioConfig(tmp_path), DownloadScenarioLogger())
    proposal = organizer.analyze_download(str(source))
    assert proposal.domain == domain
    assert proposal.relative_target == str(Path(folder) / source.name)
    assert source.read_bytes() == original and not (tmp_path / 'sorted').exists()
    status, final_path = organizer.process_file(str(source))
    assert status == 'SUCCESS'
    target = Path(final_path)
    assert target == Path(proposal.target_path)
    assert is_within(target, tmp_path / 'sorted')
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert not source.exists()


def test_real_chromium_origin_survives_cache_and_transfer(tmp_path):
    source = tmp_path / 'Lecture_DBMS.md'
    source.write_text('# DBMS Lecture\nDatabase course lecture notes')
    original = source.read_bytes()
    stamp = source.stat().st_mtime
    history = tmp_path / 'config' / 'google-chrome' / 'Default' / 'History'
    history.parent.mkdir(parents=True)
    with sqlite3.connect(history) as database:
        database.executescript('''
            CREATE TABLE downloads (id INTEGER PRIMARY KEY, target_path TEXT,
                start_time INTEGER, end_time INTEGER, total_bytes INTEGER,
                state INTEGER, tab_url TEXT, tab_referrer_url TEXT);
            CREATE TABLE downloads_url_chains (id INTEGER, chain_index INTEGER, url TEXT);
        ''')
        moment = int((stamp + 11644473600) * 1000000)
        database.execute('INSERT INTO downloads VALUES (1,?,?,?,?,?,?,?)',
                         (str(source), moment, moment, len(original), 1, '', ''))
        database.execute('INSERT INTO downloads_url_chains VALUES (1,0,?)',
                         ('https://user:SECRET@canvas.example.edu/course?token=SECRET#SECRET',))
    history_digest = hashlib.sha256(history.read_bytes()).hexdigest()
    config = DownloadScenarioConfig(tmp_path, enable_origin_detection=True)
    organizer = FileOrganizer(config, DownloadScenarioLogger())
    first = organizer.analyze_download(str(source))
    second = organizer.analyze_download(str(source))
    assert first.to_dict() == second.to_dict()
    assert first.domain == 'College' and first.confidence_level is ConfidenceLevel.CONFIRMED
    assert any(item.source_field.startswith('origin.') for item in first.evidence)
    assert 'SECRET' not in json.dumps(first.to_dict())
    assert hashlib.sha256(history.read_bytes()).hexdigest() == history_digest
    status, target = organizer.process_file(str(source))
    assert status == 'SUCCESS' and Path(target).read_bytes() == original and not source.exists()
    cache = tmp_path / 'cache' / 'smartsort' / 'metadata_cache.db'
    with sqlite3.connect(cache) as database:
        payloads = '\n'.join(row[0] for row in database.execute('SELECT metadata_json FROM file_metadata_cache'))
    assert 'SECRET' not in payloads


def test_warm_cache_cannot_override_changed_download_rule(tmp_path):
    source = tmp_path / 'invoice.md'
    source.write_text('# Invoice\nFinance billing invoice')
    config = DownloadScenarioConfig(tmp_path)
    first = FileOrganizer(config, DownloadScenarioLogger()).analyze_download(str(source))
    assert first.relative_target == 'Work/Invoices/invoice.md'
    config.data['rules'] = [{'name': 'Pinned Policy', 'priority': 1, 'enabled': True,
                             'conditions': [], 'destination': 'Pinned/{extension}'}]
    organizer = FileOrganizer(config, DownloadScenarioLogger())
    changed = organizer.analyze_download(str(source))
    assert changed.is_rule_override and changed.relative_target == 'Pinned/MD/invoice.md'
    assert changed.confidence_level is ConfidenceLevel.CONFIRMED
    assert organizer.process_file(str(source))[0] == 'SUCCESS'
    assert Path(changed.target_path).read_text() == '# Invoice\nFinance billing invoice'


def test_content_opt_out_ignores_previously_cached_document_title(tmp_path):
    source = tmp_path / 'opaque.md'
    source.write_text('# Invoice\nFinance billing invoice')
    enabled = FileOrganizer(DownloadScenarioConfig(tmp_path), DownloadScenarioLogger())
    assert enabled.analyze_download(str(source)).domain == 'Work'
    disabled = FileOrganizer(DownloadScenarioConfig(tmp_path, enable_deep_content_extraction=False), DownloadScenarioLogger())
    proposal = disabled.analyze_download(str(source))
    assert proposal.domain == 'Documents' and proposal.confidence_level is ConfidenceLevel.UNKNOWN
    assert not any(item.source_field.startswith('metadata.') for item in proposal.evidence)
    assert source.exists()


def test_malformed_document_does_not_abort_healthy_batch(tmp_path):
    root = tmp_path / 'input'
    root.mkdir()
    bad = root / 'broken.docx'
    bad.write_bytes(b'not an OOXML ZIP')
    healthy = root / 'invoice.md'
    healthy.write_text('# Invoice\nFinance billing invoice')
    organizer = DirectoryOrganizer(DownloadScenarioConfig(tmp_path), DownloadScenarioLogger())
    plan = organizer.plan(str(root), organizer.scan(str(root)))
    assert plan.total_files == 2
    bad_item = next(item for item in plan.items if item.source_path == str(bad))
    assert bad_item.confidence == 'UNKNOWN' and bad_item.category == 'Documents'
    assert plan.warnings
    original = {item.source_path: Path(item.source_path).read_bytes() for item in plan.items}
    result = organizer.execute(plan)
    assert result.success_count == 2 and result.error_count == 0
    for record in result.records:
        assert record.status is OperationStatus.VERIFIED_AND_MOVED
        assert Path(record.target).read_bytes() == original[record.source]
        assert is_within(Path(record.target), root)
        assert not Path(record.source).exists()
    report = Path(organizer.generate_report(str(root), result)).read_text()
    assert 'UNKNOWN' in report and 'broken.docx' in report and 'Work/Invoices' in report


def test_unreadable_file_preserved_while_healthy_batch_moves(tmp_path, monkeypatch):
    root = tmp_path / 'input'
    root.mkdir()
    unreadable = root / 'invoice_unreadable.md'
    unreadable.write_text('# Invoice\nFinance billing invoice')
    healthy = root / 'invoice_healthy.md'
    healthy.write_text('# Invoice\nFinance billing invoice')
    organizer = DirectoryOrganizer(DownloadScenarioConfig(tmp_path), DownloadScenarioLogger())
    plan = organizer.plan(str(root), organizer.scan(str(root)))
    original_access = os.access
    monkeypatch.setattr(os, 'access', lambda path, mode, *a, **k: False if str(path) == str(unreadable) else original_access(path, mode, *a, **k))
    result = organizer.execute(plan)
    assert result.error_count == 1 and result.success_count == 1
    assert unreadable.exists() and not healthy.exists()
    bad_record = next(record for record in result.records if record.source == str(unreadable))
    assert bad_record.status is OperationStatus.FAILED
    assert not Path(bad_record.target).exists()


def test_file_intelligence_import_and_batch_have_no_qt_requirement(tmp_path):
    source = tmp_path / 'invoice.md'
    source.write_text('# Invoice\nFinance billing invoice')
    code = '''
import importlib.abc, sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('PyQt6', 'PySide6', 'PyQt5', 'PySide2'):
            raise AssertionError('Qt imported by intelligence/core')
sys.meta_path.insert(0, NoQt())
from src.core.directory_organizer import DirectoryOrganizer
class Config:
    def get(self, key, default=None):
        return {'rules': [], 'enable_origin_detection': False}.get(key, default)
class Logger:
    def warning(self, *args): pass
instance=DirectoryOrganizer(Config(), Logger())
summary=instance.preview(sys.argv[1])
assert summary.total_files == 1 and summary.category_counts == {'Work': 1}
assert not any(name.startswith(('PyQt', 'PySide')) for name in sys.modules)
'''
    completed = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path)],
                               capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr


def test_mixed_domains_keep_exact_routes_and_cached_review(tmp_path):
    root = tmp_path / 'Unsorted'
    root.mkdir()
    expected_folders = {
        'college': 'College/DBMS/Lectures', 'project': 'Projects/SmartSort/Source',
        'cybersecurity': 'Cybersecurity/Reports', 'work': 'Work/Invoices',
        'media': 'Media/Audio', 'archives': 'Archives', 'unknown': 'Others',
    }
    expected = {}
    for kind, folder in expected_folders.items():
        source = download_scenario_file(root, kind)
        expected[str(source)] = str(root / folder / source.name)
    instance = make_organizer(enable_origin_detection=False)
    cold = plan_directory(instance, root)
    warm = plan_directory(instance, root)
    assert cold.items == warm.items
    assert {item.source_path: item.target_path for item in cold.items} == expected
    assert len(cold.items) == len(expected)
    execute_and_verify(instance, root, warm)


# Phase 17 cache regressions: cold and warm metadata must share privacy semantics.
# The values below are synthetic sentinels, never real credentials.
def _cache_regression_input(tmp_path):
    root = tmp_path / 'cache-regression-batch'
    root.mkdir()
    source = root / 'opaque.md'
    source.write_text(
        '# https://example.com/a?invoice=UncommonPrivateToken987\n'
        'repository backend frontend source code', encoding='utf-8')
    return root, source


def test_unchanged_url_metadata_keeps_identical_cold_and_warm_plan(tmp_path):
    root, source = _cache_regression_input(tmp_path)
    instance = make_organizer(enable_origin_detection=False)
    cold = instance.preview(str(root))
    warm = instance.preview(str(root))
    assert source.read_text(encoding='utf-8').startswith('# https://example.com/a?invoice=')
    assert cold == warm


def test_url_query_private_tokens_are_absent_from_persistent_metadata(tmp_path):
    import sqlite3
    from src.core.file_intelligence.extractors import ExtractorRegistry
    from src.utils.paths import AppPaths

    _, source = _cache_regression_input(tmp_path)
    extracted = ExtractorRegistry().extract_metadata(str(source))
    assert extracted.extraction_status == 'SUCCESS'
    database_path = AppPaths.cache_dir() / 'metadata_cache.db'
    assert database_path.is_file()
    with sqlite3.connect(str(database_path)) as database:
        rows = database.execute(
            'SELECT metadata_json FROM file_metadata_cache WHERE file_path=?',
            (str(source),)).fetchall()
    assert rows
    serialized = '\n'.join(row[0] for row in rows).casefold()
    assert 'uncommonprivatetoken' not in serialized

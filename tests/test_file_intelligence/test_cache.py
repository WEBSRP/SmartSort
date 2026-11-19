"""Phase 17: disposable persistence, invalidation, privacy and integration."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

from src.core.file_intelligence import MetadataCache, ExtractedMetadata, OriginInfo
from src.core.file_intelligence.extractors import ExtractorRegistry
from src.core.file_intelligence.origin import OriginDetector


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg'))


@pytest.fixture
def cache(tmp_path):
    with MetadataCache(tmp_path / 'cache.db') as instance:
        yield instance


def metadata(**changes):
    values = dict(title='DBMS Lecture', keywords=['database'], headings=['Normalization'],
                  dimensions=(640, 480), duration_seconds=2.5,
                  exif_tags={'Make': 'Camera'}, extractor_name='test', extraction_status='SUCCESS')
    values.update(changes)
    return ExtractedMetadata(**values)


def put(cache, path='sample.pdf', **identity):
    cache.put(path, 10, 2, 123.5, 500, metadata(), **identity)


def get(cache, path='sample.pdf', **identity):
    return cache.get(path, 10, 123.5, 500, **identity)


def test_roundtrip_restart_and_independent_objects(cache):
    put(cache)
    restored = get(cache)
    assert restored.to_dict() == metadata().to_dict()
    restored.keywords.append('mutation')
    assert get(cache).keywords == ['database']
    path = cache.db_path
    cache.close()
    with MetadataCache(path) as reopened:
        assert get(reopened).dimensions == (640, 480)
        assert get(reopened).duration_seconds == 2.5


def test_default_path_and_private_permissions(tmp_path):
    with MetadataCache() as cache:
        assert Path(cache.db_path) == tmp_path / 'xdg' / 'smartsort' / 'metadata_cache.db'
        assert Path(cache.db_path).stat().st_mode & 0o777 == 0o600
        assert cache._connection is not None


@pytest.mark.parametrize('changes', [dict(inode=11), dict(mtime=124), dict(size_bytes=501),
                                    dict(device=3), dict(mtime_ns=9), dict(ctime_ns=9)])
def test_composite_identity_invalidation(cache, changes):
    put(cache, mtime_ns=5, ctime_ns=6)
    args = dict(file_path='sample.pdf', inode=10, mtime=123.5, size_bytes=500,
                device=2, mtime_ns=5, ctime_ns=6)
    args.update(changes)
    assert cache.get(**args) is None
    assert get(cache, device=2, mtime_ns=5, ctime_ns=6) is not None


def test_namespaces_and_path_are_independent(cache):
    put(cache, namespace='one')
    assert get(cache, namespace='two') is None
    assert get(cache, path='other.pdf', namespace='one') is None
    put(cache, namespace='two')
    assert get(cache, namespace='one') is not None
    assert get(cache, namespace='two') is not None


def test_unicode_and_sql_characters(cache):
    path = "résumé '); DROP TABLE file_metadata_cache; --.md"
    put(cache, path)
    assert get(cache, path).title == 'DBMS Lecture'
    assert cache._connection.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0] == 1


def test_clear_removes_metadata_and_origin(cache):
    put(cache)
    cache.put_origin('sample.pdf', 10, 2, 123.5, 500, OriginInfo(url='https://example.com/a'), provenance_key='browser')
    cache.clear()
    assert get(cache) is None
    assert cache.get_origin('sample.pdf', 10, 123.5, 500, provenance_key='browser') is None


@pytest.mark.parametrize('status', ['FAILED', 'PARTIAL', 'TIMEOUT', 'UNSUPPORTED', 'PENDING'])
def test_unsuccessful_extraction_not_persisted(cache, status):
    cache.put('sample.pdf', 10, 2, 123.5, 500, metadata(extraction_status=status))
    assert get(cache) is None


def test_age_expiration_and_startup_pruning(cache):
    put(cache)
    cache._connection.execute('UPDATE file_metadata_cache SET created_at=?', (time.time()-31*86400,))
    cache._connection.commit()
    assert get(cache) is None
    with MetadataCache(cache.db_path) as reopened:
        assert reopened._connection.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0] == 0


def test_bounded_entries_and_replacement(cache, monkeypatch):
    monkeypatch.setattr(cache, 'MAX_ENTRIES', 3)
    for index in range(6):
        put(cache, f'{index}.pdf')
    assert cache._connection.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0] == 3
    assert get(cache, '0.pdf') is None and get(cache, '5.pdf') is not None
    cache.put('5.pdf', 20, 2, 130, 20, metadata())
    assert get(cache, '5.pdf') is None
    assert cache._connection.execute('SELECT count(*) FROM file_metadata_cache WHERE file_path=?',
                                     (os.path.abspath('5.pdf'),)).fetchone()[0] == 1


def test_corrupt_file_rebuilt(tmp_path):
    path = tmp_path / 'broken.db'
    path.write_bytes(b'this is not a SQLite database')
    with MetadataCache(path) as cache:
        put(cache)
        assert get(cache).title == 'DBMS Lecture'


@pytest.mark.parametrize('payload', ['{invalid', '[]', '{"title":3}',
                                     json.dumps(dict(metadata().to_dict(), keywords=[42])),
                                     json.dumps(dict(metadata().to_dict(), dimensions=[1])),
                                     json.dumps(dict(metadata().to_dict(), duration_seconds='bad'))])
def test_invalid_payload_is_a_miss(cache, payload):
    put(cache)
    cache._connection.execute('UPDATE file_metadata_cache SET metadata_json=?', (payload,))
    cache._connection.commit()
    assert get(cache) is None


def test_oversized_payload_not_written(cache):
    cache.put('sample.pdf', 10, 2, 123.5, 500, metadata(text_preview='x' * (cache.MAX_PAYLOAD_BYTES+1)))
    assert get(cache) is None


def test_unavailable_cache_path_is_nonfatal(tmp_path):
    blocked = tmp_path / 'file'
    blocked.write_text('not a directory')
    with MetadataCache(blocked / 'cache.db') as cache:
        put(cache)
        assert get(cache) is None
        cache.clear()


def test_symlink_cache_does_not_touch_target(tmp_path):
    victim = tmp_path / 'victim'
    victim.write_text('preserve')
    link = tmp_path / 'cache.db'
    link.symlink_to(victim)
    with MetadataCache(link) as cache:
        put(cache)
        assert get(cache) is None
    assert victim.read_text() == 'preserve'


def test_locked_cache_is_a_miss_and_does_not_delete_database(cache):
    put(cache)
    other = sqlite3.connect(cache.db_path, timeout=.01)
    try:
        other.execute('BEGIN IMMEDIATE')
        cache.put('new.pdf', 10, 2, 123.5, 500, metadata())
        assert get(cache, 'new.pdf') is None
    finally:
        other.rollback()
        other.close()
    assert get(cache) is not None


def test_private_fields_redacted_before_disk_write(cache):
    original = metadata(title='https://user:password@example.com/doc?token=SECRET#fragment',
                        text_preview='See https://example.com/a;session=SECRET?auth=SECRET',
                        exif_tags={'Make': 'Camera', 'GPSInfo': 'PRIVATE_COORDINATES', 'GPSLatitude': 'PRIVATE_COORDINATES'})
    cache.put('sample.pdf', 10, 2, 123.5, 500, original)
    restored = get(cache)
    assert restored.title == 'https://example.com/doc'
    assert restored.exif_tags == {'Make': 'Camera'}
    assert restored.text_preview == 'See https://example.com/a'
    assert 'SECRET' in original.title and 'GPSInfo' in original.exif_tags
    cache.close()
    raw = Path(cache.db_path).read_bytes()
    assert all(secret not in raw for secret in (b'SECRET', b'password', b'PRIVATE_COORDINATES'))


def test_origin_cache_redaction_and_provenance_key(cache):
    cache.put_origin('sample.pdf', 10, 2, 123.5, 500,
                     OriginInfo(url='https://user:SECRET@example.com/a?token=SECRET', evidence_detail='Read xattr'),
                     provenance_key='browser-state-one')
    restored = cache.get_origin('sample.pdf', 10, 123.5, 500, provenance_key='browser-state-one')
    assert restored.url == 'https://example.com/a' and restored.domain == 'example.com'
    assert cache.get_origin('sample.pdf', 10, 123.5, 500, provenance_key='browser-state-two') is None


def test_shared_connection_thread_safety(cache):
    def work(index):
        path = f'{index}.pdf'
        put(cache, path)
        return get(cache, path).title
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(work, range(80))) == ['DBMS Lecture'] * 80


def test_independent_connections_can_read_each_others_writes(cache):
    with MetadataCache(cache.db_path) as other:
        put(cache)
        assert get(other).title == 'DBMS Lecture'
        other.clear()
        assert get(cache) is None


def test_close_is_idempotent_and_operations_become_misses(cache):
    cache.close()
    cache.close()
    put(cache)
    cache.clear()
    assert get(cache) is None


def test_registry_hit_skips_dispatch_and_survives_restart(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# DBMS Lecture\nDatabase lecture')
    registry = ExtractorRegistry()
    first = registry.extract_metadata(path)
    fresh_registry = ExtractorRegistry()
    def fail(*args, **kwargs):
        raise AssertionError('content extraction was repeated')
    monkeypatch.setattr(fresh_registry, '_extract_uncached', fail)
    second = fresh_registry.extract_metadata(path)
    assert first.to_dict() == second.to_dict()
    second.headings.append('mutated')
    assert 'mutated' not in fresh_registry.extract_metadata(path).headings


def test_registry_changed_content_invalidates_even_with_restored_mtime(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# Old title')
    registry = ExtractorRegistry()
    before = path.stat()
    assert registry.extract_metadata(path).title == 'Old title'
    path.write_text('# New title')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    # Simulate changed ctime on filesystems whose clock coalesces fast writes.
    original_identity = registry._identity
    monkeypatch.setattr(registry, '_identity', lambda p: original_identity(p)[:-1] + (original_identity(p)[-1] + 1,))
    assert registry.extract_metadata(path).title == 'New title'


def test_registry_path_replacement_invalidates(tmp_path):
    path = tmp_path / 'lecture.md'
    path.write_text('# Old title')
    registry = ExtractorRegistry()
    before = path.stat()
    registry.extract_metadata(path)
    replacement = tmp_path / 'replacement'
    replacement.write_text('# New title')
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    replacement.replace(path)
    assert registry.extract_metadata(path).title == 'New title'


def test_registry_does_not_store_file_changed_during_extraction(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    original = registry._extract_uncached
    def changing(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_text('# Changed')
        return result
    monkeypatch.setattr(registry, '_extract_uncached', changing)
    registry.extract_metadata(path)
    assert registry._cache._connection.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0] == 0


def test_registry_custom_registration_bypasses_existing_cache(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    registry.extract_metadata(path)
    registry.register(object())
    calls = []
    monkeypatch.setattr(registry, '_extract_uncached', lambda *a, **k: calls.append(1) or metadata(title='Custom'))
    assert registry.extract_metadata(path).title == 'Custom'
    assert calls == [1]


@pytest.mark.parametrize('disabled', [None, False])
def test_registry_cache_can_be_disabled(tmp_path, monkeypatch, disabled):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry(cache=disabled)
    registry.extract_metadata(path)
    assert not (tmp_path / 'xdg').exists()


def test_bounded_worker_uses_its_own_cache_namespace(tmp_path, monkeypatch):
    from src.core.file_intelligence.extractors import isolated
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    assert registry.extract_metadata(path).title == 'Title'
    calls = []
    monkeypatch.setattr(isolated, 'extract_metadata', lambda *a: calls.append(1) or metadata(title='Bounded'))
    assert registry.extract_metadata(path, timeout_seconds=2).title == 'Bounded'
    assert registry.extract_metadata(path, timeout_seconds=2).title == 'Bounded'
    assert calls == [1]


def test_invalid_timeout_cannot_reuse_cached_success(tmp_path):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    assert registry.extract_metadata(path, timeout_seconds=2).extraction_status == 'SUCCESS'
    assert registry.extract_metadata(path, timeout_seconds=0).extraction_status == 'TIMEOUT'


def test_broken_cache_does_not_break_extraction(tmp_path):
    class BrokenCache:
        def get(self, *args, **kwargs):
            raise OSError('cache unavailable')
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    assert ExtractorRegistry(cache=BrokenCache()).extract_metadata(path).title == 'Title'


def test_origin_cache_hit_and_history_invalidation(tmp_path, monkeypatch):
    path = tmp_path / 'download.pdf'
    path.write_text('data')
    history = tmp_path / 'History'
    history.write_text('state one')
    detector = OriginDetector()
    monkeypatch.setattr(detector, '_discover_databases', lambda: [('chromium', history)])
    monkeypatch.setattr('src.core.file_intelligence.origin.FileMetadataExtractor.read_xattr', lambda *a: '')
    calls = []
    def detect(*args, **kwargs):
        calls.append(1)
        return OriginInfo(url='https://example.com/' + str(len(calls)))
    monkeypatch.setattr(detector, '_detect_origin_uncached', detect)
    assert detector.detect_origin(path).url == 'https://example.com/1'
    assert detector.detect_origin(path).url == 'https://example.com/1'
    history.write_text('state two changed')
    assert detector.detect_origin(path).url == 'https://example.com/2'
    Path(str(history) + '-wal').write_text('new WAL')
    assert detector.detect_origin(path).url == 'https://example.com/3'
    assert len(calls) == 3


def test_origin_disabled_does_not_read_cache_or_history(tmp_path, monkeypatch):
    path = tmp_path / 'download.pdf'
    path.write_text('data')
    detector = OriginDetector()
    monkeypatch.setattr(detector, '_discover_databases', lambda: [])
    monkeypatch.setattr(detector, '_detect_origin_uncached', lambda *a, **k: OriginInfo(url='https://example.com/a'))
    assert detector.detect_origin(path).url
    detector.enabled = False
    assert not detector.detect_origin(path).url


def test_persistent_hit_in_a_separate_process(tmp_path):
    path = tmp_path / 'lecture.md'
    path.write_text('# Persistent title')
    registry = ExtractorRegistry()
    assert registry.extract_metadata(path).title == 'Persistent title'
    code = '''import sys
from src.core.file_intelligence.extractors import ExtractorRegistry
registry=ExtractorRegistry()
def fail(*args, **kwargs): raise AssertionError('uncached dispatch')
registry._extract_uncached=fail
assert registry.extract_metadata(sys.argv[1]).title == 'Persistent title'
'''
    process = subprocess.run([sys.executable, '-B', '-c', code, str(path)], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr


def test_incompatible_schema_is_rebuilt(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as database:
        database.execute('CREATE TABLE file_metadata_cache (wrong_column TEXT)')
        database.execute('PRAGMA user_version=1')
    with MetadataCache(path) as cache:
        put(cache)
        assert get(cache).title == 'DBMS Lecture'


def test_origin_xattr_change_invalidates_without_history_access(tmp_path, monkeypatch):
    path = tmp_path / 'download.pdf'
    path.write_text('data')
    values = ['https://example.com/first?secret=SECRET']
    monkeypatch.setattr('src.core.file_intelligence.origin.FileMetadataExtractor.read_xattr', lambda *a: values[0])
    def forbidden(*args):
        pytest.fail('xattr origin should not need browser history')
    monkeypatch.setattr(OriginDetector, '_discover_databases', forbidden)
    detector = OriginDetector()
    assert detector.detect_origin(path).url == 'https://example.com/first'
    assert detector.detect_origin(path).url == 'https://example.com/first'
    values[0] = 'https://example.com/second?secret=SECRET'
    assert detector.detect_origin(path).url == 'https://example.com/second'


def test_cache_hit_rechecks_identity_after_lookup(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    registry.extract_metadata(path)
    original_get = registry._cache.get
    def change_during_lookup(*args, **kwargs):
        result = original_get(*args, **kwargs)
        path.write_text('# New title, different size')
        return result
    monkeypatch.setattr(registry._cache, 'get', change_during_lookup)
    assert registry.extract_metadata(path).title == 'New title, different size'


def test_partial_result_is_retried_until_success(tmp_path, monkeypatch):
    path = tmp_path / 'lecture.md'
    path.write_text('# Title')
    registry = ExtractorRegistry()
    calls = []
    def extract(*args, **kwargs):
        calls.append(1)
        return metadata(extraction_status='PARTIAL' if len(calls) == 1 else 'SUCCESS')
    monkeypatch.setattr(registry, '_extract_uncached', extract)
    assert registry.extract_metadata(path).extraction_status == 'PARTIAL'
    assert registry.extract_metadata(path).extraction_status == 'SUCCESS'
    assert registry.extract_metadata(path).extraction_status == 'SUCCESS'
    assert len(calls) == 2


def test_symlink_source_bypasses_persistent_cache(tmp_path, monkeypatch):
    target = tmp_path / 'real.md'
    target.write_text('# Title')
    link = tmp_path / 'link.md'
    link.symlink_to(target)
    registry = ExtractorRegistry()
    assert registry.extract_metadata(link).title == 'Title'
    assert not (tmp_path / 'xdg').exists()


def test_invalid_origin_payload_is_a_miss(cache):
    cache.put_origin('sample.pdf', 10, 2, 123.5, 500, OriginInfo(url='https://example.com/a'), provenance_key='one')
    cache._connection.execute('UPDATE file_metadata_cache SET metadata_json=?', ('{"url":[]}',))
    cache._connection.commit()
    assert cache.get_origin('sample.pdf', 10, 123.5, 500, provenance_key='one') is None

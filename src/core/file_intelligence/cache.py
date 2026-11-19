"""Disposable, private XDG SQLite cache. Cache failures are always misses.

File identity is an invalidation heuristic, not a content checksum. Registry
callers supply nanosecond mtime/ctime and device in addition to the public key.
No pickle, Qt, network, background thread or connection pool is used.
"""

import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

from src.core.file_intelligence.context import ExtractedMetadata, OriginInfo
from src.utils.paths import AppPaths


from src.core.file_intelligence.privacy import (
    _EXIF_ALLOWLIST, redact_values as _redact, normalize_metadata,
)


class MetadataCache:
    """Thread-safe persistent cache with a bounded, serialized connection.

    ``get``/``put`` retain the phase API; optional identity and namespace keywords
    prevent cross-device, changed-ctime and extractor-policy reuse in callers.
    Explicit close/context management is available; object destruction also closes.
    """

    MAX_ENTRIES = 10000
    MAX_AGE_SECONDS = 30 * 24 * 60 * 60
    MAX_PAYLOAD_BYTES = 256 * 1024
    SCHEMA_VERSION = 2
    BUSY_TIMEOUT = .02

    def __init__(self, db_path=None):
        self.db_path = os.fsdecode(db_path) if db_path is not None else ''
        self._lock = threading.RLock()
        self._connection = None
        try:
            if db_path is None:
                self.db_path = str(AppPaths.cache_dir() / 'metadata_cache.db')
            self._init_db()
        except (OSError, sqlite3.Error, ValueError):
            self.close()

    def _init_db(self, recover=True):
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Refuse links/devices; never follow a pre-existing cache symlink.
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError('Cache must be a regular file')
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        try:
            db = sqlite3.connect(self.db_path, timeout=self.BUSY_TIMEOUT, check_same_thread=False)
            self._connection = db
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=NORMAL')
            if hasattr(db, 'setlimit'):
                db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, self.MAX_PAYLOAD_BYTES + 16384)
            with db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                columns = {row[1] for row in db.execute('PRAGMA table_info(file_metadata_cache)')}
                expected = {'file_path', 'inode', 'device', 'mtime', 'size_bytes', 'mtime_ns',
                            'ctime_ns', 'namespace', 'metadata_json', 'created_at'}
                if version != self.SCHEMA_VERSION or columns != expected:
                    db.execute('DROP TABLE IF EXISTS file_metadata_cache')
                db.execute('''CREATE TABLE IF NOT EXISTS file_metadata_cache (
                    file_path TEXT NOT NULL, inode INTEGER NOT NULL, device INTEGER NOT NULL,
                    mtime REAL NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER,
                    ctime_ns INTEGER, namespace TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (file_path, inode, mtime, namespace))''')
                db.execute('CREATE INDEX IF NOT EXISTS cache_age ON file_metadata_cache(created_at)')
                db.execute(f'PRAGMA user_version={self.SCHEMA_VERSION}')
                self._prune()
        except sqlite3.DatabaseError as error:
            self.close()
            # A busy/read-only/full database is NOT corruption; leave it intact.
            code = getattr(error, 'sqlite_errorcode', None)
            corrupt = code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)
            # Python 3.8 lacks sqlite_errorcode.
            corrupt = corrupt or str(error) in ('file is not a database', 'database disk image is malformed')
            if recover and corrupt and not path.is_symlink() and path.is_file():
                path.unlink()
                for suffix in ('-wal', '-shm', '-journal'):
                    try:
                        Path(str(path) + suffix).unlink()
                    except FileNotFoundError:
                        pass
                self._init_db(recover=False)
            else:
                raise

    def _prune(self):
        db = self._connection
        db.execute('DELETE FROM file_metadata_cache WHERE created_at < ?', (time.time() - self.MAX_AGE_SECONDS,))
        count = db.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0]
        if count > self.MAX_ENTRIES:
            db.execute('DELETE FROM file_metadata_cache WHERE rowid IN '
                       '(SELECT rowid FROM file_metadata_cache ORDER BY created_at, rowid LIMIT ?)',
                       (count - self.MAX_ENTRIES,))

    def _get(self, file_path, inode, mtime, size_bytes, *, device=None,
             mtime_ns=None, ctime_ns=None, namespace='default'):
        with self._lock:
            if self._connection is None:
                return None
            try:
                row = self._connection.execute(
                    'SELECT metadata_json, device, mtime_ns, ctime_ns FROM file_metadata_cache '
                    'WHERE file_path=? AND inode=? AND mtime=? AND size_bytes=? AND namespace=? AND created_at>=?',
                    (os.path.abspath(file_path), inode, mtime, size_bytes, namespace,
                     time.time() - self.MAX_AGE_SECONDS)).fetchone()
                if row is None or any(expected is not None and expected != actual
                                      for expected, actual in zip((device, mtime_ns, ctime_ns), row[1:])):
                    return None
                if len(row[0].encode('utf-8')) > self.MAX_PAYLOAD_BYTES:
                    return None
                return json.loads(row[0])
            except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
                return None

    def get(self, file_path, inode, mtime, size_bytes, **identity):
        """Return independent metadata, or None on stale/invalid/unavailable data."""
        try:
            data = self._get(file_path, inode, mtime, size_bytes, **identity)
            if not isinstance(data, dict) or set(data) != set(ExtractedMetadata().to_dict()):
                return None
            # Cached JSON is untrusted. Validate all shapes before deserializing.
            sample = ExtractedMetadata().to_dict()
            for key, value in data.items():
                if key in {'dimensions', 'duration_seconds'}:
                    continue
                expected = sample[key]
                if expected is None:
                    if value is not None and not isinstance(value, str):
                        return None
                elif not isinstance(value, type(expected)):
                    return None
                if isinstance(value, list) and any(not isinstance(item, str) for item in value):
                    return None
            if data['extraction_status'] != 'SUCCESS':
                return None
            dims = data['dimensions']
            if dims is not None and (not isinstance(dims, list) or len(dims) != 2 or
                                     any(type(n) is not int or n <= 0 for n in dims)):
                return None
            duration = data['duration_seconds']
            if duration is not None and (type(duration) not in (int, float) or not 0 <= duration < float('inf')):
                return None
            if any(not isinstance(k, str) or not isinstance(v, str) for k, v in data['exif_tags'].items()):
                return None
            data['exif_tags'] = {k: v for k, v in data['exif_tags'].items() if k in _EXIF_ALLOWLIST}
            return normalize_metadata(ExtractedMetadata.from_dict(data))
        except (ValueError, TypeError, KeyError, RecursionError):
            return None

    def _put(self, file_path, inode, device, mtime, size_bytes, data, *,
             mtime_ns=None, ctime_ns=None, namespace='default'):
        with self._lock:
            if self._connection is None:
                return
            try:
                payload = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
                if len(payload) > self.MAX_PAYLOAD_BYTES:
                    return
                with self._connection:
                    # Keep one current identity per path and extraction policy.
                    self._connection.execute('DELETE FROM file_metadata_cache WHERE file_path=? AND namespace=?',
                                             (os.path.abspath(file_path), namespace))
                    self._connection.execute('INSERT INTO file_metadata_cache VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (os.path.abspath(file_path), inode, device, mtime, size_bytes,
                         mtime_ns, ctime_ns, namespace, payload, time.time()))
                    self._prune()
            except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError, RecursionError):
                pass

    def put(self, file_path, inode, device, mtime, size_bytes, metadata, **identity):
        """Persist only successful, redacted metadata; never cache transient failures."""
        if not isinstance(metadata, ExtractedMetadata) or metadata.extraction_status != 'SUCCESS':
            return
        try:
            data = normalize_metadata(metadata).to_dict()
            self._put(file_path, inode, device, mtime, size_bytes, data, **identity)
        except (ValueError, TypeError, AttributeError, RecursionError):
            pass

    def get_origin(self, file_path, inode, mtime, size_bytes, *, provenance_key, **identity):
        """Origin reuse requires a fingerprint of current provenance sources."""
        try:
            data = self._get(file_path, inode, mtime, size_bytes,
                             namespace='origin:' + provenance_key, **identity)
            if (not isinstance(data, dict) or set(data) != set(OriginInfo().to_dict()) or
                    any(not isinstance(value, str) for value in data.values())):
                return None
            from src.core.file_intelligence.origin import origin_from_url
            origin = OriginInfo.from_dict(data)
            clean = origin_from_url(origin.url, origin.source, origin.confidence, _redact(origin.evidence_detail))
            return clean if clean.url else None
        except (ValueError, TypeError, KeyError, RecursionError):
            return None

    def put_origin(self, file_path, inode, device, mtime, size_bytes, origin, *, provenance_key, **identity):
        from src.core.file_intelligence.origin import origin_from_url
        if not isinstance(origin, OriginInfo):
            return
        clean = origin_from_url(origin.url, origin.source, origin.confidence, _redact(origin.evidence_detail))
        if clean.url:
            self._put(file_path, inode, device, mtime, size_bytes, clean.to_dict(),
                      namespace='origin:' + provenance_key, **identity)

    def clear(self):
        with self._lock:
            if self._connection is not None:
                try:
                    with self._connection:
                        self._connection.execute('DELETE FROM file_metadata_cache')
                except sqlite3.Error:
                    pass

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        if hasattr(self, '_lock'):
            self.close()

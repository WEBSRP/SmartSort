"""Offline download provenance from xattrs and private browser-history snapshots.

No live browser database is opened by SQLite. Snapshot copies are private,
bounded, checked for concurrent changes, and removed before returning.
"""

import configparser
import hashlib
import threading
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
from urllib.parse import unquote, urlsplit, urlunsplit

from src.core.filename_cleanup import _CDN_TO_SITE
from src.core.file_intelligence.context import ConfidenceLevel, OriginInfo, OriginSource
from src.core.file_intelligence.metadata import FileMetadataExtractor


_SITES = dict(_CDN_TO_SITE, **{
    "github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket",
    "instructure.com": "lms", "blackboard.com": "lms", "arxiv.org": "academic_paper",
    "ieee.org": "academic_paper", "acm.org": "academic_paper", "kaggle.com": "kaggle",
    "unsplash.com": "wallpaper", "wallpaperflare.com": "wallpaper",
})


def origin_from_url(value, source=OriginSource.EXTENDED_ATTRIBUTE,
                    confidence=ConfidenceLevel.CONFIRMED, detail=""):
    """Validate HTTP(S), discard credentials/query/fragment and resolve locally."""
    if not isinstance(value, str) or len(value) > 4096:
        return OriginInfo()
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        return OriginInfo()
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return OriginInfo()
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        try:
            address = ipaddress.ip_address(host)
            authority = f"[{host}]" if address.version == 6 else host
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                          for label in host.split(".")):
                return OriginInfo()
            authority = host
        port = parsed.port
        if port is not None:
            if not 1 <= port <= 65535:
                return OriginInfo()
            if (parsed.scheme.lower(), port) not in (("http", 80), ("https", 443)):
                authority += f":{port}"
        # Matrix parameters can carry session IDs as well as query strings.
        path = re.sub(r";[^/]*", "", parsed.path)
        if any(ord(c) < 32 or ord(c) == 127 for c in unquote(path)):
            return OriginInfo()
        url = urlunsplit((parsed.scheme.lower(), authority, path, "", ""))
        domain = host[4:] if host.startswith("www.") else host
        site = next((name for suffix, name in _SITES.items()
                     if domain == suffix or domain.endswith("." + suffix)), None)
        if site is None and domain.split(".")[0] in ("canvas", "moodle"):
            site = "lms"
        return OriginInfo(url=url, domain=domain, site_name=site or domain,
                          source=source, confidence=confidence, evidence_detail=detail)
    except (ValueError, UnicodeError):
        return OriginInfo()


class OriginDetector:
    MAX_PROFILES = 32
    MAX_DIRECTORY_ENTRIES = 128
    MAX_ROWS = 64
    MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024  # cumulative, including retries and WAL
    TIMEOUT_SECONDS = 2.0
    TIMESTAMP_WINDOW = 24 * 60 * 60

    def __init__(self, config=None, cache=True):
        self._cache = cache
        self._cache_lock = threading.Lock()
        self.config = config
        self.enabled = config.get("enable_origin_detection", True) if config is not None else True

    def _provenance_key(self, target, file_size, file_timestamp):
        # Browser history/WAL can change independently of the downloaded file.
        attributes = [(name, FileMetadataExtractor.read_xattr(target, name))
                      for name in FileMetadataExtractor.ORIGIN_XATTRS]
        # Valid xattrs win without consulting browser history.
        if any(origin_from_url(value).url for _, value in attributes):
            databases = []
        else:
            databases = [
                (family, str(path), tuple(self._cache_identity(Path(str(path) + suffix))
                                         for suffix in ('', '-wal', '-journal')))
                for family, path in self._discover_databases()
            ]
        encoded = repr(('origin-v1', file_size, file_timestamp, attributes, databases)).encode('utf-8', 'surrogatepass')
        return hashlib.sha256(encoded).hexdigest()

    def detect_origin(self, file_path, file_size=None, *, file_timestamp=None):
        """Cache corroborated origins only while file and provenance sources match."""
        enabled = self.config.get("enable_origin_detection", self.enabled) if self.config is not None else self.enabled
        if not enabled:
            return OriginInfo()
        cache = before = key = None
        try:
            target = os.path.abspath(os.path.expanduser(os.fsdecode(file_path)))
            before = self._cache_identity(target)
            if before is not None:
                key = self._provenance_key(target, file_size, file_timestamp)
                with self._cache_lock:
                    if self._cache is True:
                        from src.core.file_intelligence.cache import MetadataCache
                        self._cache = MetadataCache()
                    cache = self._cache if self._cache not in (False, None) else None
                device, inode, size, mtime_ns, ctime_ns = before
                if cache is not None:
                    origin = cache.get_origin(target, inode, mtime_ns / 1e9, size,
                        provenance_key=key, device=device, mtime_ns=mtime_ns, ctime_ns=ctime_ns)
                    if origin is not None and self._cache_identity(target) == before and self._provenance_key(target, file_size, file_timestamp) == key:
                        return origin
        except Exception:
            cache = None
        origin = self._detect_origin_uncached(file_path, file_size, file_timestamp=file_timestamp)
        try:
            if cache is not None and origin.url and self._cache_identity(target) == before and self._provenance_key(target, file_size, file_timestamp) == key:
                cache.put_origin(target, inode, device, mtime_ns / 1e9, size, origin,
                    provenance_key=key, mtime_ns=mtime_ns, ctime_ns=ctime_ns)
        except Exception:
            pass
        return origin

    def _detect_origin_uncached(self, file_path, file_size=None, *, file_timestamp=None):
        """Return corroborated local origin, or UNKNOWN without diagnostics/URLs.

        Exact paths take precedence. Filename-only matches require both size
        and a timestamp within 24 hours. Equally strong conflicting matches
        remain unknown. An explicit timestamp is Unix seconds.
        """
        enabled = self.config.get("enable_origin_detection", self.enabled) if self.config is not None else self.enabled
        if not enabled:
            return OriginInfo()
        try:
            target = os.path.abspath(os.path.expanduser(os.fsdecode(file_path)))
            if "\x00" in target or len(target) > 4096:
                return OriginInfo()
            if file_size is not None and (isinstance(file_size, bool) or not isinstance(file_size, int) or file_size < 0):
                return OriginInfo()
            if file_timestamp is not None and (isinstance(file_timestamp, bool) or
                    not isinstance(file_timestamp, (int, float)) or not math.isfinite(file_timestamp)):
                return OriginInfo()
            deadline = time.monotonic() + self.TIMEOUT_SECONDS
            for attribute in FileMetadataExtractor.ORIGIN_XATTRS:
                if time.monotonic() > deadline:
                    return OriginInfo()
                origin = origin_from_url(FileMetadataExtractor.read_xattr(target, attribute),
                                         detail=f"Read {attribute} extended attribute")
                if origin.url:
                    return origin
            times = [float(file_timestamp)] if file_timestamp is not None else []
            try:
                info = os.stat(target)
                if not stat.S_ISREG(info.st_mode):
                    return OriginInfo()
                if file_size is None:
                    file_size = info.st_size
                if file_timestamp is None:
                    times = [info.st_mtime, info.st_ctime]
            except OSError:
                pass
            candidates, budget = [], [self.MAX_SNAPSHOT_BYTES]
            for family, path in self._discover_databases():
                if time.monotonic() > deadline:
                    break
                try:
                    with tempfile.TemporaryDirectory(prefix="smartsort-origin-") as folder:
                        snapshot, wal = self._snapshot(Path(path), Path(folder), deadline, budget)
                        uri = snapshot.as_uri() + ("?mode=ro" if wal else "?mode=ro&immutable=1")
                        with self._connection(uri, deadline) as database:
                            rows = (self._chromium_rows(database, target) if family == "chromium"
                                    else self._firefox_rows(database, target))
                            for row in rows:
                                candidate = self._candidate(row, target, file_size, times, family)
                                if candidate is not None:
                                    candidates.append(candidate)
                except (OSError, ValueError, sqlite3.Error, TimeoutError):
                    # Never echo backend exceptions: they may include private URLs.
                    continue
            if not candidates:
                return OriginInfo()
            candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
            strength, distance, best = candidates[0]
            peers = [item for item in candidates if item[0] == strength and
                     (item[1] == distance or abs(item[1] - distance) <= 1)]
            return best if len({item[2].url for item in peers}) == 1 else OriginInfo()
        except (OSError, ValueError, TypeError, OverflowError):
            return OriginInfo()

    @staticmethod
    def _connection(uri, deadline):
        # The context returned here closes the connection, unlike Connection's
        # transaction-only context manager.
        from contextlib import closing
        database = sqlite3.connect(uri, uri=True, timeout=0.05)
        try:
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA query_only=ON")
            database.execute("PRAGMA trusted_schema=OFF")
            database.execute("PRAGMA temp_store=MEMORY")
            database.execute("PRAGMA cache_size=-2048")
            if hasattr(database, "setlimit"):
                database.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 64 * 1024)
            database.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            return closing(database)
        except Exception:
            database.close()
            raise

    @staticmethod
    def _identity(path):
        try:
            info = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Browser database input is not a regular file")
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except FileNotFoundError:
            return None

    @staticmethod
    def _cache_identity(path):
        # Independent bookkeeping: snapshot retries retain their existing checks.
        try:
            info = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Cache input must be a regular file")
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except FileNotFoundError:
            return None

    def _snapshot(self, path, folder, deadline, budget):
        sources = [path, Path(str(path) + "-wal")]
        for attempt in range(2):
            if Path(str(path) + "-journal").exists():
                raise ValueError("Rollback journal present; skip live snapshot")
            identities = [self._identity(item) for item in sources]
            if identities[0] is None:
                raise ValueError("Browser database absent")
            needed = sum(item[2] for item in identities if item is not None)
            if needed > budget[0]:
                raise ValueError("Browser snapshot byte budget exceeded")
            destination = folder / str(attempt)
            destination.mkdir(mode=0o700)
            for source, identity, name in zip(sources, identities, ("history.sqlite", "history.sqlite-wal")):
                if identity is None:
                    continue
                descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(descriptor, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != identity[:2]:
                        raise ValueError("Browser snapshot input changed")
                    output = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(output, "wb") as copy:
                        remaining = identity[2]
                        while remaining:
                            if time.monotonic() > deadline:
                                raise TimeoutError
                            chunk = stream.read(min(65536, remaining))
                            if not chunk:
                                raise ValueError("Browser snapshot input truncated")
                            budget[0] -= len(chunk)
                            copy.write(chunk)
                            remaining -= len(chunk)
            if identities == [self._identity(item) for item in sources] and not Path(str(path) + "-journal").exists():
                return destination / "history.sqlite", bool(identities[1] and identities[1][2])
        raise ValueError("Browser database changed during both snapshot attempts")

    def _children(self, root):
        try:
            with os.scandir(root) as entries:
                result = []
                for index, entry in enumerate(entries):
                    if index >= self.MAX_DIRECTORY_ENTRIES:
                        break
                    if entry.is_dir(follow_symlinks=False):
                        result.append(Path(entry.path))
                return sorted(result)
        except OSError:
            return []

    def _discover_databases(self):
        home = Path.home()
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        discovered = []
        for relative in ("google-chrome", "chromium", "BraveSoftware/Brave-Browser", "microsoft-edge"):
            for profile in self._children(config / relative):
                if profile.name == "Default" or profile.name.startswith("Profile "):
                    discovered.append(("chromium", profile / "History"))
        for root in (home / ".mozilla/firefox", home / "snap/firefox/common/.mozilla/firefox",
                     home / ".var/app/org.mozilla.firefox/.mozilla/firefox"):
            profiles = self._children(root)
            try:
                ini = root / "profiles.ini"
                identity = self._identity(ini)
                if identity is None or identity[2] > 65536:
                    raise ValueError("Profile registry absent or oversized")
                descriptor = os.open(ini, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("Profile registry changed to a non-regular file")
                    content = stream.read(65537).decode("utf-8")
                if len(content) <= 65536:
                    parser = configparser.ConfigParser(interpolation=None)
                    parser.read_string(content)
                    for section in parser.sections()[:self.MAX_PROFILES]:
                        if section.startswith("Profile") and parser.has_option(section, "Path"):
                            path = Path(parser[section]["Path"])
                            profiles.append(root / path if parser[section].get("IsRelative", "1") == "1" else path)
            except (OSError, ValueError, configparser.Error):
                pass
            discovered.extend(("firefox", profile / "places.sqlite") for profile in profiles)
        seen = set()
        for family, path in discovered:
            key = os.path.abspath(path)
            if key not in seen and path.is_file() and not path.is_symlink():
                seen.add(key)
                yield family, Path(key)
                if len(seen) >= self.MAX_PROFILES:
                    break

    @staticmethod
    def _columns(database, table):
        if not database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return set()
        # Table names are fixed program constants, not user or schema inputs.
        return {row[1] for row in database.execute(f'PRAGMA table_info("{table}")')}

    @staticmethod
    def _like(value):
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _number(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return float(value) if math.isfinite(value) and value > 0 else None
            except OverflowError:
                pass
        return None

    def _chromium_rows(self, database, target):
        columns = self._columns(database, "downloads")
        path_column = "target_path" if "target_path" in columns else "full_path"
        if path_column not in columns:
            return []
        fields = ("id", path_column, "start_time", "end_time", "total_bytes", "state",
                  "tab_url", "tab_referrer_url", "referrer", "url")
        selected = []
        for name in fields:
            if name not in columns:
                expression = "NULL"
            elif name in (path_column, "tab_url", "tab_referrer_url", "referrer", "url"):
                expression = f'CASE WHEN length("{name}")<=4096 THEN "{name}" ELSE NULL END'
            else:
                expression = f'"{name}"'
            selected.append(expression + f' AS "{name}"')
        query = ",".join(selected)
        rows = database.execute(f'SELECT {query} FROM downloads WHERE "{path_column}"=? LIMIT ?',
                                (target, self.MAX_ROWS + 1)).fetchall()
        if not rows:
            rows = database.execute(f'SELECT {query} FROM downloads WHERE "{path_column}" LIKE ? ESCAPE \'\\\' LIMIT ?',
                                    ("%/" + self._like(os.path.basename(target)), self.MAX_ROWS + 1)).fetchall()
        if len(rows) > self.MAX_ROWS:
            return []
        chains = self._columns(database, "downloads_url_chains")
        results = []
        for row in rows:
            urls = []
            if {"id","chain_index","url"} <= chains and row["id"] is not None:
                urls = [item[0] for item in database.execute(
                    "SELECT CASE WHEN length(url)<=4096 THEN url ELSE NULL END FROM downloads_url_chains WHERE id=? ORDER BY chain_index DESC LIMIT 16", (row["id"],))]
            urls += [row[name] for name in ("url","tab_url","tab_referrer_url","referrer")]
            stamp = self._number(row["end_time"]) or self._number(row["start_time"])
            # Modern Chromium: microseconds since 1601; legacy: Unix seconds.
            timestamp = stamp / 1000000 - 11644473600 if stamp and stamp > 10**14 else stamp
            results.append(dict(path=row[path_column], size=row["total_bytes"], timestamp=timestamp,
                                state=row["state"], urls=urls))
        return results

    def _firefox_rows(self, database, target):
        if not {"place_id","content","dateAdded"} <= self._columns(database,"moz_annos") or not {"id","url"} <= self._columns(database,"moz_places"):
            return []
        attributes = {"id","name"} <= self._columns(database,"moz_anno_attributes")
        join = " JOIN moz_anno_attributes n ON n.id=a.anno_attribute_id" if attributes else ""
        restriction = " AND n.name='downloads/destinationFileURI'" if attributes else ""
        selection = (
            "SELECT a.place_id,CASE WHEN length(p.url)<=4096 THEN p.url ELSE NULL END url,"
            "CASE WHEN length(a.content)<=4096 THEN a.content ELSE NULL END path,a.dateAdded "
            "FROM moz_annos a JOIN moz_places p ON p.id=a.place_id" + join)
        rows = database.execute(selection + " WHERE (a.content=? OR a.content=?)" + restriction + " LIMIT ?",
                                (Path(target).as_uri(), target, self.MAX_ROWS + 1)).fetchall()
        if not rows:
            rows = database.execute(selection + " WHERE (a.content LIKE ? ESCAPE '\\' OR a.content LIKE ? ESCAPE '\\')" + restriction + " LIMIT ?",
                                    ("%/"+self._like(os.path.basename(target)),
                                     "%/"+self._like(Path(target).as_uri().rsplit("/",1)[-1]), self.MAX_ROWS + 1)).fetchall()
        if len(rows) > self.MAX_ROWS:
            return []
        results = []
        for row in rows:
            metadata = {}
            if attributes:
                item = database.execute(
                    "SELECT substr(a.content,1,8192) FROM moz_annos a JOIN moz_anno_attributes n ON n.id=a.anno_attribute_id "
                    "WHERE a.place_id=? AND n.name='downloads/metaData' LIMIT 1", (row["place_id"],)).fetchone()
                if item:
                    try:
                        metadata = json.loads(item[0])
                        if not isinstance(metadata,dict):
                            continue
                    except (TypeError, ValueError):
                        continue
            stamp = self._number(metadata.get("endTime"))
            timestamp = stamp/1000 if stamp else (self._number(row["dateAdded"]) or 0)/1000000
            results.append(dict(path=row["path"], size=metadata.get("fileSize"), timestamp=timestamp,
                                state=metadata.get("state"), urls=[row["url"]]))
        return results

    def _candidate(self, row, target, size, times, family):
        path = row["path"]
        if not isinstance(path,str) or not path:
            return None
        if path.startswith("file:"):
            uri = urlsplit(path)
            if uri.netloc not in ("","localhost") or uri.query or uri.fragment:
                return None
            path = unquote(uri.path)
        if not os.path.isabs(path) or "\x00" in path:
            return None
        path = os.path.normpath(path)
        exact = path == target
        if not exact and os.path.basename(path) != os.path.basename(target):
            return None
        if row["state"] is not None and (isinstance(row["state"],bool) or row["state"] != 1):
            return None
        recorded_size = row["size"]
        size_known = isinstance(recorded_size,int) and not isinstance(recorded_size,bool) and recorded_size >= 0 and size is not None
        if size_known and recorded_size != size:
            return None
        stamp = row["timestamp"]
        stamp_known = isinstance(stamp,(int,float)) and not isinstance(stamp,bool) and math.isfinite(stamp) and stamp > 0
        distance = min((abs(stamp-value) for value in times),default=float("inf")) if stamp_known else float("inf")
        time_match = distance <= self.TIMESTAMP_WINDOW
        if times and stamp_known and not time_match:
            return None
        if not exact and not (size_known and time_match):
            return None
        confidence = ConfidenceLevel.CONFIRMED if exact and size_known and time_match else ConfidenceLevel.PROBABLE
        detail = f"{family.title()} download: {'exact path' if exact else 'filename'}, " + ("size and timestamp matched" if size_known and time_match else "limited corroboration")
        for url in row["urls"]:
            origin = origin_from_url(url, OriginSource.BROWSER_SQLITE, confidence, detail)
            if origin.url:
                return (int(exact),int(size_known),int(time_match)), distance, origin
        return None

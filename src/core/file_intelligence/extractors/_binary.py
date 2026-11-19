"""Read-only, cumulative byte budgets for Phase 06 header inspection."""

import io
import math
import os
import stat
import time

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor


class HeaderLimit(Exception):
    pass


def clean(value, limit=256):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, (str, int, float)):
        return None
    return str(value).replace("\x00", " ").strip()[:limit] or None


def duration(result, value):
    try:
        value = float(value)
        if math.isfinite(value) and value >= 0:
            result.duration_seconds = value
    except (TypeError, ValueError, OverflowError):
        pass


def dimensions(result, width, height):
    if 0 < width <= 2**31 - 1 and 0 < height <= 2**31 - 1:
        result.dimensions = (int(width), int(height))


def keyword(result, value):
    value = clean(value, 128)
    if value and value not in result.keywords and len(result.keywords) < 20:
        result.keywords.append(value)


class HeaderReader(io.RawIOBase):
    def __init__(self, path, budget, timeout):
        super().__init__()
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self._file = os.fdopen(descriptor, "rb")
        self.size = os.fstat(self._file.fileno()).st_size
        if not stat.S_ISREG(os.fstat(self._file.fileno()).st_mode):
            self._file.close()
            raise ValueError("Header input must be a regular file")
        self.name = os.fsdecode(path)
        self.mode = "rb"
        self.remaining = budget
        self.deadline = time.monotonic() + timeout

    def _check(self):
        if time.monotonic() > self.deadline:
            raise TimeoutError("Header inspection exceeded its execution budget")

    def read(self, size=-1):
        self._check()
        available = max(0, self.size - self.tell())
        size = available if size is None or size < 0 else min(size, available)
        if size > self.remaining:
            raise HeaderLimit("Cumulative header read budget exhausted")
        data = self._file.read(size)
        self.remaining -= len(data)
        return data

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def seek(self, offset, whence=os.SEEK_SET):
        self._check()
        return self._file.seek(offset, whence)

    def tell(self):
        return self._file.tell()

    def fileno(self):
        return self._file.fileno()

    def readable(self):
        return True

    def seekable(self):
        return True

    def close(self):
        if hasattr(self, "_file"):
            self._file.close()
        super().close()


class BinaryExtractor(BaseExtractor):
    MIME_TYPES = frozenset()

    def can_extract(self, extension, mime_type):
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type in self.MIME_TYPES

    def extract(self, file_path, max_bytes=None):
        result = ExtractedMetadata(extractor_name=type(self).__name__, extraction_status="SUCCESS")
        try:
            if max_bytes is not None and (isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0):
                raise ValueError("max_bytes must be a non-negative integer or None")
            limit = self.MAX_TEXT_BYTES if max_bytes is None else min(max_bytes, self.MAX_TEXT_BYTES)
            reader = HeaderReader(file_path, limit, self.TIMEOUT_SECONDS)
        except (OSError, ValueError, TypeError):
            result.extraction_status = "FAILED"
            result.error_message = "Invalid input or read limit" if max_bytes is None else "Invalid input or max_bytes read limit"
            return result
        try:
            with reader:
                self._inspect(reader, result)
        except HeaderLimit:
            result.extraction_status = "PARTIAL"
            result.error_message = "Cumulative header read budget exhausted"
        except TimeoutError:
            result.extraction_status = "TIMEOUT"
            result.error_message = "Header inspection exceeded its execution budget"
        except Exception:
            # Backend exceptions may contain private tag values; never copy them.
            result.extraction_status = "PARTIAL"
            result.error_message = "Some header metadata could not be read"
        self._finalize(result)
        return result

    def _finalize(self, result):
        pass

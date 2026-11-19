"""Bounded archive listings. No member is opened, executed, or written to disk."""

import bz2
import lzma
import os
import re
import struct
import tarfile
import zlib

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor
from src.core.file_intelligence.extractors._binary import HeaderReader, HeaderLimit
from src.core.file_intelligence.extractors.code import CodeExtractor


class _CorruptArchive(ValueError):
    pass


class _DecodedReader:
    """Sequential decoder with bounded input, output, and XZ dictionary memory."""

    def __init__(self, source, kind, limit):
        self.source, self.remaining = source, limit
        self.pending = b""
        self.kind = kind
        if kind == "gz":
            self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif kind == "bz2":
            self.decoder = bz2.BZ2Decompressor()
        else:
            self.decoder = lzma.LZMADecompressor(memlimit=32 * 1024 * 1024)

    def read(self, size):
        self.source._check()
        if size < 0 or size > self.remaining:
            raise HeaderLimit("Decompressed TAR scan budget exhausted")
        output = bytearray()
        while len(output) < size and not self.decoder.eof:
            self.source._check()
            if self.kind == "gz" and self.pending:
                data, self.pending = self.pending, b""
            elif self.kind != "gz" and not self.decoder.needs_input:
                data = b""
            else:
                if not self.source.remaining:
                    raise HeaderLimit("Compressed archive read budget exhausted")
                data = self.source.read(min(4096, self.source.remaining))
                if not data:
                    raise _CorruptArchive("Truncated compressed TAR stream")
            try:
                piece = self.decoder.decompress(data, size - len(output))
            except lzma.LZMAError as exc:
                if "Memory usage limit" in str(exc):
                    raise HeaderLimit("XZ dictionary exceeds the 32 MiB memory limit") from exc
                raise
            except OSError as exc:
                raise _CorruptArchive("Invalid compressed TAR stream") from exc
            output.extend(piece)
            if self.kind == "gz":
                self.pending = self.decoder.unconsumed_tail
        self.remaining -= len(output)
        return bytes(output)


class ArchiveExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".7z",
    ])
    MIME_TYPES = frozenset([
        "application/zip", "application/x-zip-compressed", "application/x-tar",
        "application/gzip", "application/x-gzip", "application/x-bzip2",
        "application/x-xz", "application/x-7z-compressed",
    ])
    MAX_ENTRIES = 500
    MAX_HEADER_BYTES = 2 * 1024 * 1024
    MAX_PATH_LENGTH = 1024

    def can_extract(self, extension, mime_type):
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type in self.MIME_TYPES

    def extract(self, file_path, max_bytes=None):
        result = ExtractedMetadata(extractor_name="ArchiveExtractor", extraction_status="SUCCESS")
        warnings = []
        try:
            if max_bytes is not None and (isinstance(max_bytes, bool) or
                    not isinstance(max_bytes, int) or max_bytes < 0):
                raise ValueError("max_bytes must be a non-negative integer or None")
            limit = self.MAX_HEADER_BYTES if max_bytes is None else min(max_bytes, self.MAX_HEADER_BYTES)
            with HeaderReader(file_path, limit, self.TIMEOUT_SECONDS) as reader:
                magic = reader.read(8)
                reader.seek(0)
                if magic.startswith(b"7z\xbc\xaf\x27\x1c"):
                    warnings.append("7z inspection is unavailable in the Python standard library")
                elif magic.startswith(b"PK") or os.fsdecode(file_path).lower().endswith(".zip"):
                    self._zip(reader, result, warnings)
                else:
                    self._tar(reader, magic, limit, result, warnings)
        except HeaderLimit as exc:
            warnings.append(str(exc))
        except TimeoutError:
            result.extraction_status, result.error_message = "TIMEOUT", "Archive inspection deadline exceeded"
        except (tarfile.TarError, _CorruptArchive, EOFError, zlib.error, lzma.LZMAError,
                UnicodeDecodeError, RecursionError) as exc:
            result.extraction_status, result.error_message = "CORRUPTED", str(exc)[:512]
        except Exception as exc:
            result.extraction_status, result.error_message = "FAILED", str(exc)[:512]
        if warnings:
            if result.extraction_status == "SUCCESS":
                result.extraction_status = "PARTIAL"
            result.error_message = "; ".join(dict.fromkeys([result.error_message] + warnings)).strip("; ")[:512]
        return result

    def _zip(self, reader, result, warnings):
        # Parse central records sequentially instead of materializing an
        # unbounded ZipFile.infolist() before applying the 500-entry limit.
        length = min(reader.size, 65557)
        reader.seek(reader.size - length)
        tail = reader.read(length)
        offset = len(tail)
        end = None
        while offset:
            reader._check()
            offset = tail.rfind(b"PK\x05\x06", 0, offset)
            if offset < 0:
                break
            if offset + 22 <= len(tail):
                record = struct.unpack_from("<4s4H2IH", tail, offset)
                if offset + 22 + record[7] == len(tail):
                    end = record
                    break
        if end is None:
            raise _CorruptArchive("Missing or truncated ZIP end record")
        _, disk, directory_disk, disk_count, count, central_size, central_offset, _ = end
        if disk or directory_disk or disk_count != count:
            warnings.append("Multi-volume ZIP inspection is not supported")
            return
        if count == 65535 or central_size == 0xffffffff or central_offset == 0xffffffff:
            warnings.append("ZIP64 directory inspection is not supported")
            return
        end_position = reader.size - length + offset
        # A self-extracting prefix may shift all offsets by the same amount.
        start = end_position - central_size
        if start < central_offset or start < 0 or count * 46 > central_size:
            raise _CorruptArchive("Invalid ZIP central directory bounds")
        reader.seek(start)
        for _ in range(min(count, self.MAX_ENTRIES)):
            reader._check()
            if reader.tell() + 46 > end_position:
                raise _CorruptArchive("Truncated ZIP central header")
            header = reader.read(46)
            if len(header) != 46 or header[:4] != b"PK\x01\x02":
                raise _CorruptArchive("Invalid ZIP central header")
            fields = struct.unpack("<4s6H3I5H2I", header)
            flags, name_size, extra_size, comment_size = fields[3], fields[10], fields[11], fields[12]
            next_position = reader.tell() + name_size + extra_size + comment_size
            if next_position > end_position:
                raise _CorruptArchive("ZIP entry exceeds central directory bounds")
            if fields[13]:
                warnings.append("Skipped multi-volume ZIP member")
            if flags & (1 | 64):
                result.extraction_status = "ENCRYPTED"
                warnings.append("ZIP contains encrypted members; payloads were not inspected")
            if name_size <= self.MAX_PATH_LENGTH:
                name = reader.read(name_size).decode("utf-8" if flags & 0x800 else "cp437", errors="strict")
                self._member(name, result, warnings)
            else:
                warnings.append("Skipped oversized archive member name")
            reader.seek(next_position)
        if count > self.MAX_ENTRIES:
            warnings.append("Archive listing limited to 500 entries")
        elif reader.tell() != end_position:
            warnings.append("Additional ZIP directory records were not inspected")

    def _tar(self, reader, magic, limit, result, warnings):
        kind = None
        if magic.startswith(b"\x1f\x8b"):
            kind = "gz"
        elif magic.startswith(b"BZh"):
            kind = "bz2"
        elif magic.startswith(b"\xfd7zXZ\x00"):
            kind = "xz"
        if kind:
            # Compressed tarballs must decode intervening payload bytes to
            # reach later headers. The output budget also bounds this skipping.
            stream = _DecodedReader(reader, kind, limit)
            archive = tarfile.open(fileobj=stream, mode="r|", bufsize=512)
        else:
            # Plain TAR can seek past payloads without reading them.
            archive = tarfile.open(fileobj=reader, mode="r:")
        with archive:
            for _ in range(self.MAX_ENTRIES):
                reader._check()
                member = archive.next()
                if member is None:
                    return
                self._member(member.name, result, warnings)
            warnings.append("TAR listing stopped at 500 entries; remainder uninspected")

    def _member(self, name, result, warnings):
        # Check before normalization: repeated './' on a giant PAX name would
        # otherwise cause quadratic string copying before reaching the cap.
        if len(name) > self.MAX_PATH_LENGTH:
            warnings.append("Skipped oversized archive member name")
            return
        name = name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        if name in ("", "."):
            return
        if (len(name) > self.MAX_PATH_LENGTH or name.startswith("/") or
                re.match(r"^[A-Za-z]:", name) or ".." in name.split("/") or
                any(ord(c) < 32 or ord(c) == 127 for c in name)):
            warnings.append("Skipped unsafe or oversized archive member name")
            return
        result.toc_entries.append(name)
        if "/" in name.rstrip("/"):
            heading = name.split("/", 1)[0][:256]
            if heading not in result.headings and len(result.headings) < 64:
                result.headings.append(heading)
        elif name.endswith("/") and len(result.headings) < 64:
            heading = name.rstrip("/")[:256]
            if heading not in result.headings:
                result.headings.append(heading)
        extension = os.path.splitext(name)[1].lower()
        lower = name.rsplit("/", 1)[-1].lower()
        keywords = []
        if extension in (".ppt", ".pptx", ".odp"):
            keywords += ["presentation", "course_material"]
        if extension in (".pdf", ".doc", ".docx", ".odt", ".txt", ".md"):
            keywords.append("document")
        if extension in (".csv", ".tsv", ".xls", ".xlsx", ".ods"):
            keywords.append("spreadsheet")
        if extension in CodeExtractor.SUPPORTED_EXTENSIONS or lower in (
                "makefile", "cmakelists.txt", "package.json", "pyproject.toml", "cargo.toml", "go.mod"):
            keywords.append("code_project")
        if extension in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
            keywords.append("image")
        if extension in (".mp3", ".wav", ".flac", ".ogg"):
            keywords.append("audio")
        if extension in (".mp4", ".mkv", ".webm", ".mov"):
            keywords.append("video")
        if extension in (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z"):
            keywords.append("archive")
        for keyword in keywords:
            if keyword not in result.keywords and len(result.keywords) < 20:
                result.keywords.append(keyword)

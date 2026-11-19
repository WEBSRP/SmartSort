"""Shared, bounded ZIP/XML inspection for the Phase 05 Office extractors."""

from __future__ import annotations

from contextlib import closing
import os
import posixpath
import re
import stat
import struct
import time
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from src.core.file_intelligence.privacy import redact_url_text
from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor
from src.core.file_intelligence.extractors.text import TextExtractor


class InspectionLimit(Exception):
    pass


class UnsafeDocument(ValueError):
    pass


def local(tag):
    return tag.rsplit("}", 1)[-1]


def attribute(element, name, default=""):
    return next((v for k, v in element.attrib.items() if local(k) == name), default)


def text_of(element, tags=("t",)):
    return "".join(node.text or "" for node in element.iter() if local(node.tag) in tags).strip()


def heading(result, value):
    value = value.strip()[:256]
    if value and value not in result.headings and len(result.headings) < 64:
        result.headings.append(value)


class TextSample:
    def __init__(self, limit):
        self.remaining = limit
        self.parts = []

    def add(self, text):
        if text and self.remaining:
            raw = (("\n" if self.parts else "") + text).encode("utf-8")[:self.remaining]
            self.parts.append(raw.decode("utf-8", errors="ignore"))
            self.remaining -= len(raw)

    @property
    def text(self):
        return "".join(self.parts)


class OfficePackage:
    MAX_XML_BYTES = 500 * 1024

    def __init__(self, stream, deadline):
        # Inspect the classic ZIP index before ZipFile materializes its entries.
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail) - offset < 22:
            raise zipfile.BadZipFile("Missing ZIP end record")
        record = struct.unpack_from("<4s4H2LH", tail, offset)
        if record[1] or record[2]:
            raise UnsafeDocument("Multi-disk Office packages are not supported")
        if record[4] > 10000 or record[5] > 2 * 1024 * 1024:
            raise InspectionLimit("Office ZIP index exceeds the bounded inspection limit")
        stream.seek(0)
        self.zip = zipfile.ZipFile(stream)
        if len(self.zip.infolist()) > 10000:
            self.zip.close()
            raise InspectionLimit("Office ZIP index exceeds 10,000 entries")
        self.remaining = self.MAX_XML_BYTES
        self.deadline = deadline
        self.warnings = []

    def close(self):
        self.zip.close()

    def has(self, path):
        return path in self.zip.NameToInfo

    def events(self, path, root_tag=None):
        if not self.has(path):
            raise UnsafeDocument(f"Missing XML part: {path}")
        info = self.zip.getinfo(path)
        if info.flag_bits & 1:
            raise RuntimeError("Encrypted Office ZIP member")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise InspectionLimit("Unsupported Office ZIP compression method")
        parser = ET.XMLPullParser(events=("start", "end"))
        previous = b""
        consumed = 0
        root_checked = False
        with self.zip.open(info) as member:
            while consumed < info.file_size:
                if time.monotonic() > self.deadline:
                    raise TimeoutError("Office XML inspection exceeded its execution budget")
                if self.remaining <= 0:
                    raise InspectionLimit("Office XML exceeds the shared 500 KiB budget")
                chunk = member.read(min(4096, self.remaining))
                if not chunk:
                    break
                self.remaining -= len(chunk)
                consumed += len(chunk)
                # Also recognize UTF-16/32 declarations and split chunk boundaries.
                probe = previous + chunk.replace(b"\x00", b"").upper()
                if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                    raise UnsafeDocument("DTD/entity declarations are not allowed in Office XML")
                previous = probe[-32:]
                parser.feed(chunk)
                for event, element in parser.read_events():
                    if event == "start" and not root_checked:
                        if root_tag and local(element.tag) != root_tag:
                            raise UnsafeDocument(f"Unexpected XML root in {path}")
                        root_checked = True
                    yield event, element
        parser.close()
        yield from parser.read_events()

    def xml(self, path, optional=False, root_tag=None):
        if optional and not self.has(path):
            return None
        root = None
        with closing(self.events(path, root_tag)) as events:
            for event, element in events:
                if event == "start" and root is None:
                    root = element
        return root

    def relationships(self, path, base, kind):
        root = self.xml(path, optional=True, root_tag="Relationships")
        targets = {}
        if root is None:
            return targets
        for element in root:
            if local(element.tag) != "Relationship" or element.get("Type", "").rsplit("/", 1)[-1] != kind:
                continue
            if element.get("TargetMode", "").lower() == "external":
                self.warnings.append("Skipped external Office relationship")
                continue
            target = unquote(element.get("Target", ""))
            url = urlsplit(target)
            if url.scheme or url.netloc or url.query or url.fragment or "\\" in target or "\x00" in target:
                raise UnsafeDocument("Unsafe Office relationship target")
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(base, target))
            if path == ".." or path.startswith("../") or path == ".":
                raise UnsafeDocument("Office relationship escapes the package root")
            targets[element.get("Id", "")] = path
        return targets


class OfficeExtractor(BaseExtractor):
    LEGACY_EXTENSIONS = frozenset()
    ODF_EXTENSIONS = frozenset()
    MIME_TYPES = frozenset()

    def can_extract(self, extension, mime_type):
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type in self.MIME_TYPES

    def extract(self, file_path, max_bytes=None):
        result = ExtractedMetadata(extractor_name=type(self).__name__, extraction_status="SUCCESS")
        sample = TextSample(0)
        try:
            if max_bytes is not None and (isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0):
                raise ValueError("max_bytes must be a non-negative integer or None")
            sample = TextSample(self.MAX_TEXT_BYTES if max_bytes is None else min(max_bytes, self.MAX_TEXT_BYTES))
            extension = os.path.splitext(os.fspath(file_path))[1].lower()
            descriptor = os.open(file_path, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("Office input must be a regular file")
                if extension in self.LEGACY_EXTENSIONS:
                    result.extraction_status = "PARTIAL"
                    result.error_message = "Legacy binary/RTF metadata parsing is not available"
                    return result
                if stream.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    result.extraction_status = "PARTIAL"
                    result.error_message = "Compound binary container (possibly encrypted Office) is not supported"
                    return result
                stream.seek(0)
                with closing(OfficePackage(stream, time.monotonic() + self.TIMEOUT_SECONDS)) as package:
                    odf = extension in self.ODF_EXTENSIONS
                    self._properties(package, result, "meta.xml" if odf else "docProps/core.xml")
                    if odf:
                        self._odf(package, result, sample)
                    else:
                        self._content(package, result, sample)
                    if package.warnings:
                        result.extraction_status = "PARTIAL"
                        result.error_message = "; ".join(dict.fromkeys(package.warnings))[:512]
        except InspectionLimit as exc:
            result.extraction_status, result.error_message = "PARTIAL", str(exc)
        except TimeoutError as exc:
            result.extraction_status, result.error_message = "TIMEOUT", str(exc)
        except (zipfile.BadZipFile, ET.ParseError, UnsafeDocument) as exc:
            result.extraction_status, result.error_message = "CORRUPTED", str(exc)[:512]
        except RuntimeError as exc:
            result.extraction_status = "ENCRYPTED" if "encrypt" in str(exc).lower() else "FAILED"
            result.error_message = str(exc)[:512]
        except Exception as exc:
            result.extraction_status, result.error_message = "FAILED", str(exc)[:512]
        result.text_preview = sample.text[:1024]
        if not result.keywords:
            result.keywords = TextExtractor._extract_keywords(sample.text)
        return result

    @staticmethod
    def _properties(package, result, path):
        root = package.xml(path, optional=True, root_tag="document-meta" if path == "meta.xml" else "coreProperties")
        if root is None:
            return
        mapping = {"title": "title", "creator": "author", "initial-creator": "author",
                   "subject": "subject", "created": "created_date", "creation-date": "created_date",
                   "modified": "modified_date", "date": "modified_date"}
        for node in root.iter():
            name = local(node.tag)
            text = redact_url_text("".join(node.itertext()).strip())
            if name in mapping and text and not getattr(result, mapping[name]):
                setattr(result, mapping[name], text[:64 if mapping[name].endswith("date") else 256])
            elif name in ("keyword", "keywords"):
                for word in re.split(r"[,;\n]+", text):
                    if word.strip() and len(result.keywords) < 20:
                        result.keywords.append(word.strip()[:128])


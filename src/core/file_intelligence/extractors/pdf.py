"""Offline PDF extraction with a killable, resource-limited parser worker.

The optional pypdf backend reads at most five pages. Without it, a bounded
standard-library fallback recovers strings from a classic trailer /Info
dictionary; it never guesses page text or claims complete PDF validation.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Optional

from src.core.file_intelligence.privacy import redact_url_text
from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor
from src.core.file_intelligence.extractors.text import TextExtractor


_WORKER_CODE = (
    "from src.core.file_intelligence.extractors.pdf import _worker_main; "
    "_worker_main()"
)
_FALLBACK_BYTES = 1024 * 1024
_MAX_HEADINGS = 64
_MEMORY_BYTES = 512 * 1024 * 1024


def _result(status, message="", **fields):
    return ExtractedMetadata(
        extractor_name="PdfExtractor", extraction_status=status,
        error_message=message, **fields,
    )


def _clean(value, limit=256):
    if value is None:
        return None
    text = redact_url_text(str(value).replace("\x00", "").strip())
    return text[:limit] or None


def _keywords(value, text=""):
    if value:
        words = re.split(r"[,;\n]+", redact_url_text(str(value)))
        return list(dict.fromkeys(w.strip()[:128] for w in words if w.strip()))[:20]
    return TextExtractor._extract_keywords(text)


class PdfExtractor(BaseExtractor):
    """Extract PDF metadata in a worker killed and reaped after three seconds.

    ``max_bytes`` bounds the UTF-8 text sample, not the PDF container size.
    The worker also has a 512 MiB address-space cap on supported Linux systems.
    No source file is written, and no persistent worker or timer is created.
    """

    SUPPORTED_EXTENSIONS = frozenset([".pdf"])
    MAX_PAGES = 5

    def can_extract(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type == "application/pdf"

    def extract(self, file_path: str, max_bytes: Optional[int] = None) -> ExtractedMetadata:
        try:
            if max_bytes is not None and (
                isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0
            ):
                raise ValueError("max_bytes must be a non-negative integer or None")
            limit = self.MAX_TEXT_BYTES if max_bytes is None else min(max_bytes, self.MAX_TEXT_BYTES)
            request = {"path": os.fsdecode(os.fspath(file_path)), "limit": limit,
                       "timeout": self.TIMEOUT_SECONDS}
            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[4])
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH")]))
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            worker = subprocess.run(
                [sys.executable, "-B", "-c", _WORKER_CODE],
                input=json.dumps(request), text=True, encoding="utf-8",
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=self.TIMEOUT_SECONDS, check=False, env=env,
            )
            if worker.returncode:
                return _result("FAILED", f"PDF worker exited with code {worker.returncode}")
            return ExtractedMetadata.from_dict(json.loads(worker.stdout))
        except subprocess.TimeoutExpired:
            return _result("TIMEOUT", f"PDF extraction exceeded {self.TIMEOUT_SECONDS:g} seconds")
        except Exception as exc:
            return _result("FAILED", str(exc))


def _extract_pdf(stream, limit):
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, PdfReadError
    except ImportError:
        return _extract_fallback(stream)

    try:
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            return _result("ENCRYPTED", "PDF requires a password")
        info = reader.metadata or {}
        fields = {
            "title": _clean(info.get("/Title")),
            "author": _clean(info.get("/Author")),
            "subject": _clean(info.get("/Subject")),
            "created_date": _clean(info.get("/CreationDate"), 64),
            "modified_date": _clean(info.get("/ModDate"), 64),
        }
        headings = []
        errors = []
        try:
            # Traverse boundedly and guard against malformed cyclic outlines.
            stack = [iter(reader.outline)]
            seen = set()
            visited = 0
            while stack and len(headings) < _MAX_HEADINGS and visited < 512:
                item = next(stack[-1], None)
                if item is None:
                    stack.pop()
                    continue
                visited += 1
                if isinstance(item, list):
                    if id(item) not in seen:
                        seen.add(id(item))
                        stack.append(iter(item))
                else:
                    title = _clean(item.get("/Title"))
                    if title:
                        headings.append(title)
        except Exception:
            errors.append("Some PDF outline entries could not be read")

        parts = []
        remaining = limit
        for index in range(PdfExtractor.MAX_PAGES):
            if remaining <= 0:
                break
            try:
                page = reader.pages[index]
            except IndexError:
                break
            try:
                text = page.extract_text() or ""
                if parts:
                    text = "\n" + text
                sample = text.encode("utf-8")[:remaining]
                parts.append(sample.decode("utf-8", errors="ignore"))
                remaining -= len(sample)
            except Exception:
                errors.append(f"Text on page {index + 1} could not be read")
        text = "".join(parts)
        if not fields["title"]:
            fields["title"] = next((_clean(line) for line in text.splitlines() if line.strip()), None)
        return _result(
            "PARTIAL" if errors else "SUCCESS", "; ".join(errors),
            **fields, headings=headings, text_preview=text[:1024],
            keywords=_keywords(info.get("/Keywords"), text),
        )
    except FileNotDecryptedError:
        return _result("ENCRYPTED", "PDF requires a password")
    except PdfReadError as exc:
        return _result("CORRUPTED", str(exc)[:256])


def _read_string(data, start):
    """Read a bounded PDF literal/hex string, including nested/escaped brackets."""
    if data[start:start + 1] == b"<" and data[start:start + 2] != b"<<":
        end = data.find(b">", start + 1)
        if end < 0:
            raise ValueError("Unterminated PDF hex string")
        digits = re.sub(rb"\s", b"", data[start + 1:end])
        if len(digits) % 2:
            digits += b"0"
        return bytes.fromhex(digits.decode("ascii")), end + 1
    if data[start:start + 1] != b"(":
        return None, start
    out = bytearray()
    pos, depth = start + 1, 1
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while pos < len(data):
        char = data[pos]
        pos += 1
        if char == 92:
            if pos >= len(data):
                break
            char = data[pos]
            pos += 1
            if char in (10, 13):
                if char == 13 and data[pos:pos + 1] == b"\n":
                    pos += 1
            elif 48 <= char <= 55:
                digits = bytes([char])
                for _ in range(2):
                    if pos < len(data) and 48 <= data[pos] <= 55:
                        digits += data[pos:pos + 1]
                        pos += 1
                out.append(int(digits, 8) & 255)
            else:
                out.append(escapes.get(char, char))
        elif char == 40:
            depth += 1
            out.append(char)
        elif char == 41:
            depth -= 1
            if depth == 0:
                return bytes(out), pos
            out.append(char)
        else:
            out.append(char)
    raise ValueError("Unterminated PDF literal string")


def _info_strings(data):
    fields = {}
    pos, depth = 0, 0
    names = {b"Title", b"Author", b"Subject", b"Keywords", b"CreationDate", b"ModDate"}
    while pos < len(data):
        if data[pos:pos + 2] == b"<<":
            depth += 1
            pos += 2
        elif data[pos:pos + 2] == b">>":
            depth -= 1
            pos += 2
            if depth == 0:
                break
        elif data[pos:pos + 1] == b"%":
            end = re.search(rb"[\r\n]", data[pos:])
            pos = pos + end.end() if end else len(data)
        elif data[pos:pos + 1] in (b"(", b"<"):
            _, pos = _read_string(data, pos)
        elif data[pos:pos + 1] == b"/":
            match = re.match(rb"/([A-Za-z]+)\b\s*", data[pos:])
            if not match:
                pos += 1
                continue
            pos += match.end()
            raw, end = _read_string(data, pos)
            if raw is not None:
                if depth == 1 and match.group(1) in names:
                    encoding = "utf-16" if raw.startswith((b"\xfe\xff", b"\xff\xfe")) else "latin-1"
                    fields["/" + match.group(1).decode("ascii")] = raw.decode(encoding, errors="replace")
                pos = end
        else:
            pos += 1
    return fields


def _extract_fallback(stream):
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    half = _FALLBACK_BYTES // 2
    stream.seek(0)
    chunks = [stream.read(min(size, half))]
    if size > half:
        stream.seek(max(half, size - half))
        chunks.append(stream.read(half))
    if not chunks[0].startswith(b"%PDF-") or b"%%EOF" not in chunks[-1]:
        return _result("CORRUPTED", "Missing PDF header or end marker")
    trailers = list(re.finditer(rb"trailer\s*<<(.*?)>>", chunks[-1], re.S))
    if not trailers:
        return _result("PARTIAL", "pypdf unavailable; classic PDF trailer not found")
    trailer = trailers[-1].group(1)
    if re.search(rb"/Encrypt\b", trailer):
        return _result("ENCRYPTED", "Encrypted PDF cannot be read by the fallback parser")
    reference = re.search(rb"/Info\s+(\d+)\s+(\d+)\s+R\b", trailer)
    info = {}
    if reference:
        pattern = rb"(?<!\d)" + reference.group(1) + rb"\s+" + reference.group(2) + rb"\s+obj\s*(<<.*?)endobj"
        for chunk in chunks:
            for match in re.finditer(pattern, chunk, re.S):
                info = _info_strings(match.group(1))
    return _result(
        "PARTIAL", "pypdf unavailable; bounded /Info metadata only (no page text)",
        title=_clean(info.get("/Title")), author=_clean(info.get("/Author")),
        subject=_clean(info.get("/Subject")), keywords=_keywords(info.get("/Keywords")),
        created_date=_clean(info.get("/CreationDate"), 64),
        modified_date=_clean(info.get("/ModDate"), 64),
    )


def _worker_main():
    """Private JSON worker entry point; limits apply before importing pypdf."""
    import contextlib
    import resource

    try:
        request = json.load(sys.stdin)
        _, memory_hard = resource.getrlimit(resource.RLIMIT_AS)
        memory = _MEMORY_BYTES if memory_hard == resource.RLIM_INFINITY else min(_MEMORY_BYTES, memory_hard)
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        cpu = max(1, math.ceil(request["timeout"]))
        _, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
        if cpu_hard != resource.RLIM_INFINITY:
            cpu = min(cpu, cpu_hard)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        # Discard parser diagnostics, keeping stdout exclusively for bounded JSON.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            descriptor = os.open(request["path"], os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("PDF input must be a regular file")
                result = _extract_pdf(stream, request["limit"])
    except MemoryError:
        result = _result("FAILED", "PDF worker exceeded its memory budget")
    except Exception as exc:
        result = _result("FAILED", str(exc)[:256])
    print(json.dumps(result.to_dict(), ensure_ascii=True))

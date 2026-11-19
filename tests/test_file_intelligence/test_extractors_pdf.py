"""Phase 04: synthetic PDFs, optional-backend isolation, and real deadlines."""

from concurrent.futures import ThreadPoolExecutor
import io
import os
from pathlib import Path
import sys
import time

import pytest

from src.core.file_intelligence.extractors import PdfExtractor, ExtractorRegistry
from src.core.file_intelligence.extractors import pdf


def _pdf_bytes(pages=("Database lecture notes",), info=b"<< /Title (Database Lecture) /Author (Ada) /Subject (DBMS) /Keywords (database; lecture) /CreationDate (D:20261114090000) >>"):
    """Build a small, valid PDF with standard-library code and exact xref offsets."""
    info_id = 4 + 2 * len(pages)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count " + str(len(pages)).encode() + b" /Kids [" +
        b" ".join(str(4 + 2 * i).encode() + b" 0 R" for i in range(len(pages))) + b"] >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(pages):
        content_id = 5 + 2 * index
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents " + str(content_id).encode() + b" 0 R >>"
        )
        raw = text.encode("latin-1").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        content = b"BT /F1 12 Tf 72 720 Td (" + raw + b") Tj ET"
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    if info is not None:
        objects.append(info)
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(b"xref\n0 " + str(len(offsets)).encode() + b"\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(b"trailer\n<< /Size " + str(len(offsets)).encode() + b" /Root 1 0 R")
    if info is not None:
        output.extend(b" /Info " + str(info_id).encode() + b" 0 R")
    output.extend(b" >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n")
    return bytes(output)


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "lecture.pdf"
    path.write_bytes(_pdf_bytes())
    return path


@pytest.fixture
def primary():
    return pytest.importorskip("pypdf")


@pytest.fixture
def missing_backend(tmp_path, monkeypatch):
    location = tmp_path / "without-pypdf"
    location.mkdir()
    (location / "pypdf.py").write_text("raise ImportError('simulated missing optional backend')\n")
    monkeypatch.setenv("PYTHONPATH", str(location) + os.pathsep + os.environ.get("PYTHONPATH", ""))


class TestPdfDispatch:
    @pytest.mark.parametrize("extension,mime", [
        (".pdf", "application/octet-stream"), (".PDF", ""), (".bin", "application/pdf")
    ])
    def test_supported(self, extension, mime):
        assert PdfExtractor().can_extract(extension, mime)

    def test_unsupported(self):
        assert not PdfExtractor().can_extract(".docx", "application/msword")

    def test_registry_registration(self, document):
        assert isinstance(ExtractorRegistry().get_extractor(str(document)), PdfExtractor)

    def test_registry_magic_signature(self, document):
        path = document.with_suffix(".unknown")
        path.write_bytes(document.read_bytes())
        assert isinstance(ExtractorRegistry().get_extractor(str(path)), PdfExtractor)


class TestPdfPrimary:
    def test_metadata_and_text(self, document, primary):
        before = document.stat()
        meta = ExtractorRegistry().extract_metadata(str(document))
        assert meta.extraction_status == "SUCCESS", meta.error_message
        assert meta.extractor_name == "PdfExtractor"
        assert meta.title == "Database Lecture"
        assert meta.author == "Ada"
        assert meta.subject == "DBMS"
        assert meta.created_date == "D:20261114090000"
        assert meta.keywords == ["database", "lecture"]
        assert "Database lecture notes" in meta.text_preview
        assert document.read_bytes() == _pdf_bytes()
        assert document.stat().st_mtime_ns == before.st_mtime_ns

    def test_title_and_keywords_from_text(self, document, primary):
        document.write_bytes(_pdf_bytes(pages=("Normalization normalization transactions",), info=None))
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title == "Normalization normalization transactions"
        assert meta.keywords[0] == "normalization"

    def test_nested_outline(self, document, primary):
        writer = primary.PdfWriter(clone_from=str(document))
        parent = writer.add_outline_item("DBMS Course", 0)
        writer.add_outline_item("Normalization", 0, parent=parent)
        with document.open("wb") as stream:
            writer.write(stream)
        meta = PdfExtractor().extract(document)
        assert meta.headings == ["DBMS Course", "Normalization"]

    def test_five_page_limit(self, document, primary):
        document.write_bytes(_pdf_bytes(pages=("first", "second", "third", "fourth", "fifth", "forbiddensixth"), info=None))
        meta = PdfExtractor().extract(document)
        assert "fifth" in meta.text_preview
        assert "forbiddensixth" not in meta.text_preview
        assert "forbiddensixth" not in meta.keywords

    @pytest.mark.parametrize("limit", [None, 64 * 1024, 10**12])
    def test_hard_text_budget(self, document, primary, limit):
        document.write_bytes(_pdf_bytes(pages=("database " * 8000 + "outsidebudget",), info=None))
        meta = PdfExtractor().extract(document, max_bytes=limit)
        assert meta.extraction_status == "SUCCESS", meta.error_message
        assert len(meta.text_preview) <= 1024
        assert "outsidebudget" not in meta.keywords

    @pytest.mark.parametrize("limit", [0, 12])
    def test_small_text_budget_preserves_metadata(self, document, primary, limit):
        meta = PdfExtractor().extract(document, max_bytes=limit)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title == "Database Lecture"
        assert len(meta.text_preview.encode("utf-8")) <= limit

    def test_encrypted(self, document, primary):
        writer = primary.PdfWriter(clone_from=str(document))
        writer.encrypt("secret")
        with document.open("wb") as stream:
            writer.write(stream)
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "ENCRYPTED"
        assert meta.text_preview == ""
        assert meta.title is None

    def test_blank_page(self, document, primary):
        writer = primary.PdfWriter()
        writer.add_blank_page(612, 792)
        with document.open("wb") as stream:
            writer.write(stream)
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "SUCCESS"
        assert meta.text_preview == ""

    def test_thread_callers(self, tmp_path, primary):
        paths = [tmp_path / "first.pdf", tmp_path / "second.pdf"]
        for path in paths:
            path.write_bytes(_pdf_bytes(info=b"<< /Title (" + path.stem.encode() + b") >>"))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(PdfExtractor().extract, paths))
        assert [r.title for r in results] == ["first", "second"]
        assert all(r.extraction_status == "SUCCESS" for r in results)


class TestPdfFallback:
    def test_optional_dependency_missing(self, document, missing_backend):
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "PARTIAL", meta.error_message
        assert meta.title == "Database Lecture"
        assert meta.author == "Ada"
        assert meta.subject == "DBMS"
        assert meta.keywords == ["database", "lecture"]
        assert meta.text_preview == ""
        assert "pypdf unavailable" in meta.error_message

    def test_import_failure_branch(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pypdf", None)
        meta = pdf._extract_pdf(io.BytesIO(_pdf_bytes()), 65536)
        assert meta.extraction_status == "PARTIAL"
        assert meta.title == "Database Lecture"

    @pytest.mark.parametrize("title,expected", [
        (rb"(Nested (title) and \(escaped\) \101)", "Nested (title) and (escaped) A"),
        (b"<FEFF00440042004D0053>", "DBMS"),
        (b"(one" + bytes([92, 10]) + b"two)", "onetwo"),
    ])
    def test_pdf_strings(self, document, missing_backend, title, expected):
        document.write_bytes(_pdf_bytes(info=b"<< /Title " + title + b" >>"))
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "PARTIAL", meta.error_message
        assert meta.title == expected

    def test_only_referenced_info_is_metadata(self, document, missing_backend):
        document.write_bytes(_pdf_bytes(pages=("/Title (Untrusted page content)",), info=None))
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "PARTIAL"
        assert meta.title is None

    def test_names_inside_strings_are_not_fields(self, document, missing_backend):
        document.write_bytes(_pdf_bytes(info=b"<< /Title (Example /Author (Not an author)) >>"))
        meta = PdfExtractor().extract(document)
        assert meta.title == "Example /Author (Not an author)"
        assert meta.author is None

    def test_bounded_container_read(self):
        class BoundedStream(io.BytesIO):
            read_total = 0

            def read(self, size=-1):
                assert 0 <= size <= pdf._FALLBACK_BYTES // 2
                data = super().read(size)
                self.read_total += len(data)
                return data

        data = _pdf_bytes(pages=("x" * (2 * pdf._FALLBACK_BYTES),))
        stream = BoundedStream(data)
        meta = pdf._extract_fallback(stream)
        assert meta.title == "Database Lecture"
        assert meta.extraction_status == "PARTIAL"
        assert stream.read_total <= pdf._FALLBACK_BYTES

    def test_encrypted_trailer(self, document, missing_backend):
        data = _pdf_bytes().replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 99 0 R")
        document.write_bytes(data)
        assert PdfExtractor().extract(document).extraction_status == "ENCRYPTED"


class TestPdfFailures:
    @pytest.mark.parametrize("raw", [b"", b"not a pdf", b"%PDF-1.4\nbroken"])
    def test_corrupted(self, document, raw):
        document.write_bytes(raw)
        assert PdfExtractor().extract(document).extraction_status == "CORRUPTED"

    @pytest.mark.parametrize("raw", [b"", b"not a pdf", b"%PDF-1.4\nbroken"])
    def test_corrupted_fallback(self, document, missing_backend, raw):
        document.write_bytes(raw)
        assert PdfExtractor().extract(document).extraction_status == "CORRUPTED"

    def test_missing_file(self, tmp_path):
        assert PdfExtractor().extract(tmp_path / "absent.pdf").extraction_status == "FAILED"

    def test_directory(self, tmp_path):
        assert PdfExtractor().extract(tmp_path).extraction_status == "FAILED"

    def test_fifo_does_not_block(self, tmp_path):
        path = tmp_path / "pipe.pdf"
        os.mkfifo(path)
        meta = PdfExtractor().extract(path)
        assert meta.extraction_status == "FAILED"
        assert "regular file" in meta.error_message

    @pytest.mark.parametrize("limit", [-1, 1.5, "64", True])
    def test_invalid_limit(self, document, monkeypatch, limit):
        def unexpected_worker(*args, **kwargs):
            pytest.fail("Invalid limit reached worker startup")

        monkeypatch.setattr(pdf.subprocess, "run", unexpected_worker)
        meta = PdfExtractor().extract(document, max_bytes=limit)
        assert meta.extraction_status == "FAILED"
        assert "max_bytes" in meta.error_message

    def test_timeout_kills_and_reaps_worker(self, document, tmp_path, monkeypatch):
        location = tmp_path / "slow-backend" / "pypdf"
        location.mkdir(parents=True)
        pid_path = tmp_path / "worker.pid"
        (location / "__init__.py").write_text(
            "import os, time\n"
            "class PdfReader:\n"
            " def __init__(self, *args, **kwargs):\n"
            f"  with open({str(pid_path)!r}, 'w') as f: f.write(str(os.getpid()))\n"
            "  time.sleep(60)\n"
        )
        (location / "errors.py").write_text(
            "class PdfReadError(Exception): pass\n"
            "class FileNotDecryptedError(Exception): pass\n"
        )
        monkeypatch.setenv("PYTHONPATH", str(location.parent))
        monkeypatch.setattr(PdfExtractor, "TIMEOUT_SECONDS", 0.5)
        started = time.monotonic()
        meta = PdfExtractor().extract(document)
        elapsed = time.monotonic() - started
        assert meta.extraction_status == "TIMEOUT", meta.error_message
        assert elapsed < 2
        pid = int(pid_path.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    def test_worker_crash_is_captured(self, document, monkeypatch):
        monkeypatch.setattr(pdf, "_WORKER_CODE", "import os; os._exit(7)")
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "FAILED"
        assert "code 7" in meta.error_message

    def test_worker_resource_limits(self, document, tmp_path, monkeypatch):
        location = tmp_path / "limited-backend" / "pypdf"
        location.mkdir(parents=True)
        (location / "__init__.py").write_text(
            "import resource\n"
            "class PdfReader:\n"
            " is_encrypted = False\n"
            " outline = []\n"
            " pages = []\n"
            " def __init__(self, *args, **kwargs):\n"
            "  memory = resource.getrlimit(resource.RLIMIT_AS)[0]\n"
            "  cpu = resource.getrlimit(resource.RLIMIT_CPU)[0]\n"
            "  self.metadata = {'/Title': str(memory), '/Subject': str(cpu)}\n"
        )
        (location / "errors.py").write_text(
            "class PdfReadError(Exception): pass\n"
            "class FileNotDecryptedError(Exception): pass\n"
        )
        monkeypatch.setenv("PYTHONPATH", str(location.parent))
        meta = PdfExtractor().extract(document)
        assert meta.extraction_status == "SUCCESS", meta.error_message
        assert 0 < int(meta.title) <= pdf._MEMORY_BYTES
        assert 0 < int(meta.subject) <= PdfExtractor.TIMEOUT_SECONDS

    def test_broken_worker_protocol(self, document, monkeypatch):
        monkeypatch.setattr(pdf, "_WORKER_CODE", "print('not JSON')")
        assert PdfExtractor().extract(document).extraction_status == "FAILED"

    def test_worker_isolation_from_gui(self):
        source = Path(pdf.__file__).read_text()
        assert "PyQt" not in source
        assert "QApplication" not in source


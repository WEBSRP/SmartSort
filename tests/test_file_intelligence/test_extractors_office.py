"""Phase 05 synthetic Office packages; no Office SDK or personal data needed."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from html import escape
import os
import struct
import zipfile

import pytest

from src.core.file_intelligence.extractors import (
    DocxExtractor, PptxExtractor, XlsxExtractor, ExtractorRegistry,
)
from src.core.file_intelligence.extractors._office import OfficePackage


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _core(title="Course Notes"):
    return (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
        f'<dc:title>{escape(title)}</dc:title><dc:creator>Ada</dc:creator><dc:subject>DBMS</dc:subject>'
        '<cp:keywords>database; normalization</cp:keywords>'
        '<dcterms:created>2026-11-14T09:00:00Z</dcterms:created></cp:coreProperties>'
    )


def _zip(path, parts, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return path


def _word(paragraphs):
    content = "".join(
        '<w:p><w:pPr><w:pStyle w:val="' + escape(style, quote=True) + '"/></w:pPr>'
        '<w:r><w:t>' + escape(text) + '</w:t></w:r></w:p>'
        for style, text in paragraphs
    )
    return f'<w:document xmlns:w="{W}"><w:body>{content}</w:body></w:document>'


def _docx(path, paragraphs=(("Title", "Database Systems"), ("Heading1", "Normalization"), ("", "Lecture body")), core=True):
    parts = {"word/document.xml": _word(paragraphs)}
    if core:
        parts["docProps/core.xml"] = _core()
    return _zip(path, parts)


def _slide(title, body):
    # Body deliberately precedes title in XML document order.
    return (
        f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree>'
        f'<p:sp><p:txBody><a:p><a:r><a:t>{escape(body)}</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:nvPr><p:ph type="ctrTitle"/></p:nvPr></p:nvSpPr>'
        f'<p:txBody><a:p><a:r><a:t>{escape(title)}</a:t></a:r></a:p></p:txBody></p:sp>'
        '</p:spTree></p:cSld></p:sld>'
    )


def _pptx(path, titles=("Slide One", "Slide Two"), core=True):
    parts = {f"ppt/slides/slide{i}.xml": _slide(title, f"body{i}") for i, title in enumerate(titles, 1)}
    ids = "".join(f'<p:sldId id="{255+i}" r:id="r{i}"/>' for i in range(1, len(titles)+1))
    parts["ppt/presentation.xml"] = f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>'
    parts["ppt/_rels/presentation.xml.rels"] = f'<Relationships xmlns="{REL}">' + "".join(
        f'<Relationship Id="r{i}" Type="{R}/slide" Target="slides/slide{i}.xml"/>' for i in range(1, len(titles)+1)
    ) + '</Relationships>'
    if core:
        parts["docProps/core.xml"] = _core()
    return _zip(path, parts)


def _xlsx_parts():
    return {
        "docProps/core.xml": _core(),
        "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="Overview" sheetId="1" r:id="rSheet"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{REL}"><Relationship Id="rSheet" Type="{R}/worksheet" Target="worksheets/custom.xml"/></Relationships>',
        "xl/worksheets/custom.xml": f'<worksheet xmlns="{S}"><sheetData><row r="1">'
            '<c r="A1" t="s"><v>1</v></c><c r="B1" t="inlineStr"><is><t>Amount</t></is></c>'
            '<c r="C1"><f>WEBSERVICE("https://example.invalid")</f><v>42</v></c></row>'
            '<row r="2"><c t="inlineStr"><is><t>privatebodyvalue</t></is></c></row></sheetData></worksheet>',
        "xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><t>Unused secret</t></si><si><r><t>Customer</t></r><r><t> Name</t></r></si></sst>',
    }


def _odf(path, kind):
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" '
          'xmlns:dc="http://purl.org/dc/elements/1.1/"')
    content = {
        "odt": '<office:text><text:h>Document Heading</text:h><text:p>Document body</text:p></office:text>',
        "odp": '<office:presentation><draw:page><draw:frame presentation:class="title"><text:p>Slide Heading</text:p></draw:frame><text:p>Slide body</text:p></draw:page></office:presentation>',
        "ods": '<office:spreadsheet><table:table table:name="Budget"><table:table-row><table:table-cell><text:p>Cost</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell><text:p>ignoredbody</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>',
    }[kind]
    return _zip(path, {
        "meta.xml": f'<office:document-meta {ns}><office:meta><dc:title>ODF Title</dc:title><dc:creator>Ada</dc:creator></office:meta></office:document-meta>',
        "content.xml": f'<office:document-content {ns}><office:body>{content}</office:body></office:document-content>',
    })


class TestOfficeDispatch:
    @pytest.mark.parametrize("extension,extractor", [
        (".docx", DocxExtractor), (".DOCX", DocxExtractor), (".doc", DocxExtractor),
        (".rtf", DocxExtractor), (".odt", DocxExtractor), (".pptx", PptxExtractor),
        (".ppt", PptxExtractor), (".odp", PptxExtractor), (".xlsx", XlsxExtractor),
        (".xls", XlsxExtractor), (".ods", XlsxExtractor),
    ])
    def test_extensions(self, extension, extractor):
        assert extractor().can_extract(extension, "")
        assert isinstance(ExtractorRegistry().get_extractor("example" + extension), extractor)

    @pytest.mark.parametrize("extractor,mime", [
        (DocxExtractor, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (PptxExtractor, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (XlsxExtractor, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ])
    def test_mime_dispatch(self, extractor, mime):
        assert extractor().can_extract(".bin", mime)
        assert not extractor().can_extract(".pdf", "application/pdf")


class TestDocx:
    def test_metadata_headings_and_preview(self, tmp_path):
        path = _docx(tmp_path / "lecture.docx")
        before = path.read_bytes()
        modified = path.stat().st_mtime_ns
        result = ExtractorRegistry().extract_metadata(str(path))
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.extractor_name == "DocxExtractor"
        assert (result.title, result.author, result.subject) == ("Course Notes", "Ada", "DBMS")
        assert result.created_date == "2026-11-14T09:00:00Z"
        assert result.keywords == ["database", "normalization"]
        assert result.headings == ["Normalization"]
        assert "Lecture body" in result.text_preview
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == modified

    def test_title_style_preferred_to_heading(self, tmp_path):
        path = _docx(tmp_path / "title.docx", (("Heading1", "First Heading"), ("Heading1", "Second Heading"), ("Title", "Document Title")), core=False)
        assert DocxExtractor().extract(path).title == "Document Title"

    def test_first_heading_preferred(self, tmp_path):
        path = _docx(tmp_path / "title.docx", (("Heading1", "First Heading"), ("Heading1", "Second Heading")), core=False)
        assert DocxExtractor().extract(path).title == "First Heading"

    def test_twenty_paragraph_limit(self, tmp_path):
        paragraphs = [("Heading1", f"Chapter {i}") for i in range(20)] + [("Heading1", "forbiddenparagraph")]
        result = DocxExtractor().extract(_docx(tmp_path / "limit.docx", paragraphs))
        assert len(result.headings) == 20
        assert "forbiddenparagraph" not in result.headings
        assert "forbiddenparagraph" not in result.keywords

    def test_unicode_and_text_limit(self, tmp_path):
        result = DocxExtractor().extract(_docx(tmp_path / "unicode.docx", (("", "数据库资料" * 1000),)), max_bytes=12)
        assert result.extraction_status == "SUCCESS"
        assert len(result.text_preview.encode("utf-8")) <= 12
        assert "数据库" in result.text_preview

    def test_hard_sample_cap(self, tmp_path):
        path = _docx(tmp_path / "sample.docx", (("", "database " * 8000 + "outsidebudget"),), core=False)
        result = DocxExtractor().extract(path, max_bytes=10**12)
        assert result.extraction_status == "SUCCESS"
        assert len(result.text_preview) == 1024
        assert "outsidebudget" not in result.keywords


class TestPptx:
    def test_titles_and_slide_limits(self, tmp_path):
        path = _pptx(tmp_path / "slides.pptx", tuple(f"Title {i}" for i in range(1, 7)), core=False)
        result = PptxExtractor().extract(path)
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.title == "Title 1"
        assert result.headings == [f"Title {i}" for i in range(1, 6)]
        assert "body3" in result.text_preview
        assert "body4" not in result.text_preview
        assert "Title 6" not in result.text_preview

    def test_relationship_order(self, tmp_path):
        path = _pptx(tmp_path / "order.pptx", core=False)
        with zipfile.ZipFile(path) as archive:
            parts = {n: archive.read(n) for n in archive.namelist()}
        parts["ppt/_rels/presentation.xml.rels"] = parts["ppt/_rels/presentation.xml.rels"].replace(b"slides/slide1.xml", b"slides/slide10.xml")
        parts["ppt/slides/slide10.xml"] = parts.pop("ppt/slides/slide1.xml")
        result = PptxExtractor().extract(_zip(path, parts))
        assert result.title == "Slide One"
        assert result.headings == ["Slide One", "Slide Two"]


class TestXlsx:
    def test_relationships_shared_strings_and_headers(self, tmp_path):
        path = _zip(tmp_path / "budget.xlsx", _xlsx_parts())
        result = XlsxExtractor().extract(path)
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.title == "Course Notes"
        assert result.headings == ["Overview", "Customer Name", "Amount", "42"]
        assert "privatebodyvalue" not in result.text_preview
        assert "Unused secret" not in result.text_preview
        assert "WEBSERVICE" not in result.text_preview

    def test_sheet_name_title_fallback(self, tmp_path):
        parts = _xlsx_parts()
        del parts["docProps/core.xml"]
        result = XlsxExtractor().extract(_zip(tmp_path / "budget.xlsx", parts))
        assert result.title == "Overview"

    def test_large_worksheet_stops_after_header(self, tmp_path):
        parts = _xlsx_parts()
        parts["xl/worksheets/custom.xml"] = parts["xl/worksheets/custom.xml"].replace("privatebodyvalue", "z" * (1024 * 1024))
        result = XlsxExtractor().extract(_zip(tmp_path / "large.xlsx", parts))
        assert result.extraction_status == "SUCCESS", result.error_message
        assert "Customer Name" in result.headings

    def test_missing_shared_string_is_partial(self, tmp_path):
        parts = _xlsx_parts()
        del parts["xl/sharedStrings.xml"]
        result = XlsxExtractor().extract(_zip(tmp_path / "missing.xlsx", parts))
        assert result.extraction_status == "PARTIAL"
        assert "Amount" in result.headings


class TestOfficeCompatibility:
    @pytest.mark.parametrize("kind,extractor,heading", [
        ("odt", DocxExtractor, "Document Heading"), ("odp", PptxExtractor, "Slide Heading"),
        ("ods", XlsxExtractor, "Cost"),
    ])
    def test_opendocument(self, tmp_path, kind, extractor, heading):
        result = extractor().extract(_odf(tmp_path / ("document." + kind), kind))
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.title == "ODF Title"
        assert result.author == "Ada"
        assert heading in result.headings
        assert "ignoredbody" not in result.text_preview

    @pytest.mark.parametrize("extension,extractor", [
        ("doc", DocxExtractor), ("rtf", DocxExtractor), ("ppt", PptxExtractor), ("xls", XlsxExtractor),
    ])
    def test_legacy_inputs_are_honest_partial_results(self, tmp_path, extension, extractor):
        path = tmp_path / ("legacy." + extension)
        path.write_bytes(b"legacy binary data")
        result = extractor().extract(path)
        assert result.extraction_status == "PARTIAL"
        assert "not available" in result.error_message
        assert result.title is None
        assert result.text_preview == ""

    def test_no_optional_office_dependency_required(self, tmp_path, monkeypatch):
        paths = [_docx(tmp_path / "a.docx"), _pptx(tmp_path / "b.pptx"), _zip(tmp_path / "c.xlsx", _xlsx_parts())]
        original = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"docx", "pptx", "openpyxl", "odf", "lxml"}:
                raise ImportError("Optional Office SDK unavailable")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded)
        results = [cls().extract(path) for cls, path in zip((DocxExtractor, PptxExtractor, XlsxExtractor), paths)]
        assert all(r.extraction_status == "SUCCESS" for r in results)

    def test_concurrent_callers(self, tmp_path):
        paths = [_docx(tmp_path / "first.docx", (("Title", "First"),), core=False),
                 _docx(tmp_path / "second.docx", (("Title", "Second"),), core=False)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(DocxExtractor().extract, paths))
        assert [r.title for r in results] == ["First", "Second"]


class TestOfficeSafety:
    @pytest.mark.parametrize("extractor,extension", [(DocxExtractor, "docx"), (PptxExtractor, "pptx"), (XlsxExtractor, "xlsx")])
    def test_corrupted_zip(self, tmp_path, extractor, extension):
        path = tmp_path / ("broken." + extension)
        path.write_bytes(b"not a zip file")
        assert extractor().extract(path).extraction_status == "CORRUPTED"

    @pytest.mark.parametrize("encoding,padding", [("utf-8", 0), ("utf-16", 0), ("utf-8", 4093)])
    def test_dtd_rejected_including_split_declarations(self, tmp_path, encoding, padding):
        xml = ' ' * padding + '<!DOCTYPE root [<!ENTITY x "expanded">]><root>&x;</root>'
        path = _zip(tmp_path / "dtd.docx", {"word/document.xml": xml.encode(encoding)})
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "CORRUPTED"
        assert "DTD/entity" in result.error_message

    def test_malformed_xml(self, tmp_path):
        path = _zip(tmp_path / "invalid.docx", {"word/document.xml": '<document><p>unterminated'})
        assert DocxExtractor().extract(path).extraction_status == "CORRUPTED"

    def test_global_decompression_budget(self, tmp_path, monkeypatch):
        path = _docx(tmp_path / "large.docx", (("", "x" * (2 * OfficePackage.MAX_XML_BYTES)),))
        total = []
        original = zipfile.ZipExtFile.read

        def bounded_read(stream, size=-1):
            assert 0 <= size <= 4096
            value = original(stream, size)
            total.append(len(value))
            return value

        monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded_read)
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "PARTIAL"
        assert result.title == "Course Notes"
        assert sum(total) <= OfficePackage.MAX_XML_BYTES

    def test_budget_is_shared_across_slides(self, tmp_path, monkeypatch):
        path = _pptx(tmp_path / "budget.pptx", tuple(f"Slide {i}" for i in range(5)))
        monkeypatch.setattr(OfficePackage, "MAX_XML_BYTES", 2000)
        result = PptxExtractor().extract(path)
        assert result.extraction_status == "PARTIAL"
        assert "budget" in result.error_message
        assert result.title == "Course Notes"

    @pytest.mark.parametrize("target,mode", [("../../../escape.xml", ""), ("https://example.invalid/headers", ' TargetMode="External"')])
    def test_relationships_cannot_escape_or_fetch(self, tmp_path, target, mode):
        parts = _xlsx_parts()
        parts["xl/_rels/workbook.xml.rels"] = f'<Relationships xmlns="{REL}"><Relationship Id="rSheet" Type="{R}/worksheet" Target="{target}"{mode}/></Relationships>'
        result = XlsxExtractor().extract(_zip(tmp_path / "unsafe.xlsx", parts))
        assert result.extraction_status == ("PARTIAL" if mode else "CORRUPTED")
        assert "privatebodyvalue" not in result.text_preview

    def test_zip_entries_never_written_to_disk(self, tmp_path):
        path = _docx(tmp_path / "safe.docx")
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("../escaped.txt", "do not extract")
        before = set(tmp_path.iterdir())
        assert DocxExtractor().extract(path).extraction_status == "SUCCESS"
        assert set(tmp_path.iterdir()) == before

    @pytest.mark.parametrize("limit", [-1, 1.5, "64", True])
    def test_invalid_budget_before_open(self, monkeypatch, limit):
        def unexpected_open(*args, **kwargs):
            pytest.fail("Invalid budget reached file I/O")

        monkeypatch.setattr(os, "open", unexpected_open)
        result = DocxExtractor().extract("unused.docx", max_bytes=limit)
        assert result.extraction_status == "FAILED"
        assert "max_bytes" in result.error_message

    def test_missing_and_non_regular_inputs(self, tmp_path):
        assert DocxExtractor().extract(tmp_path / "missing.docx").extraction_status == "FAILED"
        assert DocxExtractor().extract(tmp_path).extraction_status == "FAILED"
        fifo = tmp_path / "pipe.docx"
        os.mkfifo(fifo)
        assert DocxExtractor().extract(fifo).extraction_status == "FAILED"

    def test_oversized_zip_index_rejected_before_loading(self, tmp_path):
        path = _docx(tmp_path / "index.docx")
        data = bytearray(path.read_bytes())
        offset = data.rfind(b"PK\x05\x06")
        struct.pack_into("<H", data, offset + 10, 10001)
        path.write_bytes(data)
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "PARTIAL"
        assert "ZIP index" in result.error_message

    def test_zero_sample_preserves_metadata(self, tmp_path):
        result = DocxExtractor().extract(_docx(tmp_path / "zero.docx"), max_bytes=0)
        assert result.extraction_status == "SUCCESS"
        assert result.title == "Course Notes"
        assert result.text_preview == ""

    def test_metadata_field_bounds(self, tmp_path):
        path = _zip(tmp_path / "bounds.docx", {
            "docProps/core.xml": _core("x" * 2000),
            "word/document.xml": _word((("Heading1", "h" * 2000),)),
        })
        result = DocxExtractor().extract(path)
        assert len(result.title) == 256
        assert len(result.headings[0]) == 256
        assert len(result.text_preview) == 1024

    def test_encrypted_zip_member(self, tmp_path):
        path = _docx(tmp_path / "encrypted.docx", core=False)
        data = bytearray(path.read_bytes())
        offset = data.find(b"PK\x01\x02")
        flags = struct.unpack_from("<H", data, offset + 8)[0]
        struct.pack_into("<H", data, offset + 8, flags | 1)
        path.write_bytes(data)
        assert DocxExtractor().extract(path).extraction_status == "ENCRYPTED"

    def test_compound_container_is_partial(self, tmp_path):
        path = tmp_path / "protected.docx"
        path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"compound container")
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "PARTIAL"
        assert "possibly encrypted" in result.error_message

    def test_missing_required_part(self, tmp_path):
        path = _zip(tmp_path / "missing.docx", {"docProps/core.xml": _core()})
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "CORRUPTED"
        assert "word/document.xml" in result.error_message

    def test_wrong_xml_part_type(self, tmp_path):
        path = _zip(tmp_path / "wrong.docx", {"word/document.xml": '<unrelated/>'})
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "CORRUPTED"
        assert "Unexpected XML root" in result.error_message

    def test_cooperative_deadline(self, tmp_path, monkeypatch):
        path = _docx(tmp_path / "timeout.docx")
        monkeypatch.setattr(DocxExtractor, "TIMEOUT_SECONDS", -1)
        result = DocxExtractor().extract(path)
        assert result.extraction_status == "TIMEOUT"


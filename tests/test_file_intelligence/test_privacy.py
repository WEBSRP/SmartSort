"""Privacy regressions: redact URLs before derived tokens and cache reuse."""

from html import escape
import json
import sqlite3
import zipfile

import pytest

from src.core.file_intelligence import ExtractedMetadata, MetadataCache
from src.core.file_intelligence.extractors import ExtractorRegistry
from src.core.file_intelligence.extractors.text import TextExtractor
from src.core.file_intelligence.extractors.docx import DocxExtractor
from src.core.file_intelligence.extractors.pptx import PptxExtractor
from src.core.file_intelligence.extractors.xlsx import XlsxExtractor


PRIVATE_URLS = (
    'https://PrivateUser:PrivatePassword@example.com/file;session=PrivateMatrix?invoice=PrivateQuery&auth=PrivateOther#PrivateFragment',
    'https://%50rivateUser:%50rivatePassword@example.com/file;%73ession=%50rivateMatrix?invoice=%50rivateQuery#%50rivateFragment',
)
SAFE_URL = 'https://example.com/file'


@pytest.fixture(autouse=True)
def privacy_cache_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg-cache'))


def assert_no_private_url_parts(metadata):
    serialized = json.dumps(metadata.to_dict()).casefold()
    assert 'private' not in serialized
    # Percent-encoded leading P must not leave truncated tokens like 'rivatequery'.
    assert 'rivate' not in serialized
    assert '%50' not in serialized
    assert 'session=' not in serialized
    assert '?invoice=' not in serialized
    assert '?auth=' not in serialized


def privacy_pdf_bytes(title, keywords, body='Ordinary document body'):
    def literal(value):
        return value.encode('latin-1').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
    stream = b'BT /F1 12 Tf 30 100 Td (' + literal(body) + b') Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Title (' + literal(title) + b') /Keywords (' + literal(keywords) + b') >>',
    ]
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, content in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(str(index).encode() + b' 0 obj\n' + content + b'\nendobj\n')
    xref = len(output)
    output.extend(b'xref\n0 7\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010} 00000 n \n'.encode())
    output.extend(b'trailer\n<< /Size 7 /Root 1 0 R /Info 6 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n')
    return bytes(output)


def privacy_office_package(path, title, keywords):
    core = (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{escape(title)}</dc:title><cp:keywords>{escape(keywords)}</cp:keywords>'
        '</cp:coreProperties>'
    )
    parts = {'docProps/core.xml': core}
    if path.suffix == '.docx':
        parts['word/document.xml'] = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Ordinary document body</w:t></w:r></w:p></w:body></w:document>'
        )
    elif path.suffix == '.pptx':
        parts['ppt/slides/slide1.xml'] = (
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Ordinary slide body</a:t>'
            '</a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
        )
    else:
        parts['xl/workbook.xml'] = (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets/></workbook>'
        )
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return path


@pytest.mark.parametrize('private_url', PRIVATE_URLS, ids=['raw', 'encoded'])
def test_text_url_redaction_precedes_tokens_beyond_visible_preview(tmp_path, private_url):
    path = tmp_path / 'sample.md'
    path.write_text('# Ordinary title\n' + ('ordinary ' * 180) + '\n' + private_url + '\nrepository backend frontend')
    direct = TextExtractor().extract(str(path))
    assert direct.extraction_status == 'SUCCESS'
    assert private_url not in direct.text_preview  # The URL is beyond the 1 KiB display sample.
    assert 'repository' in direct.keywords
    assert_no_private_url_parts(direct)
    result = ExtractorRegistry(cache=False).extract_metadata(str(path))
    assert_no_private_url_parts(result)


@pytest.mark.parametrize('extension,extractor', [('.docx', DocxExtractor), ('.pptx', PptxExtractor), ('.xlsx', XlsxExtractor)])
@pytest.mark.parametrize('private_url', PRIVATE_URLS, ids=['raw', 'encoded'])
def test_office_property_urls_redacted_before_keyword_delimiter_split(tmp_path, extension, extractor, private_url):
    path = privacy_office_package(tmp_path / ('document' + extension), private_url,
                                  'safealpha; ' + private_url + ', safeomega')
    direct = extractor().extract(str(path))
    assert direct.extraction_status in ('SUCCESS', 'PARTIAL')
    # Test the derived list directly: post-tokenization string redaction is too late.
    keyword_json = json.dumps(direct.keywords).casefold()
    assert 'private' not in keyword_json and 'rivate' not in keyword_json
    assert 'safealpha' in direct.keywords and 'safeomega' in direct.keywords
    result = ExtractorRegistry(cache=False).extract_metadata(str(path))
    assert result.title == SAFE_URL
    assert_no_private_url_parts(result)


@pytest.mark.parametrize('private_url', PRIVATE_URLS, ids=['raw', 'encoded'])
def test_pdf_title_and_explicit_keyword_urls_redacted_before_split(tmp_path, private_url):
    path = tmp_path / 'document.pdf'
    path.write_bytes(privacy_pdf_bytes(private_url, 'safealpha; ' + private_url + ', safeomega'))
    result = ExtractorRegistry(cache=False).extract_metadata(str(path))
    assert result.extraction_status in ('SUCCESS', 'PARTIAL')
    assert result.title == SAFE_URL
    assert 'safealpha' in result.keywords and 'safeomega' in result.keywords
    assert_no_private_url_parts(result)


@pytest.mark.parametrize('private_url', PRIVATE_URLS, ids=['raw', 'encoded'])
def test_code_intro_and_import_url_symbols_are_normalized_before_keywords(tmp_path, private_url):
    path = tmp_path / 'module.js'
    path.write_text('// Resource ' + private_url + '\nimport resource from "' + private_url + '";\nfunction load_assets() { return resource; }\n')
    result = ExtractorRegistry(cache=False).extract_metadata(str(path))
    assert result.extraction_status == 'SUCCESS'
    assert 'load_assets' in result.code_symbols
    assert SAFE_URL in result.code_symbols
    assert_no_private_url_parts(result)


class PrivacyUnavailableCache:
    def __init__(self, fail_on):
        self.fail_on = fail_on

    def get(self, *args, **kwargs):
        if self.fail_on == 'read':
            raise OSError('cache unavailable')
        return None

    def put(self, *args, **kwargs):
        if self.fail_on == 'write':
            raise OSError('cache unavailable')


@pytest.mark.parametrize('cache_mode', ['enabled', 'disabled', 'read-failure', 'write-failure'])
@pytest.mark.parametrize('encoding,status', [('utf8', 'SUCCESS'), ('latin1', 'PARTIAL'), ('corrupt-office', 'CORRUPTED')])
def test_cold_warm_metadata_equal_with_cache_disabled_or_unavailable(tmp_path, cache_mode, encoding, status):
    if encoding == 'corrupt-office':
        path = tmp_path / 'document.docx'
        path.write_bytes(b'not a ZIP document')
    else:
        path = tmp_path / 'sample.md'
        raw = ('# ' + PRIVATE_URLS[0] + '\nrepository backend frontend source code').encode()
        path.write_bytes(raw + (b'\n\xe9' if encoding == 'latin1' else b''))
    cache = True if cache_mode == 'enabled' else False if cache_mode == 'disabled' else PrivacyUnavailableCache(cache_mode.split('-')[0])
    registry = ExtractorRegistry(cache=cache)
    first = registry.extract_metadata(str(path))
    second = registry.extract_metadata(str(path))
    assert first.extraction_status == second.extraction_status == status
    assert first.to_dict() == second.to_dict()
    assert_no_private_url_parts(first)
    assert_no_private_url_parts(second)


@pytest.mark.parametrize('cache_enabled', [False, True])
def test_failed_and_timeout_statuses_preserved_by_privacy_boundary(tmp_path, cache_enabled):
    registry = ExtractorRegistry(cache=cache_enabled)
    missing = registry.extract_metadata(str(tmp_path / 'missing.md'))
    assert missing.extraction_status == 'FAILED'
    path = tmp_path / 'sample.md'
    path.write_text('# ' + PRIVATE_URLS[0])
    result = registry.extract_metadata(str(path), timeout_seconds=0)
    assert result.extraction_status == 'TIMEOUT'


def test_cache_schema_one_derived_tokens_are_discarded_on_upgrade(tmp_path):
    path = tmp_path / 'metadata_cache.db'
    with MetadataCache(path) as cache:
        cache.put('sample.md', 10, 2, 123.5, 100,
                  ExtractedMetadata(title='Legacy document', keywords=['legacyprivatekeyword'], extraction_status='SUCCESS'))
    with sqlite3.connect(path) as database:
        database.execute('PRAGMA user_version=1')
    with MetadataCache(path) as current:
        assert current.SCHEMA_VERSION >= 2
        assert current.get('sample.md', 10, 123.5, 100) is None
    with sqlite3.connect(path) as database:
        assert database.execute('SELECT count(*) FROM file_metadata_cache').fetchone()[0] == 0


@pytest.mark.parametrize('cache_enabled', [False, True])
def test_bounded_worker_returns_same_redacted_metadata_on_reuse(tmp_path, cache_enabled):
    path = tmp_path / 'sample.md'
    path.write_text('# ' + PRIVATE_URLS[1] + '\nrepository backend frontend source code')
    registry = ExtractorRegistry(cache=cache_enabled)
    first = registry.extract_metadata(str(path), timeout_seconds=2)
    second = registry.extract_metadata(str(path), timeout_seconds=2)
    assert first.extraction_status == second.extraction_status == 'SUCCESS'
    assert first.to_dict() == second.to_dict()
    assert first.title == SAFE_URL
    assert_no_private_url_parts(first)
    assert_no_private_url_parts(second)


def test_code_keyword_privacy_extends_beyond_intro_preview(tmp_path):
    path = tmp_path / 'module.py'
    comments = '# ordinary documentation\n' * 80
    path.write_text(comments + '# ' + PRIVATE_URLS[0] + '\ndef load_assets():\n    return None\n')
    result = ExtractorRegistry(cache=False).extract_metadata(str(path))
    assert result.extraction_status == 'SUCCESS'
    assert result.code_language == 'Python' and 'load_assets' in result.code_symbols
    assert PRIVATE_URLS[0] not in result.text_preview
    assert_no_private_url_parts(result)


@pytest.mark.parametrize('text,expected', [
    ('[Click](https://example.com)', '[Click](https://example.com)'),
    ('[Click](https://example.com/a?token=PrivateQuery)', '[Click](https://example.com/a)'),
    ('[Click](https://example.com/(nested)?token=PrivateQuery)', '[Click](https://example.com/(nested))'),
    ('https://[::1]/a?token=PrivateQuery', 'https://[::1]/a'),
    ('safealpha; https://example.com/a;session=PrivateMatrix?token=PrivateQuery, safeomega',
     'safealpha; https://example.com/a, safeomega'),
])
def test_redaction_preserves_markdown_delimiters_and_balanced_url_parts(text, expected):
    from src.core.file_intelligence.privacy import redact_url_text
    result = redact_url_text(text)
    assert result == expected
    assert redact_url_text(result) == result


def test_metadata_normalization_does_not_mutate_caller_or_source(tmp_path):
    from src.core.file_intelligence.privacy import normalize_metadata
    original = ExtractedMetadata(title=PRIVATE_URLS[0], keywords=['safe'],
                                 exif_tags={'Make': 'Camera', 'GPSLatitude': 'synthetic-coordinate'})
    before = original.to_dict()
    result = normalize_metadata(original)
    assert original.to_dict() == before
    assert result.title == SAFE_URL and result.exif_tags == {'Make': 'Camera'}
    assert normalize_metadata(result).to_dict() == result.to_dict()
    result.keywords.append('changed')
    assert original.keywords == ['safe']

"""Phase 07: real source fixtures, archive listings, and resource boundaries."""
import concurrent.futures
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import time
import zipfile

import pytest

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors import ArchiveExtractor, CodeExtractor, ExtractorRegistry
from src.core.file_intelligence.extractors._binary import HeaderReader


def source(tmp_path, name='sample.py', text='def report():\n    pass\n'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return path


def make_zip(path, names=('project/main.py', 'docs/lecture.pptx', 'docs/notes.pdf'), compression=zipfile.ZIP_STORED):
    with zipfile.ZipFile(path, 'w', compression=compression) as archive:
        for name in names:
            archive.writestr(name, b'payload')
    return path


def make_tar(path, mode='w', names=('project/main.py', 'docs/lecture.pptx'), payload=b'payload'):
    with tarfile.open(path, mode) as archive:
        for name in names:
            entry = tarfile.TarInfo(name)
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
    return path


@pytest.mark.parametrize('extension,language,text,symbols', [
    ('.py', 'Python', 'import os\nfrom collections import Counter\nclass Report:\n async def build(self): pass', ['os','collections','Report','build']),
    ('.c', 'C', '#include <stdio.h>\nint main(void) { return 0; }', ['stdio.h','main']),
    ('.cpp', 'C++', '#include "report.hpp"\nclass Report {};\nint main() { return 0; }', ['report.hpp','Report','main']),
    ('.h', 'C', 'struct Report { int value; };', ['Report']),
    ('.hpp', 'C++', 'class Report {};', ['Report']),
    ('.java', 'Java', 'import java.util.List;\npublic class Report {\npublic void build() {}\n}', ['java.util.List','Report','build']),
    ('.js', 'JavaScript', 'import helper from "report-kit";\nexport function build() {}\nconst render = () => {};', ['helper','report-kit','build','render']),
    ('.ts', 'TypeScript', 'interface Report {}\nexport async function build() {}', ['Report','build']),
    ('.go', 'Go', 'package main\nimport (\n "fmt"\n "net/http"\n)\nfunc (r Report) Build() {}', ['fmt','net/http','Build']),
    ('.rs', 'Rust', 'use std::io;\npub struct Report {}\npub fn build() {}', ['std::io','Report','build']),
    ('.sh', 'Shell', '#!/bin/sh\nreport() {\n echo hello\n}', ['report']),
    ('.bash', 'Shell', 'function report() {\n echo hello\n}', ['report']),
    ('.sql', 'SQL', 'CREATE TABLE reports (id INTEGER);\ncreate or replace function build() RETURNS INT;', ['reports','build']),
    ('.php', 'PHP', '<?php\nclass Report {}\nfunction build() {}', ['Report','build']),
])
def test_source_languages_and_symbols(tmp_path, extension, language, text, symbols):
    path = source(tmp_path, 'sample' + extension, text)
    meta = ExtractorRegistry().extract_metadata(path)
    assert meta.extractor_name == 'CodeExtractor'
    assert meta.extraction_status == 'SUCCESS'
    assert meta.code_language == language
    assert set(symbols) <= set(meta.code_symbols)


def test_python_docstring_sections_and_false_symbols(tmp_path):
    path = source(tmp_path, text='''#!/usr/bin/env python3
# coding: utf-8
"""Monthly reporting.
Build the finance report offline.
class Fake: pass
"""
# --- Database Configuration ---
import sqlite3
message = "def imaginary(): pass"
# class Pretend: pass
class MonthlyReport:
    def generate(self):
        return "done"
''')
    meta = CodeExtractor().extract(path)
    assert meta.title == 'Monthly reporting.'
    assert 'finance' in meta.keywords
    assert 'Database Configuration' in meta.headings
    assert {'sqlite3','MonthlyReport','generate'} <= set(meta.code_symbols)
    assert not {'Fake','imaginary','Pretend'} & set(meta.code_symbols)


def test_cpp_block_comment_and_string_masking(tmp_path):
    path = source(tmp_path, 'report.cpp', '''/* Report generator.
 * --- Database Layer ---
 * class Fake {};
 */
#include <vector>
const char *s = "class Pretend {}";
class Report {};
void build() {}
''')
    meta = CodeExtractor().extract(path)
    assert 'Report generator.' in meta.text_preview
    assert 'Database Layer' in meta.headings
    assert 'Fake' not in meta.code_symbols
    assert 'Pretend' not in meta.code_symbols


@pytest.mark.parametrize('shebang,language', [
    ('#!/usr/bin/env -S python3 -u', 'Python'),
    ('#!/usr/bin/python3.13', 'Python'),
    ('#!/bin/bash', 'Shell'),
    ('#!/usr/bin/env node', 'JavaScript'),
])
def test_shebang_detection(tmp_path, shebang, language):
    assert CodeExtractor().extract(source(tmp_path, 'script', shebang + '\n')).code_language == language


def test_source_never_executes_or_imports(tmp_path):
    marker = tmp_path / 'executed'
    path = source(tmp_path, text=f'from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError("do not run")\n')
    assert CodeExtractor().extract(path).extraction_status == 'SUCCESS'
    assert not marker.exists()


def test_code_line_limit(tmp_path):
    path = source(tmp_path, text='\n' * 199 + 'def included(): pass\ndef excluded(): pass\n')
    meta = CodeExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert 'included' in meta.code_symbols
    assert 'excluded' not in meta.code_symbols


def test_code_byte_output_and_symbol_limits(tmp_path):
    path = source(tmp_path, text='"""' + 'report ' * 20000 + '"""\n')
    meta = CodeExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert len(meta.text_preview) <= 1024
    assert len(meta.title) <= 256
    assert len(meta.keywords) <= 20
    path.write_text('\n'.join(f'def report_{i}(): pass' for i in range(200)))
    meta = CodeExtractor().extract(path)
    assert len(meta.code_symbols) == 128


def test_code_small_and_zero_budget(tmp_path):
    path = source(tmp_path)
    assert CodeExtractor().extract(path, max_bytes=0).extraction_status == 'PARTIAL'
    assert CodeExtractor().extract(path, max_bytes=4).code_symbols == []
    assert CodeExtractor().extract(path, max_bytes=10**9).extraction_status == 'SUCCESS'


@pytest.mark.parametrize('encoding', ['utf-8-sig','utf-16','latin-1'])
def test_code_encodings(tmp_path, encoding):
    path = tmp_path / 'encoding.py'
    path.write_bytes('"""Résumé report."""\ndef build(): pass\n'.encode(encoding))
    meta = CodeExtractor().extract(path)
    assert 'build' in meta.code_symbols
    assert 'Résumé' in meta.text_preview
    assert meta.extraction_status == ('PARTIAL' if encoding == 'latin-1' else 'SUCCESS')


def test_binary_code_is_partial(tmp_path):
    path = tmp_path / 'binary.py'
    path.write_bytes(b'\x00\x01def fake(): pass')
    meta = CodeExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert not meta.code_symbols


@pytest.mark.parametrize('extractor', [CodeExtractor, ArchiveExtractor])
@pytest.mark.parametrize('limit', [-1, True, False, 1.5, '100'])
def test_invalid_limits_are_failed(tmp_path, extractor, limit):
    meta = extractor().extract(source(tmp_path), max_bytes=limit)
    assert meta.extraction_status == 'FAILED'
    assert 'max_bytes' in meta.error_message


@pytest.mark.parametrize('extractor', [CodeExtractor, ArchiveExtractor])
def test_missing_and_nonregular_inputs(tmp_path, extractor):
    assert extractor().extract(tmp_path / 'missing').extraction_status == 'FAILED'
    assert extractor().extract(tmp_path).extraction_status == 'FAILED'
    fifo = tmp_path / 'pipe'
    os.mkfifo(fifo)
    assert extractor().extract(fifo).extraction_status == 'FAILED'


@pytest.mark.parametrize('extractor', [CodeExtractor, ArchiveExtractor])
def test_permission_failure_is_captured(tmp_path, monkeypatch, extractor):
    import src.core.file_intelligence.extractors._binary as binary
    path = source(tmp_path)
    def denied(*args, **kwargs):
        raise PermissionError('Permission denied')
    monkeypatch.setattr(binary.os, 'open', denied)
    assert extractor().extract(path).extraction_status == 'FAILED'


@pytest.mark.parametrize('extractor', [CodeExtractor, ArchiveExtractor])
def test_deadline_is_reported(tmp_path, extractor):
    path = source(tmp_path)
    instance = extractor()
    instance.TIMEOUT_SECONDS = -1
    assert instance.extract(path).extraction_status == 'TIMEOUT'


@pytest.mark.parametrize('suffix,mode', [('tar','w'),('tar.gz','w:gz'),('tgz','w:gz'),('tar.bz2','w:bz2'),('tar.xz','w:xz')])
def test_tar_formats_and_compound_registry_dispatch(tmp_path, suffix, mode):
    path = make_tar(tmp_path / ('bundle.' + suffix), mode)
    meta = ExtractorRegistry().extract_metadata(path)
    assert meta.extractor_name == 'ArchiveExtractor'
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['project/main.py','docs/lecture.pptx']
    assert meta.headings == ['project','docs']
    assert meta.keywords == ['code_project','presentation','course_material']


@pytest.mark.parametrize('compression', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_zip_listing_does_not_depend_on_payload_codec(tmp_path, compression):
    path = make_zip(tmp_path / 'bundle.zip', compression=compression)
    meta = ExtractorRegistry().extract_metadata(path)
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['project/main.py','docs/lecture.pptx','docs/notes.pdf']
    assert {'document','presentation','code_project'} <= set(meta.keywords)


def test_zip_comments_unicode_and_self_extracting_prefix(tmp_path):
    path = make_zip(tmp_path / 'bundle.zip', ['résumé/文档.pdf'])
    with zipfile.ZipFile(path, 'a') as archive:
        archive.comment = b'contains misleading PK\x05\x06 signature and comment text'
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['résumé/文档.pdf']
    path.write_bytes(b'#!/bin/sh\n' + path.read_bytes())
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['résumé/文档.pdf']


@pytest.mark.parametrize('kind', ['zip','tar','tar.gz'])
def test_archive_over_500_entries_is_partial(tmp_path, kind):
    names = [f'project/file_{i}.py' for i in range(700)]
    if kind == 'zip':
        path = make_zip(tmp_path / 'many.zip', names)
    else:
        path = make_tar(tmp_path / ('many.' + kind), 'w:gz' if kind.endswith('gz') else 'w', names, b'')
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert len(meta.toc_entries) == 500
    assert meta.toc_entries[-1] == 'project/file_499.py'


def test_encrypted_zip_flag_without_opening_members(tmp_path):
    path = make_zip(tmp_path / 'encrypted.zip')
    data = bytearray(path.read_bytes())
    for signature, flag_offset in ((b'PK\x03\x04',6),(b'PK\x01\x02',8)):
        pos = 0
        while (pos := data.find(signature, pos)) >= 0:
            struct.pack_into('<H', data, pos + flag_offset, 1)
            pos += 4
    path.write_bytes(data)
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'ENCRYPTED'
    assert 'project/main.py' in meta.toc_entries


@pytest.mark.parametrize('suffix', ['zip','tar','tar.gz','tar.bz2','tar.xz','7z'])
def test_corrupted_archives(tmp_path, suffix):
    path = tmp_path / ('bad.' + suffix)
    path.write_bytes(b'not a valid archive')
    assert ArchiveExtractor().extract(path).extraction_status == 'CORRUPTED'


def test_corrupt_zip_central_header_retains_earlier_entries(tmp_path):
    path = make_zip(tmp_path / 'bad.zip')
    data = bytearray(path.read_bytes())
    first = data.index(b'PK\x01\x02')
    second = data.index(b'PK\x01\x02', first + 4)
    data[second] = 0
    path.write_bytes(data)
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'CORRUPTED'
    assert meta.toc_entries == ['project/main.py']


def test_invalid_zip_utf8_name_is_corrupted(tmp_path):
    path = make_zip(tmp_path / 'bad.zip', ['x.py'])
    data = bytearray(path.read_bytes())
    central = data.index(b'PK\x01\x02')
    struct.pack_into('<H',data,central+8,0x800)
    data[central+46] = 0xff
    path.write_bytes(data)
    assert ArchiveExtractor().extract(path).extraction_status == 'CORRUPTED'


def test_empty_zip_and_tar(tmp_path):
    assert ArchiveExtractor().extract(make_zip(tmp_path/'empty.zip',[])).extraction_status == 'SUCCESS'
    assert ArchiveExtractor().extract(make_tar(tmp_path/'empty.tar', names=[])).extraction_status == 'SUCCESS'


@pytest.mark.parametrize('kind', ['zip','tar'])
def test_unsafe_member_names_are_not_retained_or_materialized(tmp_path, kind):
    names = ['../../escape.py','/absolute.py','C:\\outside.py','bad\x01name.py','safe/main.py']
    path = make_zip(tmp_path/'unsafe.zip',names) if kind == 'zip' else make_tar(tmp_path/'unsafe.tar', names=names)
    before = set(tmp_path.rglob('*'))
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert meta.toc_entries == ['safe/main.py']
    assert set(tmp_path.rglob('*')) == before


def test_zip_payloads_never_opened_and_tar_members_never_extracted(tmp_path, monkeypatch):
    zip_path = make_zip(tmp_path/'bundle.zip')
    tar_path = make_tar(tmp_path/'bundle.tar.gz','w:gz')
    def forbidden(*args, **kwargs):
        pytest.fail('Member payload API called')
    monkeypatch.setattr(zipfile.ZipFile,'open',forbidden)
    monkeypatch.setattr(zipfile.ZipFile,'infolist',forbidden)
    monkeypatch.setattr(tarfile.TarFile,'extract',forbidden)
    monkeypatch.setattr(tarfile.TarFile,'extractall',forbidden)
    monkeypatch.setattr(tarfile.TarFile,'extractfile',forbidden)
    monkeypatch.setattr(tarfile.TarFile,'getmembers',forbidden)
    assert ArchiveExtractor().extract(zip_path).extraction_status == 'SUCCESS'
    assert ArchiveExtractor().extract(tar_path).extraction_status == 'SUCCESS'


def test_compressed_tar_payload_skip_has_decompressed_budget(tmp_path):
    path = make_tar(tmp_path/'bomb.tar.gz','w:gz',['large.bin','later.py'],b'\x00'*(3*1024*1024))
    started = time.monotonic()
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert meta.toc_entries == ['large.bin']
    assert 'budget' in meta.error_message
    assert time.monotonic() - started < 3


def test_plain_tar_seeks_over_large_payload(tmp_path):
    path = make_tar(tmp_path/'large.tar',names=['large.bin','later.py'],payload=b'\x00'*(3*1024*1024))
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['large.bin','later.py']


def test_oversized_pax_header_is_bounded(tmp_path):
    path = tmp_path/'pax.tar'
    header = tarfile.TarInfo('PaxHeaders/x')
    header.type = tarfile.XHDTYPE
    header.size = 100*1024*1024
    with path.open('wb') as stream:
        stream.write(header.tobuf())
        stream.truncate(header.size + 512)  # Sparse fixture, not a 100 MiB allocation.
    assert ArchiveExtractor().extract(path).extraction_status == 'PARTIAL'


def test_valid_7z_signature_is_explicit_partial(tmp_path):
    path = tmp_path/'bundle.7z'
    path.write_bytes(b"7z\xbc\xaf\x27\x1c" + b'\x00'*26)
    meta = ExtractorRegistry().extract_metadata(path)
    assert meta.extraction_status == 'PARTIAL'
    assert '7z' in meta.error_message
    assert not meta.toc_entries


def test_zip64_and_multivolume_are_explicit_partial(tmp_path):
    path = make_zip(tmp_path/'zip64.zip')
    original = path.read_bytes()
    data = bytearray(original)
    end = data.rindex(b'PK\x05\x06')
    struct.pack_into('<HH',data,end+8,65535,65535)
    path.write_bytes(data)
    assert ArchiveExtractor().extract(path).extraction_status == 'PARTIAL'
    data = bytearray(original)
    struct.pack_into('<H',data,end+4,1)
    path.write_bytes(data)
    meta = ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert 'Multi-volume' in meta.error_message


def test_archive_small_and_zero_budget(tmp_path):
    path = make_zip(tmp_path/'bundle.zip')
    for size in (0,4,20):
        meta = ArchiveExtractor().extract(path,max_bytes=size)
        assert meta.extraction_status == 'PARTIAL'
        assert not meta.toc_entries


def test_archive_budget_is_cumulative_and_cannot_be_raised(tmp_path,monkeypatch):
    path = make_zip(tmp_path/'large.zip', [f'project/{i}.py' for i in range(1000)])
    class SmallBudget(ArchiveExtractor):
        MAX_HEADER_BYTES = 100
    meta = SmallBudget().extract(path,max_bytes=10**9)
    assert meta.extraction_status == 'PARTIAL'
    assert 'budget' in meta.error_message


def test_sources_unchanged_and_concurrent_registry_calls(tmp_path):
    paths = [source(tmp_path),make_zip(tmp_path/'bundle.zip'),make_tar(tmp_path/'bundle.tar.gz','w:gz')]
    hashes = {p:hashlib.sha256(p.read_bytes()).digest() for p in paths}
    before = set(tmp_path.rglob('*'))
    registry = ExtractorRegistry()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(registry.extract_metadata,paths*4))
    assert all(r.extraction_status == 'SUCCESS' for r in results)
    assert set(tmp_path.rglob('*')) == before
    assert all(hashlib.sha256(p.read_bytes()).digest()==hashes[p] for p in paths)
    for result in results:
        assert ExtractedMetadata.from_dict(json.loads(json.dumps(result.to_dict()))).to_dict()==result.to_dict()


def test_core_import_does_not_import_qt(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    command = 'import sys; from src.core.file_intelligence.extractors import CodeExtractor, ArchiveExtractor; assert not any(k.startswith("PyQt6") for k in sys.modules)'
    env = dict(os.environ,PYTHONPATH=str(repo),PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable,'-c',command],cwd=tmp_path,env=env,check=True,timeout=10)


def test_prefixed_docstring_and_import_aliases(tmp_path):
    path = source(tmp_path, text='r"""Report generation."""\nimport os as operating_system, sys\n')
    meta = CodeExtractor().extract(path)
    assert meta.title == 'Report generation.'
    assert meta.code_symbols == ['os','sys']


def test_symbol_cap_is_partial(tmp_path):
    path = source(tmp_path,text='\n'.join(f'def report_{i}(): pass' for i in range(200)))
    assert CodeExtractor().extract(path).extraction_status == 'PARTIAL'


def test_go_import_comments_are_not_modules(tmp_path):
    path=source(tmp_path,'main.go','package main\nimport (\n// "not-a-module"\n"fmt"\n)\n')
    meta=CodeExtractor().extract(path)
    assert 'fmt' in meta.code_symbols
    assert 'not-a-module' not in meta.code_symbols


@pytest.mark.parametrize('kind', ['gz','bz2','xz'])
def test_corrupt_compressed_headers_are_reported(tmp_path,kind):
    magic={'gz':b'\x1f\x8b','bz2':b'BZh9','xz':b'\xfd7zXZ\x00'}[kind]
    path=tmp_path/('bad.tar.'+kind)
    path.write_bytes(magic+b'broken-header'*100)
    assert ArchiveExtractor().extract(path).extraction_status == 'CORRUPTED'


def test_xz_dictionary_limit_is_partial(tmp_path,monkeypatch):
    import src.core.file_intelligence.extractors.archive as module
    real = module.lzma.LZMADecompressor
    # A valid XZ tarball needs ~8 MiB. Lowering the worker's decoder ceiling
    # exercises the real liblzma memory-limit failure without allocating a bomb.
    path=make_tar(tmp_path/'limited.tar.xz','w:xz')
    def small_decoder(**kwargs):
        return real(memlimit=1024)
    monkeypatch.setattr(module.lzma,'LZMADecompressor',small_decoder)
    meta=ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert 'dictionary' in meta.error_message


def test_oversized_zip_name_is_skipped(tmp_path):
    path=make_zip(tmp_path/'long.zip',['a'*2000+'.py','safe.py'])
    meta=ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert meta.toc_entries == ['safe.py']


def test_zip_forged_directory_bounds_are_corrupted(tmp_path):
    path=make_zip(tmp_path/'bounds.zip')
    data=bytearray(path.read_bytes())
    end=data.rindex(b'PK\x05\x06')
    struct.pack_into('<I',data,end+16,len(data)*2)
    path.write_bytes(data)
    assert ArchiveExtractor().extract(path).extraction_status == 'CORRUPTED'


def test_archive_headings_and_keywords_are_unique_and_bounded(tmp_path):
    names=[f'folder_{i}/file.pdf' for i in range(100)]
    path=make_zip(tmp_path/'folders.zip',names)
    meta=ArchiveExtractor().extract(path)
    assert len(meta.headings) == 64
    assert meta.keywords == ['document']
    assert all(len(name)<=1024 for name in meta.toc_entries)


def test_tar_link_target_is_not_followed(tmp_path):
    secret=tmp_path/'secret'
    secret.write_text('do not inspect')
    path=tmp_path/'links.tar'
    with tarfile.open(path,'w') as archive:
        entry=tarfile.TarInfo('project/link')
        entry.type=tarfile.SYMTYPE
        entry.linkname=str(secret)
        archive.addfile(entry)
    meta=ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'SUCCESS'
    assert meta.toc_entries == ['project/link']
    assert 'do not inspect' not in json.dumps(meta.to_dict())
    assert secret.read_text() == 'do not inspect'


def test_extreme_source_line_stays_bounded(tmp_path):
    path=source(tmp_path,'large.cpp','a '*32768)
    started=time.monotonic()
    meta=CodeExtractor().extract(path)
    assert meta.extraction_status in ('SUCCESS','PARTIAL')
    assert time.monotonic()-started < 3


def test_large_pax_name_is_rejected_before_normalization(tmp_path):
    path=make_tar(tmp_path/'long-name.tar',names=['./'*250000+'main.py','safe.py'],payload=b'')
    started=time.monotonic()
    meta=ArchiveExtractor().extract(path)
    assert meta.extraction_status == 'PARTIAL'
    assert meta.toc_entries == ['safe.py']
    assert time.monotonic()-started < 3

# Phase 07: Source Code & Archive Inspection Extractor

## Objective
Implement `src/core/file_intelligence/extractors/code.py` (`CodeExtractor`) and `src/core/file_intelligence/extractors/archive.py` (`ArchiveExtractor`) to inspect programming source files and compressed archive tables-of-contents without uncompressing archives to disk.

## Why This Phase Exists
Archives (`.zip`, `.tar.gz`) are opaque containers. A file named `Lecture_3_DBMS.zip` or `Project_Source.zip` can only be categorized accurately by inspecting its internal structure. Similarly, source code files contain critical symbol definitions (`class`, `def`, `import`) that identify software projects.

## Inputs
- Source code file paths (`.py`, `.c`, `.cpp`, `.java`, `.js`, `.rs`, `.go`, `.sh`) and archive paths (`.zip`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.7z`).

## Outputs
- `src/core/file_intelligence/extractors/code.py` (`CodeExtractor`).
- `src/core/file_intelligence/extractors/archive.py` (`ArchiveExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_code_archive.py`.

## Files To Create
- `src/core/file_intelligence/extractors/code.py`
- `src/core/file_intelligence/extractors/archive.py`
- `tests/test_file_intelligence/test_extractors_code_archive.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Register `CodeExtractor`, `ArchiveExtractor`.
- `src/core/file_intelligence/extractors/base.py`: Register both implementations
  in the existing registry and recognize compound TAR suffixes explicitly.

## Existing Components To Reuse
- `src/core/file_intelligence/extractors/base.py`: Inherits `BaseExtractor`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/code.py
class CodeExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".py", ".c", ".cpp", ".h", ".hpp", ".java", ".js",
        ".ts", ".go", ".rs", ".sh", ".bash", ".sql", ".php"
    ])
    ...

# src/core/file_intelligence/extractors/archive.py
class ArchiveExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".7z"
    ])
    ...
```

## Data Structures
- Produces `ExtractedMetadata` populated with `code_language`, `code_symbols`, `toc_entries`, `headings`, `keywords`.

## Algorithms
- `CodeExtractor`:
  - Scans first 200 lines.
  - Regex symbol extraction for imports (`import `, `from ... import`, `#include `, `use `).
  - Class and function definitions (`class Name`, `def func`, `fn func`, `function func`).
  - Top-level docstring / block comment extraction.
- `ArchiveExtractor`:
  - Reads classic ZIP central-directory records sequentially. Avoids
    `ZipFile.infolist()`, which materializes the entire index before truncation.
  - Uses `TarFile.next()` rather than `getmembers()`; compressed TAR streams
    use bounded decoders, and plain TAR skips payloads with seeks.
  - Collects internal member paths (up to 500 entries).
  - Derives content keywords based on internal extensions (e.g. presence of `.pptx` $\rightarrow$ `presentation`, `Makefile` $\rightarrow$ `code_project`).

## Error Handling
- ZIP encryption flags in inspected central-directory records report
  `extraction_status="ENCRYPTED"` without opening member payloads.
- Corrupted archive headers return `extraction_status="CORRUPTED"`.
- 7z, ZIP64, and multi-volume ZIP listings return explicit `PARTIAL` results.
  These formats are not parsed by this standard-library implementation.

## Security Considerations
- **ZIP BOMB DEFENSE**: Member files are **never decompressed to disk**.
- Max 500 TOC entries inspected to prevent memory exhaustion on giant tarballs.
- Cumulative input reads and decompressed TAR scanning each have a 2 MiB
  ceiling. `max_bytes` may lower these budgets, never raise them. Individual
  compressed input chunks are at most 4 KiB; XZ dictionary memory is limited
  to 32 MiB. Auxiliary TAR headers are also subject to the byte budgets.
- Oversized, absolute, traversal, drive-qualified, and control-character
  member names are omitted. Link targets are not followed; nested archives
  are never recursively opened. No archive member is written to disk.
- All inputs must be regular files. Deadlines are cooperative, checked
  between reads, decoding steps, and parsing operations.

## Performance Considerations
- Header TOC inspection executes in < 10 ms per archive.

## CI / Headless Requirements
- Pure Python standard library (`zipfile`, `tarfile`, `re`). Zero Qt imports.

## Tests
- `tests/test_file_intelligence/test_extractors_code_archive.py`:
  - Test Python and C++ source code symbol extraction.
  - Test synthetic ZIP archive TOC extraction.
  - Test TAR.GZ archive TOC extraction.
  - Test archive with >500 files ensuring truncation limit is respected.
  - Test encrypted zip handling.

## Acceptance Criteria
- [x] `CodeExtractor` and `ArchiveExtractor` implemented and registered.
- [x] Zero archive files decompressed to disk during analysis.
- [x] 100% test pass on `test_extractors_code_archive.py`.

## Dependencies
- Standard library `zipfile`, `tarfile`, `re`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] Code and archive extractors created.
- [x] Unit tests passing.

## Implementation State — 2026-11-14

Phase 07 functional acceptance is complete in the local working tree.
Implementation uses only the Python standard library and the existing
`HeaderReader` and text helpers; no dependencies were added.

Implemented behavior:

- Source code: Python, C/C++, Java, JavaScript, TypeScript, Go, Rust, shell,
  SQL, and PHP extensions; supported shebangs identify Python, shell, or
  Node scripts. Inspection reads at most 64 KiB and scans at most 200 lines.
- Strings and comments are masked before lexical symbol matching. Imports,
  class/type names, and common function definitions produce unique symbols
  in encounter order. This does not execute, import, or compile source code.
- Leading docstrings/comments supply previews; section comments supply
  headings. UTF-8/BOM, UTF-16 BOM, and Latin-1 fallback are supported. Binary
  samples return `PARTIAL`. Outputs cap previews at 1,024 characters, titles
  at 256, symbols at 128 entries of 256 characters, headings at 64 entries of
  256 characters, and keywords at 20 entries of 128 characters.
- ZIP: bounded EOCD search, sequential central records, CP437/UTF-8 names,
  encryption flags, comments, empty archives, and self-extracting prefixes.
  No ZIP member payload or codec is opened, decompressed, or validated.
- TAR, TAR.GZ/TGZ, TAR.BZ2, and TAR.XZ: incremental listings with bounded
  compressed input and decoded scanning. Large plain-TAR payloads are skipped
  by seeking. Compressed tarballs may return partial listings before later
  headers if skipping a payload exhausts the decoded-byte budget.
- Listings contain at most 500 entries and bounded top-level directory names
  and content-type keywords. Unsafe names are skipped before any path use.
- Missing/inaccessible/non-regular inputs and invalid limits return `FAILED`;
  sampled/truncated/unsupported results return `PARTIAL`; malformed inspected
  structures return `CORRUPTED`; elapsed deadlines return `TIMEOUT`.

Validation on Python 3.13.5:

- **92 Phase 07 tests passed**, no failures or skips.
- **728 full-suite tests passed, 1 existing skip**, genuine pytest exit code
  **0**. Baseline was **636 passed, 1 skipped**. The existing skip remains the
  Phase 02 permission test under a privileged user.
- Tests cover all implemented source languages, misleading strings/comments,
  source execution avoidance, encodings, byte/line/symbol caps, all supported
  archive containers, compound-suffix dispatch, encryption flags, malformed
  records, oversized indexes/names/PAX reads, compressed scan budgets, actual
  liblzma memory-limit errors, unsafe paths, untouched link targets, source
  hashes, no extraction APIs, concurrent calls, serialization, and Qt-free
  imports in a fresh interpreter.
- Full-suite execution preserves pytest's actual return value before the
  existing Qt fixture's exit-zero backstop. Compilation and whitespace checks
  pass; test state and compilation output use temporary locations.

Performance observations (20 warm extractions per small synthetic fixture):

| Format | First observed call | Warm median | Warm maximum |
|---|---:|---:|---:|
| ZIP | 0.462 ms | 0.036 ms | 0.067 ms |
| TAR | 0.294 ms | 0.094 ms | 0.144 ms |
| TAR.GZ | 0.168 ms | 0.111 ms | 0.124 ms |
| TAR.BZ2 | 0.147 ms | 0.120 ms | 0.179 ms |
| TAR.XZ | 0.205 ms | 0.116 ms | 0.177 ms |
| Python source | 1.829 ms | 0.128 ms | 0.185 ms |

The archive observations meet the 10 ms target for these fixtures. They are
local measurements, not latency guarantees for every archive.

Remaining boundaries:

- Source matching is lexical, not a complete language parser. Multiline
  declarations, macro-generated symbols, unusual import syntax, or ambiguous
  headers may be incomplete. Truncated source/encoding fallback/symbol-cap
  results are explicitly partial.
- 7z, ZIP64 directories, and multi-volume ZIP are not implemented. An encrypted
  flag beyond the sampled 500 ZIP entries cannot be detected. Listing success
  is not full payload, CRC, compression-footer, or archive-integrity validation.
- TAR stops conservatively at 500 members and reports `PARTIAL` even if the
  archive contains exactly 500. Auxiliary extension headers can consume the
  byte budget before the member limit. Only the first compressed stream is
  inspected; concatenated compression streams are not fully validated.
- Deadlines are cooperative, not the PDF worker's hard process timeout.
  There is no universal process memory cap; XZ dictionary allocation and
  compressed/decoded byte limits are bounded explicitly.
- Existing organizers, safe transfer logic, GUI, packaging, and later phases
  are unchanged. Earlier pending changes remain intact. Changes are uncommitted.

Format/API references: [PKWARE ZIP specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT),
[Python tarfile](https://docs.python.org/3/library/tarfile.html), and
[Python lzma](https://docs.python.org/3/library/lzma.html).

Next implementation phase: **08 — Local Browser Download History & Origin Resolution**.

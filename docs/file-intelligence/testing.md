# SmartSort File Intelligence Engine: Testing Strategy

## 1. Testing Philosophy

The File Intelligence Engine test suite must be **100% deterministic**, **completely offline**, **independent of display servers**, and **fast (< 3 seconds total runtime)**.

All tests operate on synthetic test fixtures created dynamically in temporary directories (`tmp_path`) without requiring external network downloads or pre-existing user environments.

---

## 2. Test Suite Architecture

```text
tests/
├── conftest.py                          # Global session fixtures & qapp setup
├── test_core.py                         # Existing Core GUI & Worker tests
├── test_directory_organizer.py          # Existing Directory Organizer tests
├── test_duplicate_detection.py          # Existing Duplicate & Move tests
├── test_filename_cleanup.py             # Existing Filename Cleanup tests
├── test_notifications.py                # Existing Notification tests
└── test_file_intelligence/              # Dedicated File Intelligence Test Suite
    ├── __init__.py
    ├── test_context.py                  # FileContext, Data Models, & Enums
    ├── test_metadata.py                 # Filesystem stat & xattr extraction
    ├── test_extractors_text.py          # Plaintext, Markdown, CSV, Log
    ├── test_extractors_pdf.py           # PDF metadata & text extraction
    ├── test_extractors_office.py        # DOCX, PPTX, XLSX extraction
    ├── test_extractors_media.py         # Image (EXIF) & Audio/Video metadata
    ├── test_extractors_code_archive.py  # Code tokens & Archive TOC
    ├── test_origin.py                   # Browser DB & xattr provenance
    ├── test_signals.py                  # Tokenization & signal weighting
    ├── test_relationships.py            # Deterministic clustering algorithms
    ├── test_classifier.py               # Domain classification & scoring
    ├── test_planner.py                  # Hierarchy generation & rule precedence
    ├── test_cache.py                    # XDG persistent cache & expiry
    └── test_integration.py              # End-to-end intelligence workflows
```

---

## 3. Synthetic Fixture Generation

Tests construct minimal valid file fixtures programmatically:

### 3.1 Synthetic PDF Generation
```python
def create_sample_pdf(path: Path, title: str = "Sample Title", text: str = "Sample Content"):
    """Generates a minimal valid PDF without external network dependencies."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({
        "/Title": title,
        "/Author": "Test Author",
        "/Subject": "DBMS Course"
    })
    with open(path, "wb") as f:
        writer.write(f)
```

### 3.2 Synthetic Office DOCX Generation
```python
def create_sample_docx(path: Path, title: str = "DBMS Lecture Notes"):
    """Generates a minimal valid OOXML DOCX file using zipfile."""
    import zipfile
    core_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                       xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>{title}</dc:title>
        <dc:creator>Professor Smith</dc:creator>
    </cp:coreProperties>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("docProps/core.xml", core_xml)
        z.writestr("word/document.xml", "<w:document><w:body/></w:document>")
```

### 3.3 Synthetic Browser SQLite Database
```python
def create_mock_chrome_history(db_path: Path, target_path: str, url: str):
    """Creates a temporary Chromium History SQLite database fixture."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE downloads (
            id INTEGER PRIMARY KEY,
            target_path TEXT,
            tab_url TEXT,
            tab_referrer_url TEXT,
            start_time INTEGER,
            total_bytes INTEGER
        )
    """)
    cur.execute("INSERT INTO downloads VALUES (1, ?, ?, '', 13200000000, 1024)", (target_path, url))
    conn.commit()
    conn.close()
```

---

## 4. Acceptance Criteria & Regression Testing

1. **Zero CI Hang Guarantee**: All `test_file_intelligence/` tests must run in headless environments with `QT_QPA_PLATFORM=offscreen`.
2. **Execution Time**: The complete File Intelligence test suite must execute in under 3.0 seconds.
3. **Existing Suite Regression**: All 116 existing SmartSort unit tests must continue to pass 100% without modification.
4. **Degradation Testing**: Tests must assert that when optional libraries (`pypdf`, `python-docx`, `mutagen`, `Pillow`) are absent or mocked as `ImportError`, the engine gracefully degrades to `ConfidenceLevel.PROBABLE` or `UNKNOWN` without crashing.

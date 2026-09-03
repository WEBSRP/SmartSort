# SmartSort File Intelligence Engine: Dependencies Audit & Policy

## 1. Dependency Philosophy & Policy

SmartSort follows a strict **minimal dependency policy**:
1. **Debian Package Availability**: Every external dependency must have an official, well-maintained package in Debian (`python3-*`) and Ubuntu repositories.
2. **License Compatibility**: All libraries must be compatible with SmartSort's `GPL-3.0-or-later` license (MIT, BSD, Apache 2.0, LGPL, GPL).
3. **Pure-Python Fallbacks**: Every format extractor must implement a standard-library fallback (e.g. `zipfile` + `xml.etree.ElementTree` for Office documents) so SmartSort remains fully operational even if optional dependencies are not installed.
4. **Zero Cloud / Zero Network**: No client libraries for cloud AI APIs (OpenAI, Anthropic, Google Cloud) or external web scrapers.

---

## 2. Dependency Audit Matrix

| Library | Debian Package | License | Status | Purpose | Fallback Implementation |
|---|---|---|---|---|---|
| **`sqlite3`** | Standard Library | Python | **Built-in** | Browser DB & Metadata Cache | N/A (Standard library) |
| **`zipfile` / `tarfile`** | Standard Library | Python | **Built-in** | Archive & OOXML Inspection | N/A (Standard library) |
| **`pypdf`** | `python3-pypdf` | BSD-3-Clause | **Recommended** | PDF text & metadata extraction | Pure-Python PDF binary dictionary parser |
| **`python-docx`** | `python3-docx` | MIT | **Optional** | Word document text extraction | `zipfile` + `xml.etree.ElementTree` on `docProps/core.xml` |
| **`openpyxl`** | `python3-openpyxl` | MIT | **Optional** | Excel workbook inspection | `zipfile` + `xml.etree.ElementTree` on `docProps/core.xml` |
| **`Pillow`** | `python3-pil` | HPND | **Recommended** | Image EXIF & dimension parsing | Binary JPEG SOF & PNG IHDR header parser |
| **`mutagen`** | `python3-mutagen` | GPL-2.0+ | **Recommended** | Audio/Video ID3 & atom metadata | Binary ID3v2 & MP4 `moov` atom header parser |

---

## 3. Debian Package Dependency Configuration

In `packaging/debian/DEBIAN/control`:

```text
Package: smartsort
Version: 1.1.6
Architecture: all
Maintainer: Soumya Ranjan Parida <contact@smartsort-org.com>
Depends: python3, python3-pyqt6, python3-watchdog, python3-notify2, python3-pypdf, python3-pil, python3-mutagen, libglib2.0-0, gir1.2-notify-0.7
Suggests: python3-docx, python3-openpyxl
Description: Intelligent Download Organizer and File Intelligence Platform for Linux
```

---

## 4. Graceful Degradation Testing

Every extractor must implement self-checking import isolation:

```python
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

class PdfExtractor(BaseExtractor):
    def extract(self, file_path: str, max_bytes: Optional[int] = None) -> ExtractedMetadata:
        if PYPDF_AVAILABLE:
            return self._extract_with_pypdf(file_path)
        else:
            return self._extract_with_fallback_parser(file_path)
```

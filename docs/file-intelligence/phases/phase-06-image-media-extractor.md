# Phase 06: Image (EXIF) & Media Metadata Extractor

## Objective
Implement `src/core/file_intelligence/extractors/image.py` (`ImageExtractor`) and `src/core/file_intelligence/extractors/media.py` (`MediaExtractor`) to extract dimensions, camera metadata, audio tags (Artist, Album, Track), and video properties while enforcing strict privacy redactions.

## Why This Phase Exists
Media files require distinct handling from text documents. Knowing image dimensions (e.g. 3840x2160 wallpaper vs 500x500 avatar) or music metadata (Artist, Album) enables precise organization into `Media/Wallpapers/` or `Media/Music/{Artist}/`.

## Inputs
- Image or audio/video media file paths.

## Outputs
- `src/core/file_intelligence/extractors/image.py` (`ImageExtractor`).
- `src/core/file_intelligence/extractors/media.py` (`MediaExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_media.py`.

## Files To Create
- `src/core/file_intelligence/extractors/_binary.py`: Shared read-only,
  cumulative header-byte budget, input validation, and bounded field helpers.
- `src/core/file_intelligence/extractors/image.py`
- `src/core/file_intelligence/extractors/media.py`
- `tests/test_file_intelligence/test_extractors_media.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Export both extractors.
- `src/core/file_intelligence/extractors/base.py`: Register both extractors in
  `ExtractorRegistry._register_default_extractors()`.
- `tests/test_file_intelligence/test_extractors_text.py`: Update unsupported
  dispatch fixtures now that PNG has a registered extractor.

## Existing Components To Reuse
- `src/core/file_intelligence/extractors/base.py`: Inherits `BaseExtractor`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/image.py
class ImageExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".svg"
    ])
    ...

# src/core/file_intelligence/extractors/media.py
class MediaExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".mp4",
        ".mkv", ".avi", ".mov", ".webm", ".wmv"
    ])
    ...
```

## Data Structures
- Produces `ExtractedMetadata` populated with `dimensions`, `duration_seconds`, `exif_tags`, `author` (Artist), `subject` (Album), `title`.

## Algorithms
- `ImageExtractor`:
  - Uses `Pillow` if available, with pure binary header fallback for JPEG SOF0/SOF2 and PNG IHDR chunks.
  - EXIF Tag Extraction: Reads `Make`, `Model`, `Software`, `DateTimeOriginal`.
  - **MANDATORY PRIVACY RULE**: Explicitly deletes/ignores `GPSInfo` (Tag `34853`). GPS coordinates are never retained.
- `MediaExtractor`:
  - Uses `mutagen` if available, with pure binary fallback for ID3v2 tags (TIT2, TPE1, TALB) and MP4 atoms (`moov.udta.meta.ilst`).

## Error Handling
- Corrupted media streams return `extraction_status="PARTIAL"` with any recovered header tags.

## Security Considerations
- Memory bounded: Never decode full raw raster bitmap pixels into uncompressed memory buffers; only inspect headers and EXIF blocks.
- Native parsing and optional backends share a **64 KiB cumulative input-read
  budget**. `max_bytes` may lower that budget, never raise it. Large payloads
  can be skipped with seeks; oversized reads fail before allocation.
- EXIF output is an allowlist: Make, Model, Software, DateTime,
  DateTimeOriginal, and LensModel. GPS IFD pointers are not followed. Media
  output likewise uses allowlisted tags and omits location/private/artwork tags.
- Optional-backend exception strings are not included in output because they
  could contain private metadata values.
- PNG EXIF lookup is guarded to avoid Pillow's implicit pixel load when no
  EXIF chunk exists. WebP uses native header parsing because Pillow's opener
  reads the entire compressed file. SVG parsing stops at the root and rejects
  DTD/entity declarations; no rendering or external resolution is performed.

## Performance Considerations
- Header and EXIF extraction executes in < 5 ms per media file.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_extractors_media.py`:
  - Test PNG dimension extraction.
  - Test JPEG EXIF extraction.
  - Test that GPS metadata is strictly redacted and absent from metadata.
  - Test MP3/ID3 audio metadata extraction.
  - Test pure binary fallback paths when `Pillow` or `mutagen` are unavailable.

## Acceptance Criteria
- [x] `ImageExtractor` and `MediaExtractor` implemented and registered.
- [x] EXIF GPS coordinates strictly excluded from all outputs.
- [x] 100% test pass on `test_extractors_media.py`.

## Dependencies
- `Pillow` (`python3-pil`), `mutagen` (`python3-mutagen`), with binary fallback.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] Image and media extractors created.
- [x] Unit tests passing.

## Implementation State — 2026-11-14

Phase 06 functional acceptance is complete in the local working tree. Optional
backends were tested with Pillow **11.1.0** and Mutagen **1.47.0** on Python
**3.13.5**. No mandatory dependencies or organizing/transfer logic were changed.

Implemented paths:

- Image headers: JPEG SOF dimensions and EXIF, PNG IHDR/eXIf, WebP VP8/VP8L/VP8X
  dimensions and EXIF, GIF/BMP dimensions, classic TIFF IFDs, and SVG root
  dimensions/viewBox. Both TIFF byte orders are supported. Container dimensions
  take precedence over potentially stale EXIF/thumbnail dimensions.
- Pillow enriches supported header metadata without `load()`, pixel iteration,
  raster conversion, or save calls. WebP and SVG remain native-only.
- Native EXIF inspection follows at most IFD0 and the EXIF IFD, with at most 128
  entries each; GPS IFDs and embedded thumbnails are not traversed.
- Media fallback: ID3v2.2/2.3/2.4 text frames; MP4/M4A/MOV title, artist, album,
  encoder, duration, and track dimensions; WAV duration/INFO tags; FLAC duration
  and allowlisted Vorbis comments; AVI main-header duration/dimensions.
- MP4 traversal is limited to 512 atoms and eight levels. Other native scanners
  also cap chunk/frame counts. Large `mdat`, audio, and artwork data are skipped.
- Mutagen enriches supported stream tags and duration. Outputs use finite,
  non-negative durations and bounded strings/keyword lists; arbitrary tag
  dictionaries are never copied to results.
- Missing optional libraries, malformed/truncated streams, and unsupported
  metadata produce explicit `PARTIAL` results with recovered fields retained.
  Inaccessible/non-regular inputs return `FAILED`. Exhausted cooperative
  deadlines return `TIMEOUT`. Backend diagnostics never echo raw tag values.

Validation:

- **69 Phase 06 tests passed**, with no failures or skips.
- **603 full-suite tests passed, 1 existing skip**, genuine pytest exit code **0**.
  Baseline was **534 passed, 1 skipped**; the existing skip remains Phase 02's
  permission test under a privileged user.
- Genuine GPS-bearing JPEG fixtures were verified before testing redaction.
  Both TIFF byte orders, GPS lookup avoidance, allowlisted serialized output,
  source preservation, PNG pixel-load guards, and native WebP routing passed.
- Optional dependency failures, backend error redaction, MP3 tags, WAV duration,
  FLAC comments, MP4 atom payload skipping, invalid inputs, finite durations,
  concurrency, and cumulative byte limits are tested.
- Two earlier registry tests now use an opaque unsupported format instead of
  PNG, which is intentionally supported in this phase.
- Source compilation, syntax, and whitespace checks passed. Test state and
  compilation output used temporary locations. The full-suite runner preserved
  pytest's actual return value despite the existing Qt exit-zero hook.

Performance observations (20 warm extractions per small synthetic fixture):

| Format | First observed call | Warm median | Warm maximum |
|---|---:|---:|---:|
| PNG | 17.795 ms | 0.047 ms | 0.112 ms |
| JPEG | 1.213 ms | 0.149 ms | 0.474 ms |
| WAV | 14.482 ms | 0.129 ms | 0.206 ms |
| MP3 | 0.868 ms | 0.249 ms | 0.364 ms |

These are local observations, not universal bounds. The **5 ms target is met
for these warm fixtures but not the first PNG/WAV calls**, which load optional
backend/plugin code. JPEG followed PNG, and MP3 followed WAV, in this run.

Remaining boundaries:

- This is sampled metadata inspection, not full image/audio/video validation.
  GPS is excluded from returned metadata; source-file metadata is not modified.
- Classic TIFF only; BigTIFF, compressed EXIF/XMP profiles, and unusual metadata
  layouts may yield partial results. SVG recognizes unitless/px dimensions and
  viewBox, without rasterization.
- The native ID3 parser does not reconstruct whole-tag unsynchronization or
  encrypted/compressed/grouped frames; the optional backend may recover them.
- OGG/ASF metadata relies on Mutagen. MKV/WebM and other unrecognized streams
  can return `PARTIAL` without metadata; declared dispatch support does not
  imply a complete native parser for every codec/container.
- Read/seek deadline checks are cooperative, not a hard process timeout like
  the PDF worker. The cumulative read limit does not cap every internal
  allocation or decompression performed by optional libraries.
- Earlier pending changes remain intact. Changes are uncommitted.

Next implementation phase: **07 — Source Code & Archive Inspection Extractor**.

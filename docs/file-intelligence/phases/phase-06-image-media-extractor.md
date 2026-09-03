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
- `src/core/file_intelligence/extractors/image.py`
- `src/core/file_intelligence/extractors/media.py`
- `tests/test_file_intelligence/test_extractors_media.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Register `ImageExtractor`, `MediaExtractor`.

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
- [ ] `ImageExtractor` and `MediaExtractor` implemented and registered.
- [ ] EXIF GPS coordinates strictly excluded from all outputs.
- [ ] 100% test pass on `test_extractors_media.py`.

## Dependencies
- `Pillow` (`python3-pil`), `mutagen` (`python3-mutagen`), with binary fallback.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] Image and media extractors created.
- [ ] Unit tests passing.

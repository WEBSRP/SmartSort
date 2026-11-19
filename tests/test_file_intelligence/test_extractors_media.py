"""Phase 06 header fixtures, genuine GPS IFDs, and bounded-read invariants."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import struct
import sys
from types import SimpleNamespace
import wave
import zlib

import pytest

from src.core.file_intelligence.extractors import ImageExtractor, MediaExtractor, ExtractorRegistry
from src.core.file_intelligence.extractors._binary import HeaderReader


def _tiff(endian="<"):
    root, exif, gps, end = 8, 98, 128, 158
    data = bytearray(end)
    data[:8] = (b"II" if endian == "<" else b"MM") + struct.pack(endian + "HI", 42, root)

    def table(offset, entries):
        struct.pack_into(endian + "H", data, offset, len(entries))
        for index, (tag, kind, value) in enumerate(entries):
            if kind == 2:
                raw = value.encode("ascii") + b"\x00"
                count = len(raw)
            elif kind == 5:
                raw = b"".join(struct.pack(endian + "II", a, b) for a, b in value)
                count = len(value)
            else:
                raw = struct.pack(endian + "I", value)
                count = 1
            if len(raw) > 4:
                pointer = len(data)
                data.extend(raw)
                raw = struct.pack(endian + "I", pointer)
            entry = struct.pack(endian + "HHI", tag, kind, count) + raw.ljust(4, b"\x00")
            start = offset + 2 + index * 12
            data[start:start + 12] = entry

    table(root, [(256, 4, 400), (257, 4, 300), (271, 2, "CameraCo"),
                 (272, 2, "Model One"), (305, 2, "GIMP"), (34665, 4, exif), (34853, 4, gps)])
    table(exif, [(36867, 2, "2026:11:14 09:00:00"), (42036, 2, "Standard Lens")])
    table(gps, [(2, 5, [(51, 1), (30, 1), (12345, 1000)]),
                (4, 5, [(7, 1), (14, 1), (54321, 1000)])])
    return bytes(data)


def _jpeg(endian="<"):
    exif = b"Exif\x00\x00" + _tiff(endian)
    sof = struct.pack(">BHHB", 8, 300, 400, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    sos = b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    return (b"\xff\xd8\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif +
            b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof +
            b"\xff\xda" + struct.pack(">H", len(sos) + 2) + sos + b"\xff\xd9")


def _png(exif=False):
    def chunk(kind, raw):
        return struct.pack(">I", len(raw)) + kind + raw + struct.pack(">I", zlib.crc32(kind + raw))

    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 6, 8, 2, 0, 0, 0))
    if exif:
        raw += chunk(b"eXIf", _tiff())
    raw += chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * 24) * 6))
    return raw + chunk(b"IEND", b"")


def _webp():
    def chunk(kind, data):
        return kind + struct.pack("<I", len(data)) + data + b"\x00" * (len(data) & 1)

    body = chunk(b"VP8X", b"\x08\x00\x00\x00" + (399).to_bytes(3, "little") + (299).to_bytes(3, "little"))
    body += chunk(b"EXIF", _tiff())
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body


def _syncsafe(value):
    return bytes((value >> shift) & 127 for shift in (21, 14, 7, 0))


def _id3(version=4, artwork=False):
    frames = []
    fields = [(b"TIT2", "Song Title"), (b"TPE1", "Artist Name"), (b"TALB", "Album Name"),
              (b"TCON", "Jazz"), (b"TLEN", "123000"), (b"TXXX", "GPS_LOCATION=privatecoordinates")]
    for name, text in fields:
        payload = b"\x00" + text.encode("latin-1")
        size = _syncsafe(len(payload)) if version == 4 else struct.pack(">I", len(payload))
        frames.append(name + size + b"\x00\x00" + payload)
    if artwork:
        payload = b"x" * (128 * 1024)
        frame = b"APIC" + (_syncsafe(len(payload)) if version == 4 else struct.pack(">I", len(payload))) + b"\x00\x00" + payload
        frames.insert(0, frame)
    body = b"".join(frames)
    return b"ID3" + bytes([version, 0, 0]) + _syncsafe(len(body)) + body


def _mp4():
    def atom(kind, raw):
        return struct.pack(">I", len(raw) + 8) + kind + raw

    fields = b"".join(atom(key, atom(b"data", b"\x00\x00\x00\x01" + b"\x00" * 4 + value)) for key, value in [
        (b"\xa9nam", b"Video Title"), (b"\xa9ART", b"Video Artist"), (b"\xa9alb", b"Video Album"),
        (b"\xa9too", b"Encoder Tool"), (b"\xa9xyz", b"privatecoordinates"),
    ])
    mvhd = atom(b"mvhd", b"\x00" * 12 + struct.pack(">II", 1000, 23500) + b"\x00" * 12)
    tkhd = atom(b"tkhd", b"\x00" * 76 + struct.pack(">II", 640 << 16, 480 << 16))
    tags = atom(b"udta", atom(b"meta", b"\x00" * 4 + atom(b"ilst", fields)))
    return atom(b"ftyp", b"isom\x00\x00\x00\x00isom") + atom(b"mdat", b"x" * (1024 * 1024)) + atom(b"moov", mvhd + atom(b"trak", tkhd) + tags)


def _flac():
    streaminfo = b"\x00" * 10 + ((8000 << 44) | (15 << 36) | 16000).to_bytes(8, "big") + b"\x00" * 16
    comments = [b"TITLE=FLAC Title", b"ARTIST=FLAC Artist", b"ALBUM=FLAC Album", b"GENRE=Jazz", b"LOCATION=privatecoordinates"]
    raw = struct.pack("<II", 0, len(comments)) + b"".join(struct.pack("<I", len(c)) + c for c in comments)
    return b"fLaC\x00" + (34).to_bytes(3, "big") + streaminfo + b"\x84" + len(raw).to_bytes(3, "big") + raw


def _wav(path):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00" * 16000)
    return path


def _write(path, raw):
    path.write_bytes(raw)
    return path


@pytest.fixture
def no_pillow(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)


@pytest.fixture
def no_mutagen(monkeypatch):
    monkeypatch.setitem(sys.modules, "mutagen", None)


class TestPhase6Dispatch:
    @pytest.mark.parametrize("extension", sorted(ImageExtractor.SUPPORTED_EXTENSIONS))
    def test_image_extensions(self, extension):
        assert ImageExtractor().can_extract(extension.upper(), "")
        assert isinstance(ExtractorRegistry().get_extractor("photo" + extension), ImageExtractor)

    @pytest.mark.parametrize("extension", sorted(MediaExtractor.SUPPORTED_EXTENSIONS))
    def test_media_extensions(self, extension):
        assert MediaExtractor().can_extract(extension.upper(), "")
        assert isinstance(ExtractorRegistry().get_extractor("recording" + extension), MediaExtractor)

    @pytest.mark.parametrize("cls,mime", [(ImageExtractor, "image/jpeg"), (MediaExtractor, "audio/mpeg")])
    def test_mime_and_unsupported(self, cls, mime):
        assert cls().can_extract(".unknown", mime)
        assert not cls().can_extract(".unknown", "application/octet-stream")


class TestImageExtraction:
    def test_png_dimensions_without_pixel_decode(self, tmp_path, monkeypatch):
        image = pytest.importorskip("PIL.Image")
        plugin = pytest.importorskip("PIL.PngImagePlugin")
        imagefile = pytest.importorskip("PIL.ImageFile")
        path = _write(tmp_path / "small.png", _png())
        calls = []

        def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError("Pixel decoding must not occur")

        monkeypatch.setattr(image.Image, "load", forbidden)
        monkeypatch.setattr(imagefile.ImageFile, "load", forbidden)
        monkeypatch.setattr(plugin.PngImageFile, "load", forbidden)
        result = ImageExtractor().extract(path)
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.dimensions == (8, 6)
        assert calls == []

    @pytest.mark.parametrize("endian", ["<", ">"])
    def test_jpeg_exif_and_gps_redaction(self, tmp_path, monkeypatch, endian, caplog):
        image = pytest.importorskip("PIL.Image")
        path = _write(tmp_path / "camera.jpg", _jpeg(endian))
        before = path.read_bytes()
        with image.open(path) as probe:
            assert probe.getexif().get_ifd(34853), "Fixture must really carry GPS data"
        original = image.Exif.get_ifd
        requested = []

        def guarded(exif, tag):
            requested.append(tag)
            assert tag != 34853, "GPS IFD must not be requested"
            return original(exif, tag)

        monkeypatch.setattr(image.Exif, "get_ifd", guarded)
        caplog.clear()
        result = ImageExtractor().extract(path)
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.dimensions == (400, 300)
        assert result.exif_tags == {"Make": "CameraCo", "Model": "Model One", "Software": "GIMP", "DateTimeOriginal": "2026:11:14 09:00:00", "LensModel": "Standard Lens"}
        assert result.created_date == "2026:11:14 09:00:00"
        assert result.keywords == ["GIMP"]
        assert 34853 not in requested
        assert "GPS" not in json.dumps(result.to_dict())
        assert not any("GPSLatitude" in record.message or "GPSLongitude" in record.message for record in caplog.records)
        assert path.read_bytes() == before

    @pytest.mark.parametrize("extension,raw,expected", [
        ("png", _png(True), (8, 6)), ("jpg", _jpeg(), (400, 300)),
        ("tiff", _tiff(), (400, 300)), ("tif", _tiff(">"), (400, 300)),
        ("webp", _webp(), (400, 300)),
        ("gif", b"GIF89a" + struct.pack("<HH", 10, 12) + b"\x00" * 6, (10, 12)),
        ("bmp", b"BM" + b"\x00" * 12 + struct.pack("<Iii", 40, 30, -20), (30, 20)),
        ("svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 60"/>', (80, 60)),
    ], ids=["png", "jpeg", "tiff-little", "tiff-big", "webp", "gif", "bmp", "svg"])
    def test_native_headers_without_pillow(self, tmp_path, no_pillow, extension, raw, expected):
        result = ImageExtractor().extract(_write(tmp_path / ("image." + extension), raw))
        assert result.extraction_status == "PARTIAL"
        assert result.dimensions == expected
        if b"CameraCo" in raw:
            assert result.exif_tags["Make"] == "CameraCo"
            assert result.exif_tags["Model"] == "Model One"
            assert result.exif_tags["LensModel"] == "Standard Lens"
            assert result.created_date == "2026:11:14 09:00:00"
        assert "GPS" not in json.dumps(result.to_dict())

    def test_webp_stays_native(self, tmp_path, monkeypatch):
        image = pytest.importorskip("PIL.Image")

        def forbidden(*args, **kwargs):
            pytest.fail("WebP must not use Pillow's full-file opener")

        monkeypatch.setattr(image, "open", forbidden)
        result = ImageExtractor().extract(_write(tmp_path / "image.webp", _webp()))
        assert result.extraction_status == "SUCCESS"
        assert result.dimensions == (400, 300)

    def test_backend_exception_cannot_leak_private_fields(self, tmp_path, monkeypatch):
        image = pytest.importorskip("PIL.Image")

        def broken(*args, **kwargs):
            raise RuntimeError("GPSLatitude=privatecoordinates")

        monkeypatch.setattr(image, "open", broken)
        result = ImageExtractor().extract(_write(tmp_path / "image.png", _png()))
        assert result.extraction_status == "PARTIAL"
        assert result.dimensions == (8, 6)
        assert "privatecoordinates" not in json.dumps(result.to_dict())

    def test_svg_entities_rejected(self, tmp_path):
        raw = b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///not-to-be-read">]><svg width="10" height="10"/>'
        result = ImageExtractor().extract(_write(tmp_path / "unsafe.svg", raw))
        assert result.extraction_status == "PARTIAL"
        assert result.dimensions is None


class TestMediaExtraction:
    @pytest.mark.parametrize("version", [3, 4])
    def test_id3_fallback(self, tmp_path, no_mutagen, version):
        result = MediaExtractor().extract(_write(tmp_path / "song.mp3", _id3(version)))
        assert result.extraction_status == "PARTIAL"
        assert (result.title, result.author, result.subject) == ("Song Title", "Artist Name", "Album Name")
        assert result.duration_seconds == 123
        assert result.keywords == ["Jazz"]
        assert "privatecoordinates" not in json.dumps(result.to_dict())

    def test_mutagen_primary_id3(self, tmp_path):
        pytest.importorskip("mutagen")
        frames = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 5
        result = MediaExtractor().extract(_write(tmp_path / "song.mp3", _id3() + frames))
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.title == "Song Title"
        assert result.author == "Artist Name"

    def test_wav_duration_and_source_preservation(self, tmp_path):
        pytest.importorskip("mutagen")
        path = _wav(tmp_path / "audio.wav")
        before = path.read_bytes()
        modified = path.stat().st_mtime_ns
        result = ExtractorRegistry().extract_metadata(str(path))
        assert result.extraction_status == "SUCCESS", result.error_message
        assert result.duration_seconds == 1
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == modified

    def test_wav_fallback(self, tmp_path, no_mutagen):
        result = MediaExtractor().extract(_wav(tmp_path / "audio.wav"))
        assert result.extraction_status == "PARTIAL"
        assert result.duration_seconds == 1

    def test_flac_fallback(self, tmp_path, no_mutagen):
        result = MediaExtractor().extract(_write(tmp_path / "song.flac", _flac()))
        assert result.extraction_status == "PARTIAL"
        assert (result.title, result.author, result.subject) == ("FLAC Title", "FLAC Artist", "FLAC Album")
        assert result.duration_seconds == 2
        assert "privatecoordinates" not in json.dumps(result.to_dict())

    @pytest.mark.parametrize("extension", ["mp4", "m4a", "mov"])
    def test_mp4_atoms_and_payload_skipping(self, tmp_path, no_mutagen, extension):
        result = MediaExtractor().extract(_write(tmp_path / ("video." + extension), _mp4()))
        assert result.extraction_status == "PARTIAL"
        assert (result.title, result.author, result.subject) == ("Video Title", "Video Artist", "Video Album")
        assert result.duration_seconds == 23.5
        assert result.dimensions == (640, 480)
        assert "Encoder Tool" in result.keywords
        assert "privatecoordinates" not in json.dumps(result.to_dict())

    def test_mutagen_allowlist_and_nonfinite_duration(self, tmp_path, monkeypatch):
        mutagen = pytest.importorskip("mutagen")
        audio = SimpleNamespace(tags={"title": ["Stream Title"], "artist": ["Artist"], "album": ["Album"], "LOCATION": ["privatecoordinates"], "genre": ["Jazz"]}, info=SimpleNamespace(length=float("nan")))
        monkeypatch.setattr(mutagen, "File", lambda *a, **kw: audio)
        result = MediaExtractor().extract(_write(tmp_path / "audio.ogg", b"OggS" + b"\x00" * 20))
        assert result.extraction_status == "SUCCESS"
        assert (result.title, result.author, result.subject) == ("Stream Title", "Artist", "Album")
        assert result.duration_seconds is None
        assert "privatecoordinates" not in json.dumps(result.to_dict())

    def test_backend_failure_retains_native_fields(self, tmp_path, monkeypatch):
        mutagen = pytest.importorskip("mutagen")

        def broken(*args, **kwargs):
            raise RuntimeError("LOCATION=privatecoordinates")

        monkeypatch.setattr(mutagen, "File", broken)
        result = MediaExtractor().extract(_write(tmp_path / "audio.mp3", _id3()))
        assert result.extraction_status == "PARTIAL"
        assert result.title == "Song Title"
        assert "privatecoordinates" not in json.dumps(result.to_dict())


class TestHeaderSafety:
    @pytest.mark.parametrize("extractor,extension", [(ImageExtractor, "jpg"), (MediaExtractor, "mp3")])
    @pytest.mark.parametrize("data", [b"", b"broken", b"\xff\xd8\xff\xe1\xff\xff"])
    def test_malformed(self, tmp_path, extractor, extension, data):
        result = extractor().extract(_write(tmp_path / ("broken." + extension), data))
        assert result.extraction_status == "PARTIAL"

    @pytest.mark.parametrize("extractor", [ImageExtractor, MediaExtractor])
    @pytest.mark.parametrize("limit", [-1, 1.5, "64", True])
    def test_invalid_limits(self, monkeypatch, extractor, limit):
        def forbidden(*args, **kwargs):
            pytest.fail("Invalid limit must be rejected before I/O")

        monkeypatch.setattr(os, "open", forbidden)
        result = extractor().extract("unused", max_bytes=limit)
        assert result.extraction_status == "FAILED"
        assert "max_bytes" in result.error_message

    @pytest.mark.parametrize("extractor", [ImageExtractor, MediaExtractor])
    def test_missing_and_nonregular_input(self, tmp_path, extractor):
        assert extractor().extract(tmp_path / "missing").extraction_status == "FAILED"
        assert extractor().extract(tmp_path).extraction_status == "FAILED"
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        assert extractor().extract(fifo).extraction_status == "FAILED"

    @pytest.mark.parametrize("limit", [0, 8, 32])
    def test_small_budget(self, tmp_path, no_pillow, limit):
        result = ImageExtractor().extract(_write(tmp_path / "small.png", _png()), max_bytes=limit)
        assert result.extraction_status == "PARTIAL"

    def test_large_artwork_does_not_bypass_budget(self, tmp_path, monkeypatch):
        path = _write(tmp_path / "artwork.mp3", _id3(artwork=True))
        reads = []
        original = HeaderReader.read

        def record(reader, size=-1):
            data = original(reader, size)
            reads.append(len(data))
            return data

        monkeypatch.setattr(HeaderReader, "read", record)
        result = MediaExtractor().extract(path, max_bytes=10**12)
        assert result.extraction_status == "PARTIAL"
        assert result.title == "Song Title"
        assert sum(reads) <= 64 * 1024

    def test_concurrent_readers(self, tmp_path, no_mutagen):
        paths = [_write(tmp_path / "one.mp3", _id3()), _write(tmp_path / "two.mp3", _id3())]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(MediaExtractor().extract, paths))
        assert all(r.title == "Song Title" for r in results)

    def test_cooperative_deadline(self, tmp_path, monkeypatch):
        path = _write(tmp_path / "small.png", _png())
        monkeypatch.setattr(ImageExtractor, "TIMEOUT_SECONDS", -1)
        assert ImageExtractor().extract(path).extraction_status == "TIMEOUT"

"""Allowlisted media tags via Mutagen and bounded binary header fallbacks."""

import struct

from src.core.file_intelligence.extractors._binary import (
    BinaryExtractor, HeaderLimit, clean, dimensions, duration, keyword,
)


def _set(result, field, value):
    value = clean(value, 64 if field == "created_date" else 256)
    if value:
        setattr(result, field, value)


def _syncsafe(raw):
    if any(value & 128 for value in raw):
        raise ValueError("Invalid ID3 size")
    value = 0
    for byte in raw:
        value = (value << 7) | byte
    return value


def _id3(reader, result):
    reader.seek(0)
    header = reader.read(10)
    if len(header) < 10 or header[3] not in (2, 3, 4):
        return
    version = header[3]
    end = min(reader.size, 10 + _syncsafe(header[6:10]))
    if header[5] & 128:
        # Whole-tag unsynchronization changes byte offsets. Do not guess.
        return
    if header[5] & 64 and version in (3, 4):
        raw = reader.read(4)
        size = _syncsafe(raw) if version == 4 else int.from_bytes(raw, "big") + 4
        if size < 4 or 10 + size > end:
            return
        reader.seek(10 + size)
    fields = {b"TIT2": "title", b"TPE1": "author", b"TALB": "subject",
              b"TDRC": "created_date", b"TYER": "created_date",
              b"TT2": "title", b"TP1": "author", b"TAL": "subject"}
    for _ in range(256):
        length = 6 if version == 2 else 10
        if reader.tell() + length > end:
            break
        frame = reader.read(length)
        if len(frame) < length or frame[0] == 0:
            break
        name = frame[:3] if version == 2 else frame[:4]
        size = int.from_bytes(frame[3:6], "big") if version == 2 else (_syncsafe(frame[4:8]) if version == 4 else int.from_bytes(frame[4:8], "big"))
        start = reader.tell()
        if size <= 0 or start + size > end:
            break
        flags = frame[9] if version != 2 else 0
        unsupported = flags & (0xE0 if version == 3 else 0x4D) if version != 2 else 0
        if not unsupported and (name in fields or name in (b"TCON", b"TSSE", b"TLEN", b"TCO", b"TEN")):
            raw = reader.read(min(size, 1024))
            if version == 4 and flags & 2:
                raw = raw.replace(b"\xff\x00", b"\xff")
            if raw and raw[0] <= 3:
                encoding = ("latin-1", "utf-16", "utf-16-be", "utf-8")[raw[0]]
                text = raw[1:].decode(encoding, errors="replace").strip("\x00 ")
                if name in fields:
                    _set(result, fields[name], text)
                elif name == b"TLEN":
                    try:
                        duration(result, float(text) / 1000)
                    except ValueError:
                        pass
                else:
                    keyword(result, text)
        reader.seek(start + size)


def _riff(reader, result):
    reader.seek(12)
    byte_rate = audio_size = None
    pending = [reader.size]
    for _ in range(256):
        if not pending:
            break
        if reader.tell() + 8 > pending[-1]:
            reader.seek(pending.pop())
            continue
        raw = reader.read(8)
        if len(raw) != 8:
            break
        kind, size = struct.unpack("<4sI", raw)
        start = reader.tell()
        end = start + size + (size & 1)
        if end > pending[-1]:
            break
        if kind == b"LIST" and size >= 4:
            category = reader.read(4)
            if category in (b"hdrl", b"INFO"):
                pending.append(end)
                continue
        elif kind == b"fmt " and size >= 16:
            data = reader.read(16)
            byte_rate = struct.unpack("<I", data[8:12])[0]
        elif kind == b"data":
            audio_size = size
        elif kind == b"avih" and size >= 40:
            data = reader.read(40)
            micros, frames, width, height = (int.from_bytes(data[pos:pos + 4], "little") for pos in (0, 16, 32, 36))
            duration(result, micros * frames / 1_000_000)
            dimensions(result, width, height)
        elif kind in (b"INAM", b"IART", b"IPRD", b"IGNR", b"ISFT"):
            value = reader.read(min(size, 1024)).rstrip(b"\x00").decode("utf-8", errors="replace")
            field = {b"INAM": "title", b"IART": "author", b"IPRD": "subject"}.get(kind)
            _set(result, field, value) if field else keyword(result, value)
        reader.seek(end)
    if byte_rate and audio_size is not None:
        duration(result, audio_size / byte_rate)


def _flac(reader, result):
    reader.seek(4)
    for _ in range(128):
        raw = reader.read(4)
        if len(raw) != 4:
            break
        last, kind, size = bool(raw[0] & 128), raw[0] & 127, int.from_bytes(raw[1:4], "big")
        start = reader.tell()
        end = start + size
        if end > reader.size:
            break
        if kind == 0 and size == 34:
            data = reader.read(34)
            value = int.from_bytes(data[10:18], "big")
            rate, samples = value >> 44, value & ((1 << 36) - 1)
            if rate:
                duration(result, samples / rate)
        elif kind == 4 and size >= 8:
            vendor = int.from_bytes(reader.read(4), "little")
            if reader.tell() + vendor + 4 > end:
                break
            reader.seek(vendor, 1)
            count = int.from_bytes(reader.read(4), "little")
            for _ in range(min(count, 128)):
                if reader.tell() + 4 > end:
                    break
                length = int.from_bytes(reader.read(4), "little")
                position = reader.tell()
                if position + length > end:
                    break
                text = reader.read(min(length, 1024)).decode("utf-8", errors="replace")
                name, _, value = text.partition("=")
                field = {"TITLE": "title", "ARTIST": "author", "ALBUM": "subject", "DATE": "created_date"}.get(name.upper())
                if field:
                    _set(result, field, value)
                elif name.upper() in ("GENRE", "ENCODER"):
                    keyword(result, value)
                reader.seek(position + length)
        reader.seek(end)
        if last:
            break


def _mp4(reader, result):
    containers = {b"moov", b"trak", b"udta", b"meta", b"ilst"}
    fields = {b"\xa9nam": "title", b"\xa9ART": "author", b"aART": "author",
              b"\xa9alb": "subject", b"\xa9day": "created_date"}
    labels = {b"\xa9gen", b"\xa9too"}
    stack = [(0, reader.size, None, 0)]
    visited = 0
    while stack and visited < 512:
        position, end, parent, depth = stack.pop()
        if position + 8 > end or depth > 8:
            continue
        reader.seek(position)
        header = reader.read(8)
        if len(header) < 8:
            break
        size, kind = struct.unpack(">I4s", header)
        header_size = 8
        if size == 1:
            size = int.from_bytes(reader.read(8), "big")
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            break
        visited += 1
        start, atom_end = position + header_size, position + size
        stack.append((atom_end, end, parent, depth))
        if kind in containers or kind in fields or kind in labels:
            stack.append((start + (4 if kind == b"meta" else 0), atom_end, kind, depth + 1))
        elif kind == b"data" and parent in set(fields) | labels and size >= header_size + 8:
            data_header = reader.read(8)
            encoding = int.from_bytes(data_header[:4], "big") & 0xFFFFFF
            raw = reader.read(min(atom_end - reader.tell(), 1024))
            if encoding in (1, 2):
                text = raw.decode("utf-8" if encoding == 1 else "utf-16-be", errors="replace")
                if parent in fields:
                    _set(result, fields[parent], text)
                else:
                    keyword(result, text)
        elif kind == b"mvhd" and atom_end - start >= 20:
            data = reader.read(min(32, atom_end - start))
            if data[0] == 0:
                rate, length = struct.unpack(">II", data[12:20])
            elif data[0] == 1 and len(data) >= 32:
                rate, length = struct.unpack(">IQ", data[20:32])
            else:
                continue
            if rate and length not in (0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                duration(result, length / rate)
        elif kind == b"tkhd" and atom_end - start >= 84:
            reader.seek(atom_end - 8)
            width, height = struct.unpack(">II", reader.read(8))
            dimensions(result, width >> 16, height >> 16)


def _mutagen_tags(audio, result):
    tags = audio.tags or {}
    mapping = {
        "title": ("TIT2", "title", "\xa9nam", "Title"),
        "author": ("TPE1", "artist", "\xa9ART", "aART", "Author"),
        "subject": ("TALB", "album", "\xa9alb", "WM/AlbumTitle"),
        "created_date": ("TDRC", "date", "\xa9day", "WM/Year"),
    }
    def value(key):
        item = tags.get(key)
        if hasattr(item, "text"):
            item = item.text
        if isinstance(item, (list, tuple)):
            item = item[0] if item else None
        # Mutagen ASF scalar wrappers expose a value property.
        if hasattr(item, "value"):
            item = item.value
        return item

    for field, keys in mapping.items():
        for key in keys:
            item = value(key)
            if clean(item):
                _set(result, field, item)
                break
    for key in ("TCON", "TSSE", "genre", "encoder", "\xa9gen", "\xa9too", "WM/Genre", "WM/EncodedBy"):
        keyword(result, value(key))
    info = getattr(audio, "info", None)
    duration(result, getattr(info, "length", None))


class MediaExtractor(BinaryExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".mp3", ".flac", ".wav", ".ogg", ".m4a", ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"])
    MIME_TYPES = frozenset(["audio/mpeg", "audio/flac", "audio/x-flac", "audio/wav", "audio/x-wav", "audio/ogg", "application/ogg", "audio/mp4", "video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/x-msvideo", "video/x-ms-wmv"])

    def _inspect(self, reader, result):
        head = reader.read(12)
        if head.startswith(b"ID3"):
            _id3(reader, result)
        elif head[:4] == b"RIFF" and head[8:12] in (b"WAVE", b"AVI "):
            _riff(reader, result)
        elif head.startswith(b"fLaC"):
            _flac(reader, result)
        elif head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free"):
            _mp4(reader, result)
        try:
            import mutagen
        except ImportError:
            result.extraction_status = "PARTIAL"
            result.error_message = "Mutagen unavailable; native header metadata only"
            return
        reader.seek(0)
        try:
            audio = mutagen.File(reader, easy=False)
            if audio is not None:
                _mutagen_tags(audio, result)
            else:
                result.extraction_status = "PARTIAL"
                result.error_message = "Media backend did not recognize a supported stream"
        except (HeaderLimit, TimeoutError):
            raise
        except Exception:
            result.extraction_status = "PARTIAL"
            result.error_message = "Media backend could not read all header metadata"

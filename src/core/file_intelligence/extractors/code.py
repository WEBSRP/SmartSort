"""Bounded, read-only lexical inspection of source code; never imports it."""

import os
import re
import shlex
import time

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor
from src.core.file_intelligence.extractors._binary import HeaderReader, HeaderLimit
from src.core.file_intelligence.extractors.text import TextExtractor


class CodeExtractor(BaseExtractor):
    LANGUAGES = {
        ".py": "Python", ".c": "C", ".cpp": "C++", ".h": "C", ".hpp": "C++",
        ".java": "Java", ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go",
        ".rs": "Rust", ".sh": "Shell", ".bash": "Shell", ".sql": "SQL", ".php": "PHP",
    }
    SUPPORTED_EXTENSIONS = frozenset(LANGUAGES)
    MIME_LANGUAGES = {
        "text/x-python": "Python", "text/x-c": "C", "text/x-c++": "C++",
        "text/x-java": "Java", "text/javascript": "JavaScript",
        "application/javascript": "JavaScript", "text/x-go": "Go",
        "text/x-rust": "Rust", "application/x-sh": "Shell", "application/sql": "SQL",
        "application/x-httpd-php": "PHP",
    }
    MAX_LINES = 200
    MAX_SYMBOLS = 128

    def can_extract(self, extension, mime_type):
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type in self.MIME_LANGUAGES

    def extract(self, file_path, max_bytes=None):
        result = ExtractedMetadata(extractor_name="CodeExtractor", extraction_status="SUCCESS")
        try:
            if max_bytes is not None and (isinstance(max_bytes, bool) or
                    not isinstance(max_bytes, int) or max_bytes < 0):
                raise ValueError("max_bytes must be a non-negative integer or None")
            limit = self.MAX_TEXT_BYTES if max_bytes is None else min(max_bytes, self.MAX_TEXT_BYTES)
            with HeaderReader(file_path, limit, self.TIMEOUT_SECONDS) as reader:
                raw = reader.read(limit)
                truncated = len(raw) < reader.size
                deadline = reader.deadline
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = raw.decode("utf-16", errors="replace")
                status = "PARTIAL" if "\ufffd" in text else "SUCCESS"
            else:
                text, status = TextExtractor._decode_bytes(raw)
            extension = os.path.splitext(os.fsdecode(file_path))[1].lower()
            result.code_language = self.LANGUAGES.get(extension)
            result.code_language = self._shebang_language(text) or result.code_language
            if "\x00" in text:
                result.extraction_status = "PARTIAL"
                result.error_message = "Binary data encountered in source sample"
                return result
            lines = text.splitlines()
            truncated = truncated or len(lines) > self.MAX_LINES
            text = "\n".join(lines[:self.MAX_LINES])
            masked, comments, intro = self._mask(text, result.code_language, deadline)
            result.text_preview = intro[:1024]
            result.title = next((line.strip()[:256] for line in intro.splitlines() if line.strip()), None)
            for comment in comments:
                for line in comment.splitlines():
                    line = line.strip().strip("* ")
                    if re.search(r"[-=]{3,}", line):
                        heading = line.strip("#*-= /\t")[:256]
                        if heading and heading not in result.headings and len(result.headings) < 64:
                            result.headings.append(heading)
            truncated = self._symbols(text, masked, result, deadline) or truncated
            result.keywords = [word[:128] for word in TextExtractor._extract_keywords(
                intro + "\n" + "\n".join(result.headings + result.code_symbols))]
            if truncated or status == "PARTIAL":
                result.extraction_status = "PARTIAL"
                result.error_message = "Source sample truncated or decoded with encoding fallback"
        except TimeoutError:
            result.extraction_status, result.error_message = "TIMEOUT", "Source inspection deadline exceeded"
        except HeaderLimit:
            result.extraction_status, result.error_message = "PARTIAL", "Source read budget exhausted"
        except Exception as exc:
            result.extraction_status, result.error_message = "FAILED", str(exc)[:512]
        return result

    @staticmethod
    def _shebang_language(text):
        if not text.startswith("#!"):
            return None
        try:
            words = shlex.split(text.splitlines()[0][2:])
        except ValueError:
            return None
        for word in words:
            name = word.rsplit("/", 1)[-1]
            if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name):
                return "Python"
            if name in ("sh", "bash", "dash", "zsh"):
                return "Shell"
            if name in ("node", "nodejs"):
                return "JavaScript"
        return None

    @staticmethod
    def _mask(text, language, deadline):
        """Blank strings/comments while retaining line positions for regexes."""
        chars, comments, leading = list(text), [], []
        i, seen_code = 0, False
        while i < len(text):
            if i % 256 == 0 and time.monotonic() > deadline:
                raise TimeoutError
            start = i
            comment = False
            if text.startswith("/*", i) and language not in ("Python", "Shell"):
                end = text.find("*/", i + 2)
                i = len(text) if end < 0 else end + 2
                value, comment = text[start + 2:i - 2 if end >= 0 else i], True
            elif ((text[i] == "#" and language in ("Python", "Shell", "PHP")) or
                  (text.startswith("//", i) and language not in ("Python", "Shell", "SQL")) or
                  (text.startswith("--", i) and language == "SQL")):
                end = text.find("\n", i)
                i = len(text) if end < 0 else end
                width = 1 if text[start] == "#" else 2
                value, comment = text[start + width:i], True
            elif (text[i] in "\"'`" or (language == "Python" and text[i] in "rRuU" and
                  text[i + 1:i + 4] in ('\"\"\"', "'''"))):
                prefix = 0 if text[i] in "\"'`" else 1
                quote = text[i + prefix]
                if language == "Python" and text.startswith(quote * 3, i + prefix):
                    quote *= 3
                j = i + prefix + len(quote)
                while j < len(text):
                    if text[j] == "\\":
                        j += 2
                    elif text.startswith(quote, j):
                        break
                    else:
                        j += 1
                i = min(len(text), j + len(quote))
                value = text[start + prefix + len(quote):j]
                if not seen_code and len(quote) == 3:
                    leading.append(value)
                seen_code = True
            else:
                if not text[i].isspace():
                    seen_code = True
                i += 1
                continue
            if comment:
                comments.append(value)
                if not seen_code and not value.startswith("!") and not re.search(r"coding[:=]", value):
                    leading.append(value.strip())
            for k in range(start, i):
                if chars[k] != "\n":
                    chars[k] = " "
        return "".join(chars), comments, "\n".join(leading).strip()

    def _symbols(self, text, masked, result, deadline):
        patterns = (
            r"\b(?:class|struct|interface|trait|enum)\s+([A-Za-z_]\w*)",
            r"\b(?:def|fn|function)\s+([A-Za-z_]\w*)\s*\(",
            r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(",
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=.*=>",
            r"^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\s*\)\s*\{",
            r"^\s*function\s+([A-Za-z_]\w*)\s*\{",
            r"^\s*(?:[A-Za-z_][\w:*&<>\[\],]*\s+)+([A-Za-z_~][\w:~]*)\s*\([^;{}]*\)\s*(?:const\s*)?\{",
            r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE|TABLE|VIEW)\s+([A-Za-z_]\w*)",
        )
        go_imports, truncated = False, False
        for original, line in zip(text.splitlines(), masked.splitlines()):
            if time.monotonic() > deadline:
                raise TimeoutError
            values = []
            for pattern in patterns:
                flags = re.I if "CREATE" in pattern else 0
                values.extend(match.group(1) for match in re.finditer(pattern, line, flags))
            match = re.match(r"\s*(?:from\s+([\w.]+)\s+import\b|import\s+(.+)|(?:pub\s+)?use\s+([\w:]+))", line)
            if match:
                payload = next(v for v in match.groups() if v is not None)
                for part in payload.split(","):
                    name = re.match(r"\s*(?:static\s+)?([A-Za-z_][\w.:]*)", part)
                    if name:
                        values.append(name.group(1))
            if re.match(r"\s*#\s*include\b", line):
                match = re.search(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", original)
                if match:
                    values.append(match.group(1))
            if result.code_language in ("JavaScript", "TypeScript", "Go"):
                if (re.match(r"\s*(?:import|export)\b", line) or go_imports) and not original.lstrip().startswith(("//", "/*", "*")):
                    values.extend(re.findall(r"[\"']([^\"']+)[\"']", original))
                if result.code_language == "Go":
                    go_imports = bool(re.match(r"\s*import\s*\(", line)) or (go_imports and ")" not in line)
            for value in values:
                value = value[:256]
                if value not in result.code_symbols:
                    if len(result.code_symbols) < self.MAX_SYMBOLS:
                        result.code_symbols.append(value)
                    else:
                        truncated = True
        return truncated
